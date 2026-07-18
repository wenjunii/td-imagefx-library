from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "embody"
SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_?key|token|password|passwd|secret|credential|"
    r"private_?key|authorization|bearer|cookie)(?:$|_)",
    re.IGNORECASE,
)


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


class EmbodyIntegrationTests(unittest.TestCase):
    def test_project_context_is_public_and_matches_imagefx_contract(self):
        context = json.loads(
            (INTEGRATION / "project-context.json").read_text(encoding="utf-8")
        )
        native = json.loads(
            (ROOT / "docs" / "native-validation.json").read_text(encoding="utf-8")
        )

        self.assertEqual(context["schema_version"], 1)
        self.assertEqual(context["project_id"], "td-imagefx-library")
        self.assertEqual(
            context["overview"]["validated_touchdesigner_build"],
            native["touchdesigner"]["build"],
        )
        self.assertEqual(context["overview"]["catalog"]["current_effect_ids"], 96)
        self.assertEqual(context["overview"]["catalog"]["immutable_package_versions"], 122)
        self.assertEqual(context["network"]["library"], "/project1/td_imagefx")
        self.assertEqual(
            context["outputs"]["primary_demo"],
            "/project1/imagefx_demo/out1_image",
        )
        self.assertFalse(
            [key for key in _walk_keys(context) if SECRET_KEY.search(key)]
        )

    def test_mcp_example_contains_only_portable_placeholders(self):
        path = INTEGRATION / "mcp-config.example.json"
        text = path.read_text(encoding="utf-8")
        config = json.loads(text)
        server = config["mcpServers"]["td-knowledge"]

        self.assertEqual(server["type"], "stdio")
        self.assertIn("--project-context", server["args"])
        self.assertIn("--faiss-db", server["args"])
        self.assertGreaterEqual(text.count("ABSOLUTE\\\\PATH\\\\TO"), 4)
        self.assertNotIn("wenju", text.lower())
        self.assertNotRegex(text.lower(), r"(api[_-]?key|password|bearer)")

    def test_validation_plan_covers_health_errors_pixels_and_performance(self):
        plan = json.loads(
            (INTEGRATION / "envoy-validation-plan.json").read_text(encoding="utf-8")
        )
        calls = [
            call
            for stage in plan["stages"]
            for call in stage.get("calls", [])
        ]
        tools = [call["tool"] for call in calls]
        captures = [
            call["arguments"]["op_path"]
            for call in calls
            if call["tool"] == "capture_top"
        ]

        self.assertEqual(plan["mode"], "read-only")
        self.assertIn("get_td_project_context", tools)
        self.assertIn("query_td_knowledge", tools)
        self.assertIn("exec_op_method", tools)
        self.assertIn("execute_python", tools)
        self.assertEqual(tools.count("get_op_errors"), 2)
        self.assertEqual(tools.count("get_project_performance"), 2)
        self.assertEqual(
            captures,
            [
                "/project1/imagefx_demo/out1_image",
                "/project1/imagefx_demo/particle_random_move/out1_particles",
                "/project1/imagefx_demo/fx_rack/out1_image",
                "/project1/td_imagefx/core/fx_browser/selected_preview",
            ],
        )

    def test_harness_scripts_preserve_the_canonical_project_boundary(self):
        installer = (
            ROOT / "touchdesigner" / "scripts" / "install_dev_harness.py"
        ).read_text(encoding="utf-8")
        validator = (
            ROOT / "touchdesigner" / "scripts" / "validate_live_project.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Refusing to install the QA harness", installer)
        self.assertIn("managed root already exists", installer)
        self.assertIn('library.op("core/fx_rack")', installer)
        self.assertIn('library.op("core/fx_browser")', installer)
        self.assertIn("_set_browser_target(browser, library)", installer)
        self.assertIn('parameter.val = ""', installer)
        self.assertIn('parameter.expr = "me.op(\'../../effects\')"', installer)
        self.assertIn("browser.cook(force=True)", installer)
        self.assertEqual(installer.count("_repair_effect_shader_paths("), 4)
        self.assertIn("ParticleRandomMove.tox", installer)
        self.assertEqual(installer.count("_sync_extension("), 6)
        self.assertIn('_sync_extension(browser, "ImageFXBrowserExt")', installer)
        self.assertIn('_sync_extension(updater, "UpdaterExt")', installer)
        self.assertIn('library.op("update_manager")', installer)
        self.assertNotIn("project.save(", installer)
        self.assertNotIn("_save_project_atomically", installer)
        self.assertIn('"errors"', validator)
        self.assertIn('"warnings"', validator)
        self.assertIn('"script_errors"', validator)
        self.assertIn("pixel_validation_required", validator)
        self.assertIn("EXPECTED_PACKAGES = 96", validator)
        self.assertIn("EXPECTED_VERSIONS = 122", validator)
        self.assertTrue(
            (ROOT / "docs" / "embody-envoy-integration.md").is_file()
        )
        self.assertLess(
            validator.index("outputs = [_output_diagnostics"),
            validator.index("roots = [_operator_diagnostics"),
        )
        self.assertLess(
            validator.index("for path in DIAGNOSTIC_COOKS"),
            validator.index("roots = [_operator_diagnostics"),
        )


if __name__ == "__main__":
    unittest.main()
