"""Run the real-frame control/media checks sequentially after the live suite.

Run in a disposable TD session, with Show Control stopped and outputs disarmed.
Call validate() from Textport with TD globals, as for validate_live_suite.py.
This returns immediately. Wait for deferred-controls.json / PASS before editing
or saving. No audience window or audible audio is enabled by these checks.
"""
from __future__ import annotations

import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "build" / "envoy-validation"
REPORT_PATH = REPORT_DIR / "deferred-controls.json"
RUNNING_KEY = "imagefx_deferred_controls_running"
JOBS = (
    ("rack_events", "validate_control_surface.py", "validate_deferred", "control-events.json", "scope"),
    ("workflow_events", "validate_workflow.py", "validate_deferred", "workflow-deferred.json", "scope"),
    ("wall_events", "validate_wall_output.py", "validate_deferred", "wall-output-events.json", "scope"),
    ("layer_images", "validate_layer_composite.py", "validate_files", "layer-composite-files.json", "scope"),
    ("layer_videos", "validate_layer_composite.py", "validate_videos", "layer-composite-videos.json", "scope"),
    ("show_media", "validate_show_media.py", "start", "show-media.json", "show_dat"),
    ("look_media", "validate_look_editor_media.py", "start", "look-editor-media.json", "dat"),
)
FIXTURES = ("show-image-fixture.png", "show-av-fixture.mp4",
            "layer-top-fixture.png", "layer-backdrop-fixture.png")


def _signature(path):
    """An old successful report must never satisfy a newly scheduled test."""
    if not path.is_file():
        return None
    return path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def _summarize(job, report, source_hash):
    if not isinstance(report, dict):
        raise ValueError("Validator report is not an object")
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError("Validator report has no checks")
    failed = sorted(name for name, value in checks.items() if value is not True)
    error = report.get("error") or report.get("restoration_error")
    return dict(name=job[0], script=job[1], report=job[3], source_sha256=source_hash,
                ok=report.get("ok") is True and not failed and not error,
                check_count=len(checks), failed_checks=failed, error=error)


def validate():
    """Schedule seven real-frame validators; reject unsafe or overlapping runs."""
    demo = op("/project1/imagefx_demo")
    if demo is None:
        raise RuntimeError("ImageFX demo is missing")
    show, wall = demo.op("show_control"), demo.op("wall_output")
    if show is None or wall is None:
        raise RuntimeError("Build Show Control and wall_output first")
    ext = show.ext.ShowControlExt
    if ext.engine.state != "stopped" or ext._look_edit is not None:
        raise RuntimeError("Stop All and finish/cancel the look draft before QA")
    if show.par.Audioenabled or not show.par.Masterblackout or not wall.par.Blackout:
        raise RuntimeError("Disarm audio and enable show/wall blackouts before QA")
    if demo.fetch(RUNNING_KEY, False):
        raise RuntimeError("A deferred control audit is already running")
    missing = [name for name in FIXTURES if not (REPORT_DIR / name).is_file()]
    if missing:
        raise RuntimeError("Missing QA fixtures: {}. Run the live suite and generate the AV fixture; see README.".format(", ".join(missing)))

    state = dict(index=0, results=[], current=None, cleanup=None, finished=False)
    report = dict(schema_version=1, validator="deferred-controls",
                  started_at=datetime.now(timezone.utc).isoformat(), ok=False,
                  hardware_outputs_tested=False, audio_auditioned=False)
    demo.store(RUNNING_KEY, True)

    def finish(error=None, keep_lock=False):
        if state["finished"]:
            return
        state["finished"] = True
        if not keep_lock:
            demo.unstore(RUNNING_KEY)
        report.update(generated_at=datetime.now(timezone.utc).isoformat(),
                      validators=state["results"], validator_count=len(state["results"]),
                      ok=error is None and len(state["results"]) == len(JOBS)
                      and all(item["ok"] for item in state["results"]))
        if error:
            report["error"] = error
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("[deferred-controls] {}: {} validators. {}".format(
            "PASS" if report["ok"] else "FAIL", len(state["results"]), REPORT_PATH))

    def later():
        run("args[0]()", advance, delayMilliSeconds=250,
            wallTime=True, delayRef=op.TDResources)

    def advance():
        if state["finished"]:
            return
        try:
            current = state["current"]
            if current is not None:
                job, path, before, started, source_hash = current
                if _signature(path) == before:
                    if time.monotonic() - started > 180:
                        # Do not destroy operators while their callbacks may still
                        # be queued. Abort; reopen this disposable session without
                        # saving if a validator cannot complete its own cleanup.
                        finish("Timed out waiting for {}. Reopen without saving before another audit.".format(job[0]), keep_lock=True)
                        return
                    later()
                    return
                item = _summarize(job, json.loads(path.read_text(encoding="utf-8")), source_hash)
                if state["cleanup"] is not None:
                    state["cleanup"]()
                state["cleanup"] = None
                state["results"].append(item)
                print("[deferred-controls] {}: {}".format(job[0], "PASS" if item["ok"] else "FAIL"))
                state["current"] = None
                state["index"] += 1
                if not item["ok"]:
                    finish("{} failed; subsequent validators were not run".format(job[0]))
                    return
            if state["index"] == len(JOBS):
                finish()
                return
            job = JOBS[state["index"]]
            script = ROOT / "touchdesigner" / "scripts" / job[1]
            source = script.read_text(encoding="utf-8")
            path = REPORT_DIR / job[3]
            state["current"] = (job, path, _signature(path), time.monotonic(),
                                 hashlib.sha256(source.encode("utf-8")).hexdigest())
            print("[deferred-controls] Running {}...".format(job[0]))
            if job[4] == "scope":
                scope = dict(globals(), __file__=str(script), __name__="_deferred_" + job[0])
                exec(compile(source, str(script), "exec"), scope)
                scope[job[2]]()
            else:
                if job[4] == "show_dat":
                    parent = demo.copy(show, name="show_media_audit")
                    state["cleanup"] = parent.destroy
                    parent.initializeExtensions()
                    dat = parent.create(textDAT, "media_audit")
                else:
                    dat = demo.create(textDAT, "look_media_audit")
                    state["cleanup"] = dat.destroy
                dat.text = source
                # Newly copied Parameter Execute DATs register on the next frame.
                run("args[0]()", getattr(dat.module, job[2]), delayFrames=2)
            later()
        except Exception:
            # An interrupted validator can still own queued callbacks. Keep the
            # overlap guard until the disposable project is reopened unsaved.
            finish(traceback.format_exc() + "\nReopen without saving before another audit.", keep_lock=True)

    advance()
    return dict(scheduled=True, report=str(REPORT_PATH), validator_count=len(JOBS))


if __name__ == "__main__":
    print(validate())
