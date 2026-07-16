from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tdimagefx.archive import StageLimits, stage_package
from tdimagefx.compatibility import RuntimeContext
from tdimagefx.errors import FeedError, SecurityError, ValidationError
from tdimagefx.feed import SourcePolicy, load_update_feed
from tdimagefx.registry import MAX_FEED_PACKAGES, LocalRegistry, UpdateFeed, validate_update_feed_data
from tests.helpers import feed_data, write_package_zip
from tools import check_immutable_history, package_release


class FeedBindingTests(unittest.TestCase):
    def test_feed_id_is_bound_to_configured_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "feed.json"
            source.write_text(
                json.dumps(feed_data("https://example.test/effect.zip", "b" * 64, 20)),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(FeedError, "source binding"):
                load_update_feed(
                    source,
                    policy=SourcePolicy(allow_file=True, file_root=root),
                    expected_feed_id="tdimagefx.different.feed",
                )

    def test_feed_counts_and_channel_hierarchy_are_bounded(self) -> None:
        data = feed_data("https://example.test/effect.zip", "b" * 64, 20)
        data["packages"] = [data["packages"][0]] * (MAX_FEED_PACKAGES + 1)
        self.assertTrue(any("package limit" in issue for issue in validate_update_feed_data(data)))

        data = feed_data("https://example.test/effect.zip", "b" * 64, 20)
        data["packages"][0]["releases"][0]["channel"] = "beta"
        with self.assertRaisesRegex(ValidationError, "hierarchy"):
            UpdateFeed.from_data(data)

    def test_candidate_output_redacts_artifact_tokens_and_ambiguous_versions_fail(self) -> None:
        data = feed_data("https://example.test/effect.zip?token=do-not-log#secret", "b" * 64, 20)
        feed = UpdateFeed.from_data(data)
        candidate = feed.updates(
            {}, RuntimeContext("windows", "x86_64", "3.11.0", "2025.1")
        )[0].to_dict()
        self.assertEqual(candidate["artifact_url"], "https://example.test/effect.zip")

        ambiguous = feed_data("https://example.test/effect.zip", "b" * 64, 20)
        second = json.loads(json.dumps(ambiguous["packages"][0]["releases"][0]))
        ambiguous["packages"][0]["releases"][0]["version"] = "1.1.0+one"
        second["version"] = "1.1.0+two"
        ambiguous["packages"][0]["releases"].append(second)
        with self.assertRaisesRegex(ValidationError, "ambiguous SemVer"):
            UpdateFeed.from_data(ambiguous)

    def test_unhashable_feed_values_report_validation_errors(self) -> None:
        data = feed_data("https://example.test/effect.zip", "b" * 64, 20)
        data["channel"] = {}
        data["packages"][0]["kind"] = []
        data["packages"][0]["releases"][0]["artifacts"][0]["os"] = [{}]
        issues = validate_update_feed_data(data)
        self.assertTrue(issues)
        with self.assertRaises(ValidationError):
            UpdateFeed.from_data(data)


class StagingBindingTests(unittest.TestCase):
    def test_stage_requires_a_non_empty_artifact_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "effect.zip"
            write_package_zip(artifact)
            store = root / "store"
            with self.assertRaisesRegex(ValidationError, "non-empty SHA-256"):
                stage_package(
                    artifact,
                    store,
                    expected_sha256="",
                    policy=SourcePolicy(allow_file=True, file_root=root),
                )
            self.assertFalse(store.exists())

    def test_feed_stage_binds_manifest_and_redacts_persisted_feed_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "effect.zip"
            artifact_sha256, _manifest = write_package_zip(artifact)
            with zipfile.ZipFile(artifact) as archive:
                manifest_sha256 = hashlib.sha256(archive.read("package.json")).hexdigest()
            store = root / "store"
            stage_package(
                artifact,
                store,
                expected_sha256=artifact_sha256,
                expected_manifest_sha256=manifest_sha256,
                expected_id="tdimagefx.test.effect",
                expected_version="1.0.0",
                policy=SourcePolicy(allow_file=True, file_root=root),
                feed_url="https://updates.example.test/feed.json?token=do-not-store#fragment",
                feed_id="tdimagefx.test.feed",
                feed_sha256="c" * 64,
            )
            registry = LocalRegistry.from_data(json.loads((store / "registry.json").read_text(encoding="utf-8")))
            source = registry.packages["tdimagefx.test.effect"][0].source
            self.assertEqual(source["feed_url"], "https://updates.example.test/feed.json")
            self.assertNotIn("token", json.dumps(source))
            self.assertEqual(source["feed_id"], "tdimagefx.test.feed")
            self.assertEqual(source["feed_sha256"], "c" * 64)

    def test_feed_stage_requires_and_checks_manifest_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "effect.zip"
            artifact_sha256, _manifest = write_package_zip(artifact)
            with self.assertRaisesRegex(SecurityError, "requires bound"):
                stage_package(
                    artifact,
                    root / "missing-binding",
                    expected_sha256=artifact_sha256,
                    policy=SourcePolicy(allow_file=True),
                    feed_url="https://updates.example.test/feed.json",
                )
            with zipfile.ZipFile(artifact) as archive:
                manifest_sha256 = hashlib.sha256(archive.read("package.json")).hexdigest()
            with self.assertRaisesRegex(SecurityError, "expected_id, expected_version"):
                stage_package(
                    artifact,
                    root / "missing-identity-binding",
                    expected_sha256=artifact_sha256,
                    expected_manifest_sha256=manifest_sha256,
                    policy=SourcePolicy(allow_file=True),
                    feed_url="https://updates.example.test/feed.json",
                    feed_id="tdimagefx.test.feed",
                    feed_sha256="c" * 64,
                )
            with self.assertRaisesRegex(SecurityError, "manifest SHA-256 mismatch"):
                stage_package(
                    artifact,
                    root / "bad-digest",
                    expected_sha256=artifact_sha256,
                    expected_manifest_sha256="0" * 64,
                    policy=SourcePolicy(allow_file=True),
                )
            with self.assertRaisesRegex(ValidationError, "max_compression_ratio"):
                stage_package(
                    artifact,
                    root / "bad-limit",
                    expected_sha256=artifact_sha256,
                    policy=SourcePolicy(allow_file=True),
                    limits=StageLimits(max_compression_ratio=float("nan")),
                )


class ReleaseOutputTests(unittest.TestCase):
    def _release_source(self, root: Path) -> None:
        package_root = root / "packages" / "tdimagefx.test.effect" / "1.0.0"
        package_root.mkdir(parents=True)
        (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
        (root / "THIRD_PARTY_NOTICES.md").write_text("None\n", encoding="utf-8")
        _, manifest = write_package_zip(root / "fixture.zip")
        manifest["provenance"] = {
            "origin": "original",
            "source": {"type": "original"},
            "changelog": "CHANGELOG.md",
            "examples": ["examples/basic.toe"],
            "presets": ["presets/default.json"],
        }
        (package_root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        (package_root / "shaders").mkdir()
        (package_root / "shaders" / "effect.frag").write_text("// shader\n", encoding="utf-8")
        (package_root / "CHANGELOG.md").write_text("# Changes\n", encoding="utf-8")
        (package_root / "examples").mkdir()
        (package_root / "examples" / "basic.toe").write_bytes(b"example")
        (package_root / "presets").mkdir()
        (package_root / "presets" / "default.json").write_text("{}\n", encoding="utf-8")

    def test_release_writes_checksums_and_provenance_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._release_source(root)
            output = root / "dist" / "packages"
            feed = root / "dist" / "update-feed.json"
            with mock.patch.object(package_release, "ROOT", root):
                package_release.build_release(
                    output,
                    feed,
                    release_tag="v1.2.3",
                    generated_at="2030-01-02T03:04:05Z",
                    repository="example/imagefx",
                    source_revision="a" * 40,
                )
            provenance = json.loads((root / "dist" / "release-provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["source_revision"], "a" * 40)
            sums = (root / "dist" / "SHA256SUMS").read_text(encoding="ascii")
            self.assertIn("update-feed.json", sums)
            self.assertIn("release-provenance.json", sums)
            artifact = next((root / "dist" / "packages").glob("*.zip"))
            with zipfile.ZipFile(artifact) as archive:
                names = set(archive.namelist())
            self.assertTrue({"CHANGELOG.md", "examples/basic.toe", "presets/default.json"} <= names)

    def test_failed_release_does_not_expose_a_partial_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._release_source(root)
            destination = root / "dist"
            with mock.patch.object(package_release, "ROOT", root), mock.patch.object(
                package_release, "package_zip", side_effect=package_release.ReleaseError("injected failure")
            ):
                with self.assertRaisesRegex(package_release.ReleaseError, "injected failure"):
                    package_release.build_release(
                        destination / "packages",
                        destination / "update-feed.json",
                        release_tag="v1.2.3",
                        generated_at="2030-01-02T03:04:05Z",
                        repository="example/imagefx",
                    )
            self.assertFalse(destination.exists())

    def test_release_feed_must_share_the_release_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(package_release.ReleaseError, "escapes"):
                package_release.build_release(
                    root / "dist" / "packages",
                    root / "outside-feed.json",
                    release_tag="v1.2.3",
                    generated_at="2030-01-02T03:04:05Z",
                    repository="example/imagefx",
                )


class ImmutableHistoryTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL)

    def test_existing_version_is_immutable_but_new_version_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "tests@example.test")
            self._git(root, "config", "user.name", "Tests")
            old = root / "packages" / "tdimagefx.test.effect" / "1.0.0"
            old.mkdir(parents=True)
            (old / "package.json").write_text("old\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "base")
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

            new = root / "packages" / "tdimagefx.test.effect" / "2.0.0"
            new.mkdir(parents=True)
            (new / "package.json").write_text("new\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "new version")
            self.assertEqual(check_immutable_history.immutable_changes(root, base), [])

            (old / "package.json").write_text("changed\n", encoding="utf-8")
            self.assertTrue(
                any("changed published file" in item for item in check_immutable_history.worktree_changes(root, base))
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "bad mutation")
            self.assertTrue(
                any("changed published file" in item for item in check_immutable_history.immutable_changes(root, base))
            )

    def test_untracked_files_in_old_versions_are_rejected_but_new_versions_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "tests@example.test")
            self._git(root, "config", "user.name", "Tests")
            old = root / "packages" / "tdimagefx.test.effect" / "1.0.0"
            old.mkdir(parents=True)
            (old / "package.json").write_text("old\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "base")
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

            new = root / "packages" / "tdimagefx.test.effect" / "2.0.0"
            new.mkdir(parents=True)
            (new / "package.json").write_text("new\n", encoding="utf-8")
            self.assertEqual(check_immutable_history.worktree_changes(root, base), [])

            (old / "unexpected.txt").write_text("mutation\n", encoding="utf-8")
            self.assertTrue(
                any("added file to published version" in item for item in check_immutable_history.worktree_changes(root, base))
            )


if __name__ == "__main__":
    unittest.main()
