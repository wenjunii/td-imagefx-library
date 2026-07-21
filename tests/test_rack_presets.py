from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESET_ROOT = ROOT / "presets" / "rack"
EXTENSION_PATH = ROOT / "touchdesigner" / "extensions" / "FxRackExt.py"
VECTOR_LENGTHS = {"xy": 2, "xyz": 3, "rgba": 4}


def _load_rack_module():
    spec = importlib.util.spec_from_file_location("tdimagefx_preset_rack", EXTENSION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RACK_MODULE = _load_rack_module()


class ShippedRackPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preset_paths = sorted(PRESET_ROOT.glob("*.json"))
        cls.manifests = {}
        for manifest_path in sorted((ROOT / "packages").glob("*/*/package.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            key = (manifest["id"], manifest["version"])
            if key in cls.manifests:
                raise AssertionError(f"duplicate installed package: {key}")
            cls.manifests[key] = manifest

    def test_collection_contains_the_curated_and_starter_presets(self):
        self.assertGreaterEqual(len(self.preset_paths), 10)
        self.assertLessEqual(
            {
                "analog-motion",
                "chromatic-motion",
                "cinematic-finish",
                "clean-key-matte",
                "depth-parallax",
                "dream-glow",
                "feedback-tunnel",
                "filmic-grade",
                "graphic-mask",
                "print-halftone",
            },
            {path.stem for path in self.preset_paths},
        )

    def test_every_preset_passes_the_runtime_schema(self):
        for preset_path in self.preset_paths:
            with self.subTest(preset=preset_path.name):
                payload = preset_path.read_bytes()
                self.assertLessEqual(len(payload), RACK_MODULE.MAX_PRESET_BYTES)
                preset = json.loads(
                    payload,
                    object_pairs_hook=RACK_MODULE._reject_duplicate_keys,
                )
                normalized = RACK_MODULE.FxRackExt.ValidatePreset(preset)
                self.assertEqual(normalized, preset)

    def test_every_compact_preset_resolves_to_an_exact_eight_slot_state(self):
        for preset_path in self.preset_paths:
            with self.subTest(preset=preset_path.name):
                preset = json.loads(preset_path.read_text(encoding="utf-8"))
                normalized = RACK_MODULE.FxRackExt.ValidatePreset(preset)
                complete = RACK_MODULE.FxRackExt._complete_preset_slots(normalized["slots"])
                populated = {slot["index"] for slot in normalized["slots"]}
                self.assertEqual([slot["index"] for slot in complete], list(range(1, 9)))
                for slot in complete:
                    if slot["index"] not in populated:
                        self.assertIsNone(slot["package"])
                        self.assertFalse(slot["enabled"])

    def test_every_slot_targets_an_installed_manifest_and_valid_parameters(self):
        for preset_path in self.preset_paths:
            preset = json.loads(preset_path.read_text(encoding="utf-8"))
            for slot in preset["slots"]:
                package = slot["package"]
                key = (package["id"], package["version"])
                with self.subTest(preset=preset_path.name, slot=slot["index"], package=key):
                    self.assertIn(key, self.manifests)
                    manifest = self.manifests[key]
                    parameters = {item["name"]: item for item in manifest["parameters"]}
                    for name, value in slot["parameters"].items():
                        self.assertNotIn(name, RACK_MODULE.SYSTEM_PARAMETER_NAMES)
                        self.assertIn(name, parameters)
                        self._assert_parameter_value(value, parameters[name])

    def _assert_parameter_value(self, value, definition):
        parameter_type = definition["type"]
        if parameter_type == "toggle":
            self.assertIsInstance(value, bool)
            return

        if parameter_type in VECTOR_LENGTHS:
            self.assertIsInstance(value, list)
            self.assertEqual(len(value), VECTOR_LENGTHS[parameter_type])
            for component in value:
                self._assert_finite_number(component, definition)
            return

        if parameter_type in {"float", "int"}:
            self._assert_finite_number(value, definition)
            if parameter_type == "int":
                self.assertEqual(value, int(value))
            return

        if parameter_type in {"string", "menu"}:
            self.assertIsInstance(value, str)
            return

        self.fail(f"unsupported preset parameter type: {parameter_type}")

    def _assert_finite_number(self, value, definition):
        self.assertIsInstance(value, (int, float))
        self.assertNotIsInstance(value, bool)
        self.assertTrue(math.isfinite(value))
        if "min" in definition:
            self.assertGreaterEqual(value, definition["min"])
        if "max" in definition:
            self.assertLessEqual(value, definition["max"])


if __name__ == "__main__":
    unittest.main()
