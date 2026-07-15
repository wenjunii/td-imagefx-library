"""Package manifest loading and semantic validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compatibility import validate_compatibility_spec
from .errors import SecurityError, ValidationError
from .jsonutil import load_json
from .paths import validate_package_path
from .semver import Version, VersionSpec


PACKAGE_SCHEMA_VERSION = 1
PACKAGE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TD_PARAMETER_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
CATEGORY_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
CHANNELS = frozenset({"stable", "beta", "experimental"})
KINDS = frozenset({"effect", "shader", "plugin", "technique", "adapter", "preset", "modulator", "example", "core"})
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _validate_objects_with_ids(value: Any, path: str, issues: list[str], *, require_nonempty: bool = False) -> None:
    if not isinstance(value, list):
        issues.append(f"{path} must be an array")
        return
    if require_nonempty and not value:
        issues.append(f"{path} must not be empty")
    identifiers: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{item_path} must be an object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or IDENTIFIER_RE.fullmatch(identifier) is None:
            issues.append(f"{item_path}.id must match {IDENTIFIER_RE.pattern}")
        elif len(identifier) > 80:
            issues.append(f"{item_path}.id must be at most 80 characters")
        elif identifier in identifiers:
            issues.append(f"{item_path}.id duplicates {identifier!r}")
        else:
            identifiers.add(identifier)


def validate_manifest_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]

    allowed_root = {
        "schema_version", "id", "name", "version", "fx_api", "kind", "category", "channel",
        "description", "publisher", "license", "entrypoints", "inputs", "outputs", "parameters",
        "compatibility", "permissions", "dependencies", "alpha_policy", "resolution_policy", "stateful", "tags",
    }
    for key in data.keys() - allowed_root:
        issues.append(f"$.{key} is not supported")
    for key in allowed_root:
        if key not in data:
            issues.append(f"$.{key} is required")

    if data.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        issues.append(f"$.schema_version must equal {PACKAGE_SCHEMA_VERSION}")

    package_id = data.get("id")
    if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
        issues.append(f"$.id must match {PACKAGE_ID_RE.pattern}")
    elif len(package_id) > 180:
        issues.append("$.id must be at most 180 characters")

    string_limits = {"name": 120, "description": 2000, "publisher": 200, "license": 100, "category": 80}
    for key, maximum in string_limits.items():
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(f"$.{key} must be a non-empty string")
        elif len(data[key]) > maximum:
            issues.append(f"$.{key} must be at most {maximum} characters")
    category = data.get("category")
    if isinstance(category, str) and CATEGORY_RE.fullmatch(category) is None:
        issues.append(f"$.category must match {CATEGORY_RE.pattern}")

    try:
        Version.parse(data.get("version"))
    except ValidationError as exc:
        issues.append(f"$.version: {exc.issues[0] if exc.issues else exc.message}")

    fx_api = data.get("fx_api")
    if not isinstance(fx_api, str) or re.fullmatch(r"\d+\.\d+(?:\.\d+)?", fx_api) is None:
        issues.append("$.fx_api must use major.minor or major.minor.patch form")

    kind = data.get("kind")
    if kind not in KINDS:
        issues.append(f"$.kind must be one of {', '.join(sorted(KINDS))}")
    channel = data.get("channel")
    if channel not in CHANNELS:
        issues.append(f"$.channel must be one of {', '.join(sorted(CHANNELS))}")

    entrypoints = data.get("entrypoints")
    if not isinstance(entrypoints, dict):
        issues.append("$.entrypoints must be an object")
    else:
        if "shader" not in entrypoints or "touchdesigner_component" not in entrypoints:
            issues.append("$.entrypoints must contain shader and touchdesigner_component")
        if not any(value is not None for value in entrypoints.values()):
            issues.append("$.entrypoints must contain at least one non-null path")
        for name, relative_path in entrypoints.items():
            if not isinstance(name, str) or IDENTIFIER_RE.fullmatch(name) is None:
                issues.append(f"$.entrypoints key {name!r} must match {IDENTIFIER_RE.pattern}")
            if name not in {"shader", "touchdesigner_component", "native_plugin"}:
                issues.append(f"$.entrypoints.{name} is not supported")
            if relative_path is not None:
                try:
                    validate_package_path(relative_path, label=f"$.entrypoints.{name}")
                except SecurityError as exc:
                    issues.append(str(exc))

    _validate_objects_with_ids(data.get("inputs"), "$.inputs", issues)
    _validate_objects_with_ids(data.get("outputs"), "$.outputs", issues)
    _validate_objects_with_ids(data.get("parameters"), "$.parameters", issues)

    for collection_name in ("inputs", "outputs"):
        collection = data.get(collection_name)
        if isinstance(collection, list):
            for index, port in enumerate(collection):
                if not isinstance(port, dict):
                    continue
                path = f"$.{collection_name}[{index}]"
                allowed = {"id", "family", "required", "semantic", "description"}
                for key in port.keys() - allowed:
                    issues.append(f"{path}.{key} is not supported")
                if port.get("family") not in {"TOP", "CHOP", "SOP", "DAT"}:
                    issues.append(f"{path}.family is invalid")
                if "required" in port and not isinstance(port["required"], bool):
                    issues.append(f"{path}.required must be boolean")
                for key, maximum in (("semantic", 80), ("description", 500)):
                    if key in port and not isinstance(port[key], str):
                        issues.append(f"{path}.{key} must be a string")
                    elif key in port and len(port[key]) > maximum:
                        issues.append(f"{path}.{key} must be at most {maximum} characters")

    parameters = data.get("parameters")
    if isinstance(parameters, list):
        parameter_types = {"float", "int", "toggle", "pulse", "string", "menu", "rgb", "rgba", "xy", "xyz", "uv", "file", "folder", "operator"}
        allowed_parameter_keys = {
            "id", "name", "label", "type", "default", "min", "max", "norm_min", "norm_max",
            "clamp_min", "clamp_max", "uniform", "page", "unit", "description", "animatable", "choices",
        }
        for index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue
            path = f"$.parameters[{index}]"
            for key in parameter.keys() - allowed_parameter_keys:
                issues.append(f"{path}.{key} is not supported")
            for required in ("id", "name", "type", "default"):
                if required not in parameter:
                    issues.append(f"{path}.{required} is required")
            if not isinstance(parameter.get("name"), str) or TD_PARAMETER_RE.fullmatch(parameter["name"]) is None:
                issues.append(f"{path}.name is not a valid TouchDesigner parameter name")
            elif len(parameter["name"]) > 80:
                issues.append(f"{path}.name must be at most 80 characters")
            if parameter.get("type") not in parameter_types:
                issues.append(f"{path}.type is invalid")
            for key in ("min", "max", "norm_min", "norm_max"):
                if key in parameter and (not isinstance(parameter[key], (int, float)) or isinstance(parameter[key], bool)):
                    issues.append(f"{path}.{key} must be numeric")
            for key in ("clamp_min", "clamp_max", "animatable"):
                if key in parameter and not isinstance(parameter[key], bool):
                    issues.append(f"{path}.{key} must be boolean")
            for key, maximum in (("label", 120), ("uniform", 120), ("page", 80), ("unit", 40), ("description", 1000)):
                if key in parameter and not isinstance(parameter[key], str):
                    issues.append(f"{path}.{key} must be a string")
                elif key in parameter and len(parameter[key]) > maximum:
                    issues.append(f"{path}.{key} must be at most {maximum} characters")
            if isinstance(parameter.get("uniform"), str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parameter["uniform"]) is None:
                issues.append(f"{path}.uniform is invalid")
            if "min" in parameter and "max" in parameter and isinstance(parameter["min"], (int, float)) and isinstance(parameter["max"], (int, float)) and parameter["min"] > parameter["max"]:
                issues.append(f"{path}.min cannot exceed max")
            if "choices" in parameter:
                choices = parameter["choices"]
                if not isinstance(choices, list) or not choices:
                    issues.append(f"{path}.choices must be a non-empty array")
                else:
                    for choice_index, choice in enumerate(choices):
                        if not isinstance(choice, dict) or set(choice) != {"value", "label"} or not isinstance(choice.get("label"), str) or not choice["label"]:
                            issues.append(f"{path}.choices[{choice_index}] must contain value and a non-empty label")
                        elif isinstance(choice.get("value"), bool) or not isinstance(choice.get("value"), (str, int, float)):
                            issues.append(f"{path}.choices[{choice_index}].value has an unsupported type")

    compatibility = data.get("compatibility")
    issues.extend(validate_compatibility_spec(compatibility))

    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        issues.append("$.permissions must be an object")
    else:
        allowed_permissions = {"python", "filesystem", "network", "subprocess", "native_code", "device_access", "network_domains", "filesystem_paths"}
        for permission in permissions.keys() - allowed_permissions:
            issues.append(f"$.permissions.{permission} is not supported")
        for required in ("python", "filesystem", "network", "subprocess"):
            if required not in permissions:
                issues.append(f"$.permissions.{required} is required")
        for permission, allowed in permissions.items():
            if not isinstance(permission, str) or not permission:
                issues.append("$.permissions keys must be non-empty strings")
            if permission in {"network_domains", "filesystem_paths"}:
                if not isinstance(allowed, list) or not all(isinstance(item, str) and item for item in allowed):
                    issues.append(f"$.permissions.{permission} must be an array of strings")
                elif len(set(allowed)) != len(allowed):
                    issues.append(f"$.permissions.{permission} must not contain duplicates")
                elif permission == "network_domains" and any(len(item) > 253 for item in allowed):
                    issues.append("$.permissions.network_domains entries must be at most 253 characters")
                elif permission == "filesystem_paths" and any(len(item) > 1024 for item in allowed):
                    issues.append("$.permissions.filesystem_paths entries must be at most 1024 characters")
            elif not isinstance(allowed, bool):
                issues.append(f"$.permissions.{permission} must be boolean")

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        issues.append("$.dependencies must be an array")
    else:
        dependency_ids: set[str] = set()
        for index, dependency in enumerate(dependencies):
            path = f"$.dependencies[{index}]"
            if not isinstance(dependency, dict):
                issues.append(f"{path} must be an object")
                continue
            for key in dependency.keys() - {"id", "version", "optional", "reason"}:
                issues.append(f"{path}.{key} is not supported")
            dep_id = dependency.get("id")
            if not isinstance(dep_id, str) or PACKAGE_ID_RE.fullmatch(dep_id) is None:
                issues.append(f"{path}.id is not a valid package id")
            elif dep_id in dependency_ids:
                issues.append(f"{path}.id duplicates {dep_id!r}")
            else:
                dependency_ids.add(dep_id)
            constraint = dependency.get("version")
            if not isinstance(constraint, str) or not constraint or len(constraint) > 120:
                issues.append(f"{path}.version must be a non-empty constraint of at most 120 characters")
            else:
                try:
                    VersionSpec.parse(constraint)
                except ValidationError as exc:
                    issues.append(f"{path}.version: {exc.message}")
            if "optional" in dependency and not isinstance(dependency["optional"], bool):
                issues.append(f"{path}.optional must be boolean")
            if "reason" in dependency and (not isinstance(dependency["reason"], str) or len(dependency["reason"]) > 500):
                issues.append(f"{path}.reason must be a string of at most 500 characters")

    alpha_policy = data.get("alpha_policy")
    if alpha_policy not in {"preserve", "process", "blend", "replace", "force_opaque", "premultiply", "unpremultiply", "configurable"}:
        issues.append("$.alpha_policy has an unsupported value")
    resolution_policy = data.get("resolution_policy")
    if resolution_policy not in {"input", "first_input", "fixed", "scale", "custom", "dynamic"}:
        issues.append("$.resolution_policy has an unsupported value")
    if not isinstance(data.get("stateful"), bool):
        issues.append("$.stateful must be boolean")

    tags = data.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        issues.append("$.tags must be an array of non-empty strings")
    elif len({tag.casefold() for tag in tags}) != len(tags):
        issues.append("$.tags must not contain duplicates")
    elif any(CATEGORY_RE.fullmatch(tag) is None for tag in tags):
        issues.append(f"$.tags items must match {CATEGORY_RE.pattern}")
    elif any(len(tag) > 60 for tag in tags):
        issues.append("$.tags items must be at most 60 characters")
    return issues


@dataclass(frozen=True, slots=True)
class PackageManifest:
    schema_version: int
    id: str
    name: str
    version: Version
    fx_api: str
    kind: str
    category: str
    channel: str
    description: str
    publisher: str
    license: str
    entrypoints: dict[str, str | None]
    inputs: tuple[dict[str, Any], ...]
    outputs: tuple[dict[str, Any], ...]
    parameters: tuple[dict[str, Any], ...]
    compatibility: dict[str, Any]
    permissions: dict[str, Any]
    dependencies: tuple[dict[str, Any], ...]
    alpha_policy: str
    resolution_policy: str
    stateful: bool
    tags: tuple[str, ...]
    raw: dict[str, Any]

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PackageManifest":
        issues = validate_manifest_data(data)
        if issues:
            raise ValidationError("Package manifest validation failed", issues)
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            name=data["name"],
            version=Version.parse(data["version"]),
            fx_api=data["fx_api"],
            kind=data["kind"],
            category=data["category"],
            channel=data["channel"],
            description=data["description"],
            publisher=data["publisher"],
            license=data["license"],
            entrypoints=dict(data["entrypoints"]),
            inputs=tuple(dict(item) for item in data["inputs"]),
            outputs=tuple(dict(item) for item in data["outputs"]),
            parameters=tuple(dict(item) for item in data["parameters"]),
            compatibility=dict(data["compatibility"]),
            permissions=dict(data["permissions"]),
            dependencies=tuple(dict(item) for item in data["dependencies"]),
            alpha_policy=data["alpha_policy"],
            resolution_policy=data["resolution_policy"],
            stateful=data["stateful"],
            tags=tuple(data["tags"]),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


def load_manifest(path: str | Path) -> PackageManifest:
    return PackageManifest.from_data(load_json(path))
