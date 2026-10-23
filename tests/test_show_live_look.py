"""Live audition routing and metadata-only cue notes do not commit draft looks."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class Par:
    def __init__(self, value): self.value = value
    def eval(self): return self.value


class LiveLookTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.cue = show.new_cue()
        self.ext.document = dict(kind=show.SHOW_KIND, schema_version=1, cues=[self.cue], mapping={})
        self.ext.engine = show.CueEngine([self.cue], Mock())
        self.ext.ownerComp = Mock()
        self.ext.ownerComp.par = SimpleNamespace(Looklive=Par(True))
        self.deck = Mock()
        self.deck.op.return_value.path = '/show/look_editor/out1_image'
        self.ext.ownerComp.op.return_value = self.deck
        self.ext._look_edit = dict(cue=copy.deepcopy(self.cue), deck=self.deck)
        self.values = dict(Selectedcue=1, Looklivetrack=2, Routingmode='independent',
                           Output1track=1, Output2track=2, Output3track=3,
                           Masterblackout=True, Notes='Line one\n第二行')
        self.ext._p = lambda name: self.values[name]
        self.ext._status = Mock()
        self.ext.Refresh = Mock()
        self.ext._save_document_dat = Mock()

    def test_only_target_track_gets_draft(self):
        self.assertEqual(self.ext.ProjectionSource(1), 'track1')
        self.assertEqual(self.ext.ProjectionSource(2), '/show/look_editor/out1_image')
        self.assertEqual(self.ext.ProjectionSource(3), 'track3')
        self.assertEqual(self.cue['look'], {})

    def test_missing_inactive_or_replaced_draft_fails_closed(self):
        self.ext.engine.state = 'running'
        self.assertEqual(self.ext.ProjectionSource(2), 'track2')
        self.ext.engine.state = 'stopped'
        self.ext.ownerComp.op.return_value = None
        self.assertEqual(self.ext.ProjectionSource(2), 'track2')
        self.ext._look_edit = None
        self.assertEqual(self.ext.ProjectionSource(2), 'track2')

    def test_live_status_reports_routing_and_blackout(self):
        self.assertIn('P2', self.ext.LiveLookStatus())
        self.assertIn('MASTER BLACKOUT ON', self.ext.LiveLookStatus())
        self.values['Routingmode'] = 'identical'
        self.assertIn('none (check Routing)', self.ext.LiveLookStatus())
        self.values['Looklivetrack'] = 1
        self.assertIn('P1,2,3', self.ext.LiveLookStatus())

    def test_stop_audition_keeps_draft(self):
        draft = self.ext._look_edit
        self.ext.StopLiveLook()
        self.assertFalse(self.ext.ownerComp.par.Looklive)
        self.assertIs(self.ext._look_edit, draft)
        self.ext._save_document_dat.assert_not_called()

    def test_notes_save_updates_metadata_without_replacing_engine_or_look(self):
        original = copy.deepcopy(self.cue)
        engine, draft = self.ext.engine, self.ext._look_edit
        self.ext.SaveCueNotes()
        self.assertIs(self.ext.engine, engine)
        self.assertIs(self.ext._look_edit, draft)
        self.assertEqual(self.cue, dict(original, notes=self.values['Notes']))
        self.assertEqual(draft['cue'], self.cue)
        self.assertEqual(engine.cues[0]['notes'], self.values['Notes'])
        self.assertEqual(self.ext._look_index(), 0)
        self.ext._save_document_dat.assert_called_once()

    def test_notes_can_be_saved_while_running(self):
        self.ext._look_edit = None
        self.ext.engine.state, self.ext.engine.elapsed = 'running', 8.25
        self.ext.SaveCueNotes()
        self.assertEqual((self.ext.engine.state, self.ext.engine.elapsed), ('running', 8.25))

    def test_invalid_notes_rejected_atomically(self):
        original = copy.deepcopy(self.ext.document)
        for value in ('x' * 4001, 12, None):
            self.values['Notes'] = value
            with self.assertRaises(ValueError): self.ext.SaveCueNotes()
            self.assertEqual(self.ext.document, original)
        self.ext._save_document_dat.assert_not_called()


if __name__ == '__main__':
    unittest.main()
