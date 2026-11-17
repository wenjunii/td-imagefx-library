"""Running-cue emphasis is view-only and follows the actual playback decks."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class CueHighlightTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.cues = [dict(show.new_cue(), name='Cue '+str(i), track=i % 3 + 1) for i in range(15)]
        self.ext.document = dict(cues=self.cues)
        self.ext.model = show
        self.ext.engine = show.CueEngine(self.cues, Mock())
        self.ext.tracks = {}
        self.ext.prepared = {}
        self.values = dict(Cuepage=1, Selectedcue=2)
        self.ext._p = self.values.__getitem__

    def playing(self, index, **kwargs):
        cue = self.cues[index]
        self.ext.engine.state = 'running'
        self.ext.engine.active[cue['id']] = (index, 0.)
        self.ext.tracks[cue['track']] = dict(cue=cue, **kwargs)

    def test_running_row_is_distinct_from_selection(self):
        self.playing(0)
        running, selected = self.ext.CueRowStyle(0), self.ext.CueRowStyle(1)
        self.assertEqual(running['state'], 'running')
        self.assertFalse(running['selected'])
        self.assertTrue(selected['selected'])
        self.assertNotEqual(running['color'], selected['color'])
        self.assertTrue(self.ext.CueLabel(0).endswith('| PLAY'))

    def test_selecting_running_cue_preserves_green_and_adds_border(self):
        self.playing(0)
        before = self.ext.CueRowStyle(0)
        self.values['Selectedcue'] = 1
        after = self.ext.CueRowStyle(0)
        self.assertEqual(before['color'], after['color'])
        self.assertTrue(after['selected'])

    def test_pause_resume_changes_color_and_label_without_mutating_cues(self):
        self.playing(0)
        before = copy.deepcopy(self.ext.document)
        color = self.ext.CueRowStyle(0)['color']
        self.ext.engine.state = 'paused'
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'paused')
        self.assertNotEqual(self.ext.CueRowStyle(0)['color'], color)
        self.assertTrue(self.ext.CueLabel(0).endswith('| PAUSE'))
        self.ext.engine.state = 'running'
        self.assertEqual(self.ext.CueRowStyle(0)['color'], color)
        self.assertEqual(self.ext.document, before)

    def test_three_tracks_can_all_be_highlighted(self):
        for i in range(3): self.playing(i)
        self.assertEqual([self.ext.CueRowStyle(i)['state'] for i in range(3)], ['running'] * 3)

    def test_outgoing_crossfade_clears_when_its_deck_is_retired(self):
        self.playing(0)
        old = self.ext.tracks[1]
        self.playing(3, old=old, fading=True)
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'fading')
        self.assertEqual(self.ext.CueRowStyle(0)['color'], self.ext.CueRowStyle(3)['color'])
        self.ext.tracks[1].update(old=None, fading=False)
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'replaced')
        self.assertTrue(self.ext.CueLabel(0).endswith('| done'))
        self.assertNotEqual(self.ext.CueRowStyle(0)['color'], self.ext.CueRowStyle(3)['color'])

    def test_held_frame_is_not_reported_as_playing(self):
        self.playing(0, finished=True)
        self.ext.engine.active.clear()
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'held')
        self.assertTrue(self.ext.CueLabel(0).endswith('| HOLD'))

    def test_audio_errors_pending_and_disabled_keep_distinct_states(self):
        cue = self.cues[0]
        cue['kind'] = 'audio'
        self.ext.engine.state = 'running'
        self.ext.engine.active[cue['id']] = (0, 0.)
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'running')
        self.ext.engine.errors[cue['id']] = 'test failure'
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'error')
        self.ext.engine.errors.clear(); self.ext.engine.active.clear()
        self.ext.engine.pending[cue['id']] = (0, 1., 0.)
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'waiting')
        self.ext.engine.pending.clear(); cue['enabled'] = False
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'disabled')

    def test_stop_clears_running_style(self):
        self.playing(0)
        self.ext.tracks.clear(); self.ext.engine.active.clear(); self.ext.engine.state = 'stopped'
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'ready')

    def test_page_and_unused_rows_do_not_leak_old_highlight(self):
        self.playing(12)
        self.values.update(Cuepage=2, Selectedcue=13)
        self.assertEqual(self.ext.CueRowStyle(0)['state'], 'running')
        for row in (3, 11, 12, -1):
            self.assertEqual(self.ext.CueRowStyle(row)['state'], 'empty')
            self.assertFalse(self.ext.CueRowStyle(row)['selected'])

    def test_both_columns_match_and_same_style_does_not_rewrite_parameters(self):
        self.playing(0)
        self.values['Selectedcue'] = 1
        nodes = [SimpleNamespace(id=i, par=Mock()) for i in (100, 101)]
        style = self.ext.CueRowStyle(0)
        for node in nodes:
            self.ext._style_cue_row(node, style)
            self.assertEqual(tuple(getattr(node.par, 'color'+axis) for axis in 'rgb'), style['color'])
            self.assertEqual(tuple(getattr(node.par, 'bgcolor'+axis) for axis in 'rgb'), style['color'])
            self.assertEqual(node.par.bgalpha, 1)
            for edge in ('leftborder', 'rightborder', 'topborder', 'bottomborder'):
                self.assertEqual(getattr(node.par, edge), 'bordera')
            node.par.colorr = 'unchanged sentinel'
            self.ext._style_cue_row(node, style)
            self.assertEqual(node.par.colorr, 'unchanged sentinel')
        self.values['Selectedcue'] = 2
        self.ext._style_cue_row(nodes[0], self.ext.CueRowStyle(0))
        for edge in ('leftborder', 'rightborder', 'topborder', 'bottomborder'):
            self.assertEqual(getattr(nodes[0].par, edge), 'off')
        nodes[0].par.value.assert_not_called()


if __name__ == '__main__':
    unittest.main()
