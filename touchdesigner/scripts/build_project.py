"""Build the native TD ImageFX .toe and .tox assets inside TouchDesigner.

Run from TouchDesigner's Textport:

    script = r"C:/path/to/video-effects/touchdesigner/scripts/build_project.py"
    exec(compile(open(script, encoding="utf-8").read(), script, "exec"),
         {"__file__": script, "__name__": "__main__"})

Before rebuilding, run ``python tools/verify_repository.py`` from the checkout
to validate source files, manifests, feeds, entrypoints, and version metadata.

The script only creates or updates operators inside ``/project1/td_imagefx`` and
``/project1/imagefx_demo``. Package source files remain text-first on disk.
"""

from __future__ import annotations

import json
import re
import statistics
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
LIBRARY_VERSION = "0.2.0"
RACK_SLOT_COUNT = 8

PREVIEW_PARAMETER_OVERRIDES = {
    "tdimagefx.color.channel-mixer": {"Redfromgreen": 0.35, "Bluefromred": 0.25},
    "tdimagefx.color.exposure": {"Exposure": 0.75, "Contrast": 1.15},
    "tdimagefx.color.hsv-shift": {"Hue": 0.18, "Saturation": 1.25},
    "tdimagefx.color.levels": {"Inputblack": 0.08, "Gamma": 0.78},
    "tdimagefx.color.lift-gamma-gain": {"Liftr": 0.08, "Gammag": 0.82, "Gainb": 1.2},
    "tdimagefx.color.temperature-tint": {"Temperature": 0.35, "Tint": -0.2},
    "tdimagefx.temporal.feedback-trails": {"Offsetx": 0.018, "Offsety": -0.012},
    "tdimagefx.temporal.feedback-rotate": {"Angle": 0.22, "Scale": 0.94},
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
    fragColor = TDOutputSwizzle(vec4(color, 1.0));
}
""".strip()

SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from tdimagefx import Version
from tdimagefx.manifest import load_manifest as _load_validated_manifest
from tdimagefx.paths import validate_package_path


def _read_text(path):
    return Path(path).read_text(encoding="utf-8")


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


def _set_par_defaults(par, definition):
    if "default" in definition:
        try:
            par.default = definition["default"]
        except Exception:
            pass
        par.val = definition["default"]
    if "min" in definition:
        par.min = definition["min"]
        par.normMin = definition["min"]
        par.clampMin = True
    if "max" in definition:
        par.max = definition["max"]
        par.normMax = definition["max"]
        par.clampMax = True


def _append_parameter(comp, page, definition):
    name = definition["name"]
    label = definition.get("label", name)
    par_type = definition.get("type", "float")
    if par_type == "toggle":
        page.appendToggle(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    if par_type == "pulse":
        page.appendPulse(name, label=label)
        return [comp.par[name]]
    if par_type == "string":
        page.appendStr(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    if par_type == "menu":
        page.appendMenu(name, label=label)
        par = comp.par[name]
        par.menuNames = list(definition.get("menu_names", []))
        par.menuLabels = list(definition.get("menu_labels", par.menuNames))
        _set_par_defaults(par, definition)
        return [par]
    if par_type in {"rgb", "rgba"}:
        getattr(page, "append{}".format(par_type.upper()))(name, label=label)
        suffixes = "rgb" if par_type == "rgb" else "rgba"
        pars = [comp.par[name + suffix] for suffix in suffixes]
        defaults = list(definition.get("default", [0.0] * len(suffixes)))
        if par_type == "rgba" and len(defaults) < 4:
            defaults.append(1.0)
        for index, par in enumerate(pars):
            _set_par_defaults(par, {"default": defaults[index], "min": 0.0, "max": 1.0})
        return pars
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
        return pars
    if par_type == "int":
        page.appendInt(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    if par_type in {"file", "folder", "operator"}:
        method = {"file": "appendFile", "folder": "appendFolder", "operator": "appendOP"}[par_type]
        getattr(page, method)(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    page.appendFloat(name, label=label)
    par = comp.par[name]
    _set_par_defaults(par, definition)
    return [par]


def _append_system_parameters(comp, manifest):
    page = comp.appendCustomPage("Package")
    definitions = []
    if any(definition.get("name") == "Time" for definition in manifest.get("parameters", [])):
        definitions.append(
            {"name": "Timescale", "label": "Time Scale", "type": "float", "default": 1.0, "min": -10.0, "max": 10.0}
        )
    definitions.extend((
        {"name": "Packageid", "label": "Package ID", "type": "string", "default": manifest["id"]},
        {"name": "Packageversion", "label": "Package Version", "type": "string", "default": manifest["version"]},
        {"name": "Fxapi", "label": "FX API", "type": "string", "default": manifest.get("fx_api", "1.0")},
        {"name": "Processingmodel", "label": "Processing Model", "type": "string", "default": (manifest.get("processing") or {}).get("model", "single_pass")},
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
    return instance


def _processing(manifest):
    value = dict(manifest.get("processing") or {})
    value.setdefault("model", "single_pass")
    value.setdefault("gpu_cost", "low")
    value.setdefault("capabilities", [])
    value.setdefault("passes", [manifest["entrypoints"]["shader"]])
    value.setdefault("history_frames", 0)
    return value


def _shader_pass(effect, manifest, pass_index, relative_path, inputs, parameter_bindings):
    shader_path = _manifest_asset(
        manifest, relative_path, "$.processing.passes[{}]".format(pass_index)
    )
    shader_source = _read_text(shader_path)
    shader_dat = effect.create(textDAT, "pixel_shader_{}".format(pass_index + 1))
    shader_dat.text = shader_source
    shader_dat.nodeX = pass_index * 230 - 100
    shader_dat.nodeY = -300

    glsl = effect.create(glslTOP, "effect_glsl_{}".format(pass_index + 1))
    glsl.nodeX = pass_index * 230
    glsl.nodeY = 0
    for input_index, input_node in enumerate(inputs):
        input_node.outputConnectors[0].connect(glsl.inputConnectors[input_index])
    glsl.par.pixeldat = shader_dat.path
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

    info = effect.create(infoDAT, "shader_info_{}".format(pass_index + 1))
    info.par.op = glsl.path
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

    effect_page = effect.appendCustomPage("ImageFX")
    parameter_bindings = []
    for definition in manifest.get("parameters", []):
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

    history = None
    if processing["model"] in {"temporal", "simulation"}:
        history = effect.create(feedbackTOP, "history_feedback")
        input_nodes[0].outputConnectors[0].connect(history.inputConnectors[0])
        history.nodeX = -210
        history.nodeY = -140
        if history.par["reset"] is not None:
            history.par.reset = False

    glsl_nodes = []
    previous = None
    pass_paths = list(processing.get("passes") or [manifest["entrypoints"]["shader"]])
    for pass_index, relative_path in enumerate(pass_paths):
        if pass_index == 0:
            pass_inputs = list(input_nodes)
            if history is not None:
                pass_inputs = [input_nodes[0], history, *input_nodes[1:]]
        else:
            pass_inputs = [previous, input_nodes[0], *input_nodes[1:]]
        previous = _shader_pass(
            effect, manifest, pass_index, relative_path, pass_inputs, parameter_bindings
        )
        glsl_nodes.append(previous)

    processed_output = previous
    if history is not None:
        feedback_target = effect.create(nullTOP, "feedback_target")
        previous.outputConnectors[0].connect(feedback_target.inputConnectors[0])
        feedback_target.nodeX = len(glsl_nodes) * 230
        feedback_target.nodeY = -80
        history.par.top = feedback_target.path
        processed_output = feedback_target

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
    tox_path.parent.mkdir(parents=True, exist_ok=True)
    effect.save(str(tox_path), createFolders=True)
    effect.par.externaltox = tox_path.relative_to(PROJECT_ROOT).as_posix()
    effect.par.enableexternaltox = True
    effect.par.savebackup = True
    if effect.par["relpath"] is not None:
        effect.par.relpath = "project"
    report["effects"].append({
        "id": manifest["id"],
        "version": manifest["version"],
        "tox": str(tox_path),
        "model": processing["model"],
        "gpu_cost": processing["gpu_cost"],
        "capabilities": list(processing["capabilities"]),
        "passes": len(pass_paths),
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

    parexec = updater.create(parameterexecuteDAT, "parameter_callbacks")
    parexec.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "updater_parameter_callbacks.py")
    parexec.par.op = updater.path
    parexec.par.pars = "Checkupdates Autocheck Intervalhours"
    parexec.par.valuechange = True
    parexec.par.onpulse = True
    parexec.par.custom = True
    parexec.par.builtin = False
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
    _append_parameter(rack, page, {"name": "Time", "type": "float", "default": 0.0, "min": -100000.0, "max": 100000.0})
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
    rack.par.Time.expr = "absTime.seconds * me.par.Timescale if me.par.Autotime else 0.0"
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
        source_connector.connect(slot.inputConnectors[0])
        if len(slot.inputConnectors) > 1:
            rack_input.outputConnectors[0].connect(slot.inputConnectors[1])
        if slot.par["Enable"] is not None:
            slot.par.Enable.expr = "parent().par.Slot{}enable".format(index)
        if slot.par["Mix"] is not None:
            slot.par.Mix.expr = "parent().par.Slot{}mix".format(index)
        if slot.par["Time"] is not None:
            slot.par.Time.expr = "parent().par.Time"
        rack.store("slot{}_package".format(index), {"id": package_id, "version": manifest["version"]})
        source_connector = slot.outputConnectors[0]

    rack_output = rack.create(outTOP, "out1_image")
    source_connector.connect(rack_output.inputConnectors[0])
    rack_output.nodeX = 600
    rack_output.nodeY = 0
    rack_output.display = True
    rack_output.render = True

    configure_extension(rack, "FxRackExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "FxRackExt.py")
    parexec = rack.create(parameterexecuteDAT, "parameter_callbacks")
    parexec.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "rack_parameter_callbacks.py")
    parexec.par.op = rack.path
    parexec.par.pars = "Slot* Reset Reloadall Bypassall Enableall Exportpreset Importpreset Savepreset Loadpreset"
    parexec.par.valuechange = True
    parexec.par.onpulse = True
    parexec.par.custom = True
    parexec.par.builtin = False
    parexec.nodeX = 400
    parexec.nodeY = -250

    rack_path = CORE_ROOT / "FxRack.tox"
    rack.save(str(rack_path), createFolders=True)
    return rack, rack_path


def build_browser(parent_comp, manifests):
    browser = parent_comp.create(baseCOMP, "fx_browser")
    browser.color = (0.14, 0.38, 0.30)
    browser.comment = "Search, filter, favorite, inspect, and create ImageFX packages"
    page = browser.appendCustomPage("Browser")
    package_ids = [manifest["id"] for manifest in manifests]
    package_labels = [manifest["name"] for manifest in manifests]
    categories = sorted({manifest["category"] for manifest in manifests})
    definitions = (
        {"name": "Search", "type": "string", "default": ""},
        {"name": "Category", "type": "menu", "default": "all", "menu_names": ["all", *categories], "menu_labels": ["All", *[value.title() for value in categories]]},
        {"name": "Tags", "type": "string", "default": ""},
        {"name": "Favorites", "type": "string", "default": "[]"},
        {"name": "Favoritesonly", "label": "Favorites Only", "type": "toggle", "default": False},
        {"name": "Selectedid", "label": "Selected Effect", "type": "menu", "default": package_ids[0], "menu_names": package_ids, "menu_labels": package_labels},
        {"name": "Target", "label": "Creation Target", "type": "operator", "default": "../../effects"},
        {"name": "Refresh", "type": "pulse"},
        {"name": "Create", "label": "Create Selected", "type": "pulse"},
        {"name": "Togglefavorite", "label": "Toggle Favorite", "type": "pulse"},
        {"name": "Status", "type": "string", "default": "Ready"},
    )
    for definition in definitions:
        _append_parameter(browser, page, definition)

    results = browser.create(tableDAT, "results")
    columns = ("id", "name", "version", "category", "tags", "favorite", "compatibility", "model", "gpu_cost", "component")
    results.appendRow(columns)
    for manifest in manifests:
        processing = _processing(manifest)
        compatibility = manifest["compatibility"]
        label = "TD {}+ | {} | {}".format(
            compatibility["touchdesigner_min_build"],
            ",".join(compatibility["os"]),
            ",".join(compatibility["architectures"]),
        )
        row = {
            "id": manifest["id"], "name": manifest["name"], "version": manifest["version"],
            "category": manifest["category"], "tags": ", ".join(manifest["tags"]),
            "favorite": "0", "compatibility": label, "model": processing["model"],
            "gpu_cost": processing["gpu_cost"], "component": manifest["entrypoints"]["touchdesigner_component"],
        }
        results.appendRow(tuple(row[column] for column in columns))
    results.nodeX = -140
    results.nodeY = 0

    configure_extension(browser, "ImageFXBrowserExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "ImageFXBrowserExt.py")
    parexec = browser.create(parameterexecuteDAT, "parameter_callbacks")
    parexec.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "browser_parameter_callbacks.py")
    parexec.par.op = browser.path
    parexec.par.pars = "Search Category Tags Favorites Favoritesonly Refresh Create Togglefavorite"
    parexec.par.valuechange = True
    parexec.par.onpulse = True
    parexec.par.custom = True
    parexec.par.builtin = False
    parexec.nodeX = 120
    parexec.nodeY = -180

    browser_path = CORE_ROOT / "FxBrowser.tox"
    browser.save(str(browser_path), createFolders=True)
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


def _save_preview(effect, package_id, report):
    preview_path = PREVIEW_ROOT / "{}.png".format(package_id)
    output = effect.op("out1_image")
    if output is None:
        raise RuntimeError("{} has no output TOP".format(package_id))
    previous_values = {}
    history = effect.op("history_feedback")
    history_reset = None
    time_parameter = effect.par["Time"]
    time_state = None
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
        if history is not None and history.par["reset"] is not None:
            history_reset = history.par.reset.eval()
            history.par.reset = True
        output.cook(force=True)
        output.save(str(preview_path), asynchronous=False, createFolders=True, quality=1.0)
    except Exception as exc:
        report["preview_errors"][package_id] = str(exc)
    finally:
        if history_reset is not None:
            history.par.reset = history_reset
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
    catalog.appendRow((
        "id", "name", "version", "kind", "category", "channel", "description", "stateful", "tags",
        "processing_model", "gpu_cost", "capabilities", "compatibility", "preview", "component",
    ))
    for manifest in manifests:
        processing = _processing(manifest)
        compatibility = manifest["compatibility"]
        catalog.appendRow((
            manifest["id"], manifest["name"], manifest["version"], manifest["kind"], manifest["category"],
            manifest["channel"], manifest["description"], str(manifest["stateful"]), ", ".join(manifest["tags"]),
            processing["model"], processing["gpu_cost"], ", ".join(processing["capabilities"]),
            "TD {}+ | {} | {}".format(
                compatibility["touchdesigner_min_build"], ",".join(compatibility["os"]),
                ",".join(compatibility["architectures"]),
            ),
            "docs/gallery/{}.png".format(manifest["id"]),
            manifest["entrypoints"]["touchdesigner_component"],
        ))
    catalog.nodeX = -400
    catalog.nodeY = -250

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
    effect_components = {}
    for index, manifest in enumerate(manifests):
        effect = build_effect(effects_parent, manifest, report)
        effect.nodeX = (index % 4) * 230
        effect.nodeY = -(index // 4) * 180
        preview_source.outputConnectors[0].connect(effect.inputConnectors[0])
        for input_index in range(1, len(manifest.get("inputs", []))):
            preview_aux.outputConnectors[0].connect(effect.inputConnectors[input_index])
        report["effects"][-1].update(_benchmark_effect(effect))
        report["effects"][-1]["preview"] = str(_save_preview(effect, manifest["id"], report))
        effect_components[manifest["id"]] = effect

    core_parent = library.create(baseCOMP, "core")
    core_parent.nodeX = 260
    core_parent.nodeY = 100
    updater = build_update_manager(library)
    updater.nodeX = 520
    updater.nodeY = 100
    rack, rack_path = build_rack(core_parent, manifests)
    rack.nodeX = 0
    rack.nodeY = 0
    browser, browser_path = build_browser(core_parent, manifests)
    browser.nodeX = 260
    browser.nodeY = 0

    configure_extension(library, "ImageFXLibraryExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "ImageFXLibraryExt.py")
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
        existing = _existing_owned_nodes(project_comp)
        for node in existing:
            node.destroy()
        library, rack_path = build_library(project_comp, manifests, report)
        build_demo(project_comp, rack_path)
        report["benchmark_data"] = str(_write_benchmark_data(report))
        if report["shader_errors"]:
            raise RuntimeError("{} effects have GLSL errors".format(len(report["shader_errors"])))
        if report["preview_errors"]:
            raise RuntimeError("{} previews could not be saved".format(len(report["preview_errors"])))
        project.save(str(PROJECT_PATH), saveExternalToxs=False)
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
