"""Build the native TD ImageFX .toe and .tox assets inside TouchDesigner.

Run from TouchDesigner's Textport:

    import sys
    from pathlib import Path
    script = r"C:/path/to/video-effects/touchdesigner/scripts/build_project.py"
    source_root = str(Path(script).resolve().parents[2] / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    exec(compile(open(script, encoding="utf-8").read(), script, "exec"),
         {"__file__": script, "__name__": "__main__"})

Before rebuilding, run ``python tools/verify_repository.py`` from the checkout
to validate source files, manifests, feeds, entrypoints, and version metadata.

Run it from a blank TouchDesigner project. The script refuses to save a native
library project when unrelated top-level operators are present, and only creates
or updates ``/project1/td_imagefx`` and ``/project1/imagefx_demo``. Package source
files remain text-first on disk.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import statistics
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "packages"
CORE_ROOT = PROJECT_ROOT / "touchdesigner" / "core"
BUILD_ROOT = PROJECT_ROOT / "build"
DOCS_ROOT = PROJECT_ROOT / "docs"
PREVIEW_ROOT = DOCS_ROOT / "gallery"
PROJECT_PATH = PROJECT_ROOT / "TD_ImageFX_Library.toe"
BUILDER_PATH = Path(__file__).resolve()
LIBRARY_VERSION = "0.3.0"
RACK_SLOT_COUNT = 8
OWNED_PROJECT_NODES = frozenset({"td_imagefx", "imagefx_demo"})
DEFAULT_TEMPLATE_NODES = {
    "geo1": "geo",
    "out1": "out",
    "noise1": "noise",
    "chopto1": "chopto",
    "displace1": "displace",
    "moviefilein1": "moviefilein",
}

RACK_AUXILIARY_INPUTS = (
    ("image_b", "Second Image"),
    ("displacement", "Displacement"),
    ("depth", "Depth"),
    ("normal", "Normal"),
    ("flow", "Flow"),
    ("mask", "Mask"),
)

_AUXILIARY_ROLE_ALIASES = {
    "image_b": "image_b",
    "second_image": "image_b",
    "second_input": "image_b",
    "auxiliary_image": "image_b",
    "transition_image": "image_b",
    "transition": "image_b",
    "displacement": "displacement",
    "displacement_map": "displacement",
    "depth": "depth",
    "depth_map": "depth",
    "normal": "normal",
    "normal_map": "normal",
    "normals": "normal",
    "flow": "flow",
    "optical_flow": "flow",
    "motion": "flow",
    "motion_vectors": "flow",
    "mask": "mask",
    "matte": "mask",
}

RESET_CALLBACK_SOURCE = r'''"""Reset callbacks generated for a stateful ImageFX component."""


def _reset(component):
    for operator_name in component.fetch("tdimagefx_history_nodes", []):
        operator = component.op(operator_name)
        if operator is None:
            continue
        reset_pulse = operator.par["resetpulse"]
        if reset_pulse is not None:
            reset_pulse.pulse()
            continue
        reset = operator.par["reset"]
        if reset is not None:
            try:
                reset.pulse()
            except Exception:
                reset.val = True
                run("args[0].val = False", reset, delayFrames=1)
    return


def onPulse(par):
    if par.name == "Reset":
        _reset(par.owner)
    return


def onValueChange(par, prev):
    if par.name == "Reset" and bool(par.eval()):
        _reset(par.owner)
    return


def onValuesChanged(changes):
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
'''

PREVIEW_PARAMETER_OVERRIDES = {
    "tdimagefx.color.color-decision-list": {
        "Slopex": 1.25,
        "Offsety": 0.08,
        "Powerz": 0.82,
        "Saturation": 1.3,
    },
    "tdimagefx.color.curves": {
        "Shadowsx": 0.22,
        "Highlightsz": 0.86,
        "Preserveluma": 0.35,
    },
    "tdimagefx.color.channel-mixer": {"Redfromgreen": 0.35, "Bluefromred": 0.25},
    "tdimagefx.color.exposure": {"Exposure": 0.75, "Contrast": 1.15},
    "tdimagefx.color.hsv-shift": {"Hue": 0.18, "Saturation": 1.25},
    "tdimagefx.color.levels": {"Inputblack": 0.08, "Gamma": 0.78},
    "tdimagefx.color.lift-gamma-gain": {"Liftr": 0.08, "Gammag": 0.82, "Gainb": 1.2},
    "tdimagefx.color.temperature-tint": {"Temperature": 0.35, "Tint": -0.2},
    "tdimagefx.composite.alpha-composite": {"Opacity": 0.62},
    "tdimagefx.composite.channel-shuffle": {"Order": 3.0, "Alphafromluma": True},
    "tdimagefx.composite.edge-extend": {"Radius": 8.0, "Threshold": 0.2},
    "tdimagefx.matte.alpha-repair": {"Mode": 1.0},
    "tdimagefx.matte.dilate": {"Radius": 7.0},
    "tdimagefx.temporal.frame-blend": {"History": 0.82},
    "tdimagefx.temporal.stutter": {"Hold": 1.0},
    "tdimagefx.temporal.time-displacement": {"Amount": 1.0, "Phase": 0.72},
    "tdimagefx.temporal.feedback-trails": {"Offsetx": 0.018, "Offsety": -0.012},
    "tdimagefx.temporal.feedback-rotate": {"Angle": 0.22, "Scale": 0.94},
    "tdimagefx.transform.corner-pin": {
        "Bottomleftx": 0.08,
        "Bottomlefty": 0.1,
        "Bottomrightx": 0.94,
        "Toprighty": 0.88,
        "Topleftx": -0.04,
    },
    "tdimagefx.transform.crop-feather": {
        "Left": 0.12,
        "Right": 0.9,
        "Bottom": 0.1,
        "Top": 0.88,
        "Feather": 0.08,
    },
    "tdimagefx.transform.fit-fill": {
        "Frameaspect": 1.0,
        "Mode": 1.0,
        "Alignmentx": 0.35,
        "Alignmenty": 0.65,
    },
    "tdimagefx.transform.perspective-warp": {
        "Tiltx": 0.38,
        "Tilty": -0.22,
        "Perspective": 1.5,
        "Zoom": 0.86,
    },
    "tdimagefx.transform.transform-2d": {
        "Translatex": 0.11,
        "Translatey": -0.08,
        "Scalex": 0.88,
        "Scaley": 1.12,
        "Rotation": 0.28,
    },
}

PREVIEW_SOURCE_SHADER = r"""
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec3 phase = vec3(0.0, 2.1, 4.2);
    vec3 color = 0.5 + 0.5 * cos(6.28318530718 * (uv.x + 0.35 * uv.y) + phase);
    float checker = mod(floor(uv.x * 12.0) + floor(uv.y * 8.0), 2.0);
    color = mix(color, color.bgr, checker * 0.32);
    float ring = 1.0 - smoothstep(0.012, 0.025, abs(length(uv - 0.5) - 0.27));
    color = mix(color, vec3(1.0, 0.92, 0.35), ring * 0.85);
    float disk = 1.0 - smoothstep(0.34, 0.37, length(uv - 0.5));
    float alphaGrid = mix(0.18, 0.72, checker);
    float alpha = max(disk, alphaGrid * (1.0 - ring));
    fragColor = TDOutputSwizzle(vec4(color, alpha));
}
""".strip()

PREVIEW_IDENTITY_LUT_SHADER = r"""
layout(location = 0) out vec4 fragColor;
void main() {
    const float size = 32.0;
    float column = clamp(floor(vUV.x * size * size), 0.0, size * size - 1.0);
    float red = mod(column, size);
    float blue = floor(column / size);
    float green = clamp(floor(vUV.y * size), 0.0, size - 1.0);
    fragColor = TDOutputSwizzle(vec4(vec3(red, green, blue) / (size - 1.0), 1.0));
}
""".strip()

PREVIEW_HELD_FRAME_SHADER = r"""
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = clamp((vUV.st - 0.5) * 1.06 + 0.5 + vec2(0.045, -0.025), 0.0, 1.0);
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 held = mix(src.rgb, src.gbr, 0.22);
    fragColor = TDOutputSwizzle(vec4(held, src.a));
}
""".strip()

SOURCE_ROOT = (PROJECT_ROOT / "src").resolve()
if not SOURCE_ROOT.is_dir():
    raise RuntimeError("TD ImageFX source tree is missing: {}".format(SOURCE_ROOT))
_source_root_text = str(SOURCE_ROOT)
if not any(str(item).casefold() == _source_root_text.casefold() for item in sys.path):
    sys.path.insert(0, _source_root_text)

from tdimagefx import Version
from tdimagefx.manifest import load_manifest as _load_validated_manifest
from tdimagefx.paths import validate_package_path


def _read_text(path):
    return Path(path).read_text(encoding="utf-8")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_sort_key(manifest):
    return (manifest.get("category", ""), manifest.get("name", ""), manifest.get("version", ""))


def _is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _manifest_asset(manifest, relative_path, label, must_exist=True):
    """Resolve one validated package-relative asset without following it outside the package."""
    safe_path = validate_package_path(relative_path, label=label)
    package_root = manifest["_path"].parent.resolve(strict=True)
    candidate = package_root.joinpath(*PurePosixPath(safe_path).parts)
    if candidate.is_symlink():
        raise RuntimeError("{} may not be a symbolic link: {}".format(label, relative_path))
    if candidate.exists():
        resolved = candidate.resolve(strict=True)
        if not _is_within(resolved, package_root) or not resolved.is_file():
            raise RuntimeError("{} is not a regular file inside the package: {}".format(label, relative_path))
        return resolved
    if must_exist:
        raise RuntimeError("{} does not exist: {}".format(label, relative_path))
    existing_parent = candidate.parent
    while not existing_parent.exists():
        existing_parent = existing_parent.parent
    resolved_parent = existing_parent.resolve(strict=True)
    if not _is_within(resolved_parent, package_root):
        raise RuntimeError("{} escapes package root: {}".format(label, relative_path))
    return candidate


def load_manifests():
    latest = {}
    package_root = PACKAGE_ROOT.resolve(strict=True)
    identities = set()
    for manifest_path in sorted(PACKAGE_ROOT.glob("*/**/package.json")):
        relative_parts = manifest_path.relative_to(PACKAGE_ROOT).parts
        resolved_manifest = manifest_path.resolve(strict=True)
        if not _is_within(resolved_manifest, package_root):
            raise RuntimeError("Manifest escapes package root: {}".format(manifest_path))
        model = _load_validated_manifest(resolved_manifest)
        manifest = model.to_dict()
        expected_parts = (manifest["id"], manifest["version"], "package.json")
        if relative_parts != expected_parts:
            raise RuntimeError(
                "Manifest layout must be packages/<id>/<version>/package.json: {}".format(manifest_path)
            )
        identity = (manifest["id"], manifest["version"])
        if identity in identities:
            raise RuntimeError("Duplicate package identity: {}@{}".format(*identity))
        identities.add(identity)
        manifest["_path"] = resolved_manifest
        _manifest_asset(manifest, manifest["entrypoints"]["shader"], "$.entrypoints.shader")
        native_plugin = manifest["entrypoints"].get("native_plugin")
        if native_plugin:
            _manifest_asset(manifest, native_plugin, "$.entrypoints.native_plugin")
        processing = manifest.get("processing") or {}
        for pass_index, pass_path in enumerate(processing.get("passes") or []):
            _manifest_asset(manifest, pass_path, "$.processing.passes[{}]".format(pass_index))
        version = Version.parse(manifest["version"])
        current = latest.get(manifest["id"])
        if current is not None and version == current[0] and not version.exactly_equals(current[0]):
            raise RuntimeError(
                "Ambiguous versions with equal SemVer precedence for {}: {} and {}".format(
                    manifest["id"], current[0], version
                )
            )
        if current is None or current[0] < version:
            latest[manifest["id"]] = (version, manifest)
    return sorted((item[1] for item in latest.values()), key=_manifest_sort_key)


def _safe_name(value):
    return re.sub(r"[^A-Za-z0-9_]", "_", str(value))


def _normalized_input_role(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _rack_input_role(input_definition, input_index):
    """Return the rack bus used by a declared non-primary package input."""
    if input_index == 0:
        return "image"
    if not isinstance(input_definition, dict):
        raise RuntimeError("Effect input definitions must be objects")
    candidates = (
        input_definition.get("role"),
        input_definition.get("semantic"),
        input_definition.get("id"),
    )
    for candidate in candidates:
        role = _AUXILIARY_ROLE_ALIASES.get(_normalized_input_role(candidate))
        if role is not None:
            return role
    raise RuntimeError(
        "Unsupported auxiliary TOP input {!r}; use one of: {}".format(
            input_definition.get("semantic") or input_definition.get("id"),
            ", ".join(role for role, _label in RACK_AUXILIARY_INPUTS),
        )
    )


def _rack_input_name(role):
    roles = ["image", *[item[0] for item in RACK_AUXILIARY_INPUTS]]
    try:
        index = roles.index(role) + 1
    except ValueError as exc:
        raise RuntimeError("Unknown rack input role: {}".format(role)) from exc
    return "in{}_{}".format(index, role)


def _history_frame_count(processing):
    """Normalize a stateful effect's retained history-frame count."""
    count = processing.get("history_frames", 0)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 64:
        raise RuntimeError("processing.history_frames must be an integer from 0 to 64")
    if processing.get("model") in {"temporal", "simulation"} and count < 1:
        raise RuntimeError("Temporal and simulation effects require at least one history frame")
    return count


