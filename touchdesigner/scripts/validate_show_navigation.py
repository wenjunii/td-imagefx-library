"""Off-air native pixel/transport tests. Does not save shows or open outputs."""
import copy
import json
from pathlib import Path
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def validate(write_report=True):
    original = op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state == 'stopped'
    assert original.ext.ShowControlExt._look_edit is None
    assert original.parent().op('show_navigation_qa') is None
    document = original.op('show_data').text
    qa = original.parent().copy(original, name='show_navigation_qa')
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    ext = qa.ext.ShowControlExt
    checks, error = {}, None
    clock = [0.0]
    report_dir = ROOT/'build/envoy-validation'
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

    try:
        builder = ROOT/'touchdesigner/scripts/build_show_control.py'
        scope = dict(globals(), __file__=str(builder))
        exec(compile(builder.read_text(encoding='utf-8'), str(builder), 'exec'), scope)
        install_navigation_controls = scope['install_navigation_controls']
        before_buttons = {b.name: b.id for b in qa.findChildren(depth=1, name='button_*')}
        install_navigation_controls(qa)
        install_navigation_controls(qa)
        after_buttons = {b.name: b.id for b in qa.findChildren(depth=1, name='button_*')}
        check('toolbar_install_is_idempotent', before_buttons == after_buttons and len(after_buttons) >= 16)
        check('toolbar_has_one_callback_per_button', all(
            len(qa.op(name).findChildren(depth=1, name='clicked*')) == 1 for name in after_buttons))
        qa.par.Renderwidth, qa.par.Renderheight = 320, 180
        qa.par.Masterblackout, qa.par.Audioenabled = False, False
        qa.par.Routingmode, qa.par.Testpattern = 'independent', False
        for track in (1, 2, 3):
            qa.par['Output%dwidth' % track], qa.par['Output%dheight' % track] = 320, 180
            qa.par['Output%dtrack' % track] = track
            qa.par['Output%dblackout' % track] = False
        fixture = qa.create(constantTOP, 'navigation_fixture')
        fixture.par.resolutionw, fixture.par.resolutionh = 320, 180
        paths = []
        for name, rgb in (('red', (.8, .1, .05)), ('blue', (.05, .1, .8))):
            fixture.par.colorr, fixture.par.colorg, fixture.par.colorb = rgb
            fixture.cook(force=True)
            path = report_dir/('navigation-' + name + '.png')
            fixture.save(str(path))
            paths.append(str(path))
        cues = [dict(ext.model.new_cue(), name='Red', source=paths[0], duration=0, fade=0),
                dict(ext.model.new_cue(), name='Blue', source=paths[1], duration=0, fade=0),
                dict(ext.model.new_cue(), name='Blackout', kind='blackout', duration=0, fade=0)]
        ext._replace_cues(cues)
        ext.engine.clock = lambda: clock[0]
        ext.engine._last = 0
        ext.engine.go(0); step(0)
        red = pixels('mapped1')
        check('red_visual_visible', red[:, :, 0].mean() > .3)
        ext.engine.go(1); step(1)
        blue = pixels('mapped1')
        check('second_visual_is_different', np.max(np.abs(red-blue)) > .2)
        ext.GoBack()
        check('go_back_keeps_on_air_pixels_during_preload', np.allclose(blue, pixels('mapped1')))
        step(2)
        check('go_back_restores_previous_cue_pixels', np.allclose(red, pixels('mapped1'), atol=1/255))
        check('go_back_did_not_stop_show_clock', ext.engine.elapsed == 2)
        ext.SelectCue(2); ext.Go(); step(3)
        check('forward_go_after_back', np.allclose(blue, pixels('mapped1'), atol=1/255))
        ext.SelectCue(3); ext.Go(); step(4)
        check('blackout_cue_makes_mapped_video_black', np.max(pixels('mapped1')[:, :, :3]) == 0)
        check('blackout_cue_holds_all_track_levels', all(float(qa.par['Track%dlevel' % i]) == 0 for i in (1, 2, 3)))
        ext.GoBack()
        check('held_visual_replay_keeps_black_during_preload', np.max(pixels('mapped1')[:, :, :3]) == 0)
        step(5)
        check('go_back_from_blackout_replays_held_visual', np.allclose(blue, pixels('mapped1'), atol=1/255))
        check('visual_releases_only_its_track', [float(qa.par['Track%dlevel' % i]) for i in (1, 2, 3)] == [1, 0, 0])
        check('replay_does_not_modify_cue_ids', [c['id'] for c in ext.document['cues']] == [c['id'] for c in cues])
        ext.engine.stop()
        ext.SelectCue(1)
        # Synchronous callback dispatch; actual pulse delivery is frame-driven.
        qa.op('show_parameters').module.onPulse(qa.par.Addblackout)
        check('add_blackout_pulse_inserts_after_selected', ext.document['cues'][1]['kind'] == 'blackout' and len(ext.document['cues']) == 4)
        qa.par.Blackoutscope, qa.par.Track, qa.par.Fade = 'track', 1, 2
        qa.par.Easing = 'linear'
        qa.op('show_parameters').module.onPulse(qa.par.Applycue)
        inserted = ext.document['cues'][1]
        check('blackout_editor_values_apply', inserted['blackout_scope'] == 'track' and inserted['fade'] == 2)
        serialized = json.loads(qa.op('show_data').text)
        check('blackout_show_document_roundtrip', ext.model.validate_show(serialized) == ext.document)
        ext.engine.clock = lambda: clock[0]
        ext.engine._last = clock[0]
        ext.engine.go(0); step(5)
        before = pixels('mapped1')
        ext.engine.go(1); step(5); step(6)
        halfway = pixels('mapped1')
        check('blackout_fade_affects_rendered_pixels', np.allclose(halfway[:, :, :3], before[:, :, :3]*.5, atol=2/255))
        check('selected_track_scope_keeps_other_levels', [float(qa.par['Track%dlevel' % i]) for i in (2, 3)] == [1, 1])
        ext.Pause(); step(50)
        paused_pixels = pixels('mapped1')
        check('pause_holds_blackout_fade_pixels', np.allclose(halfway, paused_pixels, atol=1/255))
        ext.Resume(); step(51)
        check('resume_finishes_blackout', np.max(pixels('mapped1')[:, :, :3]) == 0)
        check('audio_and_master_safety_unchanged', not qa.par.Audioenabled and not qa.par.Masterblackout)
        check('blackout_did_not_touch_audio_voices', not ext.audio)
        check('main_show_document_unchanged', original.op('show_data').text == document)
        check('native_operator_errors_empty', not qa.errors(recurse=True))
    except Exception:
        error = traceback.format_exc()
    finally:
        ext.engine.stop()
        qa.destroy()
    result = dict(ok=error is None and all(checks.values()), checks=checks, error=error)
    if write_report:
        (report_dir/'show-navigation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if error:
        raise RuntimeError(error)
    print('SHOW NAVIGATION:', len(checks), 'native checks passed')
    return result
