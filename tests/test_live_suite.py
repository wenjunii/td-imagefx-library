"""Portable coverage guards for the complete native control audit."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from touchdesigner.scripts import validate_live_suite as audit


class LiveSuiteTests(unittest.TestCase):
    def safe_session(self):
        show = Mock(par=SimpleNamespace(Audioenabled=False, Masterblackout=True))
        show.ext.ShowControlExt = SimpleNamespace(
            engine=SimpleNamespace(state="stopped"), _look_edit=None)
        show.fetch.return_value = None
        runtime = Mock()
        runtime.module.windows.return_value = [None, SimpleNamespace(isOpen=False)]
        show.op.return_value = runtime
        wall = SimpleNamespace(par=SimpleNamespace(Blackout=True))
        demo = Mock()
        demo.op.side_effect = {"show_control": show, "wall_output": wall}.get
        demo.fetch.return_value = False
        return demo, show, wall, runtime

    def test_disarmed_stopped_session_passes_preflight(self):
        demo, show, wall, runtime = self.safe_session()
        audit._require_safe_session(demo)
        show.initializeExtensions.assert_not_called()
        show.UpdateMapping.assert_not_called()

    def test_missing_show_or_output_runtime_fails_before_changes(self):
        with self.assertRaisesRegex(RuntimeError, "demo is missing"):
            audit._require_safe_session(None)
        demo, show, wall, runtime = self.safe_session()
        demo.op.side_effect = {"show_control": show}.get
        with self.assertRaisesRegex(RuntimeError, "Build Show Control"):
            audit._require_safe_session(demo)
        demo, show, wall, runtime = self.safe_session()
        show.op.return_value = None
        with self.assertRaisesRegex(RuntimeError, "Install Output Mode"):
            audit._require_safe_session(demo)

    def test_playing_paused_or_unsaved_draft_rejects_audit(self):
        for state, draft in (("running", None), ("paused", None), ("stopped", {})):
            with self.subTest(state=state, draft=draft):
                demo, show, wall, runtime = self.safe_session()
                show.ext.ShowControlExt.engine.state = state
                show.ext.ShowControlExt._look_edit = draft
                with self.assertRaisesRegex(RuntimeError, "Stop All"):
                    audit._require_safe_session(demo)

    def test_armed_audio_or_released_blackout_rejects_audit(self):
        for owner, name, value in (("show", "Audioenabled", True),
                                   ("show", "Masterblackout", False),
                                   ("wall", "Blackout", False)):
            with self.subTest(parameter=name):
                demo, show, wall, runtime = self.safe_session()
                setattr((show if owner == "show" else wall).par, name, value)
                with self.assertRaisesRegex(RuntimeError, "Disarm audio"):
                    audit._require_safe_session(demo)

    def test_open_physical_window_rejects_audit_without_closing_it(self):
        demo, show, wall, runtime = self.safe_session()
        window = Mock(isOpen=True)
        runtime.module.windows.return_value = [None, window]
        with self.assertRaisesRegex(RuntimeError, "Close all physical"):
            audit._require_safe_session(demo)
        window.par.winclose.pulse.assert_not_called()

    def test_active_export_rejects_audit_without_cancelling_it(self):
        demo, show, wall, runtime = self.safe_session()
        show.fetch.return_value = {"stage": "recording"}
        with self.assertRaisesRegex(RuntimeError, "Finish/cancel"):
            audit._require_safe_session(demo)
        show.unstore.assert_not_called()

    def test_overlapping_deferred_audit_is_rejected(self):
        demo, show, wall, runtime = self.safe_session()
        demo.fetch.return_value = True
        with self.assertRaisesRegex(RuntimeError, "deferred control audit"):
            audit._require_safe_session(demo)

    def test_all_output_and_mapping_groups_are_included(self):
        names = [item[0] for item in audit.VALIDATORS]
        self.assertEqual(len(names), 29)
        self.assertEqual(len(set(names)), 29)
        self.assertTrue({"output_mode", "projector_review", "projection_mapping",
                         "projection_resets", "projection_polygon", "show_navigation"} <= set(names))
        self.assertIn(("projection_resets", "validate_projection_mapping.py", "validate_resets"),
                      audit.VALIDATORS)

    def test_named_entry_point_records_coverage_and_does_not_run_default(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, "SCRIPT_ROOT", Path(folder)):
            (Path(folder) / "fixture.py").write_text(
                "def validate(write_report=True):\n    raise AssertionError('wrong entry point')\n"
                "def validate_resets(write_report=True):\n"
                "    return {'ok': True, 'checks': {'all_resets': write_report}}\n", encoding="utf-8")
            result = audit._run_validator("resets", "fixture.py", "validate_resets")
            self.assertTrue(result["ok"])
            self.assertEqual(result["entry_point"], "validate_resets")
            self.assertEqual(result["check_count"], 1)

    def test_missing_named_entry_point_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, "SCRIPT_ROOT", Path(folder)):
            (Path(folder) / "fixture.py").write_text("validate_resets = None\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, r"does not expose validate_resets\(\)"):
                audit._run_validator("resets", "fixture.py", "validate_resets")

    def test_nonboolean_or_empty_checks_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audit, "SCRIPT_ROOT", Path(folder)):
            for checks in ({}, {"event": 1}, {"event": None}, {"event": "true"}):
                with self.subTest(checks=checks):
                    (Path(folder) / "fixture.py").write_text(
                        "def validate(write_report=True):\n    return " + repr({"ok": True, "checks": checks}) + "\n",
                        encoding="utf-8")
                    self.assertFalse(audit._run_validator("fixture", "fixture.py")["ok"])


if __name__ == "__main__":
    unittest.main()
