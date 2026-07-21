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
PROCESSING_MODELS = frozenset({"single_pass", "multi_pass", "temporal", "simulation", "adapter"})
GPU_COSTS = frozenset({"low", "medium", "high", "extreme"})
CAPABILITIES = frozenset({
    "multi_pass", "history", "second_input", "transition", "displacement", "depth",
    "normal", "flow", "simulation", "audio", "native_plugin", "network", "python",
})
INPUT_ROLES = frozenset({
    "source_image", "second_image", "auxiliary_image", "transition_image", "mask", "depth",
    "normal", "flow", "displacement", "audio", "control", "data",
})
OUTPUT_ROLES = frozenset({"image", "mask", "state", "data"})
COLOR_SPACES = frozenset({
    "source", "project", "linear-srgb", "srgb", "rec709", "rec2020", "display-p3", "acescg", "raw",
})
COLOR_REFERENCES = frozenset({"scene_referred", "display_referred", "data"})
ALPHA_REPRESENTATIONS = frozenset({"straight", "premultiplied", "opaque", "none", "any"})
PIXEL_FORMAT_POLICIES = frozenset({"inherit", "minimum", "preferred", "fixed"})
PIXEL_FORMATS = frozenset({
    "r8", "rg8", "rgba8", "r16f", "rg16f", "rgba16f", "r32f", "rg32f", "rgba32f",
})
SAMPLING_FILTERS = frozenset({"inherit", "nearest", "linear", "mipmap", "anisotropic"})
EDGE_MODES = frozenset({"inherit", "clamp", "repeat", "mirror", "border"})
DETERMINISM_MODES = frozenset({"deterministic", "seeded", "time_dependent", "external", "non_deterministic"})
RESET_STRATEGIES = frozenset({"pulse_parameter", "toggle_parameter", "automatic", "unsupported"})
RESET_TARGETS = frozenset({"history", "simulation_state", "all"})
PROVENANCE_ORIGINS = frozenset({"original", "adapted", "ported", "generated", "third_party"})
SOURCE_TYPES = frozenset({"original", "repository", "publication", "website", "generated"})
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


def _validate_relative_path(value: Any, path: str, issues: list[str]) -> None:
    try:
        validate_package_path(value, label=path)
    except SecurityError as exc:
        issues.append(str(exc))


