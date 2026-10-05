"""Portable math and ordering regressions; native pixels have separate tests."""
from pathlib import Path
import random
import runpy
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CROP = runpy.run_path(str(ROOT / "touchdesigner/scripts/final_crop.py"))
FLOW = runpy.run_path(str(ROOT / "touchdesigner/scripts/workflow.py"))


class FinalCropTests(unittest.TestCase):
    def test_live_diagnostics_accept_one_pixel_but_reject_empty_output(self):
        scope = runpy.run_path(str(ROOT / "touchdesigner/scripts/validate_live_project.py"))
        diagnose = scope["_output_diagnostics"]
        top = SimpleNamespace(width=1, height=1, family="TOP", type="null",
                              cook=lambda **kwargs: None, errors=lambda **kwargs: [])
        with mock.patch.dict(diagnose.__globals__, {"op": lambda path: top}):
            self.assertTrue(diagnose("/crop/output")["usable"])
            for width, height in ((0, 1), (1, 0), (-1, 1)):
                top.width, top.height = width, height
                self.assertFalse(diagnose("/crop/output")["usable"])

    def test_neutral_and_square(self):
        g = CROP["geometry"]
        self.assertEqual(g(1920,1080)["pixels"], (0,0,1920,1080))
        self.assertEqual(g(1920,1080,"1x1")["pixels"], (420,0,1080,1080))
        self.assertEqual(g(3840,2160,"1x1")["size"], (2160,2160))

    def test_all_aspect_presets(self):
        for preset, ratio in CROP["RATIOS"].items():
            size = CROP["geometry"](1920,1080,preset)["size"]
            self.assertLessEqual(size[0],1920)
            self.assertLessEqual(size[1],1080)
            self.assertLess(abs(size[0]-size[1]*ratio), ratio+1)

    def test_manual_trim_uses_top_and_bottom_correctly(self):
        self.assertEqual(CROP["geometry"](1000,500,trims=(10,20,30,10))["pixels"],(100,50,700,300))

    def test_anchor_limits(self):
        self.assertEqual(CROP["geometry"](1920,1080,"1x1",anchor=(0,0))["pixels"],(0,0,1080,1080))
        self.assertEqual(CROP["geometry"](1920,1080,"1x1",anchor=(1,1))["pixels"],(840,0,1080,1080))
        self.assertEqual(CROP["geometry"](1080,1920,"1x1",anchor=(1,1))["pixels"],(0,840,1080,1080))

    def test_custom_ratio_and_source_ratio(self):
        self.assertEqual(CROP["geometry"](1600,900,"custom",ratio=(2,1))["size"],(1600,800))
        self.assertEqual(CROP["geometry"](1600,900,"source",trims=(10,10,0,0))["size"],(1280,720))

    def test_extreme_trims_are_bounded(self):
        rng = random.Random(41)
        for _ in range(1000):
            w,h = rng.randint(1,8192),rng.randint(1,8192)
            g = CROP["geometry"](w,h,"custom",ratio=(rng.uniform(.01,8192),rng.uniform(.01,8192)),trims=[rng.uniform(0,100) for _ in range(4)],anchor=(rng.random(),rng.random()))
            x,y,cw,ch = g["pixels"]
            self.assertTrue(0 <= x < w and 0 <= y < h)
            self.assertTrue(cw >= 1 and ch >= 1 and x+cw <= w and y+ch <= h)
        self.assertTrue(CROP["geometry"](100,100,trims=(100,100,100,100))["limited"])

    def test_nonfinite_controls_fall_back_safely(self):
        g = CROP["geometry"](100,100,"custom",ratio=(float("nan"),float("inf")),trims=(float("nan"),0,0,0),anchor=(float("nan"),float("inf")))
        self.assertTrue(all(0 <= v <= 1 for v in g["uv"]))

    def test_crop_parameters_and_show_contract(self):
        from tdimagefx.show import MODULE_TOGGLES, new_cue, validate_cue
        definitions = CROP["PARAMETERS"]
        self.assertEqual(len(definitions),len({d["name"] for d in definitions}))
        for d in definitions:
            if "min" in d:
                self.assertLess(d["min"],d["max"])
        self.assertEqual(MODULE_TOGGLES["final_crop"],"Finalcropenabled")
        self.assertEqual(validate_cue(dict(new_cue(),kind="parameters",target="final_crop/Left",value=10))["value"],10)


class WorkflowTests(unittest.TestCase):
    def test_default_order_has_final_layers_and_crop(self):
        from tdimagefx.show import MODULES
        self.assertEqual(set(FLOW["DEFAULT_ORDER"]),set(MODULES)|{"fx_rack"})
        self.assertEqual(FLOW["DEFAULT_ORDER"][-2:],("layer_composite","final_crop"))

    def test_invalid_orders_rejected(self):
        order = list(FLOW["DEFAULT_ORDER"])
        for invalid in (None,{},"x",order[:-1],order+[order[0]],order[:-1]+[order[0]],order[:-1]+["unknown"],order[:-1]+[{}]):
            with self.assertRaises(ValueError): FLOW["validate_order"](invalid)

    def test_every_stage_can_move_to_every_position(self):
        default = list(FLOW["DEFAULT_ORDER"])
        for name in default:
            order = FLOW["moved_order"](default,name,"Stagefirst")
            self.assertEqual(order[0],name)
            self.assertEqual(FLOW["moved_order"](order,name,"Stageup"),order)
            for index in range(1,len(order)):
                order = FLOW["moved_order"](order,name,"Stagedown")
                self.assertEqual(order[index],name)
                self.assertEqual(set(order),set(default))
            self.assertEqual(FLOW["moved_order"](order,name,"Stagedown"),order)
            self.assertEqual(FLOW["moved_order"](order,name,"Resetorder"),default)
            self.assertEqual(default,list(FLOW["DEFAULT_ORDER"]))

    def test_unknown_actions_rejected(self):
        for name, action in (("unknown","Stageup"),("fx_rack","bad")):
            with self.assertRaises(ValueError): FLOW["moved_order"](FLOW["DEFAULT_ORDER"],name,action)
