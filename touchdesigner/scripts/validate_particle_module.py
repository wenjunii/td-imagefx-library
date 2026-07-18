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
OUTPUT_PATH = DEMO_PATH + "/out1_image"
SOURCE_PATH = DEMO_PATH + "/source_image"
ROUTER_PATH = DEMO_PATH + "/video_fx_router"
PARTICLE_OUTPUT_PATH = PARTICLE_PATH + "/out1_particles"
PARTICLE_SHADER_PATH = PARTICLE_PATH + "/effect_glsl_particles"


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
        "apply_video_fx": demo.par.Applyvideofx.eval(),
        "auto_time": particles.par.Autotime.eval(),
        "manual_time": particles.par.Manualtime.eval(),
        "density": particles.par.Density.eval(),
        "seed": particles.par.Seed.eval(),
        "source_time_expression": source.par.vec0valuex.expr,
        "source_time_value": source.par.vec0valuex.eval(),
    }

    try:
        # Freeze both generators so route comparisons cannot be contaminated by
        # a later animation frame.
        source.par.vec0valuex.expr = ""
        source.par.vec0valuex = 0.0
        particles.par.Autotime = False
        particles.par.Manualtime = 0.0

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
        particles.par.Seed = int(saved["seed"]) + 17
        seed_end = _capture(particle_output)
        particles.par.Density = int(particles.par.Density.max)
        maximum_density = _capture(particle_output)

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
            "particle_columns_maximum_is_500": (
                float(particles.par.Density.max) == 500.0
            ),
            "maximum_density_cooks_visible_output": (
                float(np.std(maximum_density)) > 1.0e-5
            ),
        }
        report.update(
            {
                "checks": checks,
                "differences": differences,
                "maximum_density_metrics": _metrics(maximum_density),
                "particle_metrics": _metrics(motion_start),
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
        demo.par.Applyvideofx = saved["apply_video_fx"]
        particles.par.Autotime = saved["auto_time"]
        particles.par.Manualtime = saved["manual_time"]
        particles.par.Density = saved["density"]
        particles.par.Seed = saved["seed"]
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
