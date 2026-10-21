"""Portable coverage guards for the complete native control audit."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from touchdesigner.scripts import validate_live_suite as audit


class LiveSuiteTests(unittest.TestCase):
    def test_all_output_and_mapping_groups_are_included(self):
        names = [item[0] for item in audit.VALIDATORS]
        self.assertEqual(len(names), 27)
        self.assertEqual(len(set(names)), 27)
        self.assertTrue({"output_mode", "projector_review", "projection_mapping",
                         "projection_resets", "projection_polygon"} <= set(names))
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


if __name__ == "__main__":
    unittest.main()
