"""Running panoramic Look Preview regression on a disposable Show Control copy.

Run as a Text DAT: start(root). It stops at READY for the visible resize/focus
smoke test. Call finish() afterward; no cue, audio, or audience output is armed
in the operator's real show. This validator never saves a TOE.
"""
import copy
import json
from pathlib import Path
import traceback

import numpy as np

RUN = {}


def start(root):
    if RUN:
        raise ValueError('Preview validation already active')
    original = op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state == 'stopped'
    assert original.ext.ShowControlExt._look_edit is None
    assert original.parent().op('preview_panorama_qa') is None
    RUN.update(root=Path(root), original=original,
               before=original.op('show_data').text,
               main_look=original.ext.ShowControlExt._capture_look(original.parent()),
               checks={}, error=None)
    RUN['generator'] = prepare()
    advance()


def check(name, value):
    RUN['checks'][name] = bool(value)
    assert value, name


def advance():
    try:
        next(RUN['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=2)
    except StopIteration:
        RUN.pop('generator', None)
    except Exception:
        RUN['error'] = traceback.format_exc()
        finish()


def pixels(top):
    top.cook(force=True)
    value = top.numpyArray(delayed=False)
    assert value is not None and np.isfinite(value).all() and not top.errors()
    return value.copy()


def prepare():
    original = RUN['original']
    qa = original.parent().copy(original, name='preview_panorama_qa')
    RUN['qa'] = qa
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    ext = qa.ext.ShowControlExt
    yield
    qa.par.Audioenabled, qa.par.Masterblackout = False, True
    qa.par.Renderwidth, qa.par.Renderheight = 1920, 1080
    qa.par.Routingmode, qa.par.Panoramaoverlap = 'panoramic', 0
    qa.par.Sharedtrack = 1
    look = {'toggles': {name: False for name in RUN['main_look']['toggles']},
            'modules': {'motion_studio': {'Speed': .1}}}
    look['toggles']['Motionenabled'] = True
    cue = dict(ext.model.new_cue(), name='Panoramic preview resize QA',
               duration=0, fade=0, look=look)
    ext._replace_cues([cue])
    ext.engine.go(0)
    for _ in range(600):
        ext.Tick()
        yield
        if cue['id'] in ext.engine.active:
            break
    check('cue_started', cue['id'] in ext.engine.active and not ext.engine.errors)
    ext.SelectCue(1)
    ext.EditRunningLook()
    item = ext.tracks[1]
    deck = item['deck']
    RUN.update(deck=deck, item=item, started=item['started'], document=copy.deepcopy(ext.document))
    check('live_edit_owns_running_deck', ext.RunningLookDeck() == deck)
    output = deck.op('out1_image')
    preview, display = qa.op('look_preview'), qa.op('look_preview_display')
    check('wide_cue_render', pixels(output).shape == (1080, 5760, 4))
    check('wide_preview_render', pixels(display).shape == (1080, 5760, 4))
    check('preview_selects_running_track', preview.par.top.eval() ==
          qa.op('track{}_source{}'.format(item['track'], item['side'])))
    window = qa.op('look_preview_window')
    check('pinned_window', bool(window.par.alwaysontop))
    check('fitted_inline_preview', qa.op('look_preview_panel').par.topfill.eval() == 'best')
    check('fitted_popup_preview', display.par.fillmode.eval() == 'best')

    ext.Pause()
    yield
    baseline = pixels(preview)
    elapsed = ext.engine.elapsed
    for width, height in ((960, 540), (640, 640), (1440, 270)):
        window.par.winw, window.par.winh = width, height
        yield
        ext.Tick()
        suffix = '{}x{}'.format(width, height)
        check('pixels_unchanged/' + suffix, np.array_equal(baseline, pixels(display)))
        RUN.setdefault('dimensions', {})[suffix] = dict(
            deck=[int(deck.par.Customwidth), int(deck.par.Customheight)],
            display=[display.width, display.height], output=[output.width, output.height])
        # Pause intentionally disables deck cooking and locks its track source;
        # internal TOP allocation sizes are not meaningful until Resume.
        check('resolution_unchanged/' + suffix,
              (int(deck.par.Customwidth), int(deck.par.Customheight)) == (5760, 1080)
              and pixels(display).shape == (1080, 5760, 4))
        check('deck_not_restarted/' + suffix, ext.tracks[1] is item and item['started'] == RUN['started'])
        check('playhead_unchanged/' + suffix, ext.engine.elapsed == elapsed)
    window.par.winw, window.par.winh = 960, 540
    ext.Resume()
    qa.op('show_tick').par.active = True
    RUN['ready_elapsed'] = ext.engine.elapsed
    RUN['ready'] = True
    check('no_cue_errors', not ext.engine.errors)
    check('no_native_errors', not qa.errors(recurse=True))
    print('PANORAMIC PREVIEW READY: 5760x1080 cue running; open QA Look Preview for resize/focus smoke test, then finish().')


def finish():
    if not RUN:
        raise ValueError('No preview validation to finish')
    original = RUN['original']
    qa = RUN.get('qa')
    try:
        if RUN.get('ready'):
            ext = qa.ext.ShowControlExt
            check('running_after_window_smoke_test', ext.engine.state == 'running')
            check('same_deck_after_window_smoke_test', ext.RunningLookDeck() == RUN['deck']
                  and ext.tracks[1] is RUN['item'] and RUN['item']['started'] == RUN['started'])
            check('playback_continued', ext.engine.elapsed > RUN['ready_elapsed'])
            check('cue_values_preserved', ext.document == RUN['document'])
            check('render_still_panoramic', pixels(qa.op('look_preview_display')).shape == (1080, 5760, 4))
            check('no_cue_errors_after_resize', not ext.engine.errors)
            check('native_errors_empty_after_resize', not qa.errors(recurse=True))
        check('real_show_document_unchanged', original.op('show_data').text == RUN['before'])
        check('main_workflow_unchanged', original.ext.ShowControlExt._capture_look(original.parent()) == RUN['main_look'])
        check('real_show_stopped', original.ext.ShowControlExt.engine.state == 'stopped')
        for show in (original, qa):
            if show is not None:
                check(show.name + '/no_audience_windows', not any(w.isOpen for w in
                    show.op('show_output_mode').module.windows(show) if w is not None))
                check(show.name + '/audio_off', not show.par.Audioenabled)
    except Exception:
        RUN['error'] = (RUN.get('error') or '') + traceback.format_exc()
    finally:
        if qa is not None:
            qa.op('look_preview_window').par.winclose.pulse()
            qa.ext.ShowControlExt.engine.stop()
            qa.destroy()
    report = dict(ok=not RUN['error'] and bool(RUN.get('ready')) and all(RUN['checks'].values()),
                  checks=RUN['checks'], error=RUN['error'], dimensions=RUN.get('dimensions', {}),
                  hardware_outputs_tested=False)
    path = RUN['root'] / 'build/envoy-validation/preview-panorama.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PANORAMIC PREVIEW:', report['ok'], len(report['checks']), report['error'])
    RUN.clear()
