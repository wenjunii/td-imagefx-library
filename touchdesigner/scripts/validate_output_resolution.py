"""Live validation for HD, 4K UHD, and custom demo output resolutions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    PROJECT_ROOT / "build" / "envoy-validation" / "output-resolution.json"
)
DEMO_PATH = "/project1/imagefx_demo"
SOURCE_PATH = DEMO_PATH + "/source_image"
OUTPUT_PATH = DEMO_PATH + "/out1_image"
EXPECTED_PRESETS = ("hd", "uhd4k", "custom")


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


def _cook_resolution(source, output):
    source.cook(force=True)
    output.cook(force=True)
    return {
        "source": [int(source.width), int(source.height)],
        "output": [int(output.width), int(output.height)],
    }


def validate(write_report=True):
    """Exercise the default HD, 4K UHD, and nonstandard custom resolutions."""

    demo = op(DEMO_PATH)
    source = op(SOURCE_PATH)
    output = op(OUTPUT_PATH)
    missing = [
        name
        for name, operator in (
            ("demo", demo),
            ("source", source),
            ("output", output),
        )
        if operator is None
    ]
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
        report["error"] = "Required output-resolution operators are missing"
        if write_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    saved = {
        "preset": demo.par.Resolutionpreset.eval(),
        "custom_width": demo.par.Customwidth.eval(),
        "custom_height": demo.par.Customheight.eval(),
        "output_display": bool(output.display),
        "opviewer": (
            demo.par.opviewer.eval()
            if getattr(demo.par, "opviewer", None) is not None
            else None
        ),
    }
    try:
        # Keep native validation offscreen. Cooking a 4K TOP is the behavior
        # under test; presenting it in an operator viewer can also exercise
        # the GPU window-output path and produce unrelated driver dialogs.
        output.display = False
        if saved["opviewer"] is not None:
            demo.par.opviewer = ""

        menu_names = tuple(
            str(item) for item in demo.par.Resolutionpreset.menuNames
        )
        default_preset = str(demo.par.Resolutionpreset.default)
        default_custom = [
            int(demo.par.Customwidth.default),
            int(demo.par.Customheight.default),
        ]

        demo.par.Resolutionpreset = "hd"
        hd = _cook_resolution(source, output)

        demo.par.Resolutionpreset = "uhd4k"
        uhd4k = _cook_resolution(source, output)

        demo.par.Resolutionpreset = "custom"
        demo.par.Customwidth = 1234
        demo.par.Customheight = 678
        custom = _cook_resolution(source, output)

        output_errors = _messages(output, "errors")
        output_warnings = _messages(output, "warnings")
        checks = {
            "preset_menu_is_exact": menu_names == EXPECTED_PRESETS,
            "default_preset_is_hd": default_preset == "hd",
            "default_custom_size_is_1920_by_1080": (
                default_custom == [1920, 1080]
            ),
            "hd_output_is_1920_by_1080": (
                hd["output"] == [1920, 1080]
            ),
            "uhd4k_output_is_3840_by_2160": (
                uhd4k["output"] == [3840, 2160]
            ),
            "custom_output_is_adjustable": (
                custom["output"] == [1234, 678]
            ),
            "generated_source_follows_selected_resolution": (
                hd["source"] == hd["output"]
                and uhd4k["source"] == uhd4k["output"]
                and custom["source"] == custom["output"]
            ),
            "custom_width_is_bounded": (
                int(demo.par.Customwidth.min) == 16
                and int(demo.par.Customwidth.max) == 8192
                and bool(demo.par.Customwidth.clampMin)
                and bool(demo.par.Customwidth.clampMax)
            ),
            "custom_height_is_bounded": (
                int(demo.par.Customheight.min) == 16
                and int(demo.par.Customheight.max) == 8192
                and bool(demo.par.Customheight.clampMin)
                and bool(demo.par.Customheight.clampMax)
            ),
            "output_has_no_errors": not output_errors,
            "output_has_no_warnings": not output_warnings,
        }
        report.update(
            {
                "checks": checks,
                "preset_menu": list(menu_names),
                "resolutions": {
                    "hd": hd,
                    "uhd4k": uhd4k,
                    "custom": custom,
                },
                "output_errors": output_errors,
                "output_warnings": output_warnings,
                "ok": all(checks.values()),
            }
        )
    except Exception as exc:
        report["error"] = "{}: {}".format(type(exc).__name__, exc)
    finally:
        demo.par.Resolutionpreset = saved["preset"]
        demo.par.Customwidth = saved["custom_width"]
        demo.par.Customheight = saved["custom_height"]
        output.display = saved["output_display"]
        if saved["opviewer"] is not None:
            demo.par.opviewer = saved["opviewer"]
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
