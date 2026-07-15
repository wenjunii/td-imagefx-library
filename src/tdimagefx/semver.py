"""Strict Semantic Versioning 2.0.0 parsing, ordering, and constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from .errors import ValidationError


_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


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
        match = _VERSION_RE.fullmatch(value)
        if match is None:
            raise ValidationError("Invalid semantic version", [f"{value!r} is not valid SemVer 2.0.0"])
        prerelease = tuple(match.group("pre").split(".")) if match.group("pre") else ()
        build = tuple(match.group("build").split(".")) if match.group("build") else ()
        return cls(int(match.group("major")), int(match.group("minor")), int(match.group("patch")), prerelease, build)

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
