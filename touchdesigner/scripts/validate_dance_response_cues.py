"""Off-air response-delay capture, recall and live-edit regression checks."""
import copy
import json
from pathlib import Path
import traceback
import numpy as np

STATE = {}


def start(root, report_dir=None):
    if STATE:
        raise ValueError('Cue response validation already running')
    STATE['root'] = Path(root)
    STATE['folder'] = Path(report_dir) if report_dir else Path(root)/'build/dance-forces/response-20261027'
    STATE['generator'] = validate()
    advance()


def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=2)
    except StopIteration:
        STATE.clear()


def validate():
    root = STATE['root']
    folder = STATE['folder']
    folder.mkdir(parents=True, exist_ok=True)
    demo = op('/project1/imagefx_demo')
    show = demo.op('show_control'); ext = show.ext.ShowControlExt
    assert ext.engine.state == 'stopped' and not ext.tracks and not ext.prepared and not ext._look_edit
    assert not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w)
    original = show.op('show_data').text
    original_look = ext._capture_look(demo, active=False)
    host = op('/project1').create(baseCOMP, 'dance_response_cue_qa')
    checks, errors = {}, []

    def check(name, value):
        checks[name] = bool(value)
        assert value, name

    def field(c, name):
        node = c.op(name); node.cook(force=True)
        value = node.numpyArray(delayed=False)
        assert value is not None and np.isfinite(value).all()
        return value.copy()

    try:
        deck = host.copy(show.op('deck_template'), name='cue')
        deck.allowCooking = True
        deck.op('fx_rack').initializeExtensions()
        for name, toggle in (('ink_dream_flow', 'Inkdreamenabled'),
                             ('ink_brush_flow', 'Inkbrushenabled'),
                             ('ink_radial_flow', 'Inkradialenabled')):
            look = ext._capture_look(demo, active=False, capture_animation=True)
            look['toggles'][toggle] = True
            look['modules'][name].update(Danceenabled=True, Dancefadein=0.,
                Danceresponse=1.25, Dancespace='canvas', Danceoffset=12.)
            look['force_files'][name] = {'Dancecache': str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json'), 'Dancevideo': ''}
            ext._apply_look(deck, look); yield
            c = deck.op(name); runtime = c.op('dance_forces_runtime').module
            check(name+'/recall/value', float(c.par.Danceresponse) == 1.25)
            check(name+'/recall/space', c.par.Dancespace.eval() == 'canvas')
            check(name+'/recall/zero_material', np.abs(field(c, 'dance_motion_out')).max() == 0.)
            check(name+'/recall/zero_response', np.abs(field(c, 'dance_response_step')).max() == 0.)
            check(name+'/recall/inpoint', abs(runtime.motion_time(c)-12.) < 1e-6)
            for _ in range(30):
                c.par.Manualtime = float(c.par.Manualtime)+1/30
                yield
                field(c, 'dance_motion_out')
            check(name+'/play/response', np.abs(field(c, 'dance_response_step')).max() > 1e-5)
            check(name+'/play/material', np.abs(field(c, 'dance_motion_out')).max() > 1e-5)
            saved = ext._capture_look(deck, active=False, capture_animation=True)
            check(name+'/capture/value', saved['modules'][name]['Danceresponse'] == 1.25)
            check(name+'/capture/space', saved['modules'][name]['Dancespace'] == 'canvas')
            c.par.Danceresponse = 2.5; c.par.Dancespace = 'pattern'; yield
            held = field(c, 'dance_motion_out')
            response = field(c, 'dance_response_step')
            phase = runtime.motion_time(c)
            ext._restore_running_values(deck, saved); yield
            check(name+'/live/discard_value', float(c.par.Danceresponse) == 1.25)
            check(name+'/live/discard_space', c.par.Dancespace.eval() == 'canvas')
            check(name+'/live/clock', abs(runtime.motion_time(c)-phase) < 1e-6)
            check(name+'/live/material', np.array_equal(held, field(c, 'dance_motion_out')))
            check(name+'/live/response', np.array_equal(response, field(c, 'dance_response_step')))
            ext._apply_look(deck, look); yield
            check(name+'/retrigger/material', np.abs(field(c, 'dance_motion_out')).max() == 0.)
            check(name+'/retrigger/response', np.abs(field(c, 'dance_response_step')).max() == 0.)
            legacy = copy.deepcopy(look)
            legacy['modules'][name].pop('Danceresponse')
            legacy['modules'][name].pop('Dancespace')
            ext._apply_look(deck, legacy); yield
            check(name+'/legacy/default', float(c.par.Danceresponse) == .75)
            check(name+'/legacy/space', c.par.Dancespace.eval() == 'pattern')
            check(name+'/native/errors', not c.errors(recurse=True))
        look = ext._capture_look(demo, active=False)
        for branch, value in (('a_effects', 1.1), ('b_effects', 2.1)):
            for name in ext.model.FLOW_MODULES:
                look['branches'][branch]['modules'][name]['Danceresponse'] = value
                look['branches'][branch]['modules'][name]['Dancespace'] = 'canvas' if branch=='a_effects' else 'pattern'
        ext._apply_look(deck, look, active=False); yield
        saved = ext._capture_look(deck, active=False)
        for branch, value in (('a_effects', 1.1), ('b_effects', 2.1)):
            for name in ext.model.FLOW_MODULES:
                check(branch+'/'+name+'/recapture',
                      saved['branches'][branch]['modules'][name]['Danceresponse'] == value)
                check(branch+'/'+name+'/space', saved['branches'][branch]['modules'][name]['Dancespace'] ==
                      ('canvas' if branch=='a_effects' else 'pattern'))
        check('main/cues_unchanged', show.op('show_data').text == original)
        check('main/look_unchanged', ext._capture_look(demo, active=False) == original_look)
        check('main/outputs_closed', not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        host.destroy()
        (folder/'cue-validation.json').write_text(json.dumps(
            dict(ok=not errors, checks=checks, errors=errors), indent=2), encoding='utf-8')
        print('Cue response checks:', not errors, len(checks), errors)
