"""Off-air native interpolation checks in a disposable Show Control copy."""
from __future__ import annotations

import copy
import importlib.util
import json
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(write_report=True):
    import td
    import numpy as np
    original = td.op("/project1/imagefx_demo/show_control")
    if original is None or original.ext.ShowControlExt.engine.state != "stopped":
        raise RuntimeError("Open ImageFX and Stop All before native transition checks")
    document = copy.deepcopy(original.ext.ShowControlExt.document)
    host = original.parent().copy(original, name="cue_interpolation_qa")
    report = {"ok": False, "checks": {}, "original_cues": len(document["cues"])}
    try:
        path = ROOT / "touchdesigner/scripts/install_cue_interpolation.py"
        spec = importlib.util.spec_from_file_location("_cue_interpolation_install", path)
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        upgrade = installer.install(host)
        if not upgrade["controls_preserved"]:
            raise AssertionError("Existing Show Control values or bindings changed")
        report["checks"]["installer_preserves_values_and_bindings"] = True
        host.op("show_tick").par.active = False
        ext = host.ext.ShowControlExt
        host.par.Renderwidth, host.par.Renderheight = 320, 180
        host.par.Masterblackout, host.par.Audioenabled = True, False
        clock = [0.0]
        ext.engine.clock = lambda: clock[0]
        baseline = ext._deck(1, 0)
        baseline.allowCooking = True
        before = ext._capture_look(baseline, active=False)
        baseline.allowCooking = False
        before["toggles"] = {k: False for k in before["toggles"]}
        before["toggles"].update(Coloradjustmentenabled=True, Inkdreamenabled=True)
        before["modules"]["color_adjustment"].update(Contrast=.5, Saturation=.25)
        before["animation"] = {n: {"time": 3.0, "running": True} for n in (*ext.model.MODULES, "fx_rack")}
        after = copy.deepcopy(before)
        after["modules"]["color_adjustment"].update(Contrast=1.5, Saturation=1.75)
        after["animation"]["ink_dream_flow"]["time"] = 900
        first = dict(ext.model.new_cue(), look=before, duration=0, fade=0)
        second = dict(ext.model.new_cue(), look=after, duration=0, fade=2, transition="interpolate", easing="linear")
        fallback = copy.deepcopy(after); fallback["toggles"]["Inkdreamenabled"] = False
        third = dict(ext.model.new_cue(), look=fallback, duration=0, fade=2, transition="interpolate")
        smooth_look = copy.deepcopy(fallback)
        smooth_look["modules"]["color_adjustment"].update(Contrast=.5, Saturation=.25)
        fourth = dict(ext.model.new_cue(), look=smooth_look, duration=0, fade=2, transition="interpolate", easing="smooth")
        fifth = dict(ext.model.new_cue(), look=fallback, duration=0, fade=0, transition="interpolate")
        sixth = dict(ext.model.new_cue(), look=smooth_look, duration=1, fade=2, transition="interpolate", hold=True)
        ext._replace_cues([first, second, third, fourth, fifth, sixth])
        ext.engine.clock = lambda: clock[0]
        ext.engine._last = 0

        def require(value, name):
            if not value: raise AssertionError(name)
            report["checks"][name] = True

        def step(now):
            for _ in range(1000):
                loading = [v for v in ext.prepared.values() if v.get("loading")]
                if not loading: break
                for v in loading:
                    if "warm_frame" in v: v["warm_frame"] = td.absTime.frame - 1
                ext._service_preloads()
            clock[0] = now
            ext.engine.tick()
            require(not ext.engine.errors, "no_cue_errors")

        def pixels():
            node = host.op("track1"); node.cook(force=True)
            data = node.numpyArray(delayed=False)
            require(data is not None and np.isfinite(data).all() and float(data[:, :, :3].max()) > .001,
                    "rendered_pixels_visible_and_finite")
            return data.copy()

        ext.engine.go(0); step(0); step(1)
        live = ext.tracks[1]["deck"]; live_id = live.id
        phase = float(live.op("ink_dream_flow").par.Time)
        initial = pixels()
        ext.engine.go(1); step(1)
        require(ext.tracks[1]["deck"].id == live_id, "same_deck_reused")
        require(abs(float(live.op("ink_dream_flow").par.Time)-phase) < 1e-5, "no_phase_seek_on_go")
        require(abs(float(live.op("color_adjustment").par.Contrast)-.5) < 1e-5, "starts_at_previous_values")
        step(2)
        require(abs(float(live.op("color_adjustment").par.Contrast)-1) < 1e-5, "midpoint_contrast")
        require(abs(float(live.op("color_adjustment").par.Saturation)-1) < 1e-5, "midpoint_saturation")
        require(float(host.par.Track1blend) == ext.tracks[1]["side"], "no_image_crossfade_during_interpolation")
        midpoint = pixels()
        require(float(np.abs(initial-midpoint).mean()) > .00001, "pixels_change_during_interpolation")
        ext.engine.pause(); clock[0] = 100; ext.engine.tick()
        require(abs(float(live.op("color_adjustment").par.Contrast)-1) < 1e-5, "pause_preserves_midpoint")
        ext.engine.resume(); step(101)
        require(abs(float(live.op("color_adjustment").par.Contrast)-1.5) < 1e-5, "resume_reaches_exact_destination")
        require(not ext.tracks[1]["fading"], "transition_releases_track")
        pixels()
        ext.engine.go(2); step(101)
        require(ext.tracks[1]["deck"].id != live_id and ext.tracks[1].get("old") is not None,
                "topology_change_falls_back_to_crossfade")
        step(103); pixels()
        ext.engine.go(3); step(103); step(103.5)
        smooth_deck = ext.tracks[1]["deck"]
        require(abs(float(smooth_deck.op("color_adjustment").par.Contrast)-1.34375) < 1e-5,
                "smooth_easing_quarter_point")
        step(105)
        require(abs(float(smooth_deck.op("color_adjustment").par.Contrast)-.5) < 1e-5,
                "smooth_easing_destination")
        ext.engine.go(4); step(105)
        require(abs(float(smooth_deck.op("color_adjustment").par.Contrast)-1.5) < 1e-5,
                "zero_duration_interpolation_is_immediate")
        require(ext.tracks[1]["deck"].id == smooth_deck.id, "consecutive_interpolations_keep_live_deck")
        ext.engine.go(5); step(105); step(106)
        require(abs(float(smooth_deck.op("color_adjustment").par.Contrast)-.5) < 1e-5
                and ext.tracks[1]["finished"] and not ext.tracks[1]["fading"],
                "short_hold_finishes_at_destination")
        ext.engine.stop()
        host.par.Selectedcue = 2; ext.SelectCue()
        require(host.par.Transition.eval() == "interpolate", "editor_loads_transition")
        host.par.Transition = "crossfade"; ext.ApplyCue()
        require(ext.document["cues"][1]["transition"] == "crossfade", "editor_saves_transition")
        require(ext.model.validate_show(json.loads(json.dumps(ext.document))) == ext.document, "show_json_roundtrip")
        require(not host.errors(recurse=True) and not host.warnings(recurse=True), "no_native_errors_or_warnings")
        require(original.ext.ShowControlExt.document == document, "original_cues_preserved")
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        host.destroy()
        if write_report:
            target = ROOT / "build/cue-interpolation/native-validation.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
