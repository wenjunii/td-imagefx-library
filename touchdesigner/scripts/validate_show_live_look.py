"""Native off-air pixel checks for live audition, cue notes and blackout boundaries."""
import copy
import json
from pathlib import Path
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = {}


def start():
    if RUN.get('generator') is not None:
        raise ValueError('Validation is already running')
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
    assert original.parent().op('show_live_qa') is None
    document = original.op('show_data').text
    qa = original.parent().copy(original, name='show_live_qa')
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    ext = qa.ext.ShowControlExt
    checks, error, clock, debug = {}, None, [0.0], {}
    report_dir = ROOT / 'build/envoy-validation'
    report_dir.mkdir(parents=True, exist_ok=True)

    def check(name, condition):
        checks[name] = bool(condition)
        assert condition, name

    def pixels(name):
        top = qa.op(name)
        top.cook(force=True)
        result = top.numpyArray(delayed=False)
        assert result is not None and np.isfinite(result).all() and not top.errors(), name
        return result.copy()

    def step(now):
        for _ in range(500):
            loading = [item for item in ext.prepared.values() if item.get('loading')]
            if not loading:
                break
            for item in loading:
                if 'warm_frame' in item:
                    item['warm_frame'] = absTime.frame - 1
            ext._service_preloads()
        assert not any(item.get('loading') for item in ext.prepared.values()), 'Preparation timeout'
        clock[0] = now
        ext.engine.tick()
        ext.UpdateMapping()
        assert not ext.engine.errors, str(ext.engine.errors)

    def load(cues):
        ext.engine.stop()
        ext._replace_cues(cues)
        ext.engine.clock = lambda: clock[0]
        ext.engine._last = clock[0]

    try:
        path = ROOT / 'touchdesigner/scripts/show_live_look.py'
        scope = dict(globals(), __file__=str(path))
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), scope)
        ids = {node.name: node.id for node in qa.children}
        scope['install'](qa); scope['install'](qa)
        check('idempotent_installer_preserves_nodes', ids == {node.name: node.id for node in qa.children})
        check('startup_live_preview_is_off', not qa.par.Looklive)
        qa.par.Renderwidth, qa.par.Renderheight = 320, 180
        qa.par.Masterblackout, qa.par.Audioenabled = False, False
        qa.par.Routingmode, qa.par.Testpattern = 'independent', False
        for track in (1, 2, 3):
            qa.par['Output%dwidth' % track], qa.par['Output%dheight' % track] = 320, 180
            qa.par['Output%dtrack' % track] = track
            qa.par['Output%dblackout' % track] = False
        fixture = qa.create(constantTOP, 'live_fixture')
        paths = []
        for name, rgb in (('red', (.8, .1, .05)), ('blue', (.05, .1, .8))):
            fixture.par.colorr, fixture.par.colorg, fixture.par.colorb = rgb
            fixture.cook(force=True)
            path = report_dir / ('live-' + name + '.png')
            fixture.save(str(path)); paths.append(str(path))
        red = dict(ext.model.new_cue(), name='Red', source=paths[0], duration=0, fade=2, easing='linear')
        black = dict(ext.model.new_cue(), name='Blackout', kind='blackout', duration=0, fade=0)
        blue = dict(ext.model.new_cue(), name='Blue', source=paths[1], duration=0, fade=2, easing='linear')
        load([red, black, blue])
        ext.engine.go(0); step(0); step(2)
        red_pixels = pixels('mapped1')
        ext.engine.go(1); step(2)
        check('blackout_is_black', not pixels('mapped1')[:, :, :3].any())
        ext.engine.go(2); step(3)
        check('go_after_blackout_starts_black', not pixels('mapped1')[:, :, :3].any())
        check('go_retires_previous_deck', ext.tracks[1]['old'] is None)
        step(4); halfway = pixels('mapped1')
        step(5); blue_pixels = pixels('mapped1')
        check('go_fades_only_target_cue', np.allclose(halfway[:, :, :3], blue_pixels[:, :, :3] * .5, atol=2/255))
        ext.GoBack(); step(5)
        check('back_to_blackout_is_black', not pixels('mapped1')[:, :, :3].any())
        ext.GoBack(); step(6)
        check('back_after_blackout_starts_black', not pixels('mapped1')[:, :, :3].any())
        step(7); halfway = pixels('mapped1')
        check('back_fades_only_target_cue', np.allclose(halfway[:, :, :3], red_pixels[:, :, :3] * .5, atol=2/255))
        step(8)
        check('back_replays_target_pixels', np.allclose(pixels('mapped1'), red_pixels, atol=1/255))

        # All three ink clocks must replay their own saved phase, not the old
        # deck's end or elapsed show time. Exercise both GO and Go Back.
        for module, toggle in (('ink_dream_flow', 'Inkdreamenabled'),
                               ('ink_brush_flow', 'Inkbrushenabled'), ('ink_radial_flow', 'Inkradialenabled')):
            look = {'toggles': {toggle: True}, 'modules': {module: {'Coverage': .7, 'Animationspeed': .6}},
                    'animation': {module: {'time': 5., 'render_time': 11.25, 'running': True}}}
            ink = dict(ext.model.new_cue(), fade=0, duration=0, look=look)
            load([ink, black])
            ext.engine.go(0); step(clock[0]); first = pixels('mapped1')
            step(clock[0] + 3)
            check(module + '/animation_runs', not np.allclose(first, pixels('mapped1')))
            ext.engine.go(1); step(clock[0]); ext.GoBack(); step(clock[0])
            check(module + '/back_restarts_own_phase', np.allclose(first, pixels('mapped1'), atol=1/255))
            ext.engine.go(1, replay=True); step(clock[0]); ext.engine.go(0, replay=True); step(clock[0])
            check(module + '/go_restarts_own_phase', np.allclose(first, pixels('mapped1'), atol=1/255))

        load([blue]); ext.SelectCue(1); ext.RecallLook()
        draft = ext._look_edit['deck']
        # Real GUI edits happen across frames. Allow TD's binding/cook and
        # asynchronous file-decode queues to complete, not an artificial
        # same-frame forced shader refresh that could hide a routing bug.
        yield
        for _ in range(500):
            if ext._media_ready({'deck': draft, 'movie': draft.op('media')}):
                break
            yield
        check('draft_media_decoded', ext._media_ready({'deck': draft, 'movie': draft.op('media')}))
        snapshot = copy.deepcopy(ext.document)
        check('recall_stays_off_air', not pixels('mapped1')[:, :, :3].any())
        qa.par.Looklivetrack = 2
        ext.ShowLiveLook()
        debug['live'] = dict(ext_current=ext is qa.ext.ShowControlExt,
            enabled=qa.par.Looklive.eval(), target=qa.par.Looklivetrack.eval(),
            resolved=ext.ProjectionSource(2), source=str(qa.op('output_source2').par.top.eval()),
            mapped_means=[pixels('mapped%d' % i)[:, :, :3].mean(axis=(0,1)).tolist() for i in (1,2,3)],
            draft_mean=pixels('look_preview')[:, :, :3].mean(axis=(0,1)).tolist(),
            expected_mean=blue_pixels[:, :, :3].mean(axis=(0,1)).tolist())
        debug['live'].update(source_index=draft.op('source_image').par.index.eval(),
            source_inputs=[n.path for n in draft.op('source_image').inputs],
            movie_file=draft.op('media').par.file.eval(), movie_open=draft.op('media').isOpen)
        check('live_audition_is_targeted', np.allclose(pixels('mapped2'), blue_pixels, atol=1/255)
              and not pixels('mapped1')[:, :, :3].any() and not pixels('mapped3')[:, :, :3].any())
        draft.par.Coloradjustmentenabled = True
        draft.op('color_adjustment').par.Invert = 1
        yield
        edited = pixels('mapped2')
        debug['edit'] = dict(toggle=draft.par.Coloradjustmentenabled.eval(),
            enabled=draft.op('color_adjustment').par.Enabled.eval(),
            invert=draft.op('color_adjustment').par.Invert.eval(),
            module_cooks=draft.op('color_adjustment').allowCooking,
            draft_mean=pixels('look_preview')[:, :, :3].mean(axis=(0,1)).tolist(),
            mapped_mean=edited[:, :, :3].mean(axis=(0,1)).tolist())
        check('effect_slider_reaches_projection', not np.allclose(edited, blue_pixels))
        check('live_pixels_match_editor', np.allclose(edited, pixels('look_preview'), atol=1/255))
        check('live_audition_does_not_commit', ext.document == snapshot)
        qa.par.Masterblackout = True
        check('master_blackout_still_applies', not pixels('mapped2')[:, :, :3].any())
        qa.par.Masterblackout, qa.par.Output2blackout = False, True
        check('output_blackout_still_applies', not pixels('mapped2')[:, :, :3].any())
        qa.par.Output2blackout, qa.par.Output2brightness = False, .5
        check('output_grading_still_applies', np.allclose(pixels('mapped2')[:, :, :3], edited[:, :, :3] * .5, atol=2/255))
        qa.par.Output2brightness = 1
        qa.par.Routingmode, qa.par.Looklivetrack = 'identical', 1
        check('identical_routing_all_projectors', all(np.allclose(pixels('mapped%d' % i), edited, atol=1/255) for i in (1, 2, 3)))
        ext.StopLiveLook()
        check('stop_live_keeps_draft_but_blacks_outputs', ext._look_edit is not None and not pixels('mapped1')[:, :, :3].any())
        qa.par.Cuenotes = 'Stand by LX 12\n第二行 / hold for dancer'
        check('notes_alias_is_two_way', qa.par.Notes.eval() == qa.par.Cuenotes.eval())
        engine_id = id(ext.engine)
        ext.SaveCueNotes()
        check('notes_save_keeps_engine_and_draft', id(ext.engine) == engine_id and ext._look_edit['deck'] == draft)
        check('notes_persist_without_look_commit', ext.document['cues'][0]['notes'] == qa.par.Cuenotes.eval()
              and ext.document['cues'][0]['look'] == snapshot['cues'][0]['look'])
        check('notes_saved_json_roundtrip', ext.model.validate_show(json.loads(qa.op('show_data').text)) == ext.document)
        ext.ShowLiveLook(); ext.UpdateLook()
        check('update_disarms_live_and_commits_look', not qa.par.Looklive and ext._look_edit is None
              and ext.document['cues'][0]['look']['modules']['color_adjustment']['Invert'] == 1)
        check('update_preserves_notes', ext.document['cues'][0]['notes'] == 'Stand by LX 12\n第二行 / hold for dancer')
        ext.RecallLook(); ext.ShowLiveLook(); ext.CancelLook()
        check('cancel_disarms_live', not qa.par.Looklive and ext._look_edit is None)
        ext.RecallLook(); ext.ShowLiveLook(); ext.Stopall()
        check('stop_all_disarms_live_but_keeps_draft', not qa.par.Looklive and ext._look_edit is not None)
        ext.CancelLook()
        ext.engine.go(0); step(clock[0]); qa.par.Cuenotes = 'Notes during playback'
        engine_id, elapsed = id(ext.engine), ext.engine.elapsed
        ext.SaveCueNotes()
        check('notes_can_save_during_playback', id(ext.engine) == engine_id and ext.engine.state == 'running' and ext.engine.elapsed == elapsed)
        check('no_hardware_outputs_opened', not any(w.isOpen for w in qa.op('show_output_mode').module.windows(qa) if w))
        check('audio_stays_off', not qa.par.Audioenabled)
        check('original_show_unchanged', original.op('show_data').text == document)
        check('native_operator_errors_empty', not qa.errors(recurse=True))
    except Exception:
        error = traceback.format_exc()
    finally:
        ext.engine.stop()
        qa.destroy()
    result = dict(ok=error is None and all(checks.values()), checks=checks, error=error, debug=debug)
    (report_dir / 'show-live-look.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if error:
        raise RuntimeError(error)
    print('SHOW LIVE LOOK:', len(checks), 'native checks passed')
    return result
