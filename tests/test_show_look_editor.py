"""Off-air look editing transactions, without a TouchDesigner installation."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class LookEditorTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.ext.engine = SimpleNamespace(state="stopped")
        self.cue = dict(show.new_cue(), name="Original", source="local-movie.mp4",
                        track=3, at=12, follow="continue", media_in=2, speed=1.5,
                        look={"toggles": {"Coloradjustmentenabled": True}})
        self.ext.document = dict(kind=show.SHOW_KIND, schema_version=1,
                                 cues=[copy.deepcopy(self.cue), show.new_cue()], mapping={})
        self.ext.ownerComp = Mock()
        self.ext._look_edit = {"cue": copy.deepcopy(self.cue), "deck": Mock()}
        self.ext._p = Mock(return_value=1)
        self.ext._status = Mock()
        self.ext.SelectCue = Mock()
        self.ext.stop_all = Mock()
        self.ext.Refresh = Mock()
        self.ext._save_document_dat = Mock()
        self.look = {"toggles": {"Coloradjustmentenabled": False}}
        self.ext._capture_look = Mock(return_value=copy.deepcopy(self.look))

    def test_update_changes_only_look_and_cleans_preview(self):
        deck = self.ext._look_edit["deck"]
        self.ext.UpdateLook()
        self.assertEqual(self.ext.document["cues"][0], dict(self.cue, look=self.look))
        self.assertIsNone(self.ext._look_edit)
        deck.destroy.assert_called_once()
        self.ext.SelectCue.assert_called_once_with(1)
        self.ext._save_document_dat.assert_called_once()

    def test_save_new_preserves_original_and_is_disarmed(self):
        previous = copy.deepcopy(self.ext.document["cues"])
        self.ext.SaveLookAsNew()
        cues = self.ext.document["cues"]
        self.assertEqual(cues[:2], previous)
        new = cues[-1]
        self.assertNotEqual(new["id"], self.cue["id"])
        self.assertEqual(new["look"], self.look)
        self.assertEqual(new["source"], self.cue["source"])
        self.assertEqual(new["track"], 3)
        self.assertFalse(new["enabled"])
        self.assertIsNone(new["at"])
        self.assertEqual(new["follow"], "manual")
        self.ext.SelectCue.assert_called_once_with(3)

    def test_cancel_never_writes_document(self):
        original = copy.deepcopy(self.ext.document)
        self.ext.CancelLook()
        self.assertEqual(self.ext.document, original)
        self.ext._save_document_dat.assert_not_called()
        self.assertIsNone(self.ext._look_edit)

    def test_capture_failure_keeps_original_and_draft(self):
        original = copy.deepcopy(self.ext.document)
        draft = self.ext._look_edit
        self.ext._capture_look.side_effect = ValueError("Missing layer media")
        with self.assertRaisesRegex(ValueError, "Missing"):
            self.ext.UpdateLook()
        self.assertEqual(self.ext.document, original)
        self.assertIs(self.ext._look_edit, draft)
        draft["deck"].destroy.assert_not_called()

    def test_invalid_draft_keeps_document_and_draft(self):
        original = copy.deepcopy(self.ext.document)
        self.ext._capture_look.return_value = {"bad": float("nan")}
        with self.assertRaises(ValueError):
            self.ext.UpdateLook()
        self.assertEqual(self.ext.document, original)
        self.assertIsNotNone(self.ext._look_edit)

    def test_changed_original_cannot_be_overwritten(self):
        self.ext.document["cues"][0]["name"] = "Externally changed"
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.ext.UpdateLook()
        self.ext._capture_look.assert_not_called()

    def test_removed_original_cannot_be_overwritten(self):
        self.ext.document["cues"].pop(0)
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.ext.SaveLookAsNew()

    def test_target_is_cue_id_not_selected_row(self):
        self.ext._p.return_value = 2
        other = copy.deepcopy(self.ext.document["cues"][1])
        self.ext.UpdateLook()
        self.assertEqual(self.ext.document["cues"][1], other)
        self.assertEqual(self.ext.document["cues"][0]["look"], self.look)

    def test_playback_and_document_mutations_reject_open_draft(self):
        for action in (self.ext.Go, self.ext.Resume, self.ext.Preload,
                       self.ext.ApplyCue, self.ext.CaptureLook, self.ext.SaveShow,
                       self.ext.LoadShow, self.ext.RecallLook, self.ext.AddCue):
            with self.subTest(action=action.__name__), self.assertRaisesRegex(ValueError, "Cancel Changes"):
                action()

    def test_running_or_paused_show_cannot_begin_editing(self):
        self.ext._look_edit = None
        for state in ("running", "paused"):
            self.ext.engine.state = state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "Stop All"):
                self.ext.RecallLook()

    def test_recall_rejects_nonvisual_and_missing_source(self):
        self.ext._look_edit = None
        self.ext.document["cues"][0]["kind"] = "audio"
        with self.assertRaisesRegex(ValueError, "Visual cue"):
            self.ext.RecallLook()
        self.ext.document["cues"][0]["kind"] = "visual"
        self.ext._media_path = Mock(side_effect=ValueError("Missing media"))
        with self.assertRaisesRegex(ValueError, "Missing media"):
            self.ext.RecallLook()
        self.ext.ownerComp.copy.assert_not_called()
        self.assertIsNone(self.ext._look_edit)

    def test_actions_without_draft_give_useful_error(self):
        self.ext._look_edit = None
        for action in (self.ext.UpdateLook, self.ext.SaveLookAsNew, self.ext.CancelLook):
            with self.subTest(action=action.__name__), self.assertRaises(ValueError):
                action()


if __name__ == "__main__":
    unittest.main()
