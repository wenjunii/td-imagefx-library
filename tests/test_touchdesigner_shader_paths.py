from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, relative_path):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LIBRARY_MODULE = _load_module(
    "tdimagefx_shader_path_library",
    Path("touchdesigner/extensions/ImageFXLibraryExt.py"),
)
RACK_MODULE = _load_module(
    "tdimagefx_shader_path_rack",
    Path("touchdesigner/extensions/FxRackExt.py"),
)


class FakePixelParameter:
    def __init__(self, shader):
        self.shader = shader
        self.val = "/project1/build/effects/example/pixel_shader_1"

    def eval(self):
        return self.shader.parent().op(self.val)


class FakeParameters:
    def __init__(self, shader):
        self.pixeldat = FakePixelParameter(shader)

    def __getitem__(self, name):
        return getattr(self, name, None)


class FakeDAT:
    def __init__(self, name):
        self.name = name
        self.type = "text"
        self.children = []


class FakeGLSL:
    def __init__(self, name, owner):
        self.name = name
        self.type = "glsl"
        self.path = "/project1/loaded/{}/{}".format(owner.name, name)
        self.children = []
        self._owner = owner
        self.par = FakeParameters(self)

    def parent(self):
        return self._owner

    def relativePath(self, operator):
        return operator.name


class FakeEffect:
    def __init__(self, include_dat=True):
        self.name = "effect"
        self.shader_dat = FakeDAT("pixel_shader_1") if include_dat else None
        self.glsl = FakeGLSL("effect_glsl_1", self)
        self.children = [self.glsl]
        if self.shader_dat is not None:
            self.children.append(self.shader_dat)

    def op(self, path):
        if self.shader_dat is not None and path == self.shader_dat.name:
            return self.shader_dat
        return None


class TouchDesignerShaderPathTests(unittest.TestCase):
    def test_loaded_package_shader_paths_are_repaired_portably(self):
        for module in (LIBRARY_MODULE, RACK_MODULE):
            with self.subTest(module=module.__name__):
                effect = FakeEffect()
                self.assertIsNone(effect.glsl.par.pixeldat.eval())

                repaired = module._repair_effect_shader_paths(effect)

                self.assertEqual(repaired, 1)
                self.assertEqual(effect.glsl.par.pixeldat.val, "pixel_shader_1")
                self.assertIs(effect.glsl.par.pixeldat.eval(), effect.shader_dat)

    def test_missing_shader_dat_is_rejected(self):
        for module in (LIBRARY_MODULE, RACK_MODULE):
            with self.subTest(module=module.__name__):
                with self.assertRaisesRegex(RuntimeError, "portable Pixel Shader DAT"):
                    module._repair_effect_shader_paths(FakeEffect(include_dat=False))

    def test_builder_creates_and_repairs_relative_shader_paths(self):
        source = (
            ROOT / "touchdesigner" / "scripts" / "build_project.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "glsl.par.pixeldat = glsl.relativePath(shader_dat)",
            source,
        )
        self.assertIn("_repair_effect_shader_paths(instance)", source)
        self.assertIn('browser.par.Target.val = ""', source)
        self.assertEqual(source.count("browser.UpdateSelection()"), 2)
        self.assertIn("(selected_preview.width, selected_preview.height) != (512, 288)", source)
        self.assertIn('selected_preview.par.outputresolution = "custom"', source)
        self.assertIn("selected_preview.par.resolutionw = 512", source)
        self.assertIn("selected_preview.par.resolutionh = 288", source)
        self.assertIn("browser.cook(force=True)", source)
        self.assertLess(
            source.index('configure_extension(\n        library,\n        "ImageFXLibraryExt"'),
            source.index("browser, browser_path = build_browser("),
        )


if __name__ == "__main__":
    unittest.main()
