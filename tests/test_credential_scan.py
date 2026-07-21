from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "check_credentials.py"
SPEC = importlib.util.spec_from_file_location("tdimagefx_credential_scan", MODULE_PATH)
CREDENTIAL_SCAN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CREDENTIAL_SCAN
SPEC.loader.exec_module(CREDENTIAL_SCAN)


class CredentialScanTests(unittest.TestCase):
    def test_safe_placeholders_and_examples_are_allowed(self) -> None:
        entries = (
            (".env.example", b"API_KEY=YOUR_API_KEY\n"),
            ("config.example.toml", b'auth_token = "PLACEHOLDER_TOKEN_VALUE"\n'),
            ("README.md", b"Never commit credentials or private keys.\n"),
        )
        self.assertEqual(CREDENTIAL_SCAN.scan_entries(entries), ())

    def test_high_confidence_credentials_are_reported_without_values(self) -> None:
        github_token = b"gh" + b"p_" + b"A" * 40
        private_key = b"-----BEGIN " + b"PRIVATE KEY-----"
        assignment = b"client_secret=" + b"Z" * 32
        entries = (("src/example.py", b"\n".join((github_token, private_key, assignment))),)
        findings = CREDENTIAL_SCAN.scan_entries(entries)
        self.assertEqual(
            {finding.rule for finding in findings},
            {"github-token", "private-key-material", "secret-assignment"},
        )
        rendered = "\n".join(
            "{}:{} [{}]".format(item.path, item.line, item.rule) for item in findings
        )
        for secret in (github_token, private_key, assignment):
            self.assertNotIn(secret.decode("ascii"), rendered)

    def test_machine_local_and_credential_filenames_are_rejected(self) -> None:
        entries = tuple(
            (path, b"placeholder")
            for path in (
                ".codex/config.toml",
                "integrations/embody/local/.embody/envoy.json",
                ".env.local",
                "deploy/client.pem",
                "config/credentials.json",
            )
        )
        findings = CREDENTIAL_SCAN.scan_entries(entries)
        self.assertEqual(len(findings), len(entries))
        self.assertEqual(
            {item.rule for item in findings},
            {"machine-local-config", "credential-filename"},
        )
