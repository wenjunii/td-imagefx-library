import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from tdimagefx.errors import SecurityError
from tools import prepare_offline_handoff as handoff


class OfflineHandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Handoff Test")
        self.git("config", "user.email", "handoff-test@example.invalid")
        self.git("config", "core.autocrlf", "true")
        self.git("config", "core.excludesFile", str(self.root/"nonexistent-global-ignore"))
        self.write(".gitignore", "build/\n.imagefx/\n")
        self.write("README.md", "Committed guide\n")
        self.native_files = (handoff.MAIN_TOE, "touchdesigner/core/Library.tox", "packages/tdimagefx.test/1.0.0/tox/Effect.tox")
        self.show_source = "src/tdimagefx/show.py"
        self.module_source = "touchdesigner/scripts/show_rehearsal.py"
        for path in (*self.native_files, handoff.BUILDER, self.show_source, self.module_source):
            self.write(path, f"Fixture for {path}\n")
        self.record = dict(schema_version=1,
            results=dict(builder_errors=0, shader_errors=0, preview_errors=0),
            builder=dict(path=handoff.BUILDER, sha256=self.digest(handoff.BUILDER)),
            show_sources={self.show_source: self.digest(self.show_source)},
            module_sources={self.module_source: self.digest(self.module_source)},
            artifacts=[dict(path=p, bytes=(self.root/p).stat().st_size, sha256=self.digest(p))
                       for p in self.native_files])
        self.write_record()
        self.commit()
        self.pinned = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode("utf-8"))

    def digest(self, path):
        return hashlib.sha256((self.root/path).read_bytes()).hexdigest()

    def write_record(self):
        self.write(handoff.NATIVE_RECORD, json.dumps(self.record))

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--no-gpg-sign", "-m", "Snapshot")

    def prepare(self, revision="HEAD", target="5090"):
        return handoff.prepare_handoff(self.root, revision, target)

    def assert_no_handoff(self):
        parent = self.root/"build/handoffs/5090"
        self.assertFalse(list(parent.iterdir()) if parent.exists() else [])

    def test_export_pins_old_commit_and_ignores_worktree_and_local_show(self):
        self.write("README.md", "Newer committed guide\n")
        self.commit()
        self.write("README.md", "Dirty uncommitted guide\n")
        self.write(".imagefx/shows/current.json", "Local fixture only")
        self.write("private.mov", "Untracked fixture")
        folder = self.prepare(self.pinned[:12])
        result = json.loads((folder/"handoff.json").read_bytes())
        self.assertEqual(result["source_commit"], self.pinned)
        self.assertEqual(result["status"], "prepared_local_only")
        self.assertFalse(result["target_runtime_validated"])
        self.assertEqual(result["native_artifacts_verified"], 3)
        archive = folder/result["archive"]
        self.assertEqual(result["archive_sha256"], self.digest(archive))
        self.assertEqual((folder/"SHA256.txt").read_text(encoding="utf-8").split()[0], result["archive_sha256"])
        self.assertTrue((folder/"INSTALL.txt").is_file())
        with zipfile.ZipFile(archive) as contents:
            prefix = f"td-imagefx-library-{self.pinned[:12]}/"
            self.assertEqual(contents.read(prefix + "README.md"), b"Committed guide\n")
            self.assertFalse(any(".imagefx" in name or name.endswith("private.mov") for name in contents.namelist()))
        self.assertEqual((self.root/"README.md").read_bytes(), b"Dirty uncommitted guide\n")

    def test_does_not_replace_prepared_handoff(self):
        first = self.prepare()
        old = (first/"handoff.json").read_bytes()
        with self.assertRaisesRegex(handoff.HandoffError, "already exists"):
            self.prepare()
        self.assertEqual((first/"handoff.json").read_bytes(), old)

    def test_rejects_bad_target_and_missing_revision_before_writing(self):
        for target in ("../another", "user@machine", "con"):
            with self.subTest(target=target), self.assertRaises((handoff.HandoffError, SecurityError)):
                self.prepare(target=target)
        with self.assertRaisesRegex(handoff.HandoffError, "rev-parse"):
            self.prepare(revision="--other-option")
        self.assertFalse((self.root/"build").exists())

    def test_archive_attributes_cannot_substitute_or_omit_committed_data(self):
        self.write("README.md", "Git format: $Format:%H$\n")
        for rule, error in (("export-subst", "committed blob"), ("export-ignore", "inventory")):
            with self.subTest(rule=rule):
                self.write(".gitattributes", f"README.md {rule}\n")
                self.commit()
                with self.assertRaisesRegex(handoff.HandoffError, error):
                    self.prepare()
                self.assert_no_handoff()

    def test_refuses_committed_media_and_machine_local_path(self):
        self.write("media/private.mp4", "Synthetic fixture")
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "Machine-local file, media or model"):
            self.prepare()
        self.assert_no_handoff()
        self.git("rm", "-q", "media/private.mp4")
        self.write(".imagefx/shows/current.json", "Synthetic fixture")
        self.git("add", "-f", ".imagefx/shows/current.json")
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "Machine-local file, media or model"):
            self.prepare()
        self.assert_no_handoff()

    def test_only_public_codex_example_allowed(self):
        self.write(".codex/config.toml.example", "# Example settings only\n")
        self.commit()
        self.assertTrue((self.prepare()/"handoff.json").is_file())
        self.write(".codex/config.toml", "# Synthetic machine settings\n")
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "Machine-local file"):
            self.prepare()

    def test_redacts_credential_finding_and_leaves_no_ready_output(self):
        fixture = "ghp_" + ("w" * 40)
        self.write("config.txt", fixture)
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "Credential finding") as ctx:
            self.prepare()
        self.assertNotIn(fixture, str(ctx.exception))
        self.assert_no_handoff()

    def test_refuses_stale_toe_hash(self):
        self.write(handoff.MAIN_TOE, "Changed after native verification")
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "Recorded native hash mismatch"):
            self.prepare()
        self.assert_no_handoff()

    def test_refuses_incomplete_provenance(self):
        self.record["artifacts"].pop()
        self.write_record()
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "does not cover"):
            self.prepare()
        self.assert_no_handoff()

    def test_refuses_destination_not_git_ignored(self):
        self.write(".gitignore", ".imagefx/\n")
        self.commit()
        with self.assertRaisesRegex(handoff.HandoffError, "must be Git-ignored"):
            self.prepare()
        self.assertFalse((self.root/"build").exists())
