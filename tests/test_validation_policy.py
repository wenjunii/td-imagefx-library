from __future__ import annotations

import contextlib
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools import verify_local


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class LocalSafetyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.enterContext(contextlib.redirect_stderr(self.output))
        self.numpy = self.enterContext(mock.patch.object(verify_local.importlib, "import_module"))
        self.run = self.enterContext(mock.patch.object(verify_local.subprocess, "run"))

    def test_default_runs_history_then_one_verifier_from_repository_root(self) -> None:
        self.assertEqual(verify_local.main([]), 0)
        self.numpy.assert_called_once_with("numpy")
        self.assertEqual(self.run.call_args_list, [
            mock.call(
                [sys.executable, "tools/check_immutable_history.py", "--base", "origin/main"],
                cwd=ROOT, check=True,
            ),
            mock.call([sys.executable, "tools/verify_repository.py"], cwd=ROOT, check=True),
        ])
        self.assertIn("Native rendering, CUDA", self.output.getvalue())

    def test_explicit_local_base_is_passed_as_one_argument(self) -> None:
        self.assertEqual(verify_local.main(["--base", "HEAD~3"]), 0)
        self.assertEqual(self.run.call_args_list[0].args[0][-1], "HEAD~3")
        self.assertNotIn("shell", self.run.call_args_list[0].kwargs)

    def test_failed_history_check_stops_before_repository_checks(self) -> None:
        self.run.side_effect = subprocess.CalledProcessError(1, ["history-check"])
        self.assertEqual(verify_local.main([]), 1)
        self.assertEqual(self.run.call_count, 1)
        self.assertNotIn("[local] PASS", self.output.getvalue())
        self.assertIn("No fetch or repair was attempted", self.output.getvalue())

    def test_failed_repository_check_is_not_reported_as_success(self) -> None:
        self.run.side_effect = [None, subprocess.CalledProcessError(1, ["verify"])]
        self.assertEqual(verify_local.main([]), 1)
        self.assertEqual(self.run.call_count, 2)
        self.assertNotIn("[local] PASS", self.output.getvalue())

    def test_missing_executable_fails_without_installing_anything(self) -> None:
        self.run.side_effect = FileNotFoundError("not installed")
        self.assertEqual(verify_local.main([]), 1)
        self.assertEqual(self.run.call_count, 1)

    def test_missing_numpy_reports_setup_instructions_without_running_checks(self) -> None:
        self.numpy.side_effect = ImportError("not installed")
        self.assertEqual(verify_local.main([]), 2)
        self.run.assert_not_called()
        self.assertIn("requirements-test.txt", self.output.getvalue())

    def test_broken_numpy_runtime_is_a_failure_not_a_skipped_test_suite(self) -> None:
        self.numpy.side_effect = OSError("native dependency missing")
        self.assertEqual(verify_local.main([]), 2)
        self.run.assert_not_called()

    def test_old_python_fails_before_loading_numpy_or_starting_checks(self) -> None:
        with mock.patch.object(verify_local.sys, "version_info", (3, 10, 11)):
            self.assertEqual(verify_local.main([]), 2)
        self.numpy.assert_not_called()
        self.run.assert_not_called()

    def test_empty_or_option_like_base_is_rejected(self) -> None:
        for base in ("", " ", "--help"):
            with self.subTest(base=base), self.assertRaises(SystemExit) as caught:
                verify_local.main(["--base=" + base])
            self.assertEqual(caught.exception.code, 2)
        self.run.assert_not_called()

    def test_help_is_read_only_and_does_not_require_numpy(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            verify_local.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.numpy.assert_not_called()
        self.run.assert_not_called()


class WorkflowPolicyTests(unittest.TestCase):
    """Guard the intended policy; a workflow linter checks full YAML semantics."""

    @staticmethod
    def _read(name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    @staticmethod
    def _section(source: str, key: str) -> str:
        match = re.search(r"(?ms)^" + re.escape(key) + r":\n(.*?)(?=^\S|\Z)", source)
        if match is None:
            raise AssertionError("Missing workflow section: " + key)
        return match.group(1)

    def test_automatic_verification_is_one_job_for_main_and_pull_requests(self) -> None:
        source = self._read("verify.yml")
        self.assertEqual(self._section(source, "on").strip(), "push:\n    branches: [main]\n  pull_request:")
        jobs = re.findall(r"(?m)^  ([a-z][\w-]*):$", self._section(source, "jobs"))
        self.assertEqual(jobs, ["verify"])
        self.assertIn("name: Repository safety check", source)
        self.assertIn("runs-on: ubuntu-latest", source)
        self.assertIn('python-version: "3.11"', source)
        self.assertNotIn("matrix:", source)

    def test_automatic_history_uses_event_baseline_and_full_checkout(self) -> None:
        source = self._read("verify.yml")
        self.assertIn("github.event.pull_request.base.sha || github.event.before", source)
        self.assertIn("fetch-depth: 0", source)
        self.assertIn('python tools/verify_local.py --base "$IMMUTABLE_BASE"', source)
        self.assertIn('if [ "$IMMUTABLE_BASE" = "' + "0" * 40 + '" ]; then', source)
        self.assertNotIn("pull_request_target", source)

    def test_full_matrix_is_manual_and_keeps_all_six_combinations(self) -> None:
        source = self._read("compatibility.yml")
        self.assertEqual(self._section(source, "on").strip(), "workflow_dispatch:")
        self.assertIn("os: [ubuntu-latest, windows-latest, macos-latest]", source)
        self.assertIn('python: ["3.11", "3.13"]', source)
        self.assertIn("fail-fast: false", source)

    def test_newer_verification_runs_cancel_old_work_on_the_same_target(self) -> None:
        for filename in ("verify.yml", "compatibility.yml"):
            with self.subTest(filename=filename):
                section = self._section(self._read(filename), "concurrency")
                self.assertIn("cancel-in-progress: true", section)
                self.assertIn("github.ref", section)
        self.assertIn("github.event.pull_request.number", self._read("verify.yml"))

    def test_each_workflow_runs_one_verifier_without_duplicate_unit_or_compile_steps(self) -> None:
        for filename in ("verify.yml", "compatibility.yml", "prepare-release.yml"):
            with self.subTest(filename=filename):
                source = self._read(filename)
                calls = re.findall(r"python tools/verify_(?:local|repository)\.py", source)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("-m unittest", source)
                self.assertNotIn("-m compileall", source)
                self.assertIn("python -m pip install -r requirements-test.txt", source)

    def test_verification_retains_read_only_tokens_and_no_artifact_uploads(self) -> None:
        for filename in ("verify.yml", "compatibility.yml"):
            with self.subTest(filename=filename):
                source = self._read(filename)
                self.assertEqual(self._section(source, "permissions").strip(), "contents: read")
                self.assertIn("persist-credentials: false", source)
                self.assertNotIn("upload-artifact", source)
                self.assertNotIn("actions/cache", source)

    def test_all_workflow_actions_remain_commit_pinned(self) -> None:
        for path in WORKFLOWS.glob("*.yml"):
            for action in re.findall(r"(?m)^\s+uses: (\S+)", path.read_text(encoding="utf-8")):
                with self.subTest(workflow=path.name, action=action):
                    self.assertRegex(action, r"^[\w./-]+@[0-9a-f]{40}$")

    def test_release_remains_manual_with_history_check_and_limited_artifact_retention(self) -> None:
        source = self._read("prepare-release.yml")
        trigger = self._section(source, "on")
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("push:", trigger)
        self.assertNotIn("schedule:", trigger)
        self.assertIn("python tools/check_immutable_history.py", source)
        self.assertIn("retention-days: 14", source)
        self.assertIn("diff -qr dist-a dist-b", source)


if __name__ == "__main__":
    unittest.main()
