"""Portable guards for the real-frame audit report orchestration."""
import tempfile
import unittest
from pathlib import Path

from touchdesigner.scripts import validate_deferred_controls as audit


class DeferredControlAuditTests(unittest.TestCase):
    def test_all_nine_real_frame_groups_are_included(self):
        self.assertEqual(len(audit.JOBS), 9)
        self.assertEqual(len({job[3] for job in audit.JOBS}), 9)
        self.assertEqual({job[0] for job in audit.JOBS}, {
            "rack_events", "workflow_events", "wall_events", "layer_images",
            "layer_videos", "show_media", "look_media", "color_composition", "source_media"})

    def test_good_report_records_source_and_check_count(self):
        result = audit._summarize(audit.JOBS[0], {"ok": True, "checks": {"event": True}}, "abc")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_sha256"], "abc")
        self.assertEqual(result["check_count"], 1)

    def test_false_or_nonboolean_checks_cannot_be_hidden_by_ok(self):
        for value in (False, None, "true", 1):
            with self.subTest(value=value):
                result = audit._summarize(audit.JOBS[0], {"ok": True, "checks": {"event": value}}, "abc")
                self.assertFalse(result["ok"])
                self.assertEqual(result["failed_checks"], ["event"])

    def test_errors_and_failed_restoration_prevent_success(self):
        for field in ("error", "restoration_error"):
            result = audit._summarize(audit.JOBS[0], {"ok": True, "checks": {"event": True}, field: "failed"}, "abc")
            self.assertFalse(result["ok"])

    def test_missing_checks_or_nonobject_reports_are_rejected(self):
        for report in (None, [], {"ok": True}, {"ok": True, "checks": {}}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                audit._summarize(audit.JOBS[0], report, "abc")

    def test_report_signature_distinguishes_missing_stale_and_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            self.assertIsNone(audit._signature(path))
            path.write_text('{"ok": true}', encoding="utf-8")
            before = audit._signature(path)
            self.assertEqual(audit._signature(path), before)
            path.write_text('{"ok": false}', encoding="utf-8")
            self.assertNotEqual(audit._signature(path), before)


if __name__ == "__main__":
    unittest.main()
