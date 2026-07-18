"""Read-only structural validation for a live TD ImageFX TouchDesigner project."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "build" / "envoy-validation" / "live-project.json"
EXPECTED_PACKAGES = 96
EXPECTED_VERSIONS = 122
MANAGED_ROOTS = (
    "/project1/td_imagefx",
    "/project1/imagefx_demo",
)
OUTPUTS = (
    "/project1/imagefx_demo/out1_image",
    "/project1/imagefx_demo/ink_flow/out1_ink_flow",
    "/project1/imagefx_demo/particle_random_move/out1_particles",
    "/project1/imagefx_demo/fx_rack/out1_image",
    "/project1/td_imagefx/core/fx_browser/selected_preview",
)
DIAGNOSTIC_COOKS = (
    "/project1/td_imagefx/core/fx_browser",
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


def _safe_attr(operator, name):
    try:
        value = getattr(operator, name)
        return value() if callable(value) else value
    except Exception:
        return None


def _operator_diagnostics(path):
    operator = op(path)
    if operator is None:
        return {
            "path": path,
            "exists": False,
            "errors": ["operator is missing"],
            "warnings": [],
            "script_errors": [],
        }
    return {
        "path": path,
        "exists": True,
        "type": str(operator.type),
        "family": str(operator.family),
        "errors": _messages(operator, "errors"),
        "warnings": _messages(operator, "warnings"),
        "script_errors": _messages(operator, "scriptErrors"),
    }


def _output_diagnostics(path):
    operator = op(path)
    if operator is None:
        return {
            "path": path,
            "exists": False,
            "usable": False,
            "errors": ["TOP is missing"],
        }
    cook_error = None
    try:
        operator.cook(force=True)
    except Exception as exc:
        cook_error = "{}: {}".format(type(exc).__name__, exc)
    family = str(_safe_attr(operator, "family") or "")
    width = _safe_attr(operator, "width")
    height = _safe_attr(operator, "height")
    errors = _messages(operator, "errors")
    if cook_error:
        errors.append(cook_error)
    usable = (
        family == "TOP"
        and isinstance(width, int)
        and isinstance(height, int)
        and width >= 2
        and height >= 2
        and not errors
    )
    return {
        "path": path,
        "exists": True,
        "usable": usable,
        "type": str(_safe_attr(operator, "type") or ""),
        "family": family,
        "width": width,
        "height": height,
        "pixel_format": _safe_attr(operator, "pixelFormat"),
        "errors": errors,
    }


def validate(write_report=True):
    """Return a JSON-safe diagnostic report and optionally write the ignored copy."""

    library = op("/project1/td_imagefx")
    if library is None:
        health = {
            "ok": False,
            "error": "ImageFX library is missing",
        }
    else:
        try:
            health = dict(library.HealthCheck())
        except Exception as exc:
            health = {
                "ok": False,
                "error": "{}: {}".format(type(exc).__name__, exc),
            }

    # Cook the configured output chains and diagnostic components before
    # collecting recursive messages. TouchDesigner can retain prior GLSL path
    # errors or operator-parameter warnings on parent COMPs until the repaired
    # node has cooked again.
    outputs = [_output_diagnostics(path) for path in OUTPUTS]
    for path in DIAGNOSTIC_COOKS:
        operator = op(path)
        if operator is not None:
            operator.cook(force=True)
    roots = [_operator_diagnostics(path) for path in MANAGED_ROOTS]
    health_ok = (
        health.get("ok") is True
        and health.get("package_count") == EXPECTED_PACKAGES
        and health.get("package_version_count") == EXPECTED_VERSIONS
        and health.get("missing_entrypoints") == []
    )
    roots_ok = all(
        item["exists"]
        and not item["errors"]
        and not item["warnings"]
        and not item["script_errors"]
        for item in roots
    )
    outputs_ok = all(item["usable"] for item in outputs)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "ok": health_ok and roots_ok and outputs_ok,
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
        "health": health,
        "managed_roots": roots,
        "outputs": outputs,
        "pixel_validation_required": True,
        "pixel_validation_note": (
            "Use Envoy capture_top on every configured output; structural checks "
            "cannot detect a black or fully transparent image."
        ),
    }
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
