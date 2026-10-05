"""Portable Layer Composite contracts; pixels are tested in TouchDesigner."""
import re
import runpy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

from tdimagefx.show import MODULES, MODULE_TOGGLES, resolve_layer_files, new_cue, validate_cue

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "touchdesigner/scripts/layer_composite.py"))


class LayerCompositeTests(unittest.TestCase):
    def test_parameter_contracts(self):
        definitions = MODULE["PARAMETERS"]
        self.assertEqual(len(definitions), len({d["name"] for d in definitions}))
        for d in definitions:
            self.assertRegex(d["name"], r"^[A-Z][a-z]+$")
            if d["type"] in ("float", "int"):
                self.assertLess(d["min"], d["max"])
                self.assertLessEqual(d["min"], d["default"])
                self.assertLessEqual(d["default"], d["max"])
        defaults = {d["name"]: d["default"] for d in definitions if "default" in d}
        self.assertFalse(defaults["Flickerenabled"])
        self.assertEqual(defaults["Topfile"], "")
        self.assertEqual(defaults["Backdropfile"], "")

    def test_uniforms_are_bound_and_used(self):
        shader = MODULE["SHADER"]
        declarations = re.findall(r"uniform\s+(?:float|vec[234])\s+([^;]+);", shader)
        names = {n.strip() for group in declarations for n in group.split(",")}
        bindings = [d["uniform"] for d in MODULE["PARAMETERS"] if d.get("uniform")]
        self.assertEqual(names, set(bindings))
        self.assertEqual(len(bindings), len(set(bindings)))
        for name in names:
            self.assertGreater(len(re.findall(r"\b"+name+r"\b", shader)), 1)
        self.assertIn("sTD2DInputs[1]", shader)

    def test_show_parameter_cue(self):
        self.assertIn("layer_composite", MODULES)
        self.assertEqual(MODULE_TOGGLES["layer_composite"], "Layercompositeenabled")
        cue = dict(new_cue(), kind="parameters", target="layer_composite/Opacity", value=.2)
        self.assertEqual(validate_cue(cue)["target"], cue["target"])

    def test_local_image_paths_resolve_and_empty_clears(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.png"
            path.write_bytes(b"fixture")
            self.assertEqual(resolve_layer_files({"Topfile": "test.png"}, directory),
                             {"Topfile": str(path.resolve()), "Backdropfile": ""})
            self.assertEqual(resolve_layer_files({}, directory), {"Backdropfile": "", "Topfile": ""})

    def test_image_fields_reject_urls_and_unknown_controls(self):
        for value in ({"Topfile": "https://example.com/x.png"}, {"Topfile": 4},
                      {"Topfile": "bad\x00.png"}, {"Topfile": "a"*4097}, {"Script": "x"}, []):
            with self.assertRaises(ValueError):
                resolve_layer_files(value, ROOT)

    def test_missing_image_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Missing layer media"):
                resolve_layer_files({"Backdropfile": "missing.png"}, directory)

    def test_unselected_files_do_not_block_show(self):
        with tempfile.TemporaryDirectory() as directory:
            values={"Topfile":"missing.mp4"}
            self.assertTrue(resolve_layer_files(values,directory,selections={"Topsource":"effects"})["Topfile"].endswith("missing.mp4"))
            self.assertTrue(resolve_layer_files(values,directory,enabled=False)["Topfile"])
            with self.assertRaises(ValueError): resolve_layer_files(values,directory,selections={"Topsource":"file"})

    def test_source_routing_exhaustive(self):
        runtime={}; exec(MODULE["STATUS"],runtime)
        for port in (0,1):
            for count in (0,1,2):
                for has_file in (False,True):
                    for selection,expected in (("auto",2 if has_file else (1 if count>port else 0)),("file",2 if has_file else 0),("effects",3 if count else 0),("second",4 if count>1 else 0),("transparent",0)):
                        self.assertEqual(runtime["source_index"](selection,has_file,count,port),expected)

    def test_builder_harness_suite_and_record_include_module(self):
        for filename in ("build_project.py", "install_dev_harness.py"):
            source = (ROOT / "touchdesigner/scripts" / filename).read_text(encoding="utf-8")
            self.assertIn("LayerComposite.tox", source)
            self.assertIn("parent().par.Layercompositeenabled", source)
        source = (ROOT / "touchdesigner/scripts/validate_live_suite.py").read_text(encoding="utf-8")
        self.assertIn('("layer_composite", "validate_layer_composite.py")', source)
        from tools.record_native_validation import MODULE_SOURCES, CORE_ASSETS
        self.assertIn("touchdesigner/scripts/layer_composite.py", MODULE_SOURCES)
        self.assertIn("touchdesigner/core/LayerComposite.tox", CORE_ASSETS)
        builder=(ROOT / "touchdesigner/scripts/build_project.py").read_text(encoding="utf-8")
        self.assertIn('movie.par.premultrgbbyalpha = "off"',builder)
        self.assertIn('preview_source.par.vec0valuex = 0',builder)
        self.assertIn('module.par.opviewer = module.relativePath(output)',builder)

    def test_video_transport_defaults_and_binding(self):
        definitions={d["name"]:d for d in MODULE["PARAMETERS"]}
        builder=(ROOT / "touchdesigner/scripts/build_project.py").read_text(encoding="utf-8")
        for prefix in ("Backdrop","Top"):
            self.assertTrue(definitions[prefix+"play"]["default"])
            self.assertTrue(definitions[prefix+"loop"]["default"])
            self.assertEqual(definitions[prefix+"speed"]["default"],1.)
            self.assertEqual(definitions[prefix+"in"]["default"],0.)
            for suffix in ("restart","reload"):
                self.assertEqual(definitions[prefix+suffix]["type"],"pulse")
        self.assertIn("'sequential' if parent().par.Autotime else 'specify'",builder)
        self.assertIn("parent().par.Manualtime * parent().par.{0}speed",builder)
        self.assertIn("not parent().par.Autotime or parent().par.{}play",builder)
        self.assertIn("me.op('media_status').module.status",builder)

    def test_video_callbacks_dispatch_to_correct_reader(self):
        callbacks={}; exec(MODULE["CALLBACKS"],callbacks)
        readers={name:Mock() for name in ("backdrop_file","top_file","out1_image")}
        class Pars(dict):
            Autotime=True
        pars=Pars({p+"file":Mock(eval=lambda:"movie.mp4") for p in ("Backdrop","Top")})
        component=SimpleNamespace(op=readers.__getitem__,par=pars)
        def pulse(name): callbacks["onPulse"](SimpleNamespace(name=name,owner=component))
        pulse("Preview"); readers["out1_image"].openViewer.assert_called_once_with()
        for prefix in ("Backdrop","Top"):
            reader=readers[prefix.lower()+"_file"]
            pulse(prefix+"restart"); reader.par.cuepulse.pulse.assert_called_once_with()
            pulse(prefix+"reload"); reader.par.reloadpulse.pulse.assert_called_once_with()
            reader.preload.assert_called_once_with()
            pars.Autotime=False; pulse(prefix+"restart")
            reader.par.cuepulse.pulse.assert_called_once_with()
            pars.Autotime=True

    def test_video_paths_resolve_without_media_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"clip.mp4"; path.write_bytes(b"fixture")
            self.assertEqual(resolve_layer_files({"Topfile":"clip.mp4"},directory)["Topfile"],str(path.resolve()))

    def test_capture_does_not_allow_arbitrary_string_parameter_assignment(self):
        source = (ROOT / "touchdesigner/extensions/ShowControlExt.py").read_text(encoding="utf-8")
        self.assertIn('look["layer_files"]', source)
        self.assertIn("self.model.resolve_layer_files", source)
        self.assertIn("parameter.isNumber or parameter.isToggle or parameter.isMenu", source)
        self.assertIn("name not in {p.name for p in component.customPars}",source)
