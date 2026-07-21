"""Strict Semantic Versioning 2.0.0 parsing, ordering, and constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from .errors import ValidationError


MAX_SEMVER_CHARS = 256
_ASCII_DIGITS = frozenset("0123456789")
_IDENTIFIER_CHARS = frozenset(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-"
)


def _parse_identifiers(value: str, *, reject_numeric_leading_zero: bool) -> tuple[str, ...]:
    identifiers = tuple(value.split("."))
    if not identifiers or any(
        not item or any(character not in _IDENTIFIER_CHARS for character in item)
        for item in identifiers
    ):
        raise ValueError("invalid semantic-version identifier")
    if reject_numeric_leading_zero and any(
        len(item) > 1 and item[0] == "0" and all(char in _ASCII_DIGITS for char in item)
        for item in identifiers
    ):
        raise ValueError("numeric prerelease identifiers may not contain leading zeros")
    return identifiers


def _parse_version_text(value: str) -> tuple[int, int, int, tuple[str, ...], tuple[str, ...]]:
    """Parse bounded SemVer text without backtracking regular expressions."""

    if not value or len(value) > MAX_SEMVER_CHARS or value.count("+") > 1:
        raise ValueError("invalid semantic-version length or build separator")
    core_and_pre, build_separator, build_text = value.partition("+")
    build = (
        _parse_identifiers(build_text, reject_numeric_leading_zero=False)
        if build_separator
        else ()
    )
    core_text, prerelease_separator, prerelease_text = core_and_pre.partition("-")
    prerelease = (
        _parse_identifiers(prerelease_text, reject_numeric_leading_zero=True)
        if prerelease_separator
        else ()
    )
    core = tuple(core_text.split("."))
    if len(core) != 3 or any(
        not item
        or any(character not in _ASCII_DIGITS for character in item)
        or (len(item) > 1 and item[0] == "0")
        for item in core
    ):
        raise ValueError("invalid semantic-version core")
    major, minor, patch = (int(item) for item in core)
    return major, minor, patch, prerelease, build


@total_ordering
@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "Version":
        if not isinstance(value, str):
            raise ValidationError("Invalid semantic version", ["version must be a string"])
        try:
            major, minor, patch, prerelease, build = _parse_version_text(value)
        except ValueError:
            raise ValidationError(
                "Invalid semantic version",
                ["version is not valid bounded SemVer 2.0.0"],
            ) from None
        return cls(major, minor, patch, prerelease, build)

    def _compare_precedence(self, other: "Version") -> int:
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return -1 if core < other_core else 1
        if not self.prerelease and not other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return -1 if int(left) < int(right) else 1
            if left_numeric != right_numeric:
                return -1 if left_numeric else 1
            return -1 if left < right else 1
        if len(self.prerelease) == len(other.prerelease):
            return 0
        return -1 if len(self.prerelease) < len(other.prerelease) else 1

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._compare_precedence(other) < 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._compare_precedence(other) == 0

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def exactly_equals(self, other: "Version") -> bool:
        return (
            self.major,
            self.minor,
            self.patch,
            self.prerelease,
            self.build,
        ) == (
            other.major,
            other.minor,
            other.patch,
            other.prerelease,
            other.build,
        )

    def __str__(self) -> str:
        result = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            result += "-" + ".".join(self.prerelease)
        if self.build:
            result += "+" + ".".join(self.build)
        return result


@dataclass(frozen=True, slots=True)
class _Comparator:
    operator: str
    version: Version

    def matches(self, candidate: Version) -> bool:
        comparison = candidate._compare_precedence(self.version)
        return {
            "=": comparison == 0,
            "==": comparison == 0,
            ">": comparison > 0,
            ">=": comparison >= 0,
            "<": comparison < 0,
            "<=": comparison <= 0,
        }[self.operator]


@dataclass(frozen=True, slots=True)
class VersionSpec:
    """A compact AND-only version constraint.

    Supported forms are exact versions, comma-separated comparisons, caret ranges,
    tilde ranges, and ``*``. This intentionally avoids surprising npm-style
    implicit wildcards.
    """

    comparators: tuple[_Comparator, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "VersionSpec":
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("Invalid version constraint", ["constraint must be a non-empty string"])
        source = value.strip()
        if source in {"*", "any"}:
            return cls()
        if source.startswith("^") or source.startswith("~"):
            marker, raw = source[0], source[1:].strip()
            base = Version.parse(raw)
            lower = _Comparator(">=", base)
            if marker == "~":
                upper = Version(base.major, base.minor + 1, 0)
            elif base.major > 0:
                upper = Version(base.major + 1, 0, 0)
            elif base.minor > 0:
                upper = Version(0, base.minor + 1, 0)
            else:
                upper = Version(0, 0, base.patch + 1)
            return cls((lower, _Comparator("<", upper)))
        comparators: list[_Comparator] = []
        for item in source.split(","):
            token = item.strip()
            match = re.fullmatch(r"(<=|>=|==|=|<|>)?\s*(.+)", token)
            if match is None:
                raise ValidationError("Invalid version constraint", [f"invalid comparator {token!r}"])
            operator = match.group(1) or "="
            comparators.append(_Comparator(operator, Version.parse(match.group(2))))
        return cls(tuple(comparators))

    def matches(self, version: Version | str) -> bool:
        candidate = Version.parse(version) if isinstance(version, str) else version
        return all(item.matches(candidate) for item in self.comparators)

    def __str__(self) -> str:
        if not self.comparators:
            return "*"
        return ",".join(f"{item.operator}{item.version}" for item in self.comparators)
