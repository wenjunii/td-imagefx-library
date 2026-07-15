"""Compatibility evaluation independent of a running TouchDesigner process."""

from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass
from typing import Any

from .errors import ValidationError
from .semver import Version, VersionSpec


_OS_ALIASES = {
    "win32": "windows",
    "win": "windows",
    "windows": "windows",
    "darwin": "macos",
    "mac": "macos",
    "macos": "macos",
    "osx": "macos",
    "linux": "linux",
}
_ARCH_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86-64": "x86_64",
    "x86_64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


def normalize_os(value: str) -> str:
    return _OS_ALIASES.get(value.strip().lower(), value.strip().lower())


def normalize_architecture(value: str) -> str:
    return _ARCH_ALIASES.get(value.strip().lower(), value.strip().lower())


def _build_tuple(value: str | int | float) -> tuple[int, ...]:
    text = str(value)
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        raise ValueError(f"invalid TouchDesigner build {value!r}")
    return tuple(int(part) for part in text.split("."))


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    operating_system: str
    architecture: str
    python_version: str
    touchdesigner_build: str | int | float | None = None
    renderer: str | None = None
    gpu_features: frozenset[str] = frozenset()

    @classmethod
    def current(
        cls,
        *,
        touchdesigner_build: str | None = None,
        renderer: str | None = None,
        gpu_features: set[str] | frozenset[str] = frozenset(),
    ) -> "RuntimeContext":
        return cls(
            operating_system=normalize_os(platform.system()),
            architecture=normalize_architecture(platform.machine()),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            touchdesigner_build=touchdesigner_build,
            renderer=renderer.lower() if renderer else None,
            gpu_features=frozenset(feature.lower() for feature in gpu_features),
        )


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def compatible(self) -> bool:
        return not self.errors

    @property
    def verified(self) -> bool:
        return self.compatible and not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return {"compatible": self.compatible, "verified": self.verified, "errors": list(self.errors), "warnings": list(self.warnings)}


def check_fx_api(required: str, supported: str) -> CompatibilityReport:
    """Require the same API major and at least the requested minor/patch."""

    pattern = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
    if not isinstance(required, str) or pattern.fullmatch(required) is None:
        return CompatibilityReport((f"required FX API {required!r} is invalid",))
    if not isinstance(supported, str) or pattern.fullmatch(supported) is None:
        return CompatibilityReport((f"supported FX API {supported!r} is invalid",))
    required_parts = tuple(int(part) for part in required.split("."))
    supported_parts = tuple(int(part) for part in supported.split("."))
    required_parts += (0,) * (3 - len(required_parts))
    supported_parts += (0,) * (3 - len(supported_parts))
    if required_parts[0] != supported_parts[0]:
        return CompatibilityReport((f"FX API major {required_parts[0]} is incompatible with supported major {supported_parts[0]}",))
    if supported_parts < required_parts:
        return CompatibilityReport((f"FX API {required} requires a newer adapter than {supported}",))
    return CompatibilityReport()


def check_package_compatibility(
    manifest: Any,
    runtime: RuntimeContext,
    *,
    supported_fx_api: str,
    strict_unknown: bool = False,
) -> CompatibilityReport:
    """Combine manifest platform/build checks with the effect API contract."""

    platform_report = check_compatibility(
        getattr(manifest, "compatibility", None),
        runtime,
        strict_unknown=strict_unknown,
    )
    api_report = check_fx_api(getattr(manifest, "fx_api", None), supported_fx_api)
    return CompatibilityReport(
        errors=platform_report.errors + api_report.errors,
        warnings=platform_report.warnings + api_report.warnings,
    )


