"""Real-frame tests of point movement and default-off history on disposable copies.

Install this source in a Text DAT, call start(). Does not save projects/shows,
open outputs, or enable audio. Reports actual alpha-support motion, not RGB only.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

STATE = {}
NAMES = ('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow')


def _pixels(node):
    node.cook(force=True)
    result = node.numpyArray(delayed=False)
    if result is None or not np.isfinite(result).all():
        raise AssertionError('Nonfinite/missing pixels: ' + node.path)
    return result.copy()


def _check(name, value):
    STATE['checks'][name] = bool(value)
    if not value:
        raise AssertionError(name)


def _difference(a, b):
    return float(np.mean(np.abs(a-b)))


def _tests():
    for name in NAMES:
        module = STATE['host'].copy(op(STATE['module_root']+'/'+name), name=name)
        module.par.Enabled.mode = ParMode.CONSTANT
        module.par.Enabled.bindExpr = ''
        module.par.Enabled = True
        source = STATE['host'].create(constantTOP, name+'_source')
        source.par.outputresolution = 'custom'
        source.par.resolutionw, source.par.resolutionh = 320, 180
        source.outputConnectors[0].connect(module.inputConnectors[0])
        for p in module.customPars:
            if not p.readOnly and not p.isPulse and p.name != 'Enabled':
                p.val = p.default
        module.par.Autotime = False
        output = module.op('out1_image')
        raw = module.op('flow_feedback_source')
        clock = module.op('animation_clock').module
        prefix = name+'/'
        _check(prefix+'feedback_default_off', not module.par.Feedbackenabled)
        _check(prefix+'field_default_off', not module.par.Particlefieldenabled)
        module.par.Manualtime = 0.
        clock.reset(module); clock.field_reset(module)
        _check(prefix+'feedback_off_exact', np.array_equal(_pixels(raw), _pixels(output)))
        module.par.Particlefieldenabled = True
        module.par.Particlecolumns, module.par.Fieldsize = 36, 3.
        pixel = module.op('pixel_shader_'+name)
        original = pixel.text
        # Isolate particle geometry so RGB/visibility changes in the flow cannot
        # accidentally pass the motion test. This is a disposable test shader.
        ending = 'fragColor=TDOutputSwizzle(mix(source,result,clamp(uMix,0.,1.)));'
        pixel.text = original.replace(ending, 'float support=movingFieldGrains(screen,seed).x; fragColor=TDOutputSwizzle(vec4(vec3(support),support));')
        still = _pixels(output)
        module.par.Fieldspeed = 1.
        _check(prefix+'speed_edit_no_position_jump', np.array_equal(still, _pixels(output)))
        module.par.Manualtime = .5
        moved = _pixels(output)
        _check(prefix+'positions_move_not_just_color', _difference(still[:,:,3], moved[:,:,3])>.01)
        phase = clock.field_sample(module)
        module.par.Fieldspeed = 0.
        _check(prefix+'hold_edit_no_position_jump', np.array_equal(moved, _pixels(output)))
        module.par.Manualtime = 3.
        _check(prefix+'point_speed_zero_holds_positions', np.array_equal(moved, _pixels(output)))
        _check(prefix+'point_speed_zero_holds_phase', clock.field_sample(module)==phase)
        module.par.Fieldspeed = -1.
        _pixels(output)  # Evaluate the changed rate before advancing the test clock.
        module.par.Manualtime = 3.5
        _check(prefix+'reverse_returns_positions', _difference(still, _pixels(output))<.001)
        module.par.Fieldspeed = 1.
        clock.field_reset(module, phase=7.999)
        edge = _pixels(output)
        clock.field_reset(module, phase=8.001)
        _check(prefix+'motion_continuous', _difference(edge, _pixels(output))<.02)
        pixel.text = original
        module.par.Fieldspeed = 1.
        clock.field_reset(module, phase=0.)
        # Warm actual history across distinct frames, not forced same-frame cooks.
        module.par.Manualtime = 0.
        clock.reset(module); clock.field_reset(module)
        module.par.Feedbackenabled = True
        module.par.Feedbackamount = 1.
        module.par.Feedbackdecay = .95
        module.par.Feedbackreset.pulse()
        yield  # Parameter Execute pulses are delivered at the frame boundary.
        _check(prefix+'first_frame_clean', _difference(_pixels(raw), _pixels(output))<.001)
        yield
        for i in range(1, 8):
            module.par.Manualtime = i/30.
            _pixels(output)
            yield
        held = _pixels(output)
        _check(prefix+'history_trails_visible', _difference(_pixels(raw), held)>1e-4)
        yield
        _check(prefix+'pause_holds_feedback', _difference(held, _pixels(output))<.001)
        module.par.Feedbackreset.pulse()
        yield
        _check(prefix+'reset_clears_trails', _difference(_pixels(raw), _pixels(output))<.001)
        module.par.Feedbackamount = 0.
        _check(prefix+'amount_zero_exact', np.array_equal(_pixels(raw), _pixels(output)))
        module.par.Feedbackamount = 1.
        module.par.Feedbackdecay = 0.
        yield
        module.par.Manualtime += .1
        _check(prefix+'retention_zero_no_history', _difference(_pixels(raw), _pixels(output))<.001)
        module.par.Feedbackdecay = .95
        for parameter, value in (('Feedbackzoom', 1.02), ('Feedbackrotate', 2.),
                                 ('Feedbackoffsetx', .02), ('Feedbackoffsety', -.02)):
            # A paired clone receives the same starting frame and clock but no
            # transform. Any difference is the tested control, not elapsed time.
            module.par.Manualtime = 0.
            module.par[parameter].val = value
            clock.reset(module); clock.field_reset(module)
            module.par.Feedbackreset.pulse()
            pair = STATE['host'].copy(module, name='comparison')
            source.outputConnectors[0].connect(pair.inputConnectors[0])
            pair.par[parameter].val = pair.par[parameter].default
            pair.par.Feedbackreset.pulse()
            yield
            _pixels(output); _pixels(pair.op('out1_image'))
            yield
            module.par.Manualtime = pair.par.Manualtime = .1
            _check(prefix+parameter+'_changes_history', _difference(_pixels(output), _pixels(pair.op('out1_image')))>1e-5)
            _check(prefix+parameter+'_accepted', module.par[parameter].eval()==value)
            pair.destroy()
            module.par[parameter].val = module.par[parameter].default
            yield
        module.par.Manualtime = 10.
        _check(prefix+'seek_clears_history', _difference(_pixels(raw), _pixels(output))<.001)
        module.par.Feedbackenabled = False
        _check(prefix+'feedback_off_roundtrip_exact', np.array_equal(_pixels(raw), _pixels(output)))
        yield
        module.par.Feedbackenabled = True
        yield
        _check(prefix+'reenable_clean', _difference(_pixels(raw), _pixels(output))<.001)
        module.par.Background = 'transparent'
        module.par.Fielddensity = 0.
        module.par.Feedbackreset.pulse()
        yield
        empty = _pixels(output)
        _check(prefix+'empty_alpha_stays_zero', float(np.max(empty[:,:,3]))<1e-6)
        _check(prefix+'empty_rgb_stays_zero', float(np.max(np.abs(empty[:,:,:3])))<1e-6)
        module.par.Enabled = False
        _check(prefix+'module_bypass_exact', np.array_equal(_pixels(source), _pixels(output)))
        _check(prefix+'no_native_errors', not module.errors(recurse=True))
        module.destroy(); source.destroy()
        yield


def start(module_root='/project1/imagefx_demo'):
    if op('/project1/flow_history_validation') is not None:
        raise RuntimeError('Previous validation still running')
    STATE.clear()
    STATE.update(module_root=module_root, host=op('/project1').create(baseCOMP,'flow_history_validation'), checks={})
    STATE['steps'] = _tests()
    run("op({!r}).module.step()".format(me.path), delayFrames=1)


def step():
    try:
        next(STATE['steps'])
        run("op({!r}).module.step()".format(me.path), delayFrames=1)
    except StopIteration:
        _finish()
    except Exception:
        _finish(traceback.format_exc())


def _finish(error=None):
    root = Path(project.folder)
    if not (root/'touchdesigner/scripts').is_dir():
        # Fixtures may run in an unsaved blank session; caller supplies root.
        root = Path(me.fetch('repository_root'))
    report = dict(ok=not error and all(STATE['checks'].values()), checks=STATE['checks'],
                  error=error, generated_at=datetime.now(timezone.utc).isoformat())
    target = root/'build/envoy-validation/flow-feedback.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    STATE['host'].destroy()
    print('FLOW MOTION / FEEDBACK', 'PASS' if report['ok'] else 'FAIL', error or len(report['checks']))
