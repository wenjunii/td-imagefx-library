"""Real-frame recall/media and pulse QA; never opens windows or enables sound.

Load into a temporary Text DAT, then call its module.start(). Uses generated
show-image-fixture.png and show-av-fixture.mp4 from the show media validators.
Creates a disposable Show Control copy and never saves the TOE.
"""
import copy
import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_STATE = {}


def _pixels(top):
    top.cook(force=True)
    data = top.numpyArray(delayed=False)
    if data is None or not np.isfinite(data).all() or top.errors():
        raise RuntimeError("Invalid preview pixels")
    return hashlib.sha256(data.tobytes()).hexdigest()


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def start():
    global _STATE
    if _STATE.get("running"):
        raise RuntimeError("Look media QA is already running")
    original = op("/project1/imagefx_demo/show_control")
    if original.ext.ShowControlExt.engine.state != "stopped" or original.ext.ShowControlExt._look_edit is not None:
        raise RuntimeError("Stop All and finish any look draft before QA")
    folder = Path(original.par.Libraryroot.eval()) / "build/envoy-validation"
    for name in ("show-image-fixture.png", "show-av-fixture.mp4"):
        if not (folder / name).is_file():
            raise RuntimeError("Missing generated fixture: " + name)
    show = original.parent().copy(original, name="show_look_media_qa")
    show.initializeExtensions()
    show.par.Audioenabled = False
    show.par.Masterblackout = True
    show.par.Renderwidth, show.par.Renderheight = 320, 180
    ext = show.ext.ShowControlExt
    _STATE = dict(running=True, show=show, folder=folder, started=time.monotonic(),
                  stage="recall_image", checks={}, main=ext._capture_look(show.parent()))
    ext._replace_cues([dict(ext.model.new_cue(), source=str(folder / "show-image-fixture.png"))])
    ext.SelectCue(1)
    _STATE["original"] = copy.deepcopy(ext.document)
    # Newly copied Parameter Execute DATs register their watched parameters on
    # the next TD frame; don't pulse the just-created copy in the creation frame.
    _later()


def _later():
    run("op({!r}).module.advance()".format(me.path), delayFrames=15)


