from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tdimagefx.compatibility import RuntimeContext, check_compatibility, check_fx_api, check_package_compatibility
from tdimagefx.manifest import PackageManifest
from tdimagefx.errors import StateError, ValidationError
from tdimagefx.lockfile import LockDependency, LockPin, Lockfile, load_lockfile, write_lockfile
from tdimagefx.semver import Version
from tests.helpers import manifest_data


SPEC = {
    "touchdesigner_min_build": 2022.2,
    "touchdesigner_max_build": "2025.9",
    "os": ["windows"],
    "architectures": ["x86_64"],
}


class CompatibilityTests(unittest.TestCase):
    def test_compatible_runtime(self) -> None:
        report = check_compatibility(SPEC, RuntimeContext("windows", "amd64", "3.11.0", "2023.1"))
        self.assertTrue(report.compatible)
        self.assertTrue(report.verified)

    def test_reports_mismatches(self) -> None:
        report = check_compatibility(SPEC, RuntimeContext("macos", "arm64", "3.11.0", "2026.1"))
        self.assertFalse(report.compatible)
        self.assertGreaterEqual(len(report.errors), 3)

    def test_unknown_touchdesigner_build_can_be_warning_or_error(self) -> None:
        runtime = RuntimeContext("windows", "x86_64", "3.11.0")
        relaxed = check_compatibility(SPEC, runtime)
        strict = check_compatibility(SPEC, runtime, strict_unknown=True)
        self.assertTrue(relaxed.compatible)
        self.assertFalse(relaxed.verified)
        self.assertFalse(strict.compatible)

    def test_effect_api_major_and_minimum_are_checked(self) -> None:
        self.assertTrue(check_fx_api("1.2", "1.3").compatible)
        self.assertFalse(check_fx_api("1.3", "1.2").compatible)
        self.assertFalse(check_fx_api("2.0", "1.9").compatible)
        manifest = PackageManifest.from_data(manifest_data())
        report = check_package_compatibility(
            manifest,
            RuntimeContext("windows", "x86_64", "3.11.0", "2023.1"),
            supported_fx_api="1.0",
        )
        self.assertTrue(report.compatible)


def pin(version: str = "1.2.3") -> LockPin:
    return LockPin(
        id="tdimagefx.test.effect",
        version=Version.parse(version),
        kind="effect",
        channel="stable",
        source_feed="https://example.test/feed.json",
        manifest_sha256="a" * 64,
        artifact_sha256="b" * 64,
        requested=True,
        dependencies=(LockDependency("tdimagefx.test.base", Version.parse("1.0.0")),),
    )


def base_pin() -> LockPin:
    return LockPin(
        id="tdimagefx.test.base",
        version=Version.parse("1.0.0"),
        kind="core",
        channel="stable",
        source_feed="https://example.test/feed.json",
        manifest_sha256="c" * 64,
        artifact_sha256="d" * 64,
        requested=False,
    )


class LockfileTests(unittest.TestCase):
    def test_exact_lockfile_round_trip(self) -> None:
        lockfile = Lockfile.create(fx_api="1.0", touchdesigner_build=2023.1, project_id="show-a", packages=(pin(), base_pin()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "tdimagefx.lock.json")
            write_lockfile(path, lockfile)
            loaded = load_lockfile(path)
        self.assertEqual(str(loaded.get("tdimagefx.test.effect").version), "1.2.3")
        self.assertEqual(loaded.project_id, "show-a")

    def test_rejects_range_in_exact_pin(self) -> None:
        data = Lockfile.create(fx_api="1.0", touchdesigner_build=2023.1).to_dict()
        item = pin().to_dict()
        item["version"] = ">=1.0.0"
        data["packages"] = [item]
        with self.assertRaises(ValidationError):
            Lockfile.from_data(data)

    def test_pin_replacement_requires_explicit_permission(self) -> None:
        lockfile = Lockfile.create(fx_api="1.0", touchdesigner_build=2023.1, packages=(pin(), base_pin()))
        with self.assertRaises(StateError):
            lockfile.with_pin(pin("2.0.0"))
        replaced = lockfile.with_pin(pin("2.0.0"), replace_existing=True)
        self.assertEqual(str(replaced.get("tdimagefx.test.effect").version), "2.0.0")

    def test_source_feed_rejects_credentials_query_and_fragment_data(self) -> None:
        unsafe_sources = (
            "https://user:password@example.test/feed.json",
            "https://example.test/feed.json?token=secret",
            "https://example.test/feed.json#private",
            "file:///tmp/feed.json?token=secret",
        )
        for source in unsafe_sources:
            with self.subTest(source=source):
                data = Lockfile.create(fx_api="1.0", touchdesigner_build=2023.1).to_dict()
                item = pin().to_dict()
                item["source_feed"] = source
                data["packages"] = [item]
                with self.assertRaisesRegex(ValidationError, "credential-free"):
                    Lockfile.from_data(data)


if __name__ == "__main__":
    unittest.main()
