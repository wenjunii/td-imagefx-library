"""Off-air pixel regression for Update Look, saved phases and cue playback.

Runs on a disposable Show Control copy. Never loads or writes personal shows,
opens audience windows, or enables audio. Install in a Text DAT and call start().
"""
import copy
import json
from pathlib import Path
import traceback

import numpy as np

STATE = {}


def _later():
    run("op({!r}).module.step()".format(me.path), delayFrames=2)


def _pixels(top):
    top.cook(force=True)
    return top.numpyArray(delayed=False).copy()


def _check(name, condition):
    STATE['checks'][name] = bool(condition)
    if not condition:
        raise AssertionError(name)


def _same(name, pixels):
    difference = float(np.max(np.abs(STATE['pixels'] - pixels)))
    STATE['differences'][name] = difference
    # A saved image must be exact. Separate GLSL cooks at full resolution may
    # round to adjacent 8-bit levels; permit at most one level, never a new look.
    exact = name.endswith(('/immediate_saved_preview', '/saved_preview_stays_frozen'))
    _check(name, difference <= (1e-6 if exact else 1.0 / 255.0 + 1e-6))


def start(width=320, height=180):
    original = op('/project1/imagefx_demo/show_control')
    ext = original.ext.ShowControlExt
    if ext.engine.state != 'stopped' or ext._look_edit:
        raise ValueError('Stop All and finish your draft before validation')
    if original.parent().op('look_animation_qa') is not None:
        raise ValueError('Previous QA copy still exists; it will not be replaced')
    qa = original.parent().copy(original, name='look_animation_qa')
    qa.initializeExtensions()
    qa.par.Renderwidth, qa.par.Renderheight = width, height
    qa.par.Audioenabled, qa.par.Masterblackout = False, True
    STATE.clear()
    STATE.update(show=qa, original=original, document=copy.deepcopy(ext.document),
                 phase='next', index=0, checks={}, differences={}, resolution=[width, height],
                 modules=('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow'))
    _later()


