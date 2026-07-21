"""Live regression validation for all eight ImageFX rack selection callbacks.

The validator temporarily changes each Slot*effect menu, verifies that the
selected package was actually loaded, and restores the complete rack preset in
a finally block. It never saves the TouchDesigner project.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "build" / "envoy-validation" / "rack-selection.json"
)
RACK_PATH = "/project1/imagefx_demo/fx_rack"
OUTPUT_PATH = RACK_PATH + "/out1_image"
SLOT_COUNT = 8
ALTERNATIVE_PACKAGES = (
    "tdimagefx.color.duotone",
    "tdimagefx.stylize.pixelate",
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


def _callback_diagnostics(rack):
    callbacks = rack.op("parameter_callbacks")
    if callbacks is None:
        return {
            "ok": False,
            "exists": False,
            "errors": ["parameter_callbacks is missing"],
        }
    try:
        target = callbacks.par.op.eval()
        watched = str(callbacks.par.pars.eval())
        checks = {
            "targets_owning_rack": target == rack,
            "watches_all_slot_parameters": "Slot*" in watched,
            "value_change_enabled": bool(callbacks.par.valuechange.eval()),
            "pulse_enabled": bool(callbacks.par.onpulse.eval()),
            "custom_parameters_enabled": bool(callbacks.par.custom.eval()),
        }
        errors = _messages(callbacks, "errors")
        warnings = _messages(callbacks, "warnings")
        return {
            "ok": all(checks.values()) and not errors and not warnings,
            "exists": True,
            "path": callbacks.path,
            "target": getattr(target, "path", str(target)),
            "watched_parameters": watched,
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "ok": False,
            "exists": True,
            "path": callbacks.path,
            "errors": ["{}: {}".format(type(exc).__name__, exc)],
        }


def _slot_state(rack, index):
    state = dict(rack.SlotState(index))
    package = state.get("package")
    package_id = package.get("id") if isinstance(package, dict) else None
    return state, package_id


def _choose_alternative(parameter, original_id):
    menu_names = tuple(str(item) for item in parameter.menuNames)
    for package_id in ALTERNATIVE_PACKAGES:
        if package_id != original_id and package_id in menu_names:
            return package_id
    raise RuntimeError(
        "No regression-test package is available in {}".format(parameter.name)
    )


def validate(write_report=True):
    """Exercise all eight effect menus and restore the exact original preset."""

    rack = op(RACK_PATH)
    output = op(OUTPUT_PATH)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "ok": False,
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
        "rack_path": RACK_PATH,
        "output_path": OUTPUT_PATH,
    }
    missing = [
        name
        for name, operator in (("rack", rack), ("output", output))
        if operator is None
    ]
    report["missing_operators"] = missing
    if missing:
        report["error"] = "Required rack-selection operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    callback_diagnostics = _callback_diagnostics(rack)
    report["parameter_callbacks"] = callback_diagnostics
    callbacks = rack.op("parameter_callbacks")
    saved_preset = None
    saved_state = None
    slots = []
    restoration_error = None
    try:
        saved_preset = rack.ExportPreset(
            "rack-selection-validator-snapshot",
            indent=0,
        )
        saved_state = dict(rack.PresetData(""))

        for index in range(1, SLOT_COUNT + 1):
            original, original_id = _slot_state(rack, index)
            parameter = rack.par["Slot{}effect".format(index)]
            if parameter is None or original_id is None:
                raise RuntimeError(
                    "Slot {} must contain a package for selection QA".format(index)
                )
            alternative_id = _choose_alternative(parameter, original_id)

            parameter.val = alternative_id
            # Parameter Execute DAT events are deferred until the current
            # Textport/execute_python script returns. Invoke the same tracked
            # callback module synchronously so this one-shot validator can
            # inspect the loaded component before yielding the frame.
            callbacks.module.onValueChange(parameter, original_id)
            rack.cook(force=True)
            output.cook(force=True)
            changed, changed_id = _slot_state(rack, index)
            loaded = rack.op("slot{}".format(index))
            changed_checks = {
                "menu_changed": str(parameter.eval()) == alternative_id,
                "package_changed": changed_id == alternative_id,
                "component_loaded": loaded is not None,
                "component_has_output": (
                    loaded is not None and len(loaded.outputConnectors) > 0
                ),
            }

            parameter.val = original_id
            callbacks.module.onValueChange(parameter, alternative_id)
            rack.cook(force=True)
            output.cook(force=True)
            restored, restored_id = _slot_state(rack, index)
            restored_checks = {
                "menu_restored": str(parameter.eval()) == original_id,
                "package_restored": restored_id == original_id,
                "state_restored": restored == original,
            }
            slots.append(
                {
                    "slot": index,
                    "original_package": original.get("package"),
                    "alternative_package": changed.get("package"),
                    "changed_checks": changed_checks,
                    "restored_checks": restored_checks,
                    "ok": (
                        all(changed_checks.values())
                        and all(restored_checks.values())
                    ),
                }
            )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        if saved_preset is not None:
            try:
                rack.ImportPreset(saved_preset)
                rack.cook(force=True)
                output.cook(force=True)
            except Exception as exc:
                restoration_error = "{}: {}".format(type(exc).__name__, exc)

    final_state = None
    if saved_state is not None and restoration_error is None:
        try:
            final_state = dict(rack.PresetData(""))
        except Exception as exc:
            restoration_error = "{}: {}".format(type(exc).__name__, exc)

    rack_errors = _messages(rack, "errors")
    rack_warnings = _messages(rack, "warnings")
    output_errors = _messages(output, "errors")
    output_warnings = _messages(output, "warnings")
    state_restored = (
        saved_state is not None
        and final_state is not None
        and final_state == saved_state
    )
    report.update(
        {
            "slots": slots,
            "slot_count": len(slots),
            "state_restored": state_restored,
            "restoration_error": restoration_error,
            "rack_errors": rack_errors,
            "rack_warnings": rack_warnings,
            "output_errors": output_errors,
            "output_warnings": output_warnings,
        }
    )
    report["ok"] = (
        report.get("error") is None
        and callback_diagnostics.get("ok") is True
        and len(slots) == SLOT_COUNT
        and all(item["ok"] for item in slots)
        and state_restored
        and restoration_error is None
        and not rack_errors
        and not rack_warnings
        and not output_errors
        and not output_warnings
    )

    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
