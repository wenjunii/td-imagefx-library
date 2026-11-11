"""Off-air native regressions: old shows, real recall/live edit and motion media.

Uses a disposable Show Control. Never saves the user's show, opens outputs,
starts a camera or launches analysis. Prepared local assets must already exist.
"""
import copy
import importlib
import json
from pathlib import Path
import traceback
import numpy as np

STATE = {}


def start(root, baseline=False):
    if STATE:
        raise ValueError('Legacy motion validation is already running')
    STATE.update(root=Path(root), baseline=bool(baseline))
    STATE['generator'] = validate()
    advance()


def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=2)
    except StopIteration:
        STATE.clear()


def validate():
    root = STATE['root']; baseline = STATE['baseline']
    folder = root/'build/dance-forces/legacy-look-20261027'
    folder.mkdir(parents=True, exist_ok=True)
    original = op('/project1/imagefx_demo/show_control'); demo = original.parent()
    assert original.ext.ShowControlExt.engine.state == 'stopped'
    assert original.ext.ShowControlExt._look_edit is None
    original_text = original.op('show_data').text
    saved_files = {p: p.read_bytes() if p.exists() else None for p in (
        root/'.imagefx/dance-forces-live.json', root/'.imagefx/puppet-live.json',
        Path(original.par.Showfile.eval()))}
    assert demo.op('legacy_motion_qa') is None
    qa = demo.copy(original, name='legacy_motion_qa')
    qa.op('show_tick').par.active = False
    if not baseline:
        from tdimagefx import show as model
        importlib.reload(model)
        qa.op('ShowControlExt').text = (root/'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    qa.initializeExtensions()
    ext = qa.ext.ShowControlExt
    checks = {}; measurements = {}; clock = [0.]; error = None

    def check(name, value):
        checks[name] = bool(value)
        (folder/'progress.json').write_text(json.dumps(dict(last=name, checks=len(checks))), encoding='utf-8')
        assert value, name

    def pixels(top):
        top.cook(force=True)
        value = top.numpyArray(delayed=False)
        assert value is not None and np.isfinite(value).all(), top.path
        assert not top.errors(), top.errors()
        return value.copy()

    def tick(dt=0):
        clock[0] += dt; ext.Tick()
        assert not ext.engine.errors, str(ext.engine.errors)

    def until(predicate):
        for _ in range(900):
            tick(); yield
            if predicate(): return
        raise AssertionError('Cue preparation timed out: '+qa.par.Status.eval())

    def load(cue):
        ext.engine.stop()
        document = dict(kind=ext.model.SHOW_KIND, schema_version=1, cues=[cue], mapping={})
        path = folder/'fixture.show.json'
        path.write_text(json.dumps(document, indent=2), encoding='utf-8')
        qa.par.Showfile = str(path); ext.LoadShow()
        qa.par.Renderwidth, qa.par.Renderheight = 640, 360
        qa.par.Routingmode = 'independent'; qa.par.Masterblackout = False
        qa.par.Audioenabled = False; qa.par.Testpattern = False
        for i in (1, 2, 3):
            qa.par['Output%dwidth'%i] = 640; qa.par['Output%dheight'%i] = 360
        ext.engine.clock = lambda:clock[0]; ext.engine._last = clock[0]
        return copy.deepcopy(ext.document)

    def legacy(look):
        look = copy.deepcopy(look)
        look.pop('force_files', None); look.pop('puppet_files', None)
        look.get('modules', {}).pop('dance_puppet', None)
        look.get('toggles', {}).pop('Dancepuppetenabled', None)
        look.get('animation', {}).pop('dance_puppet', None)
        for name in ext.model.FLOW_MODULES:
            values = look.get('modules', {}).get(name, {})
            for key in list(values):
                if key.startswith('Dance'): del values[key]
        for name, branch in look.get('branches', {}).items():
            look['branches'][name] = legacy(branch)
        return look

    def enable_force(c):
        c.par.Danceenabled = True; c.par.Dancefadein = 0.
        c.par.Danceoffset = 12.; c.par.Dancethreshold = 0.

    try:
        yield
        base = legacy(original.ext.ShowControlExt._capture_look(demo, active=False))
        for key in base['toggles']: base['toggles'][key] = False
        for name in ext.model.FLOW_MODULES:
            tag = name
            look = copy.deepcopy(base); look['toggles'][ext.model.MODULE_TOGGLES[name]] = True
            look['modules'][name]['Timescale'] = 1.
            look['animation'] = {name:dict(time=0., running=True)}
            cue = dict(ext.model.new_cue(), name='Legacy '+name, fade=0, duration=0, look=look)
            document = load(cue); ext.RecallLook(); yield
            deck = ext._look_edit['deck']; c = deck.op(name)
            if baseline:
                check(tag+'/reproduced_missing_cache', c.par.Dancecache.eval() == '')
                ext.CancelLook(); continue
            expected = str(Path(demo.op(name).par.Dancecache.eval()).resolve())
            check(tag+'/recall_local_cache', c.par.Dancecache.eval() == expected)
            check(tag+'/legacy_force_still_off', not c.par.Danceenabled)
            check(tag+'/recall_does_not_change_cue', ext.document == document)
            enable_force(c); yield
            start_time = float(c.par.Time)
            for _ in range(24):
                yield; pixels(c.op('out1_image'))
            material = pixels(c.op('dance_motion_out'))
            check(tag+'/recall_clock_advances', float(c.par.Time) > start_time)
            check(tag+'/recall_real_motion', np.abs(material).max() > 1e-5)
            measurements[tag] = dict(recall_material=float(np.abs(material).max()))
            check(tag+'/recall_no_errors', not deck.errors(recurse=True))
            ext.CancelLook(); ext.engine.go(0)
            yield from until(lambda:cue['id'] in ext.engine.active)
            ext.SelectCue(1); ext.EditRunningLook()
            deck = ext.RunningLookDeck(); c = deck.op(name)
            check(tag+'/running_local_cache', c.par.Dancecache.eval() == expected)
            enable_force(c); yield
            for _ in range(24):
                tick(1/30); yield; pixels(c.op('out1_image'))
            check(tag+'/running_real_motion', np.abs(pixels(c.op('dance_motion_out'))).max() > 1e-5)
            check(tag+'/live_edit_not_saved_yet', ext.document == document)
            time_before = float(c.par.Time); ext.CancelLook(); yield
            check(tag+'/cancel_restores_off', not c.par.Danceenabled)
            check(tag+'/cancel_keeps_clock', float(c.par.Time) == time_before)
            check(tag+'/cancel_keeps_cue', ext.document == document)
            ext.EditRunningLook(); enable_force(c); c.par.Dancepush = .7; yield
            ext.UpdateLook(); yield
            saved = ext.document['cues'][0]['look']
            check(tag+'/update_pins_media', saved['force_files'][name]['Dancecache'] == expected)
            check(tag+'/update_saves_values', saved['modules'][name]['Danceenabled'] and saved['modules'][name]['Dancepush'] == .7)
            ext.engine.stop(); ext.SaveShow(); ext.LoadShow()
            ext.engine.clock = lambda:clock[0]; ext.engine._last = clock[0]
            ext.engine.go(0); yield from until(lambda:cue['id'] in ext.engine.active)
            c = ext.tracks[1]['deck'].op(name)
            check(tag+'/saved_show_force_restored', bool(c.par.Danceenabled) and c.par.Dancecache.eval() == expected)
            for _ in range(12):
                tick(1/30); yield; pixels(c.op('out1_image'))
            ext.Pause(); held = pixels(c.op('dance_motion_out')); t = float(c.par.Time)
            tick(.2); yield
            check(tag+'/pause_holds_field', float(c.par.Time) == t and np.array_equal(held,pixels(c.op('dance_motion_out'))))
            ext.Resume(); tick(1/30); yield; tick(1/30); yield
            check(tag+'/resume_advances_field', float(c.par.Time) > t and not np.array_equal(held,pixels(c.op('dance_motion_out'))))
            ext.engine.stop()

        if not baseline:
            # Independent layers must use their own designer media and clock.
            look = copy.deepcopy(base); look['toggles']['Imagecompositionenabled'] = True
            look['animation'] = {'image_composition': dict(time=0., running=True)}
            for branch in ('a_effects', 'b_effects'):
                child = look['branches'][branch]
                for key in child['toggles']: child['toggles'][key] = False
                child['toggles']['Inkdreamenabled'] = True
            cue = dict(ext.model.new_cue(), name='Legacy independent layers', fade=0, duration=0, look=look)
            load(cue); ext.RecallLook(); yield
            deck = ext._look_edit['deck']
            for branch in ('a_effects', 'b_effects'):
                child = deck.op('image_composition/'+branch)
                source = demo.op('image_composition/'+branch)
                for name in ext.model.FLOW_MODULES:
                    check(branch+'/'+name+'/local_cache', child.op(name).par.Dancecache.eval() == str(Path(source.op(name).par.Dancecache.eval()).resolve()))
                enable_force(child.op('ink_dream_flow'))
            yield
            for _ in range(20):
                yield; pixels(deck.op('out1_image'))
            for branch in ('a_effects', 'b_effects'):
                child = deck.op('image_composition/'+branch)
                check(branch+'/moving_force_field', np.abs(pixels(child.op('ink_dream_flow/dance_motion_out'))).max() > 1e-5)
                check(branch+'/puppet_local_movie', child.op('dance_puppet').par.Renderfile.eval() == str(Path(demo.op('image_composition/'+branch+'/dance_puppet').par.Renderfile.eval()).resolve()))
            ext.UpdateLook(); yield
            for branch in ('a_effects', 'b_effects'):
                check(branch+'/update_captures_motion', ext.document['cues'][0]['look']['branches'][branch]['modules']['ink_dream_flow']['Danceenabled'])

        # An older show that already has puppet files must retain those files.
        puppet_cue = next(copy.deepcopy(c) for c in original.ext.ShowControlExt.document['cues']
                          if c['look'].get('puppet_files', {}).get('Renderfile'))
        puppet_cue.update(fade=0, duration=0, enabled=True, at=None, follow='manual', track=1)
        document = load(puppet_cue); ext.RecallLook(); yield
        puppet = ext._look_edit['deck'].op('dance_puppet')
        check('puppet/old_saved_movie_preserved', puppet.par.Renderfile.eval() == document['cues'][0]['look']['puppet_files']['Renderfile'])
        if not baseline:
            puppet.par.Fadein = 0.; puppet.par.Autotime = True; yield
            for _ in range(12): yield
            a = pixels(puppet.op('puppet_rgba')); t = float(puppet.par.Time)
            for _ in range(12): yield
            b = pixels(puppet.op('puppet_rgba'))
            check('puppet/recall_animates', float(puppet.par.Time) > t and not np.allclose(a,b))
            check('puppet/recall_transparent', b[:,:,3].min() < .001 and b[:,:,3].max() > .95)
            puppet.par.Pausepreview.pulse(); yield; t = float(puppet.par.Time)
            for _ in range(3): yield
            check('puppet/preview_pause', float(puppet.par.Time) == t)
            puppet.par.Resumepreview.pulse(); yield
            for _ in range(3): yield
            check('puppet/preview_resume', float(puppet.par.Time) > t)
        ext.CancelLook()
        if not baseline:
            ext.engine.go(0); yield from until(lambda:puppet_cue['id'] in ext.engine.active)
            puppet = ext.tracks[1]['deck'].op('dance_puppet')
            tick(2.); yield; a = pixels(puppet.op('puppet_rgba'))
            tick(.5); yield; b = pixels(puppet.op('puppet_rgba'))
            check('puppet/old_cue_go_animates', not np.allclose(a,b) and b[:,:,3].max() > .9)
            ext.SelectCue(1); ext.EditRunningLook(); puppet.par.Feedbackenabled = True
            puppet.par.Trailamount = .65; puppet.par.Trailhalf = .5; yield
            for _ in range(8):
                tick(1/30); yield; pixels(puppet.op('puppet_rgba'))
            trail = pixels(puppet.op('puppet_rgba'))
            puppet.par.Feedbackenabled = False; yield
            check('puppet/live_feedback_visible', not np.allclose(trail,pixels(puppet.op('puppet_rgba'))))
            puppet.par.Feedbackenabled = True; yield; ext.UpdateLook(); yield
            check('puppet/update_saves_feedback', ext.document['cues'][0]['look']['modules']['dance_puppet']['Feedbackenabled'])
            check('puppet/update_keeps_movie', ext.document['cues'][0]['look']['puppet_files']['Renderfile'] == document['cues'][0]['look']['puppet_files']['Renderfile'])
            ext.engine.stop(); ext.SaveShow(); ext.LoadShow(); ext.RecallLook(); yield
            check('puppet/reload_keeps_feedback', bool(ext._look_edit['deck'].op('dance_puppet').par.Feedbackenabled))
            ext.CancelLook()

        # Add the puppet to a cue older than the puppet feature.
        cue = dict(ext.model.new_cue(), name='Before puppet existed', fade=0, duration=0, look=base)
        document = load(cue); ext.RecallLook(); yield
        puppet = ext._look_edit['deck'].op('dance_puppet')
        if baseline:
            check('puppet/reproduced_empty_pre_feature_media', puppet.par.Renderfile.eval() == '')
        else:
            check('puppet/pre_feature_local_movie', puppet.par.Renderfile.eval() == str(Path(demo.op('dance_puppet').par.Renderfile.eval()).resolve()))
            check('puppet/pre_feature_stays_off', not puppet.par.Enabled)
            puppet.par.Enabled = True; puppet.par.Fadein = 0.; puppet.par.Autotime = True; yield
            for _ in range(8): yield
            check('puppet/enable_on_legacy_cue_has_pixels', pixels(puppet.op('puppet_rgba'))[:,:,3].max() > .95)
            check('puppet/pre_feature_cue_unchanged', ext.document == document)
        ext.CancelLook()
        if not baseline:
            ext.engine.go(0); yield from until(lambda:cue['id'] in ext.engine.active)
            ext.SelectCue(1); ext.EditRunningLook()
            puppet = ext.RunningLookDeck().op('dance_puppet')
            puppet.par.Enabled = True; puppet.par.Fadein = 0.; yield
            tick(1.); yield; a = pixels(puppet.op('puppet_rgba'))
            tick(.5); yield; b = pixels(puppet.op('puppet_rgba'))
            check('puppet/add_to_old_running_cue_animates', b[:,:,3].max() > .95 and not np.allclose(a,b))
            ext.CancelLook(); yield
            check('puppet/cancel_removes_added_puppet', not puppet.par.Enabled and ext.document == document)
            ext.engine.stop()
        check('native/no_operator_errors', not qa.errors(recurse=True))
        check('native/main_cues_preserved', original.op('show_data').text == original_text)
        check('native/no_external_files_changed', all((p.read_bytes() if p.exists() else None) == data for p,data in saved_files.items()))
        check('native/no_output_windows', not any(w.isOpen for w in qa.op('show_output_mode').module.windows(qa) if w))
    except Exception:
        error = traceback.format_exc()
        measurements['status'] = qa.par.Status.eval()
        measurements['native_errors'] = qa.errors(recurse=True)
    finally:
        ext.engine.stop()
        if ext._look_edit is not None: ext.CancelLook()
        qa.destroy()
    result = dict(ok=error is None,checks=checks,measurements=measurements,error=error)
    (folder/('baseline.json' if baseline else 'validation.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('LEGACY MOTION QA:', len(checks), 'PASS' if error is None else error)
