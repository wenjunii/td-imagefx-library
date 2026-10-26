"""Real-frame live-cue editing regression; never opens hardware outputs.

Run as a Text DAT with module.start(), with the main Show Control stopped.
Only a disposable show copy and generated/local QA fixtures are used.
"""
import copy
import json
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = {}


def start():
    if RUN.get('generator') is not None:
        raise ValueError('Running-look validation is already active')
    RUN['generator'] = validate()
    advance()


def advance():
    try:
        next(RUN['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=2)
    except StopIteration:
        RUN.clear()
    except Exception:
        RUN.clear()
        raise


def validate():
    original = op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state == 'stopped'
    assert original.ext.ShowControlExt._look_edit is None
    assert original.parent().op('running_look_qa') is None
    original_data = original.op('show_data').text
    qa = original.parent().copy(original, name='running_look_qa')
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    ext = qa.ext.ShowControlExt
    checks, debug, clock, error = {}, {}, [0.], None
    folder = ROOT/'build/envoy-validation'
    folder.mkdir(parents=True, exist_ok=True)

    def check(name, condition):
        checks[name] = bool(condition)
        assert condition, name

    def pixels(name='mapped1'):
        top = qa.op(name)
        top.cook(force=True)
        value = top.numpyArray(delayed=False)
        assert value is not None and np.isfinite(value).all() and not top.errors(), name
        return value.copy()

    def tick(delta=0.):
        clock[0] += delta
        ext.Tick()
        ext.UpdateMapping()
        assert not ext.engine.errors, str(ext.engine.errors)

    def until(predicate, delta=0.):
        for _ in range(600):
            tick(delta)
            yield
            if predicate():
                return
        raise AssertionError('Running-look preparation timed out')

    def load(cues):
        ext.engine.stop()
        if ext._look_edit is not None:
            ext.CancelLook()
        ext._replace_cues(cues)
        ext.engine.clock = lambda: clock[0]
        ext.engine._last = clock[0]
        ext.engine.go(0)

    try:
        yield  # Finish copy/extension initialization before operating the decks.
        qa.par.Renderwidth, qa.par.Renderheight = 320, 180
        qa.par.Masterblackout, qa.par.Audioenabled = False, False
        qa.par.Routingmode, qa.par.Testpattern = 'independent', False
        for track in (1, 2, 3):
            qa.par['Output%dwidth' % track], qa.par['Output%dheight' % track] = 320, 180
            qa.par['Output%dtrack' % track] = track
            qa.par['Output%dblackout' % track] = False
        fixture = qa.create(constantTOP, 'running_fixture')
        fixture.par.resolutionw, fixture.par.resolutionh = 320, 180
        fixture.par.colorr, fixture.par.colorg, fixture.par.colorb = .8, .1, .05
        fixture.cook(force=True)
        path = folder/'running-look-image.png'
        fixture.save(str(path))
        cue = dict(ext.model.new_cue(), name='Live test', source=str(path), duration=0, fade=0)
        load([cue])
        yield from until(lambda: cue['id'] in ext.engine.active)
        ext.SelectCue(1)
        initial, saved = pixels(), copy.deepcopy(ext.document)
        item = ext.tracks[1]
        deck, engine_id, started = item['deck'], id(ext.engine), item['started']
        child_ids = {node.id for node in qa.children}
        button = next(n for n in qa.children
                      if n.fetch('show_action', None, search=False) == 'Editrunninglook')
        preview = qa.op('look_preview_panel')
        check('edit_running_button_visible_and_enabled', qa.par.Editrunninglook.enable
              and button.par.label.eval() == 'Edit Running Cue'
              and button.width == 266 and button.height == 30
              and preview.par.y.eval() + preview.height < button.par.y.eval())
        qa.par.Editrunninglook.pulse()
        yield
        check('pulse_starts_running_draft', ext.IsRunningLookEdit() and ext.RunningLookDeck() == deck)
        check('editing_does_not_allocate_workflow', child_ids == {node.id for node in qa.children})
        check('offair_buttons_disabled', not qa.par.Looklive.enable and not qa.par.Showlooklive.enable
              and not qa.par.Savelookasnew.enable)
        targets = qa.op('look_editor_controls').module
        check('every_navigation_target_scoped_to_live_deck', all(
            targets.control_target(qa, name) == (deck if relative == '.' else deck.op(relative))
            for name, relative, _ in targets.TARGETS if relative == '.' or deck.op(relative) is not None))
        deck.par.Coloradjustmentenabled = True
        deck.op('color_adjustment').par.Invert = 1
        yield
        edited = pixels()
        check('slider_changes_live_projection', not np.allclose(initial, edited))
        check('projection_equals_live_editor', np.allclose(edited, pixels('look_preview'), atol=1/255))
        check('other_projector_tracks_unchanged', not pixels('mapped2')[:, :, :3].any()
              and not pixels('mapped3')[:, :, :3].any())
        check('unsaved_edit_does_not_mutate_cue', ext.document == saved)
        check('start_keeps_engine_and_playhead', id(ext.engine) == engine_id and item['started'] == started)
        qa.par.Masterblackout = True
        check('blackout_still_protects_output', not pixels()[:, :, :3].any())
        qa.par.Masterblackout = False
        qa.par.Output1brightness = .5
        check('mapping_grade_applies_during_edit', np.allclose(pixels()[:, :, :3], edited[:, :, :3]*.5, atol=2/255))
        qa.par.Output1brightness = 1
        ext.Pause()
        frozen, elapsed = pixels(), ext.engine.elapsed
        yield
        tick(2.)
        check('pause_preserves_edit_and_pixels', ext.IsRunningLookEdit() and ext.engine.elapsed == elapsed
              and np.allclose(frozen, pixels(), atol=1/255))
        ext.Resume()
        tick(1.)
        check('resume_keeps_same_deck', ext.tracks[1]['deck'] == deck and ext.engine.state == 'running')
        qa.par.Cancellook.pulse()
        yield
        check('cancel_restores_projection', np.allclose(initial, pixels(), atol=1/255))
        check('cancel_preserves_saved_document', ext.document == saved)
        check('cancel_does_not_destroy_or_restart', ext.tracks[1]['deck'] == deck and deck.valid
              and ext.engine.state == 'running' and item['started'] == started)

        ext.EditRunningLook()
        original_values = copy.deepcopy(ext._look_edit['original'])
        rack = deck.op('fx_rack')
        rack_time = rack.par.Manualtime.eval()
        rack.par.Slot1mix = .23
        workflow = deck.op('workflow').module
        order = list(workflow.current(deck))
        order[0], order[1] = order[1], order[0]
        workflow.apply_order(deck, order)
        branch = deck.op('image_composition/a_effects')
        branch.op('color_adjustment').par.Saturation = .17
        branch_rack = branch.op('fx_rack')
        branch_expression, branch_mode = branch_rack.par.Manualtime.expr, branch_rack.par.Manualtime.mode
        branch_rack.par.Slot1mix = .38
        yield
        ext.CancelLook()
        yield
        restored_values = ext._capture_look(deck)
        check('cancel_restores_rack_slots_workflow_and_branch_values', restored_values == original_values)
        check('cancel_keeps_rack_time', rack.par.Manualtime.eval() == rack_time)
        check('cancel_keeps_branch_clock_binding', branch_rack.par.Manualtime.expr == branch_expression
              and branch_rack.par.Manualtime.mode == branch_mode)

        qa.par.Editrunninglook.pulse()
        yield
        deck.par.Coloradjustmentenabled = True
        deck.op('color_adjustment').par.Invert = 1
        yield
        before_update, elapsed = pixels(), ext.engine.elapsed
        qa.par.Updatelook.pulse()
        yield
        check('update_does_not_change_pixels', np.allclose(before_update, pixels(), atol=1/255))
        check('update_keeps_transport', id(ext.engine) == engine_id and ext.engine.state == 'running'
              and ext.engine.elapsed == elapsed and ext.tracks[1] is item)
        check('update_commits_selected_values', ext.document['cues'][0]['look']['modules']['color_adjustment']['Invert'] == 1)
        check('update_finishes_without_destroying_deck', ext._look_edit is None and deck.valid)
        show_path = folder/'running-look-saved.json'
        qa.par.Showfile = str(show_path)
        ext.SaveShow()
        check('save_show_while_running', ext.engine.state == 'running'
              and json.loads(show_path.read_text(encoding='utf-8'))['cues'][0]['look'] == ext.document['cues'][0]['look'])

        for module, toggle in (('ink_dream_flow', 'Inkdreamenabled'),
                               ('ink_brush_flow', 'Inkbrushenabled'), ('ink_radial_flow', 'Inkradialenabled')):
            animation = {module: {'time': 5., 'render_time': 11.25, 'field_time': 9., 'running': True}}
            inkcue = dict(ext.model.new_cue(), duration=0, fade=0,
                          look={'toggles': {toggle: True}, 'modules': {module: {'Coverage': .7}}, 'animation': animation})
            load([inkcue])
            yield from until(lambda: inkcue['id'] in ext.engine.active)
            ext.SelectCue(1)
            item = ext.tracks[1]
            ink = item['deck'].op(module)
            tick(2.)
            qa.par.Editrunninglook.pulse()
            yield
            before_speed = pixels()
            ink.par.Animationspeed = .5
            yield
            check(module+'/speed_edit_keeps_frame', np.allclose(before_speed, pixels(), atol=1/255))
            ink.par.Particlefieldenabled = True
            ink.par.Fieldspeed, ink.par.Fielddensity = .6, .7
            ink.par.Particlecolumns = 64
            ink.par.Feedbackenabled, ink.par.Feedbackamount = True, 0.
            ink.par.Coverage = .45
            yield
            tick(1.)
            before = pixels()
            phase = ink.op('animation_clock').module.sample(ink)
            field_phase = ink.op('animation_clock').module.field_sample(ink)
            qa.par.Updatelook.pulse()
            yield
            check(module+'/update_keeps_rendered_frame', np.allclose(before, pixels(), atol=1/255))
            check(module+'/update_keeps_live_clocks', abs(ink.op('animation_clock').module.sample(ink)-phase)<1e-6
                  and abs(ink.op('animation_clock').module.field_sample(ink)-field_phase)<1e-6)
            stored = ext.document['cues'][0]['look']
            check(module+'/original_cue_start_phase_preserved', stored['animation'] == animation)
            values = stored['modules'][module]
            check(module+'/particle_feedback_speed_saved', values['Particlefieldenabled'] and values['Fieldspeed'] == .6
                  and values['Feedbackenabled'] and values['Animationspeed'] == .5 and values['Coverage'] == .45)
            tick(1.)
            check(module+'/animation_keeps_advancing', ink.op('animation_clock').module.sample(ink) > phase)
            ext.EditRunningLook()
            ink.par.Coverage = .2
            yield
            ext.CancelLook()
            yield
            check(module+'/cancel_restores_latest_committed_settings', abs(ink.par.Coverage.eval()-.45)<1e-6)

        # The editor must not inhibit automatic transitions or mutate the next
        # track owner when Update/Cancel is chosen after the old cue has ended.
        for behavior in ('continue', 'follow'):
            first = dict(cue, id=ext.model.new_cue()['id'], duration=2 if behavior == 'follow' else 0,
                         follow=behavior, postwait=1)
            second = dict(cue, id=ext.model.new_cue()['id'], name='Next', track=1, fade=.5)
            load([first, second])
            yield from until(lambda: first['id'] in ext.engine.active)
            ext.SelectCue(1)
            ext.EditRunningLook()
            ext.RunningLookDeck().par.Coloradjustmentenabled = True
            ext.RunningLookDeck().op('color_adjustment').par.Invert = 1
            yield
            yield from until(lambda: second['id'] in ext.engine.active, delta=.1)
            check(behavior+'/next_cue_starts_without_error', not ext.engine.errors and ext.tracks[1]['cue']['id'] == second['id'])
            check(behavior+'/ended_draft_retained', ext.IsRunningLookEdit() and ext._look_edit['deck'] is None
                  and not ext._look_edit.get('capture_error'))
            next_deck = ext.tracks[1]['deck']
            check(behavior+'/next_cue_keeps_own_look', not next_deck.par.Coloradjustmentenabled)
            if behavior == 'continue':
                ext.UpdateLook()
                check(behavior+'/ended_update_targets_original_only', ext.document['cues'][0]['look']['toggles']['Coloradjustmentenabled']
                      and ext.document['cues'][1]['look'] == second['look'] and not next_deck.par.Coloradjustmentenabled)
            else:
                ext.CancelLook()
                check(behavior+'/ended_cancel_never_touches_next_deck', not next_deck.par.Coloradjustmentenabled)

        video = folder/'show-av-fixture.mp4'
        check('video_fixture_available', video.is_file())
        avcue = dict(cue, id=ext.model.new_cue()['id'], source=str(video), movie_audio=True, loop=True)
        load([avcue])
        yield from until(lambda: avcue['id'] in ext.engine.active)
        ext.SelectCue(1)
        item = ext.tracks[1]
        movie, voice = item['movie'], ext.audio[avcue['id']]['reader']
        movie_id, voice_id = movie.id, voice.id
        ext.EditRunningLook()
        item['deck'].par.Coloradjustmentenabled = True
        item['deck'].op('color_adjustment').par.Invert = 1
        yield
        ext.UpdateLook()
        check('video_and_audio_readers_not_recreated', item['movie'].id == movie_id
              and ext.audio[avcue['id']]['reader'].id == voice_id)
        check('video_and_audio_stay_playing', movie.par.play and voice.par.play)
        ext.EditRunningLook()
        item['deck'].op('color_adjustment').par.Invert = .5
        yield
        ext.CancelLook()
        check('cancel_keeps_video_audio_playing', movie.id == movie_id and voice.id == voice_id
              and movie.par.play and voice.par.play)
        ext.EditRunningLook()
        item['deck'].op('color_adjustment').par.Invert = .25
        ext.Stopall()
        check('stop_all_retains_decidable_draft', ext._look_edit['deck'] is None and not ext._look_edit.get('capture_error'))
        ext.CancelLook()
        check('native_operator_errors_empty', not qa.errors(recurse=True))
        check('no_hardware_outputs_opened', not any(w.isOpen for w in qa.op('show_output_mode').module.windows(qa) if w))
        check('audio_output_stays_disarmed', not qa.par.Audioenabled)
        check('operator_show_unchanged', original.op('show_data').text == original_data)
    except Exception:
        error = traceback.format_exc()
        debug['status'] = qa.par.Status.eval()
    finally:
        ext.engine.stop()
        qa.destroy()
    result = dict(ok=error is None and all(checks.values()), checks=checks, error=error, debug=debug)
    (folder/'running-look.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if error:
        raise RuntimeError(error)
    print('RUNNING LOOK:', len(checks), 'native checks passed')
    return result
