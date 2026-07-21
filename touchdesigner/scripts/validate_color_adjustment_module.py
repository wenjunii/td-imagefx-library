"""Live pixel validation for the reusable Color Adjustment module."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT
    / "build"
    / "envoy-validation"
    / "color-adjustment-module.json"
)
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"
COLOR_PATH = DEMO_PATH + "/color_adjustment"
COLOR_OUTPUT_PATH = COLOR_PATH + "/out1_color_adjustment"
COLOR_SHADER_PATH = COLOR_PATH + "/effect_glsl_color_adjustment"
COLOR_SWITCH_PATH = COLOR_PATH + "/enable_switch"
RACK_OUTPUT_PATH = DEMO_PATH + "/fx_rack/out1_image"
ROUTER_PATH = DEMO_PATH + "/video_fx_router"
OUTPUT_PATH = DEMO_PATH + "/out1_image"

EXPECTED_OVERLAY_MODES = (
    "normal",
    "multiply",
    "screen",
    "overlay",
    "soft_light",
    "hard_light",
    "color",
    "difference",
)

CONTROL_NAMES = (
    "Mix",
    "Invert",
    "Exposure",
    "Brightness",
    "Contrast",
    "Saturation",
    "Vibrance",
    "Hue",
    "Temperature",
    "Tint",
    "Blackpoint",
    "Whitepoint",
    "Gamma",
    "Liftx",
    "Lifty",
    "Liftz",
    "Gainx",
    "Gainy",
    "Gainz",
    "Shadows",
    "Highlights",
    "Monochrome",
    "Sepia",
    "Posterizeamount",
    "Posterizelevels",
    "Duotoneamount",
    "Duotoneshadowr",
    "Duotoneshadowg",
    "Duotoneshadowb",
    "Duotoneshadowa",
    "Duotonehighlightr",
    "Duotonehighlightg",
    "Duotonehighlightb",
    "Duotonehighlighta",
    "Overlayenabled",
    "Overlaycolorr",
    "Overlaycolorg",
    "Overlaycolorb",
    "Overlaycolora",
    "Overlayamount",
    "Overlaymode",
)

NEUTRAL_VALUES = {
    "Mix": 1.0,
    "Invert": 0.0,
    "Exposure": 0.0,
    "Brightness": 0.0,
    "Contrast": 1.0,
    "Saturation": 1.0,
    "Vibrance": 0.0,
    "Hue": 0.0,
    "Temperature": 0.0,
    "Tint": 0.0,
    "Blackpoint": 0.0,
    "Whitepoint": 1.0,
    "Gamma": 1.0,
    "Liftx": 0.0,
    "Lifty": 0.0,
    "Liftz": 0.0,
    "Gainx": 1.0,
    "Gainy": 1.0,
    "Gainz": 1.0,
    "Shadows": 0.0,
    "Highlights": 0.0,
    "Monochrome": 0.0,
    "Sepia": 0.0,
    "Posterizeamount": 0.0,
    "Posterizelevels": 8,
    "Duotoneamount": 0.0,
    "Overlayenabled": False,
    "Overlayamount": 0.5,
    "Overlaymode": "soft_light",
}


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
        raise RuntimeError(
            "TOP.numpyArray() returned no image for {}".format(top.path)
        )
    return np.array(image, dtype=np.float32, copy=True)


def _mean_absolute_difference(left, right):
    if left.shape != right.shape:
        return None
    return float(np.mean(np.abs(left - right)))


def _alpha_difference(left, right):
    if left.shape != right.shape or left.shape[-1] < 4:
        return None
    return float(np.max(np.abs(left[..., 3] - right[..., 3])))


def _signature(image):
    row_step = max(1, image.shape[0] // 32)
    column_step = max(1, image.shape[1] // 32)
    sample = np.ascontiguousarray(
        image[::row_step, ::column_step, : min(3, image.shape[-1])]
    )
    return hashlib.sha256(sample.tobytes()).hexdigest()


def _set_values(component, values):
    for name, value in values.items():
        parameter = component.par[name]
        if parameter is None:
            raise RuntimeError("Missing Color Adjustment parameter {}".format(name))
        parameter.val = value


def _capture_adjustment(component, output, source_image, values):
    _set_values(component, NEUTRAL_VALUES)
    _set_values(component, values)
    image = _capture(output)
    return image, _mean_absolute_difference(image, source_image)


def validate(write_report=True):
    """Exercise neutral behavior, adjustments, overlays, alpha, and routing."""

    required = {
        "demo": op(DEMO_PATH),
        "source": op(SOURCE_PATH),
        "color": op(COLOR_PATH),
        "color_output": op(COLOR_OUTPUT_PATH),
        "color_shader": op(COLOR_SHADER_PATH),
        "color_switch": op(COLOR_SWITCH_PATH),
        "rack_output": op(RACK_OUTPUT_PATH),
        "router": op(ROUTER_PATH),
        "output": op(OUTPUT_PATH),
    }
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "module_id": "tdimagefx.core.color-adjustment",
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
        report["error"] = "Required Color Adjustment demo operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo = required["demo"]
    source = required["source"]
    color = required["color"]
    color_output = required["color_output"]
    color_shader = required["color_shader"]
    color_switch = required["color_switch"]
    rack_output = required["rack_output"]
    router = required["router"]
    output = required["output"]

    saved = {
        "ink_flow_enabled": demo.par.Inkflowenabled.eval(),
        "random_particles_enabled": demo.par.Particlesenabled.eval(),
        "glitch_enabled": demo.par.Glitchenabled.eval(),
        "color_enabled": demo.par.Coloradjustmentenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "controls": {
            name: color.par[name].eval()
            for name in CONTROL_NAMES
        },
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Inkflowenabled = False
        demo.par.Particlesenabled = False
        demo.par.Glitchenabled = False
        demo.par.Applyvideofx = False
        _set_values(color, NEUTRAL_VALUES)

        source_image = _capture(source)

        demo.par.Coloradjustmentenabled = False
        module_bypass = _capture(color_output)

        demo.par.Coloradjustmentenabled = True
        color.par.Mix = 0.0
        mix_bypass = _capture(color_output)
        _set_values(color, NEUTRAL_VALUES)
        neutral = _capture(color_output)

        adjustment_values = {
            "invert": {"Invert": 1.0},
            "exposure": {"Exposure": 1.0},
            "brightness": {"Brightness": 0.22},
            "contrast": {"Contrast": 1.65},
            # Partial desaturation stays visually distinct from the dedicated
            # full-strength Monochrome control while still proving that the
            # saturation path changes pixels.
            "saturation": {"Saturation": 0.35},
            "vibrance": {"Vibrance": 1.0},
            "hue": {"Hue": 0.25},
            "temperature": {"Temperature": 0.85},
            "tint": {"Tint": 0.85},
            "black_point": {"Blackpoint": 0.18},
            "gamma": {"Gamma": 0.58},
            "rgb_lift": {"Liftx": 0.18, "Lifty": 0.03, "Liftz": -0.08},
            "rgb_gain": {"Gainx": 1.45, "Gainy": 0.72, "Gainz": 1.16},
            "shadows": {"Shadows": 0.72},
            "highlights": {"Highlights": -0.62},
            "monochrome": {"Monochrome": 1.0},
            "sepia": {"Sepia": 1.0},
            "posterize": {"Posterizeamount": 1.0, "Posterizelevels": 4},
            "duotone": {"Duotoneamount": 1.0},
        }
        adjustment_differences = {}
        alpha_differences = {}
        adjustment_signatures = {}
        for name, values in adjustment_values.items():
            image, difference = _capture_adjustment(
                color,
                color_output,
                source_image,
                values,
            )
            adjustment_differences[name] = difference
            alpha_differences[name] = _alpha_difference(image, source_image)
            adjustment_signatures[name] = _signature(image)

        _set_values(color, NEUTRAL_VALUES)
        color.par.Overlayenabled = True
        color.par.Overlayamount = 0.78
        color.par.Overlaycolorr = 0.88
        color.par.Overlaycolorg = 0.16
        color.par.Overlaycolorb = 0.72
        color.par.Overlaycolora = 1.0
        overlay_differences = {}
        overlay_alpha_differences = {}
        overlay_signatures = {}
        for mode in EXPECTED_OVERLAY_MODES:
            color.par.Overlaymode = mode
            image = _capture(color_output)
            overlay_differences[mode] = _mean_absolute_difference(
                image,
                source_image,
            )
            overlay_alpha_differences[mode] = _alpha_difference(
                image,
                source_image,
            )
            overlay_signatures[mode] = _signature(image)

        color.par.Overlaymode = "soft_light"
        color_only = _capture(color_output)
        router_without_rack = _capture(router)
        demo_output_without_rack = _capture(output)
        demo.par.Applyvideofx = True
        rack_processed = _capture(rack_output)
        router_with_rack = _capture(router)
        demo_output_with_rack = _capture(output)

        differences = {
            "module_bypass_vs_source": _mean_absolute_difference(
                module_bypass,
                source_image,
            ),
            "mix_zero_vs_source": _mean_absolute_difference(
                mix_bypass,
                source_image,
            ),
            "neutral_vs_source": _mean_absolute_difference(
                neutral,
                source_image,
            ),
            "router_without_rack_vs_color_output": _mean_absolute_difference(
                router_without_rack,
                color_only,
            ),
            "rack_output_vs_color_output": _mean_absolute_difference(
                rack_processed,
                color_only,
            ),
            "router_with_rack_vs_rack_output": _mean_absolute_difference(
                router_with_rack,
                rack_processed,
            ),
        }
        menu_names = tuple(str(item) for item in color.par.Overlaymode.menuNames)
        shader_errors = _messages(color_shader, "errors")
        shader_warnings = _messages(color_shader, "warnings")
        checks = {
            "module_bypass_matches_source": (
                differences["module_bypass_vs_source"] is not None
                and differences["module_bypass_vs_source"] <= 1.0e-6
            ),
            "mix_zero_matches_source": (
                differences["mix_zero_vs_source"] is not None
                and differences["mix_zero_vs_source"] <= 1.0e-6
            ),
            "neutral_controls_match_source": (
                differences["neutral_vs_source"] is not None
                and differences["neutral_vs_source"] <= 2.0e-5
            ),
            "every_adjustment_changes_source": all(
                value is not None and value > 1.0e-5
                for value in adjustment_differences.values()
            ),
            "adjustments_are_visually_distinct": (
                len(set(adjustment_signatures.values()))
                == len(adjustment_signatures)
            ),
            "overlay_menu_contains_exactly_eight_modes": (
                menu_names == EXPECTED_OVERLAY_MODES
            ),
            "every_overlay_mode_changes_source": all(
                value is not None and value > 1.0e-5
                for value in overlay_differences.values()
            ),
            "overlay_modes_are_visually_distinct": (
                len(set(overlay_signatures.values())) == len(EXPECTED_OVERLAY_MODES)
            ),
            "adjustments_preserve_source_alpha": all(
                value is not None and value <= 1.0e-6
                for value in alpha_differences.values()
            ),
            "overlays_preserve_source_alpha": all(
                value is not None and value <= 1.0e-6
                for value in overlay_alpha_differences.values()
            ),
            "router_without_rack_matches_color_output": (
                differences["router_without_rack_vs_color_output"] is not None
                and differences["router_without_rack_vs_color_output"] <= 1.0e-6
            ),
            "video_fx_can_process_color_output": (
                differences["rack_output_vs_color_output"] is not None
                and differences["rack_output_vs_color_output"] > 1.0e-6
            ),
            "router_with_rack_matches_rack_output": (
                differences["router_with_rack_vs_rack_output"] is not None
                and differences["router_with_rack_vs_rack_output"] <= 1.0e-6
            ),
            "module_enable_switch_matches_demo_toggle": (
                int(color_switch.par.index.eval())
                == int(bool(demo.par.Coloradjustmentenabled.eval()))
            ),
            "router_matches_apply_video_fx_toggle": (
                int(router.par.index.eval())
                == int(bool(demo.par.Applyvideofx.eval()))
            ),
            "output_resolution_matches_source": (
                int(color_output.width) == int(source.width)
                and int(color_output.height) == int(source.height)
            ),
            "final_output_cooks_selected_resolution": (
                int(output.width) >= 16
                and int(output.height) >= 16
                and demo_output_without_rack.size > 0
                and demo_output_with_rack.size > 0
            ),
            "color_shader_has_no_errors": not shader_errors,
            "color_shader_has_no_warnings": not shader_warnings,
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "adjustment_differences": adjustment_differences,
                "adjustment_signatures": adjustment_signatures,
                "alpha_differences": alpha_differences,
                "overlay_differences": overlay_differences,
                "overlay_signatures": overlay_signatures,
                "overlay_alpha_differences": overlay_alpha_differences,
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
        demo.par.Applyvideofx = saved["apply_video_fx"]
        _set_values(color, saved["controls"])
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
