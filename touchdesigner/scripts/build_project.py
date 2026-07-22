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
    "reference": "image_b",
    "reference_image": "image_b",
    "clean_plate": "image_b",
    "background": "image_b",
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
uniform float uTime;
void main() {
    vec2 uv = vUV.st;
    uv = fract(uv + vec2(
        0.030 * sin(uTime * 0.70),
        0.025 * sin(uTime * 0.53)
    ));
    vec3 phase = vec3(0.0, 2.1, 4.2);
    vec3 color = 0.5 + 0.5 * cos(
        6.28318530718 * (uv.x + 0.35 * uv.y) + phase + uTime * 0.45
    );
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

DEMO_SECONDARY_IMAGE_SHADER = r"""
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = clamp(vUV.st + vec2(0.018, -0.012), 0.0, 1.0);
    vec4 source = texture(sTD2DInputs[0], uv);
    float changedRegion = smoothstep(0.42, 0.58, vUV.x);
    vec3 changed = mix(source.rgb, source.gbr, 0.48);
    vec3 color = mix(source.rgb, changed, changedRegion);
    fragColor = TDOutputSwizzle(vec4(color, source.a));
}
""".strip()

DEMO_OUTPUT_PRESETS = (
    ("hd", "HD 1920 x 1080", 1920, 1080),
    ("uhd4k", "4K UHD 3840 x 2160", 3840, 2160),
    ("custom", "Custom", None, None),
)

DEMO_OUTPUT_PARAMETER_DEFINITIONS = (
    {
        "name": "Resolutionpreset",
        "label": "Resolution Preset",
        "type": "menu",
        "default": "hd",
        "menu_names": [item[0] for item in DEMO_OUTPUT_PRESETS],
        "menu_labels": [item[1] for item in DEMO_OUTPUT_PRESETS],
        "description": (
            "Choose the default 1920 x 1080 output, 4K UHD, or an adjustable "
            "custom resolution."
        ),
    },
    {
        "name": "Customwidth",
        "label": "Custom Width",
        "type": "int",
        "default": 1920,
        "min": 16,
        "max": 8192,
        "description": (
            "Output width used by the Custom preset. Values are bounded to "
            "16 through 8192 pixels."
        ),
    },
    {
        "name": "Customheight",
        "label": "Custom Height",
        "type": "int",
        "default": 1080,
        "min": 16,
        "max": 8192,
        "description": (
            "Output height used by the Custom preset. Values are bounded to "
            "16 through 8192 pixels."
        ),
    },
)


def _demo_output_resolution_expression(dimension):
    """Return a component-relative expression for the selected output size."""

    if dimension == "width":
        hd, uhd, custom = 1920, 3840, "Customwidth"
    elif dimension == "height":
        hd, uhd, custom = 1080, 2160, "Customheight"
    else:
        raise ValueError("Output dimension must be width or height")
    return (
        "{hd} if parent().par.Resolutionpreset.eval() == 'hd' else "
        "({uhd} if parent().par.Resolutionpreset.eval() == 'uhd4k' else "
        "int(parent().par.{custom}.eval()))"
    ).format(hd=hd, uhd=uhd, custom=custom)


PARTICLE_RANDOM_MOVE_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uDensity;
uniform float uSize;
uniform float uSizeVariation;
uniform vec2 uAspect;
uniform float uRotation;
uniform float uSpin;
uniform float uSoftness;
uniform float uHollow;
uniform float uSpeed;
uniform float uSpeedVariation;
uniform float uMoveAmount;
uniform float uJitter;
uniform float uTurbulence;
uniform float uScatter;
uniform float uPulseAmount;
uniform float uPulseRate;
uniform float uSeed;
uniform float uShape;
uniform float uMotionMode;
uniform float uSourceBlend;
uniform float uOpacity;
uniform float uOpacityVariation;
uniform vec2 uDrift;
uniform vec2 uSampleOffset;
uniform vec4 uTintColor;
uniform float uTintAmount;
uniform float uHue;
uniform float uHueVariation;
uniform float uSaturation;
uniform float uBrightness;
uniform vec4 uBackground;

const float TAU = 6.28318530718;

float particleHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec2 particleMotion(vec2 cell) {
    vec2 seededCell = cell + vec2(uSeed * 17.17, uSeed * 43.71);
    float phase = TAU * particleHash(seededCell);
    float variation = clamp(uSpeedVariation, 0.0, 1.0);
    float rate = mix(
        1.0 - variation,
        1.0 + variation,
        particleHash(seededCell + 19.31)
    );
    float time = uTime * uSpeed * rate;
    vec2 motion;
    if (uMotionMode < 0.5) {
        motion = vec2(
            cos(time + phase),
            sin(time * 1.137 + phase * 0.73)
        );
    } else if (uMotionMode < 1.5) {
        motion = vec2(
            sin(time * 0.83 + phase * 2.17),
            cos(time * 1.31 + phase * 0.61)
        );
    } else if (uMotionMode < 2.5) {
        motion = vec2(
            sin(time + phase),
            sin(time * 1.7 + cell.x * 0.37 + phase)
        );
    } else if (uMotionMode < 3.5) {
        float angle = phase + time + 0.35 * sin(time * 0.7 + phase);
        motion = vec2(cos(angle), sin(angle));
    } else if (uMotionMode < 4.5) {
        motion = vec2(
            0.55 * sin(time * 0.9 + phase),
            sin(time * 1.4 + phase) - 0.25
        );
    } else if (uMotionMode < 5.5) {
        motion = vec2(
            0.28 * sin(time * 0.6 + phase),
            -sin(time + phase)
        );
    } else if (uMotionMode < 6.5) {
        vec2 radial = normalize(
            vec2(
                particleHash(seededCell + 5.7) - 0.5,
                particleHash(seededCell + 9.1) - 0.5
            ) + vec2(1.0e-4)
        );
        motion = radial * sin(time + phase);
    } else {
        float angle = TAU * particleHash(floor(cell * 0.17) + uSeed);
        motion = vec2(cos(angle), sin(angle))
            * sin(time * 0.73 + phase);
    }
    motion *= uMoveAmount;
    vec2 jitter = vec2(
        sin(time * 3.11 + phase * 2.07),
        cos(time * 2.73 + phase * 1.61)
    ) * uJitter;
    vec2 drift = uDrift * sin(time * 0.43 + phase);
    vec2 turbulent = vec2(
        sin(time * 2.37 + cell.y * 1.71 + phase),
        cos(time * 2.11 + cell.x * 1.53 + phase)
    ) * uTurbulence;
    vec2 scatter = vec2(
        particleHash(seededCell + 71.3) - 0.5,
        particleHash(seededCell + 93.7) - 0.5
    ) * (2.0 * uScatter);
    vec2 displacement = motion + jitter + drift + turbulent + scatter;
    float displacementLength = length(displacement);
    return displacementLength > 1.30
        ? displacement * (1.30 / displacementLength)
        : displacement;
}

mat2 particleRotation(float angle) {
    float sine = sin(angle);
    float cosine = cos(angle);
    return mat2(cosine, -sine, sine, cosine);
}

float particleMetric(vec2 delta, float shape) {
    vec2 absoluteDelta = abs(delta);
    float circle = length(delta);
    float square = max(absoluteDelta.x, absoluteDelta.y);
    float diamond = (absoluteDelta.x + absoluteDelta.y) * 0.70710678118;
    if (shape < 0.5) {
        return circle;
    }
    if (shape < 1.5) {
        return square;
    }
    if (shape < 2.5) {
        return diamond;
    }
    if (shape < 3.5) {
        return max(
            absoluteDelta.x * 0.8660254 + delta.y * 0.5,
            -delta.y
        );
    }
    if (shape < 4.5) {
        return max(
            absoluteDelta.x * 0.8660254 + absoluteDelta.y * 0.5,
            absoluteDelta.y
        );
    }
    if (shape < 5.5) {
        return circle;
    }
    if (shape < 6.5) {
        float angle = atan(delta.y, delta.x);
        float star = mix(0.48, 1.0, 0.5 + 0.5 * cos(angle * 5.0));
        return circle / max(star, 0.2);
    }
    return max(absoluteDelta.x, absoluteDelta.y * 4.0);
}

vec3 particleRgbToHsv(vec3 color) {
    vec4 K = vec4(0.0, -0.3333333333, 0.6666666667, -1.0);
    vec4 p = mix(vec4(color.bg, K.wz), vec4(color.gb, K.xy), step(color.b, color.g));
    vec4 q = mix(vec4(p.xyw, color.r), vec4(color.r, p.yzx), step(p.x, color.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 particleHsvToRgb(vec3 color) {
    vec3 p = abs(fract(color.xxx + vec3(0.0, 0.6666666667, 0.3333333333)) * 6.0 - 3.0);
    return color.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), color.y);
}

void main() {
    vec2 uv = clamp(vUV.st, 0.0, 1.0);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    float aspect = float(max(sourceSize.x, 1)) / float(max(sourceSize.y, 1));
    float columns = max(4.0, floor(uDensity + 0.5));
    float rows = max(4.0, floor(columns / max(aspect, 0.001) + 0.5));
    vec2 grid = vec2(columns, rows);
    vec2 gridPosition = uv * grid;
    vec2 baseCell = floor(gridPosition);

    vec4 sourceHere = texture(sTD2DInputs[0], uv);
    vec4 baseLayer = mix(uBackground, sourceHere, clamp(uSourceBlend, 0.0, 1.0));
    vec3 premultiplied = baseLayer.rgb * baseLayer.a;
    float accumulatedAlpha = baseLayer.a;
    float radius = max(0.035, uSize * 0.46);

    // Motion controls are clamped so a fixed 5x5 neighborhood is sufficient.
    // This keeps work bounded at every density and resolution.
    for (int offsetY = -2; offsetY <= 2; ++offsetY) {
        for (int offsetX = -2; offsetX <= 2; ++offsetX) {
            vec2 cell = baseCell + vec2(float(offsetX), float(offsetY));
            if (
                cell.x < 0.0 || cell.y < 0.0
                || cell.x >= grid.x || cell.y >= grid.y
            ) {
                continue;
            }
            vec2 center = cell + vec2(0.5) + particleMotion(cell);
            vec2 delta = gridPosition - center;
            vec2 seededCell = cell + vec2(uSeed * 17.17, uSeed * 43.71);
            float phase = TAU * particleHash(seededCell);
            float sizeRandom = mix(
                1.0 - clamp(uSizeVariation, 0.0, 0.95),
                1.0 + clamp(uSizeVariation, 0.0, 1.0),
                particleHash(seededCell + 27.31)
            );
            float pulse = 1.0 + uPulseAmount * sin(
                uTime * uPulseRate * TAU + phase
            );
            float localRadius = radius * max(0.05, sizeRandom * pulse);
            float angle = radians(uRotation) + uTime * uSpin * TAU;
            vec2 shapedDelta = particleRotation(-angle) * delta;
            shapedDelta /= max(uAspect, vec2(0.10));
            float metric = particleMetric(shapedDelta, uShape);
            float antialias = max(
                fwidth(metric),
                0.006 + clamp(uSoftness, 0.0, 1.0) * localRadius * 0.32
            );
            float outerCoverage = 1.0 - smoothstep(
                localRadius - antialias,
                localRadius + antialias,
                metric
            );
            float hollow = max(
                clamp(uHollow, 0.0, 0.92),
                uShape >= 5.0 && uShape < 6.0 ? 0.58 : 0.0
            );
            float innerRadius = localRadius * hollow;
            float innerCoverage = 1.0 - smoothstep(
                innerRadius - antialias,
                innerRadius + antialias,
                metric
            );
            float coverage = outerCoverage * (1.0 - innerCoverage * step(0.001, hollow));
            coverage = clamp(coverage, 0.0, 1.0);
            if (coverage <= 0.0) {
                continue;
            }
            vec2 sourceUV = clamp(
                (cell + vec2(0.5)) / grid + uSampleOffset,
                0.0,
                1.0
            );
            vec4 source = texture(sTD2DInputs[0], sourceUV);
            vec3 hsv = particleRgbToHsv(max(source.rgb, vec3(0.0)));
            hsv.x = fract(
                hsv.x + uHue
                + (particleHash(seededCell + 53.19) - 0.5) * uHueVariation
            );
            hsv.y = max(0.0, hsv.y * uSaturation);
            hsv.z = max(0.0, hsv.z + uBrightness);
            source.rgb = particleHsvToRgb(hsv);
            source.rgb = mix(
                source.rgb,
                uTintColor.rgb,
                clamp(uTintAmount * uTintColor.a, 0.0, 1.0)
            );
            float opacityRandom = mix(
                1.0 - clamp(uOpacityVariation, 0.0, 1.0),
                1.0,
                particleHash(seededCell + 81.07)
            );
            float layerAlpha = clamp(
                coverage * source.a * uOpacity * opacityRandom,
                0.0,
                1.0
            );
            premultiplied = source.rgb * layerAlpha
                + premultiplied * (1.0 - layerAlpha);
            accumulatedAlpha = layerAlpha
                + accumulatedAlpha * (1.0 - layerAlpha);
        }
    }

    vec3 color = accumulatedAlpha > 0.00001
        ? premultiplied / accumulatedAlpha
        : vec3(0.0);
    fragColor = TDOutputSwizzle(vec4(color, accumulatedAlpha));
}
""".strip()

PARTICLE_PARAMETER_DEFINITIONS = (
    {
        "name": "Enabled", "label": "Particles Enabled", "type": "toggle",
        "page": "Particles", "default": True,
        "description": "Return the source unchanged when disabled.",
    },
    {
        "name": "Autotime", "label": "Auto Time", "type": "toggle",
        "page": "Animation", "default": True,
        "description": "Animate from TouchDesigner's absolute time.",
    },
    {
        "name": "Timescale", "label": "Time Scale", "type": "float",
        "page": "Animation", "default": 1.0, "min": -10.0, "max": 10.0,
        "description": "Scale or reverse automatic particle time.",
    },
    {
        "name": "Manualtime", "label": "Manual Time", "type": "float",
        "page": "Animation", "default": 0.0, "min": -100000.0, "max": 100000.0,
        "description": "Deterministic time used when Auto Time is disabled.",
    },
    {
        "name": "Time", "label": "Effective Time", "type": "float",
        "page": "Animation", "default": 0.0, "min": -100000.0, "max": 100000.0,
        "uniform": "uTime", "animatable": False, "read_only": True,
        "description": "Resolved animation time sent to the particle shader.",
    },
    {
        "name": "Density", "label": "Particle Columns", "type": "int",
        "page": "Appearance", "default": 96, "min": 8, "max": 500,
        "uniform": "uDensity",
        "description": "Particle columns; rows follow the source aspect ratio.",
    },
    {
        "name": "Size", "label": "Particle Size", "type": "float",
        "page": "Appearance", "default": 0.72, "min": 0.08, "max": 1.25,
        "uniform": "uSize",
        "description": "Particle radius relative to one grid cell.",
    },
    {
        "name": "Sizevariation", "label": "Size Variation", "type": "float",
        "page": "Appearance", "default": 0.0, "min": 0.0, "max": 0.95,
        "uniform": "uSizeVariation",
        "description": "Vary particle size deterministically across the field.",
    },
    {
        "name": "Aspect", "label": "Particle Aspect", "type": "xy",
        "page": "Appearance", "default": [1.0, 1.0], "min": 0.1, "max": 4.0,
        "uniform": "uAspect",
        "description": "Stretch particle silhouettes independently on X and Y.",
    },
    {
        "name": "Rotation", "label": "Rotation (Degrees)", "type": "float",
        "page": "Appearance", "default": 0.0, "min": -180.0, "max": 180.0,
        "uniform": "uRotation",
        "description": "Rotate non-circular particle silhouettes.",
    },
    {
        "name": "Spin", "label": "Spin (Turns/Second)", "type": "float",
        "page": "Appearance", "default": 0.0, "min": -4.0, "max": 4.0,
        "uniform": "uSpin",
        "description": "Continuously rotate non-circular particles.",
    },
    {
        "name": "Softness", "label": "Edge Softness", "type": "float",
        "page": "Appearance", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uSoftness",
        "description": "Soften particle edges beyond normal antialiasing.",
    },
    {
        "name": "Hollow", "label": "Hollow Amount", "type": "float",
        "page": "Appearance", "default": 0.0, "min": 0.0, "max": 0.92,
        "uniform": "uHollow",
        "description": "Cut out particle centers to form outlined silhouettes.",
    },
    {
        "name": "Speed", "label": "Move Speed", "type": "float",
        "page": "Motion", "default": 0.8, "min": 0.0, "max": 8.0,
        "uniform": "uSpeed",
        "description": "Speed of the deterministic random motion.",
    },
    {
        "name": "Speedvariation", "label": "Speed Variation", "type": "float",
        "page": "Motion", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uSpeedVariation",
        "description": "Give each particle a deterministic speed variation.",
    },
    {
        "name": "Moveamount", "label": "Move Amount", "type": "float",
        "page": "Motion", "default": 0.55, "min": 0.0, "max": 1.2,
        "uniform": "uMoveAmount",
        "description": "Random orbit distance in particle-cell units.",
    },
    {
        "name": "Jitter", "label": "Jitter", "type": "float",
        "page": "Motion", "default": 0.12, "min": 0.0, "max": 0.6,
        "uniform": "uJitter",
        "description": "Adds faster secondary random movement.",
    },
    {
        "name": "Drift", "label": "Directional Drift", "type": "xy",
        "page": "Motion", "default": [0.08, 0.03], "min": -1.0, "max": 1.0,
        "uniform": "uDrift",
        "description": "Adds bounded directional motion in cell units.",
    },
    {
        "name": "Turbulence", "label": "Turbulence", "type": "float",
        "page": "Motion", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uTurbulence",
        "description": "Add a faster spatially varying current.",
    },
    {
        "name": "Scatter", "label": "Static Scatter", "type": "float",
        "page": "Motion", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uScatter",
        "description": "Offset particles from their regular grid positions.",
    },
    {
        "name": "Pulseamount", "label": "Size Pulse Amount", "type": "float",
        "page": "Motion", "default": 0.0, "min": 0.0, "max": 0.9,
        "uniform": "uPulseAmount",
        "description": "Animate particle size with per-particle phase offsets.",
    },
    {
        "name": "Pulserate", "label": "Size Pulse Rate", "type": "float",
        "page": "Motion", "default": 1.0, "min": 0.0, "max": 8.0,
        "uniform": "uPulseRate",
        "description": "Set the speed of size pulsing when pulse amount is active.",
    },
    {
        "name": "Seed", "label": "Random Seed", "type": "int",
        "page": "Motion", "default": 1, "min": 0, "max": 100000,
        "uniform": "uSeed",
        "description": "Changes the deterministic motion pattern.",
    },
    {
        "name": "Shape", "label": "Particle Shape", "type": "menu",
        "page": "Appearance", "default": "circle",
        "menu_names": ["circle", "square", "diamond", "triangle", "hexagon", "ring", "star", "line"],
        "menu_labels": ["Circle", "Square", "Diamond", "Triangle", "Hexagon", "Ring", "Star", "Line"],
        "uniform": "uShape",
        "description": "Choose the particle silhouette.",
    },
    {
        "name": "Motionmode", "label": "Motion Style", "type": "menu",
        "page": "Motion", "default": "orbit",
        "menu_names": ["orbit", "wander", "wave", "swirl", "fountain", "rain", "explosion", "flow"],
        "menu_labels": ["Orbit", "Wander", "Wave", "Swirl", "Fountain", "Rain", "Explosion", "Flow Field"],
        "uniform": "uMotionMode",
        "description": "Choose one of eight bounded procedural movement fields.",
    },
    {
        "name": "Sourceblend", "label": "Source Blend", "type": "float",
        "page": "Compositing", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uSourceBlend",
        "description": "Blend the original source behind the particles.",
    },
    {
        "name": "Opacity", "label": "Particle Opacity", "type": "float",
        "page": "Compositing", "default": 1.0, "min": 0.0, "max": 1.0,
        "uniform": "uOpacity",
        "description": "Multiply particle alpha.",
    },
    {
        "name": "Opacityvariation", "label": "Opacity Variation", "type": "float",
        "page": "Compositing", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uOpacityVariation",
        "description": "Vary opacity deterministically across particles.",
    },
    {
        "name": "Sampleoffset", "label": "Source Sample Offset", "type": "xy",
        "page": "Particle Color", "default": [0.0, 0.0], "min": -1.0, "max": 1.0,
        "uniform": "uSampleOffset",
        "description": "Offset where each particle samples its source color.",
    },
    {
        "name": "Tintcolor", "label": "Particle Tint", "type": "rgba",
        "page": "Particle Color", "default": [1.0, 1.0, 1.0, 1.0],
        "uniform": "uTintColor",
        "description": "Choose a tint color; alpha scales the tint amount.",
    },
    {
        "name": "Tintamount", "label": "Tint Amount", "type": "float",
        "page": "Particle Color", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uTintAmount",
        "description": "Blend sampled particle colors toward the selected tint.",
    },
    {
        "name": "Hue", "label": "Hue Rotation", "type": "float",
        "page": "Particle Color", "default": 0.0, "min": -1.0, "max": 1.0,
        "uniform": "uHue",
        "description": "Rotate every particle hue by normalized turns.",
    },
    {
        "name": "Huevariation", "label": "Hue Variation", "type": "float",
        "page": "Particle Color", "default": 0.0, "min": 0.0, "max": 1.0,
        "uniform": "uHueVariation",
        "description": "Add deterministic per-particle hue variation.",
    },
    {
        "name": "Saturation", "label": "Particle Saturation", "type": "float",
        "page": "Particle Color", "default": 1.0, "min": 0.0, "max": 3.0,
        "uniform": "uSaturation",
        "description": "Scale the saturation of sampled particle colors.",
    },
    {
        "name": "Brightness", "label": "Particle Brightness", "type": "float",
        "page": "Particle Color", "default": 0.0, "min": -1.0, "max": 1.0,
        "uniform": "uBrightness",
        "description": "Add or subtract sampled particle value.",
    },
    {
        "name": "Background", "label": "Background", "type": "rgba",
        "page": "Compositing", "default": [0.0, 0.0, 0.0, 0.0],
        "uniform": "uBackground",
        "description": "Color and alpha behind the particle field.",
    },
)

INK_FLOW_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uVisualEnabled;
uniform float uStyle;
uniform float uVisualMix;
uniform float uInkStrength;
uniform float uEdgeDetail;
uniform float uWashSpread;
uniform float uGranulation;
uniform float uPaperTexture;
uniform vec4 uInkColor;
uniform vec4 uPaperColor;
uniform float uParticlesEnabled;
uniform float uParticleDensity;
uniform float uParticleSize;
uniform float uFlowSpeed;
uniform vec2 uFlowDirection;
uniform float uFlowStrength;
uniform float uTurbulence;
uniform float uRandomness;
uniform float uParticleStretch;
uniform float uParticleShape;
uniform float uParticleOpacity;
uniform float uParticleInkMix;
uniform float uSeed;

const float TAU = 6.28318530718;

float inkHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float inkNoise(vec2 position) {
    vec2 cell = floor(position);
    vec2 local = fract(position);
    local = local * local * (3.0 - 2.0 * local);
    float a = inkHash(cell);
    float b = inkHash(cell + vec2(1.0, 0.0));
    float c = inkHash(cell + vec2(0.0, 1.0));
    float d = inkHash(cell + vec2(1.0, 1.0));
    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

float inkFbm(vec2 position) {
    float value = 0.0;
    float amplitude = 0.55;
    for (int octave = 0; octave < 4; ++octave) {
        value += amplitude * inkNoise(position);
        position = position * 2.03 + vec2(13.17, 7.91);
        amplitude *= 0.48;
    }
    return value;
}

float sourceLuma(vec2 uv) {
    vec3 color = texture(sTD2DInputs[0], clamp(uv, 0.0, 1.0)).rgb;
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
}

vec3 paperSurface(vec2 uv) {
    float fiber = inkFbm(
        uv * vec2(410.0, 245.0) + vec2(uSeed * 0.37, uSeed * 0.19)
    );
    float verticalFiber = inkNoise(
        vec2(uv.x * 57.0 + uSeed, uv.y * 780.0)
    );
    float textureAmount = (fiber - 0.48) * 0.10
        + (verticalFiber - 0.5) * 0.025;
    vec3 paperColor = mix(vec3(1.0), uPaperColor.rgb, clamp(uPaperColor.a, 0.0, 1.0));
    return clamp(
        paperColor * (1.0 + textureAmount * uPaperTexture),
        0.0,
        1.0
    );
}

vec3 minimalInkWork(vec2 uv, vec2 texel, vec4 source) {
    float left = sourceLuma(uv - vec2(texel.x, 0.0));
    float right = sourceLuma(uv + vec2(texel.x, 0.0));
    float down = sourceLuma(uv - vec2(0.0, texel.y));
    float up = sourceLuma(uv + vec2(0.0, texel.y));
    float gradient = length(vec2(right - left, up - down));
    float line = smoothstep(
        mix(0.18, 0.035, clamp(uEdgeDetail * 0.25, 0.0, 1.0)),
        mix(0.32, 0.11, clamp(uEdgeDetail * 0.25, 0.0, 1.0)),
        gradient
    );
    float luma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float restrainedTone = (
        1.0 - smoothstep(0.08, 0.58, luma)
    ) * 0.58;
    float dryBrush = mix(
        0.82,
        1.16,
        inkFbm(uv * 170.0 + vec2(uSeed * 1.7, 0.0))
    );
    float pigment = clamp(
        (line + restrainedTone) * uInkStrength * dryBrush,
        0.0,
        1.0
    );
    return mix(
        paperSurface(uv),
        uInkColor.rgb,
        pigment * clamp(uInkColor.a, 0.0, 1.0)
    );
}

vec3 minimalInkWash(vec2 uv, vec2 texel, vec4 source) {
    vec2 spread = texel * max(uWashSpread, 0.25);
    vec3 wash = source.rgb * 0.28;
    wash += texture(sTD2DInputs[0], clamp(uv + vec2(spread.x, 0.0), 0.0, 1.0)).rgb * 0.12;
    wash += texture(sTD2DInputs[0], clamp(uv - vec2(spread.x, 0.0), 0.0, 1.0)).rgb * 0.12;
    wash += texture(sTD2DInputs[0], clamp(uv + vec2(0.0, spread.y), 0.0, 1.0)).rgb * 0.12;
    wash += texture(sTD2DInputs[0], clamp(uv - vec2(0.0, spread.y), 0.0, 1.0)).rgb * 0.12;
    wash += texture(sTD2DInputs[0], clamp(uv + spread, 0.0, 1.0)).rgb * 0.06;
    wash += texture(sTD2DInputs[0], clamp(uv - spread, 0.0, 1.0)).rgb * 0.06;
    wash += texture(sTD2DInputs[0], clamp(uv + vec2(spread.x, -spread.y), 0.0, 1.0)).rgb * 0.06;
    wash += texture(sTD2DInputs[0], clamp(uv + vec2(-spread.x, spread.y), 0.0, 1.0)).rgb * 0.06;

    float washLuma = dot(wash, vec3(0.2126, 0.7152, 0.0722));
    float sourceValue = 1.0 - dot(
        source.rgb,
        vec3(0.2126, 0.7152, 0.0722)
    );
    float pooledEdge = abs(sourceLuma(uv + spread) - sourceLuma(uv - spread));
    float diffusion = inkFbm(
        uv * 92.0 + vec2(uSeed * 2.11, uTime * 0.035)
    );
    float granules = mix(
        1.0,
        mix(0.68, 1.28, diffusion),
        clamp(uGranulation, 0.0, 1.0)
    );
    float layeredWash = pow(clamp(1.0 - washLuma, 0.0, 1.0), 1.18);
    layeredWash = smoothstep(0.035, 0.965, layeredWash);
    layeredWash *= mix(0.88, 1.10, diffusion);
    float pigment = clamp(
        (
            layeredWash * 0.72
            + sourceValue * 0.22
            + pooledEdge * uEdgeDetail * 0.32
        ) * uInkStrength * granules,
        0.0,
        1.0
    );
    return mix(
        paperSurface(uv),
        uInkColor.rgb,
        pigment * clamp(uInkColor.a, 0.0, 1.0)
    );
}

vec3 visualLayer(vec2 uv, vec2 texel, vec4 source) {
    if (uVisualEnabled <= 0.5) {
        return source.rgb;
    }
    vec3 stylized = uStyle < 0.5
        ? minimalInkWork(uv, texel, source)
        : minimalInkWash(uv, texel, source);
    return mix(source.rgb, stylized, clamp(uVisualMix, 0.0, 1.0));
}

vec2 flowBasisDirection() {
    float magnitude = length(uFlowDirection);
    return magnitude > 0.0001
        ? uFlowDirection / magnitude
        : vec2(1.0, 0.0);
}

vec2 waterParticleMotion(vec2 cell, vec2 direction) {
    vec2 seeded = cell + vec2(uSeed * 17.17, uSeed * 43.71);
    float phase = inkHash(seeded);
    float rate = mix(0.64, 1.38, inkHash(seeded + 19.31));
    float travel = fract(uTime * uFlowSpeed * rate + phase) * 2.0 - 1.0;
    float randomPhase = TAU * inkHash(seeded + 7.13);
    vec2 normal = vec2(-direction.y, direction.x);
    float crossCurrent = sin(
        uTime * uFlowSpeed * 1.73 + randomPhase
    ) * uTurbulence;
    float wandering = (
        sin(uTime * uFlowSpeed * 2.91 + randomPhase * 1.37)
        + cos(uTime * uFlowSpeed * 1.19 + randomPhase * 0.73)
    ) * 0.5 * uRandomness;
    return direction * (travel * uFlowStrength + wandering * 0.35)
        + normal * (crossCurrent + wandering);
}

float waterParticleMetric(
    vec2 delta,
    vec2 direction,
    float radius,
    float variation
) {
    vec2 normal = vec2(-direction.y, direction.x);
    float along = dot(delta, direction);
    float across = dot(delta, normal);
    float stretch = 1.0 + uParticleStretch * mix(0.85, 1.35, variation);
    vec2 shaped = vec2(
        along / max(radius * stretch, 0.001),
        across / max(radius, 0.001)
    );
    float roundDrop = length(shaped);
    float brushFleck = max(abs(shaped.x), abs(shaped.y))
        + 0.10 * sin(shaped.x * 8.0 + variation * TAU);
    float taperedDrop = length(shaped)
        + max(0.0, shaped.x) * 0.16
        - max(0.0, -shaped.x) * 0.08;
    if (uParticleShape < 0.5) {
        return roundDrop;
    }
    if (uParticleShape < 1.5) {
        return brushFleck;
    }
    return taperedDrop;
}

void main() {
    vec2 uv = clamp(vUV.st, 0.0, 1.0);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    vec2 texel = 1.0 / vec2(max(sourceSize.x, 1), max(sourceSize.y, 1));
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 baseColor = visualLayer(uv, texel, source);
    vec3 premultiplied = baseColor * source.a;
    float accumulatedAlpha = source.a;

    if (uParticlesEnabled > 0.5 && uParticleOpacity > 0.0) {
        float aspect = float(max(sourceSize.x, 1))
            / float(max(sourceSize.y, 1));
        float columns = max(4.0, floor(uParticleDensity + 0.5));
        float rows = max(
            4.0,
            floor(columns / max(aspect, 0.001) + 0.5)
        );
        vec2 grid = vec2(columns, rows);
        vec2 gridPosition = uv * grid;
        vec2 baseCell = floor(gridPosition);
        vec2 direction = flowBasisDirection();
        float radius = max(0.04, uParticleSize * 0.46);

        // Motion and stretch are bounded so this fixed 5x5 search remains
        // sufficient at every density and output resolution.
        for (int offsetY = -2; offsetY <= 2; ++offsetY) {
            for (int offsetX = -2; offsetX <= 2; ++offsetX) {
                vec2 cell = baseCell + vec2(float(offsetX), float(offsetY));
                if (
                    cell.x < 0.0 || cell.y < 0.0
                    || cell.x >= grid.x || cell.y >= grid.y
                ) {
                    continue;
                }
                float variation = inkHash(
                    cell + vec2(uSeed * 5.73, uSeed * 11.19)
                );
                vec2 center = cell + vec2(0.5)
                    + waterParticleMotion(cell, direction);
                vec2 delta = gridPosition - center;
                float metric = waterParticleMetric(
                    delta,
                    direction,
                    radius,
                    variation
                );
                float antialias = max(fwidth(metric), 0.008);
                float raggedEdge = mix(
                    0.96,
                    1.06,
                    inkNoise(cell * 5.0 + delta * 2.5 + uSeed)
                );
                float coverage = 1.0 - smoothstep(
                    raggedEdge - antialias,
                    raggedEdge + antialias,
                    metric
                );
                if (coverage <= 0.0) {
                    continue;
                }

                vec2 sourceUV = (cell + vec2(0.5)) / grid;
                vec4 particleSource = texture(
                    sTD2DInputs[0],
                    clamp(sourceUV, 0.0, 1.0)
                );
                float particleLuma = dot(
                    particleSource.rgb,
                    vec3(0.2126, 0.7152, 0.0722)
                );
                float pigmentBias = mix(0.42, 1.0, 1.0 - particleLuma);
                vec3 particleColor = mix(
                    particleSource.rgb,
                    uInkColor.rgb,
                    clamp(
                        uParticleInkMix * pigmentBias * uInkColor.a,
                        0.0,
                        1.0
                    )
                );
                float layerAlpha = clamp(
                    coverage
                    * particleSource.a
                    * uParticleOpacity
                    * mix(0.72, 1.0, variation),
                    0.0,
                    1.0
                );
                premultiplied = particleColor * layerAlpha
                    + premultiplied * (1.0 - layerAlpha);
                accumulatedAlpha = layerAlpha
                    + accumulatedAlpha * (1.0 - layerAlpha);
            }
        }
    }

    vec3 color = accumulatedAlpha > 0.00001
        ? premultiplied / accumulatedAlpha
        : vec3(0.0);
    fragColor = TDOutputSwizzle(vec4(color, accumulatedAlpha));
}
""".strip()

INK_FLOW_PARAMETER_DEFINITIONS = (
    {
        "name": "Enabled", "label": "Module Enabled", "type": "toggle",
        "page": "Ink Flow", "default": True,
        "description": "Return the input unchanged when the entire module is disabled.",
    },
    {
        "name": "Autotime", "label": "Auto Time", "type": "toggle",
        "page": "Ink Flow", "default": True,
        "description": "Animate water particles from TouchDesigner's absolute time.",
    },
    {
        "name": "Timescale", "label": "Time Scale", "type": "float",
        "page": "Ink Flow", "default": 1.0, "min": -10.0, "max": 10.0,
        "description": "Scale or reverse automatic water-flow time.",
    },
    {
        "name": "Manualtime", "label": "Manual Time", "type": "float",
        "page": "Ink Flow", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "description": "Deterministic time used when Auto Time is disabled.",
    },
    {
        "name": "Time", "label": "Effective Time", "type": "float",
        "page": "Ink Flow", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "uniform": "uTime", "animatable": False, "read_only": True,
        "description": "Resolved animation time sent to the ink-flow shader.",
    },
    {
        "name": "Visualenabled", "label": "Ink Visual Enabled",
        "type": "toggle", "page": "Ink Visuals", "default": True,
        "uniform": "uVisualEnabled",
        "description": "Apply the selected ink treatment independently of particles.",
    },
    {
        "name": "Style", "label": "Ink Style", "type": "menu",
        "page": "Ink Visuals", "default": "ink_work",
        "menu_names": ["ink_work", "ink_wash"],
        "menu_labels": [
            "Minimal Ink Work (Line and Brush)",
            "Minimal Ink Wash (Shui-mo)",
        ],
        "uniform": "uStyle",
        "description": "Choose crisp restrained ink work or soft layered ink wash.",
    },
    {
        "name": "Visualmix", "label": "Ink Visual Mix", "type": "float",
        "page": "Ink Visuals", "default": 1.0,
        "min": 0.0, "max": 1.0, "uniform": "uVisualMix",
        "description": "Blend the selected ink treatment with the source.",
    },
    {
        "name": "Inkstrength", "label": "Ink Strength", "type": "float",
        "page": "Ink Visuals", "default": 0.92,
        "min": 0.0, "max": 2.0, "uniform": "uInkStrength",
        "description": "Control pigment depth and tonal weight.",
    },
    {
        "name": "Edgedetail", "label": "Edge Detail", "type": "float",
        "page": "Ink Visuals", "default": 1.6,
        "min": 0.0, "max": 4.0, "uniform": "uEdgeDetail",
        "description": "Control line sensitivity and pooled wash edges.",
    },
    {
        "name": "Washspread", "label": "Wash Spread", "type": "float",
        "page": "Ink Visuals", "default": 3.2,
        "min": 0.25, "max": 10.0, "uniform": "uWashSpread",
        "description": "Set the diffusion radius used by the ink-wash style.",
    },
    {
        "name": "Granulation", "label": "Wash Granulation", "type": "float",
        "page": "Ink Visuals", "default": 0.42,
        "min": 0.0, "max": 1.0, "uniform": "uGranulation",
        "description": "Add controlled pigment granulation to ink wash.",
    },
    {
        "name": "Papertexture", "label": "Paper Texture", "type": "float",
        "page": "Ink Visuals", "default": 0.55,
        "min": 0.0, "max": 1.0, "uniform": "uPaperTexture",
        "description": "Reveal a subtle rice-paper-like procedural fiber texture.",
    },
    {
        "name": "Inkcolor", "label": "Ink Color", "type": "rgba",
        "page": "Ink Palette", "default": [0.035, 0.032, 0.028, 1.0],
        "uniform": "uInkColor",
        "description": "Set the pigment color used by both styles and particles.",
    },
    {
        "name": "Papercolor", "label": "Paper Color", "type": "rgba",
        "page": "Ink Palette", "default": [0.94, 0.915, 0.84, 1.0],
        "uniform": "uPaperColor",
        "description": "Set the warm paper ground used by both ink styles.",
    },
    {
        "name": "Particlesenabled", "label": "Water Particles Enabled",
        "type": "toggle", "page": "Water Particles", "default": True,
        "uniform": "uParticlesEnabled",
        "description": "Composite the water-current particle layer independently.",
    },
    {
        "name": "Particledensity", "label": "Particle Columns",
        "type": "int", "page": "Water Particles", "default": 32,
        "min": 8, "max": 500, "uniform": "uParticleDensity",
        "description": "Particle columns; rows follow the source aspect ratio.",
    },
    {
        "name": "Particlesize", "label": "Particle Size",
        "type": "float", "page": "Water Particles", "default": 0.46,
        "min": 0.08, "max": 0.90, "uniform": "uParticleSize",
        "description": "Particle radius relative to one grid cell.",
    },
    {
        "name": "Flowspeed", "label": "Flow Speed",
        "type": "float", "page": "Water Particles", "default": 0.34,
        "min": 0.0, "max": 4.0, "uniform": "uFlowSpeed",
        "description": "Speed of particle travel through the water current.",
    },
    {
        "name": "Flowdirection", "label": "Flow Direction",
        "type": "xy", "page": "Water Particles",
        "default": [1.0, -0.12], "min": -1.0, "max": 1.0,
        "uniform": "uFlowDirection",
        "description": "Set the principal two-dimensional water-flow direction.",
    },
    {
        "name": "Flowstrength", "label": "Flow Distance",
        "type": "float", "page": "Water Particles", "default": 0.48,
        "min": 0.0, "max": 0.65, "uniform": "uFlowStrength",
        "description": "Set bounded downstream travel in grid-cell units.",
    },
    {
        "name": "Turbulence", "label": "Cross-current Turbulence",
        "type": "float", "page": "Water Particles", "default": 0.11,
        "min": 0.0, "max": 0.25, "uniform": "uTurbulence",
        "description": "Add smooth movement across the main current.",
    },
    {
        "name": "Randomness", "label": "Random Wandering",
        "type": "float", "page": "Water Particles", "default": 0.06,
        "min": 0.0, "max": 0.15, "uniform": "uRandomness",
        "description": "Add deterministic seeded irregular motion.",
    },
    {
        "name": "Particlestretch", "label": "Flow Stretch",
        "type": "float", "page": "Water Particles", "default": 0.62,
        "min": 0.0, "max": 1.0, "uniform": "uParticleStretch",
        "description": "Stretch particles along the water-flow direction.",
    },
    {
        "name": "Particleshape", "label": "Particle Shape", "type": "menu",
        "page": "Water Particles", "default": "brush",
        "menu_names": ["round", "brush", "droplet"],
        "menu_labels": ["Round Pigment", "Brush Fleck", "Water Droplet"],
        "uniform": "uParticleShape",
        "description": "Choose the silhouette of the flowing particle marks.",
    },
    {
        "name": "Particleopacity", "label": "Particle Opacity",
        "type": "float", "page": "Water Particles", "default": 0.58,
        "min": 0.0, "max": 1.0, "uniform": "uParticleOpacity",
        "description": "Control the opacity of the water-current particle layer.",
    },
    {
        "name": "Particleinkmix", "label": "Particle Ink Mix",
        "type": "float", "page": "Water Particles", "default": 0.86,
        "min": 0.0, "max": 1.0, "uniform": "uParticleInkMix",
        "description": "Blend source color toward the selected ink pigment.",
    },
    {
        "name": "Seed", "label": "Random Seed", "type": "int",
        "page": "Water Particles", "default": 23,
        "min": 0, "max": 100000, "uniform": "uSeed",
        "description": "Change paper fibers and deterministic particle wandering.",
    },
)

GLITCH_FUSION_STYLE_NAMES = (
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

GLITCH_FUSION_STYLE_LABELS = (
    "RGB Split",
    "Block Shift",
    "Slice Tear",
    "Digital Noise",
    "Pixel Sort Streak",
    "Datamosh Smear",
    "VHS Tracking",
    "Scanline Jitter",
    "Macroblock Compression",
    "Signal Dropout",
    "Frame Jitter",
    "Rolling Sync",
    "Channel Swap",
    "Color Quantize",
    "Bit Crush",
    "Mosaic Scramble",
    "Wave Interference",
    "Static Snow",
    "CRT Corruption",
    "Horizontal Hold",
    "Vertical Hold",
    "Data Bend",
    "Edge Corrupt",
    "Glitch Fusion",
)

GLITCH_FUSION_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uStyle;
uniform float uMix;
uniform float uIntensity;
uniform float uSpeed;
uniform float uSeed;
uniform float uBlockSize;
uniform float uSliceDensity;
uniform float uDisplacement;
uniform float uJitter;
uniform float uSmear;
uniform float uRgbSplit;
uniform float uNoiseAmount;
uniform float uDropout;
uniform float uScanlines;
uniform float uTracking;
uniform float uCompression;
uniform float uColorShift;
uniform float uQuantize;
uniform float uEdgeAmount;

const float TAU = 6.28318530718;

float glitchHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec2 glitchHash2(vec2 value) {
    return vec2(
        glitchHash(value + vec2(17.17, 43.71)),
        glitchHash(value + vec2(91.37, 11.53))
    );
}

float glitchNoise(vec2 position) {
    vec2 cell = floor(position);
    vec2 local = fract(position);
    local = local * local * (3.0 - 2.0 * local);
    float a = glitchHash(cell);
    float b = glitchHash(cell + vec2(1.0, 0.0));
    float c = glitchHash(cell + vec2(0.0, 1.0));
    float d = glitchHash(cell + vec2(1.0, 1.0));
    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

vec2 wrapUV(vec2 uv) {
    return fract(uv + 1.0);
}

vec4 sourceAt(vec2 uv) {
    return texture(sTD2DInputs[0], wrapUV(uv));
}

float sourceLumaGlitch(vec2 uv) {
    return dot(sourceAt(uv).rgb, vec3(0.2126, 0.7152, 0.0722));
}

vec3 rgbSplitColor(vec2 uv, vec2 shift) {
    return vec3(
        sourceAt(uv + shift).r,
        sourceAt(uv).g,
        sourceAt(uv - shift).b
    );
}

vec3 smearColor(vec2 uv, vec2 direction, float distance) {
    vec3 color = sourceAt(uv).rgb * 0.34;
    color += sourceAt(uv - direction * distance * 0.25).rgb * 0.24;
    color += sourceAt(uv - direction * distance * 0.50).rgb * 0.18;
    color += sourceAt(uv - direction * distance * 0.75).rgb * 0.14;
    color += sourceAt(uv - direction * distance).rgb * 0.10;
    return color;
}

vec3 quantizeColor(vec3 color, float levels) {
    float safeLevels = max(2.0, floor(levels + 0.5));
    return floor(color * safeLevels + 0.5) / safeLevels;
}

vec3 glitchStyleColor(
    float style,
    vec2 uv,
    vec2 texel,
    vec2 resolution
) {
    float intensity = clamp(uIntensity, 0.0, 1.0);
    float animatedFrame = floor(
        uTime * max(uSpeed, 0.001) * 12.0 + uSeed * 13.0
    );
    float blockPixels = max(2.0, floor(uBlockSize + 0.5));
    vec2 blockGrid = max(vec2(1.0), resolution / blockPixels);
    vec2 blockId = floor(uv * blockGrid);
    vec2 blockLocal = fract(uv * blockGrid);
    float slices = max(2.0, floor(uSliceDensity + 0.5));
    float sliceId = floor(uv.y * slices);
    float lineId = floor(uv.y * max(resolution.y, 1.0));
    float displacement = uDisplacement * intensity;
    float split = uRgbSplit * intensity;
    vec2 sampleUV = uv;
    vec3 color = sourceAt(uv).rgb;

    if (style < 0.5) {
        // RGB Split
        float wobble = mix(
            0.65,
            1.35,
            glitchNoise(vec2(uv.y * slices, animatedFrame))
        );
        color = rgbSplitColor(
            uv,
            vec2(split * wobble, split * 0.18 * sin(uv.y * TAU))
        );
    } else if (style < 1.5) {
        // Block Shift
        float gate = step(
            1.0 - intensity * 0.72,
            glitchHash(blockId + animatedFrame)
        );
        vec2 randomOffset = glitchHash2(blockId + animatedFrame) - 0.5;
        sampleUV += gate * vec2(
            randomOffset.x * displacement,
            randomOffset.y * displacement * 0.30
        );
        color = sourceAt(sampleUV).rgb;
    } else if (style < 2.5) {
        // Slice Tear
        float sliceNoise = glitchHash(vec2(sliceId, animatedFrame));
        float gate = step(1.0 - intensity * 0.82, sliceNoise);
        float tear = (sliceNoise - 0.5) * displacement * 2.0;
        sampleUV.x += gate * tear;
        color = rgbSplitColor(
            sampleUV,
            vec2(split * gate, 0.0)
        );
    } else if (style < 3.5) {
        // Digital Noise
        float fineNoise = glitchHash(
            floor(uv * resolution) + animatedFrame
        );
        float coarseNoise = glitchHash(blockId + animatedFrame * 0.37);
        vec3 noiseColor = vec3(
            fineNoise,
            glitchHash(vec2(fineNoise, coarseNoise) + 7.3),
            coarseNoise
        );
        float mask = uNoiseAmount * intensity
            * mix(0.28, 1.0, step(0.72, coarseNoise));
        color = mix(color, noiseColor, clamp(mask, 0.0, 1.0));
    } else if (style < 4.5) {
        // Pixel Sort Streak
        float luminance = sourceLumaGlitch(uv);
        float threshold = mix(0.72, 0.20, intensity);
        float rowSeed = glitchHash(vec2(sliceId, animatedFrame));
        float streakMask = smoothstep(threshold, threshold + 0.16, luminance);
        float streak = streakMask
            * (0.15 + rowSeed * 0.85)
            * max(uSmear, displacement);
        sampleUV.x -= streak;
        color = smearColor(
            sampleUV,
            vec2(1.0, 0.0),
            streak * 0.65
        );
    } else if (style < 5.5) {
        // Datamosh Smear
        vec2 motion = normalize(vec2(
            1.0,
            sin(uv.y * TAU * 2.0 + animatedFrame) * 0.28
        ));
        float blockMotion = (
            glitchHash(blockId + animatedFrame) - 0.5
        ) * 2.0;
        color = smearColor(
            uv,
            motion,
            max(0.001, uSmear * intensity * (0.35 + abs(blockMotion)))
        );
        color = mix(
            color,
            color.gbr,
            uCompression * intensity * 0.24
        );
    } else if (style < 6.5) {
        // VHS Tracking
        float trackingBand = sin(
            uv.y * resolution.y * 0.035
            + uTime * uSpeed * 8.0
        );
        float headSwitch = smoothstep(
            0.76,
            1.0,
            fract(uv.y + uTime * uSpeed * 0.13)
        );
        sampleUV.x += trackingBand * uTracking * intensity
            + headSwitch * displacement;
        color = rgbSplitColor(
            sampleUV,
            vec2(split * 0.72, 0.0)
        );
        color *= 1.0 - uScanlines
            * (0.06 + 0.05 * sin(uv.y * resolution.y * 3.14159));
    } else if (style < 7.5) {
        // Scanline Jitter
        float lineNoise = glitchHash(vec2(lineId, animatedFrame));
        float gate = step(1.0 - intensity * 0.78, lineNoise);
        sampleUV.x += (lineNoise - 0.5)
            * uJitter * gate;
        color = sourceAt(sampleUV).rgb;
        float scan = 0.5 + 0.5 * sin(uv.y * resolution.y * 3.14159);
        color *= 1.0 - scan * uScanlines * intensity * 0.28;
    } else if (style < 8.5) {
        // Macroblock Compression
        vec2 macroUV = (blockId + vec2(0.5)) / blockGrid;
        float detailMix = clamp(
            uCompression * intensity * 1.25,
            0.0,
            1.0
        );
        color = mix(color, sourceAt(macroUV).rgb, detailMix);
        color = quantizeColor(
            color,
            mix(max(uQuantize, 2.0), 4.0, detailMix)
        );
        float chromaBleed = (blockLocal.x - 0.5) * split;
        color.rb = mix(
            color.rb,
            sourceAt(macroUV + vec2(chromaBleed, 0.0)).br,
            detailMix * 0.34
        );
    } else if (style < 9.5) {
        // Signal Dropout
        float bandNoise = glitchHash(vec2(sliceId, animatedFrame));
        float dropoutGate = step(
            1.0 - max(uDropout, 0.02) * intensity,
            bandNoise
        );
        float snow = glitchHash(
            floor(uv * resolution) + animatedFrame
        );
        vec3 dropoutColor = mix(
            vec3(0.0),
            vec3(snow),
            uNoiseAmount
        );
        color = mix(color, dropoutColor, dropoutGate);
    } else if (style < 10.5) {
        // Frame Jitter
        vec2 frameOffset = (
            glitchHash2(vec2(animatedFrame, uSeed)) - 0.5
        ) * vec2(uJitter, uJitter * 0.45) * intensity;
        color = rgbSplitColor(
            uv + frameOffset,
            vec2(split * 0.45, 0.0)
        );
    } else if (style < 11.5) {
        // Rolling Sync
        float roll = uTime * uSpeed * 0.18
            + glitchHash(vec2(animatedFrame, uSeed)) * uJitter;
        sampleUV.y = fract(sampleUV.y + roll * intensity);
        sampleUV.x += sin(sampleUV.y * TAU * 2.0)
            * uTracking * intensity;
        color = sourceAt(sampleUV).rgb;
    } else if (style < 12.5) {
        // Channel Swap
        vec3 splitColor = rgbSplitColor(
            uv,
            vec2(split, split * 0.25)
        );
        float swapState = mod(floor(animatedFrame / 2.0), 3.0);
        color = swapState < 0.5
            ? splitColor.gbr
            : (swapState < 1.5 ? splitColor.brg : splitColor.rbg);
        color = mix(sourceAt(uv).rgb, color, intensity);
    } else if (style < 13.5) {
        // Color Quantize
        color = quantizeColor(color, uQuantize);
        color = mix(
            color,
            color.brg,
            uColorShift * intensity * 0.45
        );
    } else if (style < 14.5) {
        // Bit Crush
        float levels = mix(64.0, 2.0, intensity);
        color = quantizeColor(color, levels);
        float sampleStride = mix(1.0, blockPixels, intensity);
        vec2 crushedUV = (
            floor(uv * resolution / sampleStride) + 0.5
        ) * sampleStride / resolution;
        color = mix(color, sourceAt(crushedUV).rgb, intensity * 0.62);
    } else if (style < 15.5) {
        // Mosaic Scramble
        vec2 randomCell = floor(
            (glitchHash2(blockId + animatedFrame) - 0.5)
            * mix(1.0, 5.0, intensity)
        );
        vec2 scrambled = (
            blockId + randomCell + blockLocal
        ) / blockGrid;
        color = sourceAt(scrambled).rgb;
    } else if (style < 16.5) {
        // Wave Interference
        vec2 wave = vec2(
            sin(uv.y * TAU * slices + uTime * uSpeed * 5.0),
            cos(uv.x * TAU * slices * 0.35 - uTime * uSpeed * 3.0)
        );
        sampleUV += wave * displacement * 0.32;
        color = rgbSplitColor(
            sampleUV,
            wave * split * 0.35
        );
    } else if (style < 17.5) {
        // Static Snow
        float snow = glitchHash(
            floor(uv * resolution) + animatedFrame * 17.0
        );
        float burst = step(
            1.0 - intensity * 0.75,
            glitchHash(blockId + animatedFrame)
        );
        float amount = clamp(
            uNoiseAmount * intensity * mix(0.35, 1.0, burst),
            0.0,
            1.0
        );
        color = mix(color, vec3(snow), amount);
    } else if (style < 18.5) {
        // CRT Corruption
        vec2 centered = uv * 2.0 - 1.0;
        float radius2 = dot(centered, centered);
        sampleUV = centered * (1.0 + radius2 * 0.10 * intensity);
        sampleUV = sampleUV * 0.5 + 0.5;
        color = rgbSplitColor(
            sampleUV,
            vec2(split * (0.4 + radius2), 0.0)
        );
        float scan = 0.5 + 0.5 * sin(uv.y * resolution.y * 3.14159);
        float grille = 0.5 + 0.5 * sin(uv.x * resolution.x * 2.0944);
        color *= 1.0 - uScanlines * intensity
            * (0.18 * scan + 0.06 * grille);
    } else if (style < 19.5) {
        // Horizontal Hold
        float holdCenter = glitchHash(vec2(animatedFrame, uSeed));
        float band = 1.0 - smoothstep(
            0.02,
            0.15,
            abs(uv.y - holdCenter)
        );
        sampleUV.x += band * displacement
            * (glitchHash(vec2(sliceId, animatedFrame)) - 0.5) * 2.0;
        color = sourceAt(sampleUV).rgb;
        color += band * uNoiseAmount * 0.18;
    } else if (style < 20.5) {
        // Vertical Hold
        float holdCenter = glitchHash(vec2(animatedFrame + 9.0, uSeed));
        float band = 1.0 - smoothstep(
            0.02,
            0.15,
            abs(uv.x - holdCenter)
        );
        sampleUV.y += band * displacement
            * (glitchHash(vec2(blockId.x, animatedFrame)) - 0.5) * 2.0;
        color = sourceAt(sampleUV).rgb;
        color = mix(color, color.brg, band * uColorShift);
    } else if (style < 21.5) {
        // Data Bend
        float bend = sin(
            uv.y * TAU * slices
            + glitchNoise(uv * blockGrid + animatedFrame) * TAU
        );
        sampleUV.x += bend * displacement * 0.55;
        color = sourceAt(sampleUV).rgb;
        color = mix(
            color,
            vec3(color.r, 1.0 - color.b, color.g),
            uColorShift * intensity
        );
        color = quantizeColor(
            color,
            mix(uQuantize, 3.0, uCompression * intensity)
        );
    } else if (style < 22.5) {
        // Edge Corrupt
        float left = sourceLumaGlitch(uv - vec2(texel.x, 0.0));
        float right = sourceLumaGlitch(uv + vec2(texel.x, 0.0));
        float down = sourceLumaGlitch(uv - vec2(0.0, texel.y));
        float up = sourceLumaGlitch(uv + vec2(0.0, texel.y));
        float edge = smoothstep(
            0.015,
            0.16,
            length(vec2(right - left, up - down)) * uEdgeAmount
        );
        vec2 edgeShift = (
            glitchHash2(floor(uv * resolution) + animatedFrame) - 0.5
        ) * displacement;
        vec3 corrupt = rgbSplitColor(
            uv + edgeShift,
            vec2(split, 0.0)
        );
        color = mix(color, corrupt, edge * intensity);
    } else {
        // Glitch Fusion: block shifts, slice tears, RGB separation,
        // compression, tracking noise, scanlines, and data loss together.
        float blockGate = step(
            1.0 - intensity * 0.62,
            glitchHash(blockId + animatedFrame)
        );
        float sliceGate = step(
            1.0 - intensity * 0.76,
            glitchHash(vec2(sliceId, animatedFrame + 3.0))
        );
        vec2 randomOffset = glitchHash2(blockId + animatedFrame) - 0.5;
        sampleUV += blockGate * randomOffset
            * vec2(displacement, displacement * 0.22);
        sampleUV.x += sliceGate
            * (glitchHash(vec2(sliceId, animatedFrame)) - 0.5)
            * displacement * 1.8;
        sampleUV.x += sin(
            uv.y * resolution.y * 0.032 + uTime * uSpeed * 7.0
        ) * uTracking * intensity;
        color = rgbSplitColor(
            sampleUV,
            vec2(split * (0.55 + blockGate), 0.0)
        );
        color = mix(
            color,
            quantizeColor(color, mix(uQuantize, 4.0, uCompression)),
            uCompression * intensity * 0.62
        );
        float snow = glitchHash(
            floor(uv * resolution) + animatedFrame * 23.0
        );
        color = mix(
            color,
            vec3(snow, snow * 0.72, 1.0 - snow),
            uNoiseAmount * intensity * 0.22
        );
        float dropoutGate = step(
            1.0 - uDropout * intensity,
            glitchHash(vec2(sliceId, animatedFrame + 19.0))
        );
        color *= 1.0 - dropoutGate * 0.82;
        float scan = 0.5 + 0.5 * sin(uv.y * resolution.y * 3.14159);
        color *= 1.0 - scan * uScanlines * intensity * 0.24;
    }

    color = mix(
        color,
        color.brg,
        clamp(uColorShift * intensity * 0.18, 0.0, 0.75)
    );
    return clamp(color, 0.0, 1.0);
}

void main() {
    vec2 uv = clamp(vUV.st, 0.0, 1.0);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    vec2 resolution = vec2(max(sourceSize.x, 1), max(sourceSize.y, 1));
    vec2 texel = 1.0 / resolution;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 glitched = glitchStyleColor(
        floor(uStyle + 0.5),
        uv,
        texel,
        resolution
    );
    float mixAmount = clamp(uMix, 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(
        mix(source.rgb, glitched, mixAmount),
        source.a
    ));
}
""".strip()

GLITCH_FUSION_PARAMETER_DEFINITIONS = (
    {
        "name": "Enabled", "label": "Module Enabled", "type": "toggle",
        "page": "Glitch", "default": True,
        "description": "Return the input unchanged when the entire module is disabled.",
    },
    {
        "name": "Autotime", "label": "Auto Time", "type": "toggle",
        "page": "Glitch", "default": True,
        "description": "Animate glitches from TouchDesigner's absolute time.",
    },
    {
        "name": "Timescale", "label": "Time Scale", "type": "float",
        "page": "Glitch", "default": 1.0, "min": -10.0, "max": 10.0,
        "description": "Scale or reverse automatic glitch time.",
    },
    {
        "name": "Manualtime", "label": "Manual Time", "type": "float",
        "page": "Glitch", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "description": "Deterministic time used when Auto Time is disabled.",
    },
    {
        "name": "Time", "label": "Effective Time", "type": "float",
        "page": "Glitch", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "uniform": "uTime", "animatable": False, "read_only": True,
        "description": "Resolved animation time sent to the glitch shader.",
    },
    {
        "name": "Style", "label": "Glitch Style", "type": "menu",
        "page": "Glitch Style", "default": "glitch_fusion",
        "menu_names": list(GLITCH_FUSION_STYLE_NAMES),
        "menu_labels": list(GLITCH_FUSION_STYLE_LABELS),
        "uniform": "uStyle",
        "description": "Choose one of 24 distinct glitch treatments.",
    },
    {
        "name": "Mix", "label": "Effect Mix", "type": "float",
        "page": "Glitch Style", "default": 1.0,
        "min": 0.0, "max": 1.0, "uniform": "uMix",
        "description": "Blend continuously between the source and glitch output.",
    },
    {
        "name": "Intensity", "label": "Glitch Intensity", "type": "float",
        "page": "Glitch Style", "default": 0.68,
        "min": 0.0, "max": 1.0, "uniform": "uIntensity",
        "description": "Scale the probability and strength of the selected glitch.",
    },
    {
        "name": "Speed", "label": "Glitch Speed", "type": "float",
        "page": "Glitch Style", "default": 1.0,
        "min": 0.0, "max": 8.0, "uniform": "uSpeed",
        "description": "Set the temporal rate of animated glitch decisions.",
    },
    {
        "name": "Blocksize", "label": "Block Size (Pixels)", "type": "int",
        "page": "Geometry", "default": 32,
        "min": 2, "max": 512, "uniform": "uBlockSize",
        "description": "Set macroblock and mosaic cell size in source pixels.",
    },
    {
        "name": "Slicedensity", "label": "Slice Density", "type": "int",
        "page": "Geometry", "default": 48,
        "min": 2, "max": 512, "uniform": "uSliceDensity",
        "description": "Set the number of horizontal decision bands.",
    },
    {
        "name": "Displacement", "label": "Displacement", "type": "float",
        "page": "Geometry", "default": 0.12,
        "min": 0.0, "max": 0.5, "uniform": "uDisplacement",
        "description": "Control block, slice, wave, hold, and data-bend offsets.",
    },
    {
        "name": "Jitter", "label": "Frame / Line Jitter", "type": "float",
        "page": "Geometry", "default": 0.035,
        "min": 0.0, "max": 0.25, "uniform": "uJitter",
        "description": "Control frame and scanline position instability.",
    },
    {
        "name": "Smear", "label": "Smear Distance", "type": "float",
        "page": "Geometry", "default": 0.16,
        "min": 0.0, "max": 0.6, "uniform": "uSmear",
        "description": "Control pixel-sort and datamosh streak length.",
    },
    {
        "name": "Rgbsplit", "label": "RGB Split", "type": "float",
        "page": "Signal", "default": 0.012,
        "min": 0.0, "max": 0.1, "uniform": "uRgbSplit",
        "description": "Separate red and blue sampling positions.",
    },
    {
        "name": "Noiseamount", "label": "Digital Noise", "type": "float",
        "page": "Signal", "default": 0.38,
        "min": 0.0, "max": 1.0, "uniform": "uNoiseAmount",
        "description": "Control static, snow, and digital noise amplitude.",
    },
    {
        "name": "Dropout", "label": "Signal Dropout", "type": "float",
        "page": "Signal", "default": 0.20,
        "min": 0.0, "max": 1.0, "uniform": "uDropout",
        "description": "Set the probability of missing signal bands.",
    },
    {
        "name": "Scanlines", "label": "Scanline Amount", "type": "float",
        "page": "Signal", "default": 0.42,
        "min": 0.0, "max": 1.0, "uniform": "uScanlines",
        "description": "Control analog and CRT scanline modulation.",
    },
    {
        "name": "Tracking", "label": "Tracking Error", "type": "float",
        "page": "Signal", "default": 0.018,
        "min": 0.0, "max": 0.2, "uniform": "uTracking",
        "description": "Control VHS tracking and rolling signal errors.",
    },
    {
        "name": "Compression", "label": "Compression Damage", "type": "float",
        "page": "Signal", "default": 0.46,
        "min": 0.0, "max": 1.0, "uniform": "uCompression",
        "description": "Control macroblock, datamosh, and fusion compression artifacts.",
    },
    {
        "name": "Colorshift", "label": "Color Data Shift", "type": "float",
        "page": "Color", "default": 0.35,
        "min": 0.0, "max": 1.0, "uniform": "uColorShift",
        "description": "Control channel rotation and data-bend color corruption.",
    },
    {
        "name": "Quantize", "label": "Color Levels", "type": "int",
        "page": "Color", "default": 12,
        "min": 2, "max": 64, "uniform": "uQuantize",
        "description": "Set the color levels used by quantize and compression modes.",
    },
    {
        "name": "Edgeamount", "label": "Edge Corruption", "type": "float",
        "page": "Color", "default": 1.6,
        "min": 0.0, "max": 6.0, "uniform": "uEdgeAmount",
        "description": "Set sensitivity for edge-driven corruption.",
    },
    {
        "name": "Seed", "label": "Random Seed", "type": "int",
        "page": "Color", "default": 47,
        "min": 0, "max": 100000, "uniform": "uSeed",
        "description": "Change deterministic glitch decisions and motion.",
    },
)

COLOR_ADJUSTMENT_OVERLAY_MODE_NAMES = (
    "normal",
    "multiply",
    "screen",
    "overlay",
    "soft_light",
    "hard_light",
    "color",
    "difference",
    "darken",
    "lighten",
    "color_dodge",
    "color_burn",
    "linear_dodge",
    "linear_burn",
    "exclusion",
    "luminosity",
)

COLOR_ADJUSTMENT_OVERLAY_MODE_LABELS = (
    "Normal",
    "Multiply",
    "Screen",
    "Overlay",
    "Soft Light",
    "Hard Light",
    "Color",
    "Difference",
    "Darken",
    "Lighten",
    "Color Dodge",
    "Color Burn",
    "Linear Dodge",
    "Linear Burn",
    "Exclusion",
    "Luminosity",
)

COLOR_ADJUSTMENT_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uInvert;
uniform float uExposure;
uniform float uBrightness;
uniform float uOffset;
uniform float uContrast;
uniform float uPivot;
uniform float uSaturation;
uniform float uVibrance;
uniform float uHue;
uniform float uTemperature;
uniform float uTint;
uniform float uGamma;
uniform float uBlackPoint;
uniform float uWhitePoint;
uniform vec3 uLift;
uniform vec3 uGain;
uniform float uShadows;
uniform float uMidtones;
uniform float uHighlights;
uniform float uBlacks;
uniform float uWhites;
uniform float uToe;
uniform float uShoulder;
uniform vec3 uShadowBalance;
uniform vec3 uMidtoneBalance;
uniform vec3 uHighlightBalance;
uniform float uBalancePreserveLuma;
uniform float uClarity;
uniform float uDehaze;
uniform float uMonochrome;
uniform float uSepia;
uniform float uFade;
uniform float uSolarizeAmount;
uniform float uSolarizePoint;
uniform float uThresholdAmount;
uniform float uThresholdLevel;
uniform float uThresholdSoftness;
uniform float uPosterizeAmount;
uniform float uPosterizeLevels;
uniform float uDuotoneAmount;
uniform vec4 uDuotoneShadow;
uniform vec4 uDuotoneHighlight;
uniform float uOverlayEnabled;
uniform vec4 uOverlayColor;
uniform float uOverlayAmount;
uniform float uOverlayMode;
uniform float uGrainAmount;
uniform float uGrainSize;
uniform float uGrainColored;
uniform float uGrainSeed;
uniform float uVignetteAmount;
uniform float uVignetteMidpoint;
uniform float uVignetteFeather;
uniform float uVignetteRoundness;

float colorLuma(vec3 color) {
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
}

float colorHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec3 colorRgbToHsv(vec3 color) {
    vec4 K = vec4(0.0, -0.3333333333, 0.6666666667, -1.0);
    vec4 p = mix(vec4(color.bg, K.wz), vec4(color.gb, K.xy), step(color.b, color.g));
    vec4 q = mix(vec4(p.xyw, color.r), vec4(color.r, p.yzx), step(p.x, color.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 colorHsvToRgb(vec3 color) {
    vec3 p = abs(fract(color.xxx + vec3(0.0, 0.6666666667, 0.3333333333)) * 6.0 - 3.0);
    return color.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), color.y);
}

vec3 colorOverlayBlend(vec3 base, vec3 layer, float mode) {
    if (mode < 0.5) {
        return layer;
    }
    if (mode < 1.5) {
        return base * layer;
    }
    if (mode < 2.5) {
        return 1.0 - (1.0 - base) * (1.0 - layer);
    }
    if (mode < 3.5) {
        return mix(2.0 * base * layer, 1.0 - 2.0 * (1.0 - base) * (1.0 - layer), step(0.5, base));
    }
    if (mode < 4.5) {
        return (1.0 - 2.0 * layer) * base * base + 2.0 * layer * base;
    }
    if (mode < 5.5) {
        return mix(2.0 * base * layer, 1.0 - 2.0 * (1.0 - base) * (1.0 - layer), step(0.5, layer));
    }
    if (mode < 6.5) {
        vec3 baseHsv = colorRgbToHsv(base);
        vec3 layerHsv = colorRgbToHsv(layer);
        return colorHsvToRgb(vec3(layerHsv.xy, baseHsv.z));
    }
    if (mode < 7.5) {
        return abs(base - layer);
    }
    if (mode < 8.5) {
        return min(base, layer);
    }
    if (mode < 9.5) {
        return max(base, layer);
    }
    if (mode < 10.5) {
        return min(base / max(vec3(1.0) - layer, vec3(1.0e-4)), vec3(1.0));
    }
    if (mode < 11.5) {
        return max(vec3(1.0) - (vec3(1.0) - base) / max(layer, vec3(1.0e-4)), vec3(0.0));
    }
    if (mode < 12.5) {
        return min(base + layer, vec3(1.0));
    }
    if (mode < 13.5) {
        return max(base + layer - vec3(1.0), vec3(0.0));
    }
    if (mode < 14.5) {
        return base + layer - 2.0 * base * layer;
    }
    vec3 baseHsv = colorRgbToHsv(base);
    vec3 layerHsv = colorRgbToHsv(layer);
    return colorHsvToRgb(vec3(baseHsv.xy, layerHsv.z));
}

void main() {
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec3 color = max(source.rgb, vec3(0.0));

    float whitePoint = max(uWhitePoint, uBlackPoint + 1.0e-4);
    color = clamp((color - vec3(uBlackPoint)) / (whitePoint - uBlackPoint), 0.0, 1.0);
    color *= exp2(uExposure);
    color = max(color + uLift + vec3(uOffset), vec3(0.0))
        * max(uGain, vec3(0.0));

    vec3 balance = vec3(
        1.0 + 0.18 * uTemperature + 0.08 * uTint,
        1.0 - 0.12 * uTint,
        1.0 - 0.18 * uTemperature + 0.08 * uTint
    );
    color *= max(balance, vec3(0.05));
    color = pow(max(color, vec3(0.0)), vec3(1.0 / max(uGamma, 0.05)));
    float pivot = clamp(uPivot, 0.0, 1.0);
    color = (color - pivot) * max(uContrast, 0.0) + pivot + uBrightness;

    float luminance = colorLuma(color);
    float shadowMask = 1.0 - smoothstep(0.0, 0.58, luminance);
    float midtoneMask = 1.0 - smoothstep(0.18, 0.52, abs(luminance - 0.5));
    float highlightMask = smoothstep(0.42, 1.0, luminance);
    float blackMask = 1.0 - smoothstep(0.02, 0.30, luminance);
    float whiteMask = smoothstep(0.70, 0.98, luminance);
    color += vec3(0.35 * uShadows * shadowMask);
    color += vec3(0.30 * uMidtones * midtoneMask);
    color += vec3(0.35 * uHighlights * highlightMask);
    color += vec3(0.25 * uBlacks * blackMask);
    color += vec3(0.25 * uWhites * whiteMask);
    color += vec3(0.22 * uToe * shadowMask * (1.0 - clamp(color, 0.0, 1.0)));
    color -= vec3(0.22 * uShoulder * highlightMask * clamp(color, 0.0, 1.0));

    float balanceLumaBefore = colorLuma(color);
    color += 0.30 * (
        uShadowBalance * shadowMask
        + uMidtoneBalance * midtoneMask
        + uHighlightBalance * highlightMask
    );
    float balanceLumaAfter = colorLuma(color);
    color -= vec3(
        (balanceLumaAfter - balanceLumaBefore)
        * clamp(uBalancePreserveLuma, 0.0, 1.0)
    );

    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    vec2 texel = 1.0 / vec2(max(sourceSize, ivec2(1)));
    vec3 localAverage = 0.25 * (
        texture(sTD2DInputs[0], clamp(vUV.st + vec2(texel.x, 0.0), 0.0, 1.0)).rgb
        + texture(sTD2DInputs[0], clamp(vUV.st - vec2(texel.x, 0.0), 0.0, 1.0)).rgb
        + texture(sTD2DInputs[0], clamp(vUV.st + vec2(0.0, texel.y), 0.0, 1.0)).rgb
        + texture(sTD2DInputs[0], clamp(vUV.st - vec2(0.0, texel.y), 0.0, 1.0)).rgb
    );
    color += (color - localAverage) * uClarity;
    float dehazeContrast = 1.0 + 0.65 * uDehaze;
    color = (color - 0.5) * dehazeContrast + 0.5;
    color += vec3(0.08 * uDehaze);

    vec3 hsv = colorRgbToHsv(max(color, vec3(0.0)));
    hsv.x = fract(hsv.x + uHue);
    color = colorHsvToRgb(hsv);
    luminance = colorLuma(color);
    color = mix(vec3(luminance), color, max(uSaturation, 0.0));
    float chroma = max(color.r, max(color.g, color.b)) - min(color.r, min(color.g, color.b));
    float vibranceScale = 1.0 + clamp(uVibrance, -1.0, 1.0) * (1.0 - clamp(chroma, 0.0, 1.0));
    color = mix(vec3(colorLuma(color)), color, max(vibranceScale, 0.0));

    color = mix(color, vec3(1.0) - color, clamp(uInvert, 0.0, 1.0));
    luminance = colorLuma(color);
    color = mix(color, vec3(luminance), clamp(uMonochrome, 0.0, 1.0));
    vec3 sepia = vec3(
        dot(color, vec3(0.393, 0.769, 0.189)),
        dot(color, vec3(0.349, 0.686, 0.168)),
        dot(color, vec3(0.272, 0.534, 0.131))
    );
    color = mix(color, sepia, clamp(uSepia, 0.0, 1.0));

    vec3 faded = color * 0.78 + vec3(0.11);
    color = mix(color, faded, clamp(uFade, 0.0, 1.0));
    vec3 solarizeMask = smoothstep(
        vec3(clamp(uSolarizePoint, 0.0, 1.0) - 0.04),
        vec3(clamp(uSolarizePoint, 0.0, 1.0) + 0.04),
        color
    );
    vec3 solarized = mix(color, vec3(1.0) - color, solarizeMask);
    color = mix(color, solarized, clamp(uSolarizeAmount, 0.0, 1.0));
    luminance = colorLuma(color);
    float thresholdSoftness = max(uThresholdSoftness, 0.001);
    float thresholdValue = smoothstep(
        uThresholdLevel - thresholdSoftness,
        uThresholdLevel + thresholdSoftness,
        luminance
    );
    color = mix(
        color,
        vec3(thresholdValue),
        clamp(uThresholdAmount, 0.0, 1.0)
    );

    float levels = max(floor(uPosterizeLevels + 0.5), 2.0);
    vec3 posterized = floor(clamp(color, 0.0, 1.0) * (levels - 1.0) + 0.5) / (levels - 1.0);
    color = mix(color, posterized, clamp(uPosterizeAmount, 0.0, 1.0));

    luminance = clamp(colorLuma(color), 0.0, 1.0);
    vec3 duotone = mix(uDuotoneShadow.rgb, uDuotoneHighlight.rgb, luminance);
    float duotoneAlpha = mix(
        uDuotoneShadow.a,
        uDuotoneHighlight.a,
        luminance
    );
    color = mix(
        color,
        duotone,
        clamp(uDuotoneAmount * duotoneAlpha, 0.0, 1.0)
    );

    if (uGrainAmount > 0.0) {
        float grainScale = mix(180.0, 2160.0, clamp(uGrainSize, 0.0, 1.0));
        vec2 grainCell = floor(vUV.st * grainScale) + vec2(uGrainSeed * 13.17);
        float grainMono = colorHash(grainCell) - 0.5;
        vec3 grainColor = vec3(
            colorHash(grainCell + 17.0),
            colorHash(grainCell + 37.0),
            colorHash(grainCell + 71.0)
        ) - 0.5;
        vec3 grain = mix(vec3(grainMono), grainColor, clamp(uGrainColored, 0.0, 1.0));
        color += grain * (0.35 * clamp(uGrainAmount, 0.0, 1.0));
    }

    float aspect = float(max(sourceSize.x, 1)) / float(max(sourceSize.y, 1));
    vec2 vignetteUv = vUV.st - 0.5;
    vignetteUv.x *= mix(1.0, aspect, clamp(uVignetteRoundness, 0.0, 1.0));
    float vignetteDistance = length(vignetteUv) * 1.41421356237;
    float vignetteMask = smoothstep(
        clamp(uVignetteMidpoint, 0.0, 1.0),
        clamp(uVignetteMidpoint + max(uVignetteFeather, 0.001), 0.001, 1.5),
        vignetteDistance
    );
    color *= max(0.0, 1.0 - uVignetteAmount * vignetteMask);

    if (uOverlayEnabled > 0.5 && uOverlayAmount > 0.0) {
        vec3 blended = colorOverlayBlend(clamp(color, 0.0, 1.0), uOverlayColor.rgb, uOverlayMode);
        float overlayMix = clamp(uOverlayAmount * uOverlayColor.a, 0.0, 1.0);
        color = mix(color, blended, overlayMix);
    }

    color = clamp(color, 0.0, 1.0);
    float mixAmount = clamp(uMix, 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(mix(source.rgb, color, mixAmount), source.a));
}
""".strip()

COLOR_ADJUSTMENT_PARAMETER_DEFINITIONS = (
    {
        "name": "Enabled", "label": "Module Enabled", "type": "toggle",
        "page": "Color Adjustment", "default": True,
        "description": "Return the input unchanged when the entire module is disabled.",
    },
    {
        "name": "Mix", "label": "Adjustment Mix", "type": "float",
        "page": "Color Adjustment", "default": 1.0,
        "min": 0.0, "max": 1.0, "uniform": "uMix",
        "description": "Blend continuously between the source and adjusted color.",
    },
    {
        "name": "Invert", "label": "Invert Amount", "type": "float",
        "page": "Color Adjustment", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uInvert",
        "description": "Blend toward a full RGB color inversion.",
    },
    {
        "name": "Exposure", "label": "Exposure (Stops)", "type": "float",
        "page": "Primary", "default": 0.0,
        "min": -5.0, "max": 5.0, "uniform": "uExposure",
        "description": "Scale image exposure in photographic stops.",
    },
    {
        "name": "Brightness", "label": "Brightness", "type": "float",
        "page": "Primary", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uBrightness",
        "description": "Add or subtract overall brightness after gamma correction.",
    },
    {
        "name": "Offset", "label": "Global Offset", "type": "float",
        "page": "Primary", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uOffset",
        "description": "Add a uniform RGB offset before gamma and contrast.",
    },
    {
        "name": "Contrast", "label": "Contrast", "type": "float",
        "page": "Primary", "default": 1.0,
        "min": 0.0, "max": 3.0, "uniform": "uContrast",
        "description": "Expand or compress RGB contrast around middle gray.",
    },
    {
        "name": "Pivot", "label": "Contrast Pivot", "type": "float",
        "page": "Primary", "default": 0.5,
        "min": 0.0, "max": 1.0, "uniform": "uPivot",
        "description": "Set the tonal pivot used by the contrast control.",
    },
    {
        "name": "Saturation", "label": "Saturation", "type": "float",
        "page": "Primary", "default": 1.0,
        "min": 0.0, "max": 3.0, "uniform": "uSaturation",
        "description": "Scale color saturation while preserving luminance.",
    },
    {
        "name": "Vibrance", "label": "Vibrance", "type": "float",
        "page": "Primary", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uVibrance",
        "description": "Adjust less-saturated colors more strongly than vivid colors.",
    },
    {
        "name": "Hue", "label": "Hue Rotation", "type": "float",
        "page": "Primary", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uHue",
        "description": "Rotate hue by normalized turns; 0.5 equals 180 degrees.",
    },
    {
        "name": "Temperature", "label": "Temperature", "type": "float",
        "page": "White Balance", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uTemperature",
        "description": "Shift the image from cool blue toward warm amber.",
    },
    {
        "name": "Tint", "label": "Tint", "type": "float",
        "page": "White Balance", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uTint",
        "description": "Shift the image between green and magenta.",
    },
    {
        "name": "Blackpoint", "label": "Input Black", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": 0.0, "max": 0.99, "uniform": "uBlackPoint",
        "description": "Remap this input value to black before other adjustments.",
    },
    {
        "name": "Whitepoint", "label": "Input White", "type": "float",
        "page": "Tonal Range", "default": 1.0,
        "min": 0.01, "max": 4.0, "uniform": "uWhitePoint",
        "description": "Remap this input value to white before other adjustments.",
    },
    {
        "name": "Gamma", "label": "Gamma", "type": "float",
        "page": "Tonal Range", "default": 1.0,
        "min": 0.05, "max": 4.0, "uniform": "uGamma",
        "description": "Adjust midtone gamma without changing the nominal black point.",
    },
    {
        "name": "Lift", "label": "RGB Lift", "type": "xyz",
        "page": "Tonal Range", "default": [0.0, 0.0, 0.0],
        "min": -1.0, "max": 1.0, "uniform": "uLift",
        "description": "Add independent red, green, and blue shadow offsets.",
    },
    {
        "name": "Gain", "label": "RGB Gain", "type": "xyz",
        "page": "Tonal Range", "default": [1.0, 1.0, 1.0],
        "min": 0.0, "max": 4.0, "uniform": "uGain",
        "description": "Multiply independent red, green, and blue channel gains.",
    },
    {
        "name": "Shadows", "label": "Shadows", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uShadows",
        "description": "Darken or lift the low-luminance portion of the image.",
    },
    {
        "name": "Midtones", "label": "Midtones", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uMidtones",
        "description": "Darken or lift the middle-luminance portion of the image.",
    },
    {
        "name": "Highlights", "label": "Highlights", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uHighlights",
        "description": "Darken or lift the high-luminance portion of the image.",
    },
    {
        "name": "Blacks", "label": "Blacks", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uBlacks",
        "description": "Adjust the deepest tonal region independently.",
    },
    {
        "name": "Whites", "label": "Whites", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uWhites",
        "description": "Adjust the brightest tonal region independently.",
    },
    {
        "name": "Toe", "label": "Shadow Toe", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uToe",
        "description": "Lift or deepen the shadow roll-in curve.",
    },
    {
        "name": "Shoulder", "label": "Highlight Shoulder", "type": "float",
        "page": "Tonal Range", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uShoulder",
        "description": "Compress or expand the highlight roll-off curve.",
    },
    {
        "name": "Shadowbalance", "label": "Shadow Balance", "type": "xyz",
        "page": "Color Balance", "default": [0.0, 0.0, 0.0],
        "min": -1.0, "max": 1.0, "uniform": "uShadowBalance",
        "description": "Add independent RGB color balance to shadows.",
    },
    {
        "name": "Midtonebalance", "label": "Midtone Balance", "type": "xyz",
        "page": "Color Balance", "default": [0.0, 0.0, 0.0],
        "min": -1.0, "max": 1.0, "uniform": "uMidtoneBalance",
        "description": "Add independent RGB color balance to midtones.",
    },
    {
        "name": "Highlightbalance", "label": "Highlight Balance", "type": "xyz",
        "page": "Color Balance", "default": [0.0, 0.0, 0.0],
        "min": -1.0, "max": 1.0, "uniform": "uHighlightBalance",
        "description": "Add independent RGB color balance to highlights.",
    },
    {
        "name": "Balancepreserveluma", "label": "Preserve Balance Luma", "type": "float",
        "page": "Color Balance", "default": 1.0,
        "min": 0.0, "max": 1.0, "uniform": "uBalancePreserveLuma",
        "description": "Preserve luminance while applying RGB tonal balance.",
    },
    {
        "name": "Clarity", "label": "Clarity", "type": "float",
        "page": "Detail", "default": 0.0,
        "min": -1.0, "max": 2.0, "uniform": "uClarity",
        "description": "Reduce or enhance local image contrast.",
    },
    {
        "name": "Dehaze", "label": "Dehaze", "type": "float",
        "page": "Detail", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uDehaze",
        "description": "Reduce haze or add a softer atmospheric wash.",
    },
    {
        "name": "Monochrome", "label": "Monochrome Amount", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uMonochrome",
        "description": "Blend smoothly toward luminance-only grayscale.",
    },
    {
        "name": "Sepia", "label": "Sepia Amount", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uSepia",
        "description": "Blend toward a classic warm sepia color matrix.",
    },
    {
        "name": "Fade", "label": "Fade", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uFade",
        "description": "Lift blacks and soften contrast for a faded print look.",
    },
    {
        "name": "Solarizeamount", "label": "Solarize Amount", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uSolarizeAmount",
        "description": "Invert channel values above the solarize point.",
    },
    {
        "name": "Solarizepoint", "label": "Solarize Point", "type": "float",
        "page": "Creative Color", "default": 0.5,
        "min": 0.0, "max": 1.0, "uniform": "uSolarizePoint",
        "description": "Set the crossover point used by Solarize Amount.",
    },
    {
        "name": "Thresholdamount", "label": "Threshold Amount", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uThresholdAmount",
        "description": "Blend toward an adjustable luminance threshold image.",
    },
    {
        "name": "Thresholdlevel", "label": "Threshold Level", "type": "float",
        "page": "Creative Color", "default": 0.5,
        "min": 0.0, "max": 1.0, "uniform": "uThresholdLevel",
        "description": "Set the luminance transition point for thresholding.",
    },
    {
        "name": "Thresholdsoftness", "label": "Threshold Softness", "type": "float",
        "page": "Creative Color", "default": 0.02,
        "min": 0.001, "max": 0.5, "uniform": "uThresholdSoftness",
        "description": "Control the width of the threshold transition.",
    },
    {
        "name": "Posterizeamount", "label": "Posterize Amount", "type": "float",
        "page": "Creative Color", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uPosterizeAmount",
        "description": "Blend toward discrete per-channel color levels.",
    },
    {
        "name": "Posterizelevels", "label": "Posterize Levels", "type": "int",
        "page": "Creative Color", "default": 8,
        "min": 2, "max": 64, "uniform": "uPosterizeLevels",
        "description": "Set the number of levels used by the posterize treatment.",
    },
    {
        "name": "Duotoneamount", "label": "Duotone Amount", "type": "float",
        "page": "Duotone", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uDuotoneAmount",
        "description": "Map luminance between the selected shadow and highlight colors.",
    },
    {
        "name": "Duotoneshadow", "label": "Duotone Shadow", "type": "rgba",
        "page": "Duotone", "default": [0.04, 0.07, 0.16, 1.0],
        "uniform": "uDuotoneShadow",
        "description": "Set the color used for the darkest duotone values.",
    },
    {
        "name": "Duotonehighlight", "label": "Duotone Highlight", "type": "rgba",
        "page": "Duotone", "default": [0.96, 0.62, 0.24, 1.0],
        "uniform": "uDuotoneHighlight",
        "description": "Set the color used for the brightest duotone values.",
    },
    {
        "name": "Grainamount", "label": "Grain Amount", "type": "float",
        "page": "Film", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uGrainAmount",
        "description": "Add deterministic monochrome or colored film grain.",
    },
    {
        "name": "Grainsize", "label": "Grain Size", "type": "float",
        "page": "Film", "default": 0.35,
        "min": 0.0, "max": 1.0, "uniform": "uGrainSize",
        "description": "Set the spatial scale of the deterministic grain pattern.",
    },
    {
        "name": "Graincolored", "label": "Colored Grain", "type": "float",
        "page": "Film", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uGrainColored",
        "description": "Blend the grain pattern from monochrome to independent RGB noise.",
    },
    {
        "name": "Grainseed", "label": "Grain Seed", "type": "int",
        "page": "Film", "default": 17,
        "min": 0, "max": 100000, "uniform": "uGrainSeed",
        "description": "Choose a repeatable film-grain pattern.",
    },
    {
        "name": "Vignetteamount", "label": "Vignette Amount", "type": "float",
        "page": "Film", "default": 0.0,
        "min": -1.0, "max": 1.0, "uniform": "uVignetteAmount",
        "description": "Darken positive values or lift negative values toward the edges.",
    },
    {
        "name": "Vignettemidpoint", "label": "Vignette Midpoint", "type": "float",
        "page": "Film", "default": 0.45,
        "min": 0.0, "max": 1.0, "uniform": "uVignetteMidpoint",
        "description": "Set where the vignette begins.",
    },
    {
        "name": "Vignettefeather", "label": "Vignette Feather", "type": "float",
        "page": "Film", "default": 0.35,
        "min": 0.001, "max": 1.0, "uniform": "uVignetteFeather",
        "description": "Set the softness of the vignette transition.",
    },
    {
        "name": "Vignetteroundness", "label": "Vignette Roundness", "type": "float",
        "page": "Film", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uVignetteRoundness",
        "description": "Blend between image-relative and circular vignette geometry.",
    },
    {
        "name": "Overlayenabled", "label": "Color Overlay Enabled", "type": "toggle",
        "page": "Color Overlay", "default": False,
        "uniform": "uOverlayEnabled",
        "description": "Enable the independently adjustable color-overlay layer.",
    },
    {
        "name": "Overlaycolor", "label": "Overlay Color", "type": "rgba",
        "page": "Color Overlay", "default": [0.15, 0.55, 1.0, 1.0],
        "uniform": "uOverlayColor",
        "description": "Set the overlay RGB color and multiply its strength by alpha.",
    },
    {
        "name": "Overlayamount", "label": "Overlay Amount", "type": "float",
        "page": "Color Overlay", "default": 0.5,
        "min": 0.0, "max": 1.0, "uniform": "uOverlayAmount",
        "description": "Blend the selected color-overlay mode into the adjusted image.",
    },
    {
        "name": "Overlaymode", "label": "Overlay Blend Mode", "type": "menu",
        "page": "Color Overlay", "default": "soft_light",
        "menu_names": list(COLOR_ADJUSTMENT_OVERLAY_MODE_NAMES),
        "menu_labels": list(COLOR_ADJUSTMENT_OVERLAY_MODE_LABELS),
        "uniform": "uOverlayMode",
        "description": "Choose one of sixteen color-overlay blend modes.",
    },
)

MOTION_STUDIO_STYLE_NAMES = (
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

MOTION_STUDIO_STYLE_LABELS = (
    "Pan",
    "Diagonal Pan",
    "Drift",
    "Orbit",
    "Figure Eight",
    "Bounce",
    "Pendulum",
    "Swing",
    "Shake",
    "Handheld Camera",
    "Jitter",
    "Float",
    "Breathe",
    "Zoom Pulse",
    "Infinite Zoom",
    "Dolly Zoom",
    "Rotate",
    "Spin Pulse",
    "Spiral",
    "Vortex",
    "Twist",
    "Horizontal Wave",
    "Vertical Wave",
    "Radial Wave",
    "Ripple",
    "Liquid",
    "Wobble",
    "Slither",
    "Flow Field",
    "Heat Haze",
    "Parallax",
    "Perspective Sway",
    "Rolling Shutter",
    "Whip Pan",
    "Stop Motion",
    "Step Jump",
    "Conveyor",
    "Tunnel",
    "Kaleidoscope Motion",
    "Elastic",
)

MOTION_STUDIO_EDGE_MODE_NAMES = (
    "hold",
    "repeat",
    "mirror",
    "transparent",
)

MOTION_STUDIO_EDGE_MODE_LABELS = (
    "Hold",
    "Repeat",
    "Mirror",
    "Transparent",
)

MOTION_STUDIO_EASING_NAMES = (
    "linear",
    "sine",
    "smooth",
    "smoother",
    "bounce",
    "elastic",
)

MOTION_STUDIO_EASING_LABELS = (
    "Linear",
    "Sine",
    "Smooth",
    "Smoother",
    "Bounce",
    "Elastic",
)

MOTION_STUDIO_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uStyle;
uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uSpeed;
uniform float uFrequency;
uniform float uPhase;
uniform vec2 uDirection;
uniform vec2 uCenter;
uniform float uZoom;
uniform float uRotation;
uniform float uWarp;
uniform float uRandomness;
uniform float uSeed;
uniform float uSteps;
uniform float uSegments;
uniform float uEdgeMode;
uniform float uEasing;
uniform float uTrailAmount;
uniform float uTrailSamples;

const float MOTION_PI = 3.14159265358979323846;
const float MOTION_TAU = 6.28318530717958647692;

float motionHash(float value) {
    return fract(sin(value * 127.1 + uSeed * 19.19) * 43758.5453123);
}

float motionHash2(vec2 value) {
    return fract(sin(dot(value, vec2(127.1, 311.7)) + uSeed * 7.17) * 43758.5453123);
}

float motionEase01(float value) {
    float x = clamp(value, 0.0, 1.0);
    if (uEasing < 0.5) {
        return x;
    }
    if (uEasing < 1.5) {
        return 0.5 - 0.5 * cos(MOTION_PI * x);
    }
    if (uEasing < 2.5) {
        return x * x * (3.0 - 2.0 * x);
    }
    if (uEasing < 3.5) {
        return x * x * x * (x * (x * 6.0 - 15.0) + 10.0);
    }
    if (uEasing < 4.5) {
        float bounce = abs(sin(MOTION_PI * (x + 0.12))) * (1.0 - x);
        return clamp(x + bounce * 0.32, 0.0, 1.0);
    }
    return clamp(x + sin(x * MOTION_PI * 6.0) * (1.0 - x) * 0.18, 0.0, 1.0);
}

float motionOsc(float phase) {
    float x = fract(phase);
    if (uEasing < 0.5) {
        return 1.0 - 4.0 * abs(x - 0.5);
    }
    if (uEasing < 1.5) {
        return sin(MOTION_TAU * x);
    }
    float triangle = 1.0 - 4.0 * abs(x - 0.5);
    float magnitude = motionEase01(abs(triangle));
    return sign(triangle) * magnitude;
}

mat2 motionRotate(float angle) {
    float sineValue = sin(angle);
    float cosineValue = cos(angle);
    return mat2(cosineValue, -sineValue, sineValue, cosineValue);
}

vec2 motionDirection(float aspect) {
    vec2 direction = vec2(uDirection.x * aspect, uDirection.y);
    if (dot(direction, direction) < 1.0e-6) {
        direction = vec2(aspect, 0.0);
    }
    return normalize(direction);
}

vec2 motionSmoothRandom(float value) {
    float baseValue = floor(value);
    float blendValue = motionEase01(fract(value));
    vec2 firstValue = vec2(
        motionHash(baseValue * 2.0 + 3.0),
        motionHash(baseValue * 2.0 + 11.0)
    );
    vec2 secondValue = vec2(
        motionHash((baseValue + 1.0) * 2.0 + 3.0),
        motionHash((baseValue + 1.0) * 2.0 + 11.0)
    );
    return mix(firstValue, secondValue, blendValue) * 2.0 - 1.0;
}

vec2 motionUV(float style, vec2 uv, vec2 resolution, float timeValue) {
    float aspect = resolution.x / max(resolution.y, 1.0);
    vec2 center = clamp(uCenter, vec2(0.0), vec2(1.0));
    vec2 point = uv - center;
    point.x *= aspect;
    point = motionRotate(-radians(uRotation)) * point;
    point /= max(uZoom, 0.05);

    vec2 direction = motionDirection(aspect);
    vec2 perpendicular = vec2(-direction.y, direction.x);
    float phaseTime = timeValue * uSpeed + uPhase;
    float angle = MOTION_TAU * phaseTime;
    float oscillation = motionOsc(phaseTime);
    float amount = clamp(uAmount, 0.0, 1.0);
    float warp = clamp(uWarp, 0.0, 2.0);
    float frequency = max(uFrequency, 0.01);
    float steps = max(floor(uSteps + 0.5), 2.0);
    float radius = length(point);
    vec2 moved = point;

    if (style < 0.5) {
        // Pan
        moved -= direction * phaseTime * amount * 0.32;
    } else if (style < 1.5) {
        // Diagonal Pan
        vec2 diagonal = normalize(direction + perpendicular * 0.72);
        moved -= diagonal * phaseTime * amount * 0.34;
    } else if (style < 2.5) {
        // Drift
        moved -= vec2(sin(angle * 0.73), cos(angle * 0.49 + 0.8))
            * amount * 0.16;
    } else if (style < 3.5) {
        // Orbit
        moved -= vec2(cos(angle), sin(angle)) * amount * 0.19;
    } else if (style < 4.5) {
        // Figure Eight
        moved -= vec2(sin(angle), sin(angle * 2.0) * 0.55)
            * amount * 0.20;
    } else if (style < 5.5) {
        // Bounce
        moved -= direction * oscillation * amount * 0.26;
    } else if (style < 6.5) {
        // Pendulum
        moved = motionRotate(-oscillation * amount * 0.78) * point;
    } else if (style < 7.5) {
        // Swing
        float swing = oscillation * amount;
        moved.x += point.y * swing * 0.95;
        moved.y -= direction.y * swing * 0.05;
    } else if (style < 8.5) {
        // Shake
        vec2 randomMove = motionSmoothRandom(phaseTime * frequency * 2.5);
        moved -= randomMove * amount * mix(0.035, 0.14, uRandomness);
    } else if (style < 9.5) {
        // Handheld Camera
        vec2 randomMove = motionSmoothRandom(phaseTime * frequency * 0.85);
        float randomAngle = motionSmoothRandom(
            phaseTime * frequency * 0.47 + 17.0
        ).x;
        moved = motionRotate(randomAngle * amount * 0.065) * point;
        moved -= randomMove * amount * mix(0.025, 0.09, uRandomness);
    } else if (style < 10.5) {
        // Jitter
        float frameValue = floor(phaseTime * steps);
        vec2 randomMove = vec2(
            motionHash(frameValue * 2.0 + 5.0),
            motionHash(frameValue * 2.0 + 13.0)
        ) * 2.0 - 1.0;
        moved -= randomMove * amount * mix(0.03, 0.16, uRandomness);
    } else if (style < 11.5) {
        // Float
        moved.y -= sin(angle) * amount * 0.18;
        moved = motionRotate(cos(angle * 0.57) * amount * 0.055) * moved;
    } else if (style < 12.5) {
        // Breathe
        float scaleValue = 1.0 + oscillation * amount * 0.16;
        moved = point / max(scaleValue, 0.1);
    } else if (style < 13.5) {
        // Zoom Pulse
        float scaleValue = exp2(oscillation * amount * 0.42);
        moved = point / scaleValue;
    } else if (style < 14.5) {
        // Infinite Zoom
        float scaleValue = exp2(fract(phaseTime * 0.5) * (0.65 + amount));
        moved = point / scaleValue;
    } else if (style < 15.5) {
        // Dolly Zoom
        float scaleValue = 1.0 + oscillation * amount * 0.44;
        float radialBend = 1.0 + oscillation * warp * radius * radius * 0.8;
        moved = point * radialBend / max(scaleValue, 0.12);
    } else if (style < 16.5) {
        // Rotate
        moved = motionRotate(-angle * amount) * point;
    } else if (style < 17.5) {
        // Spin Pulse
        float scaleValue = 1.0 + sin(angle * 0.5) * amount * 0.24;
        moved = motionRotate(-angle * amount * 1.35) * point;
        moved /= max(scaleValue, 0.1);
    } else if (style < 18.5) {
        // Spiral
        moved = motionRotate(-angle * amount * 0.35 - radius * warp * 3.5)
            * point;
        moved *= 1.0 + oscillation * amount * 0.12;
    } else if (style < 19.5) {
        // Vortex
        float vortexAngle = angle * amount * 0.18
            + (1.0 - smoothstep(0.0, 0.9, radius)) * warp * 4.5;
        moved = motionRotate(-vortexAngle) * point;
    } else if (style < 20.5) {
        // Twist
        float twistAngle = sin(radius * frequency * MOTION_TAU - angle)
            * amount * warp * 1.4;
        moved = motionRotate(twistAngle) * point;
    } else if (style < 21.5) {
        // Horizontal Wave
        moved.x += sin(point.y * frequency * MOTION_TAU + angle)
            * amount * (0.045 + 0.10 * warp);
    } else if (style < 22.5) {
        // Vertical Wave
        moved.y += sin(point.x * frequency * MOTION_TAU + angle)
            * amount * (0.045 + 0.10 * warp);
    } else if (style < 23.5) {
        // Radial Wave
        float scaleValue = 1.0 + sin(radius * frequency * MOTION_TAU - angle)
            * amount * warp * 0.22;
        moved = point * scaleValue;
    } else if (style < 24.5) {
        // Ripple
        vec2 radialDirection = point / max(radius, 1.0e-4);
        moved += radialDirection
            * sin(radius * frequency * MOTION_TAU - angle * 1.6)
            * amount * (0.025 + warp * 0.075);
    } else if (style < 25.5) {
        // Liquid
        moved.x += sin(point.y * frequency * MOTION_TAU + angle)
            * amount * warp * 0.075;
        moved.y += cos(point.x * frequency * MOTION_TAU * 0.83 - angle * 0.71)
            * amount * warp * 0.075;
        moved += vec2(
            sin((point.x + point.y) * frequency * 3.2 + angle * 0.43),
            cos((point.x - point.y) * frequency * 3.6 - angle * 0.37)
        ) * amount * warp * 0.028;
    } else if (style < 26.5) {
        // Wobble
        moved += vec2(
            sin(point.y * frequency * MOTION_TAU + angle),
            sin(point.x * frequency * MOTION_TAU - angle * 1.17)
        ) * amount * (0.035 + warp * 0.065);
    } else if (style < 27.5) {
        // Slither
        moved.x += sin(point.y * frequency * MOTION_TAU - angle * 1.4)
            * amount * (0.05 + warp * 0.08);
        moved.y -= direction.y * phaseTime * amount * 0.07;
    } else if (style < 28.5) {
        // Flow Field
        vec2 cell = floor((point + vec2(2.0)) * frequency * 3.0);
        float fieldAngle = motionHash2(cell) * MOTION_TAU
            + angle * (0.25 + uRandomness);
        moved += vec2(cos(fieldAngle), sin(fieldAngle))
            * amount * (0.025 + warp * 0.075);
    } else if (style < 29.5) {
        // Heat Haze
        float haze = sin(point.y * frequency * MOTION_TAU * 2.7 + angle * 2.1);
        haze += sin(point.y * frequency * MOTION_TAU * 5.3 - angle * 1.4) * 0.45;
        moved.x += haze * amount * (0.008 + warp * 0.028);
    } else if (style < 30.5) {
        // Parallax
        float layerValue = 1.0 + floor(clamp(radius * 5.0, 0.0, 3.0));
        moved -= direction * oscillation * amount * 0.055 * layerValue;
    } else if (style < 31.5) {
        // Perspective Sway
        float sway = oscillation * amount;
        float denominator = max(0.35, 1.0 + point.y * sway * 1.15);
        moved.x = (point.x + point.y * sway * 0.18) / denominator;
        moved.y = point.y / denominator;
    } else if (style < 32.5) {
        // Rolling Shutter
        float scanTime = phaseTime + point.y * (0.35 + warp * 0.8);
        moved.x += sin(scanTime * MOTION_TAU) * amount * 0.14;
    } else if (style < 33.5) {
        // Whip Pan
        float cycle = fract(phaseTime);
        float pulse = pow(max(sin(MOTION_PI * cycle), 0.0), 7.0);
        float signValue = motionHash(floor(phaseTime) + 91.0) > 0.5 ? 1.0 : -1.0;
        moved.x -= pulse * signValue * amount * (0.32 + warp * 0.26);
        moved.y += pulse * perpendicular.y * amount * 0.04;
    } else if (style < 34.5) {
        // Stop Motion
        float steppedTime = floor(phaseTime * steps) / steps;
        float steppedAngle = steppedTime * MOTION_TAU;
        moved -= vec2(sin(steppedAngle), cos(steppedAngle * 0.73))
            * amount * 0.17;
    } else if (style < 35.5) {
        // Step Jump
        float frameValue = floor(phaseTime * steps);
        vec2 jumpValue = vec2(
            motionHash(frameValue + 131.0),
            motionHash(frameValue + 271.0)
        ) * 2.0 - 1.0;
        moved -= jumpValue * amount * (0.08 + uRandomness * 0.18);
    } else if (style < 36.5) {
        // Conveyor
        moved -= direction * phaseTime * amount * 0.42;
        moved += perpendicular
            * sin(dot(point, perpendicular) * frequency * MOTION_TAU + angle)
            * amount * warp * 0.035;
    } else if (style < 37.5) {
        // Tunnel
        float tunnelAngle = atan(point.y, point.x) / MOTION_TAU;
        float tunnelDepth = 0.16 / max(radius, 0.025);
        vec2 tunnel = vec2(
            tunnelAngle + phaseTime * amount * 0.16,
            tunnelDepth + phaseTime * amount * 0.28
        );
        tunnel.x *= aspect;
        moved = tunnel - vec2(0.5 * aspect, 0.5);
    } else if (style < 38.5) {
        // Kaleidoscope Motion
        float segments = max(floor(uSegments + 0.5), 3.0);
        float segmentAngle = MOTION_TAU / segments;
        float polarAngle = atan(point.y, point.x) + angle * amount * 0.32;
        polarAngle = abs(mod(polarAngle + segmentAngle * 0.5, segmentAngle)
            - segmentAngle * 0.5);
        moved = vec2(cos(polarAngle), sin(polarAngle)) * radius;
    } else {
        // Elastic
        float cycle = fract(phaseTime);
        float elasticValue = sin(cycle * MOTION_TAU * 2.0)
            * exp(-cycle * 3.4);
        float scaleValue = 1.0 + elasticValue * amount * 0.55;
        moved = point / max(scaleValue, 0.12);
        moved -= direction * elasticValue * amount * 0.08;
    }

    moved.x /= aspect;
    return center + moved;
}

vec2 motionEdgeUV(vec2 uv, float edgeMode, out float coverage) {
    coverage = 1.0;
    if (edgeMode < 0.5) {
        return clamp(uv, 0.0, 1.0);
    }
    if (edgeMode < 1.5) {
        return fract(uv);
    }
    if (edgeMode < 2.5) {
        return vec2(1.0) - abs(mod(uv, vec2(2.0)) - vec2(1.0));
    }
    vec2 inside = step(vec2(0.0), uv) * step(uv, vec2(1.0));
    coverage = inside.x * inside.y;
    return clamp(uv, 0.0, 1.0);
}

vec4 motionSample(vec2 uv) {
    float coverage = 1.0;
    vec2 sampleUV = motionEdgeUV(uv, floor(uEdgeMode + 0.5), coverage);
    return texture(sTD2DInputs[0], sampleUV) * coverage;
}

void main() {
    vec2 uv = vUV.st;
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    vec2 resolution = vec2(max(sourceSize.x, 1), max(sourceSize.y, 1));
    vec4 source = texture(sTD2DInputs[0], uv);
    int requestedSamples = int(clamp(floor(uTrailSamples + 0.5), 1.0, 5.0));
    int sampleCount = uTrailAmount > 1.0e-5 ? requestedSamples : 1;
    vec4 accumulated = vec4(0.0);
    float totalWeight = 0.0;
    for (int sampleIndex = 0; sampleIndex < 5; ++sampleIndex) {
        if (sampleIndex >= sampleCount) {
            break;
        }
        float sampleRatio = sampleCount > 1
            ? float(sampleIndex) / float(sampleCount - 1)
            : 0.0;
        float sampleTime = uTime - sampleRatio * uTrailAmount * 0.35;
        vec2 movedUV = motionUV(
            floor(uStyle + 0.5),
            uv,
            resolution,
            sampleTime
        );
        float sampleWeight = 1.0 - sampleRatio * 0.55;
        accumulated += motionSample(movedUV) * sampleWeight;
        totalWeight += sampleWeight;
    }
    vec4 moved = accumulated / max(totalWeight, 1.0e-5);
    fragColor = TDOutputSwizzle(mix(source, moved, clamp(uMix, 0.0, 1.0)));
}
""".strip()

MOTION_STUDIO_PARAMETER_DEFINITIONS = (
    {
        "name": "Enabled", "label": "Module Enabled", "type": "toggle",
        "page": "Motion Studio", "default": True,
        "description": "Return the input unchanged when the entire motion module is disabled.",
    },
    {
        "name": "Style", "label": "Motion Style", "type": "menu",
        "page": "Motion Studio", "default": "drift",
        "menu_names": list(MOTION_STUDIO_STYLE_NAMES),
        "menu_labels": list(MOTION_STUDIO_STYLE_LABELS),
        "uniform": "uStyle",
        "description": "Choose one of forty movement, camera, warp, step, or spatial animation styles.",
    },
    {
        "name": "Mix", "label": "Motion Mix", "type": "float",
        "page": "Motion Studio", "default": 1.0,
        "min": 0.0, "max": 1.0, "uniform": "uMix",
        "description": "Blend continuously between the source and moved image.",
    },
    {
        "name": "Autotime", "label": "Auto Time", "type": "toggle",
        "page": "Timing", "default": True,
        "description": "Drive animation from TouchDesigner's absolute time.",
    },
    {
        "name": "Timescale", "label": "Time Scale", "type": "float",
        "page": "Timing", "default": 1.0,
        "min": -10.0, "max": 10.0,
        "description": "Scale, pause, or reverse automatic motion time.",
    },
    {
        "name": "Manualtime", "label": "Manual Time", "type": "float",
        "page": "Timing", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "description": "Set deterministic animation time when Auto Time is disabled.",
    },
    {
        "name": "Time", "label": "Effective Time", "type": "float",
        "page": "Timing", "default": 0.0,
        "min": -100000.0, "max": 100000.0,
        "uniform": "uTime", "animatable": False, "read_only": True,
        "description": "Resolved time sent to the motion shader.",
    },
    {
        "name": "Speed", "label": "Speed", "type": "float",
        "page": "Timing", "default": 0.7,
        "min": 0.0, "max": 10.0, "uniform": "uSpeed",
        "description": "Set the selected motion's temporal rate.",
    },
    {
        "name": "Phase", "label": "Phase", "type": "float",
        "page": "Timing", "default": 0.0,
        "min": -10.0, "max": 10.0, "uniform": "uPhase",
        "description": "Offset animation phase without changing speed.",
    },
    {
        "name": "Easing", "label": "Easing", "type": "menu",
        "page": "Timing", "default": "sine",
        "menu_names": list(MOTION_STUDIO_EASING_NAMES),
        "menu_labels": list(MOTION_STUDIO_EASING_LABELS),
        "uniform": "uEasing",
        "description": "Shape oscillating, stepped, and interpolated movement.",
    },
    {
        "name": "Steps", "label": "Animation Steps", "type": "int",
        "page": "Timing", "default": 12,
        "min": 2, "max": 120, "uniform": "uSteps",
        "description": "Set stop-motion, jitter, and step-jump temporal divisions.",
    },
    {
        "name": "Amount", "label": "Motion Amount", "type": "float",
        "page": "Transform", "default": 0.35,
        "min": 0.0, "max": 1.0, "uniform": "uAmount",
        "description": "Scale the main translation, rotation, zoom, or deformation.",
    },
    {
        "name": "Direction", "label": "Direction", "type": "xy",
        "page": "Transform", "default": [1.0, 0.25],
        "min": -1.0, "max": 1.0, "uniform": "uDirection",
        "description": "Set the primary normalized movement direction.",
    },
    {
        "name": "Center", "label": "Center / Pivot", "type": "uv",
        "page": "Transform", "default": [0.5, 0.5],
        "min": 0.0, "max": 1.0, "uniform": "uCenter",
        "description": "Set the pivot for orbit, scale, rotation, spiral, and radial motion.",
    },
    {
        "name": "Zoom", "label": "Base Zoom", "type": "float",
        "page": "Transform", "default": 1.0,
        "min": 0.25, "max": 4.0, "uniform": "uZoom",
        "description": "Apply a constant zoom before animated movement.",
    },
    {
        "name": "Rotation", "label": "Base Rotation (Degrees)", "type": "float",
        "page": "Transform", "default": 0.0,
        "min": -360.0, "max": 360.0, "uniform": "uRotation",
        "description": "Apply a constant rotation around Center before animation.",
    },
    {
        "name": "Frequency", "label": "Frequency", "type": "float",
        "page": "Deformation", "default": 3.0,
        "min": 0.1, "max": 30.0, "uniform": "uFrequency",
        "description": "Set wave density, random update rate, and spatial repetition.",
    },
    {
        "name": "Warp", "label": "Warp Strength", "type": "float",
        "page": "Deformation", "default": 0.65,
        "min": 0.0, "max": 2.0, "uniform": "uWarp",
        "description": "Scale secondary liquid, spiral, wave, perspective, and tunnel deformation.",
    },
    {
        "name": "Randomness", "label": "Randomness", "type": "float",
        "page": "Deformation", "default": 0.55,
        "min": 0.0, "max": 1.0, "uniform": "uRandomness",
        "description": "Control seeded shake, handheld, jitter, flow, and jump variation.",
    },
    {
        "name": "Seed", "label": "Random Seed", "type": "int",
        "page": "Deformation", "default": 73,
        "min": 0, "max": 100000, "uniform": "uSeed",
        "description": "Choose deterministic random movement decisions.",
    },
    {
        "name": "Segments", "label": "Kaleidoscope Segments", "type": "int",
        "page": "Deformation", "default": 8,
        "min": 3, "max": 32, "uniform": "uSegments",
        "description": "Set the number of mirrored wedges in Kaleidoscope Motion.",
    },
    {
        "name": "Edgemode", "label": "Edge Behavior", "type": "menu",
        "page": "Sampling", "default": "mirror",
        "menu_names": list(MOTION_STUDIO_EDGE_MODE_NAMES),
        "menu_labels": list(MOTION_STUDIO_EDGE_MODE_LABELS),
        "uniform": "uEdgeMode",
        "description": "Hold, repeat, mirror, or clear pixels moved beyond the source boundary.",
    },
    {
        "name": "Trailamount", "label": "Motion Trail", "type": "float",
        "page": "Sampling", "default": 0.0,
        "min": 0.0, "max": 1.0, "uniform": "uTrailAmount",
        "description": "Accumulate earlier motion samples for a bounded shutter trail.",
    },
    {
        "name": "Trailsamples", "label": "Trail Samples", "type": "int",
        "page": "Sampling", "default": 3,
        "min": 1, "max": 5, "uniform": "uTrailSamples",
        "description": "Use one to five samples; higher values increase GPU texture reads.",
    },
)

REFERENCE_PARTICLE_FIELD_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uMix;
uniform float uDensity;
uniform float uPointSize;
uniform float uThreshold;
uniform float uThresholdSoftness;
uniform float uSourceInfluence;
uniform float uFlowAmount;
uniform float uTurbulence;
uniform float uNoiseScale;
uniform float uSpeed;
uniform float uDepth;
uniform float uShimmer;
uniform float uSpread;
uniform float uOpacity;
uniform float uShape;
uniform float uPalette;
uniform float uSeed;
uniform float uBackgroundMix;
uniform vec4 uBackgroundColor;
uniform vec4 uLowColor;
uniform vec4 uMidColor;
uniform vec4 uHighColor;

const float TAU = 6.28318530718;

float particleFieldHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float particleFieldNoise(vec2 position) {
    vec2 cell = floor(position);
    vec2 local = fract(position);
    local = local * local * (3.0 - 2.0 * local);
    float a = particleFieldHash(cell);
    float b = particleFieldHash(cell + vec2(1.0, 0.0));
    float c = particleFieldHash(cell + vec2(0.0, 1.0));
    float d = particleFieldHash(cell + vec2(1.0, 1.0));
    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

float particleFieldFbm(vec2 position) {
    float value = 0.0;
    float weight = 0.55;
    for (int octave = 0; octave < 4; ++octave) {
        value += particleFieldNoise(position) * weight;
        position = position * 2.03 + vec2(17.1, 9.2);
        weight *= 0.48;
    }
    return value;
}

vec3 particleFieldPalette(float value, vec3 sourceColor, float palette) {
    vec3 gradient = value < 0.5
        ? mix(uLowColor.rgb, uMidColor.rgb, value * 2.0)
        : mix(uMidColor.rgb, uHighColor.rgb, (value - 0.5) * 2.0);
    if (palette < 0.5) {
        return sourceColor;
    }
    if (palette < 1.5) {
        return gradient;
    }
    if (palette < 2.5) {
        vec3 electric = vec3(
            0.16 + 0.18 * value,
            0.35 + 0.65 * value,
            0.78 + 0.22 * value
        );
        return mix(electric, uHighColor.rgb, smoothstep(0.72, 1.0, value));
    }
    vec3 phase = vec3(0.0, 0.33, 0.67);
    return 0.55 + 0.45 * cos(TAU * (value + phase));
}

float particleFieldShape(vec2 delta, float shape, float variation) {
    if (shape < 0.5) {
        return length(delta);
    }
    if (shape < 1.5) {
        return max(abs(delta.x), abs(delta.y));
    }
    vec2 spark = vec2(
        delta.x * mix(0.42, 0.72, variation),
        delta.y * mix(1.45, 2.10, variation)
    );
    return min(length(spark), length(spark.yx) * 1.18);
}

void main() {
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    float aspect = float(max(sourceSize.x, 1)) / float(max(sourceSize.y, 1));
    float columns = clamp(floor(uDensity + 0.5), 8.0, 500.0);
    vec2 grid = vec2(columns, max(4.0, columns / max(aspect, 0.01)));
    vec2 gridPosition = uv * grid;
    vec2 baseCell = floor(gridPosition);
    vec3 premultiplied = vec3(0.0);
    float accumulatedAlpha = 0.0;
    float animatedTime = uTime * max(uSpeed, 0.0);

    for (int offsetY = -2; offsetY <= 2; ++offsetY) {
        for (int offsetX = -2; offsetX <= 2; ++offsetX) {
            vec2 cell = baseCell + vec2(float(offsetX), float(offsetY));
            if (cell.x < 0.0 || cell.y < 0.0 || cell.x >= grid.x || cell.y >= grid.y) {
                continue;
            }
            float variation = particleFieldHash(cell + uSeed * vec2(3.17, 7.31));
            vec2 sourceUV = (cell + vec2(0.5)) / grid;
            vec4 particleSource = texture(sTD2DInputs[0], clamp(sourceUV, 0.0, 1.0));
            float luma = dot(particleSource.rgb, vec3(0.2126, 0.7152, 0.0722));
            float sourceSignal = mix(particleSource.a, luma, clamp(uSourceInfluence, 0.0, 1.0));
            float gate = smoothstep(
                uThreshold - max(uThresholdSoftness, 0.001),
                uThreshold + max(uThresholdSoftness, 0.001),
                sourceSignal
            );

            vec2 noisePosition = sourceUV * max(uNoiseScale, 0.01) + vec2(
                animatedTime * 0.19,
                -animatedTime * 0.13
            );
            float depthNoise = particleFieldFbm(noisePosition + uSeed * 0.071);
            float angle = TAU * particleFieldNoise(
                noisePosition * 1.37 + vec2(animatedTime * 0.11, uSeed)
            );
            vec2 flow = vec2(cos(angle), sin(angle));
            vec2 center = cell + vec2(0.5);
            center += flow * uFlowAmount * mix(0.35, 1.0, depthNoise);
            center += vec2(
                sin(animatedTime + variation * TAU),
                cos(animatedTime * 0.83 + variation * TAU)
            ) * uTurbulence;
            center += (vec2(
                particleFieldHash(cell + 13.7),
                particleFieldHash(cell + 41.3)
            ) - 0.5) * uSpread;

            vec2 delta = gridPosition - center;
            float size = max(0.025, uPointSize) * mix(0.62, 1.42, depthNoise * uDepth);
            float metric = particleFieldShape(delta, floor(uShape + 0.5), variation);
            float antialias = max(fwidth(metric), 0.008);
            float coverage = 1.0 - smoothstep(size - antialias, size + antialias, metric);
            if (coverage <= 0.0 || gate <= 0.0) {
                continue;
            }

            float shimmer = mix(
                1.0,
                0.58 + 0.72 * sin(animatedTime * 3.1 + variation * TAU),
                clamp(uShimmer, 0.0, 1.0)
            );
            float palettePosition = clamp(
                0.58 * luma + 0.42 * depthNoise + 0.12 * sin(animatedTime + variation * TAU),
                0.0,
                1.0
            );
            vec3 particleColor = particleFieldPalette(
                palettePosition,
                particleSource.rgb,
                floor(uPalette + 0.5)
            );
            float paletteAlpha = palettePosition < 0.5
                ? mix(uLowColor.a, uMidColor.a, palettePosition * 2.0)
                : mix(uMidColor.a, uHighColor.a, (palettePosition - 0.5) * 2.0);
            float layerAlpha = clamp(
                coverage * gate * particleSource.a * uOpacity * shimmer * paletteAlpha,
                0.0,
                1.0
            );
            premultiplied = particleColor * layerAlpha + premultiplied * (1.0 - layerAlpha);
            accumulatedAlpha = layerAlpha + accumulatedAlpha * (1.0 - layerAlpha);
        }
    }

    vec3 particleColor = accumulatedAlpha > 0.00001
        ? premultiplied / accumulatedAlpha
        : vec3(0.0);
    vec3 background = mix(source.rgb, uBackgroundColor.rgb, clamp(uBackgroundMix, 0.0, 1.0));
    vec3 effected = particleColor * accumulatedAlpha + background * (1.0 - accumulatedAlpha);
    float effectAlpha = max(source.a * (1.0 - uBackgroundMix), accumulatedAlpha);
    vec4 result = vec4(effected, max(effectAlpha, uBackgroundColor.a * uBackgroundMix));
    fragColor = TDOutputSwizzle(mix(source, result, clamp(uMix, 0.0, 1.0)));
}
""".strip()

REFERENCE_PARTICLE_FIELD_PARAMETER_DEFINITIONS = (
    {"name": "Enabled", "label": "Module Enabled", "type": "toggle", "page": "Particle Field", "default": True, "description": "Bypass the complete chromatic particle-field treatment."},
    {"name": "Mix", "label": "Effect Mix", "type": "float", "page": "Particle Field", "default": 1.0, "min": 0.0, "max": 1.0, "uniform": "uMix", "description": "Blend between the source and particle-field result."},
    {"name": "Autotime", "label": "Auto Time", "type": "toggle", "page": "Timing", "default": True, "description": "Animate from TouchDesigner's absolute time."},
    {"name": "Timescale", "label": "Time Scale", "type": "float", "page": "Timing", "default": 1.0, "min": -10.0, "max": 10.0, "description": "Scale or reverse automatic animation time."},
    {"name": "Manualtime", "label": "Manual Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "description": "Set deterministic time when Auto Time is disabled."},
    {"name": "Time", "label": "Effective Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "uniform": "uTime", "animatable": False, "read_only": True, "description": "Resolved shader time."},
    {"name": "Speed", "label": "Flow Speed", "type": "float", "page": "Timing", "default": 0.42, "min": 0.0, "max": 5.0, "uniform": "uSpeed", "description": "Set particle-field animation speed."},
    {"name": "Density", "label": "Particle Columns", "type": "int", "page": "Particles", "default": 180, "min": 8, "max": 500, "uniform": "uDensity", "description": "Set particle columns; rows follow source aspect ratio."},
    {"name": "Pointsize", "label": "Point Size", "type": "float", "page": "Particles", "default": 0.38, "min": 0.03, "max": 1.25, "uniform": "uPointSize", "description": "Set point radius relative to a grid cell."},
    {"name": "Threshold", "label": "Source Threshold", "type": "float", "page": "Particles", "default": 0.10, "min": 0.0, "max": 1.0, "uniform": "uThreshold", "description": "Suppress particles below the selected source signal."},
    {"name": "Thresholdsoftness", "label": "Threshold Softness", "type": "float", "page": "Particles", "default": 0.16, "min": 0.001, "max": 0.5, "uniform": "uThresholdSoftness", "description": "Soften particle appearance around the threshold."},
    {"name": "Sourceinfluence", "label": "Luminance Influence", "type": "float", "page": "Particles", "default": 0.72, "min": 0.0, "max": 1.0, "uniform": "uSourceInfluence", "description": "Blend alpha and luminance when distributing points."},
    {"name": "Shape", "label": "Point Shape", "type": "menu", "page": "Particles", "default": "round", "menu_names": ["round", "square", "spark"], "menu_labels": ["Round Point", "Square Pixel", "Vertical Spark"], "uniform": "uShape", "description": "Choose round, square, or luminous spark points."},
    {"name": "Flowamount", "label": "Flow Amount", "type": "float", "page": "Flow", "default": 0.62, "min": 0.0, "max": 1.25, "uniform": "uFlowAmount", "description": "Move points through the procedural vector field."},
    {"name": "Turbulence", "label": "Turbulence", "type": "float", "page": "Flow", "default": 0.20, "min": 0.0, "max": 0.75, "uniform": "uTurbulence", "description": "Add local oscillation to particle movement."},
    {"name": "Noisescale", "label": "Noise Scale", "type": "float", "page": "Flow", "default": 4.6, "min": 0.1, "max": 24.0, "uniform": "uNoiseScale", "description": "Set the scale of the turbulent flow field."},
    {"name": "Depth", "label": "Depth Variation", "type": "float", "page": "Flow", "default": 0.78, "min": 0.0, "max": 1.0, "uniform": "uDepth", "description": "Vary point size to suggest volumetric depth."},
    {"name": "Shimmer", "label": "Shimmer", "type": "float", "page": "Flow", "default": 0.48, "min": 0.0, "max": 1.0, "uniform": "uShimmer", "description": "Animate point brightness independently."},
    {"name": "Spread", "label": "Random Spread", "type": "float", "page": "Flow", "default": 0.32, "min": 0.0, "max": 1.25, "uniform": "uSpread", "description": "Scatter point centers with a deterministic seed."},
    {"name": "Opacity", "label": "Particle Opacity", "type": "float", "page": "Color", "default": 0.94, "min": 0.0, "max": 1.0, "uniform": "uOpacity", "description": "Control total point-field opacity."},
    {"name": "Palette", "label": "Color Palette", "type": "menu", "page": "Color", "default": "electric_blue", "menu_names": ["source", "custom_gradient", "electric_blue", "prismatic"], "menu_labels": ["Source Color", "Custom Gradient", "Electric Blue", "Prismatic"], "uniform": "uPalette", "description": "Choose source, custom, electric-blue, or prismatic color."},
    {"name": "Backgroundmix", "label": "Background Replacement", "type": "float", "page": "Color", "default": 0.92, "min": 0.0, "max": 1.0, "uniform": "uBackgroundMix", "description": "Blend the source background toward Background Color."},
    {"name": "Backgroundcolor", "label": "Background Color", "type": "rgba", "page": "Color", "default": [0.002, 0.006, 0.018, 1.0], "uniform": "uBackgroundColor", "description": "Set the field background and alpha."},
    {"name": "Lowcolor", "label": "Low Color", "type": "rgba", "page": "Color", "default": [0.015, 0.05, 0.22, 1.0], "uniform": "uLowColor", "description": "Set the custom-gradient shadow color."},
    {"name": "Midcolor", "label": "Middle Color", "type": "rgba", "page": "Color", "default": [0.02, 0.42, 1.0, 1.0], "uniform": "uMidColor", "description": "Set the custom-gradient middle color."},
    {"name": "Highcolor", "label": "Highlight Color", "type": "rgba", "page": "Color", "default": [0.80, 0.96, 1.0, 1.0], "uniform": "uHighColor", "description": "Set the custom-gradient highlight color."},
    {"name": "Seed", "label": "Random Seed", "type": "int", "page": "Flow", "default": 41, "min": 0, "max": 100000, "uniform": "uSeed", "description": "Choose deterministic particle placement and flow."},
)

CALLIGRAPHIC_SHADOW_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uMix;
uniform float uMaskMode;
uniform float uThreshold;
uniform float uSoftness;
uniform float uSourceOpacity;
uniform float uPaperAmount;
uniform float uShadowOpacity;
uniform vec2 uOffset;
uniform float uStretch;
uniform float uCurl;
uniform float uTurbulence;
uniform float uNoiseScale;
uniform float uSpeed;
uniform float uStrokeWeight;
uniform float uTrailLength;
uniform float uTrailSamples;
uniform float uDiffusion;
uniform float uDryBrush;
uniform float uSplatter;
uniform float uSeed;
uniform vec4 uInkColor;
uniform vec4 uPaperColor;

float calligraphyHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float calligraphyNoise(vec2 position) {
    vec2 cell = floor(position);
    vec2 local = fract(position);
    local = local * local * (3.0 - 2.0 * local);
    float a = calligraphyHash(cell);
    float b = calligraphyHash(cell + vec2(1.0, 0.0));
    float c = calligraphyHash(cell + vec2(0.0, 1.0));
    float d = calligraphyHash(cell + vec2(1.0, 1.0));
    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

float calligraphyRawMask(vec2 uv) {
    vec4 sampleColor = texture(sTD2DInputs[0], clamp(uv, 0.0, 1.0));
    float luma = dot(sampleColor.rgb, vec3(0.2126, 0.7152, 0.0722));
    float signal = uMaskMode < 0.5
        ? 1.0 - luma
        : (uMaskMode < 1.5 ? luma : sampleColor.a);
    return smoothstep(
        uThreshold - max(uSoftness, 0.001),
        uThreshold + max(uSoftness, 0.001),
        signal
    );
}

float calligraphyExpandedMask(vec2 uv, vec2 texel, float radius) {
    vec2 offsetX = vec2(texel.x * radius, 0.0);
    vec2 offsetY = vec2(0.0, texel.y * radius);
    float mask = calligraphyRawMask(uv);
    mask = max(mask, calligraphyRawMask(uv + offsetX));
    mask = max(mask, calligraphyRawMask(uv - offsetX));
    mask = max(mask, calligraphyRawMask(uv + offsetY));
    mask = max(mask, calligraphyRawMask(uv - offsetY));
    return mask;
}

void main() {
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    vec2 resolution = vec2(max(sourceSize.x, 1), max(sourceSize.y, 1));
    vec2 texel = 1.0 / resolution;
    float animatedTime = uTime * max(uSpeed, 0.0);
    int requestedSamples = int(clamp(floor(uTrailSamples + 0.5), 1.0, 8.0));
    float trailMask = 0.0;

    for (int sampleIndex = 0; sampleIndex < 8; ++sampleIndex) {
        if (sampleIndex >= requestedSamples) {
            break;
        }
        float ratio = requestedSamples > 1
            ? float(sampleIndex) / float(requestedSamples - 1)
            : 0.0;
        float trailRatio = 0.10 + ratio * max(uTrailLength, 0.0);
        vec2 noisePosition = uv * max(uNoiseScale, 0.01)
            + vec2(animatedTime * 0.17, -animatedTime * 0.11)
            + uSeed * 0.013;
        float flowNoise = calligraphyNoise(noisePosition + ratio * 7.3) - 0.5;
        float curlPhase = animatedTime + ratio * 5.0 + uv.y * 6.28318530718;
        vec2 curlOffset = vec2(
            sin(curlPhase + flowNoise * 4.0),
            cos(curlPhase * 0.73 - flowNoise * 3.0)
        ) * uCurl * trailRatio;
        vec2 displacement = uOffset * trailRatio * uStretch;
        displacement += curlOffset;
        displacement += vec2(flowNoise, -flowNoise * 0.55) * uTurbulence * trailRatio;
        float radius = uStrokeWeight * mix(0.45, 1.25, ratio);
        float mask = calligraphyExpandedMask(uv - displacement, texel, radius);
        float weight = (1.0 - ratio * 0.62) * uShadowOpacity;
        trailMask = max(trailMask, mask * weight);
    }

    float currentMask = calligraphyExpandedMask(uv, texel, uStrokeWeight * 0.45);
    float wetNoise = calligraphyNoise(
        uv * max(uNoiseScale, 0.01) * mix(4.0, 16.0, uDryBrush)
        + vec2(uSeed, animatedTime * 0.07)
    );
    float diffusion = smoothstep(
        0.0,
        max(0.001, 1.0 - uDiffusion * 0.72),
        trailMask
    );
    float dryPattern = mix(1.0, smoothstep(0.18, 0.82, wetNoise), uDryBrush);
    float splatterGate = step(
        1.0 - clamp(uSplatter, 0.0, 1.0) * trailMask * 0.32,
        calligraphyHash(floor(uv * resolution * 0.55) + floor(animatedTime * 3.0))
    );
    float inkMask = clamp(diffusion * dryPattern + splatterGate * 0.72, 0.0, 1.0);

    vec3 paper = mix(source.rgb, uPaperColor.rgb, clamp(uPaperAmount * uPaperColor.a, 0.0, 1.0));
    vec3 inked = mix(paper, uInkColor.rgb, inkMask * uInkColor.a);
    vec3 subject = mix(inked, source.rgb, clamp(currentMask * uSourceOpacity, 0.0, 1.0));
    float resultAlpha = max(source.a * (1.0 - uPaperAmount), uPaperColor.a * uPaperAmount);
    vec4 result = vec4(subject, resultAlpha);
    fragColor = TDOutputSwizzle(mix(source, result, clamp(uMix, 0.0, 1.0)));
}
""".strip()

CALLIGRAPHIC_SHADOW_PARAMETER_DEFINITIONS = (
    {"name": "Enabled", "label": "Module Enabled", "type": "toggle", "page": "Calligraphic Shadow", "default": True, "description": "Bypass the complete calligraphic shadow treatment."},
    {"name": "Mix", "label": "Effect Mix", "type": "float", "page": "Calligraphic Shadow", "default": 1.0, "min": 0.0, "max": 1.0, "uniform": "uMix", "description": "Blend between the source and calligraphic result."},
    {"name": "Autotime", "label": "Auto Time", "type": "toggle", "page": "Timing", "default": True, "description": "Animate the flowing brush deformation automatically."},
    {"name": "Timescale", "label": "Time Scale", "type": "float", "page": "Timing", "default": 1.0, "min": -10.0, "max": 10.0, "description": "Scale or reverse automatic animation time."},
    {"name": "Manualtime", "label": "Manual Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "description": "Set deterministic time when Auto Time is disabled."},
    {"name": "Time", "label": "Effective Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "uniform": "uTime", "animatable": False, "read_only": True, "description": "Resolved shader time."},
    {"name": "Speed", "label": "Ink Motion Speed", "type": "float", "page": "Timing", "default": 0.36, "min": 0.0, "max": 5.0, "uniform": "uSpeed", "description": "Set the temporal rate of ink deformation."},
    {"name": "Maskmode", "label": "Subject Mask", "type": "menu", "page": "Subject", "default": "dark", "menu_names": ["dark", "light", "alpha"], "menu_labels": ["Dark Luminance", "Light Luminance", "Source Alpha"], "uniform": "uMaskMode", "description": "Extract a dark, light, or alpha-defined subject."},
    {"name": "Threshold", "label": "Mask Threshold", "type": "float", "page": "Subject", "default": 0.38, "min": 0.0, "max": 1.0, "uniform": "uThreshold", "description": "Set the subject extraction threshold."},
    {"name": "Softness", "label": "Mask Softness", "type": "float", "page": "Subject", "default": 0.12, "min": 0.001, "max": 0.5, "uniform": "uSoftness", "description": "Soften the extracted subject edge."},
    {"name": "Sourceopacity", "label": "Subject Visibility", "type": "float", "page": "Subject", "default": 1.0, "min": 0.0, "max": 1.0, "uniform": "uSourceOpacity", "description": "Composite the original subject above its ink shadow."},
    {"name": "Paperamount", "label": "Paper Replacement", "type": "float", "page": "Subject", "default": 0.86, "min": 0.0, "max": 1.0, "uniform": "uPaperAmount", "description": "Replace the source background with the paper color."},
    {"name": "Shadowopacity", "label": "Ink Shadow Opacity", "type": "float", "page": "Shadow Flow", "default": 0.96, "min": 0.0, "max": 1.0, "uniform": "uShadowOpacity", "description": "Set the calligraphic shadow density."},
    {"name": "Offset", "label": "Shadow Direction", "type": "xy", "page": "Shadow Flow", "default": [-0.18, 0.04], "min": -1.0, "max": 1.0, "uniform": "uOffset", "description": "Set the principal ink-shadow direction."},
    {"name": "Stretch", "label": "Shadow Stretch", "type": "float", "page": "Shadow Flow", "default": 1.35, "min": 0.0, "max": 4.0, "uniform": "uStretch", "description": "Stretch the subject into long calligraphic gestures."},
    {"name": "Curl", "label": "Brush Curl", "type": "float", "page": "Shadow Flow", "default": 0.055, "min": 0.0, "max": 0.35, "uniform": "uCurl", "description": "Curl the shadow path into brush-like arcs."},
    {"name": "Turbulence", "label": "Flow Turbulence", "type": "float", "page": "Shadow Flow", "default": 0.11, "min": 0.0, "max": 0.5, "uniform": "uTurbulence", "description": "Add seeded fluid irregularity to the shadow."},
    {"name": "Noisescale", "label": "Flow Scale", "type": "float", "page": "Shadow Flow", "default": 3.8, "min": 0.1, "max": 24.0, "uniform": "uNoiseScale", "description": "Set the spatial scale of shadow deformation."},
    {"name": "Strokeweight", "label": "Stroke Weight", "type": "float", "page": "Ink Surface", "default": 2.4, "min": 0.0, "max": 12.0, "uniform": "uStrokeWeight", "description": "Expand the source silhouette into heavier brush marks."},
    {"name": "Traillength", "label": "Trail Length", "type": "float", "page": "Ink Surface", "default": 1.0, "min": 0.0, "max": 2.0, "uniform": "uTrailLength", "description": "Scale the total calligraphic shadow extent."},
    {"name": "Trailsamples", "label": "Trail Samples", "type": "int", "page": "Ink Surface", "default": 7, "min": 1, "max": 8, "uniform": "uTrailSamples", "description": "Use one to eight bounded silhouette samples."},
    {"name": "Diffusion", "label": "Wet Diffusion", "type": "float", "page": "Ink Surface", "default": 0.34, "min": 0.0, "max": 1.0, "uniform": "uDiffusion", "description": "Soften and pool the calligraphic pigment."},
    {"name": "Drybrush", "label": "Dry Brush", "type": "float", "page": "Ink Surface", "default": 0.24, "min": 0.0, "max": 1.0, "uniform": "uDryBrush", "description": "Break the ink into dry-brush fibers."},
    {"name": "Splatter", "label": "Ink Splatter", "type": "float", "page": "Ink Surface", "default": 0.16, "min": 0.0, "max": 1.0, "uniform": "uSplatter", "description": "Add sparse deterministic ink droplets near the shadow."},
    {"name": "Inkcolor", "label": "Ink Color", "type": "rgba", "page": "Palette", "default": [0.008, 0.012, 0.010, 1.0], "uniform": "uInkColor", "description": "Set shadow pigment color and alpha."},
    {"name": "Papercolor", "label": "Paper Color", "type": "rgba", "page": "Palette", "default": [0.78, 0.88, 0.82, 1.0], "uniform": "uPaperColor", "description": "Set the minimal background color and alpha."},
    {"name": "Seed", "label": "Random Seed", "type": "int", "page": "Ink Surface", "default": 53, "min": 0, "max": 100000, "uniform": "uSeed", "description": "Choose deterministic brush fibers and splatter."},
)

INK_ORBIT_CANVAS_SHADER = r"""
layout(location = 0) out vec4 fragColor;

uniform float uTime;
uniform float uMix;
uniform float uSourceMix;
uniform float uSourceInfluence;
uniform float uRingCount;
uniform float uDropletCount;
uniform float uRadius;
uniform float uStrokeWidth;
uniform float uScale;
uniform vec2 uCenter;
uniform float uPerspective;
uniform float uOrbitSpeed;
uniform float uFlowSpeed;
uniform float uIrregularity;
uniform float uSwirl;
uniform float uStretch;
uniform float uDiffusion;
uniform float uDryBrush;
uniform float uSplatter;
uniform float uShadowAmount;
uniform vec2 uShadowOffset;
uniform float uShadowSoftness;
uniform float uSeed;
uniform vec4 uInkColor;
uniform vec4 uPaperColor;

const float TAU = 6.28318530718;

float inkOrbitHash(vec2 value) {
    vec3 p3 = fract(vec3(value.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float inkOrbitNoise(vec2 position) {
    vec2 cell = floor(position);
    vec2 local = fract(position);
    local = local * local * (3.0 - 2.0 * local);
    float a = inkOrbitHash(cell);
    float b = inkOrbitHash(cell + vec2(1.0, 0.0));
    float c = inkOrbitHash(cell + vec2(0.0, 1.0));
    float d = inkOrbitHash(cell + vec2(1.0, 1.0));
    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
}

vec2 inkOrbitSpace(vec2 uv, float aspect) {
    vec2 p = uv - uCenter;
    p.x *= aspect;
    p.y /= mix(1.0, 0.42, clamp(uPerspective, 0.0, 1.0));
    p /= max(uScale, 0.05);
    return p;
}

vec2 inkOrbitCenter(float index, float timeValue) {
    float randomPhase = inkOrbitHash(vec2(index, uSeed)) * TAU;
    float orbit = timeValue * uOrbitSpeed * mix(-1.0, 1.0, step(0.5, inkOrbitHash(vec2(index + 8.0, uSeed))));
    float radial = uRadius * mix(0.12, 0.92, inkOrbitHash(vec2(index + 21.0, uSeed)));
    return vec2(cos(randomPhase + orbit), sin(randomPhase + orbit)) * radial;
}

float inkOrbitRing(vec2 p, float index, float timeValue, float softness) {
    vec2 center = inkOrbitCenter(index, timeValue);
    vec2 q = p - center;
    float phase = inkOrbitHash(vec2(index + 31.0, uSeed)) * TAU;
    float angle = atan(q.y, q.x);
    float irregular = sin(angle * mix(2.0, 7.0, inkOrbitHash(vec2(index, 17.0))) + phase + timeValue * uFlowSpeed);
    irregular += (inkOrbitNoise(q * 8.0 + vec2(timeValue * 0.19, index)) - 0.5) * 1.4;
    float localRadius = uRadius * mix(0.16, 0.48, inkOrbitHash(vec2(index + 43.0, uSeed)));
    localRadius *= 1.0 + irregular * uIrregularity * 0.32;
    q.x *= mix(1.0, 1.85, uStretch * inkOrbitHash(vec2(index + 5.0, uSeed)));
    q += vec2(-q.y, q.x) * uSwirl * 0.12 * sin(timeValue + phase);
    float distanceToStroke = abs(length(q) - localRadius);
    float width = max(0.001, uStrokeWidth * mix(0.52, 1.45, inkOrbitHash(vec2(index + 71.0, uSeed))));
    return 1.0 - smoothstep(width, width + softness, distanceToStroke);
}

float inkOrbitDroplet(vec2 p, float index, float timeValue, float softness) {
    float phase = inkOrbitHash(vec2(index + 91.0, uSeed)) * TAU;
    float travel = fract(timeValue * uFlowSpeed * 0.035 + inkOrbitHash(vec2(index, uSeed)));
    vec2 position = vec2(
        mix(-0.72, 0.72, inkOrbitHash(vec2(index + 11.0, uSeed))),
        mix(-0.46, 0.46, travel)
    );
    position += vec2(cos(phase + timeValue * 0.23), sin(phase * 1.7 + timeValue * 0.31)) * uSwirl * 0.18;
    vec2 q = p - position;
    q.x *= mix(0.62, 1.55, inkOrbitHash(vec2(index + 37.0, uSeed)));
    float radius = uStrokeWidth * mix(0.35, 2.4, inkOrbitHash(vec2(index + 57.0, uSeed)));
    return 1.0 - smoothstep(radius, radius + softness, length(q));
}

void main() {
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    ivec2 sourceSize = textureSize(sTD2DInputs[0], 0);
    float aspect = float(max(sourceSize.x, 1)) / float(max(sourceSize.y, 1));
    vec2 p = inkOrbitSpace(uv, aspect);
    float timeValue = uTime;
    int ringCount = int(clamp(floor(uRingCount + 0.5), 1.0, 12.0));
    int dropletCount = int(clamp(floor(uDropletCount + 0.5), 0.0, 24.0));
    float softness = mix(0.0008, 0.035, clamp(uDiffusion, 0.0, 1.0));
    float ink = 0.0;
    float shadow = 0.0;

    for (int index = 0; index < 12; ++index) {
        if (index >= ringCount) {
            break;
        }
        float ring = inkOrbitRing(p, float(index), timeValue, softness);
        float shadowRing = inkOrbitRing(
            p - uShadowOffset,
            float(index),
            timeValue,
            softness + uShadowSoftness * 0.05
        );
        ink = max(ink, ring);
        shadow = max(shadow, shadowRing);
    }
    for (int index = 0; index < 24; ++index) {
        if (index >= dropletCount) {
            break;
        }
        float droplet = inkOrbitDroplet(p, float(index), timeValue, softness);
        float shadowDroplet = inkOrbitDroplet(
            p - uShadowOffset,
            float(index),
            timeValue,
            softness + uShadowSoftness * 0.05
        );
        ink = max(ink, droplet);
        shadow = max(shadow, shadowDroplet);
    }

    float sourceLuma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float sourceModulation = mix(1.0, 0.35 + 0.95 * (1.0 - sourceLuma), uSourceInfluence);
    float fibers = inkOrbitNoise(uv * mix(160.0, 920.0, uDryBrush) + uSeed);
    ink *= mix(1.0, smoothstep(0.16, 0.84, fibers), uDryBrush);
    float splatter = step(
        1.0 - clamp(uSplatter, 0.0, 1.0) * ink * 0.28,
        inkOrbitHash(floor(uv * vec2(sourceSize)) + floor(timeValue * 2.0))
    );
    ink = clamp(ink * sourceModulation + splatter * 0.68, 0.0, 1.0);
    shadow = clamp(shadow * uShadowAmount * (1.0 - ink), 0.0, 1.0);

    vec3 canvas = mix(uPaperColor.rgb, vec3(0.0), shadow * 0.30);
    canvas = mix(canvas, uInkColor.rgb, ink * uInkColor.a);
    canvas = mix(canvas, source.rgb, clamp(uSourceMix * source.a, 0.0, 1.0));
    vec4 result = vec4(canvas, max(uPaperColor.a, source.a * uSourceMix));
    fragColor = TDOutputSwizzle(mix(source, result, clamp(uMix, 0.0, 1.0)));
}
""".strip()

INK_ORBIT_CANVAS_PARAMETER_DEFINITIONS = (
    {"name": "Enabled", "label": "Module Enabled", "type": "toggle", "page": "Ink Orbit Canvas", "default": True, "description": "Bypass the complete procedural ink-orbit canvas."},
    {"name": "Mix", "label": "Effect Mix", "type": "float", "page": "Ink Orbit Canvas", "default": 1.0, "min": 0.0, "max": 1.0, "uniform": "uMix", "description": "Blend between the source and ink-orbit canvas."},
    {"name": "Sourcemix", "label": "Source Visibility", "type": "float", "page": "Ink Orbit Canvas", "default": 0.0, "min": 0.0, "max": 1.0, "uniform": "uSourceMix", "description": "Composite the original image over the generated canvas."},
    {"name": "Sourceinfluence", "label": "Source Influence", "type": "float", "page": "Ink Orbit Canvas", "default": 0.22, "min": 0.0, "max": 1.0, "uniform": "uSourceInfluence", "description": "Use source luminance to vary pigment density."},
    {"name": "Autotime", "label": "Auto Time", "type": "toggle", "page": "Timing", "default": True, "description": "Animate rings and droplets automatically."},
    {"name": "Timescale", "label": "Time Scale", "type": "float", "page": "Timing", "default": 1.0, "min": -10.0, "max": 10.0, "description": "Scale or reverse automatic animation time."},
    {"name": "Manualtime", "label": "Manual Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "description": "Set deterministic time when Auto Time is disabled."},
    {"name": "Time", "label": "Effective Time", "type": "float", "page": "Timing", "default": 0.0, "min": -100000.0, "max": 100000.0, "uniform": "uTime", "animatable": False, "read_only": True, "description": "Resolved shader time."},
    {"name": "Orbitspeed", "label": "Orbit Speed", "type": "float", "page": "Timing", "default": 0.24, "min": -5.0, "max": 5.0, "uniform": "uOrbitSpeed", "description": "Set ring-center orbital movement."},
    {"name": "Flowspeed", "label": "Ink Flow Speed", "type": "float", "page": "Timing", "default": 0.48, "min": -5.0, "max": 5.0, "uniform": "uFlowSpeed", "description": "Set brush undulation and droplet travel speed."},
    {"name": "Ringcount", "label": "Ring Count", "type": "int", "page": "Geometry", "default": 7, "min": 1, "max": 12, "uniform": "uRingCount", "description": "Draw one to twelve flowing calligraphic rings."},
    {"name": "Dropletcount", "label": "Droplet Count", "type": "int", "page": "Geometry", "default": 12, "min": 0, "max": 24, "uniform": "uDropletCount", "description": "Draw zero to twenty-four animated pigment droplets."},
    {"name": "Radius", "label": "Orbit Radius", "type": "float", "page": "Geometry", "default": 0.34, "min": 0.03, "max": 1.0, "uniform": "uRadius", "description": "Set ring size and orbit extent."},
    {"name": "Strokewidth", "label": "Stroke Width", "type": "float", "page": "Geometry", "default": 0.022, "min": 0.001, "max": 0.18, "uniform": "uStrokeWidth", "description": "Set wet calligraphic stroke width."},
    {"name": "Scale", "label": "Canvas Scale", "type": "float", "page": "Geometry", "default": 1.0, "min": 0.1, "max": 4.0, "uniform": "uScale", "description": "Scale the complete orbit composition."},
    {"name": "Center", "label": "Canvas Center", "type": "uv", "page": "Geometry", "default": [0.5, 0.48], "min": 0.0, "max": 1.0, "uniform": "uCenter", "description": "Position the ink composition in the frame."},
    {"name": "Perspective", "label": "Floor Perspective", "type": "float", "page": "Geometry", "default": 0.54, "min": 0.0, "max": 1.0, "uniform": "uPerspective", "description": "Compress the composition vertically like a stage floor."},
    {"name": "Irregularity", "label": "Ring Irregularity", "type": "float", "page": "Flow", "default": 0.72, "min": 0.0, "max": 1.0, "uniform": "uIrregularity", "description": "Break perfect circles into hand-drawn ink contours."},
    {"name": "Swirl", "label": "Swirl", "type": "float", "page": "Flow", "default": 0.62, "min": 0.0, "max": 2.0, "uniform": "uSwirl", "description": "Curl ring centers and flowing droplets."},
    {"name": "Stretch", "label": "Stroke Stretch", "type": "float", "page": "Flow", "default": 0.58, "min": 0.0, "max": 1.0, "uniform": "uStretch", "description": "Stretch selected rings into brush loops."},
    {"name": "Diffusion", "label": "Wet Diffusion", "type": "float", "page": "Surface", "default": 0.36, "min": 0.0, "max": 1.0, "uniform": "uDiffusion", "description": "Soften ink edges like pigment spreading through paper."},
    {"name": "Drybrush", "label": "Dry Brush", "type": "float", "page": "Surface", "default": 0.20, "min": 0.0, "max": 1.0, "uniform": "uDryBrush", "description": "Reveal paper fibers through broken strokes."},
    {"name": "Splatter", "label": "Splatter", "type": "float", "page": "Surface", "default": 0.18, "min": 0.0, "max": 1.0, "uniform": "uSplatter", "description": "Add sparse animated ink droplets along strokes."},
    {"name": "Shadowamount", "label": "Wet Shadow", "type": "float", "page": "Surface", "default": 0.38, "min": 0.0, "max": 1.0, "uniform": "uShadowAmount", "description": "Add a soft offset shadow beneath wet pigment."},
    {"name": "Shadowoffset", "label": "Shadow Offset", "type": "xy", "page": "Surface", "default": [0.018, -0.025], "min": -0.2, "max": 0.2, "uniform": "uShadowOffset", "description": "Set the wet-pigment shadow direction."},
    {"name": "Shadowsoftness", "label": "Shadow Softness", "type": "float", "page": "Surface", "default": 0.42, "min": 0.0, "max": 1.0, "uniform": "uShadowSoftness", "description": "Diffuse the wet-pigment shadow."},
    {"name": "Inkcolor", "label": "Ink Color", "type": "rgba", "page": "Palette", "default": [0.006, 0.008, 0.007, 1.0], "uniform": "uInkColor", "description": "Set the calligraphic pigment color and alpha."},
    {"name": "Papercolor", "label": "Paper Color", "type": "rgba", "page": "Palette", "default": [0.94, 0.95, 0.92, 1.0], "uniform": "uPaperColor", "description": "Set the canvas color and alpha."},
    {"name": "Seed", "label": "Random Seed", "type": "int", "page": "Flow", "default": 67, "min": 0, "max": 100000, "uniform": "uSeed", "description": "Choose deterministic ring layout, fibers, and droplets."},
)

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
        if "read_only" in definition:
            try:
                par.readOnly = bool(definition["read_only"])
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


def _repair_effect_state_paths(root_comp):
    """Repair legacy absolute Feedback TOP targets in stateful packages."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "history_feedback":
            continue
        target = operator.parent().op("state_target")
        parameter = operator.par["top"]
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable state target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} Feedback TOP target did not resolve".format(operator.path)
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
    _repair_effect_state_paths(instance)
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
        effect.store("tdimagefx_history_seed", effect.relativePath(history_seed))

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
        history.par.top = history.relativePath(state_target)

        render_output = effect.create(nullTOP, "render_output")
        display_source.outputConnectors[0].connect(render_output.inputConnectors[0])
        render_output.nodeX = len(glsl_nodes) * 230
        render_output.nodeY = 30
        render_output.display = False
        render_output.render = False
        processed_output = render_output
        effect.store("tdimagefx_state_target", effect.relativePath(state_target))
        effect.store("tdimagefx_render_output", effect.relativePath(render_output))

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
    _append_parameter(rack, page, {"name": "Time", "label": "Effective Time", "type": "float", "default": 0.0, "min": -100000.0, "max": 100000.0, "read_only": True, "animatable": False})
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


def build_particle_module(parent_comp):
    """Build the reusable, GPU-only random-move particle module."""

    particles = parent_comp.create(baseCOMP, "particle_random_move")
    particles.color = (0.52, 0.24, 0.10)
    particles.comment = (
        "GPU random-move image particles. Use the demo routing toggles to "
        "choose particles and optional video effects."
    )
    pages = {}
    parameter_bindings = []
    for definition in PARTICLE_PARAMETER_DEFINITIONS:
        page_name = definition.get("page", "Particles")
        page = pages.get(page_name)
        if page is None:
            page = particles.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(particles, page, definition)
        parameter_bindings.append((definition, custom_pars))
    particles.par.Time.expr = (
        "absTime.seconds * me.par.Timescale "
        "if me.par.Autotime else me.par.Manualtime"
    )
    particles.store(
        "tdimagefx_particle_module",
        {
            "schema_version": 1,
            "id": "tdimagefx.core.particle-random-move",
            "renderer": "bounded_glsl_top",
            "video_fx_routing": "external_optional",
        },
    )

    source = particles.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -420
    source.nodeY = 0

    shader_dat = particles.create(textDAT, "pixel_shader_particles")
    shader_dat.text = PARTICLE_RANDOM_MOVE_SHADER
    shader_dat.nodeX = -210
    shader_dat.nodeY = -260

    particle_glsl = particles.create(glslTOP, "effect_glsl_particles")
    source.outputConnectors[0].connect(particle_glsl.inputConnectors[0])
    particle_glsl.nodeX = -80
    particle_glsl.nodeY = 0
    particle_glsl.par.pixeldat = particle_glsl.relativePath(shader_dat)
    if particle_glsl.par["glslversion"] is not None:
        particle_glsl.par.glslversion = "glsl460"
    if particle_glsl.par["compilebehavior"] is not None:
        particle_glsl.par.compilebehavior = "stalluntildone"
    if particle_glsl.par["errorbehavior"] is not None:
        particle_glsl.par.errorbehavior = "showerror"
    if particle_glsl.par["outputresolution"] is not None:
        particle_glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    particle_glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    particle_glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            particle_glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition["name"] in {"Shape", "Motionmode"}:
            particle_glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.{}.menuIndex".format(definition["name"])

    enable_switch = particles.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    particle_glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 170
    enable_switch.nodeY = 0

    output = particles.create(outTOP, "out1_particles")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 380
    output.nodeY = 0
    output.display = True
    output.render = True
    particles.par.opviewer = output.path

    particle_glsl.cook(force=True)
    errors = list(particle_glsl.errors())
    if errors:
        raise RuntimeError(
            "Random-move particle shader failed: {}".format("; ".join(errors))
        )

    particle_path = CORE_ROOT / "ParticleRandomMove.tox"
    particles.save(str(particle_path), createFolders=True)
    return particles, particle_path


def build_ink_flow_module(parent_comp):
    """Build the reusable ink-style and water-flow particle module."""

    ink_flow = parent_comp.create(baseCOMP, "ink_flow_fusion")
    ink_flow.color = (0.16, 0.22, 0.19)
    ink_flow.comment = (
        "Minimal Chinese ink work and ink wash with an independently "
        "switchable water-current particle layer."
    )
    pages = {}
    parameter_bindings = []
    for definition in INK_FLOW_PARAMETER_DEFINITIONS:
        page_name = definition.get("page", "Ink Flow")
        page = pages.get(page_name)
        if page is None:
            page = ink_flow.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(ink_flow, page, definition)
        parameter_bindings.append((definition, custom_pars))
    ink_flow.par.Time.expr = (
        "absTime.seconds * me.par.Timescale "
        "if me.par.Autotime else me.par.Manualtime"
    )
    ink_flow.store(
        "tdimagefx_ink_flow_module",
        {
            "schema_version": 1,
            "id": "tdimagefx.core.ink-flow-fusion",
            "renderer": "bounded_glsl_top",
            "styles": ["minimal_ink_work", "minimal_ink_wash"],
            "particle_motion": "seeded_water_current",
            "video_fx_routing": "external_optional",
        },
    )

    source = ink_flow.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -420
    source.nodeY = 0

    shader_dat = ink_flow.create(textDAT, "pixel_shader_ink_flow")
    shader_dat.text = INK_FLOW_SHADER
    shader_dat.nodeX = -210
    shader_dat.nodeY = -260

    ink_glsl = ink_flow.create(glslTOP, "effect_glsl_ink_flow")
    source.outputConnectors[0].connect(ink_glsl.inputConnectors[0])
    ink_glsl.nodeX = -80
    ink_glsl.nodeY = 0
    ink_glsl.par.pixeldat = ink_glsl.relativePath(shader_dat)
    if ink_glsl.par["glslversion"] is not None:
        ink_glsl.par.glslversion = "glsl460"
    if ink_glsl.par["compilebehavior"] is not None:
        ink_glsl.par.compilebehavior = "stalluntildone"
    if ink_glsl.par["errorbehavior"] is not None:
        ink_glsl.par.errorbehavior = "showerror"
    if ink_glsl.par["outputresolution"] is not None:
        ink_glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    ink_glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    ink_glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            ink_glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition["name"] in {"Style", "Particleshape"}:
            ink_glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.{}.menuIndex".format(definition["name"])

    enable_switch = ink_flow.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    ink_glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 170
    enable_switch.nodeY = 0

    output = ink_flow.create(outTOP, "out1_ink_flow")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 380
    output.nodeY = 0
    output.display = True
    output.render = True
    ink_flow.par.opviewer = output.path

    ink_glsl.cook(force=True)
    errors = list(ink_glsl.errors())
    if errors:
        raise RuntimeError(
            "Ink-flow shader failed: {}".format("; ".join(errors))
        )

    ink_flow_path = CORE_ROOT / "InkFlowFusion.tox"
    ink_flow.save(str(ink_flow_path), createFolders=True)
    return ink_flow, ink_flow_path


def build_glitch_fusion_module(parent_comp):
    """Build the reusable 24-style glitch treatment module."""

    glitch = parent_comp.create(baseCOMP, "glitch_fusion")
    glitch.color = (0.32, 0.12, 0.28)
    glitch.comment = (
        "Twenty-four selectable GPU glitch treatments with shared timing, "
        "geometry, signal, color, mix, seed, and master-bypass controls."
    )
    pages = {}
    parameter_bindings = []
    for definition in GLITCH_FUSION_PARAMETER_DEFINITIONS:
        page_name = definition.get("page", "Glitch")
        page = pages.get(page_name)
        if page is None:
            page = glitch.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(glitch, page, definition)
        parameter_bindings.append((definition, custom_pars))
    glitch.par.Time.expr = (
        "absTime.seconds * me.par.Timescale "
        "if me.par.Autotime else me.par.Manualtime"
    )
    glitch.store(
        "tdimagefx_glitch_fusion_module",
        {
            "schema_version": 1,
            "id": "tdimagefx.core.glitch-fusion",
            "renderer": "bounded_glsl_top",
            "styles": list(GLITCH_FUSION_STYLE_NAMES),
            "style_count": len(GLITCH_FUSION_STYLE_NAMES),
            "video_fx_routing": "external_optional",
        },
    )

    source = glitch.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -400
    source.nodeY = 0

    shader_dat = glitch.create(textDAT, "pixel_shader_glitch_fusion")
    shader_dat.text = GLITCH_FUSION_SHADER
    shader_dat.nodeX = -200
    shader_dat.nodeY = -200

    glitch_glsl = glitch.create(glslTOP, "effect_glsl_glitch_fusion")
    source.outputConnectors[0].connect(glitch_glsl.inputConnectors[0])
    glitch_glsl.nodeX = 0
    glitch_glsl.nodeY = 0
    glitch_glsl.par.pixeldat = glitch_glsl.relativePath(shader_dat)
    if glitch_glsl.par["glslversion"] is not None:
        glitch_glsl.par.glslversion = "glsl460"
    if glitch_glsl.par["compilebehavior"] is not None:
        glitch_glsl.par.compilebehavior = "stalluntildone"
    if glitch_glsl.par["errorbehavior"] is not None:
        glitch_glsl.par.errorbehavior = "showerror"
    if glitch_glsl.par["outputresolution"] is not None:
        glitch_glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    glitch_glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    glitch_glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            glitch_glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition["name"] == "Style":
            glitch_glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.Style.menuIndex"

    enable_switch = glitch.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    glitch_glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 200
    enable_switch.nodeY = 0

    output = glitch.create(outTOP, "out1_glitch")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 400
    output.nodeY = 0
    output.display = True
    output.render = True
    glitch.par.opviewer = output.path

    glitch_glsl.cook(force=True)
    errors = list(glitch_glsl.errors())
    if errors:
        raise RuntimeError(
            "Glitch Fusion shader failed: {}".format("; ".join(errors))
        )

    glitch_path = CORE_ROOT / "GlitchFusion.tox"
    glitch.save(str(glitch_path), createFolders=True)
    return glitch, glitch_path


def build_color_adjustment_module(parent_comp):
    """Build the reusable single-pass color-adjustment and overlay module."""

    color_adjustment = parent_comp.create(baseCOMP, "color_adjustment")
    color_adjustment.color = (0.48, 0.28, 0.08)
    color_adjustment.comment = (
        "Single-pass GPU color correction, inversion, creative treatments, "
        "tonal balance, film treatments, duotone, and sixteen color-overlay "
        "blend modes with alpha preservation."
    )
    pages = {}
    parameter_bindings = []
    for definition in COLOR_ADJUSTMENT_PARAMETER_DEFINITIONS:
        page_name = definition.get("page", "Color Adjustment")
        page = pages.get(page_name)
        if page is None:
            page = color_adjustment.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(color_adjustment, page, definition)
        parameter_bindings.append((definition, custom_pars))
    color_adjustment.store(
        "tdimagefx_color_adjustment_module",
        {
            "schema_version": 1,
            "id": "tdimagefx.core.color-adjustment",
            "renderer": "bounded_glsl_top",
            "alpha_policy": "preserve_source",
            "overlay_modes": list(COLOR_ADJUSTMENT_OVERLAY_MODE_NAMES),
            "overlay_mode_count": len(COLOR_ADJUSTMENT_OVERLAY_MODE_NAMES),
            "video_fx_routing": "before_optional_rack",
        },
    )

    source = color_adjustment.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -400
    source.nodeY = 0

    shader_dat = color_adjustment.create(textDAT, "pixel_shader_color_adjustment")
    shader_dat.text = COLOR_ADJUSTMENT_SHADER
    shader_dat.nodeX = -200
    shader_dat.nodeY = -220

    color_glsl = color_adjustment.create(glslTOP, "effect_glsl_color_adjustment")
    source.outputConnectors[0].connect(color_glsl.inputConnectors[0])
    color_glsl.nodeX = 0
    color_glsl.nodeY = 0
    color_glsl.par.pixeldat = color_glsl.relativePath(shader_dat)
    if color_glsl.par["glslversion"] is not None:
        color_glsl.par.glslversion = "glsl460"
    if color_glsl.par["compilebehavior"] is not None:
        color_glsl.par.compilebehavior = "stalluntildone"
    if color_glsl.par["errorbehavior"] is not None:
        color_glsl.par.errorbehavior = "showerror"
    if color_glsl.par["outputresolution"] is not None:
        color_glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    color_glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    color_glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            color_glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition["name"] == "Overlaymode":
            color_glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.Overlaymode.menuIndex"

    enable_switch = color_adjustment.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    color_glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 200
    enable_switch.nodeY = 0

    output = color_adjustment.create(outTOP, "out1_color_adjustment")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 400
    output.nodeY = 0
    output.display = True
    output.render = True
    color_adjustment.par.opviewer = output.path

    color_glsl.cook(force=True)
    errors = list(color_glsl.errors())
    if errors:
        raise RuntimeError(
            "Color Adjustment shader failed: {}".format("; ".join(errors))
        )

    color_adjustment_path = CORE_ROOT / "ColorAdjustment.tox"
    color_adjustment.save(str(color_adjustment_path), createFolders=True)
    return color_adjustment, color_adjustment_path


def build_motion_studio_module(parent_comp):
    """Build the reusable forty-style image motion and animation module."""

    motion = parent_comp.create(baseCOMP, "motion_studio")
    motion.color = (0.12, 0.34, 0.52)
    motion.comment = (
        "Forty selectable GPU motion styles with shared timing, transform, "
        "deformation, edge, easing, seeded randomness, trail, mix, and "
        "master-bypass controls."
    )
    pages = {}
    parameter_bindings = []
    for definition in MOTION_STUDIO_PARAMETER_DEFINITIONS:
        page_name = definition.get("page", "Motion Studio")
        page = pages.get(page_name)
        if page is None:
            page = motion.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(motion, page, definition)
        parameter_bindings.append((definition, custom_pars))
    motion.par.Time.expr = (
        "absTime.seconds * me.par.Timescale "
        "if me.par.Autotime else me.par.Manualtime"
    )
    motion.store(
        "tdimagefx_motion_studio_module",
        {
            "schema_version": 1,
            "id": "tdimagefx.core.motion-studio",
            "renderer": "bounded_single_pass_glsl_top",
            "styles": list(MOTION_STUDIO_STYLE_NAMES),
            "style_count": len(MOTION_STUDIO_STYLE_NAMES),
            "edge_modes": list(MOTION_STUDIO_EDGE_MODE_NAMES),
            "easing_modes": list(MOTION_STUDIO_EASING_NAMES),
            "maximum_trail_samples": 5,
            "alpha_policy": "transform_with_source",
            "video_fx_routing": "before_optional_rack",
        },
    )

    source = motion.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -400
    source.nodeY = 0

    shader_dat = motion.create(textDAT, "pixel_shader_motion_studio")
    shader_dat.text = MOTION_STUDIO_SHADER
    shader_dat.nodeX = -200
    shader_dat.nodeY = -220

    motion_glsl = motion.create(glslTOP, "effect_glsl_motion_studio")
    source.outputConnectors[0].connect(motion_glsl.inputConnectors[0])
    motion_glsl.nodeX = 0
    motion_glsl.nodeY = 0
    motion_glsl.par.pixeldat = motion_glsl.relativePath(shader_dat)
    if motion_glsl.par["glslversion"] is not None:
        motion_glsl.par.glslversion = "glsl460"
    if motion_glsl.par["compilebehavior"] is not None:
        motion_glsl.par.compilebehavior = "stalluntildone"
    if motion_glsl.par["errorbehavior"] is not None:
        motion_glsl.par.errorbehavior = "showerror"
    if motion_glsl.par["outputresolution"] is not None:
        motion_glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    motion_glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    motion_glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    menu_parameters = {"Style", "Easing", "Edgemode"}
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            motion_glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition["name"] in menu_parameters:
            motion_glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.{}.menuIndex".format(definition["name"])

    enable_switch = motion.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    motion_glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 200
    enable_switch.nodeY = 0

    output = motion.create(outTOP, "out1_motion")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 400
    output.nodeY = 0
    output.display = True
    output.render = True
    motion.par.opviewer = output.path

    motion_glsl.cook(force=True)
    errors = list(motion_glsl.errors())
    if errors:
        raise RuntimeError(
            "Motion Studio shader failed: {}".format("; ".join(errors))
        )

    motion_path = CORE_ROOT / "MotionStudio.tox"
    motion.save(str(motion_path), createFolders=True)
    return motion, motion_path


def _build_reference_video_module(
    parent_comp,
    *,
    component_name,
    component_label,
    shader_source,
    parameter_definitions,
    storage_key,
    module_id,
    tox_name,
    color,
    reference_video,
):
    """Build one bounded, single-input GPU module derived from a reference video."""

    module = parent_comp.create(baseCOMP, component_name)
    module.color = color
    module.comment = (
        "{}: adjustable GPU recreation of {} with master bypass, dry/wet mix, "
        "deterministic manual time, and automatic animation."
    ).format(component_label, reference_video)
    pages = {}
    parameter_bindings = []
    for definition in parameter_definitions:
        page_name = definition.get("page", component_label)
        page = pages.get(page_name)
        if page is None:
            page = module.appendCustomPage(page_name)
            pages[page_name] = page
        custom_pars = _append_parameter(module, page, definition)
        parameter_bindings.append((definition, custom_pars))
    if module.par["Time"] is not None:
        module.par.Time.expr = (
            "absTime.seconds * me.par.Timescale "
            "if me.par.Autotime else me.par.Manualtime"
        )
    module.store(
        storage_key,
        {
            "schema_version": 1,
            "id": module_id,
            "renderer": "bounded_single_pass_glsl_top",
            "reference_video": reference_video,
            "alpha_policy": "module_defined_with_bypass",
            "video_fx_routing": "before_optional_rack",
        },
    )

    source = module.create(inTOP, "in1_image")
    source.par.label = "source image"
    source.nodeX = -400
    source.nodeY = 0

    shader_suffix = component_name
    shader_dat = module.create(textDAT, "pixel_shader_{}".format(shader_suffix))
    shader_dat.text = shader_source
    shader_dat.nodeX = -200
    shader_dat.nodeY = -220

    glsl = module.create(glslTOP, "effect_glsl_{}".format(shader_suffix))
    source.outputConnectors[0].connect(glsl.inputConnectors[0])
    glsl.nodeX = 0
    glsl.nodeY = 0
    glsl.par.pixeldat = glsl.relativePath(shader_dat)
    if glsl.par["glslversion"] is not None:
        glsl.par.glslversion = "glsl460"
    if glsl.par["compilebehavior"] is not None:
        glsl.par.compilebehavior = "stalluntildone"
    if glsl.par["errorbehavior"] is not None:
        glsl.par.errorbehavior = "showerror"
    if glsl.par["outputresolution"] is not None:
        glsl.par.outputresolution = "useinput"

    active_bindings = [
        (definition, custom_pars)
        for definition, custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    glsl.seq.vec.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") not in {"rgb", "rgba"}
        ),
    )
    glsl.seq.color.numBlocks = max(
        1,
        sum(
            1
            for definition, _custom_pars in active_bindings
            if definition.get("type") in {"rgb", "rgba"}
        ),
    )
    vector_index = 0
    color_index = 0
    for definition, custom_pars in active_bindings:
        current_vector_index = vector_index
        vector_index, color_index = _configure_glsl_uniform(
            glsl,
            definition,
            custom_pars,
            vector_index,
            color_index,
        )
        if definition.get("type") == "menu":
            glsl.par[
                "vec{}valuex".format(current_vector_index)
            ].expr = "parent().par.{}.menuIndex".format(definition["name"])

    enable_switch = module.create(switchTOP, "enable_switch")
    source.outputConnectors[0].connect(enable_switch.inputConnectors[0])
    glsl.outputConnectors[0].connect(enable_switch.inputConnectors[1])
    enable_switch.par.index.expr = "1 if parent().par.Enabled else 0"
    enable_switch.nodeX = 200
    enable_switch.nodeY = 0

    output = module.create(outTOP, "out1_image")
    enable_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 400
    output.nodeY = 0
    output.display = True
    output.render = True
    module.par.opviewer = output.path

    glsl.cook(force=True)
    errors = list(glsl.errors())
    if errors:
        raise RuntimeError(
            "{} shader failed: {}".format(component_label, "; ".join(errors))
        )

    tox_path = CORE_ROOT / tox_name
    module.save(str(tox_path), createFolders=True)
    return module, tox_path


def build_reference_particle_field_module(parent_comp):
    return _build_reference_video_module(
        parent_comp,
        component_name="reference_particle_field",
        component_label="Chromatic Particle Field",
        shader_source=REFERENCE_PARTICLE_FIELD_SHADER,
        parameter_definitions=REFERENCE_PARTICLE_FIELD_PARAMETER_DEFINITIONS,
        storage_key="tdimagefx_reference_particle_field_module",
        module_id="tdimagefx.core.reference-particle-field",
        tox_name="ReferenceParticleField.tox",
        color=(0.12, 0.24, 0.56),
        reference_video="ScreenRecording_07-22-2026 16-57-40_1.mov",
    )


def build_calligraphic_shadow_module(parent_comp):
    return _build_reference_video_module(
        parent_comp,
        component_name="calligraphic_shadow",
        component_label="Calligraphic Shadow",
        shader_source=CALLIGRAPHIC_SHADOW_SHADER,
        parameter_definitions=CALLIGRAPHIC_SHADOW_PARAMETER_DEFINITIONS,
        storage_key="tdimagefx_calligraphic_shadow_module",
        module_id="tdimagefx.core.calligraphic-shadow",
        tox_name="CalligraphicShadow.tox",
        color=(0.10, 0.12, 0.10),
        reference_video="ScreenRecording_07-22-2026 16-56-53_1.mov",
    )


def build_ink_orbit_canvas_module(parent_comp):
    return _build_reference_video_module(
        parent_comp,
        component_name="ink_orbit_canvas",
        component_label="Ink Orbit Canvas",
        shader_source=INK_ORBIT_CANVAS_SHADER,
        parameter_definitions=INK_ORBIT_CANVAS_PARAMETER_DEFINITIONS,
        storage_key="tdimagefx_ink_orbit_canvas_module",
        module_id="tdimagefx.core.ink-orbit-canvas",
        tox_name="InkOrbitCanvas.tox",
        color=(0.28, 0.24, 0.16),
        reference_video="ScreenRecording_07-22-2026 15-38-39_1.mov",
    )


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
    # Preview PNGs are contractually 512x288. Pinning the TOP output avoids a
    # transient 128x128 fallback while Movie File In completes its first load,
    # without resampling a successfully loaded preview.
    if selected_preview.par["outputresolution"] is not None:
        selected_preview.par.outputresolution = "custom"
        selected_preview.par.resolutionw = 512
        selected_preview.par.resolutionh = 288

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

    starter = browser.create(executeDAT, "startup_callbacks")
    starter.text = _read_text(
        PROJECT_ROOT
        / "touchdesigner"
        / "callbacks"
        / "browser_start_callbacks.py"
    )
    starter.par.start = True
    starter.par.create = True
    starter.nodeX = 300
    starter.nodeY = -300

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
        "Use core/particle_random_move for GPU image particles with deterministic random motion.\n"
        "Use core/ink_flow_fusion for minimal ink work, ink wash, and water-current particles.\n"
        "Use core/glitch_fusion for 24 selectable digital and analog glitch treatments.\n"
        "Use core/color_adjustment for grading, inversion, duotone, and color overlays.\n"
        "Use core/motion_studio for 40 selectable movement and animation styles.\n"
        "Use core/reference_particle_field for the chromatic point-cloud reference effect.\n"
        "Use core/calligraphic_shadow for the dancer-like flowing ink shadow reference effect.\n"
        "Use core/ink_orbit_canvas for procedural wet-ink rings, droplets, and floor perspective.\n"
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
    particles, particle_path = build_particle_module(core_parent)
    particles.nodeX = 260
    particles.nodeY = 0
    ink_flow, ink_flow_path = build_ink_flow_module(core_parent)
    ink_flow.nodeX = 520
    ink_flow.nodeY = 0
    glitch, glitch_path = build_glitch_fusion_module(core_parent)
    glitch.nodeX = 780
    glitch.nodeY = 0
    color_adjustment, color_adjustment_path = build_color_adjustment_module(
        core_parent
    )
    color_adjustment.nodeX = 1040
    color_adjustment.nodeY = 0
    motion, motion_path = build_motion_studio_module(core_parent)
    motion.nodeX = 1300
    motion.nodeY = 0
    reference_particle_field, reference_particle_field_path = (
        build_reference_particle_field_module(core_parent)
    )
    reference_particle_field.nodeX = 1560
    reference_particle_field.nodeY = 0
    calligraphic_shadow, calligraphic_shadow_path = (
        build_calligraphic_shadow_module(core_parent)
    )
    calligraphic_shadow.nodeX = 1820
    calligraphic_shadow.nodeY = 0
    ink_orbit_canvas, ink_orbit_canvas_path = build_ink_orbit_canvas_module(
        core_parent
    )
    ink_orbit_canvas.nodeX = 2080
    ink_orbit_canvas.nodeY = 0
    browser, browser_path = build_browser(core_parent, manifests, compatibility_confidence)
    browser.nodeX = 2340
    browser.nodeY = 0

    library.par.Status = "Ready: {} packages".format(len(manifests))
    library_path = CORE_ROOT / "TDImageFXLibrary.tox"
    library.save(str(library_path), createFolders=True)
    report["core"] = {
        "library": str(library_path),
        "rack": str(rack_path),
        "particles": str(particle_path),
        "ink_flow": str(ink_flow_path),
        "glitch": str(glitch_path),
        "color_adjustment": str(color_adjustment_path),
        "motion": str(motion_path),
        "reference_particle_field": str(reference_particle_field_path),
        "calligraphic_shadow": str(calligraphic_shadow_path),
        "ink_orbit_canvas": str(ink_orbit_canvas_path),
        "browser": str(browser_path),
        "updater": str(CORE_ROOT / "FxUpdater.tox"),
    }
    return (
        library,
        rack_path,
        particle_path,
        ink_flow_path,
        glitch_path,
        color_adjustment_path,
        motion_path,
        reference_particle_field_path,
        calligraphic_shadow_path,
        ink_orbit_canvas_path,
    )


def build_demo(
    project_comp,
    rack_path,
    particle_path,
    ink_flow_path,
    glitch_path,
    color_adjustment_path,
    motion_path,
    reference_particle_field_path,
    calligraphic_shadow_path,
    ink_orbit_canvas_path,
):
    demo = project_comp.create(baseCOMP, "imagefx_demo")
    demo.nodeX = 100
    demo.nodeY = 100
    demo.color = (0.32, 0.18, 0.36)
    demo.comment = (
        "Animated source -> three optional reference recreations -> optional ink flow -> optional random particles -> "
        "optional Glitch Fusion -> optional color adjustment -> optional "
        "Motion Studio -> optional eight-slot video FX. "
        "Output defaults to 1920 x 1080 with 4K UHD and custom presets. "
        "Replace source_image with any TOP."
    )
    demo_page = demo.appendCustomPage("Demo")
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Referenceparticlefieldenabled",
            "label": "Chromatic Particle Field Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the 16:57:40 reference recreation before the existing modules.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Calligraphicshadowenabled",
            "label": "Calligraphic Shadow Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the 16:56:53 dancer-shadow reference recreation.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Inkorbitenabled",
            "label": "Ink Orbit Canvas Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the 15:38:39 procedural ink-canvas reference recreation.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Inkflowenabled",
            "label": "Ink Flow Module Enabled",
            "type": "toggle",
            "default": True,
            "description": "Enable the ink styles and water particles configured inside ink_flow.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Particlesenabled",
            "label": "Random Particles Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the separate legacy random-move particle module after ink_flow.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Glitchenabled",
            "label": "Glitch Module Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the selected Glitch Fusion treatment after both particle stages.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Coloradjustmentenabled",
            "label": "Color Adjustment Enabled",
            "type": "toggle",
            "default": False,
            "description": "Apply the independently adjustable color module after Glitch Fusion.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Motionenabled",
            "label": "Motion Module Enabled",
            "type": "toggle",
            "default": False,
            "description": "Animate the combined image with the selected Motion Studio style.",
        },
    )
    _append_parameter(
        demo,
        demo_page,
        {
            "name": "Applyvideofx",
            "label": "Apply Video Effects",
            "type": "toggle",
            "default": True,
            "description": "Route the source or particles through the eight-slot rack.",
        },
    )
    output_page = demo.appendCustomPage("Output")
    for definition in DEMO_OUTPUT_PARAMETER_DEFINITIONS:
        _append_parameter(demo, output_page, definition)
    demo.par.Customwidth.enableExpr = (
        "me.par.Resolutionpreset.eval() == 'custom'"
    )
    demo.par.Customheight.enableExpr = (
        "me.par.Resolutionpreset.eval() == 'custom'"
    )

    source_shader = demo.create(textDAT, "source_image_shader")
    source_shader.text = PREVIEW_SOURCE_SHADER
    source_shader.nodeX = -520
    source_shader.nodeY = 100

    source = demo.create(glslTOP, "source_image")
    source.nodeX = -300
    source.nodeY = 0
    source.par.pixeldat = source.relativePath(source_shader)
    if source.par["glslversion"] is not None:
        source.par.glslversion = "glsl460"
    if source.par["compilebehavior"] is not None:
        source.par.compilebehavior = "stalluntildone"
    if source.par["errorbehavior"] is not None:
        source.par.errorbehavior = "showerror"
    source.seq.vec.numBlocks = 1
    source.par.vec0name = "uTime"
    source.par.vec0valuex.expr = "absTime.seconds"
    if source.par["outputresolution"] is not None:
        source.par.outputresolution = "custom"
        source.par.resolutionw.expr = _demo_output_resolution_expression("width")
        source.par.resolutionh.expr = _demo_output_resolution_expression("height")
    source.cook(force=True)
    source_errors = list(source.errors())
    if source_errors:
        raise RuntimeError(
            "Demo source shader failed: {}".format("; ".join(source_errors))
        )

    reference_particle_field = load_tox_component(
        demo,
        reference_particle_field_path,
        "reference_particle_field",
    )
    reference_particle_field.nodeX = -40
    reference_particle_field.nodeY = 0
    reference_particle_field.par.Enabled.expr = (
        "parent().par.Referenceparticlefieldenabled"
    )
    source.outputConnectors[0].connect(
        reference_particle_field.inputConnectors[0]
    )

    calligraphic_shadow = load_tox_component(
        demo,
        calligraphic_shadow_path,
        "calligraphic_shadow",
    )
    calligraphic_shadow.nodeX = 220
    calligraphic_shadow.nodeY = 0
    calligraphic_shadow.par.Enabled.expr = (
        "parent().par.Calligraphicshadowenabled"
    )
    reference_particle_field.outputConnectors[0].connect(
        calligraphic_shadow.inputConnectors[0]
    )

    ink_orbit_canvas = load_tox_component(
        demo,
        ink_orbit_canvas_path,
        "ink_orbit_canvas",
    )
    ink_orbit_canvas.nodeX = 480
    ink_orbit_canvas.nodeY = 0
    ink_orbit_canvas.par.Enabled.expr = "parent().par.Inkorbitenabled"
    calligraphic_shadow.outputConnectors[0].connect(
        ink_orbit_canvas.inputConnectors[0]
    )

    ink_flow = load_tox_component(
        demo,
        ink_flow_path,
        "ink_flow",
    )
    ink_flow.nodeX = 740
    ink_flow.nodeY = 0
    ink_flow.par.Enabled.expr = "parent().par.Inkflowenabled"
    ink_orbit_canvas.outputConnectors[0].connect(ink_flow.inputConnectors[0])

    particles = load_tox_component(
        demo,
        particle_path,
        "particle_random_move",
    )
    particles.nodeX = 1000
    particles.nodeY = 0
    particles.par.Enabled.expr = "parent().par.Particlesenabled"
    ink_flow.outputConnectors[0].connect(particles.inputConnectors[0])

    glitch = load_tox_component(
        demo,
        glitch_path,
        "glitch_fusion",
    )
    glitch.nodeX = 1260
    glitch.nodeY = 0
    glitch.par.Enabled.expr = "parent().par.Glitchenabled"
    particles.outputConnectors[0].connect(glitch.inputConnectors[0])

    color_adjustment = load_tox_component(
        demo,
        color_adjustment_path,
        "color_adjustment",
    )
    color_adjustment.nodeX = 1520
    color_adjustment.nodeY = 0
    color_adjustment.par.Enabled.expr = "parent().par.Coloradjustmentenabled"
    glitch.outputConnectors[0].connect(color_adjustment.inputConnectors[0])

    motion = load_tox_component(
        demo,
        motion_path,
        "motion_studio",
    )
    motion.nodeX = 1780
    motion.nodeY = 0
    motion.par.Enabled.expr = "parent().par.Motionenabled"
    color_adjustment.outputConnectors[0].connect(motion.inputConnectors[0])

    rack = load_tox_component(demo, rack_path, "fx_rack")
    rack.nodeX = 2040
    rack.nodeY = 0
    motion.outputConnectors[0].connect(rack.inputConnectors[0])

    # Supply visible, deterministic fixtures for every semantic auxiliary bus.
    # The reusable rack still exposes these as normal inputs; this only makes
    # the canonical demo useful when a user auditions an auxiliary-input effect
    # before connecting production depth, flow, mask, or secondary-image TOPs.
    fixture_values = {
        "displacement": (0.72, 0.28, 0.50, 1.0),
        "depth": (0.68, 0.68, 0.68, 1.0),
        "normal": (0.64, 0.36, 1.00, 1.0),
        "flow": (0.58, 0.42, 0.85, 1.0),
        "mask": (0.72, 0.72, 0.72, 1.0),
    }
    secondary_shader = demo.create(textDAT, "fixture_image_b_shader")
    secondary_shader.text = DEMO_SECONDARY_IMAGE_SHADER
    secondary_shader.nodeX = -520
    secondary_shader.nodeY = -110
    secondary = demo.create(glslTOP, "fixture_image_b")
    secondary.nodeX = -300
    secondary.nodeY = -110
    source.outputConnectors[0].connect(secondary.inputConnectors[0])
    secondary.par.pixeldat = secondary.relativePath(secondary_shader)
    if secondary.par["glslversion"] is not None:
        secondary.par.glslversion = "glsl460"
    if secondary.par["compilebehavior"] is not None:
        secondary.par.compilebehavior = "stalluntildone"
    if secondary.par["errorbehavior"] is not None:
        secondary.par.errorbehavior = "showerror"
    if secondary.par["outputresolution"] is not None:
        secondary.par.outputresolution = "useinput"
    secondary.outputConnectors[0].connect(rack.inputConnectors[1])

    for input_index, (role, _label) in enumerate(RACK_AUXILIARY_INPUTS[1:], start=2):
        fixture = demo.create(constantTOP, "fixture_{}".format(role))
        fixture.nodeX = -300
        fixture.nodeY = -input_index * 110
        for suffix, value in zip("rgba", fixture_values[role]):
            parameter = fixture.par["color{}".format(suffix)]
            if parameter is not None:
                parameter.val = value
        if fixture.par["outputresolution"] is not None:
            fixture.par.outputresolution = "custom"
            fixture.par.resolutionw = 1
            fixture.par.resolutionh = 1
        fixture.outputConnectors[0].connect(rack.inputConnectors[input_index])

    video_fx_router = demo.create(switchTOP, "video_fx_router")
    motion.outputConnectors[0].connect(video_fx_router.inputConnectors[0])
    rack.outputConnectors[0].connect(video_fx_router.inputConnectors[1])
    video_fx_router.par.index.expr = "1 if parent().par.Applyvideofx else 0"
    video_fx_router.nodeX = 2290
    video_fx_router.nodeY = 0

    output = demo.create(outTOP, "out1_image")
    video_fx_router.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 2500
    output.nodeY = 0
    if output.par["outputresolution"] is not None:
        output.par.outputresolution = "custom"
        output.par.resolutionw.expr = _demo_output_resolution_expression("width")
        output.par.resolutionh.expr = _demo_output_resolution_expression("height")
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
        (
            library,
            rack_path,
            particle_path,
            ink_flow_path,
            glitch_path,
            color_adjustment_path,
            motion_path,
            reference_particle_field_path,
            calligraphic_shadow_path,
            ink_orbit_canvas_path,
        ) = build_library(
            project_comp,
            manifests,
            report,
        )
        build_demo(
            project_comp,
            rack_path,
            particle_path,
            ink_flow_path,
            glitch_path,
            color_adjustment_path,
            motion_path,
            reference_particle_field_path,
            calligraphic_shadow_path,
            ink_orbit_canvas_path,
        )
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
