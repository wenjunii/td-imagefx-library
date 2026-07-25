"""Live validation for ImageFX rack sliders and every pulse-style button.

This validator complements the rendered-pixel effect/module sweeps. It
exercises all eight rack control groups, every rack pulse, the library,
browser, and updater buttons, and the callback DAT wiring that makes a visible
TouchDesigner button do work. Rack and browser state are restored in a
``finally`` block, the project is never saved, and the preset button writes
only the ignored ``presets/.qa-control-surface.json`` runtime fixture.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "build" / "envoy-validation" / "control-surface.json"
)
LIBRARY_PATH = "/project1/td_imagefx"
UPDATER_PATH = LIBRARY_PATH + "/update_manager"
BROWSER_PATH = LIBRARY_PATH + "/core/fx_browser"
RACK_PATH = "/project1/imagefx_demo/fx_rack"
OUTPUT_PATH = RACK_PATH + "/out1_image"
SLOT_COUNT = 8
EXPECTED_PULSE_BUTTON_COUNT = 45
QA_PRESET_PATH = ".qa-control-surface.json"

RACK_GLOBAL_PULSES = (
    "Exportpreset",
    "Importpreset",
    "Savepreset",
    "Loadpreset",
    "Reloadall",
    "Reset",
    "Bypassall",
    "Enableall",
)
RACK_SLOT_PULSE_SUFFIXES = ("up", "down", "reset", "bypass")


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


def _parameter_value(component, name):
    parameter = component.par[name]
    if parameter is None:
        raise RuntimeError(
            "{} is missing parameter {}".format(component.path, name)
        )
    return parameter.eval()


def _callback_diagnostics(component, expected_names):
    callbacks = component.op("parameter_callbacks")
    if callbacks is None:
        return {
            "ok": False,
            "exists": False,
            "errors": ["parameter_callbacks is missing"],
        }
    watched = str(callbacks.par.pars.eval())
    checks = {
        "targets_owner": callbacks.par.op.eval() == component,
        "pulse_enabled": bool(callbacks.par.onpulse.eval()),
        "custom_parameters_enabled": bool(callbacks.par.custom.eval()),
        "watches_expected_parameters": all(
            name in watched or ("Slot" in name and "Slot*" in watched)
            for name in expected_names
        ),
    }
    errors = _messages(callbacks, "errors")
    warnings = _messages(callbacks, "warnings")
    return {
        "ok": all(checks.values()) and not errors and not warnings,
        "exists": True,
        "path": callbacks.path,
        "watched_parameters": watched,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def _invoke_pulse(component, callbacks, name):
    parameter = component.par[name]
    if parameter is None:
        raise RuntimeError(
            "{} is missing pulse {}".format(component.path, name)
        )
    parameter.pulse()
    component.cook(force=True)


def _slot_packages(rack):
    return [
        (rack.SlotState(index).get("package") or {}).get("id")
        for index in range(1, SLOT_COUNT + 1)
    ]


def _slot_enables(rack):
    return [
        bool(rack.par["Slot{}enable".format(index)].eval())
        for index in range(1, SLOT_COUNT + 1)
    ]


def _rack_value_controls(rack, callbacks):
    results = []

    rack.par.Autotime = False
    rack.par.Timescale = 1.0
    rack.par.Manualtime = 0.25
    low_time = float(rack.par.Time.eval())
    rack.par.Manualtime = 1.75
    high_time = float(rack.par.Time.eval())
    results.append(
        {
            "name": "Manualtime",
            "ok": (
                math.isclose(low_time, 0.25, abs_tol=1.0e-6)
                and math.isclose(high_time, 1.75, abs_tol=1.0e-6)
            ),
        }
    )
    rack.par.Autotime = True
    rack.par.Timescale = 0.0
    zero_scaled_time = float(rack.par.Time.eval())
    rack.par.Timescale = -2.0
    reverse_scaled_time = float(rack.par.Time.eval())
    results.append(
        {
            "name": "Timescale",
            "ok": (
                math.isclose(zero_scaled_time, 0.0, abs_tol=1.0e-6)
                and reverse_scaled_time < 0.0
            ),
            "zero_scaled_time": zero_scaled_time,
            "reverse_scaled_time": reverse_scaled_time,
        }
    )
    rack.par.Autotime = False
    rack.par.Timescale = 1.0

    for index in range(1, SLOT_COUNT + 1):
        slot = rack.op("slot{}".format(index))
        if slot is None:
            raise RuntimeError("Rack slot {} is missing".format(index))

        enable = rack.par["Slot{}enable".format(index)]
        original_enable = bool(enable.eval())
        enable.val = False
        rack.cook(force=True)
        disabled = not bool(slot.par.Enable.eval())
        enable.val = True
        rack.cook(force=True)
        enabled = bool(slot.par.Enable.eval())
        enable.val = original_enable
        results.append(
            {
                "name": enable.name,
                "ok": disabled and enabled,
            }
        )

        rack.par["Slot{}moddepth".format(index)].val = 0.0
        rack.par["Slot{}modstate".format(index)].val = "off"
        mix = rack.par["Slot{}mix".format(index)]
        original_mix = float(mix.eval())
        mix.val = 0.21
        rack.cook(force=True)
        low_mix = float(slot.par.Mix.eval())
        mix.val = 0.79
        rack.cook(force=True)
        high_mix = float(slot.par.Mix.eval())
        mix.val = original_mix
        results.append(
            {
                "name": mix.name,
                "ok": (
                    math.isclose(low_mix, 0.21, abs_tol=1.0e-6)
                    and math.isclose(high_mix, 0.79, abs_tol=1.0e-6)
                ),
            }
        )

        depth = rack.par["Slot{}moddepth".format(index)]
        original_depth = float(depth.eval())
        depth.val = 0.37
        callbacks.module.onValueChange(depth, original_depth)
        depth_state = dict(rack.ModulationState(index))
        depth.val = original_depth
        callbacks.module.onValueChange(depth, 0.37)
        results.append(
            {
                "name": depth.name,
                "ok": math.isclose(
                    float(depth_state["depth"]), 0.37, abs_tol=1.0e-6
                ),
            }
        )

        rate = rack.par["Slot{}modrate".format(index)]
        original_rate = float(rate.eval())
        rate.val = 2.75
        callbacks.module.onValueChange(rate, original_rate)
        rate_state = dict(rack.ModulationState(index))
        rate.val = original_rate
        callbacks.module.onValueChange(rate, 2.75)
        results.append(
            {
                "name": rate.name,
                "ok": math.isclose(
                    float(rate_state["rate"]), 2.75, abs_tol=1.0e-6
                ),
            }
        )

        modulation = rack.par["Slot{}modstate".format(index)]
        original_modulation = str(modulation.eval())
        modulation.val = "triangle"
        callbacks.module.onValueChange(modulation, original_modulation)
        modulation_state = dict(rack.ModulationState(index))
        modulation.val = original_modulation
        callbacks.module.onValueChange(modulation, "triangle")
        results.append(
            {
                "name": modulation.name,
                "ok": modulation_state["state"] == "triangle",
            }
        )

    return results


def _rack_buttons(rack, output, callbacks):
    results = []

    _invoke_pulse(rack, callbacks, "Exportpreset")
    exported = str(rack.par.Presetjson.eval())
    parsed = json.loads(exported)
    results.append(
        {
            "name": "Exportpreset",
            "ok": (
                parsed.get("schema_version") == 1
                and len(parsed.get("slots", [])) == SLOT_COUNT
            ),
        }
    )

    rack.par.Presetjson = exported
    _invoke_pulse(rack, callbacks, "Importpreset")
    results.append(
        {
            "name": "Importpreset",
            "ok": rack.PresetData(parsed.get("name", "")) == parsed,
        }
    )

    rack.par.Presetpath = QA_PRESET_PATH
    _invoke_pulse(rack, callbacks, "Savepreset")
    saved_path = PROJECT_ROOT / "presets" / QA_PRESET_PATH
    results.append(
        {
            "name": "Savepreset",
            "ok": saved_path.is_file() and saved_path.stat().st_size > 0,
        }
    )
    _invoke_pulse(rack, callbacks, "Loadpreset")
    results.append(
        {
            "name": "Loadpreset",
            "ok": rack.PresetData(parsed.get("name", "")) == parsed,
        }
    )

    before_reload = _slot_packages(rack)
    _invoke_pulse(rack, callbacks, "Reloadall")
    output.cook(force=True)
    results.append(
        {
            "name": "Reloadall",
            "ok": _slot_packages(rack) == before_reload,
        }
    )

    _invoke_pulse(rack, callbacks, "Reset")
    results.append(
        {
            "name": "Reset",
            "ok": not _messages(rack, "errors"),
        }
    )

    _invoke_pulse(rack, callbacks, "Bypassall")
    bypassed = not any(_slot_enables(rack))
    _invoke_pulse(rack, callbacks, "Enableall")
    enabled = all(_slot_enables(rack))
    results.extend(
        (
            {"name": "Bypassall", "ok": bypassed},
            {"name": "Enableall", "ok": enabled},
        )
    )

    for index in range(1, SLOT_COUNT + 1):
        before = bool(rack.par["Slot{}enable".format(index)].eval())
        name = "Slot{}bypass".format(index)
        _invoke_pulse(rack, callbacks, name)
        changed = bool(rack.par["Slot{}enable".format(index)].eval())
        _invoke_pulse(rack, callbacks, name)
        restored = bool(rack.par["Slot{}enable".format(index)].eval())
        results.append(
            {
                "name": name,
                "ok": changed != before and restored == before,
            }
        )

        reset_name = "Slot{}reset".format(index)
        _invoke_pulse(rack, callbacks, reset_name)
        results.append(
            {
                "name": reset_name,
                "ok": not _messages(rack, "errors"),
            }
        )

    before_boundary = _slot_packages(rack)
    _invoke_pulse(rack, callbacks, "Slot1up")
    results.append(
        {
            "name": "Slot1up",
            "ok": _slot_packages(rack) == before_boundary,
        }
    )
    _invoke_pulse(rack, callbacks, "Slot8down")
    results.append(
        {
            "name": "Slot8down",
            "ok": _slot_packages(rack) == before_boundary,
        }
    )

    for index in range(2, SLOT_COUNT + 1):
        before = _slot_packages(rack)
        up_name = "Slot{}up".format(index)
        down_name = "Slot{}down".format(index - 1)
        _invoke_pulse(rack, callbacks, up_name)
        moved = _slot_packages(rack)
        expected = list(before)
        expected[index - 2], expected[index - 1] = (
            expected[index - 1],
            expected[index - 2],
        )
        _invoke_pulse(rack, callbacks, down_name)
        restored = _slot_packages(rack)
        results.extend(
            (
                {"name": up_name, "ok": moved == expected},
                {"name": down_name, "ok": restored == before},
            )
        )

    return results


def _library_button(library, callbacks):
    before_ids = list(library.PackageIds)
    before_rows = int(library.op("catalog").numRows)
    _invoke_pulse(library, callbacks, "Refreshcatalog")
    after_ids = list(library.PackageIds)
    after_rows = int(library.op("catalog").numRows)
    return {
        "name": "Refreshcatalog",
        "ok": (
            len(after_ids) == 96
            and after_ids == before_ids
            and after_rows == before_rows == 97
            and str(library.par.Status.eval()).startswith("Ready: 96")
        ),
    }


def _browser_buttons(browser, callbacks):
    results = []
    result_table = browser.op("results")
    before_rows = int(result_table.numRows)
    _invoke_pulse(browser, callbacks, "Refresh")
    after_rows = int(result_table.numRows)
    refresh_status = str(browser.par.Status.eval())
    results.append(
        {
            "name": "Refresh",
            "ok": (
                before_rows > 1
                and after_rows > 1
                and "effects" in refresh_status
                and not refresh_status.startswith("Error:")
            ),
            "before_rows": before_rows,
            "after_rows": after_rows,
            "status": refresh_status,
        }
    )

    before_favorites = str(browser.par.Favorites.eval())
    _invoke_pulse(browser, callbacks, "Togglefavorite")
    changed_favorites = str(browser.par.Favorites.eval())
    _invoke_pulse(browser, callbacks, "Togglefavorite")
    restored_favorites = str(browser.par.Favorites.eval())
    results.append(
        {
            "name": "Togglefavorite",
            "ok": (
                changed_favorites != before_favorites
                and restored_favorites == before_favorites
            ),
        }
    )

    target = browser.par.Target
    saved_expression = str(target.expr)
    try:
        target.expr = "None"
        _invoke_pulse(browser, callbacks, "Create")
        create_status = str(browser.par.Status.eval())
        results.append(
            {
                "name": "Create",
                "ok": (
                    "Error:" in create_status
                    and "Target COMP" in create_status
                ),
            }
        )
    finally:
        target.expr = saved_expression
        browser.UpdateSelection()

    return results


def _updater_button(updater, callbacks):
    _invoke_pulse(updater, callbacks, "Checkupdates")
    status_started = "Checking for updates" in str(updater.par.Status.eval())
    extension = updater.ext.UpdaterExt
    thread = getattr(extension, "_thread", None)
    started = thread is not None
    deadline = time.time() + float(updater.par.Timeout.eval()) + 5.0
    while thread is not None and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    completed = thread is not None and not thread.is_alive()
    if completed:
        updater.Poll()
    status_finished = str(updater.par.Status.eval())
    return {
        "name": "Checkupdates",
        "ok": (
            status_started
            and started
            and completed
            and bool(str(updater.par.Lastcheck.eval()))
            and "failed" not in status_finished.casefold()
        ),
        "status": status_finished,
    }


def validate(write_report=True):
    """Exercise all rack sliders and every visible pulse button."""

    library = op(LIBRARY_PATH)
    updater = op(UPDATER_PATH)
    browser = op(BROWSER_PATH)
    rack = op(RACK_PATH)
    output = op(OUTPUT_PATH)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": "td-imagefx-library",
        "validator": "control-surface",
        "ok": False,
        "touchdesigner": {
            "version": str(app.version),
            "build": str(app.build),
            "os": str(app.osName),
            "architecture": str(app.architecture),
        },
    }
    missing = [
        name
        for name, operator in (
            ("library", library),
            ("updater", updater),
            ("browser", browser),
            ("rack", rack),
            ("output", output),
        )
        if operator is None
    ]
    report["missing_operators"] = missing
    if missing:
        report["error"] = "Required control-surface operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    library_callbacks = library.op("parameter_callbacks")
    updater_callbacks = updater.op("parameter_callbacks")
    browser_callbacks = browser.op("parameter_callbacks")
    rack_callbacks = rack.op("parameter_callbacks")
    callback_diagnostics = {
        "library": _callback_diagnostics(
            library, ("Refreshcatalog",)
        ),
        "updater": _callback_diagnostics(
            updater, ("Checkupdates",)
        ),
        "browser": _callback_diagnostics(
            browser, ("Refresh", "Create", "Togglefavorite")
        ),
        "rack": _callback_diagnostics(
            rack,
            RACK_GLOBAL_PULSES
            + tuple(
                "Slot{}{}".format(index, suffix)
                for index in range(1, SLOT_COUNT + 1)
                for suffix in RACK_SLOT_PULSE_SUFFIXES
            ),
        ),
    }
    saved_rack_preset = None
    saved_rack_state = None
    saved_rack_ui = {}
    saved_browser = {}
    saved_updater = {}
    saved_library_status = str(library.par.Status.eval())
    value_controls = []
    buttons = []
    restoration_errors = []
    try:
        saved_rack_preset = rack.ExportPreset(
            "control-surface-validator-snapshot", indent=0
        )
        saved_rack_state = dict(rack.PresetData(""))
        saved_rack_ui = {
            name: rack.par[name].eval()
            for name in ("Presetname", "Presetpath", "Presetjson")
        }
        saved_browser = {
            "Favorites": browser.par.Favorites.eval(),
            "Status": browser.par.Status.eval(),
            "Targetexpr": str(browser.par.Target.expr),
        }
        saved_updater = {
            name: updater.par[name].eval()
            for name in (
                "Autocheck",
                "Intervalhours",
                "Channel",
                "Timeout",
                "Lastcheck",
                "Status",
            )
        }

        updater.StopAutoCheck()
        updater.par.Autocheck = False
        updater.par.Timeout = 10.0

        value_controls = _rack_value_controls(rack, rack_callbacks)
        rack.ImportPreset(saved_rack_preset)
        buttons.extend(_rack_buttons(rack, output, rack_callbacks))
        rack.ImportPreset(saved_rack_preset)
        buttons.append(_library_button(library, library_callbacks))
        buttons.extend(_browser_buttons(browser, browser_callbacks))
        buttons.append(_updater_button(updater, updater_callbacks))
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        if saved_rack_preset is not None:
            try:
                rack.ImportPreset(saved_rack_preset)
                for name, value in saved_rack_ui.items():
                    rack.par[name].val = value
                output.cook(force=True)
            except Exception as exc:
                restoration_errors.append(
                    "rack: {}: {}".format(type(exc).__name__, exc)
                )
        if saved_browser:
            try:
                browser.par.Favorites = saved_browser["Favorites"]
                browser.par.Target.expr = saved_browser["Targetexpr"]
                browser.ApplyFilters()
                browser.UpdateSelection()
                browser.par.Status = saved_browser["Status"]
            except Exception as exc:
                restoration_errors.append(
                    "browser: {}: {}".format(type(exc).__name__, exc)
                )
        if saved_updater:
            try:
                updater.StopAutoCheck()
                for name, value in saved_updater.items():
                    updater.par[name].val = value
                if bool(saved_updater["Autocheck"]):
                    updater.StartAutoCheck()
            except Exception as exc:
                restoration_errors.append(
                    "updater: {}: {}".format(type(exc).__name__, exc)
                )
        try:
            library.par.Status = saved_library_status
        except Exception as exc:
            restoration_errors.append(
                "library: {}: {}".format(type(exc).__name__, exc)
            )

    final_rack_state = None
    if saved_rack_state is not None:
        try:
            final_rack_state = dict(rack.PresetData(""))
        except Exception as exc:
            restoration_errors.append(
                "rack-state: {}: {}".format(type(exc).__name__, exc)
            )

    operator_diagnostics = {}
    for name, operator in (
        ("library", library),
        ("updater", updater),
        ("browser", browser),
        ("rack", rack),
        ("output", output),
    ):
        operator_diagnostics[name] = {
            "errors": _messages(operator, "errors"),
            "warnings": _messages(operator, "warnings"),
        }

    button_names = [item["name"] for item in buttons]
    expected_button_names = set(
        ("Refreshcatalog", "Checkupdates", "Refresh", "Create", "Togglefavorite")
        + RACK_GLOBAL_PULSES
        + tuple(
            "Slot{}{}".format(index, suffix)
            for index in range(1, SLOT_COUNT + 1)
            for suffix in RACK_SLOT_PULSE_SUFFIXES
        )
    )
    checks = {
        "all_callback_dats_are_wired": all(
            item.get("ok") for item in callback_diagnostics.values()
        ),
        "every_rack_value_control_responds": (
            len(value_controls) == 42
            and all(item.get("ok") for item in value_controls)
        ),
        "every_pulse_button_was_exercised": (
            len(buttons) == EXPECTED_PULSE_BUTTON_COUNT
            and set(button_names) == expected_button_names
        ),
        "every_pulse_button_works": (
            bool(buttons) and all(item.get("ok") for item in buttons)
        ),
        "rack_state_restored": (
            saved_rack_state is not None
            and final_rack_state == saved_rack_state
        ),
        "complete_state_restoration": not restoration_errors,
        "clean_operator_diagnostics": all(
            not item["errors"] and not item["warnings"]
            for item in operator_diagnostics.values()
        ),
    }
    report.update(
        {
            "checks": checks,
            "callback_diagnostics": callback_diagnostics,
            "value_controls": value_controls,
            "value_control_count": len(value_controls),
            "buttons": buttons,
            "button_count": len(buttons),
            "expected_button_count": EXPECTED_PULSE_BUTTON_COUNT,
            "operator_diagnostics": operator_diagnostics,
            "restoration_errors": restoration_errors,
            "ok": (
                report.get("error") is None
                and all(checks.values())
            ),
        }
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
