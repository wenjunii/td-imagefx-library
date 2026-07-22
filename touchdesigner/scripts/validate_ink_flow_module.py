"""Live pixel validation for ink styles and water-current particles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "build" / "envoy-validation" / "ink-flow-module.json"
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"
INK_FLOW_PATH = DEMO_PATH + "/ink_flow"
INK_OUTPUT_PATH = INK_FLOW_PATH + "/out1_ink_flow"
INK_SHADER_PATH = INK_FLOW_PATH + "/effect_glsl_ink_flow"
INK_SWITCH_PATH = INK_FLOW_PATH + "/enable_switch"

EDITABLE_CONTROL_NAMES = (
    "Autotime", "Timescale", "Manualtime", "Visualenabled", "Style",
    "Visualmix", "Inkstrength", "Edgedetail", "Washspread", "Granulation",
    "Papertexture", "Inkcolorr", "Inkcolorg", "Inkcolorb", "Inkcolora",
    "Papercolorr", "Papercolorg", "Papercolorb", "Papercolora",
    "Particlesenabled", "Particledensity", "Particlesize", "Flowspeed",
    "Flowdirectionx", "Flowdirectiony", "Flowstrength", "Turbulence",
    "Randomness", "Particlestretch", "Particleshape", "Particleopacity",
    "Particleinkmix", "Seed",
)

BASE_VALUES = {
    "Autotime": False, "Timescale": 1.0, "Manualtime": 0.731,
    "Visualenabled": True, "Style": "ink_wash", "Visualmix": 0.88,
    "Inkstrength": 1.05, "Edgedetail": 1.7, "Washspread": 3.6,
    "Granulation": 0.46, "Papertexture": 0.52,
    "Inkcolorr": 0.04, "Inkcolorg": 0.08, "Inkcolorb": 0.16,
    "Inkcolora": 0.9, "Papercolorr": 0.94, "Papercolorg": 0.88,
    "Papercolorb": 0.76, "Papercolora": 0.9,
    "Particlesenabled": True, "Particledensity": 72, "Particlesize": 0.52,
    "Flowspeed": 0.75, "Flowdirectionx": 0.82, "Flowdirectiony": -0.24,
    "Flowstrength": 0.48, "Turbulence": 0.16, "Randomness": 0.10,
    "Particlestretch": 0.62, "Particleshape": "brush",
    "Particleopacity": 0.72, "Particleinkmix": 0.78, "Seed": 23,
}

SLIDER_CASES = {
    "Manualtime": ({}, 0.15, 1.25),
    "Visualmix": ({"Particlesenabled": False}, 0.1, 0.95),
    "Inkstrength": ({"Particlesenabled": False}, 0.2, 1.8),
    "Edgedetail": ({"Particlesenabled": False}, 0.2, 3.6),
    "Washspread": ({"Particlesenabled": False}, 0.5, 8.5),
    "Granulation": ({"Particlesenabled": False}, 0.0, 0.9),
    "Papertexture": ({"Particlesenabled": False}, 0.0, 1.0),
    "Inkcolorr": ({"Particlesenabled": False}, 0.0, 0.8),
    "Inkcolorg": ({"Particlesenabled": False}, 0.0, 0.8),
    "Inkcolorb": ({"Particlesenabled": False}, 0.0, 0.8),
    "Inkcolora": ({"Particlesenabled": False}, 0.1, 1.0),
    "Papercolorr": ({"Particlesenabled": False}, 0.2, 1.0),
    "Papercolorg": ({"Particlesenabled": False}, 0.2, 1.0),
    "Papercolorb": ({"Particlesenabled": False}, 0.2, 1.0),
    "Papercolora": ({"Particlesenabled": False}, 0.1, 1.0),
    "Particledensity": ({"Visualenabled": False}, 24, 120),
    "Particlesize": ({"Visualenabled": False}, 0.12, 0.82),
    "Flowspeed": ({"Visualenabled": False}, 0.2, 3.2),
    "Flowdirectionx": ({"Visualenabled": False}, -0.8, 0.8),
    "Flowdirectiony": ({"Visualenabled": False}, -0.8, 0.8),
    "Flowstrength": ({"Visualenabled": False}, 0.05, 0.62),
    "Turbulence": ({"Visualenabled": False}, 0.0, 0.24),
    "Randomness": ({"Visualenabled": False}, 0.0, 0.15),
    "Particlestretch": ({"Visualenabled": False}, 0.0, 1.0),
    "Particleopacity": ({"Visualenabled": False}, 0.15, 1.0),
    "Particleinkmix": ({"Visualenabled": False}, 0.0, 1.0),
    "Seed": ({}, 3, 97),
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


def _metrics(image):
    rgb = image[..., : min(3, image.shape[-1])]
    alpha = image[..., 3] if image.shape[-1] >= 4 else None
    return {
        "shape": [int(value) for value in image.shape],
        "minimum": float(np.min(image)),
        "maximum": float(np.max(image)),
        "mean": float(np.mean(image)),
        "standard_deviation": float(np.std(image)),
        "rgb_mean": float(np.mean(rgb)),
        "alpha_mean": float(np.mean(alpha)) if alpha is not None else 1.0,
    }


def _mean_absolute_difference(left, right):
    if left.shape != right.shape:
        return None
    return float(
        np.mean(
            np.abs(
                left.astype(np.float32)
                - right.astype(np.float32)
            )
        )
    )


def _set_values(component, values):
    for name, value in values.items():
        parameter = component.par[name]
        if parameter is None:
            raise RuntimeError("Missing Ink Flow parameter {}".format(name))
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
    """Exercise module bypass, both ink styles, and water-particle controls."""

    required = {
        "demo": op(DEMO_PATH),
        "source": op(SOURCE_PATH),
        "ink_flow": op(INK_FLOW_PATH),
        "ink_output": op(INK_OUTPUT_PATH),
        "ink_shader": op(INK_SHADER_PATH),
        "ink_switch": op(INK_SWITCH_PATH),
    }
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "module_id": "tdimagefx.core.ink-flow-fusion",
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
        report["error"] = "Required ink-flow demo operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo = required["demo"]
    source = required["source"]
    ink_flow = required["ink_flow"]
    ink_output = required["ink_output"]
    ink_shader = required["ink_shader"]
    ink_switch = required["ink_switch"]

    saved = {
        "ink_flow_enabled": demo.par.Inkflowenabled.eval(),
        "glitch_enabled": demo.par.Glitchenabled.eval(),
        "color_enabled": demo.par.Coloradjustmentenabled.eval(),
        "motion_enabled": demo.par.Motionenabled.eval(),
        "random_particles_enabled": demo.par.Particlesenabled.eval(),
        "reference_particle_field_enabled": demo.par.Referenceparticlefieldenabled.eval(),
        "calligraphic_shadow_enabled": demo.par.Calligraphicshadowenabled.eval(),
        "ink_orbit_enabled": demo.par.Inkorbitenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "controls": {
            name: ink_flow.par[name].eval()
            for name in EDITABLE_CONTROL_NAMES
        },
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Particlesenabled = False
        demo.par.Glitchenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Motionenabled = False
        demo.par.Referenceparticlefieldenabled = False
        demo.par.Calligraphicshadowenabled = False
        demo.par.Inkorbitenabled = False
        demo.par.Applyvideofx = False
        _set_values(ink_flow, BASE_VALUES)

        source_image = _capture(source)

        demo.par.Inkflowenabled = False
        module_bypass = _capture(ink_output)

        demo.par.Inkflowenabled = True
        ink_flow.par.Visualenabled = False
        ink_flow.par.Particlesenabled = False
        feature_bypass = _capture(ink_output)

        ink_flow.par.Visualenabled = True
        ink_flow.par.Particlesenabled = False
        ink_flow.par.Style = "ink_work"
        ink_work = _capture(ink_output)
        ink_flow.par.Style = "ink_wash"
        ink_wash = _capture(ink_output)

        ink_flow.par.Visualenabled = False
        ink_flow.par.Particlesenabled = True
        ink_flow.par.Manualtime = 0.0
        particles_t0 = _capture(ink_output)
        ink_flow.par.Manualtime = 1.0
        particles_t1 = _capture(ink_output)

        ink_flow.par.Manualtime = 0.0
        seed_default = _capture(ink_output)
        ink_flow.par.Seed = int(BASE_VALUES["Seed"]) + 29
        seed_changed = _capture(ink_output)

        ink_flow.par.Seed = BASE_VALUES["Seed"]
        ink_flow.par.Visualenabled = True
        ink_flow.par.Style = "ink_wash"
        ink_flow.par.Particlesenabled = True
        combined = _capture(ink_output)

        ink_flow.par.Particledensity = int(ink_flow.par.Particledensity.max)
        maximum_density = _capture(ink_output)

        (
            slider_differences,
            slider_finite,
            slider_ranges,
            slider_endpoint_values,
        ) = _sweep_sliders(ink_flow, ink_output)

        _set_values(ink_flow, BASE_VALUES)
        ink_flow.par.Autotime = True
        ink_flow.par.Timescale = 0.5
        effective_time_low = float(ink_flow.par.Time.eval())
        ink_flow.par.Timescale = 1.5
        effective_time_high = float(ink_flow.par.Time.eval())
        time_scale_range = {
            "min": float(ink_flow.par.Timescale.min),
            "max": float(ink_flow.par.Timescale.max),
            "norm_min": float(ink_flow.par.Timescale.normMin),
            "norm_max": float(ink_flow.par.Timescale.normMax),
            "clamp_min": bool(ink_flow.par.Timescale.clampMin),
            "clamp_max": bool(ink_flow.par.Timescale.clampMax),
        }

        differences = {
            "module_bypass_vs_source": _mean_absolute_difference(
                module_bypass,
                source_image,
            ),
            "feature_bypass_vs_source": _mean_absolute_difference(
                feature_bypass,
                source_image,
            ),
            "ink_work_vs_source": _mean_absolute_difference(
                ink_work,
                source_image,
            ),
            "ink_wash_vs_source": _mean_absolute_difference(
                ink_wash,
                source_image,
            ),
            "ink_work_vs_ink_wash": _mean_absolute_difference(
                ink_work,
                ink_wash,
            ),
            "particles_vs_source": _mean_absolute_difference(
                particles_t0,
                source_image,
            ),
            "particles_t0_vs_t1": _mean_absolute_difference(
                particles_t0,
                particles_t1,
            ),
            "seed_default_vs_changed": _mean_absolute_difference(
                seed_default,
                seed_changed,
            ),
            "combined_vs_ink_wash": _mean_absolute_difference(
                combined,
                ink_wash,
            ),
        }
        checks = {
            "module_bypass_matches_source": (
                differences["module_bypass_vs_source"] is not None
                and differences["module_bypass_vs_source"] <= 1.0e-6
            ),
            "independent_feature_bypass_matches_source": (
                differences["feature_bypass_vs_source"] is not None
                and differences["feature_bypass_vs_source"] <= 1.0e-6
            ),
            "minimal_ink_work_changes_source": (
                differences["ink_work_vs_source"] is not None
                and differences["ink_work_vs_source"] > 1.0e-4
            ),
            "minimal_ink_wash_changes_source": (
                differences["ink_wash_vs_source"] is not None
                and differences["ink_wash_vs_source"] > 1.0e-4
            ),
            "ink_styles_are_visually_distinct": (
                differences["ink_work_vs_ink_wash"] is not None
                and differences["ink_work_vs_ink_wash"] > 1.0e-4
            ),
            "water_particles_change_source": (
                differences["particles_vs_source"] is not None
                and differences["particles_vs_source"] > 1.0e-5
            ),
            "manual_time_moves_water_particles": (
                differences["particles_t0_vs_t1"] is not None
                and differences["particles_t0_vs_t1"] > 1.0e-6
            ),
            "seed_changes_water_particle_pattern": (
                differences["seed_default_vs_changed"] is not None
                and differences["seed_default_vs_changed"] > 1.0e-6
            ),
            "combined_mode_adds_particles_to_ink_wash": (
                differences["combined_vs_ink_wash"] is not None
                and differences["combined_vs_ink_wash"] > 1.0e-6
            ),
            "module_enable_switch_matches_demo_toggle": (
                int(ink_switch.par.index.eval())
                == int(bool(demo.par.Inkflowenabled.eval()))
            ),
            "particle_columns_maximum_is_500": (
                float(ink_flow.par.Particledensity.max) == 500.0
            ),
            "maximum_density_cooks_visible_output": (
                float(np.std(maximum_density)) > 1.0e-5
            ),
            "every_numeric_slider_is_covered": (
                EXPECTED_SLIDER_NAMES
                == set(EDITABLE_CONTROL_NAMES)
                - {"Autotime", "Visualenabled", "Style", "Particlesenabled", "Particleshape"}
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
                bool(ink_flow.par.Time.readOnly)
                and "Autotime" in str(ink_flow.par.Time.expr)
                and "Manualtime" in str(ink_flow.par.Time.expr)
            ),
            "ink_flow_shader_has_no_errors": not _messages(
                ink_shader,
                "errors",
            ),
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "ink_work_metrics": _metrics(ink_work),
                "ink_wash_metrics": _metrics(ink_wash),
                "water_particle_metrics": _metrics(particles_t0),
                "combined_metrics": _metrics(combined),
                "maximum_density_metrics": _metrics(maximum_density),
                "slider_differences": slider_differences,
                "slider_finite": slider_finite,
                "slider_ranges": slider_ranges,
                "slider_endpoint_values": slider_endpoint_values,
                "time_scale": {
                    "effective_low": effective_time_low,
                    "effective_high": effective_time_high,
                    "range": time_scale_range,
                },
                "shader_errors": _messages(ink_shader, "errors"),
                "shader_warnings": _messages(ink_shader, "warnings"),
                "ok": all(checks.values()),
            }
        )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        demo.par.Inkflowenabled = saved["ink_flow_enabled"]
        demo.par.Glitchenabled = saved["glitch_enabled"]
        demo.par.Coloradjustmentenabled = saved["color_enabled"]
        demo.par.Motionenabled = saved["motion_enabled"]
        demo.par.Particlesenabled = saved["random_particles_enabled"]
        demo.par.Referenceparticlefieldenabled = saved["reference_particle_field_enabled"]
        demo.par.Calligraphicshadowenabled = saved["calligraphic_shadow_enabled"]
        demo.par.Inkorbitenabled = saved["ink_orbit_enabled"]
        demo.par.Applyvideofx = saved["apply_video_fx"]
        _set_values(ink_flow, saved["controls"])
        if saved["source_time_expression"]:
            source.par.vec0valuex.expr = saved["source_time_expression"]
        else:
            source.par.vec0valuex.expr = ""
            source.par.vec0valuex = saved["source_time_value"]
        ink_output.cook(force=True)

    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
