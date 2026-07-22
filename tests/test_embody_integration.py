from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


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


def _load_harness_installer():
    path = ROOT / "touchdesigner" / "scripts" / "install_dev_harness.py"
    spec = importlib.util.spec_from_file_location("imagefx_dev_harness_installer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the development harness installer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.assertEqual(context["overview"]["catalog"]["immutable_package_versions"], 124)
        self.assertEqual(context["network"]["library"], "/project1/td_imagefx")
        self.assertEqual(
            context["network"]["identity_operators"],
            ["/project1/td_imagefx", "/project1/imagefx_demo"],
        )
        self.assertEqual(
            context["outputs"]["primary_demo"],
            "/project1/imagefx_demo/out1_image",
        )
        self.assertEqual(
            context["network"]["color_adjustment"],
            "/project1/td_imagefx/core/color_adjustment",
        )
        self.assertEqual(
            context["outputs"]["color_adjustment"],
            "/project1/imagefx_demo/color_adjustment/out1_color_adjustment",
        )
        self.assertEqual(
            context["network"]["motion_studio"],
            "/project1/td_imagefx/core/motion_studio",
        )
        self.assertEqual(
            context["outputs"]["motion"],
            "/project1/imagefx_demo/motion_studio/out1_motion",
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
        self.assertIn("--envoy-config", server["args"])
        self.assertIn("--faiss-db", server["args"])
        self.assertGreaterEqual(text.count("ABSOLUTE\\\\PATH\\\\TO"), 4)
        self.assertNotIn("wenju", text.lower())
        self.assertNotRegex(text.lower(), r"(api[_-]?key|password|bearer)")

        codex_path = ROOT / ".codex" / "config.toml.example"
        codex_text = codex_path.read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.td-knowledge]", codex_text)
        self.assertIn("--project-context", codex_text)
        self.assertIn("--envoy-config", codex_text)
        self.assertIn("--faiss-db", codex_text)
        self.assertGreaterEqual(codex_text.count("ABSOLUTE"), 4)
        self.assertNotIn("wenju", codex_text.lower())
        self.assertNotRegex(
            codex_text.lower(),
            r"(api[_-]?key|password|bearer|credential)",
        )

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
        python_calls = [
            call["arguments"]["code"]
            for call in calls
            if call["tool"] == "execute_python"
        ]

        self.assertEqual(plan["mode"], "read-only")
        self.assertIn("get_td_project_context", tools)
        self.assertIn("query_td_knowledge", tools)
        self.assertIn("exec_op_method", tools)
        self.assertIn("execute_python", tools)
        self.assertEqual(len(python_calls), 1)
        self.assertIn("namespace = dict(globals())", python_calls[0])
        self.assertEqual(tools.count("get_op_errors"), 2)
        self.assertEqual(tools.count("get_project_performance"), 2)
        self.assertEqual(
            captures,
            [
                "/project1/imagefx_demo/out1_image",
                "/project1/imagefx_demo/ink_flow/out1_ink_flow",
                "/project1/imagefx_demo/particle_random_move/out1_particles",
                "/project1/imagefx_demo/glitch_fusion/out1_glitch",
                "/project1/imagefx_demo/color_adjustment/out1_color_adjustment",
                "/project1/imagefx_demo/motion_studio/out1_motion",
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
        live_suite_validator = (
            ROOT / "touchdesigner" / "scripts" / "validate_live_suite.py"
        ).read_text(encoding="utf-8")
        output_validator = (
            ROOT / "touchdesigner" / "scripts" / "validate_output_resolution.py"
        ).read_text(encoding="utf-8")
        rack_validator = (
            ROOT / "touchdesigner" / "scripts" / "validate_rack_selection.py"
        ).read_text(encoding="utf-8")
        all_effect_validator = (
            ROOT
            / "touchdesigner"
            / "scripts"
            / "validate_all_effect_parameters.py"
        ).read_text(encoding="utf-8")
        bridge_checker = (
            ROOT / "integrations" / "embody" / "check_td_bridge.py"
        ).read_text(encoding="utf-8")
        browser_start_callbacks = (
            ROOT
            / "touchdesigner"
            / "callbacks"
            / "browser_start_callbacks.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Refusing to install the QA harness", installer)
        self.assertIn("managed root already exists", installer)
        self.assertIn('library.op("core/fx_rack")', installer)
        self.assertIn('library.op("core/fx_browser")', installer)
        self.assertIn("_set_browser_target(browser, library)", installer)
        self.assertIn('parameter.val = ""', installer)
        self.assertIn('parameter.expr = "me.op(\'../../effects\')"', installer)
        self.assertIn("browser.cook(force=True)", installer)
        self.assertEqual(installer.count("_repair_effect_shader_paths("), 8)
        self.assertIn("ParticleRandomMove.tox", installer)
        self.assertIn("InkFlowFusion.tox", installer)
        self.assertIn("GlitchFusion.tox", installer)
        self.assertIn("ColorAdjustment.tox", installer)
        self.assertIn("MotionStudio.tox", installer)
        self.assertIn("HD 1920 x 1080", installer)
        self.assertIn("4K UHD 3840 x 2160", installer)
        self.assertIn("Customwidth", installer)
        self.assertIn("Customheight", installer)
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
        self.assertIn("EXPECTED_VERSIONS = 124", validator)
        self.assertIn("EXPECTED_RESOLUTION_PRESETS", validator)
        self.assertIn("rack_selection", validator)
        self.assertIn("selection_matches_loaded_package", validator)
        self.assertIn("browser_startup", validator)
        self.assertIn("reloads_selected_preview", validator)
        for script_name in (
            "validate_live_project.py",
            "validate_output_resolution.py",
            "validate_rack_selection.py",
            "validate_ink_flow_module.py",
            "validate_particle_module.py",
            "validate_glitch_fusion_module.py",
            "validate_color_adjustment_module.py",
            "validate_motion_studio_module.py",
            "validate_all_effect_parameters.py",
        ):
            self.assertIn(script_name, live_suite_validator)
        self.assertIn("scope = dict(globals())", live_suite_validator)
        self.assertIn('"__file__": str(script_path)', live_suite_validator)
        self.assertIn("validator(write_report=True)", live_suite_validator)
        self.assertIn("live-suite.json", live_suite_validator)
        self.assertNotIn("project.save(", live_suite_validator)
        self.assertIn("EXPECTED_PRESETS", output_validator)
        self.assertIn("3840", output_validator)
        self.assertIn("2160", output_validator)
        self.assertIn("1234", output_validator)
        self.assertIn("678", output_validator)
        self.assertIn("SLOT_COUNT = 8", rack_validator)
        self.assertIn("ExportPreset", rack_validator)
        self.assertIn("ImportPreset", rack_validator)
        self.assertIn("finally:", rack_validator)
        self.assertNotIn("project.save(", rack_validator)
        self.assertIn("contains_exactly_96_latest_packages", all_effect_validator)
        self.assertIn("every_numeric_control_responds", all_effect_validator)
        self.assertIn("every_toggle_responds", all_effect_validator)
        self.assertIn("ExportPreset", all_effect_validator)
        self.assertIn("ImportPreset", all_effect_validator)
        self.assertIn("finally:", all_effect_validator)
        self.assertNotIn("project.save(", all_effect_validator)
        self.assertIn(
            'EXPECTED_PROJECT_ID = "td-imagefx-library"',
            bridge_checker,
        )
        self.assertIn("get_knowledge_stats", bridge_checker)
        self.assertIn("get_project_performance", bridge_checker)
        self.assertIn("--require-envoy", bridge_checker)
        self.assertIn("--envoy-config", bridge_checker)
        self.assertIn("--verbose", bridge_checker)
        self.assertIn("def _validated_error_report", bridge_checker)
        self.assertIn("Live error report did not confirm", bridge_checker)
        self.assertIn("subprocess.DEVNULL", bridge_checker)
        self.assertIn("def onStart():", browser_start_callbacks)
        self.assertIn("def onCreate():", browser_start_callbacks)
        self.assertIn("UpdateSelection()", browser_start_callbacks)
        self.assertIn("delayFrames=1", browser_start_callbacks)
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

    def test_harness_installer_requires_the_exact_unnumbered_project(self):
        installer = _load_harness_installer()
        expected = installer.EXPECTED_HARNESS_PROJECT.resolve()
        canonical = installer.CANONICAL_PROJECT.resolve()
        numbered = expected.with_name(expected.stem + ".2.toe")

        self.assertEqual(
            installer._project_path(expected.parent, expected.stem),
            expected,
        )

        installer.project = SimpleNamespace(
            folder=str(expected.parent),
            name=expected.name,
        )
        self.assertEqual(installer._validate_harness_project(), expected)

        installer.project = SimpleNamespace(
            folder=str(numbered.parent),
            name=numbered.name,
        )
        with self.assertRaisesRegex(RuntimeError, "numbered harness identity"):
            installer._validate_harness_project()

        installer.project = SimpleNamespace(
            folder=str(canonical.parent),
            name=canonical.name,
        )
        with self.assertRaisesRegex(RuntimeError, "Refusing to install"):
            installer._validate_harness_project()


if __name__ == "__main__":
    unittest.main()
