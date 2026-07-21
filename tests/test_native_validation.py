from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools import record_native_validation


class NativeValidationRecordTests(unittest.TestCase):
    def test_visual_modules_are_required_core_assets(self) -> None:
        self.assertIn(
            "touchdesigner/core/ParticleRandomMove.tox",
            record_native_validation.CORE_ASSETS,
        )
        self.assertIn(
            "touchdesigner/core/InkFlowFusion.tox",
            record_native_validation.CORE_ASSETS,
        )
        self.assertIn(
            "touchdesigner/core/GlitchFusion.tox",
            record_native_validation.CORE_ASSETS,
        )
        self.assertIn(
            "touchdesigner/core/ColorAdjustment.tox",
            record_native_validation.CORE_ASSETS,
        )

    def _fixture(self, root: Path) -> Path:
        package = root / "packages" / "tdimagefx.test.effect" / "1.0.0"
        (package / "tox").mkdir(parents=True, exist_ok=True)
        (package / "package.json").write_text(
            json.dumps({"id": "tdimagefx.test.effect", "version": "1.0.0"}) + "\n",
            encoding="utf-8",
        )
        (package / "tox" / "effect.tox").write_bytes(b"effect")
        (root / "TD_ImageFX_Library.toe").write_bytes(b"project")
        for relative in record_native_validation.CORE_ASSETS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode("utf-8"))
        docs = root / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "benchmark-data.json").write_text(
            json.dumps({"resolution": "64x64", "frames_per_sample": 3, "gpu": "test"}),
            encoding="utf-8",
        )
        builder = root / record_native_validation.BUILDER_SOURCE
        builder.parent.mkdir(parents=True, exist_ok=True)
        builder.write_text("# fixture builder\n", encoding="utf-8")
        builder_sha256 = hashlib.sha256(builder.read_bytes()).hexdigest()
        report = root / "build-report.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2030-01-02T03:04:05+00:00",
                    "library_version": "1.2.3",
                    "touchdesigner_version": "2025.1",
                    "touchdesigner_build": "12345",
                    "touchdesigner_os": "Windows",
                    "touchdesigner_architecture": "64-bit",
                    "builder": {
                        "path": record_native_validation.BUILDER_SOURCE,
                        "sha256": builder_sha256,
                    },
                    "effects": [{
                        "id": "tdimagefx.test.effect",
                        "version": "1.0.0",
                        "tox_action": "created",
                    }],
                    "errors": [],
                    "shader_errors": {},
                    "preview_errors": {},
                }
            ),
            encoding="utf-8",
        )
        return report

    def test_record_binds_environment_counts_and_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = record_native_validation.build_record(root, self._fixture(root))
            self.assertEqual(record["catalog"], {"current_effects": 1, "package_versions": 1})
            self.assertEqual(record["touchdesigner"]["build"], "12345")
            self.assertEqual(record["builder"]["path"], record_native_validation.BUILDER_SOURCE)
            self.assertEqual(len(record["artifacts"]), 10)
            self.assertTrue(all(len(item["sha256"]) == 64 for item in record["artifacts"]))

    def test_record_rejects_a_build_with_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._fixture(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["shader_errors"] = {"tdimagefx.test.effect": "compile failed"}
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(record_native_validation.NativeValidationError, "shader_errors"):
                record_native_validation.build_record(root, report)

    def test_record_rejects_stale_builder_or_effect_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._fixture(root)
            builder = root / record_native_validation.BUILDER_SOURCE
            builder.write_text("# changed after build\n", encoding="utf-8")
            with self.assertRaisesRegex(
                record_native_validation.NativeValidationError, "builder source"
            ):
                record_native_validation.build_record(root, report)

            report = self._fixture(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["effects"][0]["version"] = "9.9.9"
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                record_native_validation.NativeValidationError, "latest manifest identities"
            ):
                record_native_validation.build_record(root, report)


if __name__ == "__main__":
    unittest.main()