def _preview_state_iterations(processing, temporal):
    """Choose enough deterministic state iterations to illustrate retained history."""
    history_frames = _history_frame_count(processing)
    if history_frames == 0:
        return 1
    declared = temporal.get("warmup_frames", 0) if isinstance(temporal, dict) else 0
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise RuntimeError("temporal.warmup_frames must be a non-negative integer")
    return min(64, max(8, history_frames, declared))


def _state_render_passes(processing, pass_paths):
    """Validate and return the optional private-state/render pass pair."""
    state_pass = processing.get("state_pass")
    render_pass = processing.get("render_pass")
    if state_pass is None and render_pass is None:
        return None, None
    if not isinstance(state_pass, str) or not isinstance(render_pass, str):
        raise RuntimeError("processing.state_pass and render_pass must be declared together")
    if state_pass == render_pass:
        raise RuntimeError("processing.state_pass and render_pass must be distinct")
    try:
        state_index = pass_paths.index(state_pass)
        render_index = pass_paths.index(render_pass)
    except ValueError as exc:
        raise RuntimeError("State and render passes must occur in processing.passes") from exc
    if state_index >= render_index:
        raise RuntimeError("processing.state_pass must precede render_pass")
    if processing.get("model") not in {"temporal", "simulation"}:
        raise RuntimeError("State/render passes require temporal or simulation processing")
    return state_pass, render_pass


def _reset_parameter_type(manifest):
    definitions = [
        definition for definition in manifest.get("parameters", [])
        if definition.get("name") == "Reset"
    ]
    if not definitions:
        return "pulse"
    reset_type = definitions[0].get("type")
    if reset_type not in {"pulse", "toggle"}:
        raise RuntimeError("A stateful Reset parameter must be a pulse or toggle")
    return reset_type


def _set_par_defaults(par, definition):
    if "default" in definition:
        try:
            par.default = definition["default"]
        except Exception:
            pass
        par.val = definition["default"]
    if "min" in definition:
        par.min = definition["min"]
        par.normMin = definition.get("norm_min", definition["min"])
        par.clampMin = definition.get("clamp_min", True)
    elif "norm_min" in definition:
        par.normMin = definition["norm_min"]
        par.clampMin = definition.get("clamp_min", False)
    if "max" in definition:
        par.max = definition["max"]
        par.normMax = definition.get("norm_max", definition["max"])
        par.clampMax = definition.get("clamp_max", True)
    elif "norm_max" in definition:
        par.normMax = definition["norm_max"]
        par.clampMax = definition.get("clamp_max", False)


def _parameter_help(definition):
    """Build compact TouchDesigner help text from the manifest contract."""
    parts = []
    description = str(definition.get("description", "")).strip()
    if description:
        parts.append(description)
    unit = str(definition.get("unit", "")).strip()
    if unit:
        parts.append("Unit: {}.".format(unit))
    choices = definition.get("choices") or []
    if choices:
        parts.append(
            "Choices: {}.".format(
                ", ".join("{} ({})".format(item["label"], item["value"]) for item in choices)
            )
        )
    parts.append("Animatable." if definition.get("animatable", True) else "Constant control; animation is not supported by this effect contract.")
    return " ".join(parts)


def _parameter_metadata(definition):
    """Return the serializable parameter metadata retained on generated COMPs."""
    return {
        "id": definition.get("id", definition["name"]),
        "name": definition["name"],
        "label": definition.get("label", definition["name"]),
        "page": definition.get("page", "ImageFX"),
        "type": definition.get("type", "float"),
        "unit": definition.get("unit", ""),
        "description": definition.get("description", ""),
        "animatable": bool(definition.get("animatable", True)),
        "choices": [dict(item) for item in definition.get("choices", [])],
        "minimum": definition.get("min"),
        "maximum": definition.get("max"),
        "normal_minimum": definition.get("norm_min", definition.get("min")),
        "normal_maximum": definition.get("norm_max", definition.get("max")),
        "clamp_minimum": definition.get("clamp_min", "min" in definition),
        "clamp_maximum": definition.get("clamp_max", "max" in definition),
    }


def _apply_parameter_metadata(comp, pars, definition):
    help_text = _parameter_help(definition)
    label = definition.get("label", definition["name"])
    for par in pars:
        try:
            par.help = help_text
        except Exception:
            pass
        try:
            par.label = label
        except Exception:
            pass
    try:
        metadata = dict(comp.fetch("tdimagefx_parameter_metadata", {}))
        metadata[definition["name"]] = _parameter_metadata(definition)
        comp.store("tdimagefx_parameter_metadata", metadata)
    except Exception:
        pass
    return pars


