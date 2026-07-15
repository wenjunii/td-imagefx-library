from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tdimagefx.compatibility import RuntimeContext
from tdimagefx.errors import ValidationError
from tdimagefx.manifest import PackageManifest, load_manifest
from tdimagefx.registry import LocalRegistry, UpdateFeed, validate_local_registry_data
from tdimagefx.semver import Version

from tests.helpers import clone, feed_data, manifest_data


class ManifestTests(unittest.TestCase):
    def test_valid_manifest(self) -> None:
        manifest = PackageManifest.from_data(manifest_data())
        self.assertEqual(manifest.id, "tdimagefx.test.effect")
        self.assertEqual(str(manifest.version), "1.0.0")

    def test_load_manifest_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "package.json")
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(ValidationError) as caught:
                load_manifest(path)
        self.assertIn("duplicate", str(caught.exception))

    def test_rejects_unknown_and_unsafe_entrypoint(self) -> None:
        data = manifest_data()
        data["unexpected"] = True
        data["entrypoints"]["shader"] = "../escape.frag"
        with self.assertRaises(ValidationError) as caught:
            PackageManifest.from_data(data)
        self.assertIn("unexpected", str(caught.exception))
        self.assertIn("unsafe path", str(caught.exception))

    def test_rejects_parameter_contract_errors(self) -> None:
        data = manifest_data()
        data["parameters"].append({"id": "mix", "name": "invalid name", "type": "mystery"})
        with self.assertRaises(ValidationError) as caught:
            PackageManifest.from_data(data)
        self.assertIn("duplicates", str(caught.exception))
        self.assertIn("TouchDesigner", str(caught.exception))


class RegistryTests(unittest.TestCase):
    def test_empty_local_registry_round_trip(self) -> None:
        registry = LocalRegistry.empty(".")
        loaded = LocalRegistry.from_data(registry.to_dict())
        self.assertEqual(loaded.library_root, registry.library_root)
        self.assertEqual(loaded.packages, {})

    def test_local_registry_rejects_duplicate_package(self) -> None:
        registry = LocalRegistry.empty(".").to_dict()
        record = {
            "id": "tdimagefx.test.effect",
            "installed_versions": [
                {
                    "version": "1.0.0",
                    "install_path": "packages/x/1.0.0",
                    "manifest_path": "packages/x/1.0.0/package.json",
                    "installed_at": "2026-07-15T12:00:00Z",
                    "source": {"type": "bundled"},
                    "integrity": {"manifest_sha256": None, "artifact_sha256": None, "verification": "unverified"},
                    "status": "ready",
                }
            ],
        }
        registry["packages"] = [clone(record), clone(record)]
        self.assertTrue(any("duplicates" in issue for issue in validate_local_registry_data(registry)))

    def test_update_feed_parses_and_selects_latest_compatible(self) -> None:
        data = feed_data("https://example.test/effect.zip", "b" * 64, 12)
        older = clone(data["packages"][0]["releases"][0])
        older["version"] = "1.0.1"
        data["packages"][0]["releases"].append(older)
        feed = UpdateFeed.from_data(data)
        runtime = RuntimeContext("windows", "x86_64", "3.11.0", 2023.1)
        updates = feed.updates({"tdimagefx.test.effect": Version.parse("1.0.0")}, runtime)
        self.assertEqual(len(updates), 1)
        self.assertEqual(str(updates[0].release.version), "1.1.0")

    def test_update_feed_excludes_yanked_and_wrong_artifact_platform(self) -> None:
        data = feed_data("https://example.test/effect.zip", "b" * 64, 12)
        data["packages"][0]["releases"][0]["yanked"] = True
        feed = UpdateFeed.from_data(data)
        runtime = RuntimeContext("windows", "x86_64", "3.11.0", 2023.1)
        self.assertEqual(feed.updates({}, runtime), ())

    def test_update_feed_rejects_insecure_artifact_transport(self) -> None:
        data = feed_data("http://example.test/effect.zip", "b" * 64, 12)
        with self.assertRaises(ValidationError):
            UpdateFeed.from_data(data)


if __name__ == "__main__":
    unittest.main()
