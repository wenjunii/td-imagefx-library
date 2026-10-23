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
        self.values = dict(Selectedcue=1, Cuepage=1, Looklivetrack=2, Routingmode='independent',
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
        self.assertEqual(self.ext.CueRowNotes(0), 'Line one 第二行')

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

    def test_row_notes_are_specific_to_each_cue(self):
        self.ext.document['cues'] = [dict(show.new_cue(), notes=text)
                                     for text in ('Wait for LX 12', 'Start on music', '')]
        self.assertEqual([self.ext.CueRowNotes(i) for i in range(3)],
                         ['Wait for LX 12', 'Start on music', '—'])
        self.assertEqual(self.ext.CueRowNotes(3), '')

    def test_note_preview_preserves_full_multiline_unicode_text(self):
        self.cue['notes'] = '  Stand by\r\n第二行\t /  hold for dancer  '
        original = copy.deepcopy(self.ext.document)
        self.assertEqual(self.ext.CueRowNotes(0), 'Stand by 第二行 / hold for dancer')
        self.assertEqual(self.ext.document, original)
        self.assertNotEqual(self.ext.CueRowNotes(0), self.values['Notes'])

    def test_long_note_preview_is_truncated_but_saved_text_is_untouched(self):
        self.cue['notes'] = 'A' * 4000
        self.assertEqual(self.ext.CueRowNotes(0), 'A' * 51 + '…')
        self.assertEqual(len(self.cue['notes']), 4000)

    def test_wide_characters_fit_the_row_preview(self):
        self.cue['notes'] = '第二行' * 30
        self.assertEqual(self.ext.CueRowNotes(0), self.cue['notes'][:25] + '…')
        self.cue['notes'] = 'e\u0301' * 52
        self.assertEqual(self.ext.CueRowNotes(0), self.cue['notes'])

    def test_page_change_and_invalid_rows_do_not_leak_other_cue_notes(self):
        self.ext.document['cues'] = [dict(show.new_cue(), notes='Note {}'.format(i)) for i in range(15)]
        self.values['Cuepage'] = 2
        self.assertEqual([self.ext.CueRowNotes(i) for i in range(4)], ['Note 12', 'Note 13', 'Note 14', ''])
        for row in (-1, 12):
            self.assertEqual(self.ext.CueRowNotes(row), '')
            self.assertEqual(self.ext.CueLabel(row), '')

    def test_notes_follow_cue_when_reordered(self):
        self.ext.document['cues'] = [dict(show.new_cue(), notes='First'), dict(show.new_cue(), notes='Second')]
        self.ext.document['cues'].reverse()
        self.assertEqual([self.ext.CueRowNotes(i) for i in (0, 1)], ['Second', 'First'])

    def test_compact_cue_label_retains_number_track_and_transport_state(self):
        self.cue['name'] = 'A very long cue name that should not hide state'
        self.ext.engine.pending[self.cue['id']] = object()
        label = self.ext.CueLabel(0, compact=True)
        self.assertIn('> 001', label)
        self.assertIn('…', label)
        self.assertTrue(label.endswith('| visual / track 1 | WAIT'))

    def test_refresh_updates_both_columns_and_clears_unused_rows(self):
        self.cue['notes'] = 'Ready for dancer'
        nodes = {name: Mock() for name in ('cue_list', 'cue_text')}
        nodes.update({'cue_row_{}'.format(i): Mock() for i in range(12)})
        nodes.update({'cue_notes_{}'.format(i): Mock() for i in range(12)})
        self.ext.ownerComp.op = nodes.get
        self.ext.prepared = {}
        ShowControlExt.Refresh(self.ext)
        self.assertEqual(nodes['cue_row_0'].par.label, self.ext.CueLabel(0, compact=True))
        self.assertEqual(nodes['cue_notes_0'].par.label, 'Ready for dancer')
        self.assertEqual(nodes['cue_notes_11'].par.label, '')
        self.assertEqual(nodes['cue_row_11'].par.label, '')


if __name__ == '__main__':
    unittest.main()