def advance():
    show, checks = _STATE["show"], _STATE["checks"]
    ext = show.ext.ShowControlExt
    try:
        if time.monotonic() - _STATE["started"] > 50:
            raise RuntimeError("Look media QA timed out: " + show.par.Status.eval())
        stage = _STATE["stage"]
        draft = show.op("look_editor")
        if stage == "recall_image":
            show.par.Recalllook.pulse()
            _STATE["stage"] = "image"
        elif stage in {"image", "video"}:
            if draft is None:
                raise RuntimeError("Recall pulse failed: " + show.par.Status.eval())
            movie = draft.op("media")
            movie.cook(force=True)
            if movie.isInvalid:
                raise RuntimeError("Recalled media could not be decoded")
            if not movie.isOpen or not movie.isFullyPreRead:
                _later(); return
            _STATE["hash"] = _pixels(show.op("look_preview"))
            checks[stage + "_recall_decodes_real_media"] = True
            _require(not ext.audio and not show.op("stereo_output").par.active, "Preview created audible output")
            _require(not ext.tracks and ext.engine.state == "stopped", "Recall started the show")
            checks["preview_silent_and_off_air"] = True
            if stage == "image":
                draft.par.Coloradjustmentenabled = True
                draft.op("color_adjustment").par.Invert = .75
                show.par.Updatelook.pulse()
                _STATE["stage"] = "updated"
            else:
                _require(movie.par.speed.eval() == 1.5 and movie.par.cuepoint.eval() == .5 and
                         movie.par.textendright.eval() == "cycle", "Video playback settings lost")
                checks["video_speed_loop_and_inpoint"] = True
                _STATE["stage"] = "video_advance"
        elif stage == "updated":
            _require(draft is None and ext._look_edit is None, "Update pulse did not finish")
            _require(ext.document["cues"][0]["look"]["modules"]["color_adjustment"]["Invert"] == .75,
                     "Update pulse did not capture values")
            checks["real_update_pulse_commits"] = True
            _STATE["updated"] = copy.deepcopy(ext.document)
            show.par.Recalllook.pulse()
            _STATE["stage"] = "cancel"
        elif stage == "cancel":
            _require(draft is not None, "Second recall failed")
            draft.op("color_adjustment").par.Invert = .1
            show.par.Cancellook.pulse()
            _STATE["stage"] = "cancelled"
        elif stage == "cancelled":
            _require(draft is None and ext.document == _STATE["updated"], "Cancel pulse changed saved look")
            checks["real_cancel_pulse_preserves_original"] = True
            ext._replace_cues([dict(ext.model.new_cue(), source=str(_STATE["folder"] / "show-av-fixture.mp4"),
                                   movie_audio=True, media_in=.5, speed=1.5, loop=True)])
            ext.SelectCue(1)
            _STATE["video_original"] = copy.deepcopy(ext.document["cues"][0])
            show.par.Recalllook.pulse()
            _STATE["stage"] = "video"
        elif stage == "video_advance":
            _require(_STATE["hash"] != _pixels(show.op("look_preview")), "Video preview is frozen")
            checks["recalled_video_frames_advance"] = True
            draft.par.Coloradjustmentenabled = True
            draft.op("color_adjustment").par.Invert = .5
            show.par.Savelookasnew.pulse()
            _STATE["stage"] = "saved_new"
        elif stage == "saved_new":
            _require(draft is None and len(ext.document["cues"]) == 2, "Save New pulse failed")
            _require(ext.document["cues"][0] == _STATE["video_original"], "Save New modified the original")
            _require(not ext.document["cues"][1]["enabled"], "New copy was not disarmed")
            checks["real_save_new_pulse_preserves_original"] = True
            show.par.Recalllook.pulse()
            _STATE["stage"] = "restart"
        elif stage == "restart":
            _require(draft is not None, "Recall disabled copy failed")
            restart = show.parent().copy(show, name="show_look_restart_qa")
            try:
                restart.initializeExtensions()
                _require(restart.op("look_editor") is None and not restart.par.Lookediting,
                         "Saved/reinitialized show retained a draft")
                _require(restart.op("look_preview").par.top.eval() == restart.op("black"), "Stale preview after restart")
                checks["restart_discards_draft_and_disconnects_preview"] = True
            finally:
                restart.destroy()
            ext.CancelLook()
            ext._replace_cues([dict(ext.model.new_cue(), source=str(_STATE["folder"] / "missing-look-fixture.png"))])
            ext.SelectCue(1)
            _STATE["missing_original"] = copy.deepcopy(ext.document)
            show.par.Recalllook.pulse()
            _STATE["stage"] = "missing"
        elif stage == "missing":
            _require(draft is None and ext._look_edit is None and "Missing media" in show.par.Status.eval(),
                     "Missing-media recall did not fail cleanly")
            _require(ext.document == _STATE["missing_original"], "Missing media changed a cue")
            checks["missing_media_pulse_preserves_cue"] = True
            _require(ext._capture_look(show.parent()) == _STATE["main"], "QA modified the main designer")
            checks["main_workflow_unchanged"] = True
            _finish()
            return
        _later()
    except Exception:
        _finish(traceback.format_exc())


def _finish(error=None):
    show = _STATE["show"]
    try:
        if show.ext.ShowControlExt._look_edit is not None:
            show.ext.ShowControlExt.CancelLook()
    finally:
        show.destroy()
        _STATE["running"] = False
    report = dict(ok=error is None, generated_at=datetime.now(timezone.utc).isoformat(),
                  checks=_STATE["checks"], error=error, hardware_outputs_tested=False, audio_auditioned=False)
    (_STATE["folder"] / "look-editor-media.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
