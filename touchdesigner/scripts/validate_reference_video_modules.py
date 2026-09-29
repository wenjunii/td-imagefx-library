"""Live rendered-pixel validation for the three reference-video modules.

Run only in a disposable development project.  The validator temporarily sets
the demo to 320 x 180, isolates each module, sweeps every writable numeric
control, exercises every menu, and restores the complete state in ``finally``.
It never saves the project.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "build" / "envoy-validation" / "reference-video-modules.json"
)
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"

DEMO_TOGGLES = (
    "Referenceparticlefieldenabled",
    "Calligraphicshadowenabled",
    "Inkorbitenabled",
    "Inkdreamenabled",
    "Layercompositeenabled",
    "Inkflowenabled",
    "Particlesenabled",
    "Glitchenabled",
    "Coloradjustmentenabled",
    "Motionenabled",
    "Applyvideofx",
)


def _case(activators, low, high):
    return (dict(activators), low, high)


MODULES = (
    {
        "name": "reference_particle_field",
        "id": "tdimagefx.core.reference-particle-field",
        "toggle": "Referenceparticlefieldenabled",
        "path": DEMO_PATH + "/reference_particle_field",
        "output": DEMO_PATH + "/reference_particle_field/out1_image",
        "shader": DEMO_PATH + "/reference_particle_field/effect_glsl_reference_particle_field",
        "switch": DEMO_PATH + "/reference_particle_field/enable_switch",
        "upstream": DEMO_PATH + "/layer_composite/out1_image",
        "base": {
            "Autotime": False, "Timescale": 1.0, "Manualtime": 0.71,
            "Mix": 1.0, "Speed": 0.42, "Density": 120, "Pointsize": 0.38,
            "Threshold": 0.10, "Thresholdsoftness": 0.16,
            "Sourceinfluence": 0.72, "Shape": "round", "Flowamount": 0.62,
            "Turbulence": 0.20, "Noisescale": 4.6, "Depth": 0.78,
            "Shimmer": 0.48, "Spread": 0.32, "Opacity": 0.94,
            "Palette": "electric_blue", "Backgroundmix": 0.92,
            "Backgroundcolorr": 0.002, "Backgroundcolorg": 0.006,
            "Backgroundcolorb": 0.018, "Backgroundcolora": 1.0,
            "Lowcolorr": 0.015, "Lowcolorg": 0.05, "Lowcolorb": 0.22,
            "Lowcolora": 1.0, "Midcolorr": 0.02, "Midcolorg": 0.42,
            "Midcolorb": 1.0, "Midcolora": 1.0, "Highcolorr": 0.80,
            "Highcolorg": 0.96, "Highcolorb": 1.0, "Highcolora": 1.0,
            "Seed": 41,
        },
        "menus": {
            "Shape": ("round", "square", "spark"),
            "Palette": ("source", "custom_gradient", "electric_blue", "prismatic"),
        },
        "sliders": {
            "Manualtime": _case({}, 0.11, 1.37),
            "Mix": _case({}, 0.05, 1.0),
            "Speed": _case({}, 0.05, 3.2),
            "Density": _case({}, 24, 260),
            "Pointsize": _case({}, 0.08, 0.95),
            "Threshold": _case({}, 0.01, 0.82),
            "Thresholdsoftness": _case({}, 0.01, 0.46),
            "Sourceinfluence": _case({}, 0.0, 1.0),
            "Flowamount": _case({}, 0.0, 1.20),
            "Turbulence": _case({}, 0.0, 0.72),
            "Noisescale": _case({}, 0.3, 18.0),
            "Depth": _case({}, 0.0, 1.0),
            "Shimmer": _case({}, 0.0, 1.0),
            "Spread": _case({}, 0.0, 1.20),
            "Opacity": _case({}, 0.08, 1.0),
            "Backgroundmix": _case({}, 0.0, 1.0),
            "Backgroundcolorr": _case({}, 0.0, 0.8),
            "Backgroundcolorg": _case({}, 0.0, 0.7),
            "Backgroundcolorb": _case({}, 0.0, 0.9),
            "Backgroundcolora": _case({}, 0.15, 1.0),
            "Lowcolorr": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Lowcolorg": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Lowcolorb": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Lowcolora": _case({"Palette": "custom_gradient"}, 0.15, 1.0),
            "Midcolorr": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Midcolorg": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Midcolorb": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Midcolora": _case({"Palette": "custom_gradient"}, 0.15, 1.0),
            "Highcolorr": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Highcolorg": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Highcolorb": _case({"Palette": "custom_gradient"}, 0.0, 1.0),
            "Highcolora": _case({"Palette": "custom_gradient"}, 0.15, 1.0),
            "Seed": _case({}, 3, 97),
        },
    },
    {
        "name": "calligraphic_shadow",
        "id": "tdimagefx.core.calligraphic-shadow",
        "toggle": "Calligraphicshadowenabled",
        "path": DEMO_PATH + "/calligraphic_shadow",
        "output": DEMO_PATH + "/calligraphic_shadow/out1_image",
        "shader": DEMO_PATH + "/calligraphic_shadow/effect_glsl_calligraphic_shadow",
        "switch": DEMO_PATH + "/calligraphic_shadow/enable_switch",
        "upstream": DEMO_PATH + "/reference_particle_field/out1_image",
        "base": {
            "Autotime": False, "Timescale": 1.0, "Manualtime": 0.71,
            "Mix": 1.0, "Speed": 0.36, "Maskmode": "dark",
            "Threshold": 0.38, "Softness": 0.12, "Sourceopacity": 1.0,
            "Paperamount": 0.86, "Shadowopacity": 0.96, "Offsetx": -0.18,
            "Offsety": 0.04, "Stretch": 1.35, "Curl": 0.055,
            "Turbulence": 0.11, "Noisescale": 3.8, "Strokeweight": 2.4,
            "Traillength": 1.0, "Trailsamples": 7, "Diffusion": 0.34,
            "Drybrush": 0.24, "Splatter": 0.16, "Particleamount": 0.72,
            "Particledensity": 0.58, "Particlesize": 3.0,
            "Particlesoftness": 0.18, "Particleopacity": 0.92,
            "Particlespeed": 0.85, "Particlejitter": 0.36,
            "Particleflow": 0.70, "Particlespread": 0.42,
            "Particleglow": 0.12, "Particlecolorr": 0.10,
            "Particlecolorg": 0.14, "Particlecolorb": 0.16,
            "Particlecolora": 1.0, "Glitteramount": 0.82,
            "Glitterdensity": 0.52, "Glittersize": 2.4,
            "Glitterthreshold": 0.22, "Glittersoftness": 0.10,
            "Glittershimmer": 0.78, "Glitterspeed": 1.15,
            "Glitterspread": 0.20, "Staramount": 0.30,
            "Glittercolorr": 0.76, "Glittercolorg": 0.92,
            "Glittercolorb": 1.0, "Glittercolora": 1.0,
            "Inkcolorr": 0.008,
            "Inkcolorg": 0.012, "Inkcolorb": 0.010, "Inkcolora": 1.0,
            "Papercolorr": 0.78, "Papercolorg": 0.88, "Papercolorb": 0.82,
            "Papercolora": 1.0, "Seed": 53,
        },
        "menus": {"Maskmode": ("dark", "light", "alpha")},
        "sliders": {
            "Manualtime": _case({}, 0.11, 1.37),
            "Mix": _case({}, 0.05, 1.0),
            "Speed": _case({}, 0.05, 3.2),
            "Threshold": _case({}, 0.05, 0.90),
            "Softness": _case({}, 0.01, 0.46),
            "Sourceopacity": _case({}, 0.0, 1.0),
            "Paperamount": _case({}, 0.0, 1.0),
            "Shadowopacity": _case({}, 0.08, 1.0),
            "Offsetx": _case({}, -0.55, 0.35),
            "Offsety": _case({}, -0.35, 0.35),
            "Stretch": _case({}, 0.20, 3.8),
            "Curl": _case({}, 0.0, 0.32),
            "Turbulence": _case({}, 0.0, 0.48),
            "Noisescale": _case({}, 0.3, 18.0),
            "Strokeweight": _case({}, 0.0, 11.0),
            "Traillength": _case({}, 0.15, 1.95),
            "Trailsamples": _case({}, 1, 8),
            "Diffusion": _case({}, 0.0, 1.0),
            "Drybrush": _case({}, 0.0, 1.0),
            "Splatter": _case({}, 0.0, 1.0),
            "Particleamount": _case({"Glitteramount": 0.0}, 0.0, 1.0),
            "Particledensity": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.03, 1.0),
            "Particlesize": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.6, 18.0),
            "Particlesoftness": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particleopacity": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.08, 1.0),
            "Particlespeed": _case({"Particleamount": 1.0, "Particleflow": 1.0, "Glitteramount": 0.0}, -5.0, 5.0),
            "Particlejitter": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particleflow": _case({"Particleamount": 1.0, "Particlespeed": 1.0, "Glitteramount": 0.0}, -3.0, 3.0),
            "Particlespread": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particleglow": _case({"Particleamount": 1.0, "Particlecolorr": 0.7, "Particlecolorg": 0.8, "Particlecolorb": 1.0, "Glitteramount": 0.0}, 0.0, 2.0),
            "Particlecolorr": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particlecolorg": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particlecolorb": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.0, 1.0),
            "Particlecolora": _case({"Particleamount": 1.0, "Glitteramount": 0.0}, 0.10, 1.0),
            "Glitteramount": _case({}, 0.0, 1.8),
            "Glitterdensity": _case({"Glitteramount": 1.0}, 0.03, 1.0),
            "Glittersize": _case({"Glitteramount": 1.0}, 0.6, 10.0),
            "Glitterthreshold": _case({"Glitteramount": 1.0}, 0.02, 0.88),
            "Glittersoftness": _case({"Glitteramount": 1.0}, 0.005, 0.48),
            "Glittershimmer": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Glitterspeed": _case({"Glitteramount": 1.0}, -5.0, 5.0),
            "Glitterspread": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Staramount": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Glittercolorr": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Glittercolorg": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Glittercolorb": _case({"Glitteramount": 1.0}, 0.0, 1.0),
            "Glittercolora": _case({"Glitteramount": 1.0}, 0.10, 1.0),
            "Inkcolorr": _case({}, 0.0, 1.0),
            "Inkcolorg": _case({}, 0.0, 1.0),
            "Inkcolorb": _case({}, 0.0, 1.0),
            "Inkcolora": _case({}, 0.10, 1.0),
            "Papercolorr": _case({}, 0.0, 1.0),
            "Papercolorg": _case({}, 0.0, 1.0),
            "Papercolorb": _case({}, 0.0, 1.0),
            "Papercolora": _case({}, 0.10, 1.0),
            "Seed": _case({}, 3, 97),
        },
    },
    {
        "name": "ink_orbit_canvas",
        "id": "tdimagefx.core.ink-orbit-canvas",
        "toggle": "Inkorbitenabled",
        "path": DEMO_PATH + "/ink_orbit_canvas",
        "output": DEMO_PATH + "/ink_orbit_canvas/out1_image",
        "shader": DEMO_PATH + "/ink_orbit_canvas/effect_glsl_ink_orbit_canvas",
        "switch": DEMO_PATH + "/ink_orbit_canvas/enable_switch",
        "upstream": DEMO_PATH + "/calligraphic_shadow/out1_image",
        "base": {
            "Autotime": False, "Timescale": 1.0, "Manualtime": 0.71,
            "Mix": 1.0, "Sourcemix": 0.0, "Sourceinfluence": 0.22,
            "Orbitspeed": 0.24, "Flowspeed": 0.48, "Ringcount": 7,
            "Dropletcount": 12, "Radius": 0.34, "Strokewidth": 0.022,
            "Scale": 1.0, "Centeru": 0.5, "Centerv": 0.48,
            "Perspective": 0.54, "Irregularity": 0.72, "Swirl": 0.62,
            "Stretch": 0.58, "Diffusion": 0.36, "Drybrush": 0.20,
            "Splatter": 0.18, "Shadowamount": 0.38, "Shadowoffsetx": 0.018,
            "Shadowoffsety": -0.025, "Shadowsoftness": 0.42,
            "Inkcolorr": 0.006, "Inkcolorg": 0.008, "Inkcolorb": 0.007,
            "Inkcolora": 1.0, "Papercolorr": 0.94, "Papercolorg": 0.95,
            "Papercolorb": 0.92, "Papercolora": 1.0, "Seed": 67,
        },
        "menus": {},
        "sliders": {
            "Manualtime": _case({}, 0.11, 1.37),
            "Mix": _case({}, 0.05, 1.0),
            "Sourcemix": _case({}, 0.0, 1.0),
            "Sourceinfluence": _case({}, 0.0, 1.0),
            "Orbitspeed": _case({}, -3.2, 3.2),
            "Flowspeed": _case({}, -3.2, 3.2),
            "Ringcount": _case({}, 1, 12),
            "Dropletcount": _case({}, 0, 24),
            "Radius": _case({}, 0.05, 0.92),
            "Strokewidth": _case({}, 0.003, 0.17),
            "Scale": _case({}, 0.20, 3.8),
            "Centeru": _case({}, 0.15, 0.85),
            "Centerv": _case({}, 0.15, 0.85),
            "Perspective": _case({}, 0.0, 1.0),
            "Irregularity": _case({}, 0.0, 1.0),
            "Swirl": _case({}, 0.0, 1.9),
            "Stretch": _case({}, 0.0, 1.0),
            "Diffusion": _case({}, 0.0, 1.0),
            "Drybrush": _case({}, 0.0, 1.0),
            "Splatter": _case({}, 0.0, 1.0),
            "Shadowamount": _case({}, 0.0, 1.0),
            "Shadowoffsetx": _case({}, -0.18, 0.18),
            "Shadowoffsety": _case({}, -0.18, 0.18),
            "Shadowsoftness": _case({}, 0.0, 1.0),
            "Inkcolorr": _case({}, 0.0, 1.0),
            "Inkcolorg": _case({}, 0.0, 1.0),
            "Inkcolorb": _case({}, 0.0, 1.0),
            "Inkcolora": _case({}, 0.10, 1.0),
            "Papercolorr": _case({}, 0.0, 1.0),
            "Papercolorg": _case({}, 0.0, 1.0),
            "Papercolorb": _case({}, 0.0, 1.0),
            "Papercolora": _case({}, 0.10, 1.0),
            "Seed": _case({}, 3, 97),
        },
    },
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
            raise RuntimeError("Missing {} parameter {}".format(component.name, name))
        parameter.val = value


def _sweep_sliders(component, output, base, cases):
    differences = {}
    finite = {}
    ranges = {}
    endpoints = {}
    for name, (activators, low_value, high_value) in cases.items():
        _set_values(component, base)
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
        endpoints[name] = {
            "low_requested": low_value, "low_evaluated": float(low_evaluated),
            "high_requested": high_value,
            "high_evaluated": float(high_evaluated),
        }
    return differences, finite, ranges, endpoints


def _validate_particle_shadow_edges(component, output, base):
    """Check semantic endpoints, not only whether a slider changes pixels."""
    saved = {name: component.par[name].eval() for name in base}
    upstream = component.inputs[0]
    fixture = component.parent().create(constantTOP, "particle_shadow_qa_fixture")
    checks = {}
    differences = {}
    endpoint_finite = {}
    try:
        fixture.par.colorr = 0.0
        fixture.par.colorg = 0.0
        fixture.par.colorb = 0.0
        fixture.par.alpha = 1.0
        fixture.par.outputresolution = "custom"
        fixture.par.resolutionw = 320
        fixture.par.resolutionh = 180
        fixture.outputConnectors[0].connect(component.inputConnectors[0])

        active = dict(base)
        active.update({
            "Autotime": False, "Manualtime": 0.0, "Speed": 0.0,
            "Maskmode": "dark", "Threshold": 0.5, "Softness": 0.01,
            "Paperamount": 1.0, "Sourceopacity": 0.0,
            "Papercolorr": 0.0, "Papercolorg": 0.0, "Papercolorb": 0.0,
            "Glitteramount": 0.0, "Particleamount": 1.0,
            "Particledensity": 0.65, "Particlesize": 8.0,
            "Particlesoftness": 0.1, "Particleopacity": 1.0,
            "Particlespeed": 1.0, "Particlejitter": 0.0,
            "Particleflow": 1.0, "Particlespread": 1.0,
            "Particleglow": 0.0, "Particlecolorr": 1.0,
            "Particlecolorg": 1.0, "Particlecolorb": 1.0,
            "Particlecolora": 1.0, "Offsetx": 1.0, "Offsety": 0.0,
        })
        _set_values(component, active)
        frame_zero = _capture(output)
        component.par.Manualtime = 1.0
        frame_forward = _capture(output)
        differences["positive_flow_right_shift"] = _difference(
            frame_forward[:, 8:, :], frame_zero[:, :-8, :]
        )
        component.par.Particleflow = -1.0
        frame_reverse = _capture(output)
        differences["negative_flow_left_shift"] = _difference(
            frame_reverse[:, :-8, :], frame_zero[:, 8:, :]
        )
        checks["particle_positive_flow_follows_shadow_direction"] = (
            differences["positive_flow_right_shift"] <= 1.0e-5
        )
        checks["particle_negative_flow_reverses_direction"] = (
            differences["negative_flow_left_shift"] <= 1.0e-5
        )
        checks["particle_fixture_has_visible_grains"] = (
            float(np.max(frame_zero[:, :, :3])) > 0.1
        )

        _set_values(component, active)
        component.par.Maskmode = "light"
        component.par.Particleopacity = 0.0
        empty = _capture(output)
        component.par.Particleopacity = 1.0
        empty_with_particles = _capture(output)
        differences["empty_mask_max_spread"] = _difference(empty, empty_with_particles)
        checks["particle_max_spread_preserves_empty_background"] = (
            differences["empty_mask_max_spread"] <= 1.0e-6
        )

        component.par.Particleamount = 0.0
        component.par.Glitteramount = 2.0
        component.par.Glitterthreshold = 0.0
        component.par.Glittersoftness = 1.0
        component.par.Glitterspread = 1.0
        differences["empty_mask_max_glitter"] = _difference(empty, _capture(output))
        checks["glitter_extreme_settings_preserve_empty_background"] = (
            differences["empty_mask_max_glitter"] <= 1.0e-6
        )

        for name in ("Particledensity", "Particleopacity", "Particlecolora"):
            _set_values(component, active)
            component.par[name] = 0.0
            image = _capture(output)
            differences[name + "_zero"] = _difference(image, empty)
            checks[name.lower() + "_zero_removes_particles"] = (
                differences[name + "_zero"] <= 1.0e-6
            )

        _set_values(component, active)
        component.par.Particleamount = 0.0
        off_first = _capture(output)
        for name in base:
            if name.startswith("Particle") and name != "Particleamount":
                component.par[name] = float(component.par[name].max)
        off_second = _capture(output)
        differences["particle_amount_zero"] = _difference(off_first, off_second)
        checks["particle_amount_zero_ignores_particle_controls"] = (
            differences["particle_amount_zero"] <= 1.0e-6
        )

        _set_values(component, active)
        component.par.Particlespeed = 0.0
        component.par.Particlejitter = 1.0
        frozen_first = _capture(output)
        component.par.Manualtime = 3.0
        frozen_second = _capture(output)
        differences["particle_speed_zero"] = _difference(frozen_first, frozen_second)
        checks["particle_speed_zero_freezes_flow_and_jitter"] = (
            differences["particle_speed_zero"] <= 1.0e-6
        )

        for name in base:
            if not name.startswith("Particle"):
                continue
            parameter = component.par[name]
            endpoint_finite[name] = True
            for value in (float(parameter.min), float(parameter.max)):
                _set_values(component, active)
                parameter.val = value
                image = _capture(output)
                endpoint_finite[name] = endpoint_finite[name] and bool(
                    np.isfinite(image).all()
                    and abs(float(parameter.eval()) - value) <= 1.0e-6
                )
        checks["particle_actual_min_max_values_are_finite_and_accepted"] = all(
            endpoint_finite.values()
        )
    finally:
        upstream.outputConnectors[0].connect(component.inputConnectors[0])
        fixture.destroy()
        _set_values(component, saved)
        output.cook(force=True)
    return {"checks": checks, "differences": differences, "endpoint_finite": endpoint_finite}


def _validate_module(demo, definition, operators):
    component = operators["component"]
    output = operators["output"]
    upstream = operators["upstream"]
    shader = operators["shader"]
    enable_switch = operators["switch"]
    for toggle in DEMO_TOGGLES:
        demo.par[toggle] = False
    _set_values(component, definition["base"])

    upstream_image = _capture(upstream)
    demo.par[definition["toggle"]] = False
    module_bypass = _capture(output)
    demo.par[definition["toggle"]] = True
    component.par.Mix = 0.0
    mix_bypass = _capture(output)
    _set_values(component, definition["base"])
    showcase = _capture(output)

    component.par.Autotime = False
    component.par.Manualtime = 0.17
    time_first = _capture(output)
    component.par.Manualtime = 1.19
    time_second = _capture(output)

    menu_signatures = {}
    menu_finite = {}
    menu_exact = {}
    for name, expected_values in definition["menus"].items():
        _set_values(component, definition["base"])
        signatures = {}
        finite = {}
        for value in expected_values:
            component.par[name] = value
            image = _capture(output)
            signatures[value] = _signature(image)
            finite[value] = bool(np.isfinite(image).all())
        menu_signatures[name] = signatures
        menu_finite[name] = finite
        menu_exact[name] = tuple(str(item) for item in component.par[name].menuNames)

    slider_differences, slider_finite, slider_ranges, endpoints = _sweep_sliders(
        component,
        output,
        definition["base"],
        definition["sliders"],
    )
    particle_edges = None
    if definition["name"] == "calligraphic_shadow":
        particle_edges = _validate_particle_shadow_edges(
            component, output, definition["base"]
        )
    _set_values(component, definition["base"])
    component.par.Autotime = True
    component.par.Timescale = 0.5
    effective_time_low = float(component.par.Time.eval())
    component.par.Timescale = 1.5
    effective_time_high = float(component.par.Time.eval())
    timescale = component.par.Timescale
    timescale_range = {
        "min": float(timescale.min), "max": float(timescale.max),
        "norm_min": float(timescale.normMin),
        "norm_max": float(timescale.normMax),
        "clamp_min": bool(timescale.clampMin),
        "clamp_max": bool(timescale.clampMax),
    }

    numeric_controls = set(definition["sliders"]) | {"Timescale"}
    # Compare against native controls, not just the hand-maintained test cases:
    # omitting a new parameter from both base and sliders must fail coverage.
    expected_numeric = {
        parameter.name for parameter in component.customPars
        if parameter.isNumber and not parameter.isToggle
        and not parameter.isMenu and not parameter.readOnly
    }
    native_menus = {p.name for p in component.customPars if p.isMenu}
    native_toggles = {p.name for p in component.customPars if p.isToggle}
    differences = {
        "module_bypass_vs_upstream": _difference(module_bypass, upstream_image),
        "mix_zero_vs_upstream": _difference(mix_bypass, upstream_image),
        "showcase_vs_upstream": _difference(showcase, upstream_image),
        "manual_time_change": _difference(time_first, time_second),
    }
    shader_errors = _messages(shader, "errors")
    shader_warnings = _messages(shader, "warnings")
    checks = {
        "module_bypass_matches_upstream": (
            differences["module_bypass_vs_upstream"] is not None
            and differences["module_bypass_vs_upstream"] <= 1.0e-6
        ),
        "mix_zero_matches_upstream": (
            differences["mix_zero_vs_upstream"] is not None
            and differences["mix_zero_vs_upstream"] <= 1.0e-6
        ),
        "showcase_changes_upstream": (
            differences["showcase_vs_upstream"] is not None
            and differences["showcase_vs_upstream"] > 1.0e-5
        ),
        "manual_time_changes_output": (
            differences["manual_time_change"] is not None
            and differences["manual_time_change"] > 1.0e-7
        ),
        "menus_match_contract": all(
            menu_exact[name] == tuple(expected)
            for name, expected in definition["menus"].items()
        ),
        "menu_outputs_are_finite": all(
            all(values.values()) for values in menu_finite.values()
        ),
        "menu_options_are_visually_distinct": all(
            len(set(values.values())) == len(values)
            for values in menu_signatures.values()
        ),
        "every_numeric_control_is_covered": numeric_controls == expected_numeric,
        "every_menu_is_covered": native_menus == set(definition["menus"]),
        "every_toggle_is_covered": native_toggles == {"Enabled", "Autotime"},
        "every_numeric_control_changes_output": all(
            value is not None and value > 1.0e-8
            for value in slider_differences.values()
        ),
        "every_numeric_control_stays_finite": all(slider_finite.values()),
        "every_numeric_control_has_valid_range": (
            all(
                values["min"] < values["max"]
                and abs(values["norm_min"] - values["min"]) <= 1.0e-9
                and abs(values["norm_max"] - values["max"]) <= 1.0e-9
                and values["clamp_min"] and values["clamp_max"]
                for values in slider_ranges.values()
            )
            and timescale_range["min"] < timescale_range["max"]
            and timescale_range["clamp_min"]
            and timescale_range["clamp_max"]
        ),
        "every_numeric_control_accepts_endpoints": all(
            abs(values["low_requested"] - values["low_evaluated"]) <= 1.0e-6
            and abs(values["high_requested"] - values["high_evaluated"]) <= 1.0e-6
            for values in endpoints.values()
        ),
        "time_scale_changes_effective_time": (
            abs(effective_time_high - effective_time_low) > 1.0e-3
        ),
        "effective_time_is_read_only_and_resolved": (
            bool(component.par.Time.readOnly)
            and "Autotime" in str(component.par.Time.expr)
            and "Manualtime" in str(component.par.Time.expr)
        ),
        "enable_switch_matches_demo_toggle": (
            int(enable_switch.par.index.eval())
            == int(bool(demo.par[definition["toggle"]].eval()))
        ),
        "output_resolution_matches_upstream": (
            int(output.width) == int(upstream.width)
            and int(output.height) == int(upstream.height)
        ),
        "shader_has_no_errors": not shader_errors,
        "shader_has_no_warnings": not shader_warnings,
    }
    if particle_edges is not None:
        checks.update(particle_edges["checks"])
    return {
        "module_id": definition["id"],
        "checks": checks,
        "differences": differences,
        "menu_signatures": menu_signatures,
        "slider_differences": slider_differences,
        "slider_finite": slider_finite,
        "slider_ranges": slider_ranges,
        "slider_endpoint_values": endpoints,
        "particle_shadow_edges": particle_edges,
        "native_control_inventory": {
            "numeric": sorted(expected_numeric),
            "menus": sorted(native_menus),
            "toggles": sorted(native_toggles),
        },
        "time_scale": {
            "effective_low": effective_time_low,
            "effective_high": effective_time_high,
            "range": timescale_range,
        },
        "shader_errors": shader_errors,
        "shader_warnings": shader_warnings,
        "ok": all(checks.values()),
    }


def validate(write_report=True):
    """Validate bypass, timing, menus, and every numeric control on all modules."""

    demo = op(DEMO_PATH)
    source = op(SOURCE_PATH)
    required = {"demo": demo, "source": source}
    module_operators = {}
    for definition in MODULES:
        operators = {
            "component": op(definition["path"]),
            "output": op(definition["output"]),
            "shader": op(definition["shader"]),
            "switch": op(definition["switch"]),
            "upstream": op(definition["upstream"]),
        }
        module_operators[definition["name"]] = operators
        for role, operator in operators.items():
            required["{}_{}".format(definition["name"], role)] = operator
    missing = [name for name, operator in required.items() if operator is None]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "validator": "reference-video-modules",
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
        report["error"] = "Required reference-video module operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    saved = {
        "toggles": {name: demo.par[name].eval() for name in DEMO_TOGGLES},
        "resolution_preset": demo.par.Resolutionpreset.eval(),
        "custom_width": demo.par.Customwidth.eval(),
        "custom_height": demo.par.Customheight.eval(),
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
        "controls": {
            definition["name"]: {
                name: module_operators[definition["name"]]["component"].par[name].eval()
                for name in definition["base"]
            }
            for definition in MODULES
        },
    }

    try:
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        demo.par.Resolutionpreset = "custom"
        demo.par.Customwidth = 320
        demo.par.Customheight = 180
        module_reports = {}
        for definition in MODULES:
            module_reports[definition["name"]] = _validate_module(
                demo,
                definition,
                module_operators[definition["name"]],
            )
        checks = {
            "all_three_modules_present": len(module_reports) == 3,
            "all_three_modules_pass": all(
                item["ok"] for item in module_reports.values()
            ),
        }
        report.update(
            {
                "checks": checks,
                "modules": module_reports,
                "ok": all(checks.values()),
            }
        )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        for definition in MODULES:
            _set_values(
                module_operators[definition["name"]]["component"],
                saved["controls"][definition["name"]],
            )
        for name, value in saved["toggles"].items():
            demo.par[name] = value
        demo.par.Resolutionpreset = saved["resolution_preset"]
        demo.par.Customwidth = saved["custom_width"]
        demo.par.Customheight = saved["custom_height"]
        if saved["source_time_expression"]:
            source.par.vec0valuex.expr = saved["source_time_expression"]
        else:
            source.par.vec0valuex.expr = ""
            source.par.vec0valuex = saved["source_time_value"]

    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
