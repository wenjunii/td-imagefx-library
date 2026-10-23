"""Real-frame Continue/Follow regression, isolated from the operator's show."""
import json
import time
import traceback
from pathlib import Path

import numpy as np

STATE = {}


def check(name, condition):
    STATE['checks'][name] = bool(condition)
    assert condition, name


def pixels(track=1):
    top = STATE['qa'].op('track%d' % track)
    top.cook(force=True)
    data = top.numpyArray(delayed=False)
    assert data is not None and np.isfinite(data).all() and not top.errors()
    return data.copy()


def tick(delta=.1, allow_errors=False):
    STATE['clock'] += delta
    STATE['ext'].Tick()
    if not allow_errors:
        assert not STATE['ext'].engine.errors, str(STATE['ext'].engine.errors)


def until(predicate, *, delta=.1, allow_errors=False):
    for _ in range(600):
        tick(delta, allow_errors)
        yield
        if predicate():
            return
    raise AssertionError('Continue test condition timed out')


def setup(cues):
    ext = STATE['ext']
    ext.engine.stop()
    ext._replace_cues(cues)
    STATE['clock'] = 0.
    ext.engine.clock = lambda: STATE['clock']
    ext.engine._last = 0.
    ext.engine.go(0)


def cases():
    qa, ext = STATE['qa'], STATE['ext']
    fixture = qa.create(constantTOP, 'continue_fixture')
    fixture.par.resolutionw, fixture.par.resolutionh = 320, 180
    paths = []
    for name, rgb in (('red', (.8, 0, 0)), ('green', (0, .8, 0)), ('blue', (0, 0, .8))):
        fixture.par.colorr, fixture.par.colorg, fixture.par.colorb = rgb
        fixture.cook(force=True)
        path = STATE['folder']/('continue-' + name + '.png')
        fixture.save(str(path))
        paths.append(str(path))
    cues = [dict(ext.model.new_cue(), name=name, source=path, duration=0,
                 fade=1, easing='linear', follow='continue' if i < 2 else 'manual')
            for i, (name, path) in enumerate(zip(('Red', 'Green', 'Blue'), paths))]
    setup(cues)
    yield from until(lambda: cues[1]['id'] in ext.engine._waiting_preparation)
    check('next_cue_is_wait_not_error', ext.CueLabel(1).endswith('| WAIT') and not ext.engine.errors)
    first = ext.tracks[1]
    check('busy_request_keeps_first_deck', first['cue']['id'] == cues[0]['id'])
    check('first_image_still_visible_while_waiting', pixels()[:, :, 0].mean() > .01)
    check('next_deck_not_partially_applied', cues[1]['id'] not in ext.prepared)
    ext.Pause()
    before, elapsed = pixels(), ext.engine.elapsed
    for _ in range(3):
        tick(100)
        yield
    check('pause_holds_waiting_cue', cues[1]['id'] in ext.engine._waiting_preparation and ext.engine.elapsed == elapsed)
    check('pause_holds_rendered_pixels', np.allclose(before, pixels(), atol=1/255))
    ext.Resume()
    yield from until(lambda: cues[1]['id'] in ext.engine.active)
    starts = [ext.engine.active[cue['id']][1] for cue in cues[:2]]
    check('next_starts_after_first_crossfade', starts[1] - starts[0] >= cues[0]['fade'])
    yield from until(lambda: cues[2]['id'] in ext.engine._waiting_preparation)
    check('third_continue_cue_also_waits', ext.CueLabel(2).endswith('| WAIT'))
    yield from until(lambda: ext.engine.elapsed - starts[1] >= .4)
    midway = pixels()
    check('second_crossfade_has_both_images', midway[:, :, 0].mean() > .05 and midway[:, :, 1].mean() > .05)
    yield from until(lambda: cues[2]['id'] in ext.engine.active)
    starts.append(ext.engine.active[cues[2]['id']][1])
    check('third_starts_after_second_crossfade', starts[2] - starts[1] >= cues[1]['fade'])
    yield from until(lambda: not ext.tracks[1]['fading'])
    final = pixels()
    check('final_cue_renders_its_own_image', final[:, :, 2].mean() > .7 and np.max(final[:, :, :2]) < .01)
    check('continue_chain_has_no_errors_or_waiters', not ext.engine.errors and not ext.engine.pending and not ext.engine._waiting_preparation)
    check('continue_does_not_change_saved_values', ext.document['cues'] == ext.model.validate_show(dict(kind=ext.model.SHOW_KIND, schema_version=1, cues=cues))['cues'])
    STATE['start_times'] = starts

    setup(cues[:2])
    yield from until(lambda: cues[1]['id'] in ext.engine._waiting_preparation)
    ext.engine.stop_cue(1)
    for _ in range(20):
        tick()
        yield
    check('stop_selected_cancels_waiting_cue', cues[1]['id'] not in ext.engine.active and not ext.engine.pending and not ext.engine._waiting_preparation)
    check('stop_selected_does_not_clear_current_image', pixels()[:, :, 0].mean() > .7)

    setup(cues[:2])
    yield from until(lambda: cues[1]['id'] in ext.engine._waiting_preparation)
    ext.engine.stop()
    for _ in range(3):
        tick()
        yield
    check('stop_all_clears_queue', ext.engine.state == 'stopped' and not ext.engine.pending and not ext.engine._waiting_preparation)
    check('stop_all_output_is_black', np.max(pixels()[:, :, :3]) == 0)

    independent = [dict(cues[0], fade=10), dict(cues[1], track=2, follow='manual')]
    setup(independent)
    yield from until(lambda: independent[1]['id'] in ext.engine.active)
    check('other_track_starts_without_waiting_for_first_fade', ext.engine.active[independent[1]['id']][1] - ext.engine.active[independent[0]['id']][1] < 10 and ext.tracks[1]['fading'])
    check('other_track_keeps_first_track_running', set(ext.tracks) == {1, 2})
    yield from until(lambda: all(not item['fading'] for item in ext.tracks.values()))
    check('independent_projector_pixels_are_correct', pixels(1)[:, :, 0].mean() > .7 and pixels(2)[:, :, 1].mean() > .7)

    follow = [dict(cues[0], duration=1, fade=.2, follow='follow', postwait=.5),
              dict(cues[1], fade=.2, prewait=.5, follow='manual')]
    setup(follow)
    yield from until(lambda: follow[0]['id'] in ext.engine.active)
    started = ext.engine.active[follow[0]['id']][1]
    ext.Pause()
    for _ in range(3):
        tick(100)
        yield
    check('follow_pause_preserves_duration', follow[0]['id'] in ext.engine.active and not ext.engine.follows and follow[1]['id'] not in ext.engine.triggered)
    ext.Resume()
    yield from until(lambda: bool(ext.engine.follows))
    due = ext.engine.follows[0][0]
    check('follow_scheduled_only_after_duration', ext.engine.elapsed >= started + 1 and follow[1]['id'] not in ext.engine.pending)
    check('follow_postwait_is_after_completion', abs(due - ext.engine.elapsed - .5) < .001)
    yield from until(lambda: follow[1]['id'] in ext.engine.pending)
    next_due = ext.engine.pending[follow[1]['id']][1]
    check('follow_respects_next_prewait', ext.engine.elapsed >= due and next_due >= due + .5 - .001)
    yield from until(lambda: follow[1]['id'] in ext.engine.active)
    check('follow_starts_after_all_waits', ext.engine.active[follow[1]['id']][1] >= started + 2 - .001)
    yield from until(lambda: not ext.tracks[1]['fading'])
    check('follow_renders_next_image', pixels()[:, :, 1].mean() > .7 and np.max(pixels()[:, :, 0]) < .01)

    # A timed Wait cue can Follow into a track that another cue still owns.
    timed = dict(ext.model.new_cue(), kind='wait', track=2, duration=.5, follow='follow')
    blocked_follow = [dict(cues[0], fade=3, follow='manual'), timed,
                      dict(cues[1], follow='manual')]
    setup(blocked_follow)
    yield from until(lambda: blocked_follow[0]['id'] in ext.engine.active)
    ext.engine.go(1)
    yield from until(lambda: blocked_follow[2]['id'] in ext.engine._waiting_preparation)
    check('follow_busy_track_is_wait_not_error', ext.CueLabel(2).endswith('| WAIT') and not ext.engine.errors)
    yield from until(lambda: blocked_follow[2]['id'] in ext.engine.active)
    check('follow_busy_track_recovers', not ext.engine.errors and not ext.engine._waiting_preparation)
    yield from until(lambda: not ext.tracks[1]['fading'])
    check('follow_after_busy_track_renders_next_image', pixels()[:, :, 1].mean() > .7)

    setup(follow)
    yield from until(lambda: follow[0]['id'] in ext.engine.active)
    ext.engine.stop_cue(0)
    for _ in range(30):
        tick()
        yield
    check('stopping_parent_cancels_follow', not ext.engine.follows and follow[1]['id'] not in ext.engine.triggered)

    missing = dict(cues[1], source=str(STATE['folder']/'continue-intentionally-missing.png'), follow='manual')
    assert not Path(missing['source']).exists()
    setup([cues[0], missing])
    yield from until(lambda: missing['id'] in ext.engine.errors, allow_errors=True)
    check('genuine_missing_media_still_shows_error', 'Missing media' in ext.engine.errors[missing['id']] and ext.CueLabel(1).endswith('| ERROR'))
    check('genuine_error_is_not_retried_as_busy', missing['id'] not in ext.engine.pending and missing['id'] not in ext.engine._waiting_preparation)
    check('main_show_document_unchanged', STATE['original'].op('show_data').text == STATE['document'])
    check('native_diagnostics_empty', not qa.errors(recurse=True))
    check('audio_never_armed', not qa.par.Audioenabled)


