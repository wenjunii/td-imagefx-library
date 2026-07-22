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

EDITABLE_CONTROL_NAMES = (
    "Autotime", "Timescale", "Manualtime", "Style", "Mix", "Intensity",
    "Speed", "Blocksize", "Slicedensity", "Displacement", "Jitter", "Smear",
    "Rgbsplit", "Noiseamount", "Dropout", "Scanlines", "Tracking",
    "Compression", "Colorshift", "Quantize", "Edgeamount", "Seed",
)

BASE_VALUES = {
    "Autotime": False, "Timescale": 1.0, "Manualtime": 0.731,
    "Style": "glitch_fusion", "Mix": 1.0, "Intensity": 0.78,
    "Speed": 1.4, "Blocksize": 36, "Slicedensity": 52,
    "Displacement": 0.18, "Jitter": 0.07, "Smear": 0.22,
    "Rgbsplit": 0.025, "Noiseamount": 0.42, "Dropout": 0.28,
    "Scanlines": 0.48, "Tracking": 0.045, "Compression": 0.52,
    "Colorshift": 0.42, "Quantize": 10, "Edgeamount": 2.2, "Seed": 47,
}

SLIDER_CASES = {
    "Manualtime": ({"Style": "digital_noise"}, 0.15, 1.35),
    "Mix": ({"Style": "glitch_fusion"}, 0.05, 1.0),
    "Intensity": ({"Style": "glitch_fusion"}, 0.15, 1.0),
    "Speed": ({"Style": "digital_noise", "Manualtime": 0.67}, 0.2, 6.0),
    "Blocksize": ({"Style": "block_shift"}, 4, 260),
    "Slicedensity": ({"Style": "slice_tear"}, 4, 280),
    "Displacement": ({"Style": "block_shift"}, 0.02, 0.48),
    "Jitter": ({"Style": "scanline_jitter"}, 0.0, 0.24),
    "Smear": ({"Style": "datamosh"}, 0.02, 0.58),
    "Rgbsplit": ({"Style": "rgb_split"}, 0.002, 0.095),
    "Noiseamount": ({"Style": "digital_noise"}, 0.05, 1.0),
    "Dropout": ({"Style": "signal_dropout"}, 0.05, 0.95),
    "Scanlines": ({"Style": "crt_corruption"}, 0.05, 1.0),
    "Tracking": ({"Style": "vhs_tracking"}, 0.002, 0.19),
    "Compression": ({"Style": "macroblock"}, 0.05, 1.0),
    "Colorshift": ({"Style": "data_bend"}, 0.05, 1.0),
    "Quantize": ({"Style": "color_quantize"}, 3, 56),
    "Edgeamount": ({"Style": "edge_corrupt"}, 0.2, 5.5),
    "Seed": ({"Style": "digital_noise"}, 3, 91),
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


def _set_values(component, values):
    for name, value in values.items():
        parameter = component.par[name]
        if parameter is None:
            raise RuntimeError("Missing Glitch Fusion parameter {}".format(name))
        parameter.val = value


def _sweep_sliders(component, output):
    differences = {}
    finite = {}
    ranges = {}
    endpoint_values = {}
    for name, (activators, low_value, high_value) in SLIDER_CASES.items():
        _set_values(component, BASE_VALUES)
        _set_values(component, activators)
        parameter = component.par[name]
        parameter.val = low_value
        low_evaluated = parameter.eval()
        low_image = _capture(output)
        parameter.val = high_value
        high_evaluated = parameter.eval()
        high_image = _capture(output)
        differences[name] = _mean_absolute_difference(low_image, high_image)
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
        "motion_enabled": demo.par.Motionenabled.eval(),
        "reference_particle_field_enabled": demo.par.Referenceparticlefieldenabled.eval(),
        "calligraphic_shadow_enabled": demo.par.Calligraphicshadowenabled.eval(),
        "ink_orbit_enabled": demo.par.Inkorbitenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "controls": {
            name: glitch.par[name].eval()
            for name in EDITABLE_CONTROL_NAMES
        },
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Inkflowenabled = False
        demo.par.Particlesenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Motionenabled = False
        demo.par.Referenceparticlefieldenabled = False
        demo.par.Calligraphicshadowenabled = False
        demo.par.Inkorbitenabled = False
        demo.par.Applyvideofx = False
        _set_values(glitch, BASE_VALUES)

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
        glitch.par.Seed = BASE_VALUES["Seed"]
        seed_default = _capture(glitch_output)
        glitch.par.Seed = int(BASE_VALUES["Seed"]) + 31
        seed_changed = _capture(glitch_output)

        glitch.par.Seed = BASE_VALUES["Seed"]
        glitch_only = _capture(glitch_output)
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
        ) = _sweep_sliders(glitch, glitch_output)

        _set_values(glitch, BASE_VALUES)
        glitch.par.Autotime = True
        glitch.par.Timescale = 0.5
        effective_time_low = float(glitch.par.Time.eval())
        glitch.par.Timescale = 1.5
        effective_time_high = float(glitch.par.Time.eval())
        time_scale_range = {
            "min": float(glitch.par.Timescale.min),
            "max": float(glitch.par.Timescale.max),
            "norm_min": float(glitch.par.Timescale.normMin),
            "norm_max": float(glitch.par.Timescale.normMax),
            "clamp_min": bool(glitch.par.Timescale.clampMin),
            "clamp_max": bool(glitch.par.Timescale.clampMax),
        }

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
            "every_numeric_slider_is_covered": (
                EXPECTED_SLIDER_NAMES
                == set(EDITABLE_CONTROL_NAMES) - {"Autotime", "Style"}
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
                bool(glitch.par.Time.readOnly)
                and "Autotime" in str(glitch.par.Time.expr)
                and "Manualtime" in str(glitch.par.Time.expr)
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
        demo.par.Referenceparticlefieldenabled = saved["reference_particle_field_enabled"]
        demo.par.Calligraphicshadowenabled = saved["calligraphic_shadow_enabled"]
        demo.par.Inkorbitenabled = saved["ink_orbit_enabled"]
        demo.par.Applyvideofx = saved["apply_video_fx"]
        _set_values(glitch, saved["controls"])
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
