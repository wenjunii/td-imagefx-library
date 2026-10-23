"""Preparation stays off-air and preserves cue-owned animation settings."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class PreloadTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.ext.prepared = {}
        self.ext.tracks = {}
        self.ext.audio = {}
        self.ext.automations = {}
        self.ext.ownerComp = Mock()
        self.ext._status = Mock()
        self.ext._release_audio = Mock()
        self.ext._halt_deck = Mock()

    def test_ready_rejects_incomplete_and_failed_preparation(self):
        cue = show.new_cue()
        self.ext._media_ready = Mock(return_value=True)
        self.ext.prepared[cue['id']] = {'loading': True}
        self.assertFalse(self.ext.ready(cue))
        self.ext._media_ready.assert_not_called()
        self.ext.prepared[cue['id']] = {'loading': False, 'error': 'broken shader'}
        with self.assertRaisesRegex(ValueError, 'broken shader'):
            self.ext.ready(cue)

    def test_prepare_does_not_apply_or_publish_standby_synchronously(self):
        cue = show.new_cue()
        deck = Mock()
        self.ext._deck = Mock(return_value=deck)
        self.ext._media_path = Mock(return_value='')
        self.ext._apply_look_steps = Mock()
        self.ext._prepare(cue)
        self.assertFalse(deck.allowCooking)
        self.ext._apply_look_steps.assert_not_called()
        self.assertTrue(self.ext.prepared[cue['id']]['loading'])
        self.assertEqual(self.ext.ownerComp.op.return_value.par.top, 'black')

    def test_replaced_standby_is_never_started_with_default_parameters(self):
        cue = show.new_cue()
        self.ext.prepared[cue['id']] = {'deck_id': 123, 'deck': SimpleNamespace(id=456)}
        with self.assertRaisesRegex(ValueError, 'replaced'):
            self.ext.ready(cue)

    def test_preparation_error_does_not_stop_current_track(self):
        def broken():
            yield
            raise ValueError('cannot decode')
        cue = show.new_cue()
        live = {'cue': show.new_cue(), 'deck': Mock()}
        self.ext.tracks[1] = live
        item = {'cue': cue, 'steps': broken(), 'loading': True, 'deck': Mock()}
        self.ext.prepared[cue['id']] = item
        with patch('touchdesigner.extensions.ShowControlExt.absTime', SimpleNamespace(frame=5), create=True):
            self.ext._service_preloads()
        self.assertEqual(item['error'], 'cannot decode')
        self.assertIs(self.ext.tracks[1], live)
        self.ext._halt_deck.assert_called_once_with(item)

    def test_warm_up_requires_a_later_frame(self):
        cue = show.new_cue()
        def steps():
            yield
        item = {'cue': cue, 'steps': steps(), 'loading': True, 'warm_frame': 10}
        self.ext.prepared[cue['id']] = item
        with patch('touchdesigner.extensions.ShowControlExt.absTime', SimpleNamespace(frame=10), create=True):
            self.ext._service_preloads()
        self.assertTrue(item['loading'])
        with patch('touchdesigner.extensions.ShowControlExt.absTime', SimpleNamespace(frame=11), create=True):
            self.ext._service_preloads()
        self.assertFalse(item['loading'])

    def test_saved_time_scale_is_used_for_cue_animation(self):
        module = SimpleNamespace(par=SimpleNamespace(Manualtime=0, Timescale=Mock()))
        module.par.Timescale.eval.return_value = .25
        deck = Mock()
        deck.op.return_value = module
        deck.fetch.return_value = {}
        cue = dict(show.new_cue(), fade=0)
        self.ext.ownerComp.par = {}
        self.ext.tracks[1] = {'cue': cue, 'deck': deck, 'started': 2, 'side': 0}
        self.ext.tick(6)
        self.assertEqual(module.par.Manualtime, 1)
        module.par.Timescale.eval.return_value = 0
        self.ext.tick(8)
        self.assertEqual(module.par.Manualtime, 0)
        module.par.Timescale.eval.return_value = -.5
        self.ext.tick(8)
        self.assertEqual(module.par.Manualtime, -3)
        deck.fetch.return_value = {name: {'time': 23.5, 'running': True}
                                   for name in (*show.MODULES, 'fx_rack')}
        self.ext.tick(8)
        self.assertEqual(module.par.Manualtime, 20.5)
        for clock in deck.fetch.return_value.values():
            clock['running'] = False
        self.ext.tick(20)
        self.assertEqual(module.par.Manualtime, 23.5)


if __name__ == '__main__':
    unittest.main()