def step():
    qa = STATE['show']
    ext = qa.ext.ShowControlExt
    try:
        phase = STATE['phase']
        if phase == 'next':
            if STATE['index'] == len(STATE['modules']):
                _branch_checks(qa, ext)
                _finish()
                return
            name = STATE['modules'][STATE['index']]
            STATE['module'] = name
            cue = dict(ext.model.new_cue(), name='Phase QA ' + name, fade=0, duration=0,
                       look={'toggles': {ext.model.MODULE_TOGGLES[name]: True},
                             'modules': {name: {'Coverage': .7, 'Timescale': .3, 'Patternenabled': True}}})
            ext._replace_cues([cue]); ext.SelectCue(1); ext.RecallLook()
            draft = ext._look_edit['deck']
            ink = draft.op(name)
            _check(name + '/legacy_cue_speed_default', ink.par.Animationspeed.eval() == 1.)
            _check(name + '/legacy_cue_particle_defaults',
                   ink.par.Particlecolumns.eval() == 180 and ink.par.Particleshape.eval() == 'round'
                   and abs(ink.par.Particledepth.eval()-.78)<1e-6 and not ink.par.Particlefieldenabled)
            ink.par.Particlefieldenabled = True
            ink.par.Fielddensity, ink.par.Fieldsize = .6, 3.5
            ink.par.Particlecolumns, ink.par.Particleshape, ink.par.Particledepth = 72, 'square', .38
            ink.par.Feedbackenabled, ink.par.Feedbackamount = True, 0.
            ink.par.Feedbackdecay, ink.par.Feedbackzoom = .93, 1.005
            ink.par.Autotime, ink.par.Manualtime = False, 23.5
            STATE['pixels'] = _pixels(draft.op('out1_image'))
            ink.par.Fieldspeed = .8
            _same(name + '/point_speed_edit_preserves_frame', _pixels(draft.op('out1_image')))
            ink.par.Animationspeed = .5 + STATE['index'] * .75
            _same(name + '/speed_edit_preserves_frame', _pixels(draft.op('out1_image')))
            ink.par.Manualtime = 25.5
            STATE['render_phase'] = ink.op('animation_clock').module.sample(ink)
            STATE['field_phase'] = ink.op('animation_clock').module.field_sample(ink)
            _check(name + '/rate_applied_after_edit', abs(STATE['render_phase'] - (23.5 + 2 * ink.par.Animationspeed.eval())) < 1e-6)
            STATE['pixels'] = _pixels(draft.op('out1_image'))
            STATE['original_cue'] = copy.deepcopy(cue)
            STATE['ext'] = ext
            qa.par.Updatelook.pulse()
            STATE['phase'] = 'updated'
        elif phase == 'updated':
            name = STATE['module']
            cue = STATE['original_cue']
            STATE['update_status'] = qa.par.Status.eval()
            STATE['preview_debug'] = dict(target=str(qa.op('look_preview').par.top.eval()),
                result_exists=qa.op('look_result') is not None,
                result_size=([qa.op('look_result').width, qa.op('look_result').height] if qa.op('look_result') else None),
                result_locked=(qa.op('look_result').lock if qa.op('look_result') else None),
                extension_same=ext is STATE.get('ext'),
                lookstatus=qa.par.Lookstatus.eval())
            _check(name + '/update_finishes_draft', ext._look_edit is None and qa.op('look_editor') is None)
            _check(name + '/saved_phase', ext.document['cues'][0]['look']['animation'][name] == {'time': 25.5, 'running': False, 'render_time': STATE['render_phase'], 'field_time': STATE['field_phase']})
            _check(name + '/point_speed_saved', ext.document['cues'][0]['look']['modules'][name]['Fieldspeed'] == .8)
            _check(name + '/speed_saved', ext.document['cues'][0]['look']['modules'][name]['Animationspeed'] == .5 + STATE['index'] * .75)
            saved=ext.document['cues'][0]['look']['modules'][name]
            _check(name + '/feedback_settings_saved', saved['Feedbackenabled'] and saved['Feedbackamount']==0.
                   and saved['Feedbackdecay']==.93 and saved['Feedbackzoom']==1.005)
            _check(name + '/particle_controls_saved', saved['Particlecolumns']==72
                   and saved['Particleshape']=='square' and abs(saved['Particledepth']-.38)<1e-6
                   and saved['Particlefieldenabled'] and saved['Fielddensity']==.6 and saved['Fieldsize']==3.5)
            _check(name + '/metadata_unchanged', {k:v for k,v in ext.document['cues'][0].items() if k != 'look'} == {k:v for k,v in cue.items() if k != 'look'})
            _same(name + '/immediate_saved_preview', _pixels(qa.op('look_preview')))
            _check(name + '/saved_preview_no_errors', not qa.op('look_result').errors())
            STATE['phase'] = 'recall'
        elif phase == 'recall':
            name = STATE['module']
            _same(name + '/saved_preview_stays_frozen', _pixels(qa.op('look_preview')))
            _check(name + '/preview_button_enabled', qa.par.Openlookpreview.enable)
            ext.RecallLook()
            ink = ext._look_edit['deck'].op(name)
            _check(name + '/recall_clock', ink.par.Time.eval() == 25.5 and not ink.par.Autotime)
            _check(name + '/recall_render_phase', ink.op('animation_clock').module.sample(ink) == STATE['render_phase'])
            _check(name + '/recall_point_phase', ink.op('animation_clock').module.field_sample(ink) == STATE['field_phase'])
            _check(name + '/recall_feedback_history_clean', ink.fetch('imagefx_flow_feedback_state', None, search=False) is None)
            _check(name + '/recall_feedback_settings', bool(ink.par.Feedbackenabled) and ink.par.Feedbackamount.eval()==0.
                   and ink.par.Feedbackdecay.eval()==.93 and ink.par.Feedbackzoom.eval()==1.005)
            _check(name + '/speed_recalled', ink.par.Animationspeed.eval() == .5 + STATE['index'] * .75)
            _check(name + '/particle_controls_recalled', ink.par.Particlecolumns.eval()==72
                   and ink.par.Particleshape.eval()=='square' and abs(ink.par.Particledepth.eval()-.38)<1e-6
                   and ink.par.Particlefieldenabled and ink.par.Fielddensity.eval()==.6 and ink.par.Fieldsize.eval()==3.5)
            _same(name + '/recall_pixels', _pixels(qa.op('look_preview')))
            ext.CancelLook()
            ext.Preload()
            STATE['phase'] = 'ready'
            STATE['wait_frames'] = 0
        elif phase == 'ready':
            cue = ext.document['cues'][0]
            STATE['wait_frames'] += 1
            if not ext.ready(cue):
                if STATE['wait_frames'] > 600:
                    raise RuntimeError('Timed out preloading the phase test')
                _later(); return
            ext.Go()
            STATE['phase'] = 'playing'
        elif phase == 'playing':
            name = STATE['module']
            item = ext.tracks.get(1)
            _check(name + '/go_started', item is not None)
            ink = item['deck'].op(name)
            _check(name + '/go_clock', ink.par.Time.eval() == 25.5)
            _check(name + '/go_render_phase', ink.op('animation_clock').module.sample(ink) == STATE['render_phase'])
            _check(name + '/go_point_phase', ink.op('animation_clock').module.field_sample(ink) == STATE['field_phase'])
            _check(name + '/go_feedback_settings', bool(ink.par.Feedbackenabled) and ink.par.Feedbackamount.eval()==0.
                   and ink.par.Feedbackdecay.eval()==.93 and ink.par.Feedbackzoom.eval()==1.005)
            _check(name + '/go_speed', ink.par.Animationspeed.eval() == .5 + STATE['index'] * .75)
            _check(name + '/particle_controls_go', ink.par.Particlecolumns.eval()==72
                   and ink.par.Particleshape.eval()=='square' and abs(ink.par.Particledepth.eval()-.38)<1e-6
                   and ink.par.Particlefieldenabled and ink.par.Fielddensity.eval()==.6 and ink.par.Fieldsize.eval()==3.5)
            _same(name + '/go_pixels', _pixels(item['deck'].op('out1_image')))
            ext.Stopall()
            ext.RecallLook()
            draft = ext._look_edit['deck']
            ink = draft.op(name)
            # Capture a running clock at a known nonzero phase, including a
            # negative time scale. The current frame's origin is exact.
            ink.store('imagefx_look_time_origin', absTime.seconds)
            ink.store('imagefx_look_time_phase', 17.25)
            ink.par.Timescale, ink.par.Autotime = -.5, True
            render_phase = ink.op('animation_clock').module.sample(ink)
            field_phase = ink.op('animation_clock').module.field_sample(ink)
            ext.UpdateLook()
            _check(name + '/running_clock_saved', ext.document['cues'][0]['look']['animation'][name] == {'time': 17.25, 'running': True, 'render_time': render_phase, 'field_time': field_phase})
            ext.RecallLook()
            ink = ext._look_edit['deck'].op(name)
            _check(name + '/running_recall_phase', ink.par.Time.eval() == 17.25 and bool(ink.par.Autotime))
            review = qa.op('show_review_export').module
            review._set_time(ext._look_edit['deck'], ext.model.MODULES, 4)
            _check(name + '/export_phase_and_reverse', ink.par.Time.eval() == 15.25)
            _check(name + '/export_speed', ink.par.Animationspeed.eval() == .5 + STATE['index'] * .75)
            _check(name + '/export_render_phase', abs(ink.op('animation_clock').module.sample(ink) - (render_phase - 2 * ink.par.Animationspeed.eval())) < 1e-6)
            _check(name + '/export_point_phase', abs(ink.op('animation_clock').module.field_sample(ink) - (field_phase - 2 * ink.par.Animationspeed.eval() * .8)) < 1e-6)
            ext.CancelLook()
            STATE['index'] += 1
            STATE['phase'] = 'next'
        _later()
    except Exception:
        _finish(traceback.format_exc())


