"""Scan tracked or staged repository files for high-confidence credentials.

Only rule names and file locations are printed. Suspected values are never
included in output, keeping CI logs safe while a finding is investigated.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 16 * 1024 * 1024
PLACEHOLDER_MARKERS = (
    b"ABSOLUTE",
    b"CHANGEME",
    b"DUMMY",
    b"EXAMPLE",
    b"FAKE",
    b"PLACEHOLDER",
    b"REDACTED",
    b"YOUR_",
)
SENSITIVE_BASENAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
SENSITIVE_SUFFIXES = {
    ".jks",
    ".kdbx",
    ".key",
    ".keystore",
    ".ovpn",
    ".p12",
    ".pem",
    ".pfx",
}
SENSITIVE_PROJECT_PATHS = {
    ".codex/config.toml",
    "integrations/embody/local/.embody/envoy.json",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


CONTENT_RULES = (
    (
        "private-key-material",
        re.compile(br"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    ("github-token", re.compile(br"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github-fine-grained-token", re.compile(br"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws-access-key", re.compile(br"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "openai-api-key",
        re.compile(br"\bsk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    ("google-api-key", re.compile(br"\bAIza[A-Za-z0-9_-]{30,}\b")),
    ("slack-token", re.compile(br"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("stripe-live-key", re.compile(br"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
)
ASSIGNMENT_RULE = re.compile(
    br"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    br"password|private[_-]?key)\s*[=:]\s*[\"']?([A-Za-z0-9_./+=-]{16,})"
)


def _git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        stderr=subprocess.DEVNULL,
    )


def _paths_from_nul(payload: bytes) -> tuple[str, ...]:
    return tuple(
        item.decode("utf-8", errors="strict")
        for item in payload.split(b"\0")
        if item
    )


def _tracked_entries() -> tuple[tuple[str, bytes], ...]:
    paths = _paths_from_nul(_git_bytes("ls-files", "-z"))
    entries = []
    for path in paths:
        source = ROOT.joinpath(*PurePosixPath(path).parts)
        if not source.is_file():
            continue
        size = source.stat().st_size
        if size > MAX_FILE_BYTES:
            raise RuntimeError("tracked file exceeds credential-scan limit: {}".format(path))
        entries.append((path, source.read_bytes()))
    return tuple(entries)


def _staged_entries() -> tuple[tuple[str, bytes], ...]:
    paths = _paths_from_nul(
        _git_bytes("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    )
    entries = []
    for path in paths:
        payload = _git_bytes("show", ":{}".format(path))
        if len(payload) > MAX_FILE_BYTES:
            raise RuntimeError("staged file exceeds credential-scan limit: {}".format(path))
        entries.append((path, payload))
    return tuple(entries)


def _path_finding(path: str) -> Finding | None:
    normalized = PurePosixPath(path.replace("\\", "/"))
    lowered = normalized.as_posix().casefold()
    basename = normalized.name.casefold()
    suffix = normalized.suffix.casefold()
    if lowered in SENSITIVE_PROJECT_PATHS:
        return Finding(path, 1, "machine-local-config")
    if basename in SENSITIVE_BASENAMES or basename.startswith(".env."):
        if basename == ".env.example":
            return None
        return Finding(path, 1, "credential-filename")
    if suffix in SENSITIVE_SUFFIXES:
        return Finding(path, 1, "credential-filename")
    if (
        ("credential" in basename or "secret" in basename)
        and suffix in {".json", ".toml", ".yaml", ".yml"}
    ):
        return Finding(path, 1, "credential-filename")
    return None


def _line_number(payload: bytes, offset: int) -> int:
    return payload.count(b"\n", 0, offset) + 1


def scan_entries(entries: tuple[tuple[str, bytes], ...]) -> tuple[Finding, ...]:
    findings = []
    for path, payload in entries:
        path_finding = _path_finding(path)
        if path_finding is not None:
            findings.append(path_finding)
        for rule, pattern in CONTENT_RULES:
            for match in pattern.finditer(payload):
                findings.append(Finding(path, _line_number(payload, match.start()), rule))
        for match in ASSIGNMENT_RULE.finditer(payload):
            value = match.group(1).upper()
            if any(marker in value for marker in PLACEHOLDER_MARKERS):
                continue
            findings.append(
                Finding(path, _line_number(payload, match.start()), "secret-assignment")
            )
    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="scan only added or modified files currently staged in Git",
    )
    args = parser.parse_args()
    try:
        entries = _staged_entries() if args.staged else _tracked_entries()
        findings = scan_entries(entries)
    except (OSError, RuntimeError, subprocess.CalledProcessError, UnicodeError) as exc:
        print("Credential scan could not complete: {}".format(exc))
        return 2
    if findings:
        print("Credential scan failed; suspected values are redacted:")
        for finding in findings:
            print("- {}:{} [{}]".format(finding.path, finding.line, finding.rule))
        return 1
    scope = "staged" if args.staged else "tracked"
    print("Credential scan passed: {} {} files checked".format(len(entries), scope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
