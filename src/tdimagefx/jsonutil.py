"""Strict JSON I/O with duplicate-key detection and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ValidationError


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    duplicates: list[str] = []
    for key, value in pairs:
        if key in result:
            duplicates.append(key)
        result[key] = value
    if duplicates:
        names = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"duplicate JSON object key(s): {names}")
    return result


def loads_json(data: str | bytes, *, source: str = "JSON") -> dict[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f"Invalid {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Invalid {source}", ["document root must be an object"])
    return value


def load_json(path: str | os.PathLike[str], *, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
    source = Path(path)
    try:
        stat_result = source.stat()
    except OSError as exc:
        raise ValidationError(f"Cannot read JSON file {source}: {exc}") from exc
    if not source.is_file():
        raise ValidationError(f"Cannot read JSON file {source}", ["path is not a regular file"])
    if stat_result.st_size > max_bytes:
        raise ValidationError(
            f"Cannot read JSON file {source}",
            [f"file exceeds the {max_bytes}-byte limit"],
        )
    try:
        return loads_json(source.read_bytes(), source=str(source))
    except OSError as exc:
        raise ValidationError(f"Cannot read JSON file {source}: {exc}") from exc


def atomic_write_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def expect_mapping(value: Any, path: str, issues: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return None
    return value


def expect_list(value: Any, path: str, issues: list[str]) -> list[Any] | None:
    if not isinstance(value, list):
        issues.append(f"{path} must be an array")
        return None
    return value


def expect_string(value: Any, path: str, issues: list[str], *, allow_empty: bool = False) -> str | None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        issues.append(f"{path} must be a non-empty string" if not allow_empty else f"{path} must be a string")
        return None
    return value