def _validate_image_contract(value: Any, alpha_policy: Any, issues: list[str]) -> None:
    path = "$.image_contract"
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return
    allowed = {"color", "alpha", "pixel_format", "sampling"}
    for key in value.keys() - allowed:
        issues.append(f"{path}.{key} is not supported")
    for key in allowed:
        if key not in value:
            issues.append(f"{path}.{key} is required")

    color = value.get("color")
    if not isinstance(color, dict):
        issues.append(f"{path}.color must be an object")
    else:
        color_keys = {"input_space", "working_space", "output_space", "reference"}
        for key in color.keys() - color_keys:
            issues.append(f"{path}.color.{key} is not supported")
        for key in color_keys:
            if key not in color:
                issues.append(f"{path}.color.{key} is required")
        for key in ("input_space", "working_space", "output_space"):
            if not isinstance(color.get(key), str) or color[key] not in COLOR_SPACES:
                issues.append(f"{path}.color.{key} must be one of {', '.join(sorted(COLOR_SPACES))}")
        if not isinstance(color.get("reference"), str) or color["reference"] not in COLOR_REFERENCES:
            issues.append(f"{path}.color.reference must be one of {', '.join(sorted(COLOR_REFERENCES))}")

    alpha = value.get("alpha")
    if not isinstance(alpha, dict):
        issues.append(f"{path}.alpha must be an object")
    else:
        alpha_keys = {"input", "working", "output"}
        for key in alpha.keys() - alpha_keys:
            issues.append(f"{path}.alpha.{key} is not supported")
        for key in alpha_keys:
            if key not in alpha:
                issues.append(f"{path}.alpha.{key} is required")
            elif not isinstance(alpha[key], str) or alpha[key] not in ALPHA_REPRESENTATIONS:
                issues.append(f"{path}.alpha.{key} must be one of {', '.join(sorted(ALPHA_REPRESENTATIONS))}")
        alpha_output = alpha.get("output")
        expected_output = {
            "premultiply": "premultiplied",
            "unpremultiply": "straight",
            "force_opaque": "opaque",
        }.get(alpha_policy) if isinstance(alpha_policy, str) else None
        if expected_output is not None and alpha_output != expected_output:
            issues.append(f"{path}.alpha.output must be {expected_output!r} when $.alpha_policy is {alpha_policy!r}")
        alpha_input = alpha.get("input")
        if alpha_policy == "preserve" and isinstance(alpha_input, str) and alpha_input != "any" and alpha_output != alpha_input:
            issues.append(f"{path}.alpha.output must match input when $.alpha_policy is 'preserve'")

    pixel_format = value.get("pixel_format")
    if not isinstance(pixel_format, dict):
        issues.append(f"{path}.pixel_format must be an object")
    else:
        for key in pixel_format.keys() - {"policy", "format"}:
            issues.append(f"{path}.pixel_format.{key} is not supported")
        policy = pixel_format.get("policy")
        if not isinstance(policy, str) or policy not in PIXEL_FORMAT_POLICIES:
            issues.append(f"{path}.pixel_format.policy must be one of {', '.join(sorted(PIXEL_FORMAT_POLICIES))}")
        format_name = pixel_format.get("format")
        if policy == "inherit" and "format" in pixel_format:
            issues.append(f"{path}.pixel_format.format must be omitted when policy is 'inherit'")
        elif (
            isinstance(policy, str)
            and policy in {"minimum", "preferred", "fixed"}
            and (not isinstance(format_name, str) or format_name not in PIXEL_FORMATS)
        ):
            issues.append(f"{path}.pixel_format.format must be one of {', '.join(sorted(PIXEL_FORMATS))}")

    sampling = value.get("sampling")
    if not isinstance(sampling, dict):
        issues.append(f"{path}.sampling must be an object")
    else:
        for key in sampling.keys() - {"filter", "edge", "mipmaps", "border_color"}:
            issues.append(f"{path}.sampling.{key} is not supported")
        for key in ("filter", "edge", "mipmaps"):
            if key not in sampling:
                issues.append(f"{path}.sampling.{key} is required")
        filter_name = sampling.get("filter")
        if not isinstance(filter_name, str) or filter_name not in SAMPLING_FILTERS:
            issues.append(f"{path}.sampling.filter must be one of {', '.join(sorted(SAMPLING_FILTERS))}")
        edge = sampling.get("edge")
        if not isinstance(edge, str) or edge not in EDGE_MODES:
            issues.append(f"{path}.sampling.edge must be one of {', '.join(sorted(EDGE_MODES))}")
        mipmaps = sampling.get("mipmaps")
        if not isinstance(mipmaps, bool):
            issues.append(f"{path}.sampling.mipmaps must be boolean")
        elif isinstance(filter_name, str) and filter_name in {"mipmap", "anisotropic"} and not mipmaps:
            issues.append(f"{path}.sampling.mipmaps must be true for {filter_name!r} filtering")
        border_color = sampling.get("border_color")
        if edge == "border":
            if (
                not isinstance(border_color, list)
                or len(border_color) != 4
                or any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in border_color)
            ):
                issues.append(f"{path}.sampling.border_color must contain four numbers when edge is 'border'")
        elif "border_color" in sampling:
            issues.append(f"{path}.sampling.border_color is only supported when edge is 'border'")


