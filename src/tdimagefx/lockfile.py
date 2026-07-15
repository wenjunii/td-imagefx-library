"""Exact-version project lockfiles."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import StateError, ValidationError
from .jsonutil import atomic_write_json, load_json
from .manifest import CHANNELS, KINDS, PACKAGE_ID_RE, is_sha256
from .registry import InstalledVersion, LocalRegistry, utc_now
from .semver import Version


LOCKFILE_SCHEMA_VERSION = 1


def _is_datetime(value: Any) -> bool:
    from datetime import datetime

    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _is_build(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    return isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)+", value) is not None


def _is_uri(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "file"))


@dataclass(frozen=True, slots=True)
class LockDependency:
    id: str
    version: Version

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": str(self.version)}


@dataclass(frozen=True, slots=True)
class LockPin:
    id: str
    version: Version
    kind: str
    channel: str
    source_feed: str | None
    manifest_sha256: str | None
    artifact_sha256: str | None
    requested: bool
    dependencies: tuple[LockDependency, ...] = ()

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "LockPin":
        return cls(
            id=data["id"],
            version=Version.parse(data["version"]),
            kind=data["kind"],
            channel=data["channel"],
            source_feed=data["source_feed"],
            manifest_sha256=data["manifest_sha256"].lower() if data["manifest_sha256"] else None,
            artifact_sha256=data["artifact_sha256"].lower() if data["artifact_sha256"] else None,
            requested=data["requested"],
            dependencies=tuple(LockDependency(item["id"], Version.parse(item["version"])) for item in data["dependencies"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": str(self.version),
            "kind": self.kind,
            "channel": self.channel,
            "source_feed": self.source_feed,
            "manifest_sha256": self.manifest_sha256,
            "artifact_sha256": self.artifact_sha256,
            "requested": self.requested,
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


def validate_lockfile_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]
    allowed_root = {"schema_version", "generated_at", "project_id", "fx_api", "touchdesigner_build", "packages"}
    for key in data.keys() - allowed_root:
        issues.append(f"$.{key} is not supported")
    if data.get("schema_version") != LOCKFILE_SCHEMA_VERSION:
        issues.append(f"$.schema_version must equal {LOCKFILE_SCHEMA_VERSION}")
    if not _is_datetime(data.get("generated_at")):
        issues.append("$.generated_at must be an RFC 3339 date-time with timezone")
    if data.get("project_id") is not None and (not isinstance(data["project_id"], str) or not data["project_id"]):
        issues.append("$.project_id must be a non-empty string when provided")
    if not isinstance(data.get("fx_api"), str) or re.fullmatch(r"\d+\.\d+(?:\.\d+)?", data["fx_api"]) is None:
        issues.append("$.fx_api is invalid")
    if not _is_build(data.get("touchdesigner_build")):
        issues.append("$.touchdesigner_build is invalid")
    packages = data.get("packages")
    if not isinstance(packages, list):
        issues.append("$.packages must be an array")
        return issues
    seen_ids: set[str] = set()
    allowed_pin = {
        "id", "version", "kind", "channel", "source_feed", "manifest_sha256",
        "artifact_sha256", "requested", "dependencies",
    }
    for index, package in enumerate(packages):
        path = f"$.packages[{index}]"
        if not isinstance(package, dict):
            issues.append(f"{path} must be an object")
            continue
        for key in package.keys() - allowed_pin:
            issues.append(f"{path}.{key} is not supported")
        for key in allowed_pin:
            if key not in package:
                issues.append(f"{path}.{key} is required")
        package_id = package.get("id")
        if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
            issues.append(f"{path}.id is invalid")
        elif package_id in seen_ids:
            issues.append(f"{path}.id duplicates {package_id!r}")
        else:
            seen_ids.add(package_id)
        try:
            Version.parse(package.get("version"))
        except ValidationError as exc:
            issues.append(f"{path}.version: {exc.message}")
        if package.get("kind") not in KINDS:
            issues.append(f"{path}.kind is invalid")
        if package.get("channel") not in CHANNELS:
            issues.append(f"{path}.channel is invalid")
        if package.get("source_feed") is not None and not _is_uri(package["source_feed"]):
            issues.append(f"{path}.source_feed must be null or a URI")
        for key in ("manifest_sha256", "artifact_sha256"):
            if package.get(key) is not None and not is_sha256(package[key]):
                issues.append(f"{path}.{key} must be null or a SHA-256 digest")
        if not isinstance(package.get("requested"), bool):
            issues.append(f"{path}.requested must be boolean")
        dependencies = package.get("dependencies")
        if not isinstance(dependencies, list):
            issues.append(f"{path}.dependencies must be an array")
            continue
        dep_ids: set[str] = set()
        for dep_index, dependency in enumerate(dependencies):
            dep_path = f"{path}.dependencies[{dep_index}]"
            if not isinstance(dependency, dict) or set(dependency) != {"id", "version"}:
                issues.append(f"{dep_path} must contain exactly id and version")
                continue
            dep_id = dependency.get("id")
            if not isinstance(dep_id, str) or PACKAGE_ID_RE.fullmatch(dep_id) is None:
                issues.append(f"{dep_path}.id is invalid")
            elif dep_id in dep_ids:
                issues.append(f"{dep_path}.id duplicates {dep_id!r}")
            else:
                dep_ids.add(dep_id)
            try:
                Version.parse(dependency.get("version"))
            except ValidationError as exc:
                issues.append(f"{dep_path}.version: {exc.message}")
    exact_versions: dict[str, Version] = {}
    for package in packages:
        if not isinstance(package, dict):
            continue
        try:
            exact_versions[package["id"]] = Version.parse(package["version"])
        except (KeyError, ValidationError, TypeError):
            continue
    for package_index, package in enumerate(packages):
        if not isinstance(package, dict) or not isinstance(package.get("dependencies"), list):
            continue
        for dependency_index, dependency in enumerate(package["dependencies"]):
            if not isinstance(dependency, dict):
                continue
            dep_id = dependency.get("id")
            dep_version = dependency.get("version")
            if not isinstance(dep_id, str) or not isinstance(dep_version, str):
                continue
            path = f"$.packages[{package_index}].dependencies[{dependency_index}]"
            pinned = exact_versions.get(dep_id)
            if pinned is None:
                issues.append(f"{path} references package {dep_id!r}, which is not pinned")
                continue
            try:
                required = Version.parse(dep_version)
            except ValidationError:
                continue
            if not pinned.exactly_equals(required):
                issues.append(f"{path} requires {dep_id} {required}, but the lock pins {pinned}")
    return issues


@dataclass(frozen=True, slots=True)
class Lockfile:
    generated_at: str
    fx_api: str
    touchdesigner_build: str | int | float
    packages: tuple[LockPin, ...]
    project_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        fx_api: str,
        touchdesigner_build: str | int | float,
        project_id: str | None = None,
        packages: tuple[LockPin, ...] = (),
    ) -> "Lockfile":
        result = cls(utc_now(), fx_api, touchdesigner_build, packages, project_id)
        issues = validate_lockfile_data(result.to_dict())
        if issues:
            raise ValidationError("Lockfile validation failed", issues)
        return result

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "Lockfile":
        issues = validate_lockfile_data(data)
        if issues:
            raise ValidationError("Lockfile validation failed", issues)
        return cls(
            generated_at=data["generated_at"],
            fx_api=data["fx_api"],
            touchdesigner_build=data["touchdesigner_build"],
            packages=tuple(LockPin.from_data(item) for item in data["packages"]),
            project_id=data.get("project_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": LOCKFILE_SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "fx_api": self.fx_api,
            "touchdesigner_build": self.touchdesigner_build,
            "packages": [item.to_dict() for item in sorted(self.packages, key=lambda pin: pin.id)],
        }
        if self.project_id is not None:
            result["project_id"] = self.project_id
        return result

    def get(self, package_id: str) -> LockPin | None:
        return next((pin for pin in self.packages if pin.id == package_id), None)

    def versions(self) -> dict[str, Version]:
        return {pin.id: pin.version for pin in self.packages}

    def with_pin(self, pin: LockPin, *, replace_existing: bool = False) -> "Lockfile":
        existing = self.get(pin.id)
        if existing is not None and not replace_existing:
            raise StateError(f"lockfile already pins {pin.id} to {existing.version}")
        pins = tuple(item for item in self.packages if item.id != pin.id) + (pin,)
        result = replace(self, generated_at=utc_now(), packages=pins)
        issues = validate_lockfile_data(result.to_dict())
        if issues:
            raise ValidationError("Lockfile validation failed", issues)
        return result

    def without(self, package_id: str) -> "Lockfile":
        if self.get(package_id) is None:
            raise StateError(f"lockfile does not contain {package_id}")
        result = replace(self, generated_at=utc_now(), packages=tuple(item for item in self.packages if item.id != package_id))
        issues = validate_lockfile_data(result.to_dict())
        if issues:
            raise ValidationError("Lockfile validation failed", issues)
        return result


def load_lockfile(path: str | Path) -> Lockfile:
    return Lockfile.from_data(load_json(path))


def write_lockfile(path: str | Path, lockfile: Lockfile) -> None:
    issues = validate_lockfile_data(lockfile.to_dict())
    if issues:
        raise ValidationError("Lockfile validation failed", issues)
    atomic_write_json(path, lockfile.to_dict())


def resolve_lockfile(
    lockfile: Lockfile,
    registry: LocalRegistry,
    *,
    require_verified: bool = True,
    allowed_statuses: frozenset[str] = frozenset({"ready", "staged"}),
) -> dict[str, InstalledVersion]:
    """Resolve every exact pin without falling back to a different version."""

    resolved: dict[str, InstalledVersion] = {}
    issues: list[str] = []
    for pin in lockfile.packages:
        candidates = registry.packages.get(pin.id, ())
        installed = next(
            (item for item in candidates if item.version.exactly_equals(pin.version)),
            None,
        )
        if installed is None:
            issues.append(f"missing exact package {pin.id} {pin.version}")
            continue
        if installed.status not in allowed_statuses:
            issues.append(f"package {pin.id} {pin.version} has unusable status {installed.status!r}")
        verification = installed.integrity.get("verification")
        if require_verified and verification != "verified":
            issues.append(f"package {pin.id} {pin.version} is not integrity-verified")
        for field, expected in (
            ("manifest_sha256", pin.manifest_sha256),
            ("artifact_sha256", pin.artifact_sha256),
        ):
            actual = installed.integrity.get(field)
            if expected is not None and (not isinstance(actual, str) or actual.lower() != expected.lower()):
                issues.append(f"package {pin.id} {pin.version} has a different {field}")
        resolved[pin.id] = installed
    if issues:
        raise StateError("lockfile cannot be resolved exactly:\n- " + "\n- ".join(issues))
    return resolved
