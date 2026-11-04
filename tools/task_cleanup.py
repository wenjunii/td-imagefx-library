"""Record and recycle known disposable task artifacts; never scan for old files.

The dedicated build/task-artifacts/<task>/ area is not for show assets. Recording
an item is a declaration that this task created it, not dependency discovery.
Check dependencies and finish verification before clean --apply --verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
KINDS = {"scratch", "installer", "partial_download", "task_copy", "cache"}
RESERVED = {"cleanup.json", "cleanup-report.json"}
PROTECTED = {"models", "weights", "assets", "shows", "backups", "backup", ".imagefx",
             ".git", ".venv", "venv", "env", "puppet-cuda-venv", "puppet-live-venv", "puppet-venv"}
MODEL_SUFFIXES = {".onnx", ".safetensors", ".ckpt", ".pt", ".pth", ".task"}
ENTRY_FIELDS = {"path", "kind", "reason", "sha256", "bytes", "files"}
RECYCLE_COMMAND = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName Microsoft.VisualBasic
$p = [Environment]::GetEnvironmentVariable('IMAGEFX_CLEANUP_TARGET')
$item = Get-Item -LiteralPath $p -Force
if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked target refused' }
if ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($p)).DriveType -ne [IO.DriveType]::Fixed) {
    throw 'Only a local fixed drive is supported for Recycle Bin cleanup'
}
if ($item.PSIsContainer) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
        [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException)
} else {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
        [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException)
}
"""


class CleanupError(ValueError):
    pass


