"""Software-only cue/mapping QA. Never opens audience windows or enables audio.

Run in a disposable local build. Restores the cue document and controls, and
never saves the TOE. Physical displays, listening tests and long show rehearsals
remain necessary; this is not a show-readiness certification.
"""
from __future__ import annotations

import copy
import json
import math
import struct
import traceback
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "build" / "envoy-validation" / "show-control.json"


def validate(write_report=True):
    show = op("/project1/imagefx_demo/show_control")
    if show is None:
        raise RuntimeError("Build the show-control module first")
    ext = show.ext.ShowControlExt
    if ext.engine.state != "stopped":
        raise RuntimeError("Stop All before running show-control QA")
    original = copy.deepcopy(ext.document)
    values = {p.name: p.eval() for p in show.customPars if not p.isPulse}
    tick_active = show.op("show_tick").par.active.eval()
    show.op("show_tick").par.active = False
    checks, details = {}, {}
    coverage = {}

    def require(condition, description):
        if not condition:
            raise AssertionError(description)

    def pixels(name):
        node = show.op(name)
        node.cook(force=True)
        data = node.numpyArray(delayed=False)
        require(data is not None and np.isfinite(data).all(), name + " invalid pixels")
        require(not node.errors(), name + ": " + node.errors())
        return data.copy()

    def cue(**kwargs):
        return dict(ext.model.new_cue(), **kwargs)

    clock = [0.0]
    def load(cues):
        ext.engine.stop()
        ext._replace_cues(cues)
        ext.engine.clock = lambda: clock[0]
        clock[0] = 0
        ext.engine._last = 0

    def step(now):
        clock[0] = now
        ext.engine.tick()
        ext.UpdateMapping()
        require(not ext.engine.errors, str(ext.engine.errors))

    try:
        show.par.Audioenabled = False
        show.par.Renderwidth, show.par.Renderheight = 320, 180
        for i in (1, 2, 3):
            show.par["Output{}width".format(i)] = 320
            show.par["Output{}height".format(i)] = 180
        show.par.Masterblackout = False
        show.par.Routingmode = "identical"
        ext.UpdateMapping()
        load([cue(duration=0, fade=0)])
        ext.engine.go(0); step(0)
        a = pixels("mapped1")
        require(np.std(a[:,:,:3]) > .01, "Visual cue must produce a visible pattern")
        require(np.allclose(a, pixels("mapped2")), "Identical mapping differs")
        require(np.allclose(a, pixels("mapped3")), "Third identical output differs")
        image_fixture=ROOT/"build"/"envoy-validation"/"show-image-fixture.png"
        image_fixture.parent.mkdir(parents=True,exist_ok=True)
        show.op("mapped1").save(str(image_fixture))
        checks["visual_go_and_identical_three_outputs"] = True

        show.par.Masterblackout = True
        require(np.max(pixels("mapped1")[:,:,:3]) == 0, "Blackout failed")
        show.par.Masterblackout = False
        show.par.Output1blackout = True
        require(np.max(pixels("mapped1")[:,:,:3]) == 0 and np.max(pixels("mapped2")[:,:,:3]) > 0, "Per output blackout failed")
        show.par.Output1blackout = False
        checks["master_and_individual_blackouts"] = True

        # Every per-output numeric mapping/grade control must visibly respond.
        sweeps = {"brightness": .25, "gamma": 2.5, "rotate": 24, "cropleft": .25, "cropright": .75, "cropbottom": .25, "croptop": .75,
                  "edgeleft": .4, "edgeright": .4, "edgebottom": .4, "edgetop": .4,
                  "blx": .15, "bly": .15, "brx": .85, "bry": .15, "trx": .85, "try": .85, "tlx": .15, "tly": .85,
                  "flipx": True, "flipy": True}
        for i in (1,2,3):
            name = "mapped{}".format(i)
            baseline = pixels(name)
            for suffix, value in sweeps.items():
                par = show.par["Output{}{}".format(i,suffix)]
                old = par.eval()
                par.val = value; ext.UpdateMapping()
                require(np.max(np.abs(pixels(name)-baseline)) > .001, par.name + " has no visible response")
                par.val = old; ext.UpdateMapping()
        checks["all_63_mapping_grade_flip_controls"] = True
        baseline = pixels("mapped1")
        show.par.Output1cropleft = 1
        ext.UpdateMapping()
        require("positive" in show.par.Mappingstatus.eval(), "Invalid crop must be reported")
        require(np.allclose(pixels("mapped1"), baseline), "Invalid crop changed audience mapping")
        show.par.Output1cropleft = 0
        ext.UpdateMapping()
        require(show.par.Mappingstatus.eval() == "Mapping valid", "Mapping status did not recover")
        checks["invalid_crop_preserves_last_valid_mapping"] = True
        show.par.Testpattern = True
        require(not np.allclose(pixels("mapped1"), a), "Calibration grid failed")
        show.par.Testpattern = False
        checks["calibration_grid"] = True

        ext.engine.pause(); before = ext.engine.elapsed; clock[0] = 40; ext.engine.tick()
        require(ext.engine.elapsed == before, "Pause did not freeze show clock")
        require(not ext.tracks[1]["deck"].allowCooking, "Pause did not freeze effects")
        ext.engine.resume(); step(41)
        require(ext.engine.elapsed == before+1, "Resume jumped show clock")
        checks["pause_resume_effect_clock"] = True

        ext.engine.stop(); show.par.Routingmode = "panoramic"
        load([cue(duration=0, fade=0)]); ext.engine.go(0); step(0)
        require(show.op("track1").width == 960, "Panorama is not triple width")
        require(not np.allclose(pixels("mapped1"), pixels("mapped2")), "Panorama does not crop unique regions")
        checks["panoramic_three_regions"] = True
        ext.engine.stop(); show.par.Panoramaoverlap = .25; ext.UpdateMapping()
        load([cue(duration=0, fade=0)]); ext.engine.go(0); step(0)
        require(show.op("track1").width == 800, "Panorama overlap did not change render width")
        require(abs(show.op("mapped2").par.vec3valuex.eval() - .3) < 1e-6, "Panorama overlap crop incorrect")
        show.par.Panoramaoverlap = 0; ext.UpdateMapping()
        checks["panorama_overlap_render_and_crop"] = True

        ext.engine.stop(); show.par.Routingmode = "independent"
        # A full captured look verifies every serializable module value.
        load([cue(track=1,duration=0,fade=0),cue(track=2,duration=0,fade=0),cue(track=3,duration=0,fade=0)])
        show.par.Selectedcue=1; ext.CaptureLook()
        look = ext.document["cues"][0]["look"]
        require("ink_dream_flow" in look["modules"] and "Inkdreamenabled" in look["toggles"], "Ink Dream Flow missing from captured look")
        checks["ink_dream_flow_capture_look"] = True
        ext.engine.clock=lambda:clock[0]; ext.engine._last=clock[0]
        for i in range(3): ext.engine.go(i)
        step(clock[0])
        for i in (1,2,3): require(i in ext.tracks, "Missing independent track")
        ext._stop_track(2)
        require(np.max(pixels("mapped2")[:,:,:3]) == 0 and np.max(pixels("mapped1")[:,:,:3]) > 0, "Independent stop affected another output")
        show.par.Output2track=1
        require(np.allclose(pixels("mapped2"),pixels("mapped1")), "Independent track selector failed")
        show.par.Output2track=2
        checks["independent_tracks_routing_and_capture_look"] = True

        # Parameter cue automation, crossfade standby and missing-file retention.
        load([cue(duration=0,fade=0),cue(kind="parameters",target="calligraphic_shadow/Particleamount",value=.7,duration=2),cue(duration=1,fade=2)])
        ext.engine.go(0); step(0)
        target = ext.tracks[1]["deck"].op("calligraphic_shadow").par.Particleamount
        initial = target.eval(); ext.engine.go(1); step(0); step(1)
        require(abs(target.eval() - (initial+.7)/2) < .001, "Parameter animation midpoint failed")
        step(2); require(abs(target.eval()-.7)<.001, "Parameter animation end failed")
        ext.engine.go(2); step(2); step(3)
        require(not ext.tracks[1]["fading"] and ext.tracks[1]["finished"], "Short held cue retained crossfade lock")
        current = ext.tracks[1]["deck"]
        try: ext.prepare(cue(source=str(ROOT/"build"/"absent-show-media.png")))
        except ValueError: pass
        else: raise AssertionError("Missing media was accepted")
        require(ext.tracks[1]["deck"] == current, "Missing media replaced active output")
        checks["parameter_animation_crossfade_hold_missing_media"] = True

        # Re-preloading a playing/held cue must not silence or replace it.
        selected = ext.document["cues"][2]
        try: ext.prepare(selected)
        except ValueError: pass
        else: raise AssertionError("Preloading a held cue was accepted")
        require(ext.tracks[1]["deck"] == current, "Rejected preload stopped the held output")
        ext.engine.stop()
        load([cue(duration=0,fade=2),cue(duration=0,fade=0)])
        ext.engine.go(0); step(0)
        require(np.max(pixels("track1")[:,:,:3]) == 0, "First fade after stop exposed stale content")
        step(2)
        ext.prepare(ext.document["cues"][1])
        ext.engine.stop_cue(0)
        ext.engine.go(1); step(2)
        require(np.max(pixels("track1")[:,:,:3]) > 0, "Stopping current cue broke prepared successor")
        checks["stop_fades_from_black_and_preserves_prepared_successor"] = True
        checks["running_and_held_preload_protection"] = True

        ext.engine.stop()
        dream_look = {"toggles": {"Inkdreamenabled": True}, "modules": {"ink_dream_flow": {"Coverage": .4}}}
        load([cue(duration=0,fade=0,look=dream_look), cue(kind="parameters",target="ink_dream_flow/Coverage",value=.75,duration=2)])
        ext.engine.go(0); step(0)
        dream = ext.tracks[1]["deck"].op("ink_dream_flow")
        require(bool(dream.par.Enabled), "Dream cue toggle did not apply")
        deck = ext.tracks[1]["deck"]
        for name, toggle in ext.model.MODULE_TOGGLES.items():
            require(deck.op(name).par.Enabled.expr == "parent().par." + toggle, "Lost cue routing expression: " + name)
        checks["all_module_cue_routing_expressions_preserved"] = True
        first_dream = pixels("track1")
        ext.engine.go(1); step(0); step(1); step(2)
        require(abs(dream.par.Coverage.eval()-.75)<.001, "Dream parameter cue failed")
        require(not np.allclose(first_dream,pixels("track1")), "Dream cue pixels did not change")
        checks["ink_dream_flow_parameter_cue"] = True

        ext.engine.stop()
        fixture = ROOT/"build"/"envoy-validation"/"show-fixture.wav"
        fixture.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(fixture),"wb") as output:
            output.setnchannels(2); output.setsampwidth(2); output.setframerate(48000)
            output.writeframes(b"".join(struct.pack("<hh",int(3000*math.sin(i*2*math.pi*220/48000)),int(2000*math.sin(i*2*math.pi*330/48000))) for i in range(96000)))
        load([cue(kind="audio",source=str(fixture),duration=2,fade=.25,gain=.6)])
        ext.engine.go(0); step(0); step(.5)
        item = next(iter(ext.audio.values()))
        item["gain"].cook(force=True)
        require(not item["reader"].errors() and not item["stereo"].errors(), "Audio decode/stereo normalization failed")
        require(item["stereo"].numChans == 2, "Audio bus must have two channels")
        require(abs(item["gain"].par.gain.eval()-.6)<.001, "Audio gain envelope failed")
        ext.engine.pause(); require(not item["reader"].par.play, "Audio pause failed")
        ext.engine.resume(); require(bool(item["reader"].par.play), "Audio resume failed")
        show.par.Audiomute=True; require(show.op("audio_master").par.gain.eval()==0,"Master mute failed")
        show.par.Audiomute=False
        for level in (0, .25, 1):
            show.par.Mastervolume=level
            require(abs(show.op("audio_master").par.gain.eval()-level)<1e-6,"Master volume binding failed")
        step(3); require(not ext.audio, "Audio voice not released at end")
        require(not show.op("stereo_output").par.active, "QA unexpectedly enabled sound")
        checks["stereo_audio_decode_gain_pause_mute_finish"] = True

        # File image/video opening crosses TD frames. validate_show_media.py
        # exercises those asynchronously, separately from this synchronous suite.
        ext.engine.stop()
        for i in (1,2,3):
            for width,height in ((1920,1080),(3840,2160)):
                show.par["Output{}width".format(i)]=width
                show.par["Output{}height".format(i)]=height
                node=show.op("mapped{}".format(i)); node.cook(force=True)
                require((node.width,node.height)==(width,height),"1080p/4K output dimensions not supported by this license/device")
            show.par["Output{}width".format(i)]=320
            show.par["Output{}height".format(i)]=180
        checks["three_outputs_1080p_and_4k_dimensions"] = True

        # Exercise all editing actions without mutating any user's saved show.
        load([cue(name="one"),cue(name="two")])
        ext.SelectCue(1); ext.DuplicateCue(); require(len(ext.document["cues"])==3,"Duplicate failed")
        ext.MoveCue(1); require(ext.document["cues"][2]["name"]=="one copy","Move cue failed")
        ext.RemoveCue(); require(len(ext.document["cues"])==2,"Remove failed")
        ext.AddCue(); show.par.Cuename="Edited"; show.par.Timestamp="00:00:04"; show.par.Gain=.3; ext.ApplyCue()
        require(ext.document["cues"][-1]["name"]=="Edited" and ext.document["cues"][-1]["at"]==4,"Apply cue failed")
        require(ext.Preflight()==[],"Preflight rejected blank built-in visual source")
        ext.SelectRow(0); require(int(show.par.Selectedcue)==1,"Cue row selection failed")
        checks["cue_edit_add_duplicate_reorder_remove_apply_preflight"] = True
        # Round-trip every editor value, not only the cue's label and timestamp.
        editor = {"Cuename": ("name", "All values"), "Cuekind": ("kind", "wait"),
                  "Cueenabled": ("enabled", False), "Mediafile": ("source", str(image_fixture)),
                  "Track": ("track", 3), "Timestamp": ("at", "00:00:12.5"),
                  "Prewait": ("prewait", 1.25), "Duration": ("duration", 3.5),
                  "Fade": ("fade", .75), "Postwait": ("postwait", 1.5),
                  "Mediain": ("media_in", .5), "Follow": ("follow", "continue"),
                  "Loop": ("loop", True), "Movieaudio": ("movie_audio", True),
                  "Hold": ("hold", False), "Speed": ("speed", 1.5), "Gain": ("gain", .35),
                  "Target": ("target", "calligraphic_shadow/Particleamount"),
                  "Targetvalue": ("value", "0.4"), "Easing": ("easing", "linear"),
                  "Notes": ("notes", "QA: no physical output")}
        for name, (_, value) in editor.items(): show.par[name] = value
        ext.ApplyCue()
        stored = ext.document["cues"][int(show.par.Selectedcue)-1]
        for name, (field, expected) in editor.items():
            if name == "Timestamp": expected = 12.5
            if name == "Targetvalue": expected = .4
            require(stored[field] == expected, name + " did not apply")
        ext.SelectCue(int(show.par.Selectedcue))
        for name, (field, _) in editor.items():
            actual = show.par[name].eval()
            if name == "Timestamp": actual = ext.model.timestamp(actual)
            if name == "Targetvalue": actual = json.loads(actual)
            require(actual == stored[field], name + " did not restore into editor")
        for name in ("Prewait", "Duration", "Fade", "Postwait", "Mediain"):
            require(show.par[name].normMax < show.par[name].max, name + " slider must have a useful rehearsal range")
        coverage["editor_values"] = sorted(editor)
        checks["all_21_cue_editor_values_roundtrip"] = True
        load([cue(name="Row {}".format(i)) for i in range(1,26)])
        show.par.Cuepage=2; ext.SelectRow(11)
        require(int(show.par.Selectedcue)==24 and "Row 24" in ext.CueLabel(11), "Cue paging/selection failed")
        show.par.Cuepage=1
        checks["cue_paging_and_selected_number"] = True
        load([cue(kind="wait",duration=0),cue(kind="wait",at=2,duration=1),cue(kind="wait")])
        ext.SelectCue(1); ext.Go(); ext.Tick()
        clock[0]=2; ext.Tick()
        require(int(show.par.Selectedcue)==3,"Scheduled GO did not advance the visible selected cue")
        checks["automatic_go_advances_visible_selection"] = True

        # Save/load only a generated local test show, never user's chosen file.
        ext.engine.stop(); show.par.Showfile=str(ROOT/"build"/"envoy-validation"/"show-qa.json")
        ext.SaveShow(); saved=copy.deepcopy(ext.document)
        saved_bytes=Path(show.par.Showfile.eval()).read_bytes()
        show.par.Output1cropleft=1
        try: ext.SaveShow()
        except ValueError: pass
        else: raise AssertionError("Invalid mapping was saved")
        require(Path(show.par.Showfile.eval()).read_bytes()==saved_bytes and ext.document==saved,"Rejected save modified show")
        show.par.Output1cropleft=0; ext.UpdateMapping()
        ext.AddCue(); ext.LoadShow()
        require(ext.document==saved,"Show save/load roundtrip differs")
        require(bool(show.par.Masterblackout) and not show.par.Audioenabled,"Load did not disarm outputs")
        checks["show_file_roundtrip_and_load_safety"] = True
        checks["invalid_mapping_save_is_transactional"] = True

        # Dispatch every visible pulse through its real Parameter Execute DAT.
        # Stub only the extension endpoints in this wiring-only pass; functional
        # cases above exercise the real endpoints without opening hardware.
        endpoints={"Gocue":"Go","Pause":"Pause","Resume":"Resume","Stopall":"Stopall",
                   "Stopcue":"Stopcue","Preload":"Preload","Preflight":"Preflight",
                   "Saveshow":"SaveShow","Loadshow":"LoadShow","Selectcue":"SelectCue",
                   "Openoutputs":"Openoutputs","Closeoutputs":"Closeoutputs","Applycue":"ApplyCue",
                   "Capturelook":"CaptureLook","Addcue":"AddCue","Duplicatecue":"DuplicateCue",
                   "Removecue":"RemoveCue","Cueup":"MoveCue","Cuedown":"MoveCue"}
        pulses={p.name for p in show.customPars if p.isPulse}
        require(pulses==set(endpoints), "Uncovered show pulse: "+str(pulses.symmetric_difference(endpoints)))
        callbacks=show.op("show_parameters")
        require(callbacks.par.op.eval()==show and callbacks.par.onpulse and callbacks.par.custom, "Pulse callback not watching custom controls")
        originals={name:getattr(ext,name) for name in set(endpoints.values())}
        calls=[]
        try:
            for name in originals:
                setattr(ext,name,lambda *args,_name=name:calls.append((_name,args)))
            for name, method in endpoints.items():
                before=len(calls); callbacks.module.onPulse(show.par[name])
                require(len(calls)==before+1 and calls[-1][0]==method,name+" pulse dispatch failed")
            for node in show.findChildren(depth=1, name="button_*"):
                method=endpoints[node.fetch("show_action")]
                before=len(calls); node.op("clicked").module.onOffToOn(None)
                require(len(calls)==before+1 and calls[-1][0]==method,node.name+" click dispatch failed")
        finally:
            for name, method in originals.items(): setattr(ext,name,method)
        for row in range(12):
            callback=show.op("cue_row_{}".format(row)).op("clicked")
            require(callback.par.offtoon and callback.par.panelvalue.eval()=="lselect","Cue row callback disconnected")
        for axis in ("x","y"):
            old=show.par["Window"+axis].eval()
            show.par["Window"+axis]=-123
            require(show.op("audience_window").par["winoffset"+axis].eval()==-123,"Audience window position not wired")
            show.par["Window"+axis]=old
        require("Audioenabled" in show.op("stereo_output").par.active.expr, "Audio output arm not wired")
        require("Audiodevice" in show.op("stereo_output").par.device.expr and bool(show.par.Audiodevice.menuSource), "Audio device menu not wired")
        coverage["pulse_dispatch"] = sorted(pulses)
        coverage["hardware_wiring_only"] = ["Openoutputs","Closeoutputs","Audioenabled","Audiodevice","Windowx","Windowy"]
        checks["all_19_show_pulses_and_8_panel_buttons_dispatch"] = True
        checks["hardware_controls_wired_without_enabling_outputs"] = True
        load([cue(duration=0,fade=0)])
        ext.engine.go(0); step(0)
        restart=show.parent().copy(show,name="show_restart_qa")
        try:
            restart.initializeExtensions()
            require(not restart.par.Audioenabled and bool(restart.par.Masterblackout), "Restart did not disarm output")
            require(not any(node.fetch("imagefx_show_runtime",False,search=False) for node in restart.children), "Restart retained old media readers/decks")
            require(all(not restart.par["Track{}visible".format(i)] for i in (1,2,3)), "Restart retained a live visual track")
            checks["restart_clears_runtime_media_and_disarms"] = True
        finally:
            restart.destroy()
        require(not show.errors(recurse=True), show.errors(recurse=True))
        checks["no_native_operator_errors"] = True
    except Exception:
        details["error"] = traceback.format_exc()
    finally:
        ext.engine.stop()
        ext.document=original
        ext._replace_cues(original["cues"])
        for name,value in values.items(): show.par[name]=value
        show.par.Audioenabled=False
        show.par.Masterblackout=True
        show.op("show_tick").par.active=tick_active
        ext._mapping_key=None
        ext.UpdateMapping(); ext.SelectCue(1)
    report={"ok":not details,"generated_at":datetime.now(timezone.utc).isoformat(),"checks":checks,"details":details,"coverage":coverage,"hardware_outputs_tested":False,"audio_auditioned":False}
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    validate()
