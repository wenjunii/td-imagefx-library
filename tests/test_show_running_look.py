"""Running-cue edits must not replace the engine, media or playback clock."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class RunningLookTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.cue = dict(show.new_cue(), name="On air", source="movie.mp4", track=2,
                        look={"toggles": {"Coloradjustmentenabled": True},
                              "animation": {"ink_dream_flow": {"time": 4.0, "running": True}}})
        self.ext.document = show.validate_show(dict(kind=show.SHOW_KIND, schema_version=1,
                                                  cues=[self.cue, show.new_cue()], mapping={}))
        self.cue = self.ext.document["cues"][0]
        self.ext.engine = Mock(state="running", elapsed=42.0, selected=1,
                               active={self.cue["id"]: (0, 4.0)}, cues=copy.deepcopy(self.ext.document["cues"]))
        self.deck = Mock(id=123, path="/show/deck2_0")
        self.item = dict(cue=copy.deepcopy(self.cue), deck=self.deck, movie=Mock(),
                         track=2, side=0, started=4.0, fading=False, finished=False)
        self.ext.tracks = {2: self.item}
        self.ext.automations = {}
        self.ext._look_edit = None
        self.ext.ownerComp = MagicMock()
        self.preview = Mock()
        self.ext.ownerComp.op.side_effect = lambda name: self.deck if name == "deck2_0" else self.preview
        self.ext._p = Mock(return_value=1)
        self.ext._status = Mock()
        self.ext.Refresh = Mock()
        self.ext._save_document_dat = Mock()
        self.ext._clear_look_result = Mock()
        self.original = {"toggles": {"Coloradjustmentenabled": True}}
        self.changed = {"toggles": {"Coloradjustmentenabled": False}}
        self.ext._capture_look = Mock(return_value=copy.deepcopy(self.original))
        self.ext._restore_running_values = Mock()

    def begin(self):
        self.ext.EditRunningLook()
        self.ext._capture_look.return_value = copy.deepcopy(self.changed)

    def test_begin_owns_current_instance_without_mutating_playback(self):
        original = copy.deepcopy(self.ext.document)
        self.begin()
        self.assertIs(self.ext.RunningLookDeck(), self.deck)
        self.assertEqual(self.ext.document, original)
        self.ext.ownerComp.copy.assert_not_called()
        self.ext.engine.stop.assert_not_called()
        self.item["movie"].assert_not_called()
        self.assertEqual(self.item["started"], 4.0)
        self.assertEqual(self.ext.engine.elapsed, 42.0)
        self.assertEqual(self.preview.par.top, 'track2_source0')

    def test_update_changes_only_saved_look_without_transport_reset(self):
        self.begin()
        engine, item = self.ext.engine, self.item
        self.ext.UpdateLook()
        expected = dict(self.changed, animation=copy.deepcopy(self.cue["look"]["animation"]))
        self.assertEqual(self.cue["look"], expected)
        self.assertEqual(engine.cues[0]["look"], expected)
        self.assertIs(self.ext.engine, engine)
        self.assertIs(self.ext.tracks[2], item)
        self.assertEqual(item["started"], 4.0)
        self.assertEqual(item["cue"]["look"]["toggles"], self.original["toggles"])
        engine.stop.assert_not_called()
        self.deck.destroy.assert_not_called()
        self.ext._restore_running_values.assert_not_called()
        self.ext._save_document_dat.assert_called_once()
        self.assertIsNone(self.ext._look_edit)

    def test_cancel_restores_runtime_but_never_writes_cue(self):
        original = copy.deepcopy(self.ext.document)
        self.begin()
        self.ext.CancelLook()
        self.ext._restore_running_values.assert_called_once_with(self.deck, self.original)
        self.assertEqual(self.ext.document, original)
        self.ext._save_document_dat.assert_not_called()
        self.ext.engine.stop.assert_not_called()
        self.deck.destroy.assert_not_called()

    def test_pause_does_not_lose_edit_or_block_resume(self):
        self.begin()
        self.ext.engine.state = "paused"
        self.assertIs(self.ext.RunningLookDeck(), self.deck)
        self.ext.Resume()
        self.ext.engine.resume.assert_called_once()
        self.ext.CancelLook()

    def test_rejects_stopped_paused_nonvisual_or_wrong_row(self):
        for state in ("stopped", "paused"):
            self.ext.engine.state = state
            with self.assertRaisesRegex(ValueError, "Run or resume"):
                self.ext.EditRunningLook()
        self.ext.engine.state = "running"
        for kind in ("audio", "blackout", "parameters", "stop"):
            self.cue["kind"] = kind
            with self.assertRaisesRegex(ValueError, "PLAY"):
                self.ext.EditRunningLook()
        self.cue["kind"] = "visual"
        self.ext._p.return_value = 2
        with self.assertRaisesRegex(ValueError, "PLAY"):
            self.ext.EditRunningLook()

    def test_rejects_fade_automation_and_held_cue(self):
        self.item["fading"] = True
        with self.assertRaisesRegex(ValueError, "crossfade"):
            self.ext.EditRunningLook()
        self.item["fading"] = False
        self.ext.automations = {"a": {"cue": {"track": 2}}}
        with self.assertRaisesRegex(ValueError, "automation"):
            self.ext.EditRunningLook()
        self.ext.automations.clear()
        self.item["finished"] = True
        with self.assertRaisesRegex(ValueError, "PLAY"):
            self.ext.EditRunningLook()

    def test_foreign_or_reused_deck_is_never_edited(self):
        self.begin()
        self.ext.tracks[2] = dict(self.item)
        with self.assertRaisesRegex(ValueError, "ended or changed"):
            self.ext.RunningLookDeck()
        self.ext.tracks[2] = self.item
        self.deck.id = 999
        with self.assertRaisesRegex(ValueError, "ended or changed"):
            self.ext.CancelLook()
        self.ext._restore_running_values.assert_not_called()

    def test_ended_draft_can_be_committed_without_touching_new_deck(self):
        self.begin()
        self.ext._detach_running_look(self.item)
        self.assertIsNone(self.ext._look_edit["deck"])
        self.ext.tracks[2] = {"deck": Mock()}
        self.ext.UpdateLook()
        self.assertEqual(self.cue["look"]["toggles"], self.changed["toggles"])
        self.ext._restore_running_values.assert_not_called()
        self.deck.destroy.assert_not_called()

    def test_detach_preserves_outgoing_image_and_cancel_discards_values(self):
        self.begin()
        self.ext._detach_running_look(self.item)
        self.ext.CancelLook()
        self.ext._restore_running_values.assert_not_called()
        self.ext._save_document_dat.assert_not_called()
        self.assertEqual(self.cue["look"]["toggles"], self.original["toggles"])

    def test_detach_capture_failure_does_not_break_transport(self):
        self.begin()
        self.ext._capture_look.side_effect = ValueError("bad layer path")
        self.ext._detach_running_look(self.item)
        with self.assertRaisesRegex(ValueError, "could not be captured"):
            self.ext.UpdateLook()
        self.ext.CancelLook()
        self.assertIsNone(self.ext._look_edit)

    def test_stop_track_captures_before_removing_identity(self):
        self.begin()
        self.ext._release_audio = Mock()
        self.ext._halt_deck = Mock()
        self.ext._stop_track(2)
        self.assertNotIn(2, self.ext.tracks)
        self.assertNotIn("capture_error", self.ext._look_edit)
        self.assertEqual(self.ext._look_edit["pending_look"]["toggles"], self.changed["toggles"])

    def test_invalid_commit_and_external_changes_leave_draft(self):
        self.begin()
        self.ext._capture_look.return_value = {"bad": float("nan")}
        with self.assertRaises(ValueError):
            self.ext.UpdateLook()
        self.assertIsNotNone(self.ext._look_edit)
        self.cue["name"] = "External"
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.ext.UpdateLook()

    def test_manual_transport_allowed_but_save_new_and_offair_audition_rejected(self):
        self.begin()
        self.ext.SelectCue = Mock()
        self.ext.Go()
        self.ext.engine.go.assert_called_once_with(0)
        self.ext.GoBack()
        self.ext.engine.go_back.assert_called_once()
        for action in (self.ext.SaveLookAsNew, self.ext.ShowLiveLook):
            with self.assertRaises(ValueError):
                action()

    def test_starting_clocks_are_preserved_recursively_not_elapsed_time(self):
        look = {"animation": {"x": 99}, "rack": {"time": 100, "autotime": False},
                "branches": {"a_effects": {"animation": {"x": 200}, "rack": {"time": 300}}}}
        saved = {"animation": {"x": 3}, "rack": {"time": 2, "autotime": True},
                 "branches": {"a_effects": {"rack": {"time": 7, "autotime": False}}}}
        result = self.ext._keep_starting_clocks(look, saved)
        self.assertEqual(result["animation"], {"x": 3})
        self.assertEqual(result["rack"], {"time": 2, "autotime": True})
        self.assertNotIn("animation", result["branches"]["a_effects"])
        self.assertEqual(result["branches"]["a_effects"]["rack"], {"time": 7, "autotime": False})

    def test_notes_on_other_row_do_not_change_draft_cue(self):
        self.begin()
        other = self.ext.document["cues"][1]
        self.ext._p.side_effect = lambda key: 2 if key == "Selectedcue" else "New note"
        self.ext.SaveCueNotes()
        self.assertEqual(other["notes"], "New note")
        self.assertEqual(self.ext._look_edit["cue"]["notes"], self.cue["notes"])

    def test_save_committed_show_during_playback_leaves_engine_untouched(self):
        self.ext.ownerComp.customPars = []
        self.ext._mapping_matrices = Mock()
        engine = self.ext.engine
        with tempfile.TemporaryDirectory() as directory:
            # macOS temp roots can traverse /var -> /private/var. Use the
            # real directory; SaveShow deliberately rejects symlink paths.
            path = Path(directory).resolve() / "show.json"
            self.ext._p.return_value = str(path)
            self.ext.SaveShow()
            self.assertEqual(json.loads(path.read_text())["cues"][0]["id"], self.cue["id"])
        self.assertIs(self.ext.engine, engine)
        engine.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
