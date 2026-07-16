"""Reject changes to package versions that already exist in a Git base tree."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


class HistoryError(RuntimeError):
    """Published package history was changed or could not be inspected."""


def _git(repo: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise HistoryError("git {} failed: {}".format(" ".join(arguments), message))
    return process.stdout


def tree_files(repo: Path, revision: str) -> dict[str, tuple[str, str]]:
    """Return package paths mapped to immutable (mode, object id) identities."""

    payload = _git(repo, "ls-tree", "-r", "-z", "--full-tree", revision, "--", "packages")
    result: dict[str, tuple[str, str]] = {}
    for record in payload.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ")
        if object_type != "blob":
            continue
        path = raw_path.decode("utf-8")
        result[path] = (mode, object_id)
    return result


def _published_versions(repo: Path, base: str) -> set[tuple[str, ...]]:
    return {
        tuple(PurePosixPath(path).parts[:3])
        for path in tree_files(repo, base)
        if len(PurePosixPath(path).parts) >= 4
        and PurePosixPath(path).parts[0] == "packages"
    }


def immutable_changes(repo: Path, base: str, head: str = "HEAD") -> list[str]:
    base_tree = tree_files(repo, base)
    head_tree = tree_files(repo, head)
    published_versions = _published_versions(repo, base)
    changes: list[str] = []
    for version_path in sorted(published_versions):
        prefix = "/".join(version_path) + "/"
        before = {path: identity for path, identity in base_tree.items() if path.startswith(prefix)}
        after = {path: identity for path, identity in head_tree.items() if path.startswith(prefix)}
        for path in sorted(set(before) | set(after)):
            if path not in after:
                changes.append("removed published file {}".format(path))
            elif path not in before:
                changes.append("added file to published version {}".format(path))
            elif before[path] != after[path]:
                changes.append("changed published file {}".format(path))
    return changes


def worktree_changes(repo: Path, base: str) -> list[str]:
    """Return staged, unstaged, and untracked edits inside published versions."""

    published_versions = _published_versions(repo, base)
    payload = _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        "--",
        "packages",
    )
    changes: list[str] = []
    for raw_record in payload.split(b"\0"):
        if not raw_record:
            continue
        record = raw_record.decode("utf-8")
        if len(record) < 4 or record[2] != " ":
            raise HistoryError("could not parse git status record {!r}".format(record))
        status = record[:2]
        path = record[3:]
        parts = PurePosixPath(path).parts
        if len(parts) < 4 or tuple(parts[:3]) not in published_versions:
            continue
        if status == "??" or "A" in status:
            changes.append("added file to published version {}".format(path))
        elif "D" in status:
            changes.append("removed published file {}".format(path))
        else:
            changes.append("changed published file {}".format(path))
    return changes


def default_base(repo: Path) -> str:
    explicit = os.environ.get("IMMUTABLE_HISTORY_BASE")
    if explicit:
        return explicit
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        remote_ref = "origin/{}".format(base_ref)
        return _git(repo, "merge-base", "HEAD", remote_ref).decode("ascii").strip()
    return "HEAD^"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Git revision containing immutable published versions")
    parser.add_argument("--head", default="HEAD", help="Git revision to verify (default: HEAD)")
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument(
        "--committed-only",
        action="store_true",
        help="ignore staged, unstaged, and untracked changes under published versions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = args.repository.resolve()
    base = args.base or default_base(repo)
    changes = immutable_changes(repo, base, args.head)
    if not args.committed_only:
        if args.head != "HEAD":
            raise HistoryError("worktree checking requires --head HEAD or --committed-only")
        changes.extend(item for item in worktree_changes(repo, base) if item not in changes)
    if changes:
        print("Immutable package history check failed:", file=sys.stderr)
        for change in changes:
            print("- " + change, file=sys.stderr)
        print("Publish a new exact version directory instead of editing an existing one.", file=sys.stderr)
        return 1
    print("Immutable package history is unchanged relative to {}.".format(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