def _append_parameter(comp, page, definition):
    name = definition["name"]
    label = definition.get("label", name)
    par_type = definition.get("type", "float")
    if par_type == "toggle":
        page.appendToggle(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return _apply_parameter_metadata(comp, [par], definition)
    if par_type == "pulse":
        page.appendPulse(name, label=label)
        return _apply_parameter_metadata(comp, [comp.par[name]], definition)
    if par_type == "string":
        page.appendStr(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return _apply_parameter_metadata(comp, [par], definition)
    if par_type == "menu":
        page.appendMenu(name, label=label)
        par = comp.par[name]
        choices = definition.get("choices") or []
        menu_names = list(definition.get("menu_names", []))
        menu_labels = list(definition.get("menu_labels", menu_names))
        if choices:
            menu_names = [str(item["value"]) for item in choices]
            menu_labels = [str(item["label"]) for item in choices]
        par.menuNames = menu_names
        par.menuLabels = menu_labels
        normalized = dict(definition)
        if choices and "default" in normalized:
            normalized["default"] = str(normalized["default"])
        _set_par_defaults(par, normalized)
        return _apply_parameter_metadata(comp, [par], definition)
    if par_type in {"rgb", "rgba"}:
        getattr(page, "append{}".format(par_type.upper()))(name, label=label)
        suffixes = "rgb" if par_type == "rgb" else "rgba"
        pars = [comp.par[name + suffix] for suffix in suffixes]
        defaults = list(definition.get("default", [0.0] * len(suffixes)))
        if par_type == "rgba" and len(defaults) < 4:
            defaults.append(1.0)
        for index, par in enumerate(pars):
            _set_par_defaults(par, {"default": defaults[index], "min": 0.0, "max": 1.0})
        return _apply_parameter_metadata(comp, pars, definition)
    if par_type in {"xy", "xyz", "uv"}:
        method = {"xy": "appendXY", "xyz": "appendXYZ", "uv": "appendUV"}[par_type]
        getattr(page, method)(name, label=label)
        suffixes = tuple(par_type)
        pars = [comp.par[name + suffix] for suffix in suffixes]
        defaults = list(definition.get("default", [0.0] * len(suffixes)))
        for index, par in enumerate(pars):
            item = dict(definition)
            item["default"] = defaults[index]
            _set_par_defaults(par, item)
        return _apply_parameter_metadata(comp, pars, definition)
    if par_type == "int":
        page.appendInt(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return _apply_parameter_metadata(comp, [par], definition)
    if par_type in {"file", "folder", "operator"}:
        method = {"file": "appendFile", "folder": "appendFolder", "operator": "appendOP"}[par_type]
        getattr(page, method)(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return _apply_parameter_metadata(comp, [par], definition)
    page.appendFloat(name, label=label)
    par = comp.par[name]
    _set_par_defaults(par, definition)
    return _apply_parameter_metadata(comp, [par], definition)


def _append_system_parameters(comp, manifest):
    page = comp.appendCustomPage("Package")
    definitions = []
    processing = _processing(manifest)
    parameter_names = {definition.get("name") for definition in manifest.get("parameters", [])}
    if any(definition.get("name") == "Time" for definition in manifest.get("parameters", [])):
        definitions.append(
            {"name": "Timescale", "label": "Time Scale", "type": "float", "default": 1.0, "min": -10.0, "max": 10.0}
        )
    history_frames = _history_frame_count(processing)
    if history_frames:
        _reset_parameter_type(manifest)
    if history_frames and "Reset" not in parameter_names:
        definitions.append(
            {"name": "Reset", "label": "Reset State", "type": "pulse"}
        )
    definitions.extend((
        {"name": "Packageid", "label": "Package ID", "type": "string", "default": manifest["id"]},
        {"name": "Packageversion", "label": "Package Version", "type": "string", "default": manifest["version"]},
        {"name": "Fxapi", "label": "FX API", "type": "string", "default": manifest.get("fx_api", "1.0")},
        {"name": "Processingmodel", "label": "Processing Model", "type": "string", "default": (manifest.get("processing") or {}).get("model", "single_pass")},
        {"name": "Historyframes", "label": "History Frames", "type": "int", "default": processing["history_frames"], "min": 0, "max": 64},
        {"name": "Gpucost", "label": "GPU Cost", "type": "string", "default": (manifest.get("processing") or {}).get("gpu_cost", "low")},
        {"name": "Capabilities", "type": "string", "default": ", ".join((manifest.get("processing") or {}).get("capabilities", []))},
        {"name": "Status", "type": "string", "default": "Ready"},
    ))
    for definition in definitions:
        _append_parameter(comp, page, definition)


def _configure_glsl_uniform(glsl, definition, custom_pars, vector_index, color_index):
    uniform = definition.get("uniform")
    if not uniform:
        return vector_index, color_index
    if definition.get("type") in {"rgb", "rgba"}:
        glsl.par["color{}name".format(color_index)] = uniform
        suffixes = ("rgbr", "rgbg", "rgbb", "alpha")
        for shader_suffix, custom_par in zip(suffixes, custom_pars):
            target = glsl.par["color{}{}".format(color_index, shader_suffix)]
            target.expr = "parent().par.{}".format(custom_par.name)
        return vector_index, color_index + 1
    glsl.par["vec{}name".format(vector_index)] = uniform
    axes = ("x", "y", "z", "w")
    for axis, custom_par in zip(axes, custom_pars):
        target = glsl.par["vec{}value{}".format(vector_index, axis)]
        target.expr = "parent().par.{}".format(custom_par.name)
    return vector_index + 1, color_index


def configure_extension(comp, class_name, source_path):
    code_dat = comp.create(textDAT, class_name)
    code_dat.text = _read_text(source_path)
    code_dat.nodeX = -200
    code_dat.nodeY = -300
    comp.par.ext0object = "op('./{}').module.{}(me)".format(class_name, class_name)
    comp.par.ext0name = class_name
    comp.par.ext0promote = True
    comp.par.initextonstart = True
    comp.par.reinitextensions.pulse()
    return code_dat


def configure_parameter_callbacks(owner_comp, source_path, parameters):
    """Create relocation-safe Parameter Execute callbacks for a component."""

    callbacks = owner_comp.create(parameterexecuteDAT, "parameter_callbacks")
    callbacks.text = _read_text(source_path)
    callbacks.par.op = callbacks.relativePath(owner_comp)
    callbacks.par.pars = parameters
    callbacks.par.valuechange = True
    callbacks.par.onpulse = True
    callbacks.par.custom = True
    callbacks.par.builtin = False
    return callbacks


def _repair_effect_shader_paths(root_comp):
    """Make packaged effect GLSL-to-DAT references portable across networks."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        name = str(getattr(operator, "name", ""))
        if str(getattr(operator, "type", "")) != "glsl" or not name.startswith(
            "effect_glsl_"
        ):
            continue
        shader_name = "pixel_shader_" + name[len("effect_glsl_"):]
        shader_dat = operator.parent().op(shader_name)
        parameter = operator.par["pixeldat"]
        if shader_dat is None or parameter is None:
            raise RuntimeError(
                "{} is missing its portable Pixel Shader DAT".format(operator.path)
            )
        parameter.val = operator.relativePath(shader_dat)
        if parameter.eval() != shader_dat:
            raise RuntimeError(
                "{} Pixel Shader reference did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _repair_effect_callback_paths(root_comp):
    """Repair legacy absolute reset callback targets in packaged effects."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "reset_callbacks":
            continue
        parameter = operator.par["op"]
        target = operator.parent()
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable reset callback target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} reset callback target did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def load_tox_component(parent_comp, tox_path, name):
    """Load a .tox as a direct child and return its top-level component."""
    before_ids = {child.id for child in parent_comp.children}
    parent_comp.loadTox(str(tox_path))
    created = [child for child in parent_comp.children if child.id not in before_ids]
    if len(created) != 1:
        raise RuntimeError(
            "Expected one top-level component from {}, found {}".format(tox_path, len(created))
        )
    instance = created[0]
    instance.name = name
    _repair_effect_shader_paths(instance)
    _repair_effect_callback_paths(instance)
    return instance


def _git_tracks_path(path):
    """Return True/False for Git tracking, or None when tracking is unknowable."""

    path = Path(path).resolve()
    try:
        relative_path = path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    if not (PROJECT_ROOT / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative_path.as_posix()],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError("Git could not determine whether this artifact is tracked: {}".format(path))


def _save_versioned_tox(effect, tox_path):
    """Create prepublication artifacts without rewriting tracked exact versions."""

    tox_path = Path(tox_path)
    tracking = _git_tracks_path(tox_path) if tox_path.exists() else False
    if tracking is True:
        return "preserved_published"
    if (
        tox_path.exists()
        and tracking is None
        and os.environ.get("TDIMAGEFX_ALLOW_UNTRACKED_TOX_OVERWRITE") != "1"
    ):
        raise RuntimeError(
            "Refusing to overwrite an existing versioned component outside a Git checkout: {}. "
            "Create a new package version, or set TDIMAGEFX_ALLOW_UNTRACKED_TOX_OVERWRITE=1 "
            "only for a known prepublication artifact.".format(tox_path)
    )
    action = "rebuilt_unpublished" if tox_path.exists() else "created"
    tox_path.parent.mkdir(parents=True, exist_ok=True)
    effect.save(str(tox_path), createFolders=True)
    return action


def _processing(manifest):
    value = dict(manifest.get("processing") or {})
    value.setdefault("model", "single_pass")
    value.setdefault("gpu_cost", "low")
    value.setdefault("capabilities", [])
    value.setdefault("passes", [manifest["entrypoints"]["shader"]])
    value.setdefault("history_frames", 0)
    return value


def _shader_pass(
    effect, manifest, pass_index, relative_path, inputs, parameter_bindings, node_key=None
):
    shader_path = _manifest_asset(
        manifest, relative_path, "$.processing.passes[{}]".format(pass_index)
    )
    shader_source = _read_text(shader_path)
    node_key = str(pass_index + 1) if node_key is None else str(node_key)
    shader_dat = effect.create(textDAT, "pixel_shader_{}".format(node_key))
    shader_dat.text = shader_source
    shader_dat.nodeX = pass_index * 230 - 100
    shader_dat.nodeY = -300

    glsl = effect.create(glslTOP, "effect_glsl_{}".format(node_key))
    glsl.nodeX = pass_index * 230
    glsl.nodeY = 0
    for input_index, input_node in enumerate(inputs):
        input_node.outputConnectors[0].connect(glsl.inputConnectors[input_index])
    glsl.par.pixeldat = glsl.relativePath(shader_dat)
    if glsl.par["glslversion"] is not None:
        glsl.par.glslversion = "glsl460"
    if glsl.par["compilebehavior"] is not None:
        glsl.par.compilebehavior = "stalluntildone"
    if glsl.par["errorbehavior"] is not None:
        glsl.par.errorbehavior = "showprevious"
    if glsl.par["outputresolution"] is not None:
        glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
        and re.search(r"\buniform\s+\w+\s+{}\s*;".format(re.escape(definition["uniform"])), shader_source)
    ]
    glsl.seq.vec.numBlocks = max(
        1, sum(1 for definition, _pars in active_bindings if definition.get("type") not in {"rgb", "rgba"})
    )
    glsl.seq.color.numBlocks = max(
        1, sum(1 for definition, _pars in active_bindings if definition.get("type") in {"rgb", "rgba"})
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        vector_index, color_index = _configure_glsl_uniform(
            glsl, definition, custom_pars, vector_index, color_index
        )

    info = effect.create(infoDAT, "shader_info_{}".format(node_key))
    info.par.op = info.relativePath(glsl)
    info.nodeX = pass_index * 230
    info.nodeY = -430
    return glsl


def _collect_shader_diagnostics(manifest, glsl_nodes, report):
    errors = []
    gpu_ms = 0.0
    for glsl in glsl_nodes:
        glsl.cook(force=True)
        try:
            errors.extend("{}: {}".format(glsl.name, error) for error in glsl.errors())
        except Exception:
            pass
        try:
            gpu_ms += max(0.0, float(glsl.gpuCookTime))
        except Exception:
            pass
    if errors:
        report["shader_errors"][manifest["id"]] = errors
    return gpu_ms


def build_effect(parent_comp, manifest, report):
    processing = _processing(manifest)
    component_name = _safe_name(manifest["id"])
    effect = parent_comp.create(baseCOMP, component_name)
    effect.nodeWidth = 200
    effect.nodeHeight = 120
    effect.color = {
        "single_pass": (0.18, 0.32, 0.46),
        "multi_pass": (0.32, 0.24, 0.50),
        "temporal": (0.46, 0.24, 0.30),
        "simulation": (0.46, 0.34, 0.14),
    }.get(processing["model"], (0.20, 0.30, 0.38))
    effect.comment = "{}\n{}\n{} · {} · {} GPU".format(
        manifest["name"], manifest["id"], manifest["version"], processing["model"], processing["gpu_cost"]
    )
    effect.store("tdimagefx_processing", processing)

    effect_pages = {"ImageFX": effect.appendCustomPage("ImageFX")}
    parameter_bindings = []
    for definition in manifest.get("parameters", []):
        page_name = str(definition.get("page") or "ImageFX").strip() or "ImageFX"
        if page_name == "Package":
            page_name = "ImageFX Package Controls"
        effect_page = effect_pages.get(page_name)
        if effect_page is None:
            effect_page = effect.appendCustomPage(page_name)
            effect_pages[page_name] = effect_page
        custom_pars = _append_parameter(effect, effect_page, definition)
        parameter_bindings.append((definition, custom_pars))
    _append_system_parameters(effect, manifest)

    input_nodes = []
    for input_index, input_definition in enumerate(manifest.get("inputs", []), start=1):
        input_node = effect.create(inTOP, "in{}_{}".format(input_index, _safe_name(input_definition["id"])))
        input_node.par.label = input_definition["id"]
        input_node.nodeX = -440
        input_node.nodeY = 180 - input_index * 120
        input_nodes.append(input_node)
    if not input_nodes:
        raise RuntimeError("{} does not declare a TOP input".format(manifest["id"]))

    time_par = effect.par["Time"]
    if time_par is not None:
        time_par.expr = "absTime.seconds * me.par.Timescale"

    history_frames = _history_frame_count(processing)
    history = None
    history_input = None
    history_nodes = []
    if history_frames:
        history_seed = effect.create(constantTOP, "history_seed")
        history_seed.nodeX = -440
        history_seed.nodeY = -140
        for channel in ("colorr", "colorg", "colorb", "colora"):
            if history_seed.par[channel] is not None:
                history_seed.par[channel] = 0.0
        if history_seed.par["outputresolution"] is not None:
            history_seed.par.outputresolution = "custom"
            history_seed.par.resolutionw = 1
            history_seed.par.resolutionh = 1
        history = effect.create(feedbackTOP, "history_feedback")
        history_seed.outputConnectors[0].connect(history.inputConnectors[0])
        history.nodeX = -210
        history.nodeY = -140
        if history.par["reset"] is not None:
            history.par.reset = False
        history_input = history
        history_nodes.append(history.name)

        # Feedback TOP supplies the previous state. When a package declares a
        # deeper history, retain exactly that many states on the GPU and expose
        # the oldest retained state through the existing single-history input.
        # This keeps the FX API 1.0 sampler layout compatible while honoring
        # the declared delay instead of silently collapsing every value to 1.
        if history_frames > 1:
            history_cache = effect.create(cacheTOP, "history_cache")
            history.outputConnectors[0].connect(history_cache.inputConnectors[0])
            history_cache.nodeX = -30
            history_cache.nodeY = -140
            if history_cache.par["active"] is not None:
                history_cache.par.active = True
            if history_cache.par["cachesize"] is not None:
                history_cache.par.cachesize = history_frames
            if history_cache.par["outputindex"] is not None:
                history_cache.par.outputindex = -(history_frames - 1)
            if history_cache.par["interp"] is not None:
                history_cache.par.interp = False
            history_input = history_cache
            history_nodes.append(history_cache.name)

        effect.store("tdimagefx_history_nodes", history_nodes)
        effect.store("tdimagefx_history_frames", history_frames)
        effect.store("tdimagefx_history_seed", history_seed.path)

    glsl_nodes = []
    previous = None
    pass_paths = list(processing.get("passes") or [manifest["entrypoints"]["shader"]])
    state_pass_path, render_pass_path = _state_render_passes(processing, pass_paths)
    state_pass_output = None
    render_pass_output = None
    for pass_index, relative_path in enumerate(pass_paths):
        if pass_index == 0:
            pass_inputs = list(input_nodes)
            if history_input is not None:
                pass_inputs = [input_nodes[0], history_input, *input_nodes[1:]]
        else:
            pass_inputs = [previous, input_nodes[0], *input_nodes[1:]]
            if history_input is not None and relative_path == state_pass_path:
                pass_inputs = [previous, input_nodes[0], history_input, *input_nodes[1:]]
        previous = _shader_pass(
            effect, manifest, pass_index, relative_path, pass_inputs, parameter_bindings
        )
        glsl_nodes.append(previous)
        if relative_path == state_pass_path:
            state_pass_output = previous
        if relative_path == render_pass_path:
            render_pass_output = previous

    processed_output = previous
    if history is not None:
        # Keep simulation state private. Explicit state/render packages feed
        # back the state pass and expose the render pass. Legacy one-pass
        # packages branch the same GLSL result into distinct state/render TOPs,
        # preserving their pixels while avoiding an output-as-feedback target.
        state_source = state_pass_output or previous
        display_source = render_pass_output or previous
        state_target = effect.create(nullTOP, "state_target")
        state_source.outputConnectors[0].connect(state_target.inputConnectors[0])
        state_target.nodeX = len(glsl_nodes) * 230
        state_target.nodeY = -100
        state_target.display = False
        state_target.render = False
        history.par.top = state_target.path

        render_output = effect.create(nullTOP, "render_output")
        display_source.outputConnectors[0].connect(render_output.inputConnectors[0])
        render_output.nodeX = len(glsl_nodes) * 230
        render_output.nodeY = 30
        render_output.display = False
        render_output.render = False
        processed_output = render_output
        effect.store("tdimagefx_state_target", state_target.path)
        effect.store("tdimagefx_render_output", render_output.path)

        reset_callbacks = effect.create(parameterexecuteDAT, "reset_callbacks")
        reset_callbacks.text = RESET_CALLBACK_SOURCE
        reset_callbacks.par.op = reset_callbacks.relativePath(effect)
        reset_callbacks.par.pars = "Reset"
        reset_type = _reset_parameter_type(manifest)
        reset_callbacks.par.onpulse = reset_type == "pulse"
        reset_callbacks.par.valuechange = reset_type == "toggle"
        reset_callbacks.par.custom = True
        reset_callbacks.par.builtin = False
        reset_callbacks.nodeX = state_target.nodeX
        reset_callbacks.nodeY = -300

    bypass_switch = effect.create(switchTOP, "enable_switch")
    input_nodes[0].outputConnectors[0].connect(bypass_switch.inputConnectors[0])
    processed_output.outputConnectors[0].connect(bypass_switch.inputConnectors[1])
    bypass_switch.par.index.expr = "1 if parent().par.Enable else 0"
    bypass_switch.nodeX = len(glsl_nodes) * 230 + 180
    bypass_switch.nodeY = 0

    output = effect.create(outTOP, "out1_image")
    bypass_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = bypass_switch.nodeX + 170
    output.nodeY = 0
    output.display = True
    output.render = True

    gpu_ms = _collect_shader_diagnostics(manifest, glsl_nodes, report)
    tox_path = _manifest_asset(
        manifest,
        manifest["entrypoints"]["touchdesigner_component"],
        "$.entrypoints.touchdesigner_component",
        must_exist=False,
    )
    tox_action = _save_versioned_tox(effect, tox_path)
    effect.par.externaltox = tox_path.relative_to(PROJECT_ROOT).as_posix()
    effect.par.enableexternaltox = True
    effect.par.savebackup = True
    if effect.par["relpath"] is not None:
        effect.par.relpath = "project"
    report["effects"].append({
        "id": manifest["id"],
        "version": manifest["version"],
        "tox": str(tox_path),
        "tox_action": tox_action,
        "model": processing["model"],
        "gpu_cost": processing["gpu_cost"],
        "capabilities": list(processing["capabilities"]),
        "passes": len(pass_paths),
        "history_frames": history_frames,
        "preview_state_iterations": _preview_state_iterations(
            processing, manifest.get("temporal", {})
        ),
        "state_pass": state_pass_path,
        "render_pass": render_pass_path,
        "gpu_ms": gpu_ms,
    })
    return effect


def build_update_manager(parent_comp):
    updater = parent_comp.create(baseCOMP, "update_manager")
    updater.color = (0.42, 0.28, 0.12)
    updater.comment = "Safe update discovery. Installs are never activated automatically."
    page = updater.appendCustomPage("Updates")
    definitions = (
        {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""},
        {"name": "Autocheck", "label": "Auto Check", "type": "toggle", "default": True},
        {"name": "Intervalhours", "label": "Interval (Hours)", "type": "float", "default": 24.0, "min": 1.0 / 60.0, "max": 720.0},
        {"name": "Channel", "type": "menu", "default": "stable", "menu_names": ["stable", "beta", "experimental"], "menu_labels": ["Stable", "Beta", "Experimental"]},
        {"name": "Timeout", "label": "Timeout (Seconds)", "type": "float", "default": 10.0, "min": 1.0, "max": 120.0},
        {"name": "Checkupdates", "label": "Check for Updates", "type": "pulse"},
        {"name": "Lastcheck", "label": "Last Check", "type": "string", "default": ""},
        {"name": "Status", "type": "string", "default": "Not checked"},
    )
    for definition in definitions:
        _append_parameter(updater, page, definition)

    results = updater.create(tableDAT, "update_results")
    results.setSize(0, 0)
    results.appendRow(("id", "installed", "available", "channel", "restart", "permissions_changed", "source", "changelog"))
    results.nodeX = 0
    results.nodeY = 0

    configure_extension(updater, "UpdaterExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "UpdaterExt.py")

    parexec = configure_parameter_callbacks(
        updater,
        PROJECT_ROOT / "touchdesigner" / "callbacks" / "updater_parameter_callbacks.py",
        "Checkupdates Autocheck Intervalhours",
    )
    parexec.nodeX = 220
    parexec.nodeY = -120

    starter = updater.create(executeDAT, "startup_callbacks")
    starter.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "updater_start_callbacks.py")
    starter.par.start = True
    starter.nodeX = 220
    starter.nodeY = -240

    updater.save(str(CORE_ROOT / "FxUpdater.tox"), createFolders=True)
    return updater


def build_rack(parent_comp, manifests):
    rack = parent_comp.create(baseCOMP, "fx_rack")
    rack.color = (0.28, 0.20, 0.48)
    rack.comment = "Eight-slot ImageFX rack with reordering, presets, bypass, and modulation"
    page = rack.appendCustomPage("Rack")
    package_ids = [manifest["id"] for manifest in manifests]
    package_labels = [manifest["name"] for manifest in manifests]
    defaults = [
        "tdimagefx.distort.wave-warp",
        "tdimagefx.color.exposure",
        "tdimagefx.blur.gaussian-blur",
        "tdimagefx.glitch.rgb-split",
        "tdimagefx.temporal.feedback-trails",
        "tdimagefx.stylize.halftone",
        "tdimagefx.light.bloom",
        "tdimagefx.stylize.scanlines",
    ]
    _append_parameter(rack, page, {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""})
    _append_parameter(rack, page, {"name": "Autotime", "label": "Auto Time", "type": "toggle", "default": True})
    _append_parameter(rack, page, {"name": "Timescale", "label": "Time Scale", "type": "float", "default": 1.0, "min": -10.0, "max": 10.0})
    _append_parameter(rack, page, {"name": "Manualtime", "label": "Manual Time", "type": "float", "default": 0.0, "min": -100000.0, "max": 100000.0})
    _append_parameter(rack, page, {"name": "Time", "label": "Effective Time", "type": "float", "default": 0.0, "min": -100000.0, "max": 100000.0})
    _append_parameter(rack, page, {"name": "Presetname", "label": "Preset Name", "type": "string", "default": "My Rack"})
    _append_parameter(rack, page, {"name": "Presetpath", "label": "Preset Path", "type": "file", "default": "rack/my-rack.json"})
    _append_parameter(rack, page, {"name": "Presetjson", "label": "Preset JSON", "type": "string", "default": ""})
    for name, label in (
        ("Exportpreset", "Export Preset"), ("Importpreset", "Import Preset"),
        ("Savepreset", "Save Preset"), ("Loadpreset", "Load Preset"),
        ("Reloadall", "Reload All"), ("Reset", "Reset All"),
        ("Bypassall", "Bypass All"), ("Enableall", "Enable All"),
    ):
        _append_parameter(rack, page, {"name": name, "label": label, "type": "pulse"})
    rack.par.Time.expr = "absTime.seconds * me.par.Timescale if me.par.Autotime else me.par.Manualtime"
    for index in range(1, RACK_SLOT_COUNT + 1):
        _append_parameter(rack, page, {
            "name": "Slot{}effect".format(index), "label": "Slot {} Effect".format(index), "type": "menu",
            "default": defaults[index - 1], "menu_names": package_ids, "menu_labels": package_labels,
        })
        _append_parameter(rack, page, {"name": "Slot{}enable".format(index), "label": "Slot {} Enable".format(index), "type": "toggle", "default": True})
        _append_parameter(rack, page, {"name": "Slot{}mix".format(index), "label": "Slot {} Mix".format(index), "type": "float", "default": 1.0, "min": 0.0, "max": 1.0})
        _append_parameter(rack, page, {"name": "Slot{}moddepth".format(index), "label": "Slot {} Mod Depth".format(index), "type": "float", "default": 0.0, "min": -1.0, "max": 1.0})
        _append_parameter(rack, page, {"name": "Slot{}modrate".format(index), "label": "Slot {} Mod Rate".format(index), "type": "float", "default": 1.0, "min": 0.0, "max": 60.0})
        _append_parameter(rack, page, {
            "name": "Slot{}modstate".format(index), "label": "Slot {} Modulation".format(index),
            "type": "menu", "default": "off", "menu_names": ["off", "sine", "triangle", "saw"],
            "menu_labels": ["Off", "Sine", "Triangle", "Saw"],
        })
        for action, label in (("up", "Up"), ("down", "Down"), ("reset", "Reset"), ("bypass", "Bypass")):
            _append_parameter(rack, page, {
                "name": "Slot{}{}".format(index, action),
                "label": "Slot {} {}".format(index, label),
                "type": "pulse",
            })

    rack_input = rack.create(inTOP, "in1_image")
    rack_input.par.label = "image"
    rack_input.nodeX = -520
    rack_input.nodeY = 0

    rack_inputs = {"image": rack_input}
    for input_number, (role, label) in enumerate(RACK_AUXILIARY_INPUTS, start=2):
        auxiliary_input = rack.create(inTOP, "in{}_{}".format(input_number, role))
        auxiliary_input.par.label = label
        auxiliary_input.nodeX = -520
        auxiliary_input.nodeY = -(input_number - 1) * 110
        rack_inputs[role] = auxiliary_input

    source_connector = rack_input.outputConnectors[0]
    for index, package_id in enumerate(defaults, start=1):
        manifest = next(item for item in manifests if item["id"] == package_id)
        tox_path = _manifest_asset(
            manifest,
            manifest["entrypoints"]["touchdesigner_component"],
            "$.entrypoints.touchdesigner_component",
        )
        slot = load_tox_component(rack, tox_path, "slot{}".format(index))
        slot.nodeX = -300 + (index - 1) * 210
        slot.nodeY = 0
        declared_inputs = manifest.get("inputs", [])
        if len(slot.inputConnectors) != len(declared_inputs):
            raise RuntimeError(
                "{} declares {} inputs but its component exposes {}".format(
                    package_id, len(declared_inputs), len(slot.inputConnectors)
                )
            )
        source_connector.connect(slot.inputConnectors[0])
        input_routes = {"0": "image"}
        for input_index, input_definition in enumerate(declared_inputs[1:], start=1):
            role = _rack_input_role(input_definition, input_index)
            rack_inputs[role].outputConnectors[0].connect(slot.inputConnectors[input_index])
            input_routes[str(input_index)] = role
        if slot.par["Enable"] is not None:
            slot.par.Enable.expr = "parent().par.Slot{}enable".format(index)
        if slot.par["Mix"] is not None:
            slot.par.Mix.expr = "parent().ModulatedMix({})".format(index)
        if slot.par["Time"] is not None:
            slot.par.Time.expr = "parent().par.Time"
        rack.store("slot{}_package".format(index), {"id": package_id, "version": manifest["version"]})
        rack.store("slot{}_input_routes".format(index), input_routes)
        source_connector = slot.outputConnectors[0]

    rack_output = rack.create(outTOP, "out1_image")
    source_connector.connect(rack_output.inputConnectors[0])
    rack_output.nodeX = 600
    rack_output.nodeY = 0
    rack_output.display = True
    rack_output.render = True

    configure_extension(rack, "FxRackExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "FxRackExt.py")
    parexec = configure_parameter_callbacks(
        rack,
        PROJECT_ROOT / "touchdesigner" / "callbacks" / "rack_parameter_callbacks.py",
        "Slot* Reset Reloadall Bypassall Enableall Exportpreset Importpreset Savepreset Loadpreset",
    )
    parexec.nodeX = 400
    parexec.nodeY = -250

    rack_path = CORE_ROOT / "FxRack.tox"
    rack.save(str(rack_path), createFolders=True)
    return rack, rack_path


def build_browser(parent_comp, manifests, compatibility_confidence="declared"):
    browser = parent_comp.create(baseCOMP, "fx_browser")
    browser.color = (0.14, 0.38, 0.30)
    browser.comment = "Search, filter, favorite, inspect, and create ImageFX packages"
    page = browser.appendCustomPage("Browser")
    package_ids = [manifest["id"] for manifest in manifests]
    package_labels = [manifest["name"] for manifest in manifests]
    categories = sorted({manifest["category"] for manifest in manifests})
    channels = sorted({manifest["channel"] for manifest in manifests})
    models = sorted({_processing(manifest)["model"] for manifest in manifests})
    capabilities = sorted({
        capability
        for manifest in manifests
        for capability in _processing(manifest)["capabilities"]
    })
    definitions = (
        {"name": "Search", "type": "string", "default": "", "description": "AND-search names, IDs, descriptions, tags, inputs, parameters, and image contracts."},
        {"name": "Category", "type": "menu", "default": "all", "menu_names": ["all", *categories], "menu_labels": ["All", *[value.title() for value in categories]], "description": "Limit results to one effect category."},
        {"name": "Channel", "type": "menu", "default": "all", "menu_names": ["all", *channels], "menu_labels": ["All", *[value.title() for value in channels]], "description": "Filter by release maturity channel."},
        {"name": "Model", "label": "Processing Model", "type": "menu", "default": "all", "menu_names": ["all", *models], "menu_labels": ["All", *[value.replace("_", " ").title() for value in models]], "description": "Filter single-pass, multi-pass, temporal, or simulation effects."},
        {"name": "Capability", "type": "menu", "default": "all", "menu_names": ["all", *capabilities], "menu_labels": ["All", *[value.replace("_", " ").title() for value in capabilities]], "description": "Require one processing capability."},
        {"name": "Inputreadiness", "label": "Input Readiness", "type": "menu", "default": "all", "menu_names": ["all", "ready", "needs_aux", "image_only"], "menu_labels": ["All", "Ready With Available Inputs", "Needs Auxiliary Input", "Image Only"], "description": "Compare effect input roles with Available Inputs."},
        {"name": "Availableinputs", "label": "Available Inputs", "type": "string", "default": "image", "description": "Comma-separated semantic buses currently available, such as image, depth, mask, flow, normal, displacement, or image_b."},
        {"name": "Sortby", "label": "Sort By", "type": "menu", "default": "name", "menu_names": ["name", "category", "cost"], "menu_labels": ["Name", "Category", "GPU Cost"], "description": "Choose the stable results ordering."},
        {"name": "Tags", "type": "string", "default": "", "description": "Comma-separated tags; every requested tag must match."},
        {"name": "Favorites", "type": "string", "default": "[]", "description": "JSON-backed favorite package IDs."},
        {"name": "Favoritesonly", "label": "Favorites Only", "type": "toggle", "default": False},
        {"name": "Selectedid", "label": "Selected Effect", "type": "menu", "default": package_ids[0], "menu_names": package_ids, "menu_labels": package_labels},
        {"name": "Selectedpreview", "label": "Selected Preview", "type": "string", "default": "docs/gallery/{}.png".format(package_ids[0]), "animatable": False},
        {"name": "Selecteddiagnostics", "label": "Selected Diagnostics", "type": "string", "default": "", "animatable": False},
        {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "folder", "default": "", "description": "Root used to resolve preview paths when the library is installed outside the current project folder."},
        {"name": "Target", "label": "Creation Target", "type": "operator", "default": "", "description": "COMP where Create Selected instantiates the immutable package .tox."},
        {"name": "Refresh", "type": "pulse"},
        {"name": "Create", "label": "Create Selected", "type": "pulse"},
        {"name": "Togglefavorite", "label": "Toggle Favorite", "type": "pulse"},
        {"name": "Status", "type": "string", "default": "Ready", "animatable": False},
    )
    for definition in definitions:
        _append_parameter(browser, page, definition)

    results = browser.create(tableDAT, "results")
    columns = (
        "id", "name", "version", "category", "channel", "description", "tags", "favorite", "preview",
        "input_count", "input_roles", "input_readiness", "parameter_count", "parameters", "alpha_policy",
        "resolution_policy", "image_contract", "compatibility", "compatibility_confidence", "quality", "model",
        "gpu_cost", "capabilities", "component",
    )
    results.appendRow(columns)
    for manifest in manifests:
        catalog_row = _manifest_catalog_row(manifest, compatibility_confidence)
        row = dict(catalog_row)
        row["favorite"] = "0"
        row["model"] = catalog_row["processing_model"]
        results.appendRow(tuple(row[column] for column in columns))
    results.nodeX = -140
    results.nodeY = 0

    results_text = browser.create(textDAT, "results_text")
    results_text.text = "\n".join(
        "{:>2}.  {}  [{} / {} GPU]".format(index, manifest["name"], manifest["category"], _processing(manifest)["gpu_cost"])
        for index, manifest in enumerate(manifests[:24], start=1)
    )
    results_text.nodeX = -360
    results_text.nodeY = -180

    first_row = _manifest_catalog_row(manifests[0], compatibility_confidence)
    first_details = (
        ("Effect", "{} {}".format(first_row["name"], first_row["version"])),
        ("Description", first_row["description"]),
        ("Processing", "{} | {} GPU".format(first_row["processing_model"], first_row["gpu_cost"])),
        ("Inputs", "{}: {}".format(first_row["input_count"], first_row["input_roles"])),
        ("Input readiness", first_row["input_readiness"]),
        ("Parameters", "{} | {}".format(first_row["parameter_count"], first_row["parameters"])),
        ("Image contract", "alpha={} | resolution={} | {}".format(first_row["alpha_policy"], first_row["resolution_policy"], first_row["image_contract"])),
        ("Quality", first_row["quality"]),
        ("Compatibility", "{} ({})".format(first_row["compatibility"], first_row["compatibility_confidence"])),
    )
    selected_details = browser.create(tableDAT, "selected_details")
    selected_details.appendRow(("field", "value"))
    for detail in first_details:
        selected_details.appendRow(detail)
    selected_details.nodeX = -140
    selected_details.nodeY = -180

    selected_detail_text = browser.create(textDAT, "selected_detail_text")
    selected_detail_text.text = "\n\n".join("{}\n{}".format(label, value) for label, value in first_details)
    selected_detail_text.nodeX = 80
    selected_detail_text.nodeY = -300

    configure_extension(browser, "ImageFXBrowserExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "ImageFXBrowserExt.py")

    selected_preview = browser.create(moviefileinTOP, "selected_preview")
    selected_preview.nodeX = -360
    selected_preview.nodeY = 180
    selected_preview.par.file.expr = "parent().PreviewPath()"
    if selected_preview.par["play"] is not None:
        selected_preview.par.play = False

    results_view = browser.create(textTOP, "results_view")
    results_view.nodeX = -100
    results_view.nodeY = 180
    results_view.par.text.expr = "op('results_text').text"
    if results_view.par["outputresolution"] is not None:
        results_view.par.outputresolution = "custom"
        results_view.par.resolutionw = 560
        results_view.par.resolutionh = 680

    details_view = browser.create(textTOP, "details_view")
    details_view.nodeX = 140
    details_view.nodeY = 180
    details_view.par.text.expr = "op('selected_detail_text').text"
    if details_view.par["outputresolution"] is not None:
        details_view.par.outputresolution = "custom"
        details_view.par.resolutionw = 560
        details_view.par.resolutionh = 330
    for text_view, font_size in ((results_view, 18), (details_view, 13)):
        for parameter_name, value in (
            ("wordwrap", True), ("alignx", "left"), ("aligny", "top"),
            ("positionunit", "fract"), ("position1", 0.025), ("position2", 0.97),
            ("fontautosize", "fitiffat"), ("fontsizex", font_size), ("fontsizey", font_size),
            ("bgalpha", 1.0), ("bgcolorr", 0.035), ("bgcolorg", 0.055), ("bgcolorb", 0.075),
        ):
            if text_view.par[parameter_name] is not None:
                text_view.par[parameter_name] = value

    browser_panel = browser.create(containerCOMP, "browser_panel")
    browser_panel.nodeX = 380
    browser_panel.nodeY = 120
    for name, x, y, width, height, viewer in (
        ("results_panel", 0, 0, 570, 720, results_view),
        ("preview_panel", 580, 370, 700, 350, selected_preview),
        ("details_panel", 580, 0, 700, 360, details_view),
    ):
        panel = browser_panel.create(opviewerCOMP, name)
        for parameter_name, value in (("x", x), ("y", y), ("w", width), ("h", height)):
            if panel.par[parameter_name] is not None:
                panel.par[parameter_name] = value
        if panel.par["opviewer"] is not None:
            panel.par.opviewer = viewer.path
        if panel.par["topdirect"] is not None:
            panel.par.topdirect = True
        if panel.par["interactive"] is not None:
            panel.par.interactive = False
    if browser_panel.par["w"] is not None:
        browser_panel.par.w = 1280
        browser_panel.par.h = 720
    if browser.par["opviewer"] is not None:
        browser.par.opviewer = browser_panel.path

    parexec = configure_parameter_callbacks(
        browser,
        PROJECT_ROOT / "touchdesigner" / "callbacks" / "browser_parameter_callbacks.py",
        (
            "Search Category Channel Model Capability Inputreadiness Availableinputs Sortby Tags Favorites "
            "Favoritesonly Selectedid Refresh Create Togglefavorite"
        ),
    )
    parexec.nodeX = 120
    parexec.nodeY = -180

    # Keep the dormant constant empty: TouchDesigner can preserve a warning for
    # a relative operator path stored there even while the active expression
    # resolves correctly. Set and cook the expression both before and after
    # exporting because palette serialization may rewrite operator parameters.
    browser.par.Target.val = ""
    browser.par.Target.expr = "me.op('../../effects')"
    if browser.UpdateSelection() is None:
        raise RuntimeError("Browser could not initialize its selected effect preview")
    browser.cook(force=True)
    selected_preview.cook(force=True)
    if (selected_preview.width, selected_preview.height) != (512, 288):
        raise RuntimeError(
            "Browser selected preview did not load at 512x288: {}x{}".format(
                selected_preview.width,
                selected_preview.height,
            )
        )
    browser_path = CORE_ROOT / "FxBrowser.tox"
    browser.save(str(browser_path), createFolders=True)
    browser.par.Target.val = ""
    browser.par.Target.expr = "me.op('../../effects')"
    if browser.UpdateSelection() is None:
        raise RuntimeError("Browser could not restore its selected effect preview after export")
    browser.cook(force=True)
    selected_preview.cook(force=True)
    return browser, browser_path


def _benchmark_effect(effect, frames=12):
    glsl_nodes = sorted(effect.findChildren(type=glslTOP), key=lambda node: node.name)
    output = effect.op("out1_image")
    gpu_samples = []
    cpu_samples = []
    for _index in range(frames):
        if output is not None:
            output.cook(force=True)
        gpu_total = 0.0
        cpu_total = 0.0
        for glsl in glsl_nodes:
            glsl.cook(force=True)
            try:
                gpu_total += max(0.0, float(glsl.gpuCookTime))
            except Exception:
                pass
            try:
                cpu_total += max(0.0, float(glsl.cpuCookTime))
            except Exception:
                pass
        gpu_samples.append(gpu_total)
        cpu_samples.append(cpu_total)
    measured_gpu = [value for value in gpu_samples if value > 0.0]
    gpu_memory = 0
    for glsl in glsl_nodes:
        try:
            gpu_memory += max(0, int(glsl.gpuMemory))
        except Exception:
            pass
    return {
        "gpu_ms": float(statistics.median(measured_gpu)) if measured_gpu else None,
        "cpu_submission_ms": float(statistics.median(cpu_samples)) if cpu_samples else 0.0,
        "gpu_memory_bytes": gpu_memory,
    }


def _parameter_suffixes(definition):
    """Return the TouchDesigner suffixes used by one manifest parameter."""
    parameter_type = definition.get("type", "float")
    if parameter_type == "rgb":
        return tuple("rgb")
    if parameter_type == "rgba":
        return tuple("rgba")
    if parameter_type in {"xy", "xyz", "uv"}:
        return tuple(parameter_type)
    return ("",)


def _effect_parameter_bindings(effect, manifest):
    """Reconstruct shader parameter bindings from an already-built effect COMP."""
    bindings = []
    for definition in manifest.get("parameters", []):
        parameter_names = [
            definition["name"] + suffix for suffix in _parameter_suffixes(definition)
        ]
        parameters = [effect.par[name] for name in parameter_names]
        missing = [
            name for name, parameter in zip(parameter_names, parameters)
            if parameter is None
        ]
        if missing:
            raise RuntimeError(
                "{} is missing preview parameter(s): {}".format(
                    manifest["id"], ", ".join(missing)
                )
            )
        bindings.append((definition, parameters))
    return bindings


def _held_frame_preview_seed(effect, input_node):
    """Create a recognizable prior-frame fixture for freeze-only preview effects."""
    shader_dat = effect.create(textDAT, "preview_held_frame_shader")
    shader_dat.text = PREVIEW_HELD_FRAME_SHADER
    shader_dat.nodeX = -100
    shader_dat.nodeY = -620
    glsl = effect.create(glslTOP, "preview_held_frame")
    glsl.nodeX = 0
    glsl.nodeY = -500
    input_node.outputConnectors[0].connect(glsl.inputConnectors[0])
    glsl.par.pixeldat = shader_dat.path
    if glsl.par["glslversion"] is not None:
        glsl.par.glslversion = "glsl460"
    if glsl.par["compilebehavior"] is not None:
        glsl.par.compilebehavior = "stalluntildone"
    if glsl.par["errorbehavior"] is not None:
        glsl.par.errorbehavior = "showprevious"
    if glsl.par["outputresolution"] is not None:
        glsl.par.outputresolution = "useinput"
    return glsl


def _stateful_preview_output(effect, manifest, iterations):
    """Build a temporary deterministic DAG that iterates the declared state shader."""
    processing = _processing(manifest)
    history_frames = _history_frame_count(processing)
    if history_frames < 1:
        raise RuntimeError("A stateful preview requires retained history")
    pass_paths = list(processing.get("passes") or [manifest["entrypoints"]["shader"]])
    state_pass_path, render_pass_path = _state_render_passes(processing, pass_paths)
    parameter_bindings = _effect_parameter_bindings(effect, manifest)
    input_nodes = []
    for input_index, input_definition in enumerate(manifest.get("inputs", []), start=1):
        input_node = effect.op(
            "in{}_{}".format(input_index, _safe_name(input_definition["id"]))
        )
        if input_node is None:
            raise RuntimeError(
                "{} is missing preview input {}".format(manifest["id"], input_index)
            )
        input_nodes.append(input_node)
    if not input_nodes:
        raise RuntimeError("{} does not declare a TOP input".format(manifest["id"]))
    history_seed = effect.op("history_seed")
    if history_seed is None:
        raise RuntimeError("{} has no deterministic history seed".format(manifest["id"]))

    glsl_nodes = []
    # A held static image is indistinguishable from its current frame, while a
    # held black reset is visually empty. Give the Stutter gallery capture one
    # deterministic prior-frame fixture; the shipped runtime still resets its
    # real Feedback TOP from the black history_seed above.
    if manifest["id"] == "tdimagefx.temporal.stutter":
        history_seed = _held_frame_preview_seed(effect, input_nodes[0])
        glsl_nodes.append(history_seed)
    # Cache TOP history_frames=N exposes an older retained state. Mirror that
    # delay with a fixed-length queue of shader outputs.
    history_queue = [history_seed] * history_frames
    display_output = None
    for iteration_index in range(max(1, int(iterations))):
        history_input = history_queue[0]
        previous = None
        state_output = None
        render_output = None
        for pass_index, relative_path in enumerate(pass_paths):
            if pass_index == 0:
                pass_inputs = [input_nodes[0], history_input, *input_nodes[1:]]
            else:
                pass_inputs = [previous, input_nodes[0], *input_nodes[1:]]
                if relative_path == state_pass_path:
                    pass_inputs = [
                        previous, input_nodes[0], history_input, *input_nodes[1:]
                    ]
            previous = _shader_pass(
                effect,
                manifest,
                pass_index,
                relative_path,
                pass_inputs,
                parameter_bindings,
                node_key="preview_{:02d}_{:02d}".format(
                    iteration_index + 1, pass_index + 1
                ),
            )
            glsl_nodes.append(previous)
            if relative_path == state_pass_path:
                state_output = previous
            if relative_path == render_pass_path:
                render_output = previous
        next_state = state_output or previous
        display_output = render_output or previous
        if next_state is None or display_output is None:
            raise RuntimeError("{} did not produce a preview state".format(manifest["id"]))
        history_queue.append(next_state)
        history_queue.pop(0)

    errors = []
    for glsl in glsl_nodes:
        glsl.cook(force=True)
        try:
            errors.extend("{}: {}".format(glsl.name, error) for error in glsl.errors())
        except Exception:
            pass
    if errors:
        raise RuntimeError("; ".join(errors))
    return display_output


def _save_preview(effect, manifest, report):
    package_id = manifest["id"]
    preview_path = PREVIEW_ROOT / "{}.png".format(package_id)
    output = effect.op("out1_image")
    if output is None:
        raise RuntimeError("{} has no output TOP".format(package_id))
    previous_values = {}
    time_parameter = effect.par["Time"]
    time_state = None
    original_child_ids = {child.id for child in effect.children}
    iterations = int(effect.fetch("tdimagefx_history_frames", 0))
    if report.get("effects") and report["effects"][-1].get("id") == package_id:
        iterations = int(report["effects"][-1].get("preview_state_iterations", 1))
    iterations = max(1, iterations)
    try:
        if time_parameter is not None:
            time_state = (time_parameter.mode, time_parameter.expr, time_parameter.eval())
            time_parameter.mode = ParMode.CONSTANT
            time_parameter.val = 1.25
        for name, value in PREVIEW_PARAMETER_OVERRIDES.get(package_id, {}).items():
            parameter = effect.par[name]
            if parameter is None:
                raise RuntimeError("{} preview override references missing parameter {}".format(package_id, name))
            previous_values[name] = parameter.eval()
            parameter.val = value
        if int(effect.fetch("tdimagefx_history_frames", 0)) > 0:
            output = _stateful_preview_output(effect, manifest, iterations)
        output.cook(force=True)
        output.save(str(preview_path), asynchronous=False, createFolders=True, quality=1.0)
    except Exception as exc:
        report["preview_errors"][package_id] = str(exc)
    finally:
        for child in sorted(
            (child for child in effect.children if child.id not in original_child_ids),
            key=lambda child: child.id,
            reverse=True,
        ):
            child.destroy()
        for name, value in previous_values.items():
            effect.par[name].val = value
        if time_state is not None:
            previous_mode, previous_expression, previous_value = time_state
            time_parameter.mode = ParMode.CONSTANT
            time_parameter.val = previous_value
            time_parameter.expr = previous_expression
            time_parameter.mode = previous_mode
    return preview_path


def _gpu_label():
    values = []
    for name in ("SYS_GFX_VENDOR", "SYS_GFX_RENDERER", "SYS_GFX_CARD"):
        try:
            value = str(var(name)).strip()
        except Exception:
            value = ""
        if value and value not in values:
            values.append(value)
    return " | ".join(values) or "unknown"


def _write_benchmark_data(report):
    samples = []
    for item in sorted(report["effects"], key=lambda value: value["id"]):
        samples.append({
            "id": item["id"],
            "version": item["version"],
            "model": item["model"],
            "gpu_cost": item["gpu_cost"],
            "gpu_ms": round(float(item["gpu_ms"]), 6) if item.get("gpu_ms") is not None else None,
            "cpu_submission_ms": round(float(item.get("cpu_submission_ms", 0.0)), 6),
            "gpu_memory_bytes": int(item.get("gpu_memory_bytes", 0)),
            "passes": int(item.get("passes", 1)),
        })
    payload = {
        "schema_version": 1,
        "generated_at": report["generated_at"],
        "touchdesigner_build": report["touchdesigner_build"],
        "gpu": _gpu_label(),
        "resolution": "512x288",
        "frames_per_sample": 12,
        "method": (
            "Median per-operator timing over forced cooks within one TouchDesigner frame, "
            "plus resident GLSL TOP texture memory"
        ),
        "gpu_timing_note": (
            "A null gpu_ms means this TouchDesigner build/driver did not expose per-operator GPU execution timing. "
            "cpu_submission_ms measures CPU command submission and must not be interpreted as GPU execution time. "
            "Temporal and simulation samples are first-frame measurements, not warmed steady-state profiles."
        ),
        "samples": samples,
    }
    path = DOCS_ROOT / "benchmark-data.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


LIBRARY_CATALOG_COLUMNS = (
    "id", "name", "version", "kind", "category", "channel", "description", "stateful", "tags",
    "processing_model", "gpu_cost", "capabilities", "quality", "compatibility",
    "compatibility_confidence", "preview", "input_count", "input_roles", "input_readiness",
    "parameter_count", "parameters", "alpha_policy", "resolution_policy", "image_contract", "component",
)


def _manifest_input_roles(manifest):
    roles = []
    for input_index, definition in enumerate(manifest.get("inputs", [])):
        if input_index == 0:
            roles.append("image")
            continue
        try:
            role = _rack_input_role(definition, input_index)
        except RuntimeError:
            role = _normalized_input_role(
                definition.get("role") or definition.get("semantic") or definition.get("id") or "input_{}".format(input_index + 1)
            )
        roles.append(role or "input_{}".format(input_index + 1))
    return tuple(roles or ("image",))


def _manifest_parameter_summary(manifest):
    summaries = []
    for definition in manifest.get("parameters", []):
        label = definition.get("label", definition["name"])
        details = [definition.get("type", "float")]
        if definition.get("unit"):
            details.append(definition["unit"])
        if definition.get("animatable", True) is False:
            details.append("constant")
        summaries.append("{} ({})".format(label, ", ".join(details)))
    return "; ".join(summaries)


def _manifest_image_contract(manifest):
    contract = manifest.get("image_contract") or {}
    if not contract:
        return "legacy manifest contract"
    color = contract.get("color") or {}
    alpha = contract.get("alpha") or {}
    pixel = contract.get("pixel_format") or {}
    sampling = contract.get("sampling") or {}
    color_text = "color {}>{}>{} ({})".format(
        color.get("input_space", "?"), color.get("working_space", "?"),
        color.get("output_space", "?"), color.get("reference", "?"),
    )
    alpha_text = "alpha {}>{}>{}".format(
        alpha.get("input", "?"), alpha.get("working", "?"), alpha.get("output", "?"),
    )
    pixel_text = "pixel {}{}".format(
        pixel.get("policy", "?"), ":{}".format(pixel["format"]) if pixel.get("format") else "",
    )
    sampling_text = "sampling {}/{}{}".format(
        sampling.get("filter", "?"), sampling.get("edge", "?"),
        "/mipmaps" if sampling.get("mipmaps") else "",
    )
    return " | ".join((color_text, alpha_text, pixel_text, sampling_text))


def _manifest_quality(manifest):
    processing = _processing(manifest)
    tiers = [str(item.get("label") or item.get("id")) for item in processing.get("quality_tiers", [])]
    maturity = {
        "stable": "curated stable",
        "beta": "curated beta",
        "experimental": "experimental",
    }.get(manifest.get("channel"), manifest.get("channel", "unknown"))
    return "{} ({})".format(maturity, ", ".join(tiers)) if tiers else maturity


def _manifest_catalog_row(manifest, compatibility_confidence="declared"):
    processing = _processing(manifest)
    compatibility = manifest["compatibility"]
    roles = _manifest_input_roles(manifest)
    parameters = manifest.get("parameters", [])
    return {
        "id": manifest["id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "kind": manifest["kind"],
        "category": manifest["category"],
        "channel": manifest["channel"],
        "description": manifest["description"],
        "stateful": str(manifest["stateful"]),
        "tags": ", ".join(manifest["tags"]),
        "processing_model": processing["model"],
        "gpu_cost": processing["gpu_cost"],
        "capabilities": ", ".join(processing["capabilities"]),
        "quality": _manifest_quality(manifest),
        "compatibility": "TD {}+ | {} | {}".format(
            compatibility["touchdesigner_min_build"], ",".join(compatibility["os"]),
            ",".join(compatibility["architectures"]),
        ),
        "compatibility_confidence": compatibility_confidence,
        "preview": "docs/gallery/{}.png".format(manifest["id"]),
        "input_count": str(len(roles)),
        "input_roles": ", ".join(roles),
        "input_readiness": "Ready" if len(roles) == 1 else "Needs {}".format(", ".join(roles[1:])),
        "parameter_count": str(len(parameters)),
        "parameters": _manifest_parameter_summary(manifest),
        "alpha_policy": manifest.get("alpha_policy", "unspecified"),
        "resolution_policy": manifest.get("resolution_policy", "unspecified"),
        "image_contract": _manifest_image_contract(manifest),
        "component": manifest["entrypoints"]["touchdesigner_component"],
    }


def build_library(project_comp, manifests, report):
    library = project_comp.create(baseCOMP, "td_imagefx")
    library.nodeX = -250
    library.nodeY = 100
    library.color = (0.10, 0.34, 0.42)
    library.comment = "TD ImageFX Library {}".format(LIBRARY_VERSION)
    page = library.appendCustomPage("Library")
    definitions = (
        {"name": "Version", "type": "string", "default": LIBRARY_VERSION},
        {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""},
        {"name": "Status", "type": "string", "default": "Building"},
        {"name": "Refreshcatalog", "label": "Refresh Catalog", "type": "pulse"},
    )
    for definition in definitions:
        _append_parameter(library, page, definition)

    catalog = library.create(tableDAT, "catalog")
    catalog.setSize(0, 0)
    catalog.appendRow(LIBRARY_CATALOG_COLUMNS)
    compatibility_confidence = "native build verified: TD {} / {} / {}".format(
        report.get("touchdesigner_build", "unknown"), report.get("touchdesigner_os", "unknown"),
        report.get("touchdesigner_architecture", "unknown"),
    )
    for manifest in manifests:
        row = _manifest_catalog_row(manifest, compatibility_confidence)
        catalog.appendRow(tuple(row[column] for column in LIBRARY_CATALOG_COLUMNS))
    catalog.nodeX = -400
    catalog.nodeY = -250
    # The browser resolves the public library API while it initializes its
    # selected preview, so promote the library extension before building core.
    configure_extension(
        library,
        "ImageFXLibraryExt",
        PROJECT_ROOT / "touchdesigner" / "extensions" / "ImageFXLibraryExt.py",
    )

    readme = library.create(textDAT, "README")
    readme.text = (
        "TD ImageFX Library {}\n\n"
        "Use core/fx_rack for an eight-effect chain with presets and modulation.\n"
        "Use core/fx_browser to search, filter, favorite, and create effects.\n"
        "Use the promoted Find(), CreateEffect(), CheckUpdates(), and HealthCheck() methods.\n"
        "All effect versions are immutable and stored under packages/<id>/<version>.\n"
        "Updates are notify-only by default; review and activation are separate actions.\n"
    ).format(LIBRARY_VERSION)
    readme.nodeX = -150
    readme.nodeY = -250

    effects_parent = library.create(baseCOMP, "effects")
    effects_parent.nodeX = 0
    effects_parent.nodeY = 100
    preview_shader = effects_parent.create(textDAT, "preview_source_shader")
    preview_shader.text = PREVIEW_SOURCE_SHADER
    preview_shader.nodeX = -760
    preview_shader.nodeY = 180
    preview_source = effects_parent.create(glslTOP, "preview_source")
    preview_source.nodeX = -520
    preview_source.nodeY = 180
    preview_source.par.pixeldat = preview_shader.path
    if preview_source.par["glslversion"] is not None:
        preview_source.par.glslversion = "glsl460"
    if preview_source.par["compilebehavior"] is not None:
        preview_source.par.compilebehavior = "stalluntildone"
    if preview_source.par["outputresolution"] is not None:
        preview_source.par.outputresolution = "custom"
        preview_source.par.resolutionw = 512
        preview_source.par.resolutionh = 288
    preview_source.cook(force=True)
    preview_source_errors = list(preview_source.errors())
    if preview_source_errors:
        raise RuntimeError("Preview source shader failed: {}".format("; ".join(preview_source_errors)))
    preview_aux = effects_parent.create(noiseTOP, "preview_auxiliary")
    preview_aux.nodeX = -520
    preview_aux.nodeY = -20
    if preview_aux.par["outputresolution"] is not None:
        preview_aux.par.outputresolution = "custom"
        preview_aux.par.resolutionw = 512
        preview_aux.par.resolutionh = 288
    preview_lut_shader = effects_parent.create(textDAT, "preview_identity_lut_shader")
    preview_lut_shader.text = PREVIEW_IDENTITY_LUT_SHADER
    preview_lut_shader.nodeX = -760
    preview_lut_shader.nodeY = -180
    preview_lut = effects_parent.create(glslTOP, "preview_identity_lut")
    preview_lut.nodeX = -520
    preview_lut.nodeY = -180
    preview_lut.par.pixeldat = preview_lut_shader.path
    if preview_lut.par["glslversion"] is not None:
        preview_lut.par.glslversion = "glsl460"
    if preview_lut.par["compilebehavior"] is not None:
        preview_lut.par.compilebehavior = "stalluntildone"
    if preview_lut.par["outputresolution"] is not None:
        preview_lut.par.outputresolution = "custom"
        preview_lut.par.resolutionw = 1024
        preview_lut.par.resolutionh = 32
    preview_lut.cook(force=True)
    preview_lut_errors = list(preview_lut.errors())
    if preview_lut_errors:
        raise RuntimeError("Identity LUT preview shader failed: {}".format("; ".join(preview_lut_errors)))
    for index, manifest in enumerate(manifests):
        effect = build_effect(effects_parent, manifest, report)
        effect.nodeX = (index % 4) * 230
        effect.nodeY = -(index // 4) * 180
        preview_source.outputConnectors[0].connect(effect.inputConnectors[0])
        for input_index, input_definition in enumerate(manifest.get("inputs", [])[1:], start=1):
            fixture = preview_lut if input_definition.get("semantic") == "lut" else preview_aux
            fixture.outputConnectors[0].connect(effect.inputConnectors[input_index])
        report["effects"][-1].update(_benchmark_effect(effect))
        report["effects"][-1]["preview"] = str(_save_preview(effect, manifest, report))
        # The immutable .tox, benchmark, and preview now exist. Keep the shipped
        # library lightweight and let CreateEffect/FxRack load packages lazily.
        effect.destroy()
    preview_aux.destroy()
    preview_lut.destroy()
    preview_lut_shader.destroy()
    preview_source.destroy()
    preview_shader.destroy()

    core_parent = library.create(baseCOMP, "core")
    core_parent.nodeX = 260
    core_parent.nodeY = 100
    updater = build_update_manager(library)
    updater.nodeX = 520
    updater.nodeY = 100
    rack, rack_path = build_rack(core_parent, manifests)
    rack.nodeX = 0
    rack.nodeY = 0
    browser, browser_path = build_browser(core_parent, manifests, compatibility_confidence)
    browser.nodeX = 260
    browser.nodeY = 0

    library.par.Status = "Ready: {} packages".format(len(manifests))
    library_path = CORE_ROOT / "TDImageFXLibrary.tox"
    library.save(str(library_path), createFolders=True)
    report["core"] = {
        "library": str(library_path),
        "rack": str(rack_path),
        "browser": str(browser_path),
        "updater": str(CORE_ROOT / "FxUpdater.tox"),
    }
    return library, rack_path


def build_demo(project_comp, rack_path):
    demo = project_comp.create(baseCOMP, "imagefx_demo")
    demo.nodeX = 100
    demo.nodeY = 100
    demo.color = (0.32, 0.18, 0.36)
    demo.comment = "Animated starter chain. Replace source_image with any TOP."

    source = demo.create(rampTOP, "source_image")
    source.nodeX = -300
    source.nodeY = 0
    if source.par["outputresolution"] is not None:
        source.par.outputresolution = "custom"
        source.par.resolutionw = 1280
        source.par.resolutionh = 720

    rack = load_tox_component(demo, rack_path, "fx_rack")
    rack.nodeX = 0
    rack.nodeY = 0
    source.outputConnectors[0].connect(rack.inputConnectors[0])

    output = demo.create(outTOP, "out1_image")
    rack.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 280
    output.nodeY = 0
    output.display = True
    output.render = True
    demo.par.opviewer = output.path
    return demo


def _existing_owned_nodes(project_comp):
    return [node for node in (project_comp.op("td_imagefx"), project_comp.op("imagefx_demo")) if node is not None]


def _foreign_project_node_names(project_comp):
    """Return unrelated top-level nodes that would leak into the generated .toe."""
    foreign = []
    for node in project_comp.children:
        if node.name in OWNED_PROJECT_NODES:
            continue
        expected_type = DEFAULT_TEMPLATE_NODES.get(node.name)
        if expected_type is not None and str(node.type) == expected_type:
            continue
        foreign.append(node.name)
    return sorted(foreign)


def _default_template_nodes(project_comp):
    """Return disposable operators created by TouchDesigner's blank templates."""
    return [
        node for node in project_comp.children
        if node.name in DEFAULT_TEMPLATE_NODES
        and str(node.type) == DEFAULT_TEMPLATE_NODES[node.name]
    ]


def _numbered_project_siblings(project_path):
    project_path = Path(project_path)
    pattern = re.compile(
        r"^{}\.[1-9][0-9]*{}$".format(
            re.escape(project_path.stem), re.escape(project_path.suffix)
        )
    )
    return {
        path for path in project_path.parent.glob(
            "{}.*{}".format(project_path.stem, project_path.suffix)
        )
        if pattern.fullmatch(path.name)
    }


def _save_project_atomically(project_path=PROJECT_PATH, build_root=BUILD_ROOT, project_object=None):
    """Replace the generated .toe without TouchDesigner's interactive overwrite dialog."""
    project_path = Path(project_path)
    build_root = Path(build_root)
    build_root.mkdir(parents=True, exist_ok=True)
    backup_path = build_root / ("." + project_path.name + ".previous")
    numbered_before = _numbered_project_siblings(project_path)
    created_numbered = set()
    if project_path.is_symlink() or backup_path.is_symlink():
        raise RuntimeError("Native project and recovery paths may not be symbolic links")
    if backup_path.exists():
        raise RuntimeError(
            "A previous native-project recovery file exists; inspect it before rebuilding: {}".format(
                backup_path
            )
        )
    had_existing = project_path.exists()
    if had_existing and not project_path.is_file():
        raise RuntimeError("Native project destination is not a regular file: {}".format(project_path))
    if had_existing:
        project_path.replace(backup_path)
    saver = project if project_object is None else project_object
    try:
        saved = saver.save(str(project_path), saveExternalToxs=False)
        if saved is not True:
            raise RuntimeError("TouchDesigner did not save the native library project")
        if project_path.is_symlink() or not project_path.is_file():
            raise RuntimeError(
                "TouchDesigner reported success without writing the requested native project: {}".format(
                    project_path
                )
            )
        if project_path.stat().st_size <= 0:
            raise RuntimeError("TouchDesigner wrote an empty native library project")
        created_numbered = _numbered_project_siblings(project_path) - numbered_before
        for sibling in created_numbered:
            if sibling.is_symlink() or not sibling.is_file():
                raise RuntimeError(
                    "TouchDesigner created an unsafe numbered native project: {}".format(sibling)
                )
            if (
                sibling.stat().st_size != project_path.stat().st_size
                or _sha256_file(sibling) != _sha256_file(project_path)
            ):
                raise RuntimeError(
                    "TouchDesigner created a conflicting numbered native project: {}".format(
                        sibling
                    )
                )
        for sibling in created_numbered:
            sibling.unlink()
        created_numbered.clear()
    except Exception as exc:
        rollback_error = None
        created_numbered.update(_numbered_project_siblings(project_path) - numbered_before)
        for sibling in created_numbered:
            try:
                if sibling.is_symlink() or sibling.is_file():
                    sibling.unlink()
                else:
                    rollback_error = "numbered destination is not a file"
            except OSError as cleanup_exc:
                rollback_error = str(cleanup_exc)
        if os.path.lexists(str(project_path)):
            try:
                if project_path.is_symlink() or project_path.is_file():
                    project_path.unlink()
                else:
                    rollback_error = "unsafe destination is not a file"
            except OSError as cleanup_exc:
                rollback_error = str(cleanup_exc)
        if had_existing and backup_path.exists() and not os.path.lexists(str(project_path)):
            try:
                backup_path.replace(project_path)
            except OSError as restore_exc:
                rollback_error = str(restore_exc)
        if rollback_error is not None:
            raise RuntimeError(
                "Native project save failed and rollback was incomplete ({}): {}".format(
                    rollback_error, project_path
                )
            ) from exc
        raise
    if backup_path.exists():
        backup_path.unlink()


def build():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    CORE_ROOT.mkdir(parents=True, exist_ok=True)
    PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_version": LIBRARY_VERSION,
        "touchdesigner_version": str(app.version),
        "touchdesigner_build": str(app.build),
        "touchdesigner_os": str(app.osName),
        "touchdesigner_architecture": str(app.architecture),
        "project": str(PROJECT_PATH),
        "builder": {
            "path": BUILDER_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": _sha256_file(BUILDER_PATH),
        },
        "effects": [],
        "core": {},
        "shader_errors": {},
        "preview_errors": {},
        "errors": [],
    }
    report_path = BUILD_ROOT / "touchdesigner-build-report.json"
    try:
        manifests = load_manifests()
        if not manifests:
            raise RuntimeError("No package manifests found")
        project_comp = op("/project1")
        if project_comp is None:
            project_comp = root.create(baseCOMP, "project1")
        foreign_nodes = _foreign_project_node_names(project_comp)
        if foreign_nodes:
            raise RuntimeError(
                "Native library builds require a blank /project1; unrelated top-level operators: {}".format(
                    ", ".join(foreign_nodes)
                )
            )
        existing = _existing_owned_nodes(project_comp)
        template_nodes = _default_template_nodes(project_comp)
        for node in [*existing, *template_nodes]:
            node.destroy()
        library, rack_path = build_library(project_comp, manifests, report)
        build_demo(project_comp, rack_path)
        report["benchmark_data"] = str(_write_benchmark_data(report))
        if report["shader_errors"]:
            raise RuntimeError("{} effects have GLSL errors".format(len(report["shader_errors"])))
        if report["preview_errors"]:
            raise RuntimeError("{} previews could not be saved".format(len(report["preview_errors"])))
        _save_project_atomically()
    except Exception as exc:
        report["errors"].append({"error": str(exc), "traceback": traceback.format_exc()})
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    debug(
        "TD ImageFX build complete",
        str(PROJECT_PATH),
        "effects",
        len(report["effects"]),
        "report",
        str(report_path),
    )
    return report


if __name__ == "__main__":
    build()
