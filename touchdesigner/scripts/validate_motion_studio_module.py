"""Live pixel validation for the reusable Motion Studio module."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "build" / "envoy-validation" / "motion-studio-module.json"
)
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"
COLOR_OUTPUT_PATH = DEMO_PATH + "/color_adjustment/out1_color_adjustment"
MOTION_PATH = DEMO_PATH + "/motion_studio"
MOTION_OUTPUT_PATH = MOTION_PATH + "/out1_motion"
MOTION_SHADER_PATH = MOTION_PATH + "/effect_glsl_motion_studio"
MOTION_SWITCH_PATH = MOTION_PATH + "/enable_switch"
RACK_OUTPUT_PATH = DEMO_PATH + "/fx_rack/out1_image"
ROUTER_PATH = DEMO_PATH + "/video_fx_router"
OUTPUT_PATH = DEMO_PATH + "/out1_image"

EXPECTED_MOTION_STYLES = (
    "pan",
    "diagonal_pan",
    "drift",
    "orbit",
    "figure_eight",
    "bounce",
    "pendulum",
    "swing",
    "shake",
    "handheld",
    "jitter",
    "float",
    "breathe",
    "zoom_pulse",
    "infinite_zoom",
    "dolly_zoom",
    "rotate",
    "spin_pulse",
    "spiral",
    "vortex",
    "twist",
    "horizontal_wave",
    "vertical_wave",
    "radial_wave",
    "ripple",
    "liquid",
    "wobble",
    "slither",
    "flow_field",
    "heat_haze",
    "parallax",
    "perspective_sway",
    "rolling_shutter",
    "whip_pan",
    "stop_motion",
    "step_jump",
    "conveyor",
    "tunnel",
    "kaleidoscope_motion",
    "elastic",
)
EXPECTED_EDGE_MODES = ("hold", "repeat", "mirror", "transparent")
EXPECTED_EASING_MODES = (
    "linear",
    "sine",
    "smooth",
    "smoother",
    "bounce",
    "elastic",
)

CONTROL_NAMES = (
    "Autotime",
    "Timescale",
    "Manualtime",
    "Style",
    "Mix",
    "Amount",
    "Speed",
    "Frequency",
    "Phase",
    "Directionx",
    "Directiony",
    "Centeru",
    "Centerv",
    "Zoom",
    "Rotation",
    "Warp",
    "Randomness",
    "Seed",
    "Steps",
    "Segments",
    "Edgemode",
    "Easing",
    "Trailamount",
    "Trailsamples",
)

STANDARD_VALUES = {
    "Autotime": False,
    "Timescale": 1.0,
    "Manualtime": 0.731,
    "Style": "drift",
    "Mix": 1.0,
    "Amount": 0.42,
    "Speed": 0.87,
    "Frequency": 3.7,
    "Phase": 0.13,
    "Directionx": 0.88,
    "Directiony": 0.31,
    "Centeru": 0.47,
    "Centerv": 0.53,
    "Zoom": 1.0,
    "Rotation": 0.0,
    "Warp": 0.82,
    "Randomness": 0.67,
    "Seed": 73,
    "Steps": 12,
    "Segments": 8,
    "Edgemode": "mirror",
    "Easing": "sine",
    "Trailamount": 0.0,
    "Trailsamples": 3,
}

SLIDER_CASES = {
    "Manualtime": ({"Style": "orbit"}, 0.15, 1.35),
    "Mix": ({"Style": "drift"}, 0.05, 1.0),
    "Amount": ({"Style": "drift"}, 0.08, 1.0),
    "Speed": ({"Style": "orbit"}, 0.2, 6.5),
    "Frequency": ({"Style": "horizontal_wave"}, 0.5, 22.0),
    "Phase": ({"Style": "horizontal_wave"}, -2.5, 3.7),
    "Directionx": ({"Style": "pan"}, -0.8, 0.9),
    "Directiony": ({"Style": "pan"}, -0.8, 0.9),
    "Centeru": ({"Style": "rotate", "Amount": 1.0}, 0.2, 0.8),
    "Centerv": ({"Style": "rotate", "Amount": 1.0}, 0.2, 0.8),
    "Zoom": ({"Style": "drift"}, 0.55, 1.8),
    "Rotation": ({"Style": "drift"}, -55.0, 70.0),
    "Warp": ({"Style": "liquid"}, 0.1, 1.8),
    "Randomness": ({"Style": "handheld"}, 0.05, 1.0),
    "Seed": ({"Style": "handheld"}, 3, 97),
    "Steps": ({"Style": "stop_motion"}, 3, 96),
    "Segments": ({"Style": "kaleidoscope_motion"}, 3, 28),
    "Trailamount": ({"Style": "liquid", "Trailsamples": 5}, 0.0, 0.95),
    "Trailsamples": ({"Style": "liquid", "Trailamount": 0.85}, 1, 5),
}

EXPECTED_SLIDER_NAMES = set(SLIDER_CASES) | {"Timescale"}


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


def _capture(top):
    top.cook(force=True)
    image = top.numpyArray(delayed=False, writable=False)
    if image is None:
        image = top.numpyArray(delayed=False, writable=False)
    if image is None:
        raise RuntimeError("TOP.numpyArray() returned no image for {}".format(top.path))
    return np.array(image, dtype=np.float32, copy=True)


def _difference(left, right):
    if left.shape != right.shape:
        return None
    return float(np.mean(np.abs(left - right)))


def _signature(image):
    row_step = max(1, image.shape[0] // 32)
    column_step = max(1, image.shape[1] // 32)
    sample = np.ascontiguousarray(image[::row_step, ::column_step, :])
    return hashlib.sha256(sample.tobytes()).hexdigest()


def _set_values(component, values):
    for name, value in values.items():
        parameter = component.par[name]
        if parameter is None:
            raise RuntimeError("Missing Motion Studio parameter {}".format(name))
        parameter.val = value


def _sweep_sliders(component, output):
    differences = {}
    finite = {}
    ranges = {}
    endpoint_values = {}
    for name, (activators, low_value, high_value) in SLIDER_CASES.items():
        _set_values(component, STANDARD_VALUES)
        _set_values(component, activators)
        parameter = component.par[name]
        parameter.val = low_value
        low_evaluated = parameter.eval()
        low_image = _capture(output)
        parameter.val = high_value
        high_evaluated = parameter.eval()
        high_image = _capture(output)
        differences[name] = _difference(low_image, high_image)
        finite[name] = bool(
            np.isfinite(low_image).all() and np.isfinite(high_image).all()
        )
        ranges[name] = {
            "min": float(parameter.min), "max": float(parameter.max),
            "norm_min": float(parameter.normMin),
            "norm_max": float(parameter.normMax),
            "clamp_min": bool(parameter.clampMin),
            "clamp_max": bool(parameter.clampMax),
        }
        endpoint_values[name] = {
            "low_requested": low_value, "low_evaluated": float(low_evaluated),
            "high_requested": high_value,
            "high_evaluated": float(high_evaluated),
        }
    return differences, finite, ranges, endpoint_values


def validate(write_report=True):
    """Exercise every style, bypass, time, sampling, trails, and rack routing."""

    required = {
        "demo": op(DEMO_PATH),
        "source": op(SOURCE_PATH),
        "color_output": op(COLOR_OUTPUT_PATH),
        "motion": op(MOTION_PATH),
        "motion_output": op(MOTION_OUTPUT_PATH),
        "motion_shader": op(MOTION_SHADER_PATH),
        "motion_switch": op(MOTION_SWITCH_PATH),
        "rack_output": op(RACK_OUTPUT_PATH),
        "router": op(ROUTER_PATH),
        "output": op(OUTPUT_PATH),
    }
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "module_id": "tdimagefx.core.motion-studio",
        "ok": False,
        "missing_operators": missing,
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
    }
    if missing:
        report["error"] = "Required Motion Studio demo operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo = required["demo"]
    source = required["source"]
    color_output = required["color_output"]
    motion = required["motion"]
    motion_output = required["motion_output"]
    motion_shader = required["motion_shader"]
    motion_switch = required["motion_switch"]
    rack_output = required["rack_output"]
    router = required["router"]
    output = required["output"]

    saved = {
        "ink_flow_enabled": demo.par.Inkflowenabled.eval(),
        "random_particles_enabled": demo.par.Particlesenabled.eval(),
        "glitch_enabled": demo.par.Glitchenabled.eval(),
        "color_enabled": demo.par.Coloradjustmentenabled.eval(),
        "motion_enabled": demo.par.Motionenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "controls": {name: motion.par[name].eval() for name in CONTROL_NAMES},
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Inkflowenabled = False
        demo.par.Particlesenabled = False
        demo.par.Glitchenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Applyvideofx = False
        _set_values(motion, STANDARD_VALUES)

        source_image = _capture(source)
        upstream_image = _capture(color_output)

        demo.par.Motionenabled = False
        module_bypass = _capture(motion_output)

        demo.par.Motionenabled = True
        motion.par.Mix = 0.0
        mix_bypass = _capture(motion_output)

        _set_values(motion, STANDARD_VALUES)
        motion.par.Amount = 0.0
        zero_amount = _capture(motion_output)

        _set_values(motion, STANDARD_VALUES)
        style_differences = {}
        style_signatures = {}
        style_finite = {}
        for style in EXPECTED_MOTION_STYLES:
            motion.par.Style = style
            image = _capture(motion_output)
            style_differences[style] = _difference(image, upstream_image)
            style_signatures[style] = _signature(image)
            style_finite[style] = bool(np.isfinite(image).all())

        _set_values(motion, STANDARD_VALUES)
        motion.par.Style = "orbit"
        motion.par.Manualtime = 0.23
        time_first = _capture(motion_output)
        motion.par.Manualtime = 0.81
        time_second = _capture(motion_output)

        _set_values(motion, STANDARD_VALUES)
        motion.par.Style = "pan"
        motion.par.Amount = 1.0
        motion.par.Manualtime = 2.4
        edge_signatures = {}
        edge_finite = {}
        for edge_mode in EXPECTED_EDGE_MODES:
            motion.par.Edgemode = edge_mode
            image = _capture(motion_output)
            edge_signatures[edge_mode] = _signature(image)
            edge_finite[edge_mode] = bool(np.isfinite(image).all())

        _set_values(motion, STANDARD_VALUES)
        motion.par.Style = "liquid"
        motion.par.Trailamount = 0.0
        motion.par.Trailsamples = 1
        trail_off = _capture(motion_output)
        motion.par.Trailamount = 0.82
        motion.par.Trailsamples = 5
        trail_on = _capture(motion_output)

        _set_values(motion, STANDARD_VALUES)
        motion.par.Style = "perspective_sway"
        motion.par.Zoom = 1.18
        motion.par.Rotation = 11.0
        motion_only = _capture(motion_output)
        router_without_rack = _capture(router)
        demo_output_without_rack = _capture(output)
        demo.par.Applyvideofx = True
        rack_processed = _capture(rack_output)
        router_with_rack = _capture(router)
        demo_output_with_rack = _capture(output)

        (
            slider_differences,
            slider_finite,
            slider_ranges,
            slider_endpoint_values,
        ) = _sweep_sliders(motion, motion_output)

        _set_values(motion, STANDARD_VALUES)
        motion.par.Autotime = True
        motion.par.Timescale = 0.5
        effective_time_low = float(motion.par.Time.eval())
        motion.par.Timescale = 1.5
        effective_time_high = float(motion.par.Time.eval())
        time_scale_range = {
            "min": float(motion.par.Timescale.min),
            "max": float(motion.par.Timescale.max),
            "norm_min": float(motion.par.Timescale.normMin),
            "norm_max": float(motion.par.Timescale.normMax),
            "clamp_min": bool(motion.par.Timescale.clampMin),
            "clamp_max": bool(motion.par.Timescale.clampMax),
        }

        differences = {
            "upstream_vs_source": _difference(upstream_image, source_image),
            "module_bypass_vs_upstream": _difference(module_bypass, upstream_image),
            "mix_zero_vs_upstream": _difference(mix_bypass, upstream_image),
            "zero_amount_vs_upstream": _difference(zero_amount, upstream_image),
            "manual_time_change": _difference(time_first, time_second),
            "trail_on_vs_off": _difference(trail_on, trail_off),
            "router_without_rack_vs_motion": _difference(
                router_without_rack,
                motion_only,
            ),
            "rack_output_vs_motion": _difference(rack_processed, motion_only),
            "router_with_rack_vs_rack": _difference(
                router_with_rack,
                rack_processed,
            ),
        }
        style_menu = tuple(str(item) for item in motion.par.Style.menuNames)
        edge_menu = tuple(str(item) for item in motion.par.Edgemode.menuNames)
        easing_menu = tuple(str(item) for item in motion.par.Easing.menuNames)
        shader_errors = _messages(motion_shader, "errors")
        shader_warnings = _messages(motion_shader, "warnings")
        checks = {
            "module_bypass_matches_upstream": (
                differences["module_bypass_vs_upstream"] is not None
                and differences["module_bypass_vs_upstream"] <= 1.0e-6
            ),
            "mix_zero_matches_upstream": (
                differences["mix_zero_vs_upstream"] is not None
                and differences["mix_zero_vs_upstream"] <= 1.0e-6
            ),
            "zero_amount_matches_upstream": (
                differences["zero_amount_vs_upstream"] is not None
                and differences["zero_amount_vs_upstream"] <= 2.0e-5
            ),
            "style_menu_contains_exactly_forty_modes": (
                style_menu == EXPECTED_MOTION_STYLES
            ),
            "every_motion_style_changes_source": all(
                value is not None and value > 1.0e-5
                for value in style_differences.values()
            ),
            "motion_styles_are_visually_distinct": (
                len(set(style_signatures.values())) == len(EXPECTED_MOTION_STYLES)
            ),
            "every_motion_style_is_finite": all(style_finite.values()),
            "manual_time_changes_motion": (
                differences["manual_time_change"] is not None
                and differences["manual_time_change"] > 1.0e-5
            ),
            "edge_menu_contains_exactly_four_modes": (
                edge_menu == EXPECTED_EDGE_MODES
            ),
            "edge_modes_are_visually_distinct": (
                len(set(edge_signatures.values())) == len(EXPECTED_EDGE_MODES)
            ),
            "edge_modes_are_finite": all(edge_finite.values()),
            "easing_menu_contains_exactly_six_modes": (
                easing_menu == EXPECTED_EASING_MODES
            ),
            "trail_sampling_changes_output": (
                differences["trail_on_vs_off"] is not None
                and differences["trail_on_vs_off"] > 1.0e-5
            ),
            "trail_samples_are_bounded_to_five": (
                int(motion.par.Trailsamples.max) == 5
            ),
            "router_without_rack_matches_motion_output": (
                differences["router_without_rack_vs_motion"] is not None
                and differences["router_without_rack_vs_motion"] <= 1.0e-6
            ),
            "video_fx_can_process_motion_output": (
                differences["rack_output_vs_motion"] is not None
                and differences["rack_output_vs_motion"] > 1.0e-6
            ),
            "router_with_rack_matches_rack_output": (
                differences["router_with_rack_vs_rack"] is not None
                and differences["router_with_rack_vs_rack"] <= 1.0e-6
            ),
            "module_enable_switch_matches_demo_toggle": (
                int(motion_switch.par.index.eval())
                == int(bool(demo.par.Motionenabled.eval()))
            ),
            "router_matches_apply_video_fx_toggle": (
                int(router.par.index.eval())
                == int(bool(demo.par.Applyvideofx.eval()))
            ),
            "output_resolution_matches_upstream": (
                int(motion_output.width) == int(color_output.width)
                and int(motion_output.height) == int(color_output.height)
            ),
            "final_output_cooks_selected_resolution": (
                int(output.width) >= 16
                and int(output.height) >= 16
                and demo_output_without_rack.size > 0
                and demo_output_with_rack.size > 0
            ),
            "every_numeric_slider_is_covered": (
                EXPECTED_SLIDER_NAMES
                == set(CONTROL_NAMES) - {"Autotime", "Style", "Edgemode", "Easing"}
            ),
            "every_numeric_slider_changes_output": all(
                value is not None and value > 1.0e-6
                for value in slider_differences.values()
            ),
            "every_numeric_slider_stays_finite": all(slider_finite.values()),
            "every_numeric_slider_has_valid_range": (
                all(
                    values["min"] < values["max"]
                    and abs(values["norm_min"] - values["min"]) <= 1.0e-9
                    and abs(values["norm_max"] - values["max"]) <= 1.0e-9
                    and values["clamp_min"] and values["clamp_max"]
                    for values in slider_ranges.values()
                )
                and time_scale_range["min"] < time_scale_range["max"]
                and time_scale_range["clamp_min"]
                and time_scale_range["clamp_max"]
            ),
            "every_numeric_slider_accepts_test_endpoints": all(
                abs(values["low_requested"] - values["low_evaluated"]) <= 1.0e-6
                and abs(values["high_requested"] - values["high_evaluated"]) <= 1.0e-6
                for values in slider_endpoint_values.values()
            ),
            "time_scale_changes_effective_time": (
                abs(effective_time_high - effective_time_low) > 1.0e-3
            ),
            "effective_time_is_read_only_and_resolved": (
                bool(motion.par.Time.readOnly)
                and "Autotime" in str(motion.par.Time.expr)
                and "Manualtime" in str(motion.par.Time.expr)
            ),
            "motion_shader_has_no_errors": not shader_errors,
            "motion_shader_has_no_warnings": not shader_warnings,
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "style_differences": style_differences,
                "style_signatures": style_signatures,
                "style_finite": style_finite,
                "edge_signatures": edge_signatures,
                "edge_finite": edge_finite,
                "slider_differences": slider_differences,
                "slider_finite": slider_finite,
                "slider_ranges": slider_ranges,
                "slider_endpoint_values": slider_endpoint_values,
                "time_scale": {
                    "effective_low": effective_time_low,
                    "effective_high": effective_time_high,
                    "range": time_scale_range,
                },
                "shader_errors": shader_errors,
                "shader_warnings": shader_warnings,
                "ok": all(checks.values()),
            }
        )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        demo.par.Inkflowenabled = saved["ink_flow_enabled"]
        demo.par.Particlesenabled = saved["random_particles_enabled"]
        demo.par.Glitchenabled = saved["glitch_enabled"]
        demo.par.Coloradjustmentenabled = saved["color_enabled"]
        demo.par.Motionenabled = saved["motion_enabled"]
        demo.par.Applyvideofx = saved["apply_video_fx"]
        _set_values(motion, saved["controls"])
        if saved["source_time_expression"]:
            source.par.vec0valuex.expr = saved["source_time_expression"]
        else:
            source.par.vec0valuex.expr = ""
            source.par.vec0valuex = saved["source_time_value"]
        output.cook(force=True)

    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