def task_folder(root: Path, task: str) -> Path:
    if not isinstance(task, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", task):
        raise CleanupError("Task name must be a short lowercase slug")
    folder = root / "build" / "task-artifacts" / task
    reject_links(root, folder)
    return folder


def reject_links(root: Path, path: Path) -> None:
    """Check every existing ancestor, including Windows junction/reparse points."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CleanupError("Target is outside the project") from exc
    current = root
    for part in (None, *relative.parts):
        if part is not None:
            current /= part
        if not current.exists() and not current.is_symlink():
            continue
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise CleanupError("Symlink/junction/reparse point refused: " + str(current))


def target_path(root: Path, task: str, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CleanupError("Use an explicit project-relative path with forward slashes")
    parts = value.split("/")
    if (PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
            or any(part in {"", ".", ".."} or ":" in part or part[-1:] in {".", " "} for part in parts)):
        raise CleanupError("Absolute, aliased or traversal paths are not allowed")
    folder = task_folder(root, task)
    prefix = folder.relative_to(root).parts
    if tuple(parts[:len(prefix)]) != prefix or len(parts) <= len(prefix):
        raise CleanupError("Target must be inside this task's dedicated artifact folder")
    if parts[len(prefix)].casefold() in RESERVED:
        raise CleanupError("Cleanup metadata cannot be a target")
    if any(part.casefold() in PROTECTED for part in parts[len(prefix):]):
        raise CleanupError("Runtime/assets/models/backups/environments are protected")
    path = root.joinpath(*parts)
    reject_links(root, path)
    return path


def fingerprint(root: Path, path: Path) -> dict:
    reject_links(root, path)
    if not path.exists():
        raise CleanupError("Artifact is missing: " + str(path))
    digest, size, count = hashlib.sha256(), 0, 0

    def visit(item: Path) -> None:
        nonlocal size, count
        reject_links(root, item)
        info = item.lstat()
        name = item.relative_to(path).as_posix() if item != path else "."
        if item.name.casefold() in PROTECTED or item.suffix.casefold() in MODEL_SUFFIXES:
            raise CleanupError("Protected asset/environment/model found: " + str(item))
        if stat.S_ISDIR(info.st_mode):
            digest.update(json.dumps(["directory", name]).encode())
            for child in sorted(item.iterdir(), key=lambda p: p.name):
                visit(child)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink > 1:
                raise CleanupError("Hard-linked file refused: " + str(item))
            content = hashlib.sha256()
            with item.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    content.update(block)
            digest.update(json.dumps(["file", name, info.st_size, content.hexdigest()]).encode())
            size += info.st_size
            count += 1
        else:
            raise CleanupError("Special file refused: " + str(item))

    visit(path)
    return {"sha256": digest.hexdigest(), "bytes": size, "files": count}


def git_guard(root: Path, path: Path) -> None:
    relative = path.relative_to(root).as_posix()
    result = subprocess.run(["git", "ls-files", "-z", "--", ":(literal)" + relative], cwd=root,
                            capture_output=True, check=True)
    if result.stdout:
        raise CleanupError("Tracked content cannot be cleaned")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", relative], cwd=root, capture_output=True)
    if ignored.returncode != 0:
        raise CleanupError("Target must be Git-ignored")


def metadata_path(root: Path, task: str, name: str) -> Path:
    path = task_folder(root, task) / name
    reject_links(root, path)
    if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        raise CleanupError("Cleanup metadata must be an ordinary unlinked file")
    git_guard(root, path)
    return path


def read_manifest(root: Path, task: str) -> dict:
    path = metadata_path(root, task, "cleanup.json")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise CleanupError("Cleanup manifest is too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"schema_version", "task", "entries"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["task"] != task
            or not isinstance(data["entries"], list) or not 1 <= len(data["entries"]) <= 1000):
        raise CleanupError("Invalid cleanup manifest")
    paths = []
    for entry in data["entries"]:
        if (not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS
                or not isinstance(entry["kind"], str) or entry["kind"] not in KINDS
                or not isinstance(entry["reason"], str) or not entry["reason"].strip()
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                or any(type(entry[key]) is not int or entry[key] < 0 for key in ("bytes", "files"))):
            raise CleanupError("Invalid cleanup entry")
        path = target_path(root, task, entry["path"])
        if any(path == old or path in old.parents or old in path.parents for old in paths):
            raise CleanupError("Duplicate or overlapping cleanup targets")
        paths.append(path)
    return data


def record(root: Path, task: str, paths: list[str], kind: str, reason: str) -> dict:
    if kind not in KINDS or not reason.strip() or len(reason) > 500:
        raise CleanupError("A supported kind and concise purpose are required")
    folder = task_folder(root, task)
    if (folder / "cleanup-report.json").exists():
        raise CleanupError("Task has already been cleaned; use a new task name")
    manifest = metadata_path(root, task, "cleanup.json")
    data = read_manifest(root, task) if manifest.exists() else {"schema_version": 1, "task": task, "entries": []}
    data = json.loads(json.dumps(data))
    previous = [target_path(root, task, entry["path"]) for entry in data["entries"]]
    for value in paths:
        path = target_path(root, task, value)
        if any(path == old or path in old.parents or old in path.parents for old in previous):
            raise CleanupError("Duplicate or overlapping cleanup targets")
        git_guard(root, path)
        data["entries"].append(dict(path=value, kind=kind, reason=reason, **fingerprint(root, path)))
        previous.append(path)
    if not paths or len(data["entries"]) > 1000:
        raise CleanupError("Record between 1 and 1000 artifacts")
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def recycle(path: Path) -> None:
    if sys.platform != "win32":
        raise CleanupError("Apply requires the Windows Recycle Bin; no permanent-delete fallback")
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        raise CleanupError("PowerShell is unavailable; files are retained")
    env = dict(os.environ, IMAGEFX_CLEANUP_TARGET=str(path))
    subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", RECYCLE_COMMAND],
                   env=env, check=True, capture_output=True)
    if path.exists() or path.is_symlink():
        raise CleanupError("Recycle operation did not remove the target")


def clean(root: Path, task: str, *, apply: bool = False, verified: bool = False) -> dict:
    if apply and not verified:
        raise CleanupError("Finish verification/dependency checks before --apply --verified")
    data = read_manifest(root, task)
    metadata_path(root, task, "cleanup-report.json")

    def check(entry: dict) -> Path:
        path = target_path(root, task, entry["path"])
        git_guard(root, path)
        actual = fingerprint(root, path)
        if any(actual[key] != entry[key] for key in actual):
            raise CleanupError("Artifact changed since registration; retained: " + entry["path"])
        return path

    for entry in data["entries"]:  # Preflight every target before recycling any.
        check(entry)
    report = {"task": task, "mode": "recycle" if apply else "dry-run", "ok": True,
              "bytes": sum(entry["bytes"] for entry in data["entries"]),
              "files": sum(entry["files"] for entry in data["entries"]), "entries": data["entries"]}
    if apply:
        report.update(completed=[], remaining=[entry["path"] for entry in data["entries"]])
        for entry in data["entries"]:
            try:
                recycle(check(entry))  # Recheck immediately before each operation.
                report["completed"].append(entry["path"])
                report["remaining"].remove(entry["path"])
            except (OSError, CleanupError, subprocess.SubprocessError):
                report.update(ok=False, error="Recycle failed; remaining artifacts retained")
                break
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        metadata_path(root, task, "cleanup-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("record", help="Register only artifacts created/downloaded by this task")
    register.add_argument("task")
    register.add_argument("paths", nargs="+")
    register.add_argument("--kind", choices=sorted(KINDS), required=True)
    register.add_argument("--reason", required=True)
    cleanup = sub.add_parser("clean", help="Dry-run by default; never infer unused files")
    cleanup.add_argument("task")
    cleanup.add_argument("--apply", action="store_true")
    cleanup.add_argument("--verified", action="store_true", help="Assert tests finished and dependencies were reviewed")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        report = (record(root, args.task, args.paths, args.kind, args.reason) if args.command == "record"
                  else clean(root, args.task, apply=args.apply, verified=args.verified))
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok", True) else 1
    except (OSError, CleanupError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("[cleanup] REFUSED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
