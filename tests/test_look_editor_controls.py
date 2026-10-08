"""Look Editor shortcuts must target only the active off-air draft."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from touchdesigner.scripts import look_editor_controls as controls
from touchdesigner.scripts.workflow import DEFAULT_ORDER, LABELS


class LookEditorControlTests(unittest.TestCase):
    def setUp(self):
        # Execute exactly the self-contained code embedded in the TOE.
        self.targets = controls.target_definitions(DEFAULT_ORDER, LABELS)
        self.runtime = {}
        exec(controls.runtime_source(self.targets), self.runtime)
        self.deck = Mock(path="/show/look_editor")
        self.module = Mock(path="/show/look_editor/calligraphic_shadow")
        self.module.customPages = ["Calligraphic Shadow", "Glitter"]
        self.module.currentPage = "Base"
        self.deck.op.return_value = self.module
        self.ext = SimpleNamespace(engine=SimpleNamespace(state="stopped"),
                                   _look_edit={"deck": self.deck})
        self.show = Mock(path="/show")
        self.show.ext.ShowControlExt = self.ext
        self.show.op.return_value = self.deck
        self.show.par.Lookmodule.eval.return_value = "calligraphic_shadow"

    def call(self, name, *args):
        return self.runtime[name](self.show, *args)

    def test_menu_contains_all_stages_and_slots(self):
        self.assertEqual(len(self.targets), 25)
        self.assertEqual([row[0] for row in self.targets[1:17]], list(DEFAULT_ORDER))
        self.assertEqual([row[2] for row in self.targets[1:17]], list(LABELS))
        self.assertEqual(self.targets[-1][1], "fx_rack/slot8")

    def test_every_menu_target_resolves_inside_draft(self):
        for name, path, _ in self.targets:
            with self.subTest(name=name):
                result = self.call("control_target", name)
                self.assertIs(result, self.deck if path == "." else self.module)
                if path != ".":
                    self.deck.op.assert_called_with(path)

    def test_selected_module_uses_parameter_value(self):
        self.assertIs(self.call("control_target"), self.module)
        self.deck.op.assert_called_once_with("calligraphic_shadow")

    def test_workflow_opens_draft_not_designer(self):
        self.assertIs(self.call("control_target", "workflow"), self.deck)
        self.deck.op.assert_not_called()
        self.show.parent.assert_not_called()

    def test_preview_uses_draft_output(self):
        self.assertIs(self.call("open_preview"), self.module)
        self.deck.op.assert_called_once_with("out1_image")
        self.module.openViewer.assert_called_once_with()

    def test_missing_preview_is_reported(self):
        self.deck.op.return_value = None
        with self.assertRaisesRegex(ValueError, "no output preview"):
            self.call("open_preview")

    def test_no_draft_never_falls_back_to_main(self):
        self.ext._look_edit = None
        for action in ("control_target", "open_preview"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "Recall Look"):
                self.call(action)
        self.show.parent.assert_not_called()

    def test_running_and_paused_are_rejected(self):
        for state in ("running", "paused"):
            self.ext.engine.state = state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "Stop All"):
                self.call("open_controls")

    def test_stale_draft_is_rejected(self):
        self.show.op.return_value = Mock()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.call("open_controls")

    def test_foreign_draft_is_rejected(self):
        self.deck.path = "/main/workflow"
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.call("open_controls")

    def test_missing_slot_is_reported(self):
        self.deck.op.return_value = None
        with self.assertRaisesRegex(ValueError, "empty"):
            self.call("control_target", "rack_slot_8")

    def test_unknown_and_traversal_selections_are_rejected(self):
        for selection in ("../../imagefx_demo", "", "unknown"):
            with self.subTest(selection=selection), self.assertRaisesRegex(ValueError, "menu"):
                self.call("control_target", selection)
        self.deck.op.assert_not_called()

    def test_foreign_module_is_rejected(self):
        self.module.path = "/show/look_editor_other/calligraphic_shadow"
        with self.assertRaisesRegex(ValueError, "only opens"):
            self.call("open_controls")

    def test_opens_custom_page_instead_of_empty_base(self):
        self.assertIs(self.call("open_controls"), self.module)
        self.assertEqual(self.module.currentPage, "Calligraphic Shadow")
        self.module.openParameters.assert_called_once_with()

    def test_remembers_selected_custom_page(self):
        self.module.currentPage = "Glitter"
        self.call("open_controls")
        self.assertEqual(self.module.currentPage, "Glitter")

    def test_components_without_custom_pages_still_open(self):
        self.module.customPages = []
        self.call("open_controls")
        self.module.openParameters.assert_called_once_with()

    def test_pulses_dispatch_and_report_target(self):
        for action in ("Editlookcontrols", "Openlookpreview"):
            with self.subTest(action=action):
                self.assertTrue(self.call("on_pulse", action))
                self.assertEqual(self.show.par.Lookcontrolstatus, "OFF-AIR: " + self.module.path)

    def test_pulse_errors_are_visible_without_reinitializing(self):
        self.ext._look_edit = None
        self.assertFalse(self.call("on_pulse", "Editlookcontrols"))
        self.assertIn("Recall Look", self.show.par.Lookcontrolstatus)
        self.show.initializeExtensions.assert_not_called()

    def test_unrelated_pulses_are_not_handled(self):
        self.assertFalse(self.call("on_pulse", "Gocue"))
        self.show.op.assert_not_called()


if __name__ == "__main__":
    unittest.main()
