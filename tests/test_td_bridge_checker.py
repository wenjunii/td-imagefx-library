from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integrations" / "embody" / "check_td_bridge.py"
spec = importlib.util.spec_from_file_location("imagefx_bridge_checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def result(payload=None, text=None, error=False):
    return SimpleNamespace(
        is_error=error,
        structured_content=payload,
        content=[] if text is None else [SimpleNamespace(type="text", text=text)],
    )


class BridgeCheckerTests(unittest.TestCase):
    def test_mcp2_structured_result(self):
        self.assertEqual(checker._payload(result({"status": "online"})), {"status": "online"})

    def test_json_text_fallback(self):
        self.assertEqual(checker._payload(result(text='{"chunks": 3}')), {"chunks": 3})

    def test_failed_tool_result_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            checker._payload(result({"status": "online"}, "not connected", error=True))

    def test_failed_tool_without_content(self):
        with self.assertRaisesRegex(RuntimeError, "Unknown tool error"):
            checker._payload(result(error=True))

    def test_non_object_results_rejected(self):
        for invalid in (result([]), result(text="[]"), result(text="null")):
            with self.subTest(result=invalid), self.assertRaisesRegex(RuntimeError, "JSON object"):
                checker._payload(invalid)

    def test_missing_json_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "did not include JSON"):
            checker._payload(result())

    def test_missing_runtime_has_actionable_json_error(self):
        output = io.StringIO()
        with patch.dict("sys.modules", {"anyio": None}), contextlib.redirect_stdout(output):
            self.assertEqual(checker.main([]), 1)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ok"])
        self.assertIn("td-knowledge-mcp/.venv", report["error"])

    def test_live_report_requires_exact_root_and_boolean_diagnostics(self):
        path = "/project1/imagefx_demo"
        good = {"path": path, "hasErrors": False, "hasWarnings": False}
        self.assertEqual(checker._validated_error_report(good, path), good)
        for invalid in (
            {**good, "error": "unavailable"},
            {**good, "path": "/project1/other"},
            {**good, "hasErrors": "false"},
            {"path": path, "hasErrors": False},
        ):
            with self.subTest(report=invalid), self.assertRaises(RuntimeError):
                checker._validated_error_report(invalid, path)

    def test_local_catalog_includes_passive_health_tool(self):
        self.assertEqual(len(checker.LOCAL_TOOL_NAMES), 6)
        self.assertIn("get_td_server_health", checker.LOCAL_TOOL_NAMES)

    def test_checker_uses_modern_client_without_legacy_aliases(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("from mcp.client import Client", source)
        for legacy in ("ClientSession", "isError", "structuredContent", "serverInfo"):
            self.assertNotIn(legacy, source)
        self.assertIn("read_timeout_seconds=30", source)
        self.assertIn("anyio.fail_after", source)
        self.assertNotIn("send_ping", source)
        self.assertNotIn('call_tool("reload_td_knowledge"', source)
        self.assertNotIn('call_tool("execute_python"', source)

    def test_config_templates_use_isolated_bridge_environment(self):
        config = json.loads((ROOT / "integrations/embody/mcp-config.example.json").read_text())
        server = config["mcpServers"]["td-knowledge"]
        self.assertIn("td-knowledge-mcp\\.venv\\", server["command"])
        self.assertTrue(server["cwd"].endswith("td-knowledge-mcp"))
        text = (ROOT / ".codex/config.toml.example").read_text()
        self.assertIn("td-knowledge-mcp\\.venv\\", text)
        self.assertNotIn("td-ai-assistant\\venv", text)


if __name__ == "__main__":
    unittest.main()
