from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from tests.helpers import feed_data, manifest_data


MODULE_PATH = Path(__file__).resolve().parents[1] / "touchdesigner" / "extensions" / "UpdaterExt.py"
SPEC = importlib.util.spec_from_file_location("tdimagefx_touchdesigner_updater", MODULE_PATH)
UPDATER_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(UPDATER_MODULE)


class TouchDesignerUpdaterTransportTests(unittest.TestCase):
    def test_source_identity_is_exact_and_rejects_unsafe_url_data(self):
        identity = UPDATER_MODULE._source_identity
        self.assertEqual(
            identity("HTTPS://EXAMPLE.TEST/feed.json"),
            "https://example.test/feed.json",
        )
        self.assertNotEqual(
            identity("https://example.test/feed.json"),
            identity("https://example.test:443/feed.json"),
        )
        self.assertNotEqual(
            identity("https://example.test/feed.json"),
            identity("https://example.test/feed.json/"),
        )
        unsafe_urls = (
            "https://example.test/feed.json?token=secret",
            "https://example.test/feed.json#fragment",
            "https://user:secret@example.test/feed.json",
            "https://example.test:not-a-port/feed.json",
            "https://example.test:65536/feed.json",
            "file://user:secret@localhost/feed.json",
            "file:///tmp/feed.json?token=secret",
            "file:///tmp/feed.json#fragment",
        )
        for unsafe_url in unsafe_urls:
            with self.subTest(url=unsafe_url):
                with self.assertRaises(ValueError):
                    identity(unsafe_url)

    def test_fetch_rejects_unsafe_urls_before_network_access(self):
        unsafe_urls = (
            "https://example.test/feed.json?token=secret",
            "https://example.test/feed.json#fragment",
            "https://user:secret@example.test/feed.json",
            "https://example.test:not-a-port/feed.json",
            "https://example.test:65536/feed.json",
        )
        with mock.patch.object(
            UPDATER_MODULE.urllib.request,
            "build_opener",
            side_effect=AssertionError("network access was attempted"),
        ):
            for unsafe_url in unsafe_urls:
                with self.subTest(url=unsafe_url):
                    with self.assertRaises(ValueError):
                        UPDATER_MODULE.UpdaterExt._load_json_url(unsafe_url, 1)

    def test_redaction_and_safe_error_handle_malformed_urls_without_leaks(self):
        malformed_urls = (
            "https://user:secret@example.test:not-a-port/feed?token=private#fragment",
            "https://[broken/feed?token=private",
            "http://user:secret@example.test/feed?token=private#fragment",
        )
        for malformed_url in malformed_urls:
            with self.subTest(url=malformed_url):
                redacted = UPDATER_MODULE._redact_url(malformed_url)
                safe_error = UPDATER_MODULE._safe_error(
                    ValueError("could not fetch {}".format(malformed_url))
                )
                for secret in ("user", "secret", "token", "private", "fragment"):
                    self.assertNotIn(secret, redacted)
                    self.assertNotIn(secret, safe_error)

    def test_project_lock_rejects_unsafe_source_feed_urls(self):
        unsafe_urls = (
            "https://example.test/feed.json?token=secret",
            "https://example.test/feed.json#fragment",
            "https://user:secret@example.test/feed.json",
            "https://example.test:not-a-port/feed.json",
            "https://example.test:65536/feed.json",
            "file://user:secret@localhost/feed.json",
            "file:///tmp/feed.json?token=secret",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "packages" / "tdimagefx.test.effect" / "1.0.0" / "package.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")
            lock = {
                "schema_version": 1,
                "generated_at": "2026-07-16T12:00:00Z",
                "fx_api": "1.0",
                "touchdesigner_build": "2025.1",
                "packages": [{
                    "id": "tdimagefx.test.effect",
                    "version": "1.0.0",
                    "kind": "effect",
                    "channel": "stable",
                    "source_feed": None,
                    "manifest_sha256": None,
                    "artifact_sha256": None,
                    "requested": True,
                    "dependencies": [],
                }],
            }
            lock_path = root / "tdimagefx.lock.json"
            for unsafe_url in unsafe_urls:
                with self.subTest(url=unsafe_url):
                    lock["packages"][0]["source_feed"] = unsafe_url
                    lock_path.write_text(json.dumps(lock), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        UPDATER_MODULE.UpdaterExt._project_lock(root)

    def test_reconciles_duplicate_candidates_by_lock_source_then_trust(self):
        def candidate(source, trust, version, manifest_digest, artifact_digest):
            source_url = "https://{}.example.test/feed.json".format(source)
            return {
                "id": "tdimagefx.test.effect",
                "source": source,
                "source_trust": trust,
                "available": version,
                "manifest_sha256": manifest_digest,
                "artifact_sha256": artifact_digest,
                "_source_identity": UPDATER_MODULE._source_identity(source_url),
            }

        community = candidate("community", "community", "99.0.0", "c" * 64, "d" * 64)
        first_party = candidate("official", "first_party", "1.1.0", "a" * 64, "b" * 64)
        updates, issues = UPDATER_MODULE.UpdaterExt._reconcile_candidates(
            [community, first_party], {}
        )
        self.assertEqual(issues, [])
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["source"], "official")
        self.assertNotIn("_source_identity", updates[0])

        locked = {
            "tdimagefx.test.effect": {
                "source_feed": "https://community.example.test/feed.json"
            }
        }
        updates, issues = UPDATER_MODULE.UpdaterExt._reconcile_candidates(
            [community, first_party], locked
        )
        self.assertEqual(issues, [])
        self.assertEqual(updates[0]["source"], "community")

        conflict = candidate("mirror", "first_party", "1.1.0", "e" * 64, "f" * 64)
        updates, issues = UPDATER_MODULE.UpdaterExt._reconcile_candidates(
            [first_party, conflict], {}
        )
        self.assertEqual(updates, [])
        self.assertTrue(any("conflicting digests" in issue for issue in issues))

    def test_semver_key_handles_build_metadata_and_numeric_prereleases(self):
        key = UPDATER_MODULE.UpdaterExt._version_key
        self.assertEqual(key("1.2.3+build.7"), key("1.2.3+other"))
        self.assertLess(key("1.2.3-beta.2"), key("1.2.3-beta.10"))
        self.assertLess(key("1.2.3-beta.10"), key("1.2.3"))

    def test_semver_key_rejects_redos_shape_and_invalid_identifiers(self):
        key = UPDATER_MODULE.UpdaterExt._version_key
        adversarial = "0.0.0-0." + "--." * 10_000 + "!"
        with self.assertRaises(ValueError) as raised:
            key(adversarial)
        self.assertLess(len(str(raised.exception)), 200)

        for value in (
            "1.0.0-alpha..1",
            "1.0.0-alpha+build+second",
            "1.0.0-α",
            "1.0.0+build_1",
            1,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                key(value)

        self.assertLess(key("1.0.0-alpha--beta.7+build.001"), key("1.0.0"))

    def test_unknown_touchdesigner_build_is_compatible_but_unverified(self):
        spec = {
            "touchdesigner_min_build": 2022.2,
            "touchdesigner_max_build": None,
            "os": ["windows"],
            "architectures": ["x86_64"],
        }
        self.assertEqual(
            UPDATER_MODULE.UpdaterExt._compatibility_report(
                spec,
                {"os": "windows", "architecture": "amd64", "touchdesigner_build": None},
            ),
            (True, False),
        )

    def test_reads_bounded_local_json_feed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "feed.json"
            expected = {"schema_version": 1, "packages": []}
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(UPDATER_MODULE.UpdaterExt._load_json_url(path.as_uri(), 1), expected)

    def test_rejects_duplicate_json_keys_and_feed_source_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "feed.json"
            path.write_text('{"schema_version":1,"schema_version":1,"packages":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                UPDATER_MODULE.UpdaterExt._load_json_url(path.as_uri(), 1)

        feed = feed_data("https://example.test/effect.zip", "b" * 64, 20)
        with self.assertRaisesRegex(ValueError, "configured source"):
            UPDATER_MODULE.UpdaterExt._validate_feed(feed, "tdimagefx.different.feed")

    def test_worker_applies_channel_compatibility_and_project_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root = root / "packages" / "tdimagefx.test.effect" / "1.0.0"
            package_root.mkdir(parents=True)
            package_manifest = manifest_data("1.0.0")
            (package_root / "package.json").write_text(json.dumps(package_manifest), encoding="utf-8")

            registry_root = root / "registry"
            registry_root.mkdir()
            feed = feed_data("https://example.test/effect.zip", "b" * 64, 20)
            feed["feed_id"] = "tdimagefx.test.source"
            feed_path = registry_root / "feed.json"
            feed_path.write_text(json.dumps(feed), encoding="utf-8")
            feed_digest = hashlib.sha256(feed_path.read_bytes()).hexdigest()
            config_root = root / "config"
            config_root.mkdir()
            config = {
                "schema_version": 1,
                "sources": [{
                    "id": "tdimagefx.test.source",
                    "name": "Test source",
                    "url": "registry/feed.json",
                    "enabled": True,
                    "trust": "first_party",
                    "auto_stage": False,
                    "auto_activate": False,
                    "sha256": feed_digest,
                }],
            }
            (config_root / "update_sources.json").write_text(json.dumps(config), encoding="utf-8")
            lock = {
                "schema_version": 1,
                "generated_at": "2026-07-16T12:00:00Z",
                "fx_api": "1.0",
                "touchdesigner_build": "2025.1",
                "packages": [{
                    "id": "tdimagefx.test.effect",
                    "version": "1.0.0",
                    "kind": "effect",
                    "channel": "stable",
                    "source_feed": feed_path.as_uri(),
                    "manifest_sha256": hashlib.sha256((package_root / "package.json").read_bytes()).hexdigest(),
                    "artifact_sha256": None,
                    "requested": True,
                    "dependencies": [],
                }],
            }
            (root / "tdimagefx.lock.json").write_text(json.dumps(lock), encoding="utf-8")
            output = root / ".imagefx" / "status.json"
            UPDATER_MODULE.UpdaterExt._worker_check(
                root,
                "stable",
                1,
                output,
                {"os": "windows", "architecture": "amd64", "touchdesigner_build": "2025.1"},
            )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["project_lock"]["packages"], 1)
            self.assertEqual(result["updates"][0]["locked"], "1.0.0")
            self.assertEqual(result["updates"][0]["feed_sha256"], feed_digest)

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