def _validate_determinism(value: Any, parameters: Any, issues: list[str]) -> None:
    path = "$.determinism"
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return
    allowed = {"mode", "seed_parameter", "fixed_seed", "fixed_timestep"}
    for key in value.keys() - allowed:
        issues.append(f"{path}.{key} is not supported")
    mode = value.get("mode")
    if not isinstance(mode, str) or mode not in DETERMINISM_MODES:
        issues.append(f"{path}.mode must be one of {', '.join(sorted(DETERMINISM_MODES))}")
    seed_keys = [key for key in ("seed_parameter", "fixed_seed") if key in value]
    if mode == "seeded" and len(seed_keys) != 1:
        issues.append(f"{path} must define exactly one of seed_parameter or fixed_seed when mode is 'seeded'")
    elif mode != "seeded" and seed_keys:
        issues.append(f"{path} seed fields are only supported when mode is 'seeded'")

    parameter_id = value.get("seed_parameter")
    if "seed_parameter" in value:
        if not isinstance(parameter_id, str) or IDENTIFIER_RE.fullmatch(parameter_id) is None:
            issues.append(f"{path}.seed_parameter must be a parameter id")
        else:
            parameter_map = {
                item.get("id"): item for item in parameters or []
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            } if isinstance(parameters, list) else {}
            parameter = parameter_map.get(parameter_id)
            if parameter is None:
                issues.append(f"{path}.seed_parameter must reference an item in $.parameters")
            elif not isinstance(parameter.get("type"), str) or parameter["type"] not in {"int", "float"}:
                issues.append(f"{path}.seed_parameter must reference an int or float parameter")
    if "fixed_seed" in value:
        fixed_seed = value["fixed_seed"]
        if not isinstance(fixed_seed, int) or isinstance(fixed_seed, bool) or not -(2**31) <= fixed_seed < 2**31:
            issues.append(f"{path}.fixed_seed must be a signed 32-bit integer")
    if "fixed_timestep" in value:
        timestep = value["fixed_timestep"]
        if not isinstance(timestep, (int, float)) or isinstance(timestep, bool) or timestep <= 0:
            issues.append(f"{path}.fixed_timestep must be a positive number")


