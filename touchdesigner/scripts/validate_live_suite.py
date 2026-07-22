"""Run every TD ImageFX live validator from one TouchDesigner Textport call.

Use a disposable development harness because several validators temporarily
change rack selections and module parameters.  Every validator restores its
own state in a ``finally`` block, and this runner never saves the project.

Run from TouchDesigner's Textport, replacing the checkout path::

    script = r"C:/path/to/td-imagefx-library/touchdesigner/scripts/validate_live_suite.py"
    scope = dict(globals())
    scope.update({"__file__": script, "__name__": "__main__"})
    exec(compile(open(script, encoding="utf-8").read(), script, "exec"), scope)

Copying the Textport globals is intentional: the rendered-pixel validators use
TouchDesigner-provided names such as ``op``, ``app``, ``root``, ``textDAT``,
and ``glslTOP``.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "touchdesigner" / "scripts"
REPORT_PATH = PROJECT_ROOT / "build" / "envoy-validation" / "live-suite.json"

VALIDATORS = (
    ("live_project", "validate_live_project.py"),
    ("output_resolution", "validate_output_resolution.py"),
    ("rack_selection", "validate_rack_selection.py"),
    ("ink_flow", "validate_ink_flow_module.py"),
    ("random_particles", "validate_particle_module.py"),
    ("glitch_fusion", "validate_glitch_fusion_module.py"),
    ("color_adjustment", "validate_color_adjustment_module.py"),
    ("motion_studio", "validate_motion_studio_module.py"),
    ("reference_video_modules", "validate_reference_video_modules.py"),
    ("all_effect_parameters", "validate_all_effect_parameters.py"),
)


def _run_validator(name, filename):
    script_path = SCRIPT_ROOT / filename
    if not script_path.is_file():
        raise RuntimeError("Missing live validator: {}".format(script_path))

    scope = dict(globals())
    scope.update(
        {
            "__file__": str(script_path),
            "__name__": "_tdimagefx_live_suite_{}".format(name),
        }
    )
    source = script_path.read_text(encoding="utf-8")
    exec(compile(source, str(script_path), "exec"), scope)
    validator = scope.get("validate")
    if not callable(validator):
        raise RuntimeError("{} does not expose validate()".format(filename))

    result = validator(write_report=True)
    if not isinstance(result, dict):
        raise RuntimeError("{} returned a non-dictionary report".format(filename))
    failed_checks = [
        key for key, value in result.get("checks", {}).items() if value is False
    ]
    return {
        "name": name,
        "script": filename,
        "ok": result.get("ok") is True,
        "failed_checks": failed_checks,
        "generated_at": result.get("generated_at"),
    }


def validate(write_report=True):
    """Run the complete live suite, continue after failures, and summarize it."""

    results = []
    for name, filename in VALIDATORS:
        print("[validate_live_suite] Running {}...".format(name))
        try:
            result = _run_validator(name, filename)
        except Exception as error:
            result = {
                "name": name,
                "script": filename,
                "ok": False,
                "failed_checks": [],
                "error": "{}: {}".format(type(error).__name__, error),
                "traceback": traceback.format_exc(),
            }
        results.append(result)
        print(
            "[validate_live_suite] {}: {}".format(
                name, "PASS" if result["ok"] else "FAIL"
            )
        )

    report = {
        "schema_version": 1,
        "project_id": "td-imagefx-library",
        "validator": "live-suite",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(item["ok"] for item in results),
        "validator_count": len(results),
        "validators": results,
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