def _branch_checks(qa, ext):
    cue = dict(ext.model.new_cue(), look={'toggles': {'Imagecompositionenabled': True}})
    ext._replace_cues([cue]); ext.SelectCue(1); ext.RecallLook()
    draft = ext._look_edit['deck']
    composition = draft.op('image_composition')
    composition.par.Autotime, composition.par.Manualtime = False, 7
    for i, name in enumerate(('a_effects', 'b_effects')):
        child = composition.op(name + '/ink_dream_flow')
        child.par.Manualtime = 11.5 + i
        child.par.Timescale = .25
        child.par.Animationspeed = .5 + i
        child.op('animation_clock').module.reset(child, phase=19. + i * 12.)
    ext.UpdateLook(); ext.RecallLook()
    composition = ext._look_edit['deck'].op('image_composition')
    for i, name in enumerate(('a_effects', 'b_effects')):
        _check(name + '/phase_not_double_counted', composition.op(name + '/ink_dream_flow').par.Time.eval() == 11.5 + i)
        _check(name + '/speed_recalled', composition.op(name + '/ink_dream_flow').par.Animationspeed.eval() == .5 + i)
        child = composition.op(name + '/ink_dream_flow')
        _check(name + '/render_phase_recalled', child.op('animation_clock').module.sample(child) == 19. + i * 12.)
    composition.par.Manualtime = 11
    for i, name in enumerate(('a_effects', 'b_effects')):
        _check(name + '/relative_parent_clock', composition.op(name + '/ink_dream_flow').par.Time.eval() == 12.5 + i)
        child = composition.op(name + '/ink_dream_flow')
        _check(name + '/relative_render_clock', child.op('animation_clock').module.sample(child) == 19. + i * 12. + .5 + i)
    ext.CancelLook()


def _finish(error=None):
    qa = STATE['show']
    _check('personal_show_unchanged', STATE['original'].ext.ShowControlExt.document == STATE['document'])
    _check('audience_and_audio_disarmed', bool(qa.par.Masterblackout) and not qa.par.Audioenabled)
    report = dict(ok=not error and all(STATE['checks'].values()), checks=STATE['checks'],
                  pixel_max_differences=STATE['differences'], error=error,
                  update_status=STATE.get('update_status'), preview_debug=STATE.get('preview_debug'),
                  resolution=STATE['resolution'],
                  pixel_tolerance='Saved preview: exact; independent renders: at most one 8-bit level',
                  scope='Isolated saved-preview, Recall, GO, export clock and branch tests')
    path = Path(qa.par.Libraryroot.eval()) / 'build/envoy-validation/look-animation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    qa.ext.ShowControlExt.stop_all()
    qa.destroy()
    print('LOOK ANIMATION:', report['ok'], len(report['checks']), error or '')
