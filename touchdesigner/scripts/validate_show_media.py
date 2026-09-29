"""Asynchronous image/video/embedded-audio QA on real TD frames.

Run this source as a Text DAT, then call its module.start(). Requires the
generated show-image-fixture.png and show-av-fixture.mp4 in build/envoy-validation.
Never enables sound or opens an audience window. Restores the cue document.
"""
import copy
import hashlib
import json
import time
import traceback
from pathlib import Path

_STATE = {}


def _snapshot(top):
    top.cook(force=True)
    array=top.numpyArray(delayed=False)
    if array is None: raise RuntimeError("No media pixels")
    return hashlib.sha256(array.tobytes()).hexdigest()


def start():
    global _STATE
    show=me.parent()
    ext=show.ext.ShowControlExt
    if ext.engine.state!="stopped": raise RuntimeError("Stop All before media QA")
    root=Path(show.par.Libraryroot.eval())
    folder=root/"build"/"envoy-validation"
    for filename in ("show-image-fixture.png","show-av-fixture.mp4"):
        if not (folder/filename).is_file(): raise RuntimeError("Missing generated media fixture: "+filename)
    _STATE={"document":copy.deepcopy(ext.document),"values":{p.name:p.eval() for p in show.customPars if not p.isPulse},
            "folder":folder,"stage":"image","started":time.monotonic(),"checks":{}}
    show.par.Audioenabled=False
    show.par.Masterblackout=True
    show.par.Renderwidth=320; show.par.Renderheight=180
    ext._replace_cues([dict(ext.model.new_cue(),source=str(folder/"show-image-fixture.png"),duration=0,fade=0),
                       dict(ext.model.new_cue(),source=str(folder/"show-av-fixture.mp4"),movie_audio=True,duration=0,fade=0,loop=True,media_in=.5,speed=1.5)])
    ext.engine.go(0)
    _later()


def _later():
    run("op({!r}).module.advance()".format(me.path),delayFrames=30)


def advance():
    show=me.parent(); ext=show.ext.ShowControlExt
    try:
        if time.monotonic()-_STATE["started"]>40: raise RuntimeError("Media QA timed out")
        if ext.engine.errors: raise RuntimeError(str(ext.engine.errors))
        stage=_STATE["stage"]
        if stage in {"image","video"}:
            wanted=ext.document["cues"][0 if stage=="image" else 1]["id"]
            active=ext.tracks.get(1)
            if not active or active["cue"]["id"]!=wanted:
                _later(); return
            if not active["movie"].isOpen: raise RuntimeError("Media not open")
            _STATE["checks"][stage+"_decoded_on_real_frames"]=True
            if stage=="image":
                _STATE["image_hash"]=_snapshot(show.op("track1"))
                ext.engine.go(1); _STATE["stage"]="video"; _later(); return
            audio=ext.audio.get(wanted)
            movie=active["movie"]
            if (abs(movie.par.speed.eval()-1.5)>1e-6 or abs(movie.par.cuepoint.eval()-.5)>1e-6
                    or movie.par.cuepointunit.eval()!="seconds" or movie.par.textendright.eval()!="cycle"):
                raise RuntimeError("Video speed, media in or loop control is not bound")
            _STATE["checks"]["video_speed_inpoint_loop_bindings"]=True
            if not audio: raise RuntimeError("Video soundtrack voice missing")
            audio["stereo"].cook(force=True)
            if audio["reader"].errors() or audio["stereo"].numChans!=2: raise RuntimeError("Embedded stereo audio invalid")
            _STATE["checks"]["embedded_stereo_audio_decode"]=True
            _STATE["hash"]=_snapshot(show.op("track1"))
            _STATE["stage"]="motion"; _later(); return
        if stage=="motion":
            if _snapshot(show.op("track1"))==_STATE["hash"]: raise RuntimeError("Playing video frame did not advance")
            _STATE["checks"]["video_frames_advance"]=True
            ext.Pause(); _STATE["paused_time"]=ext.engine.elapsed
            _STATE["hash"]=_snapshot(show.op("track1"))
            _STATE["stage"]="paused"; _later(); return
        if stage=="paused":
            if ext.engine.elapsed!=_STATE["paused_time"] or _snapshot(show.op("track1"))!=_STATE["hash"]:
                raise RuntimeError("Paused video/clock changed")
            if any(item["reader"].par.play for item in ext.audio.values()): raise RuntimeError("Paused audio still playing")
            _STATE["checks"]["pause_freezes_video_audio_clock"]=True
            ext.Resume(); _STATE["stage"]="resumed"; _later(); return
        if stage=="resumed":
            if _snapshot(show.op("track1"))==_STATE["hash"]: raise RuntimeError("Video did not resume")
            _STATE["checks"]["video_resumes"]=True
            if show.par.Audioenabled: raise RuntimeError("QA enabled physical audio")
            ext.engine.stop()
            layer_look={"toggles":{"Layercompositeenabled":True},
                        "modules":{"layer_composite":{"Opacity":.9,"Invert":True}},
                        "layer_files":{"Topfile":str(_STATE["folder"]/"show-image-fixture.png"),
                                       "Backdropfile":str(_STATE["folder"]/"show-image-fixture.png")}}
            ext._replace_cues([
                dict(ext.model.new_cue(),duration=0,fade=0,look=layer_look),
                dict(ext.model.new_cue(),kind="parameters",target="layer_composite/Opacity",value=.2,duration=.25)])
            ext.engine.go(0); _STATE["stage"]="layer"; _later(); return
        if stage=="layer":
            active=ext.tracks.get(1)
            if not active:
                _later(); return
            layer=active["deck"].op("layer_composite")
            if not all(layer.op(name).isOpen and layer.op(name).isFullyPreRead for name in ("top_file","backdrop_file")):
                raise RuntimeError("Layer cue began before both images were ready")
            _STATE["checks"]["layer_images_decoded_before_go"]=True
            _STATE["hash"]=_snapshot(show.op("track1"))
            ext.engine.go(1); _STATE["stage"]="layer_opacity"; _later(); return
        if stage=="layer_opacity":
            layer=ext.tracks[1]["deck"].op("layer_composite")
            if abs(layer.par.Opacity.eval()-.2)>1e-5:
                _later(); return
            if _snapshot(show.op("track1"))==_STATE["hash"]:
                raise RuntimeError("Layer opacity cue did not change pixels")
            _STATE["checks"]["layer_opacity_parameter_cue_pixels"]=True
            finish()
    except Exception:
        finish(traceback.format_exc())


def finish(error=None):
    show=me.parent(); ext=show.ext.ShowControlExt
    ext.engine.stop()
    ext.document=_STATE["document"]
    ext._replace_cues(ext.document["cues"])
    for name,value in _STATE["values"].items(): show.par[name]=value
    show.par.Audioenabled=False; show.par.Masterblackout=True
    ext.SelectCue(1); ext.UpdateMapping()
    report={"ok":error is None,"checks":_STATE["checks"],"error":error,"audio_auditioned":False,"hardware_outputs_tested":False}
    (_STATE["folder"]/"show-media.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("Show media QA:",json.dumps(report))
