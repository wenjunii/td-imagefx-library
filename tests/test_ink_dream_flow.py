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

    def test_static_glitter_is_separate_and_default_off(self):
        names = {d["name"]:d for d in MODULE["PARAMETERS"]}
        self.assertFalse(names["Staticglitterenabled"]["default"])
        self.assertTrue({"Staticglitteramount", "Staticglitterseed", "Staticglittercolor",
                         "Staticglittersurface", "Staticglittersize", "Staticglitterstars",
                         "Staticglittershimmer", "Staticglittertwinklespeed",
                         "Staticglittershimmercontrast", "Staticglittershimmerfloor",
                         "Staticglittershimmerrandom"} <= set(names))
        self.assertEqual(names["Staticglittershimmer"]["default"],0.)
        static_function = MODULE["SHADER"].split("vec3 staticGlitterGrains",1)[1].split("void main()",1)[0]
        geometry = static_function.split("float pulse=",1)[0]
        self.assertNotIn("uTime", geometry)
        self.assertIn("uTime*uStaticTwinkleSpeed",static_function)
        self.assertNotIn("uGlitter", static_function)

    def test_brush_inherits_all_parameters_without_mutation(self):
        import copy
        original = copy.deepcopy(MODULE["PARAMETERS"])
        parameters, shader = MODULE["brush_variant"]()
        self.assertEqual(original, MODULE["PARAMETERS"])
        inherited = {d["name"]:d for d in parameters}
        for definition in original:
            variant = inherited[definition["name"]]
            for key in ("type", "uniform", "min", "max", "menu_names"):
                self.assertEqual(variant.get(key), definition.get(key))
        self.assertIn("softCurrent(q,t,seed)", shader)
        self.assertIn("currentWisps(pq,pt,seed)", shader)
        self.assertNotIn("second-nearest",shader)
        coordinate_function = shader.split("vec2 currentCoordinates",1)[1].split("float softCurrent",1)[0]
        self.assertNotIn("q=currentCoordinates",coordinate_function)
        self.assertLess(inherited["Papercolor"]["default"][0],.05)
        self.assertGreater(inherited["Particlecolor"]["default"][2],.9)
        self.assertIn("Staticglitterenabled", inherited)

    def test_brush_uniforms_bound_and_used(self):
        parameters, shader = MODULE["brush_variant"]()
        declared = set()
        for declaration in re.findall(r"uniform\s+(?:float|vec[234])\s+([^;]+);",shader):
            declared.update(n.strip() for n in declaration.split(","))
        bound = {d["uniform"] for d in parameters if d.get("uniform")}
        self.assertEqual(declared,bound)
        for name in bound:
            self.assertGreaterEqual(len(re.findall(r"\b"+name+r"\b",shader)),2,name)

    def test_packed_bindings_cover_every_scalar_once(self):
        for parameters, shader in ((MODULE["PARAMETERS"],MODULE["SHADER"]),MODULE["brush_variant"](),MODULE["radial_variant"]()):
            packed, bindings = MODULE["pack_scalar_uniforms"](shader,parameters)
            scalar = [d for d in parameters if d.get("uniform") and d["type"] not in ("xy","rgb","rgba")]
            self.assertEqual(sum(len(values) for _,values in bindings),len(scalar))
            self.assertLess(len(bindings)+1,32)
            for definition in scalar:
                self.assertEqual(len(re.findall(r"#define "+definition["uniform"]+r"\s+uPacked\d+\.[xyzw]",packed)),1)
                expr = "parent().par."+definition["name"]+(".menuIndex" if definition["type"]=="menu" else "")
                self.assertEqual(sum(values.count(expr) for _,values in bindings),1)
            self.assertNotRegex(packed,r"uniform\s+float")

    def test_brush_show_and_harness_routes(self):
        self.assertEqual(MODULE_TOGGLES["ink_brush_flow"],"Inkbrushenabled")
        for parameter in ("Brushweb", "Staticglitteramount", "Staticglittershimmer", "Staticglittertwinklespeed", "Glittercolorr", "Particletrail"):
            cue = dict(new_cue(),kind="parameters",target="ink_brush_flow/"+parameter,value=.7)
            self.assertEqual(validate_cue(cue)["target"],cue["target"])
        for name in ("build_project.py","install_dev_harness.py"):
            text = (ROOT/"touchdesigner/scripts"/name).read_text(encoding="utf-8")
            self.assertIn("InkBrushFlow.tox",text)
            self.assertIn("parent().par.Inkbrushenabled",text)
        suite = (ROOT/"touchdesigner/scripts/validate_live_suite.py").read_text(encoding="utf-8")
        self.assertIn('("ink_brush_flow", "validate_ink_brush_flow.py")',suite)

    def test_radial_inherits_every_brush_control_without_mutation(self):
        import copy
        brush, _ = MODULE["brush_variant"]()
        before = copy.deepcopy(brush)
        radial, _ = MODULE["radial_variant"]()
        self.assertEqual(before, brush)
        inherited = {d["name"]: d for d in radial}
        self.assertEqual(len(inherited),len(radial))
        for definition in brush:
            variant=inherited[definition["name"]]
            for key in ("type", "uniform", "min", "max", "norm_min", "norm_max", "menu_names", "menu_labels", "read_only"):
                self.assertEqual(variant.get(key),definition.get(key),definition["name"]+":"+key)
        self.assertFalse(inherited["Glitterenabled"]["default"])
        self.assertFalse(inherited["Staticglitterenabled"]["default"])
        self.assertEqual(inherited["Staticglittershimmer"]["default"],0.)
        self.assertEqual(len(radial)-len(brush),10)

    def test_radial_uniforms_and_valid_defaults(self):
        parameters, shader=MODULE["radial_variant"]()
        declared=set()
        for declaration in re.findall(r"uniform\s+(?:float|vec[234])\s+([^;]+);",shader):
            declared.update(n.strip() for n in declaration.split(","))
        bound={d["uniform"] for d in parameters if d.get("uniform")}
        self.assertEqual(declared,bound)
        for d in parameters:
            self.assertRegex(d["name"],r"^[A-Z][a-z]+$")
            if d["type"] in ("float","int"):
                self.assertLess(d["min"],d["max"])
                self.assertLessEqual(d["min"],d["default"])
                self.assertGreaterEqual(d["max"],d["default"])
            if d.get("uniform"):
                self.assertGreaterEqual(len(re.findall(r"\b"+d["uniform"]+r"\b",shader)),2,d["name"])
        self.assertNotIn("absTime",shader)
        self.assertIn("radialBlend()",shader)
        self.assertIn("t*uRadialSpeed*6.2831853",shader)
        self.assertIn("float first=3.*a",shader)
        self.assertIn("float second=5.*a",shader)
        self.assertIn("max(length(p),.001)",shader)

    def test_radial_show_harness_and_validation_routes(self):
        self.assertEqual(MODULE_TOGGLES["ink_radial_flow"],"Inkradialenabled")
        for parameter in ("Radialenabled","Radialamount","Radialspeed","Centerx","Brushglow","Staticglittershimmer","Glittercolorr"):
            cue=dict(new_cue(),kind="parameters",target="ink_radial_flow/"+parameter,value=.7)
            self.assertEqual(validate_cue(cue)["target"],cue["target"])
        for name in ("build_project.py","install_dev_harness.py"):
            source=(ROOT/"touchdesigner/scripts"/name).read_text(encoding="utf-8")
            self.assertIn("InkRadialFlow.tox",source)
            self.assertIn("parent().par.Inkradialenabled",source)
            self.assertIn("ink_brush_flow.outputConnectors[0].connect(ink_radial_flow.inputConnectors[0])",source)
            self.assertIn("ink_radial_flow.outputConnectors[0].connect(ink_flow.inputConnectors[0])",source)
        suite=(ROOT/"touchdesigner/scripts/validate_live_suite.py").read_text(encoding="utf-8")
        self.assertIn('("ink_radial_flow", "validate_ink_radial_flow.py")',suite)