def validate_compatibility_spec(spec: Any, *, path: str = "$.compatibility") -> list[str]:
    issues: list[str] = []
    if not isinstance(spec, dict):
        return [f"{path} must be an object"]

    for required in ("touchdesigner_min_build", "touchdesigner_max_build", "os", "architectures"):
        if required not in spec:
            issues.append(f"{path}.{required} is required")
    for key in spec.keys() - {"touchdesigner_min_build", "touchdesigner_max_build", "os", "architectures"}:
        issues.append(f"{path}.{key} is not supported")

    td = spec.get("touchdesigner", {})
    if td is not None and not isinstance(td, dict):
        issues.append(f"{path}.touchdesigner must be an object")
    elif isinstance(td, dict):
        for key in ("min_build", "max_build"):
            value = td.get(key)
            if value is not None:
                try:
                    _build_tuple(value)
                except ValueError as exc:
                    issues.append(f"{path}.touchdesigner.{key}: {exc}")

    for key in ("touchdesigner_min_build", "touchdesigner_max_build"):
        if key in spec and spec[key] is not None:
            try:
                _build_tuple(spec[key])
            except ValueError as exc:
                issues.append(f"{path}.{key}: {exc}")

    for key in ("operating_systems", "os", "architectures", "renderers", "gpu_features"):
        if key in spec:
            value = spec[key]
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                issues.append(f"{path}.{key} must be an array of non-empty strings")

    operating_systems = spec.get("os")
    if isinstance(operating_systems, list):
        if not operating_systems or any(item not in {"windows", "macos"} for item in operating_systems):
            issues.append(f"{path}.os must contain one or more supported operating systems")
        elif len(set(operating_systems)) != len(operating_systems):
            issues.append(f"{path}.os must not contain duplicates")
    architectures = spec.get("architectures")
    if isinstance(architectures, list):
        if not architectures or any(item not in {"x86_64", "arm64"} for item in architectures):
            issues.append(f"{path}.architectures must contain one or more supported architectures")
        elif len(set(architectures)) != len(architectures):
            issues.append(f"{path}.architectures must not contain duplicates")

    python_spec = spec.get("python", spec.get("python_version"))
    if python_spec is not None:
        if not isinstance(python_spec, str):
            issues.append(f"{path}.python must be a version-constraint string")
        else:
            try:
                VersionSpec.parse(python_spec)
            except ValidationError as exc:
                issues.append(f"{path}.python: {exc.message}")
    return issues


def check_compatibility(
    spec: dict[str, Any] | None,
    runtime: RuntimeContext,
    *,
    strict_unknown: bool = False,
) -> CompatibilityReport:
    """Check a manifest/release compatibility object against a runtime.

    Missing TouchDesigner or renderer information is reported as unverified by
    default. Set ``strict_unknown`` to turn those unknowns into incompatibilities.
    """

    if not spec:
        return CompatibilityReport()
    validation_issues = validate_compatibility_spec(spec)
    if validation_issues:
        return CompatibilityReport(tuple(validation_issues))

    errors: list[str] = []
    warnings: list[str] = []

    allowed_os = spec.get("operating_systems", spec.get("os", []))
    if allowed_os and normalize_os(runtime.operating_system) not in {normalize_os(item) for item in allowed_os}:
        errors.append(f"operating system {runtime.operating_system!r} is not supported")

    allowed_arches = spec.get("architectures", [])
    if allowed_arches and normalize_architecture(runtime.architecture) not in {
        normalize_architecture(item) for item in allowed_arches
    }:
        errors.append(f"architecture {runtime.architecture!r} is not supported")

    python_spec = spec.get("python", spec.get("python_version"))
    if python_spec:
        try:
            candidate = Version.parse(runtime.python_version)
        except ValidationError:
            errors.append(f"runtime Python version {runtime.python_version!r} is invalid")
        else:
            if not VersionSpec.parse(python_spec).matches(candidate):
                errors.append(f"Python {runtime.python_version} does not satisfy {python_spec}")

    td_spec = spec.get("touchdesigner") or {}
    minimum = td_spec.get("min_build", spec.get("touchdesigner_min_build"))
    maximum = td_spec.get("max_build", spec.get("touchdesigner_max_build"))
    if minimum is not None or maximum is not None:
        if runtime.touchdesigner_build is None:
            message = "TouchDesigner build is unknown"
            (errors if strict_unknown else warnings).append(message)
        else:
            try:
                current_build = _build_tuple(runtime.touchdesigner_build)
            except ValueError:
                errors.append(f"runtime TouchDesigner build {runtime.touchdesigner_build!r} is invalid")
            else:
                if minimum is not None and current_build < _build_tuple(minimum):
                    errors.append(f"TouchDesigner build {runtime.touchdesigner_build} is below minimum {minimum}")
                if maximum is not None and current_build > _build_tuple(maximum):
                    errors.append(f"TouchDesigner build {runtime.touchdesigner_build} is above maximum {maximum}")

    renderers = [item.lower() for item in spec.get("renderers", [])]
    if renderers:
        if runtime.renderer is None:
            (errors if strict_unknown else warnings).append("renderer is unknown")
        elif runtime.renderer.lower() not in renderers:
            errors.append(f"renderer {runtime.renderer!r} is not supported")

    required_features = {item.lower() for item in spec.get("gpu_features", [])}
    missing_features = required_features - {item.lower() for item in runtime.gpu_features}
    if missing_features:
        errors.append(f"missing GPU features: {', '.join(sorted(missing_features))}")

    return CompatibilityReport(tuple(errors), tuple(warnings))
