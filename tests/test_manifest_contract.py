from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tdimagefx.errors import ValidationError
from tdimagefx.manifest import PackageManifest
from tools import new_effect

from tests.helpers import clone, manifest_data


ROOT = Path(__file__).resolve().parents[1]


def production_manifest() -> dict[str, object]:
    data = manifest_data()
    data["inputs"][0]["role"] = "source_image"
    data["outputs"][0]["role"] = "image"
    data["parameters"].extend([
        {"id": "seed", "name": "Seed", "type": "int", "default": 1},
        {"id": "reset", "name": "Reset", "type": "pulse", "default": False},
    ])
    data["stateful"] = True
    data["processing"] = {
        "model": "temporal",
        "gpu_cost": "medium",
        "capabilities": ["history"],
        "passes": ["shaders/effect.frag", "shaders/render.frag"],
        "history_frames": 2,
        "state_pass": "shaders/effect.frag",
        "render_pass": "shaders/render.frag",
        "pass_scale": 1.0,
        "iterations": 1,
        "quality_tiers": [
            {"id": "preview", "label": "Preview", "pass_scale": 0.5, "iterations": 1},
            {"id": "full", "label": "Full", "pass_scale": 1.0, "iterations": 2, "default": True},
        ],
    }
    data["image_contract"] = {
        "color": {
            "input_space": "source",
            "working_space": "linear-srgb",
            "output_space": "source",
            "reference": "scene_referred",
        },
        "alpha": {"input": "straight", "working": "straight", "output": "straight"},
        "pixel_format": {"policy": "minimum", "format": "rgba16f"},
        "sampling": {"filter": "linear", "edge": "clamp", "mipmaps": False},
    }
    data["determinism"] = {"mode": "seeded", "seed_parameter": "seed", "fixed_timestep": 1 / 60}
    data["temporal"] = {
        "reset": {
            "strategy": "pulse_parameter",
            "parameter": "reset",
            "clears": "history",
            "on_resolution_change": True,
            "on_input_change": False,
        },
        "warmup_frames": 3,
    }
    data["provenance"] = {
        "origin": "adapted",
        "source": {
            "type": "repository",
            "url": "https://example.test/source",
            "revision": "abc123",
            "author": "Example Author",
            "license": "MIT",
        },
        "changelog": "CHANGELOG.md",
        "examples": ["examples/basic.toe"],
        "presets": ["presets/default.json"],
        "known_limitations": ["Requires floating-point input for best results."],
    }
    return data