def _validate_temporal_contract(value: Any, data: dict[str, Any], processing: Any, issues: list[str]) -> None:
    path = "$.temporal"
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return
    allowed = {"reset", "warmup_frames"}
    for key in value.keys() - allowed:
        issues.append(f"{path}.{key} is not supported")
    reset = value.get("reset")
    if not isinstance(reset, dict):
        issues.append(f"{path}.reset must be an object")
    else:
        reset_allowed = {"strategy", "parameter", "clears", "on_resolution_change", "on_input_change"}
        for key in reset.keys() - reset_allowed:
            issues.append(f"{path}.reset.{key} is not supported")
        for key in {"strategy", "clears", "on_resolution_change", "on_input_change"}:
            if key not in reset:
                issues.append(f"{path}.reset.{key} is required")
        strategy = reset.get("strategy")
        if not isinstance(strategy, str) or strategy not in RESET_STRATEGIES:
            issues.append(f"{path}.reset.strategy must be one of {', '.join(sorted(RESET_STRATEGIES))}")
        clears = reset.get("clears")
        if not isinstance(clears, str) or clears not in RESET_TARGETS:
            issues.append(f"{path}.reset.clears must be one of {', '.join(sorted(RESET_TARGETS))}")
        for key in ("on_resolution_change", "on_input_change"):
            if key in reset and not isinstance(reset[key], bool):
                issues.append(f"{path}.reset.{key} must be boolean")
        parameter_id = reset.get("parameter")
        parameter_strategies = {"pulse_parameter": "pulse", "toggle_parameter": "toggle"}
        if isinstance(strategy, str) and strategy in parameter_strategies:
            parameter_map = {
                item.get("id"): item for item in data.get("parameters", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            } if isinstance(data.get("parameters"), list) else {}
            parameter = parameter_map.get(parameter_id) if isinstance(parameter_id, str) else None
            if parameter is None:
                issues.append(f"{path}.reset.parameter must reference an item in $.parameters")
            elif parameter.get("type") != parameter_strategies[strategy]:
                issues.append(
                    f"{path}.reset.parameter must reference a {parameter_strategies[strategy]} parameter "
                    f"for {strategy!r}"
                )
        elif "parameter" in reset:
            issues.append(f"{path}.reset.parameter is only supported for parameter reset strategies")

    warmup_frames = value.get("warmup_frames", 0)
    if not isinstance(warmup_frames, int) or isinstance(warmup_frames, bool) or not 0 <= warmup_frames <= 10000:
        issues.append(f"{path}.warmup_frames must be an integer from 0 to 10000")
    model = processing.get("model") if isinstance(processing, dict) else None
    history_frames = processing.get("history_frames", 0) if isinstance(processing, dict) else 0
    capabilities = processing.get("capabilities") if isinstance(processing, dict) else None
    if data.get("stateful") is not True:
        issues.append(f"{path} requires $.stateful to be true")
    if not isinstance(model, str) or model not in {"temporal", "simulation"}:
        issues.append(f"{path} requires a temporal or simulation processing model")
    if not isinstance(history_frames, int) or isinstance(history_frames, bool) or history_frames < 1:
        issues.append(f"{path} requires at least one processing history frame")
    if not isinstance(capabilities, list) or "history" not in capabilities:
        issues.append(f"{path} requires the processing history capability")
    if isinstance(reset, dict) and reset.get("clears") == "simulation_state" and model != "simulation":
        issues.append(f"{path}.reset.clears may be 'simulation_state' only for simulation models")


def _validate_provenance(value: Any, issues: list[str]) -> None:
    path = "$.provenance"
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return
    allowed = {"origin", "source", "changelog", "examples", "presets", "known_limitations"}
    for key in value.keys() - allowed:
        issues.append(f"{path}.{key} is not supported")
    for key in ("origin", "source"):
        if key not in value:
            issues.append(f"{path}.{key} is required")
    origin = value.get("origin")
    if not isinstance(origin, str) or origin not in PROVENANCE_ORIGINS:
        issues.append(f"{path}.origin must be one of {', '.join(sorted(PROVENANCE_ORIGINS))}")
    source = value.get("source")
    if not isinstance(source, dict):
        issues.append(f"{path}.source must be an object")
    else:
        source_allowed = {"type", "url", "revision", "author", "license"}
        for key in source.keys() - source_allowed:
            issues.append(f"{path}.source.{key} is not supported")
        source_type = source.get("type")
        if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
            issues.append(f"{path}.source.type must be one of {', '.join(sorted(SOURCE_TYPES))}")
        for key, maximum in (("url", 2048), ("revision", 200), ("author", 200), ("license", 100)):
            if key in source and (not isinstance(source[key], str) or not source[key].strip() or len(source[key]) > maximum):
                issues.append(f"{path}.source.{key} must be a non-empty string of at most {maximum} characters")
        source_url = source.get("url")
        if isinstance(source_url, str) and re.fullmatch(r"https?://[^\s]+", source_url) is None:
            issues.append(f"{path}.source.url must use http or https")
        if isinstance(origin, str) and origin in {"adapted", "ported", "third_party"} and not isinstance(source_url, str):
            issues.append(f"{path}.source.url is required when origin is {origin!r}")

    if "changelog" in value:
        _validate_relative_path(value["changelog"], f"{path}.changelog", issues)
    for key in ("examples", "presets"):
        paths = value.get(key)
        if paths is not None:
            if not isinstance(paths, list):
                issues.append(f"{path}.{key} must be an array")
            else:
                for index, relative_path in enumerate(paths):
                    _validate_relative_path(relative_path, f"{path}.{key}[{index}]", issues)
                if all(isinstance(item, str) for item in paths) and len(set(paths)) != len(paths):
                    issues.append(f"{path}.{key} must not contain duplicates")
    limitations = value.get("known_limitations")
    if limitations is not None:
        if (
            not isinstance(limitations, list)
            or any(not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in limitations)
        ):
            issues.append(f"{path}.known_limitations must be an array of non-empty strings up to 1000 characters")
        elif len(set(limitations)) != len(limitations):
            issues.append(f"{path}.known_limitations must not contain duplicates")


def validate_manifest_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]

    allowed_root = {
        "schema_version", "id", "name", "version", "fx_api", "kind", "category", "channel",
        "description", "publisher", "license", "entrypoints", "inputs", "outputs", "parameters",
        "compatibility", "permissions", "dependencies", "alpha_policy", "resolution_policy", "stateful", "tags",
        "processing", "image_contract", "determinism", "temporal", "provenance",
    }
    for key in data.keys() - allowed_root:
        issues.append(f"$.{key} is not supported")
    optional_root = {"processing", "image_contract", "determinism", "temporal", "provenance"}
    for key in allowed_root - optional_root:
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
    if not isinstance(kind, str) or kind not in KINDS:
        issues.append(f"$.kind must be one of {', '.join(sorted(KINDS))}")
    channel = data.get("channel")
    if not isinstance(channel, str) or channel not in CHANNELS:
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
                allowed = {"id", "family", "required", "semantic", "role", "description"}
                for key in port.keys() - allowed:
                    issues.append(f"{path}.{key} is not supported")
                if not isinstance(port.get("family"), str) or port["family"] not in {"TOP", "CHOP", "SOP", "DAT"}:
                    issues.append(f"{path}.family is invalid")
                if "required" in port and not isinstance(port["required"], bool):
                    issues.append(f"{path}.required must be boolean")
                for key, maximum in (("semantic", 80), ("description", 500)):
                    if key in port and not isinstance(port[key], str):
                        issues.append(f"{path}.{key} must be a string")
                    elif key in port and len(port[key]) > maximum:
                        issues.append(f"{path}.{key} must be at most {maximum} characters")
                role = port.get("role")
                supported_roles = INPUT_ROLES if collection_name == "inputs" else OUTPUT_ROLES
                if role is not None and (not isinstance(role, str) or role not in supported_roles):
                    issues.append(f"{path}.role must be one of {', '.join(sorted(supported_roles))}")
                family = port.get("family")
                if (
                    isinstance(role, str)
                    and role in (INPUT_ROLES | OUTPUT_ROLES) - {"audio", "control", "data"}
                    and family != "TOP"
                ):
                    issues.append(f"{path}.family must be TOP for role {role!r}")
                if role == "audio" and (not isinstance(family, str) or family not in {"TOP", "CHOP"}):
                    issues.append(f"{path}.family must be TOP or CHOP for role 'audio'")
                if role == "control" and (not isinstance(family, str) or family not in {"CHOP", "DAT"}):
                    issues.append(f"{path}.family must be CHOP or DAT for role 'control'")

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
            if not isinstance(parameter.get("type"), str) or parameter["type"] not in parameter_types:
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

    processing = data.get("processing")
    if processing is not None:
        if not isinstance(processing, dict):
            issues.append("$.processing must be an object")
        else:
            allowed_processing = {
                "model", "gpu_cost", "capabilities", "passes", "history_frames", "state_pass", "render_pass",
                "pass_scale", "iterations", "quality_tiers",
            }
            for key in processing.keys() - allowed_processing:
                issues.append(f"$.processing.{key} is not supported")
            model = processing.get("model")
            if not isinstance(model, str) or model not in PROCESSING_MODELS:
                issues.append(f"$.processing.model must be one of {', '.join(sorted(PROCESSING_MODELS))}")
            gpu_cost = processing.get("gpu_cost")
            if not isinstance(gpu_cost, str) or gpu_cost not in GPU_COSTS:
                issues.append(f"$.processing.gpu_cost must be one of {', '.join(sorted(GPU_COSTS))}")
            capabilities = processing.get("capabilities")
            if not isinstance(capabilities, list):
                issues.append("$.processing.capabilities must be an array")
            elif not all(isinstance(item, str) and item in CAPABILITIES for item in capabilities):
                issues.append(f"$.processing.capabilities items must be one of {', '.join(sorted(CAPABILITIES))}")
            elif len(set(capabilities)) != len(capabilities):
                issues.append("$.processing.capabilities must not contain duplicates")

            passes = processing.get("passes")
            if passes is not None:
                if not isinstance(passes, list) or not passes:
                    issues.append("$.processing.passes must be a non-empty array")
                else:
                    for index, relative_path in enumerate(passes):
                        try:
                            validate_package_path(relative_path, label=f"$.processing.passes[{index}]")
                        except SecurityError as exc:
                            issues.append(str(exc))
                    if all(isinstance(item, str) for item in passes) and len(set(passes)) != len(passes):
                        issues.append("$.processing.passes must not contain duplicates")
                    shader_entrypoint = entrypoints.get("shader") if isinstance(entrypoints, dict) else None
                    if shader_entrypoint is not None and passes[0] != shader_entrypoint:
                        issues.append("$.processing.passes[0] must match $.entrypoints.shader")
            if model == "multi_pass" and (not isinstance(passes, list) or len(passes) < 2):
                issues.append("$.processing.passes must contain at least two shaders for multi_pass")

            state_pass = processing.get("state_pass")
            render_pass = processing.get("render_pass")
            if (state_pass is None) != (render_pass is None):
                issues.append("$.processing.state_pass and render_pass must be declared together")
            if state_pass is not None and render_pass is not None:
                _validate_relative_path(state_pass, "$.processing.state_pass", issues)
                _validate_relative_path(render_pass, "$.processing.render_pass", issues)
                if state_pass == render_pass:
                    issues.append("$.processing.state_pass and render_pass must be distinct")
                if not isinstance(model, str) or model not in {"temporal", "simulation"}:
                    issues.append("$.processing state/render passes require a temporal or simulation model")
                if not isinstance(capabilities, list) or "history" not in capabilities:
                    issues.append("$.processing state/render passes require the history capability")
                if isinstance(passes, list) and all(isinstance(item, str) for item in passes):
                    if state_pass not in passes:
                        issues.append("$.processing.state_pass must appear in $.processing.passes")
                    if render_pass not in passes:
                        issues.append("$.processing.render_pass must appear in $.processing.passes")
                    if state_pass in passes and render_pass in passes and passes.index(state_pass) >= passes.index(render_pass):
                        issues.append("$.processing.state_pass must precede render_pass")

            if "pass_scale" in processing:
                pass_scale = processing["pass_scale"]
                if (
                    not isinstance(pass_scale, (int, float))
                    or isinstance(pass_scale, bool)
                    or not 0.0625 <= pass_scale <= 4.0
                ):
                    issues.append("$.processing.pass_scale must be a number from 0.0625 to 4")
            if "iterations" in processing:
                iterations = processing["iterations"]
                if not isinstance(iterations, int) or isinstance(iterations, bool) or not 1 <= iterations <= 1024:
                    issues.append("$.processing.iterations must be an integer from 1 to 1024")
            quality_tiers = processing.get("quality_tiers")
            if quality_tiers is not None:
                if not isinstance(quality_tiers, list) or not 1 <= len(quality_tiers) <= 16:
                    issues.append("$.processing.quality_tiers must contain from 1 to 16 tiers")
                else:
                    tier_ids: set[str] = set()
                    default_count = 0
                    for index, tier in enumerate(quality_tiers):
                        path = f"$.processing.quality_tiers[{index}]"
                        if not isinstance(tier, dict):
                            issues.append(f"{path} must be an object")
                            continue
                        tier_allowed = {"id", "label", "pass_scale", "iterations", "default"}
                        for key in tier.keys() - tier_allowed:
                            issues.append(f"{path}.{key} is not supported")
                        for key in ("id", "label", "pass_scale", "iterations"):
                            if key not in tier:
                                issues.append(f"{path}.{key} is required")
                        tier_id = tier.get("id")
                        if not isinstance(tier_id, str) or IDENTIFIER_RE.fullmatch(tier_id) is None:
                            issues.append(f"{path}.id must match {IDENTIFIER_RE.pattern}")
                        elif tier_id in tier_ids:
                            issues.append(f"{path}.id duplicates {tier_id!r}")
                        else:
                            tier_ids.add(tier_id)
                        label = tier.get("label")
                        if not isinstance(label, str) or not label.strip() or len(label) > 120:
                            issues.append(f"{path}.label must be a non-empty string of at most 120 characters")
                        tier_scale = tier.get("pass_scale")
                        if (
                            not isinstance(tier_scale, (int, float))
                            or isinstance(tier_scale, bool)
                            or not 0.0625 <= tier_scale <= 4.0
                        ):
                            issues.append(f"{path}.pass_scale must be a number from 0.0625 to 4")
                        tier_iterations = tier.get("iterations")
                        if (
                            not isinstance(tier_iterations, int)
                            or isinstance(tier_iterations, bool)
                            or not 1 <= tier_iterations <= 1024
                        ):
                            issues.append(f"{path}.iterations must be an integer from 1 to 1024")
                        if "default" in tier and not isinstance(tier["default"], bool):
                            issues.append(f"{path}.default must be boolean")
                        elif tier.get("default") is True:
                            default_count += 1
                    if default_count != 1:
                        issues.append("$.processing.quality_tiers must define exactly one default tier")

            history_frames = processing.get("history_frames", 0)
            valid_history_frames = (
                isinstance(history_frames, int)
                and not isinstance(history_frames, bool)
                and 0 <= history_frames <= 64
            )
            if not valid_history_frames:
                issues.append("$.processing.history_frames must be an integer from 0 to 64")
            elif isinstance(model, str) and model in {"temporal", "simulation"} and history_frames < 1:
                issues.append("$.processing.history_frames must be at least 1 for temporal or simulation models")
            if (
                valid_history_frames
                and isinstance(capabilities, list)
                and "history" in capabilities
                and history_frames < 1
            ):
                issues.append("$.processing.history_frames must be at least 1 when history is required")

            capability_requirements = {
                "second_image": "second_input",
                "auxiliary_image": "second_input",
                "transition_image": "transition",
                "depth": "depth",
                "normal": "normal",
                "flow": "flow",
                "displacement": "displacement",
                "audio": "audio",
            }
            if isinstance(capabilities, list):
                for index, port in enumerate(data.get("inputs", [])):
                    if not isinstance(port, dict):
                        continue
                    role = port.get("role")
                    required_capability = capability_requirements.get(role) if isinstance(role, str) else None
                    if required_capability is not None and required_capability not in capabilities:
                        issues.append(
                            f"$.inputs[{index}].role {role!r} requires processing capability {required_capability!r}"
                        )

    alpha_policy = data.get("alpha_policy")
    if not isinstance(alpha_policy, str) or alpha_policy not in {"preserve", "process", "blend", "replace", "force_opaque", "premultiply", "unpremultiply", "configurable"}:
        issues.append("$.alpha_policy has an unsupported value")
    resolution_policy = data.get("resolution_policy")
    if not isinstance(resolution_policy, str) or resolution_policy not in {"input", "first_input", "fixed", "scale", "custom", "dynamic"}:
        issues.append("$.resolution_policy has an unsupported value")
    if not isinstance(data.get("stateful"), bool):
        issues.append("$.stateful must be boolean")

    if "image_contract" in data:
        _validate_image_contract(data["image_contract"], alpha_policy, issues)
    if "determinism" in data:
        _validate_determinism(data["determinism"], parameters, issues)
    if "temporal" in data:
        _validate_temporal_contract(data["temporal"], data, processing, issues)
    if "provenance" in data:
        _validate_provenance(data["provenance"], issues)

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
    processing: dict[str, Any]
    image_contract: dict[str, Any]
    determinism: dict[str, Any]
    temporal: dict[str, Any]
    provenance: dict[str, Any]
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
            processing=dict(data.get("processing") or {
                "model": "single_pass",
                "gpu_cost": "low",
                "capabilities": [],
                "history_frames": 0,
            }),
            image_contract=dict(data.get("image_contract") or {}),
            determinism=dict(data.get("determinism") or {}),
            temporal=dict(data.get("temporal") or {}),
            provenance=dict(data.get("provenance") or {}),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


def load_manifest(path: str | Path) -> PackageManifest:
    return PackageManifest.from_data(load_json(path))