def start():
    original = op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state == 'stopped'
    assert original.ext.ShowControlExt._look_edit is None
    assert not STATE.get('running')
    assert original.parent().op('show_continue_qa') is None
    qa = original.parent().copy(original, name='show_continue_qa')
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    qa.par.Audioenabled, qa.par.Masterblackout = False, False
    qa.par.Renderwidth, qa.par.Renderheight = 320, 180
    folder = Path(qa.par.Libraryroot.eval())/'build/envoy-validation'
    folder.mkdir(parents=True, exist_ok=True)
    STATE.clear()
    STATE.update(running=True, original=original, document=original.op('show_data').text,
                 qa=qa, ext=qa.ext.ShowControlExt, folder=folder, clock=0., checks={},
                 started=time.monotonic(), steps=cases())
    run('op({!r}).module.advance()'.format(me.path), delayFrames=2)


def advance():
    if not STATE.get('running'):
        return
    try:
        assert time.monotonic()-STATE['started'] < 180, 'Continue QA timeout'
        next(STATE['steps'])
        run('op({!r}).module.advance()'.format(me.path), delayFrames=1)
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


def finish(error=None):
    STATE['running'] = False
    STATE['ext'].engine.stop()
    STATE['qa'].destroy()
    report = dict(ok=error is None and bool(STATE['checks']) and all(STATE['checks'].values()),
                  checks=STATE['checks'], error=error, start_times=STATE.get('start_times'),
                  physical_outputs_tested=False, audio_auditioned=False)
    (STATE['folder']/'show-continue.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('SHOW CONTINUE QA:', json.dumps(report))