class ProductionManifestContractTests(unittest.TestCase):
    def test_complete_contract_is_valid_and_exposed(self) -> None:
        manifest = PackageManifest.from_data(production_manifest())
        self.assertEqual(manifest.image_contract["pixel_format"]["format"], "rgba16f")
        self.assertEqual(manifest.determinism["seed_parameter"], "seed")
        self.assertEqual(manifest.temporal["reset"]["parameter"], "reset")
        self.assertEqual(manifest.provenance["source"]["revision"], "abc123")

    def test_all_published_manifests_remain_valid_without_optional_contract(self) -> None:
        manifests = sorted((ROOT / "packages").glob("*/*/package.json"))
        self.assertGreaterEqual(len(manifests), 78)
        for path in manifests:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                PackageManifest.from_data(json.loads(path.read_text(encoding="utf-8")))

    def test_image_and_seed_cross_field_rules(self) -> None:
        cases = []
        wrong_alpha = production_manifest()
        wrong_alpha["alpha_policy"] = "premultiply"
        cases.append((wrong_alpha, "alpha.output must be 'premultiplied'"))

        inherited_format = production_manifest()
        inherited_format["image_contract"]["pixel_format"] = {"policy": "inherit", "format": "rgba8"}
        cases.append((inherited_format, "format must be omitted"))

        missing_seed = production_manifest()
        missing_seed["determinism"] = {"mode": "seeded"}
        cases.append((missing_seed, "exactly one"))

        wrong_seed_parameter = production_manifest()
        wrong_seed_parameter["determinism"] = {"mode": "seeded", "seed_parameter": "reset"}
        cases.append((wrong_seed_parameter, "int or float"))

        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValidationError, message):
                PackageManifest.from_data(data)

    def test_state_render_and_reset_cross_field_rules(self) -> None:
        cases = []
        unpaired = production_manifest()
        del unpaired["processing"]["render_pass"]
        cases.append((unpaired, "declared together"))

        reversed_passes = production_manifest()
        reversed_passes["processing"]["passes"] = ["shaders/render.frag", "shaders/effect.frag"]
        reversed_passes["entrypoints"]["shader"] = "shaders/render.frag"
        cases.append((reversed_passes, "must precede"))

        missing_history = production_manifest()
        missing_history["processing"]["capabilities"] = []
        cases.append((missing_history, "history capability"))

        wrong_reset_type = production_manifest()
        wrong_reset_type["parameters"][-1]["type"] = "toggle"
        cases.append((wrong_reset_type, "pulse parameter"))

        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValidationError, message):
                PackageManifest.from_data(data)

    def test_semantic_roles_quality_tiers_and_provenance_are_checked(self) -> None:
        missing_capability = production_manifest()
        missing_capability["inputs"].append({
            "id": "depth_map", "family": "TOP", "required": True, "role": "depth"
        })
        with self.assertRaisesRegex(ValidationError, "requires processing capability 'depth'"):
            PackageManifest.from_data(missing_capability)

        duplicate_default = production_manifest()
        duplicate_default["processing"]["quality_tiers"][0]["default"] = True
        with self.assertRaisesRegex(ValidationError, "exactly one default"):
            PackageManifest.from_data(duplicate_default)

        unsafe_example = production_manifest()
        unsafe_example["provenance"]["examples"] = ["../escape.toe"]
        with self.assertRaisesRegex(ValidationError, "unsafe path"):
            PackageManifest.from_data(unsafe_example)

    def test_unhashable_contract_values_report_errors_without_crashing(self) -> None:
        data = production_manifest()
        data["inputs"][0]["role"] = {}
        data["image_contract"]["color"]["input_space"] = {}
        data["image_contract"]["alpha"]["input"] = []
        data["image_contract"]["pixel_format"]["policy"] = {}
        data["image_contract"]["sampling"]["filter"] = {}
        data["determinism"]["mode"] = {}
        data["temporal"]["reset"]["strategy"] = {}
        data["provenance"]["origin"] = {}

        with self.assertRaises(ValidationError) as caught:
            PackageManifest.from_data(data)
        message = str(caught.exception)
        self.assertIn("image_contract.color.input_space", message)
        self.assertIn("determinism.mode", message)
        self.assertIn("temporal.reset.strategy", message)
        self.assertIn("provenance.origin", message)


class ProductionScaffoldContractTests(unittest.TestCase):
    def test_temporal_scaffold_emits_state_reset_and_image_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for model, clears in (("temporal", "history"), ("simulation", "simulation_state")):
                with self.subTest(model=model):
                    args = argparse.Namespace(
                        slug=f"{model}-scaffold",
                        name=f"{model.title()} Scaffold",
                        category="temporal",
                        version="1.0.0",
                        model=model,
                        gpu_cost="medium",
                        capability=[],
                        history_frames=2,
                        inputs=1,
                        description=None,
                    )
                    with mock.patch.object(new_effect, "PACKAGES", Path(temporary) / "packages"):
                        package_root = new_effect.scaffold(args)
                    data = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
                    manifest = PackageManifest.from_data(data)

                    self.assertEqual(manifest.processing["state_pass"], f"shaders/{model}_scaffold.frag")
                    self.assertEqual(manifest.processing["render_pass"], "shaders/render.frag")
                    self.assertEqual(manifest.temporal["reset"]["strategy"], "pulse_parameter")
                    self.assertEqual(manifest.temporal["reset"]["clears"], clears)
                    self.assertEqual(manifest.image_contract["pixel_format"], {"policy": "inherit"})
                    self.assertEqual(manifest.inputs[0]["role"], "source_image")
                    self.assertTrue((package_root / "shaders" / "render.frag").is_file())


if __name__ == "__main__":
    unittest.main()
