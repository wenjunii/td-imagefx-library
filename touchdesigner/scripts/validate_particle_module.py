"""Live pixel and routing validation for the random-move particle module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "build" / "envoy-validation" / "particle-module.json"
DEMO_PATH = "/project1/imagefx_demo"
PARTICLE_PATH = DEMO_PATH + "/particle_random_move"
INK_FLOW_PATH = DEMO_PATH + "/ink_flow"
OUTPUT_PATH = DEMO_PATH + "/out1_image"
SOURCE_PATH = DEMO_PATH + "/source_image"
ROUTER_PATH = DEMO_PATH + "/video_fx_router"
PARTICLE_OUTPUT_PATH = PARTICLE_PATH + "/out1_particles"
PARTICLE_SHADER_PATH = PARTICLE_PATH + "/effect_glsl_particles"

EXPECTED_SHAPES = (
    "circle",
    "square",
    "diamond",
    "triangle",
    "hexagon",
    "ring",
    "star",
    "line",
)

EXPECTED_MOTION_MODES = (
    "orbit",
    "wander",
    "wave",
    "swirl",
    "fountain",
    "rain",
    "explosion",
    "flow",
)

EDITABLE_CONTROL_NAMES = (
    "Autotime",
    "Timescale",
    "Manualtime",
    "Density",
    "Size",
    "Sizevariation",
    "Aspectx",
    "Aspecty",
    "Rotation",
    "Spin",
    "Softness",
    "Hollow",
    "Speed",
    "Speedvariation",
    "Moveamount",
    "Jitter",
    "Driftx",
    "Drifty",
    "Turbulence",
    "Scatter",
    "Pulseamount",
    "Pulserate",
    "Seed",
    "Shape",
    "Motionmode",
    "Sourceblend",
    "Opacity",
    "Opacityvariation",
    "Sampleoffsetx",
    "Sampleoffsety",
    "Tintcolorr",
    "Tintcolorg",
    "Tintcolorb",
    "Tintcolora",
    "Tintamount",
    "Hue",
    "Huevariation",
    "Saturation",
    "Brightness",
    "Backgroundr",
    "Backgroundg",
    "Backgroundb",
    "Backgrounda",
)

BASE_VALUES = {
    "Autotime": False,
    "Timescale": 1.0,
    "Manualtime": 1.137,
    "Density": 72,
    "Size": 0.72,
    "Sizevariation": 0.0,
    "Aspectx": 1.0,
    "Aspecty": 1.0,
    "Rotation": 0.0,
    "Spin": 0.0,
    "Softness": 0.0,
    "Hollow": 0.0,
    "Speed": 0.8,
    "Speedvariation": 0.0,
    "Moveamount": 0.55,
    "Jitter": 0.12,
    "Driftx": 0.08,
    "Drifty": 0.03,
    "Turbulence": 0.0,
    "Scatter": 0.0,
    "Pulseamount": 0.0,
    "Pulserate": 1.0,
    "Seed": 1,
    "Shape": "square",
    "Motionmode": "orbit",
    "Sourceblend": 0.0,
    "Opacity": 1.0,
    "Opacityvariation": 0.0,
    "Sampleoffsetx": 0.0,
    "Sampleoffsety": 0.0,
    "Tintcolorr": 1.0,
    "Tintcolorg": 1.0,
    "Tintcolorb": 1.0,
    "Tintcolora": 1.0,
    "Tintamount": 0.0,
    "Hue": 0.0,
    "Huevariation": 0.0,
    "Saturation": 1.0,
    "Brightness": 0.0,
    "Backgroundr": 0.0,
    "Backgroundg": 0.0,
    "Backgroundb": 0.0,
    "Backgrounda": 0.0,
}

SLIDER_CASES = {
    "Manualtime": ({}, 0.2, 1.4),
    "Density": ({}, 32, 110),
    "Size": ({}, 0.24, 1.0),
    "Sizevariation": ({}, 0.0, 0.85),
    "Aspectx": ({}, 0.5, 2.2),
    "Aspecty": ({}, 0.5, 2.2),
    "Rotation": ({"Shape": "square"}, -55.0, 40.0),
    "Spin": ({"Shape": "square"}, -1.5, 1.5),
    "Softness": ({}, 0.0, 0.85),
    "Hollow": ({}, 0.0, 0.78),
    "Speed": ({}, 0.25, 2.2),
    "Speedvariation": ({}, 0.0, 0.9),
    "Moveamount": ({}, 0.1, 1.1),
    "Jitter": ({}, 0.0, 0.55),
    "Driftx": ({}, -0.65, 0.65),
    "Drifty": ({}, -0.65, 0.65),
    "Turbulence": ({}, 0.0, 0.85),
    "Scatter": ({}, 0.0, 0.85),
    "Pulseamount": ({"Manualtime": 0.37}, 0.0, 0.8),
    "Pulserate": ({"Manualtime": 0.37, "Pulseamount": 0.8}, 0.4, 3.2),
    "Seed": ({}, 1, 47),
    "Sourceblend": ({}, 0.0, 0.85),
    "Opacity": ({}, 0.2, 1.0),
    "Opacityvariation": ({}, 0.0, 0.9),
    "Sampleoffsetx": ({}, -0.2, 0.2),
    "Sampleoffsety": ({}, -0.2, 0.2),
    "Tintcolorr": ({"Tintamount": 0.85}, 0.0, 1.0),
    "Tintcolorg": ({"Tintamount": 0.85}, 0.0, 1.0),
    "Tintcolorb": ({"Tintamount": 0.85}, 0.0, 1.0),
    "Tintcolora": (
        {"Tintamount": 1.0, "Tintcolorr": 0.85, "Tintcolorg": 0.15},
        0.1,
        1.0,
    ),
    "Tintamount": (
        {"Tintcolorr": 0.85, "Tintcolorg": 0.15, "Tintcolorb": 0.65},
        0.0,
        1.0,
    ),
    "Hue": ({}, -0.25, 0.3),
    "Huevariation": ({}, 0.0, 0.9),
    "Saturation": ({}, 0.2, 2.2),
    "Brightness": ({}, -0.3, 0.3),
    "Backgroundr": ({"Backgrounda": 1.0}, 0.0, 1.0),
    "Backgroundg": ({"Backgrounda": 1.0}, 0.0, 1.0),
    "Backgroundb": ({"Backgrounda": 1.0}, 0.0, 1.0),
    "Backgrounda": (
        {"Backgroundr": 0.25, "Backgroundg": 0.45, "Backgroundb": 0.75},
        0.0,
        1.0,
    ),
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
    return float(np.mean(np.abs(left.astype(np.float32) - right.astype(np.float32))))


def _signature(image):
    row_step = max(1, image.shape[0] // 32)
    column_step = max(1, image.shape[1] // 32)
    sample = np.ascontiguousarray(
        image[::row_step, ::column_step, : min(3, image.shape[-1])]
    )
    import hashlib

    return hashlib.sha256(sample.tobytes()).hexdigest()


def _set_values(component, values):
    for name, value in values.items():
        parameter = component.par[name]
        if parameter is None:
            raise RuntimeError("Missing particle parameter {}".format(name))
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
        if parameter is None:
            raise RuntimeError("Missing particle slider {}".format(name))
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
            "min": float(parameter.min),
            "max": float(parameter.max),
            "norm_min": float(parameter.normMin),
            "norm_max": float(parameter.normMax),
            "clamp_min": bool(parameter.clampMin),
            "clamp_max": bool(parameter.clampMax),
        }
        endpoint_values[name] = {
            "low_requested": low_value,
            "low_evaluated": float(low_evaluated),
            "high_requested": high_value,
            "high_evaluated": float(high_evaluated),
        }
    return differences, finite, ranges, endpoint_values


def _capture_route(demo, output, router, particles_enabled, apply_video_fx):
    demo.par.Particlesenabled = particles_enabled
    demo.par.Applyvideofx = apply_video_fx
    image = _capture(output)
    return {
        "particles_enabled": bool(particles_enabled),
        "apply_video_fx": bool(apply_video_fx),
        "router_index": int(router.par.index.eval()),
        "metrics": _metrics(image),
        "_image": image,
    }


def validate(write_report=True):
    """Exercise all four demo routes plus deterministic motion and seed changes."""

    required = {
        "demo": op(DEMO_PATH),
        "ink_flow": op(INK_FLOW_PATH),
        "particles": op(PARTICLE_PATH),
        "particle_output": op(PARTICLE_OUTPUT_PATH),
        "particle_shader": op(PARTICLE_SHADER_PATH),
        "source": op(SOURCE_PATH),
        "router": op(ROUTER_PATH),
        "output": op(OUTPUT_PATH),
    }
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
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
        report["error"] = "Required particle demo operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    demo = required["demo"]
    particles = required["particles"]
    particle_output = required["particle_output"]
    particle_shader = required["particle_shader"]
    source = required["source"]
    router = required["router"]
    output = required["output"]

    saved = {
        "particles_enabled": demo.par.Particlesenabled.eval(),
        "ink_flow_enabled": demo.par.Inkflowenabled.eval(),
        "glitch_enabled": demo.par.Glitchenabled.eval(),
        "color_enabled": demo.par.Coloradjustmentenabled.eval(),
        "motion_enabled": demo.par.Motionenabled.eval(),
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "controls": {
            name: particles.par[name].eval()
            for name in EDITABLE_CONTROL_NAMES
        },
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        # Freeze both generators so route comparisons cannot be contaminated by
        # a later animation frame.
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Inkflowenabled = False
        demo.par.Glitchenabled = False
        demo.par.Coloradjustmentenabled = False
        demo.par.Motionenabled = False
        _set_values(particles, BASE_VALUES)

        source_image = _capture(source)
        routes = {}
        for particles_enabled, apply_video_fx in (
            (False, False),
            (False, True),
            (True, False),
            (True, True),
        ):
            key = "{}{}".format(
                int(bool(particles_enabled)),
                int(bool(apply_video_fx)),
            )
            routes[key] = _capture_route(
                demo,
                output,
                router,
                particles_enabled,
                apply_video_fx,
            )

        demo.par.Particlesenabled = True
        demo.par.Applyvideofx = False
        particles.par.Manualtime = 0.0
        motion_start = _capture(particle_output)
        particles.par.Manualtime = 1.0
        motion_end = _capture(particle_output)
        particles.par.Manualtime = 0.0
        seed_start = _capture(particle_output)
        particles.par.Seed = int(BASE_VALUES["Seed"]) + 17
        seed_end = _capture(particle_output)
        particles.par.Density = int(particles.par.Density.max)
        maximum_density = _capture(particle_output)

        _set_values(particles, BASE_VALUES)
        shape_names = tuple(str(item) for item in particles.par.Shape.menuNames)
        shape_signatures = {}
        shape_differences = {}
        for shape in EXPECTED_SHAPES:
            particles.par.Shape = shape
            image = _capture(particle_output)
            shape_signatures[shape] = _signature(image)
            shape_differences[shape] = _mean_absolute_difference(
                image,
                source_image,
            )

        _set_values(particles, BASE_VALUES)
        motion_names = tuple(
            str(item) for item in particles.par.Motionmode.menuNames
        )
        motion_signatures = {}
        motion_differences = {}
        for mode in EXPECTED_MOTION_MODES:
            particles.par.Motionmode = mode
            image = _capture(particle_output)
            motion_signatures[mode] = _signature(image)
            motion_differences[mode] = _mean_absolute_difference(
                image,
                source_image,
            )

        (
            slider_differences,
            slider_finite,
            slider_ranges,
            slider_endpoint_values,
        ) = _sweep_sliders(particles, particle_output)

        _set_values(particles, BASE_VALUES)
        particles.par.Autotime = True
        particles.par.Timescale = 0.5
        effective_time_low = float(particles.par.Time.eval())
        particles.par.Timescale = 1.5
        effective_time_high = float(particles.par.Time.eval())
        time_scale_range = {
            "min": float(particles.par.Timescale.min),
            "max": float(particles.par.Timescale.max),
            "norm_min": float(particles.par.Timescale.normMin),
            "norm_max": float(particles.par.Timescale.normMax),
            "clamp_min": bool(particles.par.Timescale.clampMin),
            "clamp_max": bool(particles.par.Timescale.clampMax),
        }

        differences = {
            "bypass_vs_source": _mean_absolute_difference(
                routes["00"]["_image"],
                source_image,
            ),
            "particles_vs_source": _mean_absolute_difference(
                routes["10"]["_image"],
                source_image,
            ),
            "source_fx_vs_source": _mean_absolute_difference(
                routes["01"]["_image"],
                routes["00"]["_image"],
            ),
            "particle_fx_vs_particles": _mean_absolute_difference(
                routes["11"]["_image"],
                routes["10"]["_image"],
            ),
            "motion_t0_vs_t1": _mean_absolute_difference(
                motion_start,
                motion_end,
            ),
            "seed_default_vs_changed": _mean_absolute_difference(
                seed_start,
                seed_end,
            ),
        }
        checks = {
            "all_router_indices_match": all(
                item["router_index"] == int(item["apply_video_fx"])
                for item in routes.values()
            ),
            "particle_bypass_matches_source": (
                differences["bypass_vs_source"] is not None
                and differences["bypass_vs_source"] <= 1.0e-6
            ),
            "particles_change_source": (
                differences["particles_vs_source"] is not None
                and differences["particles_vs_source"] > 1.0e-4
            ),
            "video_fx_change_source": (
                differences["source_fx_vs_source"] is not None
                and differences["source_fx_vs_source"] > 1.0e-6
            ),
            "video_fx_change_particles": (
                differences["particle_fx_vs_particles"] is not None
                and differences["particle_fx_vs_particles"] > 1.0e-6
            ),
            "manual_time_moves_particles": (
                differences["motion_t0_vs_t1"] is not None
                and differences["motion_t0_vs_t1"] > 1.0e-5
            ),
            "seed_changes_pattern": (
                differences["seed_default_vs_changed"] is not None
                and differences["seed_default_vs_changed"] > 1.0e-5
            ),
            "particle_shader_has_no_errors": not _messages(
                particle_shader,
                "errors",
            ),
            "particle_shader_has_no_warnings": not _messages(
                particle_shader,
                "warnings",
            ),
            "particle_columns_maximum_is_500": (
                float(particles.par.Density.max) == 500.0
            ),
            "maximum_density_cooks_visible_output": (
                float(np.std(maximum_density)) > 1.0e-5
            ),
            "shape_menu_contains_exactly_eight_shapes": (
                shape_names == EXPECTED_SHAPES
            ),
            "every_shape_changes_source": all(
                value is not None and value > 1.0e-5
                for value in shape_differences.values()
            ),
            "all_shapes_are_visually_distinct": (
                len(set(shape_signatures.values())) == len(EXPECTED_SHAPES)
            ),
            "motion_menu_contains_exactly_eight_modes": (
                motion_names == EXPECTED_MOTION_MODES
            ),
            "every_motion_mode_changes_source": all(
                value is not None and value > 1.0e-5
                for value in motion_differences.values()
            ),
            "all_motion_modes_are_visually_distinct": (
                len(set(motion_signatures.values()))
                == len(EXPECTED_MOTION_MODES)
            ),
            "every_numeric_slider_is_covered": (
                EXPECTED_SLIDER_NAMES
                == set(EDITABLE_CONTROL_NAMES)
                - {"Autotime", "Shape", "Motionmode"}
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
                    and values["clamp_min"]
                    and values["clamp_max"]
                    for values in slider_ranges.values()
                )
                and time_scale_range["min"] < time_scale_range["max"]
                and abs(time_scale_range["norm_min"] - time_scale_range["min"])
                <= 1.0e-9
                and abs(time_scale_range["norm_max"] - time_scale_range["max"])
                <= 1.0e-9
                and time_scale_range["clamp_min"]
                and time_scale_range["clamp_max"]
            ),
            "every_numeric_slider_accepts_test_endpoints": all(
                abs(values["low_requested"] - values["low_evaluated"])
                <= 1.0e-6
                and abs(values["high_requested"] - values["high_evaluated"])
                <= 1.0e-6
                for values in slider_endpoint_values.values()
            ),
            "time_scale_changes_effective_time": (
                abs(effective_time_high - effective_time_low) > 1.0e-3
            ),
            "effective_time_is_read_only_and_resolved": (
                bool(particles.par.Time.readOnly)
                and "Autotime" in str(particles.par.Time.expr)
                and "Manualtime" in str(particles.par.Time.expr)
            ),
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "maximum_density_metrics": _metrics(maximum_density),
                "particle_metrics": _metrics(motion_start),
                "shape_differences": shape_differences,
                "shape_signatures": shape_signatures,
                "motion_differences": motion_differences,
                "motion_signatures": motion_signatures,
                "slider_differences": slider_differences,
                "slider_finite": slider_finite,
                "slider_ranges": slider_ranges,
                "slider_endpoint_values": slider_endpoint_values,
                "time_scale": {
                    "effective_low": effective_time_low,
                    "effective_high": effective_time_high,
                    "range": time_scale_range,
                },
                "routes": {
                    key: {
                        field: value
                        for field, value in item.items()
                        if field != "_image"
                    }
                    for key, item in routes.items()
                },
                "shader_errors": _messages(particle_shader, "errors"),
                "shader_warnings": _messages(particle_shader, "warnings"),
                "ok": all(checks.values()),
            }
        )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        demo.par.Particlesenabled = saved["particles_enabled"]
        demo.par.Inkflowenabled = saved["ink_flow_enabled"]
        demo.par.Glitchenabled = saved["glitch_enabled"]
        demo.par.Coloradjustmentenabled = saved["color_enabled"]
        demo.par.Motionenabled = saved["motion_enabled"]
        demo.par.Applyvideofx = saved["apply_video_fx"]
        _set_values(particles, saved["controls"])
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
