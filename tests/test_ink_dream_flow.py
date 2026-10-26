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

    def test_dot_pattern_inherits_with_stable_glitter_menus(self):
        for definitions, shader in ((MODULE["PARAMETERS"],MODULE["SHADER"]),MODULE["brush_variant"](),MODULE["radial_variant"]()):
            controls = {d["name"]:d for d in definitions}
            self.assertFalse(controls["Patternenabled"]["default"])
            self.assertEqual(controls["Patternmode"]["default"], "overlay")
            self.assertEqual(controls["Patternsurface"]["menu_names"], ["full","ink","wash","particles","combined"])
            self.assertEqual(len([n for n in controls if n.startswith("Pattern")]), 18)
            for name in ("Glittersurface","Staticglittersurface"):
                self.assertEqual(controls[name]["menu_names"], ["ink","wash","particles","combined","pattern"])
            self.assertIn("float patternTime=uTime*uPatternSpeed;", shader)
            self.assertIn("if(uPatternEnabled>.5 && uPatternAmount>0.)", shader)
            self.assertLess(shader.index("// Dot pattern layer"), shader.index("if(uGlitterEnabled>.5"))
            self.assertIn("smoothstep(.55,1.4",shader)
            for parameter in ("Patternamount", "Patternspeed", "Patterncolorr"):
                for module in ("ink_dream_flow", "ink_brush_flow", "ink_radial_flow"):
                    cue = dict(new_cue(),kind="parameters",target=module+"/"+parameter,value=.7)
                    self.assertEqual(validate_cue(cue)["target"],cue["target"])

    def test_dot_pattern_lighting_precedes_glitter(self):
        _, brush = MODULE["brush_variant"]()
        _, radial = MODULE["radial_variant"]()
        for shader in (brush,radial):
            self.assertLess(shader.index("// Premultiplied emission"),shader.index("// Dot pattern layer"))
            self.assertIn("patternCoord=mix(p,currentCoordinates(p,patternTime,seed),uPatternFlow)",shader)
        self.assertLess(radial.index("if(uLiquidEnabled>.5 && radialBlend()>0."),radial.index("// Dot pattern layer"))

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

    def test_particle_conversion_is_optional_and_does_not_rewrite_flow(self):
        for definitions, shader in ((MODULE["PARAMETERS"], MODULE["SHADER"]), MODULE["brush_variant"](), MODULE["radial_variant"]()):
            controls = {d["name"]: d for d in definitions}
            self.assertFalse(controls["Particlefieldenabled"]["default"])
            self.assertEqual(controls["Particlecolumns"]["max"], 500)
            self.assertEqual(controls["Particleshape"]["menu_names"], ["round", "square", "spark"])
            self.assertIn("vec4 fieldBackground=result;", shader)
            self.assertIn("if(uParticleFieldEnabled>.5) result=vec4(0.);", shader)
            self.assertIn("result*=vec4(vec3(points.y),points.x);", shader)
            self.assertGreater(shader.index("vec2 points=movingFieldGrains(screen,seed);"), shader.index("if(uStaticEnabled>.5"))
            helper = shader.split("vec2 fieldGrains",1)[1].split("vec2 movingFieldGrains",1)[0]
            self.assertNotIn("uTime", helper)
            self.assertNotIn("flow(", helper)
            self.assertNotIn("uParticleDensity", helper)
            self.assertIn("for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++)", shader)
            self.assertIn("if(uFieldDensity<=0.) return dots;", shader)
            self.assertEqual(controls["Background"]["menu_names"], ["paper", "source", "transparent"])
        radial = MODULE["radial_variant"]()[1]
        self.assertIn("currentWisps", radial)
        self.assertIn("paper=mix(paper,ambient", radial)

    def test_motion_is_opt_in_and_moves_sampling_positions(self):
        for definitions, shader in ((MODULE['PARAMETERS'], MODULE['SHADER']), MODULE['brush_variant'](), MODULE['radial_variant']()):
            controls = {d['name']:d for d in definitions}
            self.assertEqual(controls['Fieldspeed']['default'], 0.)
            self.assertIn('field_sample', controls['Fieldspeed']['uniform_expression'])
            # A stateful clock readout on the component creates a dependency
            # warning in copied cue decks. Keep phase internal to the uniform.
            self.assertNotIn('Fieldtime', controls)
            self.assertIn('center+=.18*', shader)
            self.assertIn('if(uFieldTime!=0.)', shader)
            self.assertIn('vec2 d=f-offset-center;', shader)
        self.assertIn('currentVelocity(p,t,seed)', MODULE['brush_variant']()[1])

    def test_feedback_is_optional_embedded_and_separate_from_base_shader(self):
        for definitions, shader in ((MODULE['PARAMETERS'], MODULE['SHADER']), MODULE['brush_variant'](), MODULE['radial_variant']()):
            controls = {d['name']:d for d in definitions}
            self.assertFalse(controls['Feedbackenabled']['default'])
            self.assertEqual(controls['Feedbackreset']['type'], 'pulse')
            self.assertNotIn('uHistory', shader)
        self.assertIn('premult(current)', MODULE['FEEDBACK_SHADER'])
        self.assertIn("or abs(delta) > .5", MODULE['FEEDBACK_RUNTIME_SOURCE'])
        builder = (ROOT/'touchdesigner/scripts/build_project.py').read_text(encoding='utf-8')
        self.assertIn('output_setup=scope["install_feedback"]', builder)
        cues = (ROOT/'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
        self.assertIn("module.store('imagefx_flow_feedback_state', None)", cues)

    def test_legacy_flow_defaults_restored(self):
        variants = ((MODULE["PARAMETERS"], .48, [0.94, .85, .67, 1.]),
                    (MODULE["brush_variant"]()[0], .57, [.012, .02, .045, 1.]),
                    (MODULE["radial_variant"]()[0], .57, [1., .43, .14, 1.]))
        for definitions, coverage, paper in variants:
            controls = {d['name']: d for d in definitions}
            self.assertEqual(controls['Coverage']['default'], coverage)
            self.assertEqual(controls['Papercolor']['default'], paper)
            self.assertGreater(controls['Papertexture']['default'], 0.)
            self.assertEqual(controls['Particlefieldenabled']['page'], 'Particle Field')
        for name in ('Fielddensity', 'Fieldsize'):
            self.assertEqual(next(d for d in MODULE['PARAMETERS'] if d['name']==name)['page'], 'Particle Field')

    def test_new_particle_values_are_cue_targets(self):
        for module in ("ink_dream_flow", "ink_brush_flow", "ink_radial_flow"):
            for name, value in (("Particlefieldenabled", True), ("Particlecolumns", 250), ("Particleshape", "spark"), ("Particledepth", .7), ("Fielddensity", .8), ("Fieldsize", 2.), ("Fieldspeed", -1.), ("Feedbackenabled", True), ("Feedbackamount", .75), ("Feedbackdecay", .94), ("Feedbackzoom", 1.01), ("Feedbackrotate", .25), ("Feedbackoffsetx", .001), ("Feedbackoffsety", -.002)):
                cue = dict(new_cue(), kind="parameters", target=module+"/"+name, value=value)
                self.assertEqual(validate_cue(cue)["value"], value)

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
        self.assertIn("currentVelocity(point,t,seed)", shader)
        self.assertIn("currentWisps", shader)
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
            self.assertLessEqual(len(bindings)+1,32)
            for definition in scalar:
                self.assertEqual(len(re.findall(r"#define "+definition["uniform"]+r"\s+uPacked\d+\.[xyzw]",packed)),1)
                expr = definition.get("uniform_expression") or "parent().par."+definition["name"]+(".menuIndex" if definition["type"]=="menu" else "")
                self.assertEqual(sum(values.count(expr) for _,values in bindings),1)
            self.assertNotRegex(packed,r"uniform\s+float")

    def test_animation_speed_is_neutral_and_shared_by_all_variants(self):
        for name, (parameters, shader) in zip(
            ("ink_dream_flow", "ink_brush_flow", "ink_radial_flow"),
            ((MODULE["PARAMETERS"], MODULE["SHADER"]), MODULE["brush_variant"](), MODULE["radial_variant"]()),
        ):
            controls = {d["name"]: d for d in parameters}
            speed = controls["Animationspeed"]
            self.assertEqual((speed["default"], speed["min"], speed["max"]), (1., 0., 10.))
            self.assertEqual(speed["page"], "Timing")
            self.assertNotIn("uniform", speed)  # Existing uniform layout is unchanged.
            _, bindings = MODULE["pack_scalar_uniforms"](shader, parameters)
            expression = controls["Time"]["uniform_expression"]
            self.assertEqual(sum(values.count(expression) for _, values in bindings), 1)
            self.assertEqual(expression, "parent().op('animation_clock').module.sample(parent())")
            self.assertNotIn("absTime", shader)
            cue = dict(new_cue(), kind="parameters", target=name + "/Animationspeed", value=.5)
            self.assertEqual(validate_cue(cue)["value"], .5)

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
