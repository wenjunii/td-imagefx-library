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
    "/project1/imagefx_demo/glitch_fusion/out1_glitch",
    "/project1/imagefx_demo/color_adjustment/out1_color_adjustment",
    "/project1/imagefx_demo/fx_rack/out1_image",
    "/project1/td_imagefx/core/fx_browser/selected_preview",
)
DIAGNOSTIC_COOKS = (
    "/project1/td_imagefx/core/fx_browser",
)
EXPECTED_RESOLUTION_PRESETS = ("hd", "uhd4k", "custom")
RACK_PATH = "/project1/imagefx_demo/fx_rack"
RACK_SLOT_COUNT = 8
BROWSER_PATH = "/project1/td_imagefx/core/fx_browser"


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


def _resolution_diagnostics(primary_output):
    demo = op("/project1/imagefx_demo")
    if demo is None:
        return {
            "ok": False,
            "errors": ["imagefx_demo is missing"],
        }
    try:
        preset = str(demo.par.Resolutionpreset.eval())
        custom_width = int(demo.par.Customwidth.eval())
        custom_height = int(demo.par.Customheight.eval())
        menu_names = tuple(
            str(item) for item in demo.par.Resolutionpreset.menuNames
        )
        targets = {
            "hd": (1920, 1080),
            "uhd4k": (3840, 2160),
            "custom": (custom_width, custom_height),
        }
        target = targets.get(preset)
        actual = (
            primary_output.get("width"),
            primary_output.get("height"),
        )
        errors = []
        if menu_names != EXPECTED_RESOLUTION_PRESETS:
            errors.append("Resolution preset menu does not match the contract")
        if target is None:
            errors.append("Unknown resolution preset: {}".format(preset))
        elif actual != target:
            errors.append(
                "Primary output is {}x{} but {} requires {}x{}".format(
                    actual[0],
                    actual[1],
                    preset,
                    target[0],
                    target[1],
                )
            )
        return {
            "ok": not errors,
            "preset": preset,
            "preset_menu": list(menu_names),
            "custom_width": custom_width,
            "custom_height": custom_height,
            "target_width": target[0] if target else None,
            "target_height": target[1] if target else None,
            "actual_width": actual[0],
            "actual_height": actual[1],
            "errors": errors,
        }
    except Exception as exc:
        return {
            "ok": False,
            "errors": ["{}: {}".format(type(exc).__name__, exc)],
        }


def _rack_diagnostics():
    rack = op(RACK_PATH)
    if rack is None:
        return {
            "ok": False,
            "path": RACK_PATH,
            "errors": ["rack is missing"],
            "slots": [],
        }

    callbacks = rack.op("parameter_callbacks")
    callback_checks = {
        "exists": callbacks is not None,
        "targets_owning_rack": False,
        "watches_all_slot_parameters": False,
        "value_change_enabled": False,
    }
    callback_errors = []
    if callbacks is not None:
        try:
            callback_checks.update(
                {
                    "targets_owning_rack": callbacks.par.op.eval() == rack,
                    "watches_all_slot_parameters": (
                        "Slot*" in str(callbacks.par.pars.eval())
                    ),
                    "value_change_enabled": bool(
                        callbacks.par.valuechange.eval()
                    ),
                }
            )
            callback_errors.extend(_messages(callbacks, "errors"))
            callback_errors.extend(_messages(callbacks, "warnings"))
        except Exception as exc:
            callback_errors.append(
                "{}: {}".format(type(exc).__name__, exc)
            )

    slots = []
    for index in range(1, RACK_SLOT_COUNT + 1):
        try:
            state = dict(rack.SlotState(index))
            package = state.get("package")
            package_id = (
                package.get("id") if isinstance(package, dict) else None
            )
            parameter = rack.par["Slot{}effect".format(index)]
            selected_id = (
                str(parameter.eval()) if parameter is not None else None
            )
            loaded = rack.op("slot{}".format(index))
            checks = {
                "parameter_exists": parameter is not None,
                "component_matches_state": (
                    (package_id is None and loaded is None)
                    or (package_id is not None and loaded is not None)
                ),
                "selection_matches_loaded_package": (
                    package_id is None or selected_id == package_id
                ),
            }
            slots.append(
                {
                    "slot": index,
                    "selected_package": selected_id,
                    "loaded_package": package,
                    "checks": checks,
                    "ok": all(checks.values()),
                }
            )
        except Exception as exc:
            slots.append(
                {
                    "slot": index,
                    "ok": False,
                    "errors": [
                        "{}: {}".format(type(exc).__name__, exc)
                    ],
                }
            )

    rack_errors = _messages(rack, "errors")
    rack_warnings = _messages(rack, "warnings")
    return {
        "ok": (
            all(callback_checks.values())
            and not callback_errors
            and len(slots) == RACK_SLOT_COUNT
            and all(item["ok"] for item in slots)
            and not rack_errors
            and not rack_warnings
        ),
        "path": RACK_PATH,
        "parameter_callbacks": {
            "checks": callback_checks,
            "errors": callback_errors,
        },
        "slots": slots,
        "errors": rack_errors,
        "warnings": rack_warnings,
    }


def _browser_diagnostics():
    browser = op(BROWSER_PATH)
    if browser is None:
        return {
            "ok": False,
            "path": BROWSER_PATH,
            "errors": ["browser is missing"],
        }

    preview = browser.op("selected_preview")
    callbacks = browser.op("startup_callbacks")
    callback_text = str(callbacks.text) if callbacks is not None else ""
    preview_path = ""
    try:
        preview_path = str(browser.PreviewPath())
    except Exception:
        pass
    checks = {
        "preview_exists": preview is not None,
        "preview_file_exists": bool(
            preview_path and Path(preview_path).is_file()
        ),
        "startup_callbacks_exist": callbacks is not None,
        "startup_enabled": bool(
            callbacks is not None and callbacks.par.start.eval()
        ),
        "create_enabled": bool(
            callbacks is not None
            and callbacks.par["create"] is not None
            and callbacks.par.create.eval()
        ),
        "reloads_selected_preview": (
            "UpdateSelection()" in callback_text
            and "delayFrames=1" in callback_text
        ),
    }
    errors = _messages(browser, "errors")
    warnings = _messages(browser, "warnings")
    return {
        "ok": all(checks.values()) and not errors and not warnings,
        "path": BROWSER_PATH,
        "checks": checks,
        "selected_id": str(browser.par.Selectedid.eval()),
        "preview_path": preview_path,
        "errors": errors,
        "warnings": warnings,
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
    resolution = _resolution_diagnostics(outputs[0])
    rack = _rack_diagnostics()
    browser = _browser_diagnostics()
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
        "ok": (
            health_ok
            and roots_ok
            and outputs_ok
            and resolution["ok"]
            and rack["ok"]
            and browser["ok"]
        ),
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
        "health": health,
        "managed_roots": roots,
        "outputs": outputs,
        "output_resolution": resolution,
        "rack_selection": rack,
        "browser_startup": browser,
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
