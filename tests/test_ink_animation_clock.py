"""Animation Speed changes rate, never the current rendered composition."""
import runpy
from pathlib import Path
from types import SimpleNamespace
import unittest
from tdimagefx import show


SOURCE = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                           'touchdesigner/scripts/ink_dream_flow.py'))['ANIMATION_CLOCK_SOURCE']
CLOCK = {}
exec(SOURCE, CLOCK)


class Value:
    def __init__(self, value):
        self.value = value

    def eval(self):
        return self.value


class Component:
    def __init__(self, raw=0., speed=1.):
        self.par = SimpleNamespace(Time=Value(raw), Animationspeed=Value(speed), Fieldspeed=Value(0.))
        self.storage = {}
        self.startup = {}

    def store(self, key, value):
        self.storage[key] = value

    def fetch(self, key, default=None, search=False):
        return self.storage.get(key, default)

    def storeStartupValue(self, key, value):
        self.startup[key] = value


class InkAnimationClockTests(unittest.TestCase):
    def speed(self, component, value, callback=True):
        previous = component.par.Animationspeed.value
        component.par.Animationspeed.value = value
        if callback:
            CLOCK['change_speed'](component, previous)
        return CLOCK['sample'](component)

    def test_default_one_preserves_original_time_and_seeking(self):
        c = Component(3.7)
        for raw in (3.7, 20., 2., -10., 3.7):
            c.par.Time.value = raw
            self.assertAlmostEqual(CLOCK['sample'](c), raw)

    def test_slow_fast_and_freeze_resume_are_continuous(self):
        c = Component(10.)
        self.assertEqual(CLOCK['sample'](c), 10.)
        self.assertEqual(self.speed(c, .5), 10.)
        c.par.Time.value = 12.
        self.assertEqual(CLOCK['sample'](c), 11.)
        self.assertEqual(self.speed(c, 2.), 11.)
        c.par.Time.value = 13.
        self.assertEqual(CLOCK['sample'](c), 13.)
        self.assertEqual(self.speed(c, 0.), 13.)
        c.par.Time.value = 100.
        self.assertEqual(CLOCK['sample'](c), 13.)
        self.assertEqual(self.speed(c, 1.), 13.)
        c.par.Time.value = 101.
        self.assertEqual(CLOCK['sample'](c), 14.)

    def test_repeated_rate_changes_at_same_time_do_not_seek(self):
        c = Component(123.45)
        CLOCK['sample'](c)
        for speed in (10., 0., .25, 4., 2., .5, 1.):
            self.assertEqual(self.speed(c, speed), 123.45)

    def test_fallback_without_callback_preserves_phase(self):
        c = Component(10.)
        CLOCK['sample'](c)
        c.par.Time.value = 12.
        self.assertEqual(self.speed(c, 2., callback=False), 12.)
        c.par.Time.value = 13.
        self.assertEqual(CLOCK['sample'](c), 14.)

    def test_first_change_uses_previous_speed_before_first_render(self):
        c = Component(12.)
        self.assertEqual(self.speed(c, 2.), 12.)
        c.par.Time.value = 13.
        self.assertEqual(CLOCK['sample'](c), 14.)

    def test_saved_phase_supports_seek_reverse_and_offline_export(self):
        c = Component(17., .5)
        CLOCK['reset'](c, raw=17., phase=8.)
        for raw, expected in ((17., 8.), (21., 10.), (15., 7.), (17., 8.)):
            c.par.Time.value = raw
            self.assertEqual(CLOCK['sample'](c), expected)

    def test_old_cues_keep_legacy_render_phase(self):
        c = Component(5., 2.)
        CLOCK['reset'](c)
        self.assertEqual(CLOCK['sample'](c), 10.)

    def test_session_anchor_is_not_reused_after_reopening(self):
        c = Component(100., 2.)
        CLOCK['reset'](c, phase=17.)
        self.assertEqual(c.startup, {CLOCK['KEY']: None})
        c.storage.update(c.startup)
        c.par.Time.value = 0.
        self.assertEqual(CLOCK['sample'](c), 0.)

    def test_inactive_cue_capture_matches_embedded_render_clock(self):
        self.assertEqual(CLOCK['KEY'], show.INK_CLOCK_KEY)
        c = Component(17., .5)
        CLOCK['reset'](c, phase=8.)
        for raw, speed in ((18., .5), (20., 2.), (21., 0.), (40., 1.)):
            c.par.Time.value, c.par.Animationspeed.value = raw, speed
            captured = show.ink_render_time(raw, speed, c.fetch(show.INK_CLOCK_KEY))
            self.assertEqual(captured, CLOCK['sample'](c))
        self.assertEqual(show.ink_render_time(5., 2.), 10.)

    def test_field_speed_changes_are_continuous_and_can_reverse(self):
        c = Component(10.)
        self.assertEqual(CLOCK['field_sample'](c), 0.)
        c.par.Fieldspeed.value = 1.
        self.assertEqual(CLOCK['change_field_speed'](c, 0.), 0.)
        c.par.Time.value = 12.
        self.assertEqual(CLOCK['field_sample'](c), 2.)
        c.par.Fieldspeed.value = -2.
        self.assertEqual(CLOCK['change_field_speed'](c, 1.), 2.)
        c.par.Time.value = 13.
        self.assertEqual(CLOCK['field_sample'](c), 0.)

    def test_field_clock_holds_with_zero_or_master_freeze(self):
        c = Component(10.)
        c.par.Fieldspeed.value = 1.
        CLOCK['field_reset'](c, phase=3.)
        self.speed(c, 0.)
        c.par.Time.value = 30.
        self.assertEqual(CLOCK['field_sample'](c), 3.)
        self.speed(c, 1.)
        c.par.Fieldspeed.value = 0.
        CLOCK['change_field_speed'](c, 1.)
        c.par.Time.value = 40.
        self.assertEqual(CLOCK['field_sample'](c), 3.)

    def test_field_cue_phase_and_export_reproduce_motion(self):
        c = Component(17., .5)
        c.par.Fieldspeed.value = .75
        CLOCK['reset'](c, phase=8.)
        CLOCK['field_reset'](c, phase=4.)
        self.assertEqual(CLOCK['FIELD_KEY'], show.INK_FIELD_CLOCK_KEY)
        c.par.Time.value = 21.
        self.assertEqual(CLOCK['field_sample'](c), 5.5)
        self.assertEqual(show.ink_render_time(10., .75, c.fetch(show.INK_FIELD_CLOCK_KEY)), 5.5)
        c.par.Time.value = 17.
        self.assertEqual(CLOCK['field_sample'](c), 4.)
        self.assertIsNone(c.startup[show.INK_FIELD_CLOCK_KEY])


if __name__ == '__main__':
    unittest.main()
