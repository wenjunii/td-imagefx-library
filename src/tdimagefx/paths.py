"""Cross-platform path validation for untrusted package metadata."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath

from .errors import SecurityError


_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def validate_package_path(value: str, *, label: str = "package path") -> PurePosixPath:
    """Return a safe relative POSIX path or raise ``SecurityError``.

    The stricter Windows rules are applied on every host so a package staged on
    one platform cannot become dangerous or ambiguous when copied to another.
    """

    if not isinstance(value, str) or not value or "\x00" in value:
        raise SecurityError(f"{label} must be a non-empty string without NUL bytes")
    if value != unicodedata.normalize("NFC", value):
        raise SecurityError(f"{label} must use canonical Unicode normalization")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SecurityError(f"{label} contains control characters")
    if "\\" in value:
        raise SecurityError(f"{label} must use forward slashes")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise SecurityError(f"{label} must be relative")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise SecurityError(f"{label} contains an unsafe path segment")
    path = PurePosixPath(value)
    if len(value) > 1024:
        raise SecurityError(f"{label} is too long")
    for part in path.parts:
        if len(part) > 255:
            raise SecurityError(f"{label} contains an overlong path segment")
        if part.endswith((" ", ".")) or ":" in part:
            raise SecurityError(f"{label} contains a Windows-unsafe segment {part!r}")
        base_name = part.split(".", 1)[0].upper()
        if base_name in _WINDOWS_RESERVED:
            raise SecurityError(f"{label} contains reserved name {part!r}")
    return path


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
