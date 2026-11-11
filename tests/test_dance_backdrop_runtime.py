"""Transport regressions that do not require TouchDesigner or private media."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RangedValue:
    def __init__(self, value=0.):
        self.value = value
        self.range_writes = 0

    def __float__(self):
        return float(self.value)

    def __setattr__(self, name, value):
        if name in ('max', 'normMax'):
            self.range_writes += 1
        object.__setattr__(self, name, value)


class BackdropRuntimeTests(unittest.TestCase):
    def setUp(self):
        path = ROOT/'touchdesigner/scripts/dance_backdrop_runtime.py'
        spec = importlib.util.spec_from_file_location('backdrop_runtime_test', path)
        self.runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runtime)
        self.clip = SimpleNamespace(duration=61.6, fps=30., end=61.6-1/30)
        self.runtime._clip = self.clip
        self.pars = SimpleNamespace(Position=RangedValue(), Referencepose=RangedValue())
        self.component = SimpleNamespace(par=self.pars)

    def test_ranges_are_configured_only_once_per_clip(self):
        for _ in range(120):
            self.assertIs(self.runtime.model(self.component), self.clip)
        self.assertEqual(self.pars.Position.range_writes, 2)
        self.assertEqual(self.pars.Referencepose.range_writes, 2)
        self.assertEqual(self.pars.Position.max, self.clip.duration)
        self.assertEqual(self.pars.Referencepose.normMax, self.clip.end)

    def test_replacement_clip_updates_ranges_once(self):
        self.runtime.model(self.component)
        new_clip = SimpleNamespace(duration=120., fps=60., end=120.-1/60)
        self.runtime._clip = new_clip
        for _ in range(120):
            self.runtime.model(self.component)
        self.assertEqual(self.pars.Position.range_writes, 4)
        self.assertEqual(self.pars.Referencepose.range_writes, 4)
        self.assertEqual(self.pars.Duration, 120.)
        self.assertEqual(self.pars.Framerate, 60.)
        self.assertEqual(self.pars.Referencepose.max, new_clip.end)

    def test_frame_refresh_does_not_rebuild_parameter_ranges(self):
        for name in ('Motionoffset', 'Smoothing', 'Confidence', 'Stagezoom',
                     'Stagepanx', 'Stagepany', 'Posefollow', 'Velocityresponse',
                     'Bodyweight', 'Handweight', 'Footweight', 'Dancer1', 'Dancer2'):
            setattr(self.pars, name, .1)
        self.pars.Mirror = False
        self.pars.Playing = True
        shader = SimpleNamespace(par={})
        math = SimpleNamespace(module=SimpleNamespace(
            vectors=lambda *a, **kw: ([[0., 0., .1, .1]]*12, [0.5, 0.5])))
        nodes = {'motion_math': math, 'motion_warp': shader}
        self.component.op = nodes.__getitem__
        for frame in range(120):
            self.pars.Position.value = frame/60
            self.runtime.refresh(self.component)
        self.assertEqual(self.pars.Position.range_writes, 2)
        self.assertEqual(self.pars.Referencepose.range_writes, 2)
        self.assertEqual(len(shader.par), 48)
        self.assertTrue(self.pars.Status.startswith('PLAYING'))


if __name__ == '__main__':
    unittest.main()
