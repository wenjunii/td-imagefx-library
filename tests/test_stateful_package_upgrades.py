from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
STATEFUL_IDS = {
    "tdimagefx.simulation.cellular-automata",
    "tdimagefx.simulation.fluid-ink",
    "tdimagefx.simulation.particle-advection",
    "tdimagefx.simulation.reaction-diffusion",
    "tdimagefx.temporal.echo",
    "tdimagefx.temporal.feedback-kaleidoscope",
    "tdimagefx.temporal.feedback-rotate",
    "tdimagefx.temporal.feedback-trails",
    "tdimagefx.temporal.frame-blend",
    "tdimagefx.temporal.motion-smear",
    "tdimagefx.temporal.recursive-zoom",
    "tdimagefx.temporal.stutter",
    "tdimagefx.temporal.temporal-glitch",
    "tdimagefx.temporal.time-displacement",
}


def _load(package_id: str, version: str) -> dict:
    return json.loads((PACKAGES / package_id / version / "package.json").read_text(encoding="utf-8"))


class StatefulPackageUpgradeTests(unittest.TestCase):
    def test_latest_stateful_packages_separate_state_from_rendering(self) -> None:
        discovered = {
            path.parent.parent.name
            for path in PACKAGES.glob("tdimagefx.temporal.*/1.1.0/package.json")
        } | {
            path.parent.parent.name
            for path in PACKAGES.glob("tdimagefx.simulation.*/1.1.0/package.json")
        }
        self.assertEqual(discovered, STATEFUL_IDS)

        for package_id in sorted(STATEFUL_IDS):
            with self.subTest(package_id=package_id):
                old = _load(package_id, "1.0.0")
                current = _load(package_id, "1.1.0")
                package_root = PACKAGES / package_id / "1.1.0"
                processing = current["processing"]

                self.assertEqual(current["version"], "1.1.0")
                self.assertEqual(current["id"], old["id"])
                self.assertEqual(
                    current["entrypoints"]["touchdesigner_component"],
                    old["entrypoints"]["touchdesigner_component"],
                )
                self.assertEqual(
                    [(item["id"], item["default"]) for item in current["parameters"] if item["id"] != "reset"],
                    [(item["id"], item["default"]) for item in old["parameters"]],
                )

                reset = next(item for item in current["parameters"] if item["id"] == "reset")
                self.assertEqual((reset["name"], reset["type"], reset["default"]), ("Reset", "pulse", False))
                self.assertEqual(current["inputs"][0]["role"], "source_image")
                self.assertEqual(current["outputs"][0]["role"], "image")
                self.assertEqual(
                    processing["passes"],
                    [processing["state_pass"], processing["render_pass"]],
                )
                self.assertEqual(processing["history_frames"], 1)

                state_shader = (package_root / processing["state_pass"]).read_text(encoding="utf-8")
                render_shader = (package_root / processing["render_pass"]).read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"\buMix\b", state_shader))
                self.assertRegex(state_shader, r"sTD2DInputs\[0\]")
                self.assertRegex(state_shader, r"sTD2DInputs\[1\]")
                self.assertRegex(render_shader, r"uniform\s+float\s+uMix\s*;")
                self.assertRegex(render_shader, r"sTD2DInputs\[0\]")
                self.assertRegex(render_shader, r"sTD2DInputs\[1\]")

                reset_contract = current["temporal"]["reset"]
                self.assertEqual(reset_contract["strategy"], "pulse_parameter")
                self.assertEqual(reset_contract["parameter"], "reset")
                expected_target = "simulation_state" if processing["model"] == "simulation" else "history"
                self.assertEqual(reset_contract["clears"], expected_target)

    def test_simulations_use_explicit_private_state_encodings(self) -> None:
        for package_id in sorted(item for item in STATEFUL_IDS if ".simulation." in item):
            with self.subTest(package_id=package_id):
                manifest = _load(package_id, "1.1.0")
                shader = (PACKAGES / package_id / "1.1.0" / manifest["processing"]["state_pass"]).read_text(
                    encoding="utf-8"
                )
                self.assertIn("Private", shader)
                self.assertNotIn("mix(src.rgb", shader)

        automata = (
            PACKAGES
            / "tdimagefx.simulation.cellular-automata"
            / "1.1.0"
            / "shaders"
            / "cellular_automata.frag"
        ).read_text(encoding="utf-8")
        self.assertIn("abs(neighbors - birthCount)", automata)
        self.assertIn("abs(neighbors - survivalCount)", automata)

        reaction = (
            PACKAGES
            / "tdimagefx.simulation.reaction-diffusion"
            / "1.1.0"
            / "shaders"
            / "reaction_diffusion.frag"
        ).read_text(encoding="utf-8")
        self.assertIn("float reaction = a * b * b;", reaction)
        self.assertIn("diffusionA * laplacian.r - reaction", reaction)
        self.assertIn("diffusionB * laplacian.g + reaction", reaction)


if __name__ == "__main__":
    unittest.main()
