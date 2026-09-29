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


def validate(write_report=True):
    source_path = ROOT / "touchdesigner/scripts/ink_dream_flow.py"
    scope = {}
    exec(compile(source_path.read_text(encoding="utf-8"), str(source_path), "exec"), scope)
    definitions = scope["PARAMETERS"]
    module = op("/project1/imagefx_demo/ink_dream_flow")
    if module is None:
        raise RuntimeError("Build Ink Dream Flow first")
    host = op("/project1").create(baseCOMP, "ink_dream_qa")
    checks, controls = {}, {}
    report = dict(validator="ink-dream-flow", generated_at=datetime.now(timezone.utc).isoformat(), ok=False)
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
        shader = test.op("effect_glsl_ink_dream_flow")
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
        }
        for par in test.customPars:
            if par.readOnly:
                checks[par.name + "_readonly"] = par.name == "Time" and bool(par.expr)
                continue
            reset()
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
        checks["all_controls_covered"] = set(controls) == {p.name for p in test.customPars if not p.readOnly}
        checks["demo_toggle_binding"] = module.par.Enabled.expr == "parent().par.Inkdreamenabled"
        checks["chain_input"] = module.inputs[0] == op("/project1/imagefx_demo/ink_orbit_canvas/out1_image")
        checks["chain_output"] = op("/project1/imagefx_demo/ink_flow").inputs[0] == module.op("out1_image")
        # Check native full-resolution rendering without claiming frame-rate suitability.
        for width, height in ((1920,1080), (3840,2160)):
            fixture.par.resolutionw, fixture.par.resolutionh = width, height
            reset()
            rendered = capture()
            checks[str(width) + "x" + str(height)] = rendered.shape[:2] == (height,width)
        report.update(checks=checks, controls=controls, control_count=len(controls), ok=all(checks.values()))
    except Exception:
        report.update(checks=checks, controls=controls, error=traceback.format_exc())
    finally:
        host.destroy()
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
