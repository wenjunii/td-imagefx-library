"""Live pixel validation for all Glitch Fusion styles and routing controls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "build" / "envoy-validation" / "glitch-fusion-module.json"
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"
GLITCH_PATH = DEMO_PATH + "/glitch_fusion"
GLITCH_OUTPUT_PATH = GLITCH_PATH + "/out1_glitch"
GLITCH_SHADER_PATH = GLITCH_PATH + "/effect_glsl_glitch_fusion"
GLITCH_SWITCH_PATH = GLITCH_PATH + "/enable_switch"
ROUTER_PATH = DEMO_PATH + "/video_fx_router"
RACK_OUTPUT_PATH = DEMO_PATH + "/fx_rack/out1_image"
OUTPUT_PATH = DEMO_PATH + "/out1_image"

EXPECTED_STYLES = (
    "rgb_split",
    "block_shift",
    "slice_tear",
    "digital_noise",
    "pixel_sort",
    "datamosh",
    "vhs_tracking",
    "scanline_jitter",
    "macroblock",
    "signal_dropout",
    "frame_jitter",
    "rolling_sync",
    "channel_swap",
    "color_quantize",
    "bit_crush",
    "mosaic_scramble",
    "wave_interference",
    "static_snow",
    "crt_corruption",
    "horizontal_hold",
    "vertical_hold",
    "data_bend",
    "edge_corrupt",
    "glitch_fusion",
)


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


def _signature(image):
    row_step = max(1, image.shape[0] // 32)
    column_step = max(1, image.shape[1] // 32)
    sample = np.ascontiguousarray(
        image[::row_step, ::column_step, : min(3, image.shape[-1])]
    )
    return hashlib.sha256(sample.tobytes()).hexdigest()


def validate(write_report=True):
    """Exercise bypass, all 24 styles, timing, seed, and rack routing."""

    required = {
        "demo": op(DEMO_PATH),
        "source": op(SOURCE_PATH),
        "glitch": op(GLITCH_PATH),
        "glitch_output": op(GLITCH_OUTPUT_PATH),
        "glitch_shader": op(GLITCH_SHADER_PATH),
        "glitch_switch": op(GLITCH_SWITCH_PATH),
        "router": op(ROUTER_PATH),
        "rack_output": op(RACK_OUTPUT_PATH),
        "output": op(OUTPUT_PATH),
    }
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "module_id": "tdimagefx.core.glitch-fusion",
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
        report["error"] = "Required Glitch Fusion demo operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo = required["demo"]
    source = required["source"]
    glitch = required["glitch"]
    glitch_output = required["glitch_output"]
    glitch_shader = required["glitch_shader"]
    glitch_switch = required["glitch_switch"]
    router = required["router"]
    rack_output = required["rack_output"]
    output = required["output"]

    saved = {
        "ink_flow_enabled": demo.par.Inkflowenabled.eval(),
        "random_particles_enabled": demo.par.Particlesenabled.eval(),
        "glitch_enabled": demo.par.Glitchenabled.eval(),
        "color_enabled": demo.par.Coloradjustmentenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "auto_time": glitch.par.Autotime.eval(),
        "manual_time": glitch.par.Manualtime.eval(),
        "style": glitch.par.Style.eval(),
        "mix": glitch.par.Mix.eval(),
        "intensity": glitch.par.Intensity.eval(),
        "seed": glitch.par.Seed.eval(),
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Inkflowenabled = False
        demo.par.Particlesenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Applyvideofx = False
        glitch.par.Autotime = False
        glitch.par.Manualtime = 0.0
        glitch.par.Mix = 1.0
        glitch.par.Intensity = max(0.68, float(saved["intensity"]))

        source_image = _capture(source)

        demo.par.Glitchenabled = False
        module_bypass = _capture(glitch_output)

        demo.par.Glitchenabled = True
        glitch.par.Mix = 0.0
        mix_bypass = _capture(glitch_output)
        glitch.par.Mix = 1.0

        menu_names = tuple(str(item) for item in glitch.par.Style.menuNames)
        style_differences = {}
        style_signatures = {}
        style_standard_deviations = {}
        for style in EXPECTED_STYLES:
            glitch.par.Style = style
            image = _capture(glitch_output)
            style_differences[style] = _mean_absolute_difference(
                image,
                source_image,
            )
            style_signatures[style] = _signature(image)
            style_standard_deviations[style] = float(np.std(image))

        glitch.par.Style = "glitch_fusion"
        glitch.par.Manualtime = 0.0
        time_zero = _capture(glitch_output)
        glitch.par.Manualtime = 1.0
        time_one = _capture(glitch_output)

        glitch.par.Manualtime = 0.0
        glitch.par.Seed = saved["seed"]
        seed_default = _capture(glitch_output)
        glitch.par.Seed = int(saved["seed"]) + 31
        seed_changed = _capture(glitch_output)

        glitch.par.Seed = saved["seed"]
        glitch_only = _capture(glitch_output)
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
            "manual_time_zero_vs_one": _mean_absolute_difference(
                time_zero,
                time_one,
            ),
            "seed_default_vs_changed": _mean_absolute_difference(
                seed_default,
                seed_changed,
            ),
            "router_without_rack_vs_glitch_output": _mean_absolute_difference(
                router_without_rack,
                glitch_only,
            ),
            "rack_output_vs_glitch_output": _mean_absolute_difference(
                rack_processed,
                glitch_only,
            ),
            "router_with_rack_vs_rack_output": _mean_absolute_difference(
                router_with_rack,
                rack_processed,
            ),
        }
        shader_errors = _messages(glitch_shader, "errors")
        shader_warnings = _messages(glitch_shader, "warnings")
        checks = {
            "module_bypass_matches_source": (
                differences["module_bypass_vs_source"] is not None
                and differences["module_bypass_vs_source"] <= 1.0e-6
            ),
            "mix_zero_matches_source": (
                differences["mix_zero_vs_source"] is not None
                and differences["mix_zero_vs_source"] <= 1.0e-6
            ),
            "style_menu_contains_exactly_24_modes": (
                menu_names == EXPECTED_STYLES
            ),
            "every_glitch_style_changes_source": all(
                value is not None and value > 1.0e-5
                for value in style_differences.values()
            ),
            "every_glitch_style_cooks_visible_output": all(
                value > 1.0e-5
                for value in style_standard_deviations.values()
            ),
            "glitch_styles_are_visually_distinct": (
                len(set(style_signatures.values())) == len(EXPECTED_STYLES)
            ),
            "manual_time_animates_glitch": (
                differences["manual_time_zero_vs_one"] is not None
                and differences["manual_time_zero_vs_one"] > 1.0e-6
            ),
            "seed_changes_glitch_pattern": (
                differences["seed_default_vs_changed"] is not None
                and differences["seed_default_vs_changed"] > 1.0e-6
            ),
            "router_without_rack_matches_glitch_output": (
                differences["router_without_rack_vs_glitch_output"] is not None
                and differences["router_without_rack_vs_glitch_output"] <= 1.0e-6
            ),
            "router_matches_apply_video_fx_toggle": (
                int(router.par.index.eval())
                == int(bool(demo.par.Applyvideofx.eval()))
            ),
            "video_fx_can_process_glitch_output": (
                differences["rack_output_vs_glitch_output"] is not None
                and differences["rack_output_vs_glitch_output"] > 1.0e-6
            ),
            "router_with_rack_matches_rack_output": (
                differences["router_with_rack_vs_rack_output"] is not None
                and differences["router_with_rack_vs_rack_output"] <= 1.0e-6
            ),
            "final_output_cooks_selected_resolution": (
                int(output.width) >= 16
                and int(output.height) >= 16
                and demo_output_without_rack.size > 0
                and demo_output_with_rack.size > 0
            ),
            "module_enable_switch_matches_demo_toggle": (
                int(glitch_switch.par.index.eval())
                == int(bool(demo.par.Glitchenabled.eval()))
            ),
            "output_resolution_matches_source": (
                int(glitch_output.width) == int(source.width)
                and int(glitch_output.height) == int(source.height)
            ),
            "glitch_shader_has_no_errors": not shader_errors,
            "glitch_shader_has_no_warnings": not shader_warnings,
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "style_differences": style_differences,
                "style_signatures": style_signatures,
                "style_standard_deviations": style_standard_deviations,
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
        glitch.par.Autotime = saved["auto_time"]
        glitch.par.Manualtime = saved["manual_time"]
        glitch.par.Style = saved["style"]
        glitch.par.Mix = saved["mix"]
        glitch.par.Intensity = saved["intensity"]
        glitch.par.Seed = saved["seed"]
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
