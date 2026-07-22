"""Exhaustive live response validation for every published ImageFX control.

The validator temporarily reduces the demo to 320x180, disables the dedicated
modules, loads each latest package into rack slot 1, and exercises every
numeric component plus toggles, rack mix, time, and per-effect time scale. It
restores the complete rack preset, demo routing, resolution, and source time in
a ``finally`` block and never saves the TouchDesigner project.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT
    / "build"
    / "envoy-validation"
    / "all-effect-parameters.json"
)
DEMO_PATH = "/project1/imagefx_demo"
RACK_PATH = DEMO_PATH + "/fx_rack"
RACK_OUTPUT_PATH = RACK_PATH + "/out1_image"
SOURCE_PATH = DEMO_PATH + "/source_image"
SOURCE_SHADER_PATH = DEMO_PATH + "/source_image_shader"
SLOT_COUNT = 8
QA_WIDTH = 320
QA_HEIGHT = 180
DIFFERENCE_THRESHOLD = 1.0e-6
NUMERIC_TYPES = {"float", "int", "xy", "uv", "xyz", "rgb", "rgba"}
COMPONENT_SUFFIXES = {
    "xy": ("x", "y"),
    "uv": ("u", "v"),
    "xyz": ("x", "y", "z"),
    "rgb": ("r", "g", "b"),
    "rgba": ("r", "g", "b", "a"),
}
READ_ONLY_SLOT_PARAMETERS = {
    "Enable",
    "Mix",
    "Time",
    "Packageid",
    "Packageversion",
    "Fxapi",
    "Processingmodel",
    "Historyframes",
    "Gpucost",
    "Capabilities",
    "Status",
}
MASTER_ACTIVATORS = {
    "Amount",
    "Coloramount",
    "Strength",
    "Intensity",
    "Opacity",
    "Feedback",
    "Injection",
    "Advection",
    "Highlight",
    "Softknee",
    "Chance",
    "Density",
    "Spread",
    "Distortion",
}
CONDITIONAL_CONTROL_OVERRIDES = {
    "tdimagefx.blur.bokeh-blur": {
        "Highlight": {"Radius": 32.0},
    },
    "tdimagefx.color.exposure": {
        "Pivot": {"Exposure": 0.0, "Offset": 0.0, "Contrast": 2.0},
    },
    "tdimagefx.color.tone-map": {
        "Whitepoint": {"Mode": 0.0, "Exposure": 2.0},
    },
    "tdimagefx.key.despill": {
        "Keycolor": {
            "Keycolorr": 0.65,
            "Keycolorg": 0.45,
            "Keycolorb": 0.20,
            "Keycolora": 1.0,
            "Amount": 1.0,
            "Balance": 0.15,
            "Restoreluma": 0.0,
        },
    },
    "tdimagefx.stylize.vignette": {
        "Color": {"Amount": 1.0, "Softness": 0.65},
    },
    "tdimagefx.transform.fit-fill": {
        "Alignment": {"Mode": 1.0, "Frameaspect": 1.0},
        "Background": {
            "Mode": 0.0,
            "Frameaspect": 1.0,
            "Backgrounda": 1.0,
        },
    },
}
SOURCE_FIXTURE_PACKAGES = {
    "tdimagefx.blur.bokeh-blur": "hdr",
    "tdimagefx.key.despill": "green-spill",
}
PATTERN_STATE_FIXTURE_PACKAGES = {
    "tdimagefx.simulation.cellular-automata",
    "tdimagefx.simulation.reaction-diffusion",
    "tdimagefx.temporal.stutter",
}
PACKAGE_ACTIVATION_OVERRIDES = {
    "tdimagefx.temporal.stutter": {"Hold": 1.0},
}


def _version_key(text):
    core, _separator, prerelease = str(text).partition("-")
    values = tuple(int(value) for value in core.split("."))
    return values, prerelease == "", prerelease


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: {}".format(key))
        result[key] = value
    return result


def _latest_manifests():
    latest = {}
    for path in sorted((PROJECT_ROOT / "packages").glob("*/*/package.json")):
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        current = latest.get(manifest["id"])
        if current is None or _version_key(manifest["version"]) > _version_key(
            current["manifest"]["version"]
        ):
            latest[manifest["id"]] = {"manifest": manifest, "path": str(path)}
    return [latest[key] for key in sorted(latest)]


def _messages(operator, method_name):
    method = getattr(operator, method_name, None)
    if method is None:
        return ["{} is unavailable".format(method_name)]
    try:
        value = method(recurse=True)
    except TypeError:
        value = method(True)
    if value is None:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    try:
        return [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        text = str(value).strip()
        return [text] if text else []


def _pattern_state_seed(slot):
    shader = slot.create(textDAT, "validator_state_seed_shader")
    shader.text = """layout(location = 0) out vec4 fragColor;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
    vec2 cell = floor(vUV.st * vec2(97.0, 53.0));
    float alive = step(0.46, hash21(cell));
    float chemical = mix(0.12, 0.88, hash21(cell + vec2(19.0, 37.0)));
    fragColor = TDOutputSwizzle(vec4(alive, chemical, 1.0, 0.0));
}
"""
    seed = slot.create(glslTOP, "validator_state_seed")
    seed.par.pixeldat = seed.relativePath(shader)
    if seed.par["glslversion"] is not None:
        seed.par.glslversion = "glsl460"
    if seed.par["compilebehavior"] is not None:
        seed.par.compilebehavior = "stalluntildone"
    if seed.par["outputresolution"] is not None:
        seed.par.outputresolution = "custom"
        seed.par.resolutionw = QA_WIDTH
        seed.par.resolutionh = QA_HEIGHT
    seed.cook(force=True)
    return seed, shader


def _capture(top, slot, stateful=False, pattern_state=False):
    temporary_seed = None
    temporary_shader = None
    history_seed = (
        slot.op("history_seed")
        if stateful and not pattern_state and slot is not None
        else None
    )
    history_input = None
    state_input = None
    saved_seed = {}
    if pattern_state and slot is not None:
        temporary_seed, temporary_shader = _pattern_state_seed(slot)
        history_input = slot.op("history_cache") or slot.op("history_feedback")
        state_shader = slot.op("effect_glsl_1")
        if history_input is not None and state_shader is not None:
            state_input = state_shader.inputConnectors[1]
            try:
                state_input.disconnect()
            except Exception:
                pass
            temporary_seed.outputConnectors[0].connect(state_input)
    elif history_seed is not None:
        for name, value in (
            ("colorr", 0.23),
            ("colorg", 0.47),
            ("colorb", 0.71),
            ("colora", 1.0),
        ):
            parameter = history_seed.par[name]
            if parameter is not None:
                saved_seed[name] = parameter.eval()
                parameter.val = value
        history_seed.cook(force=True)
        history_input = slot.op("history_cache") or slot.op("history_feedback")
        state_shader = slot.op("effect_glsl_1")
        if history_input is not None and state_shader is not None:
            state_input = state_shader.inputConnectors[1]
            try:
                state_input.disconnect()
            except Exception:
                pass
            history_seed.outputConnectors[0].connect(state_input)
    reset = slot.par["Reset"] if slot is not None else None
    if reset is not None:
        try:
            reset.pulse()
        except Exception:
            try:
                reset.val = True
                reset.val = False
            except Exception:
                pass
    try:
        for _index in range(2 if stateful else 1):
            top.cook(force=True)
        image = top.numpyArray(delayed=False, writable=False)
        if image is None:
            image = top.numpyArray(delayed=False, writable=False)
        if image is None:
            raise RuntimeError(
                "TOP.numpyArray() returned no image for {}".format(top.path)
            )
        return np.array(image, dtype=np.float32, copy=True)
    finally:
        if state_input is not None and history_input is not None:
            try:
                state_input.disconnect()
            except Exception:
                pass
            history_input.outputConnectors[0].connect(state_input)
        if history_seed is not None:
            for name, value in saved_seed.items():
                history_seed.par[name].val = value
        if temporary_seed is not None:
            temporary_seed.destroy()
        if temporary_shader is not None:
            temporary_shader.destroy()


def _difference(left, right):
    if left.shape != right.shape:
        return None
    return float(np.mean(np.abs(left - right)))


def _component_names(definition):
    suffixes = COMPONENT_SUFFIXES.get(definition.get("type"))
    if suffixes is None:
        return (definition["name"],)
    return tuple(definition["name"] + suffix for suffix in suffixes)


def _component_defaults(definition):
    names = _component_names(definition)
    default = definition.get("default", 0)
    if isinstance(default, (list, tuple)):
        values = list(default)
        if definition.get("type") == "rgba" and len(values) < 4:
            values.append(1.0)
        return dict(zip(names, values))
    return {names[0]: default}


def _range(definition):
    if definition.get("type") in {"rgb", "rgba"}:
        return 0.0, 1.0
    return float(definition.get("min", 0.0)), float(definition.get("max", 1.0))


def _test_values(definition, component_index=0):
    minimum, maximum = _range(definition)
    span = maximum - minimum
    if not math.isfinite(span) or span <= 0.0:
        raise ValueError("Parameter range is not sweepable")
    low_fraction = 0.19 + 0.03 * (component_index % 3)
    high_fraction = 0.73 - 0.02 * (component_index % 2)
    if definition.get("type") == "int":
        low = int(round(minimum + span * low_fraction))
        high = int(round(minimum + span * high_fraction))
        if low == high:
            low = int(minimum)
            high = int(maximum)
        return low, high
    return minimum + span * low_fraction, minimum + span * high_fraction


def _activation_value(definition, component_index=0):
    minimum, maximum = _range(definition)
    span = maximum - minimum
    fraction = (0.37, 0.61, 0.79, 0.68)[component_index % 4]
    value = minimum + span * fraction
    if definition.get("type") == "int":
        return int(round(value))
    return value


def _set_parameter(slot, name, value):
    parameter = slot.par[name]
    if parameter is None:
        raise RuntimeError("Loaded component is missing parameter {}".format(name))
    parameter.val = value


def _source_fixture_text(original, package_id):
    marker = "fragColor = TDOutputSwizzle(vec4(color, alpha));"
    if marker not in original:
        raise RuntimeError("Demo source shader fixture marker is missing")
    fixture = SOURCE_FIXTURE_PACKAGES.get(package_id)
    if fixture == "hdr":
        replacement = "color *= 3.0;\n    " + marker
    elif fixture == "green-spill":
        replacement = (
            "color = mix(color, vec3(0.04, 1.30, 0.10), 0.82);\n    "
            + marker
        )
    else:
        return original
    return original.replace(marker, replacement, 1)


def _restore_defaults(slot, manifest, rack):
    rack.par.Slot1enable = True
    rack.par.Slot1mix = 1.0
    rack.par.Slot1moddepth = 0.0
    rack.par.Slot1modrate = 1.0
    rack.par.Slot1modstate = "off"
    rack.par.Autotime = False
    rack.par.Timescale = 1.0
    rack.par.Manualtime = 0.731
    if slot.par["Timescale"] is not None:
        slot.par.Timescale = 1.0
    for definition in manifest.get("parameters", []):
        if definition.get("type") == "toggle" and definition["name"] != "Enable":
            _set_parameter(slot, definition["name"], definition.get("default", False))
        elif definition.get("type") in NUMERIC_TYPES and definition["name"] not in {
            "Mix",
            "Time",
        }:
            for name, value in _component_defaults(definition).items():
                _set_parameter(slot, name, value)


def _activate(slot, manifest, broad=False, skip=None):
    skip = set(skip or ())
    for definition in manifest.get("parameters", []):
        name = definition["name"]
        if name in skip or name in {"Enable", "Mix", "Time"}:
            continue
        parameter_type = definition.get("type")
        if parameter_type == "toggle":
            _set_parameter(slot, name, True)
            continue
        if parameter_type not in NUMERIC_TYPES:
            continue
        if not broad and name not in MASTER_ACTIVATORS:
            continue
        for index, component_name in enumerate(_component_names(definition)):
            _set_parameter(
                slot,
                component_name,
                _activation_value(definition, index),
            )
    for name, value in PACKAGE_ACTIVATION_OVERRIDES.get(manifest["id"], {}).items():
        if name not in skip:
            _set_parameter(slot, name, value)


def _range_diagnostics(parameter, definition):
    expected_min, expected_max = _range(definition)
    tolerance = 1.0e-5 * max(1.0, abs(expected_min), abs(expected_max))
    return {
        "min": float(parameter.min),
        "max": float(parameter.max),
        "norm_min": float(parameter.normMin),
        "norm_max": float(parameter.normMax),
        "clamp_min": bool(parameter.clampMin),
        "clamp_max": bool(parameter.clampMax),
        "expected_min": expected_min,
        "expected_max": expected_max,
        "valid": (
            abs(float(parameter.min) - expected_min) <= tolerance
            and abs(float(parameter.max) - expected_max) <= tolerance
            and float(parameter.normMin) <= float(parameter.normMax)
            and bool(parameter.clampMin)
            and bool(parameter.clampMax)
        ),
    }


def _apply_conditional_overrides(slot, manifest, definition):
    package_overrides = CONDITIONAL_CONTROL_OVERRIDES.get(manifest["id"], {})
    overrides = package_overrides.get(definition["name"], {})
    for name, value in overrides.items():
        _set_parameter(slot, name, value)
    return bool(overrides)


def _uses_pattern_state_fixture(manifest):
    return manifest["id"] in PATTERN_STATE_FIXTURE_PACKAGES


def _sweep_component(output, slot, rack, manifest, definition, component_name):
    component_index = _component_names(definition).index(component_name)
    low, high = _test_values(definition, component_index)
    stateful = (manifest.get("processing") or {}).get("model") in {
        "temporal",
        "simulation",
    }
    best = None
    contexts = ["targeted", "broad"]
    if definition["name"] in CONDITIONAL_CONTROL_OVERRIDES.get(
        manifest["id"], {}
    ):
        contexts.insert(0, "conditional")
    for context in contexts:
        _restore_defaults(slot, manifest, rack)
        _activate(
            slot,
            manifest,
            broad=context == "broad",
            skip={definition["name"]},
        )
        if context == "conditional":
            _apply_conditional_overrides(slot, manifest, definition)
        _set_parameter(slot, component_name, low)
        low_image = _capture(
            output,
            slot,
            stateful=stateful,
            pattern_state=(
                _uses_pattern_state_fixture(manifest)
                and definition["name"] != "Seed"
            ),
        )
        low_evaluated = slot.par[component_name].eval()
        _set_parameter(slot, component_name, high)
        high_image = _capture(
            output,
            slot,
            stateful=stateful,
            pattern_state=(
                _uses_pattern_state_fixture(manifest)
                and definition["name"] != "Seed"
            ),
        )
        high_evaluated = slot.par[component_name].eval()
        difference = _difference(low_image, high_image)
        candidate = {
            "context": context,
            "difference": difference,
            "finite": bool(
                np.isfinite(low_image).all() and np.isfinite(high_image).all()
            ),
            "requested_low": low,
            "evaluated_low": low_evaluated,
            "requested_high": high,
            "evaluated_high": high_evaluated,
            "accepts_values": (
                abs(float(low_evaluated) - float(low)) <= 1.0e-6
                and abs(float(high_evaluated) - float(high)) <= 1.0e-6
            ),
        }
        if best is None or (candidate["difference"] or 0.0) > (
            best["difference"] or 0.0
        ):
            best = candidate
        if (
            candidate["difference"] is not None
            and candidate["difference"] > DIFFERENCE_THRESHOLD
            and candidate["finite"]
        ):
            break
    best["range"] = _range_diagnostics(slot.par[component_name], definition)
    best["responds"] = bool(
        best["difference"] is not None
        and best["difference"] > DIFFERENCE_THRESHOLD
    )
    best["ok"] = bool(
        best["responds"]
        and best["finite"]
        and best["accepts_values"]
        and best["range"]["valid"]
    )
    return best


def _sweep_rack_mix(output, slot, rack, manifest):
    stateful = (manifest.get("processing") or {}).get("model") in {
        "temporal",
        "simulation",
    }
    _restore_defaults(slot, manifest, rack)
    _activate(slot, manifest, broad=True)
    rack.par.Slot1mix = 0.0
    low = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    rack.par.Slot1mix = 1.0
    high = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    difference = _difference(low, high)
    return {
        "difference": difference,
        "finite": bool(np.isfinite(low).all() and np.isfinite(high).all()),
        "responds": bool(difference is not None and difference > DIFFERENCE_THRESHOLD),
    }


def _sweep_toggle(output, slot, rack, manifest, name):
    stateful = (manifest.get("processing") or {}).get("model") in {
        "temporal",
        "simulation",
    }
    _restore_defaults(slot, manifest, rack)
    _activate(slot, manifest, broad=True, skip={name})
    if name == "Enable":
        rack.par.Slot1enable = False
    else:
        _set_parameter(slot, name, False)
    off = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    if name == "Enable":
        rack.par.Slot1enable = True
    else:
        _set_parameter(slot, name, True)
    on = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    difference = _difference(off, on)
    return {
        "difference": difference,
        "finite": bool(np.isfinite(off).all() and np.isfinite(on).all()),
        "responds": bool(difference is not None and difference > DIFFERENCE_THRESHOLD),
    }


def _sweep_time(output, slot, rack, manifest):
    stateful = (manifest.get("processing") or {}).get("model") in {
        "temporal",
        "simulation",
    }
    _restore_defaults(slot, manifest, rack)
    _activate(slot, manifest, broad=True)
    rack.par.Manualtime = 0.271
    first = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    rack.par.Manualtime = 1.137
    second = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    time_difference = _difference(first, second)

    rack.par.Manualtime = 0.823
    slot.par.Timescale = 0.31
    slow = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    slot.par.Timescale = 1.47
    fast = _capture(
        output,
        slot,
        stateful=stateful,
        pattern_state=_uses_pattern_state_fixture(manifest),
    )
    scale_difference = _difference(slow, fast)
    return {
        "time_difference": time_difference,
        "time_responds": bool(
            time_difference is not None and time_difference > DIFFERENCE_THRESHOLD
        ),
        "time_scale_difference": scale_difference,
        "time_scale_responds": bool(
            scale_difference is not None and scale_difference > DIFFERENCE_THRESHOLD
        ),
        "time_expression": str(slot.par.Time.expr),
        "time_read_only": bool(slot.par.Time.readOnly),
        "time_scale_read_only": bool(slot.par.Timescale.readOnly),
        "finite": bool(
            np.isfinite(first).all()
            and np.isfinite(second).all()
            and np.isfinite(slow).all()
            and np.isfinite(fast).all()
        ),
    }


def validate(write_report=True):
    """Exercise every latest package parameter and restore all project state."""

    demo = op(DEMO_PATH)
    rack = op(RACK_PATH)
    output = op(RACK_OUTPUT_PATH)
    source = op(SOURCE_PATH)
    source_shader = op(SOURCE_SHADER_PATH)
    manifests = _latest_manifests()
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "validator": "all-effect-parameters",
        "ok": False,
        "package_count": len(manifests),
        "qa_resolution": [QA_WIDTH, QA_HEIGHT],
        "fixtures": {
            "standard": "animated procedural RGBA source",
            "hdr": "16-bit-float procedural source above 1.0 for highlight controls",
            "green_spill": "16-bit-float green-dominant source for despill controls",
            "stateful": "deterministic non-black history seed",
        },
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
    }
    missing = [
        name
        for name, operator in (
            ("demo", demo),
            ("rack", rack),
            ("output", output),
            ("source", source),
            ("source_shader", source_shader),
        )
        if operator is None
    ]
    report["missing_operators"] = missing
    if missing:
        report["error"] = "Required all-parameter validation operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo_names = (
        "Inkflowenabled",
        "Particlesenabled",
        "Glitchenabled",
        "Coloradjustmentenabled",
        "Motionenabled",
        "Referenceparticlefieldenabled",
        "Calligraphicshadowenabled",
        "Inkorbitenabled",
        "Applyvideofx",
        "Resolutionpreset",
        "Customwidth",
        "Customheight",
    )
    saved_demo = {name: demo.par[name].eval() for name in demo_names}
    saved_source_expression = source.par.vec0valuex.expr
    saved_source_value = source.par.vec0valuex.eval()
    saved_source_shader_text = source_shader.text
    saved_source_format = source.par.format.eval()
    saved_timeline_frame = int(root.time.frame)
    saved_timeline_play = bool(root.time.play)
    saved_preset = None
    package_results = []
    restoration_error = None
    try:
        saved_preset = rack.ExportPreset(
            "all-effect-parameter-validator-snapshot",
            indent=0,
        )
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        root.time.play = False
        demo.par.Inkflowenabled = False
        demo.par.Particlesenabled = False
        demo.par.Glitchenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Motionenabled = False
        demo.par.Referenceparticlefieldenabled = False
        demo.par.Calligraphicshadowenabled = False
        demo.par.Inkorbitenabled = False
        demo.par.Applyvideofx = True
        demo.par.Resolutionpreset = "custom"
        demo.par.Customwidth = QA_WIDTH
        demo.par.Customheight = QA_HEIGHT
        for index in range(2, SLOT_COUNT + 1):
            rack.ClearSlot(index)

        for item in manifests:
            manifest = item["manifest"]
            package_id = manifest["id"]
            result = {
                "id": package_id,
                "version": manifest["version"],
                "model": (manifest.get("processing") or {}).get(
                    "model", "single_pass"
                ),
                "numeric": {},
                "toggles": {},
                "errors": [],
            }
            try:
                fixture_text = _source_fixture_text(
                    saved_source_shader_text,
                    package_id,
                )
                if source_shader.text != fixture_text:
                    source_shader.text = fixture_text
                source.par.format = (
                    "rgba16float"
                    if package_id in SOURCE_FIXTURE_PACKAGES
                    else saved_source_format
                )
                source.cook(force=True)
                rack.par.Slot1effect = package_id
                slot = rack.LoadSlot(1, package_id, manifest["version"])
                output.cook(force=True)
                result["resolution"] = [int(output.width), int(output.height)]
                result["read_only"] = {
                    name: bool(slot.par[name].readOnly)
                    for name in sorted(READ_ONLY_SLOT_PARAMETERS)
                    if slot.par[name] is not None
                }
                result["read_only_ok"] = all(result["read_only"].values())

                for definition in manifest.get("parameters", []):
                    parameter_type = definition.get("type")
                    name = definition["name"]
                    if parameter_type == "toggle":
                        result["toggles"][name] = _sweep_toggle(
                            output,
                            slot,
                            rack,
                            manifest,
                            name,
                        )
                    elif parameter_type in NUMERIC_TYPES:
                        if name == "Mix":
                            result["numeric"][name] = _sweep_rack_mix(
                                output,
                                slot,
                                rack,
                                manifest,
                            )
                        elif name == "Time":
                            result["numeric"][name] = _sweep_time(
                                output,
                                slot,
                                rack,
                                manifest,
                            )
                            result["numeric"][name]["responds"] = bool(
                                result["numeric"][name]["time_responds"]
                                and result["numeric"][name][
                                    "time_scale_responds"
                                ]
                            )
                            result["numeric"][name]["ok"] = bool(
                                result["numeric"][name]["responds"]
                                and result["numeric"][name]["finite"]
                                and result["numeric"][name]["time_read_only"]
                                and not result["numeric"][name][
                                    "time_scale_read_only"
                                ]
                                and "me.par.Timescale" in result["numeric"][
                                    name
                                ]["time_expression"]
                            )
                            result["numeric"]["Timescale"] = {
                                "difference": result["numeric"][name][
                                    "time_scale_difference"
                                ],
                                "finite": result["numeric"][name]["finite"],
                                "responds": result["numeric"][name][
                                    "time_scale_responds"
                                ],
                            }
                        else:
                            for component_name in _component_names(definition):
                                result["numeric"][component_name] = _sweep_component(
                                    output,
                                    slot,
                                    rack,
                                    manifest,
                                    definition,
                                    component_name,
                                )

                result["shader_errors"] = _messages(slot, "errors")
                result["shader_warnings"] = _messages(slot, "warnings")
                numeric_ok = all(
                    value.get("responds")
                    and value.get("finite")
                    and value.get("ok", True)
                    for value in result["numeric"].values()
                )
                toggles_ok = all(
                    value.get("responds") and value.get("finite")
                    for value in result["toggles"].values()
                )
                result["ok"] = bool(
                    numeric_ok
                    and toggles_ok
                    and result["read_only_ok"]
                    and result["resolution"] == [QA_WIDTH, QA_HEIGHT]
                    and not result["shader_errors"]
                    and not result["shader_warnings"]
                )
            except Exception as exc:
                result["errors"].append(
                    "{}: {}".format(type(exc).__name__, exc)
                )
                result["ok"] = False
            package_results.append(result)
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        try:
            if saved_preset is not None:
                rack.ImportPreset(saved_preset)
            for name, value in saved_demo.items():
                demo.par[name].val = value
            if saved_source_expression:
                source.par.vec0valuex.expr = saved_source_expression
            else:
                source.par.vec0valuex.expr = ""
                source.par.vec0valuex = saved_source_value
            source_shader.text = saved_source_shader_text
            source.par.format = saved_source_format
            source.cook(force=True)
            root.time.frame = saved_timeline_frame
            root.time.play = saved_timeline_play
            output.cook(force=True)
        except Exception as exc:
            restoration_error = "{}: {}".format(type(exc).__name__, exc)

    numeric_results = [
        value
        for package in package_results
        for value in package.get("numeric", {}).values()
    ]
    toggle_results = [
        value
        for package in package_results
        for value in package.get("toggles", {}).values()
    ]
    failed_packages = [
        package["id"] for package in package_results if not package.get("ok")
    ]
    checks = {
        "contains_exactly_96_latest_packages": len(package_results) == 96,
        "every_numeric_control_responds": bool(numeric_results)
        and all(value.get("responds") for value in numeric_results),
        "every_numeric_capture_is_finite": bool(numeric_results)
        and all(value.get("finite") for value in numeric_results),
        "every_numeric_control_accepts_valid_values_and_ranges": all(
            value.get("ok", True) for value in numeric_results
        ),
        "every_toggle_responds": bool(toggle_results)
        and all(value.get("responds") for value in toggle_results),
        "rack_driven_and_metadata_fields_are_read_only": all(
            package.get("read_only_ok") for package in package_results
        ),
        "every_package_cooks_at_qa_resolution": all(
            package.get("resolution") == [QA_WIDTH, QA_HEIGHT]
            for package in package_results
        ),
        "every_package_has_clean_operator_diagnostics": all(
            not package.get("shader_errors")
            and not package.get("shader_warnings")
            and not package.get("errors")
            for package in package_results
        ),
        "complete_state_restoration": restoration_error is None,
    }
    report.update(
        {
            "checks": checks,
            "packages": package_results,
            "failed_packages": failed_packages,
            "numeric_control_count": len(numeric_results),
            "toggle_control_count": len(toggle_results),
            "restoration_error": restoration_error,
            "ok": (
                report.get("error") is None
                and not failed_packages
                and all(checks.values())
            ),
        }
    )
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
