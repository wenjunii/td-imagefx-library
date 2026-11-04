"""Cleanup safety tests use disposable Git repositories, never real show files."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools import task_cleanup as cleanup


class TaskCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        self.folder = self.root / "build/task-artifacts/sample"
        self.folder.mkdir(parents=True)
        self.path = self.folder / "scratch.txt"
        self.path.write_text("disposable fixture", encoding="utf-8")
        self.relative = self.path.relative_to(self.root).as_posix()
        self.recycle = self.enterContext(mock.patch.object(cleanup, "recycle"))

    def record(self, *paths):
        return cleanup.record(self.root, "sample", list(paths or [self.relative]), "scratch", "Created by this test")

    def mutate_manifest(self, fn):
        path = self.folder / "cleanup.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_record_captures_exact_hash_size_and_purpose(self):
        data = self.record()
        self.assertEqual(data, cleanup.read_manifest(self.root, "sample"))
        self.assertEqual(data["entries"][0]["bytes"], self.path.stat().st_size)
        self.assertEqual(data["entries"][0]["files"], 1)
        self.assertEqual(len(data["entries"][0]["sha256"]), 64)
        self.recycle.assert_not_called()

    def test_default_dry_run_preserves_files_and_does_not_write_report(self):
        self.record()
        report = cleanup.clean(self.root, "sample")
        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "dry-run")
        self.assertTrue(self.path.exists())
        self.assertFalse((self.folder / "cleanup-report.json").exists())
        self.recycle.assert_not_called()

    def test_apply_requires_verification_assertion(self):
        self.record()
        with self.assertRaisesRegex(cleanup.CleanupError, "verification"):
            cleanup.clean(self.root, "sample", apply=True)
        self.recycle.assert_not_called()

    def test_changed_file_is_retained_even_when_size_is_same(self):
        self.record()
        self.path.write_bytes(b"x" * self.path.stat().st_size)
        with self.assertRaisesRegex(cleanup.CleanupError, "changed"):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_all_targets_are_preflighted_before_any_recycle(self):
        other = self.folder / "second.txt"
        other.write_text("second")
        self.record(self.relative, other.relative_to(self.root).as_posix())
        other.write_text("changed")
        with self.assertRaises(cleanup.CleanupError):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_directory_fingerprint_includes_new_files_and_empty_directories(self):
        directory = self.folder / "copy"
        directory.mkdir()
        original = cleanup.fingerprint(self.root, directory)
        (directory / "empty").mkdir()
        self.assertNotEqual(original, cleanup.fingerprint(self.root, directory))
        (directory / "added.txt").write_text("new")
        self.assertEqual(cleanup.fingerprint(self.root, directory)["files"], 1)

    def test_paths_cannot_escape_task_or_address_runtime_folders(self):
        values = ["../outside", "build/task-artifacts/sample/../other/file", "/absolute",
                  "C:/absolute", "C:relative", "//server/share", "build\\task-artifacts\\sample\\x",
                  "build/task-artifacts/other/file", "build/task-artifacts/sample", ".imagefx/shows/x.json",
                  "build/puppet-cuda-venv/x", "build/task-artifacts/sample/x:stream",
                  "build/task-artifacts/sample/x.", "build/task-artifacts/sample/x ",
                  "build/task-artifacts/sample//x", "build/task-artifacts/sample/./x"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(cleanup.CleanupError):
                cleanup.target_path(self.root, "sample", value)

    def test_task_slug_and_metadata_names_are_guarded(self):
        for task in ("../other", "UPPER", "", "a" * 65, "a/b"):
            with self.subTest(task=task), self.assertRaises(cleanup.CleanupError):
                cleanup.task_folder(self.root, task)
        for name in cleanup.RESERVED:
            with self.subTest(name=name), self.assertRaises(cleanup.CleanupError):
                cleanup.target_path(self.root, "sample", "build/task-artifacts/sample/" + name)

    def test_models_and_runtime_environment_contents_are_not_registered(self):
        directory = self.folder / "copy"
        directory.mkdir()
        for name in ("weights.onnx", "model.pt", "pose.task", "model.safetensors", "model.pth"):
            path = directory / name
            path.write_text("model fixture")
            with self.subTest(name=name), self.assertRaises(cleanup.CleanupError):
                cleanup.fingerprint(self.root, directory)
            path.unlink()
        (directory / "models").mkdir()
        with self.assertRaises(cleanup.CleanupError):
            cleanup.fingerprint(self.root, directory)

    def test_hard_link_cannot_remove_a_shared_source(self):
        source = self.root / "source.txt"
        source.write_text("keep")
        linked = self.folder / "linked.txt"
        os.link(source, linked)
        with self.assertRaisesRegex(cleanup.CleanupError, "Hard-linked"):
            self.record(linked.relative_to(self.root).as_posix())
        self.assertEqual(source.read_text(), "keep")

    def test_windows_reparse_point_is_refused_on_any_platform(self):
        original = Path.lstat
        def simulated(path, *args, **kwargs):
            if path == self.path:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", simulated), self.assertRaisesRegex(cleanup.CleanupError, "reparse"):
            cleanup.reject_links(self.root, self.path)

    def test_linked_ancestor_is_refused_before_reading_children(self):
        original = Path.lstat
        def simulated(path, *args, **kwargs):
            if path == self.folder.parent:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "lstat", simulated), self.assertRaises(cleanup.CleanupError):
            cleanup.target_path(self.root, "sample", self.relative)

    def test_force_tracked_artifact_is_never_cleaned(self):
        self.record()
        subprocess.run(["git", "add", "-f", "--", self.relative], cwd=self.root, check=True, capture_output=True)
        with self.assertRaisesRegex(cleanup.CleanupError, "Tracked"):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_directory_with_force_tracked_descendant_is_never_cleaned(self):
        directory = self.folder / "copy"
        directory.mkdir()
        child = directory / "source.txt"
        child.write_text("keep")
        relative = directory.relative_to(self.root).as_posix()
        self.record(relative)
        subprocess.run(["git", "add", "-f", "--", child.relative_to(self.root).as_posix()],
                       cwd=self.root, check=True, capture_output=True)
        with self.assertRaisesRegex(cleanup.CleanupError, "Tracked"):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_git_failure_is_not_treated_as_untracked_success(self):
        with mock.patch.object(cleanup.subprocess, "run", side_effect=subprocess.CalledProcessError(128, ["git"])):
            with self.assertRaises(subprocess.CalledProcessError):
                self.record()
        self.assertTrue(self.path.exists())

    def test_nonignored_artifact_is_refused(self):
        (self.root / ".gitignore").write_text("")
        with self.assertRaisesRegex(cleanup.CleanupError, "Git-ignored"):
            self.record()

    def test_duplicate_and_overlapping_targets_are_refused(self):
        self.record()
        with self.assertRaises(cleanup.CleanupError):
            self.record()
        directory = self.folder / "copy"
        directory.mkdir()
        child = directory / "child.txt"
        child.write_text("new")
        with self.assertRaises(cleanup.CleanupError):
            self.record(directory.relative_to(self.root).as_posix(), child.relative_to(self.root).as_posix())
        self.assertEqual(len(cleanup.read_manifest(self.root, "sample")["entries"]), 1)

    def test_invalid_manifest_is_fail_closed(self):
        self.record()
        originals = (self.folder / "cleanup.json").read_text()
        for change in (lambda d: d.update(schema_version=True), lambda d: d.update(entries=[]),
                       lambda d: d["entries"][0].update(kind=[]), lambda d: d["entries"][0].update(files=True),
                       lambda d: d["entries"][0].update(sha256="wrong"), lambda d: d.update(extra="unknown")):
            (self.folder / "cleanup.json").write_text(originals)
            self.mutate_manifest(change)
            with self.assertRaises(cleanup.CleanupError):
                cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_report_hard_link_is_refused_before_recycling(self):
        self.record()
        source = self.root / "source.txt"
        source.write_text("keep")
        os.link(source, self.folder / "cleanup-report.json")
        with self.assertRaises(cleanup.CleanupError):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()
        self.assertEqual(source.read_text(), "keep")

    def test_manifest_hard_link_cannot_overwrite_shared_data(self):
        source = self.root / "shared.json"
        source.write_text("keep")
        os.link(source, self.folder / "cleanup.json")
        with self.assertRaises(cleanup.CleanupError):
            self.record()
        self.assertEqual(source.read_text(), "keep")

    def test_empty_file_and_directory_are_valid_disposable_artifacts(self):
        self.path.write_bytes(b"")
        empty = self.folder / "empty"
        empty.mkdir()
        self.record(self.relative, empty.relative_to(self.root).as_posix())
        report = cleanup.clean(self.root, "sample")
        self.assertEqual((report["bytes"], report["files"]), (0, 1))
        self.recycle.assert_not_called()

    def test_missing_artifact_is_retained_as_error_not_success(self):
        self.record()
        self.path.unlink()
        with self.assertRaises(cleanup.CleanupError):
            cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.recycle.assert_not_called()

    def test_success_records_completed_items_and_keeps_metadata(self):
        self.record()
        self.recycle.side_effect = lambda path: path.unlink()
        report = cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.assertTrue(report["ok"])
        self.assertEqual(report["completed"], [self.relative])
        self.assertEqual(report["remaining"], [])
        self.assertTrue((self.folder / "cleanup.json").exists())
        self.assertEqual(json.loads((self.folder / "cleanup-report.json").read_text()), report)
        with self.assertRaises(cleanup.CleanupError):
            self.record()

    def test_recycle_failure_has_no_permanent_delete_fallback(self):
        self.record()
        self.recycle.side_effect = OSError("unavailable")
        report = cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["remaining"], [self.relative])
        self.assertTrue(self.path.exists())

    def test_change_after_preflight_is_caught_before_recycle(self):
        self.record()
        original = cleanup.fingerprint
        calls = [0]
        def mutate_on_second(root, path):
            calls[0] += 1
            if calls[0] == 2:
                path.write_text("changed just before recycling")
            return original(root, path)
        with mock.patch.object(cleanup, "fingerprint", side_effect=mutate_on_second):
            report = cleanup.clean(self.root, "sample", apply=True, verified=True)
        self.assertFalse(report["ok"])
        self.recycle.assert_not_called()

    def test_cli_default_is_dry_run_and_invalid_flags_fail(self):
        self.record()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cleanup.main(["--root", str(self.root), "clean", "sample"]), 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "dry-run")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cleanup.main(["--root", str(self.root), "clean", "sample", "--apply"]), 1)
        self.recycle.assert_not_called()


class RecycleBackendTests(unittest.TestCase):
    def test_backend_success_without_removing_target_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "scratch.txt"
            path.write_text("keep")
            with mock.patch.object(cleanup.sys, "platform", "win32"), \
                    mock.patch.object(cleanup.shutil, "which", return_value="pwsh"), \
                    mock.patch.object(cleanup.subprocess, "run"):
                with self.assertRaisesRegex(cleanup.CleanupError, "did not remove"):
                    cleanup.recycle(path)
            self.assertTrue(path.exists())

    def test_nonwindows_refuses_without_deleting(self):
        with mock.patch.object(cleanup.sys, "platform", "linux"), mock.patch.object(cleanup.subprocess, "run") as run:
            with self.assertRaisesRegex(cleanup.CleanupError, "no permanent-delete fallback"):
                cleanup.recycle(Path("unused"))
        run.assert_not_called()

    def test_missing_powershell_refuses_without_deleting(self):
        with mock.patch.object(cleanup.sys, "platform", "win32"), mock.patch.object(cleanup.shutil, "which", return_value=None):
            with self.assertRaises(cleanup.CleanupError):
                cleanup.recycle(Path("unused"))

    def test_windows_uses_literal_environment_argument_and_explicit_recycle_option(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "name with 'quotes'; dollar$.txt"
            path.write_text("temporary")
            with mock.patch.object(cleanup.sys, "platform", "win32"), mock.patch.object(cleanup.shutil, "which", return_value="pwsh"), \
                    mock.patch.object(cleanup.subprocess, "run", side_effect=lambda *a, **kw: path.unlink()) as run:
                cleanup.recycle(path)
            args, kwargs = run.call_args
            self.assertEqual(args[0][-1], cleanup.RECYCLE_COMMAND)
            self.assertNotIn(str(path), args[0][-1])
            self.assertEqual(kwargs["env"]["IMAGEFX_CLEANUP_TARGET"], str(path))
            self.assertNotIn("shell", kwargs)
            self.assertIn("SendToRecycleBin", cleanup.RECYCLE_COMMAND)
            self.assertNotIn("DeletePermanently", cleanup.RECYCLE_COMMAND)


if __name__ == "__main__":
    unittest.main()
