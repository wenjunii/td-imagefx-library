"""Portable contracts; actual rendered-control coverage runs inside TD."""
import re
import runpy
import unittest
from pathlib import Path

from tdimagefx.show import MODULES, MODULE_TOGGLES, TOGGLES, new_cue, validate_cue

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "touchdesigner/scripts/ink_dream_flow.py"))


class InkDreamFlowTests(unittest.TestCase):
    def test_parameter_names_and_ranges(self):
        definitions = MODULE["PARAMETERS"]
        self.assertEqual(len({d["name"] for d in definitions}), len(definitions))
        for d in definitions:
            self.assertRegex(d["name"], r"^[A-Z][a-z]+$")
            if d["type"] in ("float", "int"):
                self.assertLess(d["min"], d["max"])
                self.assertLessEqual(d["min"], d["default"])
                self.assertGreaterEqual(d["max"], d["default"])
            if d["type"] == "rgba":
                self.assertEqual(len(d["default"]), 4)
                self.assertTrue(all(0 <= v <= 1 for v in d["default"]))

    def test_every_uniform_is_bound_and_used(self):
        shader = MODULE["SHADER"]
        declared = set()
        for declaration in re.findall(r"uniform\s+(?:float|vec[234])\s+([^;]+);", shader):
            declared.update(n.strip() for n in declaration.split(","))
        bound = [d["uniform"] for d in MODULE["PARAMETERS"] if d.get("uniform")]
        self.assertEqual(set(bound), declared)
        self.assertEqual(len(bound), len(set(bound)))
        for name in bound:
            self.assertGreaterEqual(len(re.findall(r"\b" + name + r"\b", shader)), 2, name)

    def test_independent_layers_and_palette(self):
        names = {d["name"] for d in MODULE["PARAMETERS"]}
        self.assertTrue({"Liquidenabled", "Particlesenabled", "Flowspeed", "Particlespeed", "Inkcolor", "Washcolor", "Particlecolor", "Papercolor",
                         "Glitterenabled", "Glittersurface", "Glitterspeed", "Glittertwinklespeed", "Glitterseed", "Glittercolor"} <= names)
        glitter_switch = next(d for d in MODULE["PARAMETERS"] if d["name"] == "Glitterenabled")
        self.assertFalse(glitter_switch["default"])
        self.assertIn("if(uParticleDensity<=0.) return 0.;", MODULE["SHADER"])

    def test_show_cue_accepts_module(self):
        self.assertIn("ink_dream_flow", MODULES)
        self.assertIn("Inkdreamenabled", TOGGLES)
        self.assertEqual(set(MODULE_TOGGLES), set(MODULES))
        self.assertEqual(set(MODULE_TOGGLES.values()), set(TOGGLES) - {"Applyvideofx"})
        cue = dict(new_cue(), kind="parameters", target="ink_dream_flow/Flowamount", value=.75)
        self.assertEqual(validate_cue(cue)["target"], cue["target"])
        for parameter in ("Glitteramount", "Glittercolorr", "Glitterspeed"):
            cue = dict(new_cue(), kind="parameters", target="ink_dream_flow/"+parameter, value=.75)
            self.assertEqual(validate_cue(cue)["target"], cue["target"])

    def test_builder_harness_and_suite_include_module(self):
        for name in ("build_project.py", "install_dev_harness.py"):
            text = (ROOT / "touchdesigner/scripts" / name).read_text(encoding="utf-8")
            self.assertIn("InkDreamFlow.tox", text)
            self.assertIn("parent().par.Inkdreamenabled", text)
        suite = (ROOT / "touchdesigner/scripts/validate_live_suite.py").read_text(encoding="utf-8")
        self.assertIn('("ink_dream_flow", "validate_ink_dream_flow.py")', suite)

    def test_native_record_rejects_changed_module_source(self):
        import tempfile
        from tests.test_native_validation import NativeValidationRecordTests
        from tools import record_native_validation as recorder
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = NativeValidationRecordTests()._fixture(root)
            (root / recorder.MODULE_SOURCES[0]).write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(recorder.NativeValidationError, "module sources"):
                recorder.build_record(root, report)

    def test_live_suite_keeps_failures_and_source_identity(self):
        import tempfile
        import hashlib
        import types
        path = ROOT / "touchdesigner/scripts/validate_live_suite.py"
        runner = types.ModuleType("test_live_suite")
        runner.__file__ = str(path)
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), runner.__dict__)
        with tempfile.TemporaryDirectory() as directory:
            runner.SCRIPT_ROOT = Path(directory)
            fixture = runner.SCRIPT_ROOT / "check.py"
            for result in (
                {"ok": False, "details": {"error": "cue toggle failed"}},
                {"ok": True, "checks": {"missing_control": False}},
                {"ok": True, "checks": {"all_controls": True}},
            ):
                source = "def validate(write_report=True):\n    return " + repr(result) + "\n"
                fixture.write_text(source, encoding="utf-8")
                summary = runner._run_validator("fixture", "check.py")
                self.assertEqual(summary["ok"], result["ok"] and all(result.get("checks", {}).values()))
                self.assertEqual(summary["source_sha256"], hashlib.sha256(source.encode()).hexdigest())
                self.assertGreaterEqual(summary["duration_seconds"], 0.)
                if not result["ok"]:
                    self.assertEqual(summary["error"], "cue toggle failed")
