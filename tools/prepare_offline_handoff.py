"""Prepare a verified local ImageFX checkout ZIP without contacting a target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
for search_path in (ROOT, ROOT / "src"):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from tdimagefx.errors import SecurityError  # noqa: E402
from tdimagefx.paths import rename_directory_with_retry, validate_package_path  # noqa: E402
from tools.check_credentials import MAX_FILE_BYTES, scan_entries  # noqa: E402
from tools.task_cleanup import reject_links  # noqa: E402

MAIN_TOE = "TD_ImageFX_Library.toe"
NATIVE_RECORD = "docs/native-validation.json"
BUILDER = "touchdesigner/scripts/build_project.py"
PUBLIC_CONFIG = ".codex/config.toml.example"
LOCAL_PARTS = {".git", ".imagefx", ".codex", ".venv", ".embody", "build", "env", "venv", "__pycache__"}
PRIVATE_TYPES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".flac", ".aac",
                 ".onnx", ".safetensors", ".pt", ".pth", ".ckpt"}
GIT_ID = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})")
SHA256 = re.compile(r"[a-f0-9]{64}")


class HandoffError(ValueError):
    pass


def _git(root: Path, *args: str) -> bytes:
    # No remote operations; never echo Git stderr, which can contain paths or config.
    try:
        # Git archive applies checkout conversion. Use command-local LF defaults
        # and verify blobs afterward so neither conversion nor export attributes
        # can alter the data in a verified handoff.
        return subprocess.check_output(
            ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", *args],
            cwd=root, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise HandoffError(f"Local git {args[0]} failed") from exc


def _committed_files(root: Path, commit: str) -> dict[str, str]:
    files, folded = {}, set()
    for item in _git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        path = validate_package_path(name, label="handoff path")
        if any(character in name for character in '<>"|?*'):
            raise HandoffError(f"Windows-unsafe committed path: {name}")
        lower = name.casefold()
        if mode not in {"100644", "100755"} or kind != "blob" or not GIT_ID.fullmatch(blob):
            raise HandoffError(f"Non-regular committed entry: {name}")
        if lower in folded:
            raise HandoffError(f"Windows-equivalent duplicate path: {name}")
        if name != PUBLIC_CONFIG and (
            LOCAL_PARTS.intersection(part.casefold() for part in path.parts)
            or path.suffix.casefold() in PRIVATE_TYPES
        ):
            raise HandoffError(f"Machine-local file, media or model refused: {name}")
        folded.add(lower)
        files[name] = blob
    if any(ancestor.as_posix() in folded for name in folded for ancestor in PurePosixPath(name).parents):
        raise HandoffError("Windows-equivalent file and directory paths")
    for required in (MAIN_TOE, NATIVE_RECORD, BUILDER, "README.md"):
        if required not in files:
            raise HandoffError(f"Committed handoff is missing {required}")
    return files


def _archive_inventory(archive: zipfile.ZipFile, prefix: str, expected: dict[str, str]):
    entries = {}
    for entry in archive.infolist():
        if not entry.filename.startswith(prefix):
            raise HandoffError("ZIP entry escapes the single project directory")
        name = entry.filename[len(prefix):]
        if entry.is_dir():
            if name:
                validate_package_path(name.rstrip("/"), label="ZIP directory")
            continue
        validate_package_path(name, label="ZIP file")
        if name in entries or stat.S_ISLNK(entry.external_attr >> 16):
            raise HandoffError(f"Duplicate or linked ZIP entry: {name}")
        if entry.file_size > MAX_FILE_BYTES:
            raise HandoffError(f"File exceeds the credential-scan limit: {name}")
        entries[name] = entry
    if entries.keys() != expected.keys():
        raise HandoffError("ZIP inventory does not match the committed tree")
    return entries


def _verify_archive(path: Path, prefix: str, expected: dict[str, str]) -> tuple[dict, int]:
    digests, sizes, record = {}, {}, None
    with zipfile.ZipFile(path) as archive:
        for name, entry in _archive_inventory(archive, prefix, expected).items():
            data = archive.read(entry)
            git_hash = hashlib.sha1(usedforsecurity=False) if len(expected[name]) == 40 else hashlib.sha256()
            git_hash.update(f"blob {len(data)}\0".encode("ascii"))
            git_hash.update(data)
            if git_hash.hexdigest() != expected[name]:
                raise HandoffError(f"ZIP data is not the committed blob: {name}")
            findings = scan_entries(((name, data),))
            if findings:
                finding = findings[0]
                raise HandoffError(f"Credential finding: {finding.path}:{finding.line} ({finding.rule})")
            digests[name], sizes[name] = hashlib.sha256(data).hexdigest(), len(data)
            if name == NATIVE_RECORD:
                try:
                    record = json.loads(data)
                except ValueError as exc:
                    raise HandoffError("Native build record is not valid JSON") from exc

    def require_hash(name, digest):
        if not isinstance(digest, str) or not SHA256.fullmatch(digest) or digests.get(name) != digest:
            raise HandoffError(f"Recorded native hash mismatch: {name}")

    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise HandoffError("Invalid native build record")
    results = record.get("results")
    if not isinstance(results, dict) or any(results.get(k) != 0 for k in
                                           ("builder_errors", "shader_errors", "preview_errors")):
        raise HandoffError("Native build did not record zero errors")
    artifacts, recorded = record.get("artifacts"), set()
    if not isinstance(artifacts, list):
        raise HandoffError("Missing native artifact list")
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or item["path"] in recorded:
            raise HandoffError("Invalid or duplicate native artifact")
        name = item["path"]
        require_hash(name, item.get("sha256"))
        if type(item.get("bytes")) is not int or item["bytes"] != sizes[name]:
            raise HandoffError(f"Recorded native file size mismatch: {name}")
        recorded.add(name)
    native = {name for name in expected if name.endswith(".tox") and
              name.startswith(("touchdesigner/core/", "packages/"))}
    if recorded != native | {MAIN_TOE} or not native:
        raise HandoffError("Native build record does not cover all shipped TOE/TOX files")
    builder = record.get("builder")
    if not isinstance(builder, dict) or builder.get("path") != BUILDER:
        raise HandoffError("Missing native builder binding")
    require_hash(BUILDER, builder.get("sha256"))
    for group in ("show_sources", "module_sources"):
        sources = record.get(group)
        if not isinstance(sources, dict) or not sources:
            raise HandoffError(f"Missing native source bindings: {group}")
        for name, digest in sources.items():
            require_hash(name, digest)
    return {"main_toe_sha256": digests[MAIN_TOE], "tracked_files": len(expected)}, len(recorded)


def _instructions(archive: str, commit: str) -> str:
    return (
        f"Prepared locally from commit {commit}. Nothing was transferred.\n\n"
        "When ready, stop playback on the destination and keep its working checkout,\n"
        "show JSON, media, output mapping, motion workers and machine settings intact.\n"
        f"Transfer {archive} and SHA256.txt, then compare SHA-256 before extraction.\n"
        "On Windows, use Get-FileHash -Algorithm SHA256 with the transferred ZIP.\n"
        "Extract to a separate folder and keep the entire checkout together.\n"
        "Open TD_ImageFX_Library.toe with both blackouts on, audio off and all\n"
        "physical outputs closed. Load a target-local show without resaving it,\n"
        "then test Pre-Show Check and Rehearsal Log off-air. Verify the actual\n"
        "projectors, audio and any live workers separately before switching over.\n"
        "If verification fails, close the new session and reopen the old checkout.\n"
        "See docs/offline-handoff.md in checkouts that include the handoff tooling.\n"
    )


def prepare_handoff(root: Path, revision: str, target: str) -> Path:
    """Publish a local, complete handoff directory or leave none on failure."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", target):
        raise HandoffError("Target must be a short lowercase label, e.g. 5090")
    validate_package_path(target, label="target")
    root = root.resolve(strict=True)
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode("ascii").strip()
    if not GIT_ID.fullmatch(commit):
        raise HandoffError("Git did not return a single committed revision")
    expected = _committed_files(root, commit)
    short = commit[:12]
    parent = root / "build" / "handoffs" / target
    output = parent / short
    reject_links(root, output)
    if os.path.lexists(output):
        raise HandoffError(f"Handoff already exists: {output}")
    try:
        _git(root, "check-ignore", "--quiet", "--no-index", "--", output.relative_to(root).as_posix())
    except HandoffError as exc:
        raise HandoffError("Handoff destination must be Git-ignored") from exc
    parent.mkdir(parents=True, exist_ok=True)
    reject_links(root, parent)
    if not parent.resolve(strict=True).is_relative_to(root / "build"):
        raise HandoffError("Handoff output escapes the build directory")
    label = f"ImageFX-{target}-{short}.zip"
    prefix = f"td-imagefx-library-{short}/"
    with tempfile.TemporaryDirectory(prefix=".handoff-", dir=parent) as temp:
        stage = Path(temp) / "ready"
        stage.mkdir()
        archive = stage / label
        _git(root, "archive", "--format=zip", "--prefix=" + prefix, "--output=" + str(archive), commit)
        facts, native_count = _verify_archive(archive, prefix, expected)
        with archive.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        report = dict(status="prepared_local_only", source_commit=commit, target=target, archive=label,
                      archive_sha256=checksum, archive_bytes=archive.stat().st_size,
                      native_artifacts_verified=native_count, target_runtime_validated=False, **facts)
        (stage / "SHA256.txt").write_text(f"{checksum} *{label}\n", encoding="utf-8")
        (stage / "INSTALL.txt").write_text(_instructions(label, commit), encoding="utf-8")
        (stage / "handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        reject_links(root, output)
        rename_directory_with_retry(stage, output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="Local Git commit or ref to pin")
    parser.add_argument("--target", required=True, help="Short label, e.g. 5090 (not a network address)")
    args = parser.parse_args(argv)
    try:
        output = prepare_handoff(ROOT, args.revision, args.target)
    except (ValueError, OSError, SecurityError, zipfile.BadZipFile) as exc:
        print(f"Handoff not prepared: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared locally: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
