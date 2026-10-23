"""Saved look phase and play/freeze state must agree in Recall, GO and export."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.scripts.show_review_export import _set_time


class LookAnimationTests(unittest.TestCase):
    def look(self, **clock):
        return {'animation': {'ink_dream_flow': dict(time=23.5, running=True, **clock)}}

    def test_old_look_starts_at_zero_and_new_clock_continues(self):
        self.assertEqual(show.animation_time({}, 'ink_dream_flow', 4, .3), 1.2)
        animation = self.look()['animation']
        self.assertEqual(show.animation_time(animation, 'ink_dream_flow', 0, .3), 23.5)
        self.assertEqual(show.animation_time(animation, 'ink_dream_flow', 4, -.5), 21.5)
        self.assertEqual(show.animation_time(animation, 'ink_dream_flow', 99, 0), 23.5)

    def test_frozen_phase_does_not_advance(self):
        animation = {'ink_brush_flow': {'time': -5.25, 'running': False}}
        self.assertEqual(show.animation_time(animation, 'ink_brush_flow', 100, 9), -5.25)

    def test_show_roundtrip_preserves_phase_and_freeze(self):
        look = self.look(render_time=12.75)
        look['branches'] = {'a_effects': {'animation': {'ink_radial_flow': {'time': -9, 'running': False, 'render_time': 30.}}}}
        cue = dict(show.new_cue(), look=look)
        doc = dict(kind=show.SHOW_KIND, schema_version=1, cues=[cue], mapping={})
        self.assertEqual(show.validate_show(doc), doc)

    def test_bad_render_phase_is_rejected(self):
        for value in (float('nan'), float('inf'), True, '3', 1e13):
            with self.subTest(value=value), self.assertRaises(ValueError):
                show.validate_cue(dict(show.new_cue(), look=self.look(render_time=value)))
        with self.assertRaises(ValueError):
            show.validate_cue(dict(show.new_cue(), look={'animation': {
                'calligraphic_shadow': dict(time=1, running=True, render_time=3)}}))

    def test_bad_phase_metadata_is_rejected(self):
        values = [None, [], {'unknown': {'time': 0, 'running': True}},
                  {'ink_dream_flow': {}}, {'ink_dream_flow': {'time': 0, 'running': True, 'expr': 'bad'}}]
        for value in (float('nan'), float('inf'), True, '3', 1e10):
            values.append({'ink_dream_flow': {'time': value, 'running': True}})
        for value in (0, 1, 'false', None):
            values.append({'ink_dream_flow': {'time': 0, 'running': value}})
        for animation in values:
            with self.subTest(animation=animation), self.assertRaises(ValueError):
                show.validate_cue(dict(show.new_cue(), look={'animation': animation}))

    def test_invalid_nested_phase_is_rejected_before_loading_media(self):
        look = {'branches': {'a_effects': {'animation': {'ink_dream_flow': {'time': float('nan'), 'running': True}}}}}
        with self.assertRaises(ValueError):
            show.validate_cue(dict(show.new_cue(), look=look))
        with self.assertRaises(ValueError):
            show.validate_look_media(look, '.')

    def test_export_uses_the_same_saved_phase_and_speed(self):
        class Pars(SimpleNamespace):
            def __getitem__(self, name):
                return getattr(self, name, None)
        module = SimpleNamespace(par=Pars(Manualtime=0, Autotime=True, Timescale=Mock()))
        module.par.Timescale.eval.return_value = .25
        deck = Mock()
        deck.op.side_effect = lambda name: module if name == 'ink_dream_flow' else None
        animation = self.look()['animation']
        before = copy.deepcopy(animation)
        deck.fetch.return_value = animation
        _set_time(deck, ('ink_dream_flow',), 4)
        self.assertEqual(module.par.Manualtime, 24.5)
        self.assertFalse(module.par.Autotime)
        self.assertEqual(animation, before)
        animation['ink_dream_flow']['running'] = False
        _set_time(deck, ('ink_dream_flow',), 8)
        self.assertEqual(module.par.Manualtime, 23.5)


if __name__ == '__main__':
    unittest.main()
