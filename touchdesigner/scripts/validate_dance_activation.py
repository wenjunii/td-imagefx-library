"""Off-air activation/fade regression: real frames, no audience or camera."""
import json
import cProfile
import io
import pstats
from pathlib import Path
import runpy
import time
import traceback
import numpy as np

STATE = {}


def start(root, folder):
    if STATE: raise ValueError('Activation validation is already running')
    STATE.update(root=Path(root), folder=Path(folder))
    STATE['generator'] = validate()
    advance()


def advance():
    try:
        next(STATE['generator'])
        run('op({!r}).module.advance()'.format(me.path), delayFrames=1)
    except StopIteration:
        STATE.clear()


def validate():
    root, folder = STATE['root'], STATE['folder']
    folder.mkdir(parents=True, exist_ok=True)
    demo = op('/project1/imagefx_demo'); show = demo.op('show_control'); ext = show.ext.ShowControlExt
    assert ext.engine.state == 'stopped' and not ext.tracks and not ext.prepared and not ext._look_edit
    assert not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w)
    original = show.op('show_data').text
    look = ext._capture_look(demo, active=False)
    host = op('/project1').create(baseCOMP, 'dance_activation_qa')
    page = host.appendCustomPage('Fixture')
    for n in ('Inkdreamenabled','Inkbrushenabled','Inkradialenabled'): page.appendToggle(n)[0].val = True
    defs = runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    checks, measurements, errors = {}, {}, []

    def check(name, value):
        checks[name] = bool(value)
        assert value, name

    def pixels(node):
        node.cook(force=True)
        a = node.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(), node.path
        return a.copy()

    def tick(c, dt=1/60):
        c.par.Manualtime = float(c.par.Manualtime)+dt
        yield
        pixels(c.op('out1_image'))

    try:
        source = host.create(rampTOP, 'input'); source.par.outputresolution = 'custom'
        source.par.resolutionw = 480; source.par.resolutionh = 270
        for name in defs['MODULES']:
            c = host.copy(demo.op(name), name=name)
            c.par.Enabled.mode = ParMode.CONSTANT; c.par.Enabled.bindExpr = ''; c.par.Enabled = True
            source.outputConnectors[0].connect(c.inputConnectors[0])
            c.par.Autotime = False; c.par.Manualtime = 3.7; c.par.Animationspeed = 0.
            c.op('animation_clock').module.reset(c, phase=3.7)
            c.par.Feedbackenabled = False; c.par.Mix = 1.; c.par.Danceenabled = False
            c.par.Danceoffset = 12.; c.par.Danceamount = 1.; c.par.Danceresponse = .75
            c.par.Dancecache = str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json')
            c.par.Dancefadein = 1.5; c.par.Scale = 3.; c.par.Stretch = 1.
            raw = c.op('dance_forces_switch').inputs[0]
            yield
            baseline = pixels(raw)
            defs['install'](c, raw, root); yield
            rt = c.op('dance_forces_runtime').module
            if name == defs['MODULES'][0]:
                # Explicit cold process-cache test, not just a warm re-run.
                import sys
                old = sys.modules.pop('_tdimagefx_prepared_dance_forces_v3',None)
                if old is not None: old.cache.close()
            check(name+'/off_exact', np.array_equal(baseline,pixels(raw)))
            check(name+'/off_gate',rt.output_enabled(c)==0)
            c.par.Danceenabled = True
            check(name+'/same_frame_gate',rt.output_enabled(c)==0)
            check(name+'/same_frame_pixels',np.array_equal(baseline,pixels(raw)))
            costs, fields, gains = [], [], []
            ready_at = None
            for i in range(150):
                yield from tick(c)
                # Measure actual runtime sample, not a pre-computed per-frame hit.
                rt._sample_key = None
                profiler = cProfile.Profile() if i==0 else None
                if profiler: profiler.enable()
                at = time.perf_counter(); sample = np.asarray(rt.sample(c)); costs.append((time.perf_counter()-at)*1000.)
                if profiler:
                    profiler.disable(); stats=io.StringIO()
                    pstats.Stats(profiler,stream=stats).sort_stats('cumtime').print_stats(35)
                    (folder/(name+'-profile.txt')).write_text(stats.getvalue(),encoding='utf-8')
                fields.append(float(np.max(np.abs(pixels(c.op('dance_motion_out'))))))
                if c.fetch('dance_force_ready',False,search=False):
                    if ready_at is None:
                        ready_at = i
                        check(name+'/first_ready_zero_force',np.max(np.abs(sample[:,2:]))<1e-8)
                    elapsed = float(c.par.Time)-c.fetch('dance_force_activation')
                    gains.append(c.op('dance_forces_math').module.fade_in(elapsed,float(c.par.Dancefadein)))
                elif i<3:
                    check(name+'/loading_keeps_pattern/'+str(i),np.array_equal(baseline,pixels(raw)))
            measurements[name] = dict(sample_ms_max=max(costs),sample_ms_median=float(np.median(costs)),
                peak_sample_frame=int(np.argmax(costs)),sample_ms_first=costs[:12],
                ready_frame=ready_at,material_max=max(fields),first_material=fields[:12],fade=gains[:12])
            check(name+'/ready',ready_at is not None)
            check(name+'/nonblocking_samples',max(costs)<60.)
            check(name+'/fade_gradual',len(gains)>30 and gains[0]==0. and 0.<gains[10]<.15 and gains[-1]==1.)
            check(name+'/material_moves',max(fields)>1e-5)
            phase = rt.motion_time(c)
            c.par.Danceenabled=False; pixels(raw)
            check(name+'/off_again_exact',np.array_equal(baseline,pixels(raw)))
            c.par.Danceenabled=True
            check(name+'/retrigger_no_old_frame',np.array_equal(baseline,pixels(raw)))
            check(name+'/retrigger_clock_preserved',abs(rt.motion_time(c)-phase)<1e-6)
            yield
            pixels(raw)
            check(name+'/retrigger_zero_history',np.max(np.abs(pixels(c.op('dance_motion_out'))))==0.)
            for _ in range(30): yield from tick(c)
            held = pixels(c.op('dance_motion_out'))
            fade_start = c.fetch('dance_force_activation')
            yield; pixels(raw); yield
            check(name+'/pause_history',np.array_equal(held,pixels(c.op('dance_motion_out'))))
            check(name+'/pause_fade',c.fetch('dance_force_activation')==fade_start)
            # New smoothing settings prepare asynchronously, with the previous
            # valid filtered motion retained until ready (no timeline/fade reset).
            c.par.Dancesmooth=.31; rt._sample_key=None
            at=time.perf_counter(); rt.sample(c)
            check(name+'/filter_edit_nonblocking',(time.perf_counter()-at)*1000.<60.)
            check(name+'/filter_edit_keeps_fade',c.fetch('dance_force_activation')==fade_start)
            check(name+'/filter_edit_keeps_material',np.array_equal(held,pixels(c.op('dance_motion_out'))))
            for _ in range(60): yield from tick(c)
            check(name+'/filter_edit_applied',rt._clip.settings[0]==.31)
            # Instant remains an intentional option; fresh history still starts
            # at zero and no previous cue field can appear on activation.
            c.par.Dancefadein=0.; c.par.Danceenabled=False; pixels(raw)
            c.par.Danceenabled=True
            check(name+'/instant_still_zero_activation_frame',np.array_equal(baseline,pixels(raw)))
            for _ in range(5): yield from tick(c)
            check(name+'/instant_works',np.max(np.abs(pixels(c.op('dance_motion_out'))))>0.)
            c.par.Feedbackenabled=True
            for _ in range(5): yield from tick(c)
            c.par.Danceenabled=False; yield from tick(c)
            c.par.Danceenabled=True
            check(name+'/feedback_activation_finite',np.isfinite(pixels(c.op('out1_image'))).all())
            check(name+'/native_errors',not c.errors(recurse=True))
            c.destroy()
        check('main/cues_preserved',show.op('show_data').text==original)
        check('main/look_preserved',ext._capture_look(demo,active=False)==look)
        check('main/outputs_closed',not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        host.destroy()
        report=dict(ok=not errors,checks=checks,measurements=measurements,errors=errors,gpu=sysinfo.GPUName)
        (folder/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Force activation checks:',report['ok'],len(checks),errors)
