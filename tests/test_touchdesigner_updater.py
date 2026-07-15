from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "touchdesigner" / "extensions" / "UpdaterExt.py"
SPEC = importlib.util.spec_from_file_location("tdimagefx_touchdesigner_updater", MODULE_PATH)
UPDATER_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(UPDATER_MODULE)


class TouchDesignerUpdaterTransportTests(unittest.TestCase):
    def test_semver_key_handles_build_metadata_and_numeric_prereleases(self):
        key = UPDATER_MODULE.UpdaterExt._version_key
        self.assertEqual(key("1.2.3+build.7"), key("1.2.3+other"))
        self.assertLess(key("1.2.3-beta.2"), key("1.2.3-beta.10"))
        self.assertLess(key("1.2.3-beta.10"), key("1.2.3"))

    def test_reads_bounded_local_json_feed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "feed.json"
            expected = {"schema_version": 1, "packages": []}
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(UPDATER_MODULE.UpdaterExt._load_json_url(path.as_uri(), 1), expected)

    def test_rejects_http_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "Only HTTPS and file"):
            UPDATER_MODULE.UpdaterExt._load_json_url("http://example.invalid/feed.json", 1)

    def test_rejects_feed_larger_than_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large-feed.json"
            path.write_bytes(b" " * (UPDATER_MODULE.MAX_FEED_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                UPDATER_MODULE.UpdaterExt._load_json_url(path.as_uri(), 1)

    def test_rejects_https_downgrade_redirect(self):
        request = urllib.request.Request("https://example.invalid/feed.json")
        handler = UPDATER_MODULE._HttpsOnlyRedirectHandler()
        with self.assertRaisesRegex(ValueError, "redirect to HTTPS"):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://example.invalid/feed.json",
            )

    def test_status_write_does_not_follow_predictable_or_destination_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status_root = root / ".imagefx"
            status_root.mkdir()
            outside = root / "outside.txt"
            outside.write_text("unchanged", encoding="utf-8")
            legacy_temporary = status_root / "update-status.tmp"
            destination = status_root / "update-status.json"
            try:
                legacy_temporary.symlink_to(outside)
            except OSError as exc:
                self.skipTest("symbolic links are unavailable: {}".format(exc))

            payload = {"schema_version": 1, "status": "complete"}
            UPDATER_MODULE.UpdaterExt._write_json_atomic(root, destination, payload)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), payload)
            self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged")

            destination.unlink()
            destination.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                UPDATER_MODULE.UpdaterExt._write_json_atomic(root, destination, payload)
            self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged")

    def test_auto_check_schedules_a_promoted_public_method(self):
        class Toggle:
            def __bool__(self):
                return True

        class Parameters:
            Autocheck = Toggle()

        class Owner:
            path = "/project1/td_imagefx/update_manager"
            par = Parameters()

        calls = []
        original_run = getattr(UPDATER_MODULE, "run", None)
        original_op = getattr(UPDATER_MODULE, "op", None)
        UPDATER_MODULE.run = lambda command, **kwargs: calls.append((command, kwargs))
        UPDATER_MODULE.op = type("OpGlobals", (), {"TDResources": object()})()
        try:
            updater = UPDATER_MODULE.UpdaterExt(Owner())
            self.assertTrue(updater.StartAutoCheck())
        finally:
            if original_run is None:
                del UPDATER_MODULE.run
            else:
                UPDATER_MODULE.run = original_run
            if original_op is None:
                del UPDATER_MODULE.op
            else:
                UPDATER_MODULE.op = original_op

        self.assertEqual(len(calls), 1)
        self.assertIn(".AutoTick(1)", calls[0][0])
        self.assertNotIn("._AutoTick", calls[0][0])


if __name__ == "__main__":
    unittest.main()
