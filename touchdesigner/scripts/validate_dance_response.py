"""Off-air GPU checks for force response lag; never starts a camera or output."""
import json
import math
from pathlib import Path
import runpy
import traceback
import numpy as np

STATE = {}


def start(root):
    if STATE:
        raise ValueError('Response validation already running')
    STATE['root'] = Path(root)
    STATE['generator'] = validate()
    advance()


def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=1)
    except StopIteration:
        STATE.clear()


def validate():
    root = STATE['root']
    folder = root/'build/dance-forces/response-20261027'
    folder.mkdir(parents=True, exist_ok=True)
    demo = op('/project1/imagefx_demo')
    show = demo.op('show_control'); ext = show.ext.ShowControlExt
    assert ext.engine.state == 'stopped' and not ext.tracks and not ext.prepared and not ext._look_edit
    original = show.op('show_data').text
    host = op('/project1').create(baseCOMP, 'dance_response_qa')
    page = host.appendCustomPage('Fixture')
    for n in ('Inkdreamenabled','Inkbrushenabled','Inkradialenabled'):
        page.appendToggle(n)[0].val = True
    defs = runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    checks, measurements, failures = {}, {}, []

    def check(name, value):
        checks[name] = bool(value)
        assert value, name

    def pixels(node):
        node.cook(force=True)
        a = node.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(), node.path
        assert not node.errors(), node.errors()
        return a.copy()

    def tick(c, count=1, dt=1/30):
        for _ in range(count):
            c.par.Manualtime = float(c.par.Manualtime) + dt
            yield
            pixels(c.op('out1_image'))

    def force(c, x=.12):
        for top in (c.op('dance_motion_step'), c.op('dance_response_step')):
            for i in range(12):
                for axis, value in zip('xyzw', (.5,.5,x if i == 0 else 0.,0.)):
                    top.par[f'vec{i+1}value{axis}'] = value

    def reference(c, name, code, input_node):
        dat = c.create(textDAT, name+'_pixel'); dat.text = code
        top = c.create(glslTOP, name)
        top.par.pixeldat = dat.path; top.par.glslversion = 'glsl460'
        top.par.outputresolution = 'custom'; top.par.resolutionw = 240; top.par.resolutionh = 135
        top.par.format = 'rgba32float'; top.par.compilebehavior = 'stalluntildone'
        input_node.outputConnectors[0].connect(top.inputConnectors[0])
        top.seq.vec.numBlocks = 14
        source = c.op('dance_motion_step')
        for i in range(14):
            top.par[f'vec{i}name'] = source.par[f'vec{i}name'].eval()
            for axis in 'xyzw':
                top.par[f'vec{i}value{axis}'].expr = f"op({source.path!r}).par.vec{i}value{axis}"
        return top

    try:
        source = host.create(rampTOP, 'input')
        source.par.outputresolution = 'custom'; source.par.resolutionw = 480; source.par.resolutionh = 270
        for name in defs['MODULES']:
            c = host.copy(demo.op(name), name=name)
            c.par.Enabled.mode = ParMode.CONSTANT; c.par.Enabled.bindExpr = ''; c.par.Enabled = True
            source.outputConnectors[0].connect(c.inputConnectors[0])
            c.par.Autotime = False; c.par.Manualtime = 3.7; c.par.Animationspeed = 0.
            c.op('animation_clock').module.reset(c, phase=3.7)
            c.par.Feedbackenabled = False; c.par.Mix = 1.; c.par.Danceenabled = False
            raw = c.op('dance_forces_switch').inputs[0]
            legacy_code = c.op('dance_motion_pixel').text
            # Repeated validation may run after installation; reconstruct only
            # the old analytic integration, not a different force equation.
            if 'responseAt' in legacy_code:
                legacy_code = defs['FORCE_FIELD'] + legacy_code[legacy_code.index('void main(){'):]
                legacy_code = legacy_code.replace('responseAt(', 'velocityAt(')
            yield
            before = pixels(raw)
            defs['install'](c, raw, root)
            yield
            output = c.op('out1_image'); rt = c.op('dance_forces_runtime').module
            material = c.op('dance_motion_out'); response = c.op('dance_response_step')
            check(name+'/default', float(c.par.Danceresponse) == .75)
            check(name+'/off_exact', np.array_equal(before, pixels(raw)))
            for value, expected in ((-1.,0.), (5.,5.), (7.,5.), (.75,.75)):
                c.par.Danceresponse = value
                check(name+'/range/'+str(value), float(c.par.Danceresponse) == expected)
            c.par.Danceenabled = True; c.par.Dancefadein = 0.
            c.par.Dancepush = 1.; c.par.Danceswirl = 0.; c.par.Danceacceleration = 1.
            force(c)
            analytic = reference(c, name+'_analytic', legacy_code, c.op('dance_motion_history'))
            target = reference(c, name+'_target', defs['FORCE_FIELD'] + '\nvoid main(){fragColor=TDOutputSwizzle(vec4(velocityAt(vUV.st),0.));}', c.op('dance_motion_zero'))
            c.par.Danceresponse = 0.; rt.reset_flow(c); yield; pixels(output)
            yield from tick(c, 5)
            direct, legacy = pixels(c.op('dance_motion_step')), pixels(analytic)
            info=c.create(infoDAT,name+'_compile_info'); info.par.op=analytic.path; info.cook(force=True)
            measurements[name] = dict(zero_delay_max_error=float(np.max(np.abs(direct-legacy))),
                zero_delay_peak=float(np.max(np.abs(legacy))), direct_center=direct[67,120].tolist(),
                legacy_center=legacy[67,120].tolist(), legacy_code=legacy_code,
                analytic_code=analytic.par.pixeldat.eval().text,
                direct_uniforms=[c.op('dance_motion_step').par['vec13value'+a].eval() for a in 'xyzw'],
                analytic_uniforms=[analytic.par['vec13value'+a].eval() for a in 'xyzw'])
            measurements[name]['compile_info']=info.text
            measurements[name]['reference_parameters']={p.name:str(p.eval()) for p in analytic.pars() if p.name in ('mode','pixeldat','vertexdat','computedat','compilebehavior','errorbehavior')}
            check(name+'/zero_delay_original_field', np.allclose(direct, legacy, rtol=1e-6, atol=1e-7))
            c.par.Danceresponse = .75; rt.reset_flow(c); yield; pixels(output)
            check(name+'/reset_velocity', not np.any(pixels(response)))
            check(name+'/reset_material', not np.any(pixels(material)))
            desired = pixels(target)
            for count in range(1, 46):
                yield from tick(c)
                if count in (1,15,45):
                    expected = desired * (1.-math.exp(-(count/30)/.75))
                    check(name+'/gradual_step/'+str(count), np.allclose(pixels(response), expected, atol=2e-5))
            measurements[name].update(after_1_5_seconds=float(pixels(response)[67,120,0]), target=float(desired[67,120,0]))
            held = pixels(response); travel = pixels(material)
            yield; pixels(output); yield
            check(name+'/pause_velocity', np.array_equal(held, pixels(response)))
            check(name+'/pause_material', np.array_equal(travel, pixels(material)))
            phase = rt.motion_time(c)
            c.par.Danceresponse = 2.; yield; pixels(output)
            check(name+'/live_edit_keeps_history', np.array_equal(held, pixels(response)) and np.array_equal(travel, pixels(material)))
            check(name+'/live_edit_keeps_motion_time', abs(phase-rt.motion_time(c)) < 1e-6)
            c.par.Danceresponse = .75
            force(c, -.12)
            yield from tick(c)
            check(name+'/reversal_no_kick', pixels(response)[67,120,0] > 0.)
            yield from tick(c, 45)
            check(name+'/reversal_eventually_turns', pixels(response)[67,120,0] < -.01)
            force(c, 0.)
            release_start = pixels(response)
            yield from tick(c, 30)
            check(name+'/release_is_gradual', np.allclose(pixels(response), release_start*math.exp(-1/.75), atol=2e-5))
            # Equal elapsed time at different frame intervals gives equal lag.
            force(c); rt.reset_flow(c); yield; pixels(output)
            yield from tick(c, 15, 1/30); at30 = pixels(response)
            rt.reset_flow(c); yield; pixels(output)
            yield from tick(c, 30, 1/60)
            check(name+'/frame_rate_independent', np.allclose(at30, pixels(response), atol=2e-5))
            c.par.Manualtime = float(c.par.Manualtime)-1.; yield; pixels(output)
            check(name+'/seek_clears_both', not np.any(pixels(response)) and not np.any(pixels(material)))
            for w,h in ((1920,1080),(3840,2160),(5760,1080)):
                source.par.resolutionw=w; source.par.resolutionh=h; yield
                a=pixels(output)
                check(name+'/resolution/'+str(w), a.shape[:2] == (h,w))
                check(name+'/small_response_texture/'+str(w), response.width == round(135*w/h) and response.height == 135)
            source.par.resolutionw=480; source.par.resolutionh=270
            c.par.Dancecache=str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json')
            c.par.Danceoffset=12.
            for top in (c.op('dance_motion_step'), response):
                for i in range(12):
                    for axis,j in zip('xyzw',range(4)):
                        top.par[f'vec{i+1}value{axis}'].expr=f"parent().op('dance_forces_runtime').module.sample(parent())[{i}][{j}]"
            rt.reset(c); yield; pixels(output)
            yield from tick(c, 45)
            check(name+'/recorded_motion_works', np.max(np.abs(pixels(response))) > 1e-5 and np.max(np.abs(pixels(material))) > 1e-5)
            check(name+'/native_errors', not c.errors(recurse=True))
            c.destroy()
        check('main/cues_unchanged', show.op('show_data').text == original)
        check('main/outputs_closed', not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception:
        failures.append(traceback.format_exc())
    finally:
        host.destroy()
        report=dict(ok=not failures, checks=checks, measurements=measurements, errors=failures, gpu=sysinfo.GPUName)
        (folder/'native-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Dance response:', report['ok'], len(checks), failures)
