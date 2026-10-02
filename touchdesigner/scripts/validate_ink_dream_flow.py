"""Rendered-pixel coverage of every Ink Dream Flow control; never saves a TOE.

Only creates a temporary copy of the module with a deterministic test source;
does not modify the user's demo controls or effect chain.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "build" / "envoy-validation" / "ink-dream-flow.json"


def validate(write_report=True, brush=False):
    source_path = ROOT / "touchdesigner/scripts/ink_dream_flow.py"
    scope = {}
    exec(compile(source_path.read_text(encoding="utf-8"), str(source_path), "exec"), scope)
    definitions = scope["brush_variant"]()[0] if brush else scope["PARAMETERS"]
    module_name = "ink_brush_flow" if brush else "ink_dream_flow"
    module = op("/project1/imagefx_demo/" + module_name)
    if module is None:
        raise RuntimeError("Build " + module_name + " first")
    host = op("/project1").create(baseCOMP, module_name + "_qa")
    checks, controls = {}, {}
    report = dict(validator=module_name.replace("_", "-"), generated_at=datetime.now(timezone.utc).isoformat(), ok=False)
    try:
        test = host.copy(module, name="test")
        fixture = host.create(constantTOP, "source")
        fixture.par.outputresolution = "custom"
        fixture.par.resolutionw = 320
        fixture.par.resolutionh = 180
        fixture.par.colorr = .68
        fixture.par.colorg = .34
        fixture.par.colorb = .17
        fixture.par.alpha = .65
        fixture.outputConnectors[0].connect(test.inputConnectors[0])
        output = test.op("out1_image")
        shader = test.op("effect_glsl_" + module_name)
        defaults = {}
        for d in definitions:
            if d.get("read_only"):
                continue
            suffixes = d["type"] if d["type"] in ("xy", "rgb", "rgba") else ""
            if suffixes:
                for suffix, value in zip(suffixes, d["default"]):
                    defaults[d["name"] + suffix] = value
            else:
                defaults[d["name"]] = d["default"]
        defaults.update(Autotime=False, Manualtime=3.7, Enabled=True, Particlesize=4.0)

        def set_values(values):
            for name, value in values.items():
                test.par[name].val = value

        def reset(**values):
            set_values(defaults)
            set_values(values)

        def capture(node=output):
            node.cook(force=True)
            value = node.numpyArray(delayed=False, writable=False)
            if value is None:
                value = node.numpyArray(delayed=False, writable=False)
            if value is None or not np.isfinite(value).all():
                raise AssertionError("Invalid pixels: " + node.path)
            if shader.errors():
                raise AssertionError(str(shader.errors()))
            return np.array(value, dtype=np.float32, copy=True)

        def difference(a, b):
            return float(np.mean(np.abs(a-b)))

        reset()
        integer_names = {d["name"] for d in definitions if d["type"] == "int"}
        sample_ranges = {
            "Rotation": (-45., 60.), "Direction": (-90., 45.),
            "Centerx": (-.3, .4), "Centery": (-.3, .4),
            "Manualtime": (.4, 8.), "Timescale": (0., .002),
            "Flowspeed": (-.5, .8), "Particlespeed": (-.5, .8), "Seed": (1, 89),
            "Glitterspeed": (-.5, .8), "Glitterdirection": (-90., 45.),
            "Glitterstarrotation": (-30., 15.), "Glitterseed": (1, 89),
            "Staticglitterstarrotation": (-30., 15.), "Staticglitterseed": (1, 89),
            "Staticglittertwinklespeed": (-.4, 1.1),
        }
        for par in test.customPars:
            if par.readOnly:
                checks[par.name + "_readonly"] = par.name == "Time" and bool(par.expr)
                continue
            reset()
            if par.name.startswith("Glitter") and par.name != "Glitterenabled":
                reset(Glitterenabled=True, Glitteramount=1., Glitterdensity=.65,
                      Glittersize=4., Glitterbrightness=2., Glitterthreshold=.08,
                      Glitterspread=.15, Glitterstars=.8, Glitterglow=.6)
            if par.name.startswith("Staticglitter") and par.name != "Staticglitterenabled":
                reset(Staticglitterenabled=True, Staticglitteramount=1.,
                      Staticglitterdensity=.75, Staticglittersize=1.8,
                      Staticglitterbrightness=2., Staticglitterthreshold=.04,
                      Staticglitterspread=.15, Staticglitterstars=.9, Staticglitterglow=.6,
                      Staticglittershimmer=.8)
            if par.name == "Staticglittersurface":
                # Isolate carrier choice: spread plus a low threshold can
                # legitimately saturate the mask across a wide composition.
                set_values(dict(Staticglitterspread=0., Staticglitterthreshold=.12, Staticglitteredge=.08))
            if par.name == "Autotime":
                test.par.Timescale = 0.0
            if par.name == "Timescale":
                test.par.Autotime = True
            if par.isMenu:
                values = list(par.menuNames)
            elif par.isToggle:
                values = [False, True]
            else:
                values = list(sample_ranges.get(par.name, (float(par.min), float(par.max))))
                if par.name in integer_names:
                    values = [int(v) for v in values]
                checks[par.name + "_range"] = par.min < par.max and par.normMin < par.normMax and par.clampMin and par.clampMax
                # Exact range ends must accept values and render finite, even for
                # cyclic angles whose two endpoints are the same visual state.
                for edge in (par.min, par.max):
                    par.val = int(edge) if par.name in integer_names else float(edge)
                    checks[par.name + "_endpoint_" + str(edge)] = abs(par.eval()-edge)<1e-5
                    capture()
            images, accepted = [], []
            for value in values:
                par.val = value
                accepted.append(par.eval() == value)
                images.append(capture())
            changes = [difference(images[i], images[j]) for i in range(len(images)) for j in range(i+1, len(images))]
            controls[par.name] = dict(values=values, accepted=accepted, differences=changes)
            checks[par.name + "_accepts_values"] = all(accepted)
            checks[par.name + "_changes_pixels"] = all(v > 1e-8 for v in changes)

        reset(Enabled=False)
        checks["disabled_exact_bypass"] = difference(capture(),capture(fixture)) < 1e-7
        reset(Mix=0.)
        checks["mix_zero_exact_bypass"] = difference(capture(),capture(fixture)) < 1e-7
        reset()
        first = capture()
        test.par.Manualtime = 17.0
        checks["time_animates"] = difference(first, capture()) > 1e-6
        test.par.Manualtime = defaults["Manualtime"]
        checks["time_seek_repeatable"] = np.array_equal(first,capture())
        reset(Autotime=True, Timescale=0.0)
        checks["timescale_zero_resolves_zero"] = test.par.Time.eval() == 0.0
        reset(Flowspeed=0.0, Particlespeed=0.0)
        first = capture()
        test.par.Manualtime = 25.0
        checks["zero_speeds_freeze_all"] = np.array_equal(first,capture())
        reset(Liquidenabled=False, Particlesenabled=False, Background="source")
        checks["empty_layers_source_passthrough"] = difference(capture(),capture(fixture)) < 1e-7
        test.par.Background = "transparent"
        checks["empty_layers_transparent_black"] = float(np.max(np.abs(capture()))) == 0.0
        reset(Background="transparent")
        transparent = capture()
        checks["transparent_ink_has_alpha_variation"] = float(np.ptp(transparent[:,:,3])) > .1
        checks["transparent_alpha_bounded"] = bool(((transparent[:,:,3]>=0)&(transparent[:,:,3]<=1)).all())
        for name in ("Particledensity", "Particleamount", "Particlecolora"):
            reset(Liquidenabled=False, Background="transparent", **{name: 0.0})
            checks[name + "_zero_removes_particles"] = float(np.max(np.abs(capture()))) == 0.0
        reset(Liquidenabled=False, Particlesenabled=True, Background="transparent")
        checks["particles_only_visible"] = float(np.max(capture()[:,:,3])) > .1
        reset(Liquidenabled=True, Particlesenabled=False, Background="transparent")
        checks["liquid_only_visible"] = float(np.max(capture()[:,:,3])) > .1
        reset()
        without_glitter = capture()
        set_values(dict(Glitterenabled=False, Glitteramount=2., Glitterdensity=1.,
                        Glitterbrightness=8., Glitterspread=1., Glitterglow=2.))
        checks["glitter_disabled_exact_bypass"] = np.array_equal(without_glitter,capture())
        for name in ("Glitteramount", "Glitterdensity", "Glitterbrightness", "Glittercolora"):
            reset(Glitterenabled=True, **{name: 0.})
            checks[name+"_zero_exact_bypass"] = np.array_equal(without_glitter,capture())
        reset(Glitterenabled=True, Flowspeed=0., Particlespeed=0.,
              Glitterspeed=0., Glittertwinklespeed=0.)
        first = capture()
        test.par.Manualtime = 25.
        checks["all_glitter_clocks_zero_freeze"] = np.array_equal(first,capture())
        for label, drift_speed, shimmer_speed in (("shimmer",0.,1.1),("drift",.25,0.)):
            reset(Glitterenabled=True, Flowspeed=0., Particlespeed=0.,
                  Glitterspeed=drift_speed, Glittertwinklespeed=shimmer_speed)
            first = capture()
            test.par.Manualtime = 25.
            checks["glitter_"+label+"_animates_independently"] = difference(first,capture()) > 1e-6
        reset(Glitterenabled=True)
        first = capture()
        test.par.Manualtime = 17.
        checks["glitter_time_animates"] = difference(first,capture()) > 1e-6
        test.par.Manualtime = defaults["Manualtime"]
        checks["glitter_seek_repeatable"] = np.array_equal(first,capture())
        reset(Glitterenabled=True, Liquidenabled=False, Particlesenabled=False,
              Background="transparent", Glitterthreshold=0., Glitterspread=0.)
        checks["glitter_without_carrier_preserves_empty_background"] = float(np.max(np.abs(capture()))) == 0.
        test.par.Glitterspread = 1.
        standalone_glitter = capture()
        checks["glitter_only_visible_with_spread"] = float(np.max(standalone_glitter[:,:,3])) > .1
        checks["glitter_alpha_bounded"] = bool(((standalone_glitter[:,:,3]>=0)&(standalone_glitter[:,:,3]<=1)).all())
        # Check exact zero-alpha RGB before 8-bit quantization: tiny nonzero
        # straight-alpha highlights can otherwise round alpha to zero while
        # their unpremultiplied color stays nonzero (and is ignored by Over).
        original_format = shader.par.format.eval()
        try:
            shader.par.format = "rgba32float"
            precise = capture(shader)
            checks["glitter_no_hidden_rgb_at_zero_alpha_float32"] = bool((precise[precise[:,:,3]==0.,:3]==0.).all())
        finally:
            shader.par.format = original_format
        reset(Glitterenabled=True, Liquidenabled=False, Particlesenabled=False,
              Background="source", Glitterspread=0.)
        checks["glitter_without_carrier_preserves_source"] = difference(capture(),capture(fixture)) < 1e-7
        for surface, toggle in (("ink","Liquidenabled"),("wash","Liquidenabled"),("particles","Particlesenabled")):
            reset(Glitterenabled=True, Glittersurface=surface, Glitterthreshold=0.,
                  Glitterspread=0., Background="transparent", **{toggle:False})
            first = capture()
            test.par.Glitterenabled = False
            checks["glitter_"+surface+"_respects_layer_switch"] = np.array_equal(first,capture())
        reset()
        without_static = capture()
        set_values(dict(Staticglitterenabled=False, Staticglitteramount=2.,
                        Staticglitterdensity=1., Staticglitterbrightness=8., Staticglitterspread=1.))
        checks["static_disabled_exact_bypass"] = np.array_equal(without_static,capture())
        for parameter in ("Staticglitteramount", "Staticglitterdensity", "Staticglitterbrightness", "Staticglittercolora"):
            reset(Staticglitterenabled=True, **{parameter:0.})
            checks[parameter + "_zero_exact_bypass"] = np.array_equal(without_static,capture())
        reset(Staticglitterenabled=True, Flowspeed=0., Particlespeed=0.)
        first = capture()
        test.par.Manualtime = 25.
        checks["static_shimmer_zero_time_invariant"] = np.array_equal(first,capture())
        reset(Staticglitterenabled=True, Liquidenabled=False, Particlesenabled=False,
              Background="transparent", Staticglitterthreshold=0., Staticglitterspread=0.)
        checks["static_without_carrier_empty"] = float(np.max(np.abs(capture()))) == 0.
        test.par.Staticglitterspread = 1.
        first = capture()
        checks["static_only_visible_with_spread"] = float(np.max(first[:,:,3])) > .1
        checks["static_alpha_bounded"] = bool(((first[:,:,3]>=0)&(first[:,:,3]<=1)).all())
        original_format = shader.par.format.eval()
        try:
            shader.par.format = "rgba32float"
            precise = capture(shader)
            checks["static_no_hidden_rgb_at_zero_alpha_float32"] = bool((precise[precise[:,:,3]==0.,:3]==0.).all())
        finally:
            shader.par.format = original_format
        test.par.Manualtime = 25.
        checks["static_only_time_invariant"] = np.array_equal(first,capture())
        # Keep carrier/grain geometry fixed and exercise only brightness.
        reset(Staticglitterenabled=True, Staticglittershimmer=1.,
              Staticglittertwinklespeed=1.15, Flowspeed=0., Particlespeed=0.,
              Liquidenabled=False, Particlesenabled=False, Background="transparent",
              Staticglitterspread=1., Staticglitterthreshold=0.)
        original_format = shader.par.format.eval()
        try:
            # An 8-bit alpha rounding change is not grain movement.
            shader.par.format = "rgba32float"
            first = capture(shader)
            test.par.Manualtime = 17.
            second = capture(shader)
            checks["static_shimmer_animates_independently"] = difference(first,second)>1e-6
            changed_support=(first[:,:,3]>0.)!=(second[:,:,3]>0.)
            # Even float32 mix(source,result,1) can cancel sub-epsilon alpha.
            # Native diagnosis found only <=1.8e-7 halo/core values affected;
            # retain strict support for visible grains, ignoring float roundoff.
            support_alpha=np.maximum(first[:,:,3],second[:,:,3])[changed_support]
            checks["static_shimmer_preserves_grain_support"] = bool(np.all(support_alpha<1e-6))
            test.par.Manualtime = defaults["Manualtime"]
            checks["static_shimmer_seek_repeatable"] = np.array_equal(first,capture(shader))
            test.par.Staticglittertwinklespeed = 0.
            first = capture(shader)
            test.par.Manualtime = 25.
            checks["static_shimmer_speed_zero_freezes"] = np.array_equal(first,capture(shader))
        finally:
            shader.par.format = original_format
        for surface, toggle in (("ink","Liquidenabled"),("wash","Liquidenabled"),("particles","Particlesenabled")):
            reset(Staticglitterenabled=True, Staticglittersurface=surface, Staticglitterthreshold=0.,
                  Staticglitterspread=0., Background="transparent", **{toggle:False})
            first = capture()
            test.par.Staticglitterenabled = False
            checks["static_"+surface+"_respects_layer_switch"] = np.array_equal(first,capture())
        reset(Glitterenabled=True, Staticglitterenabled=False)
        animated_only = capture()
        test.par.Staticglitterenabled = True
        both = capture()
        checks["both_glitter_layers_combine"] = difference(animated_only,both) > 1e-6
        test.par.Glitterenabled = False
        checks["animated_switch_independent_of_static"] = difference(both,capture()) > 1e-6
        if brush:
            reset(Brushenabled=False)
            unbrushed = capture()
            test.par.Brushenabled = True
            checks["brush_renderer_is_distinct"] = difference(unbrushed,capture()) > 1e-5
        checks["all_controls_covered"] = set(controls) == {p.name for p in test.customPars if not p.readOnly}
        checks["demo_toggle_binding"] = module.par.Enabled.expr == "parent().par." + ("Inkbrushenabled" if brush else "Inkdreamenabled")
        checks["chain_input"] = module.inputs[0] == op("/project1/imagefx_demo/" + ("ink_dream_flow" if brush else "ink_orbit_canvas") + "/out1_image")
        checks["chain_output"] = op("/project1/imagefx_demo/" + ("ink_flow" if brush else "ink_brush_flow")).inputs[0] == module.op("out1_image")
        # Check native full-resolution rendering without claiming frame-rate suitability.
        for width, height in ((1920,1080), (3840,2160)):
            fixture.par.resolutionw, fixture.par.resolutionh = width, height
            reset(Glitterenabled=True, Staticglitterenabled=True)
            rendered = capture()
            checks[str(width) + "x" + str(height)] = rendered.shape[:2] == (height,width)
        report.update(checks=checks, controls=controls, control_count=len(controls), ok=all(checks.values()))
    except Exception:
        report.update(checks=checks, controls=controls, error=traceback.format_exc())
    finally:
        host.destroy()
    if write_report:
        report_path = REPORT_PATH.with_name(module_name.replace("_", "-") + ".json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
