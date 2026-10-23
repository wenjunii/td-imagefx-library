"""Real-frame, off-air pixel tests for ink recall/GO and standby transitions.

Load this file in a temporary Text DAT and call module.start(). No user show is
saved, physical windows stay closed, and audio is never armed.
"""
import json
import cProfile
import io
import pstats
import time
import traceback
from pathlib import Path

import numpy as np

STATE = {}
INK = ('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow')


def pixels(top):
    top.cook(force=True)
    data = top.numpyArray(delayed=False)
    assert data is not None and np.isfinite(data).all(), 'Invalid rendered pixels'
    assert not top.errors(), top.errors()
    return data.copy()


def later():
    run('op({!r}).module.advance()'.format(me.path), delayFrames=1)


def start(width=320, height=180):
    original = op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state == 'stopped', 'Stop show before QA'
    assert not STATE.get('running'), 'QA is already running'
    qa = original.parent().copy(original, name='cue_playback_qa')
    qa.op('show_tick').par.active = False
    qa.initializeExtensions()
    qa.par.Audioenabled = False
    qa.par.Masterblackout = False
    qa.par.Renderwidth, qa.par.Renderheight = width, height
    ext = qa.ext.ShowControlExt
    STATE.clear()
    STATE.update(running=True, qa=qa, ext=ext, index=0, clock=0., stage='setup', width=width, height=height,
                 checks={}, pixel_errors={}, timings=[], queued=[], started=time.monotonic())
    later()


def advance():
    s = STATE
    if not s.get('running'): return
    qa, ext = s['qa'], s['ext']
    try:
        assert time.monotonic() - s['started'] < 120, 'Cue playback QA timeout'
        stage = s['stage']
        if stage == 'setup':
            name = INK[s['index']]
            ext.engine.stop()
            values = dict(Coverage=.82, Seed=143, Scale=2.1, Particlesize=3.2,
                          Timescale=.25, Inkcolorr=.7, Inkcolorg=.03, Inkcolorb=.12,
                          Papercolorr=.08, Papercolorg=.12, Papercolorb=.2,
                          Patternenabled=True, Patterndensity=29., Patternsize=.22,
                          Patterncolorr=.1, Patterncolorg=.9, Patterncolorb=.4,
                          Glitterenabled=True, Glitterdensity=.7, Glittersize=4.,
                          Staticglitterenabled=True, Staticglitterdensity=.8,
                          Staticglittershimmer=.85, Staticglittertwinklespeed=2.3)
            cue = dict(ext.model.new_cue(), name=name, fade=0, duration=0,
                       look={'toggles':{ext.model.MODULE_TOGGLES[name]:True},
                             'modules':{name:values}})
            # Independent renderer, no ShowControl _apply_look. This detects a
            # saved-value/GLSL binding mismatch that parameter-only tests miss.
            parent = qa.create(baseCOMP, 'pixel_reference')
            source = parent.create(constantTOP, 'source')
            source.par.resolutionw, source.par.resolutionh = s['width'], s['height']
            golden = parent.copy(original_module(name), name='ink')
            golden.par.Enabled.bindExpr = ''
            golden.par.Enabled.mode = ParMode.CONSTANT
            golden.par.Enabled = True
            golden.par.Autotime = False
            golden.par.Manualtime = 0
            source.outputConnectors[0].connect(golden.inputConnectors[0])
            defaults = pixels(golden.op('out1_image'))
            for key, value in values.items(): golden.par[key] = value
            expected = pixels(golden.op('out1_image'))
            assert np.mean(np.abs(defaults-expected)) > .02, 'Custom fixture looks like defaults'
            ext._replace_cues([cue])
            ext.engine.clock = lambda: s['clock']
            ext.engine._last = s['clock']
            ext.SelectCue(1)
            ext.RecallLook()
            draft = ext._look_edit['deck'].op(name)
            draft.par.Autotime = False
            draft.par.Manualtime = 0
            s.update(stage='recall', cue=cue, golden=golden, expected=expected, frame=absTime.frame)
        elif stage == 'recall' and absTime.frame-s['frame'] >= 3:
            error = float(np.max(np.abs(pixels(qa.op('look_preview'))-s['expected'])))
            assert error < .012, 'Recall pixel mismatch: {}'.format(error)
            s['pixel_errors'][INK[s['index']]+'_recall_pixels'] = error
            s['checks'][INK[s['index']]+'_recall_pixels'] = True
            ext.CancelLook()
            t = time.perf_counter()
            ext.engine.go(0)
            s['queued'].append(time.perf_counter()-t)
            assert not ext.tracks, 'GO published incomplete deck'
            s['stage'] = 'go'
        elif stage == 'go':
            profiler = cProfile.Profile()
            t = time.perf_counter()
            profiler.enable()
            ext.Tick()
            profiler.disable()
            elapsed = time.perf_counter()-t
            s['timings'].append(elapsed)
            if elapsed > .03:
                stream = io.StringIO()
                pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(18)
                folder = Path(qa.par.Libraryroot.eval())/'build/envoy-validation'
                (folder/('cue-slow-'+INK[s['index']]+'.txt')).write_text(stream.getvalue())
            assert not ext.engine.errors, str(ext.engine.errors)
            if ext.tracks:
                error = float(np.max(np.abs(pixels(qa.op('track1'))-s['expected'])))
                if error >= .012:
                    folder = Path(qa.par.Libraryroot.eval())/'build/envoy-validation'
                    qa.op('track1').save(str(folder/'cue-go-actual.png'))
                    s['golden'].op('out1_image').save(str(folder/'cue-go-expected.png'))
                    deck=ext.tracks[1]['deck']
                    print('DECK DEBUG', deck.path, deck.allowCooking, qa.allowCooking,
                          deck.par.Customwidth.eval(), deck.par.Customheight.eval(),
                          deck.op(INK[s['index']]).par.Coverage.eval(),
                          {k:str(v) for k,v in ext.tracks[1].items() if k != 'cue'},
                          'source',str(qa.op('track1_source0').par.top.eval()))
                    print('GO DEBUG', qa.par.Track1blend.eval(), qa.par.Track1visible.eval(),
                          deck.op(INK[s['index']]).par.Enabled.eval(),
                          pixels(deck.op('out1_image')).shape,
                          [(p.name,str(p.eval())) for p in qa.op('track1').pars('vec*')])
                assert error < .012, 'GO pixel mismatch: {}'.format(error)
                s['pixel_errors'][INK[s['index']]+'_go_pixels'] = error
                s['checks'][INK[s['index']]+'_go_pixels'] = True
                s['clock'] += 8.
                ext.Tick()
                module = ext.tracks[1]['deck'].op(INK[s['index']])
                assert abs(module.par.Time.eval()-2.) < 1e-5, 'Saved Timescale not applied'
                s['golden'].par.Manualtime = 2.
                error = float(np.max(np.abs(pixels(qa.op('track1'))-pixels(s['golden'].op('out1_image')))))
                assert error < .012, 'Animated custom look mismatch: {}'.format(error)
                s['pixel_errors'][INK[s['index']]+'_timed_pixels'] = error
                s['checks'][INK[s['index']]+'_timed_pixels'] = True
                # Hold the active look while a radically different standby is
                # prepared. No frame may change before GO.
                module.par.Timescale = 0
                ext.tick(s['clock'])
                s['held'] = pixels(qa.op('track1'))
                next_cue = dict(ext.model.new_cue(), duration=0, fade=1)
                s['next'] = next_cue
                t = time.perf_counter(); ext.prepare(next_cue)
                s['queued'].append(time.perf_counter()-t)
                s['stage'] = 'standby'
        elif stage == 'standby':
            t = time.perf_counter(); ext._service_preloads()
            s['timings'].append(time.perf_counter()-t)
            hold_error = float(np.max(np.abs(s['held']-pixels(qa.op('track1')))))
            key = INK[s['index']]+'_standby_max_pixel_error'
            s['pixel_errors'][key] = max(s['pixel_errors'].get(key,0),hold_error)
            assert hold_error < .008, 'Preload changed the live output: {}'.format(hold_error)
            s['checks'][key] = True
            if ext.ready(s['next']):
                ext.start(s['next'], s['clock'])
                ext.tick(s['clock'])
                assert np.max(np.abs(s['held']-pixels(qa.op('track1')))) < .008, 'Fade began with a flash'
                new = pixels(ext.tracks[1]['deck'].op('out1_image'))
                ext.tick(s['clock']+.5)
                midway = pixels(qa.op('track1'))
                assert np.max(np.abs(midway-(s['held']+new)*.5)) < .015, 'Crossfade midpoint is not continuous'
                ext.tick(s['clock']+1.)
                assert np.max(np.abs(pixels(qa.op('track1'))-new)) < .015, 'Fade endpoint mismatch'
                s['checks'][INK[s['index']]+'_preload_and_crossfade'] = True
                ext.engine.stop()
                qa.op('pixel_reference').destroy()
                s['index'] += 1
                if s['index'] == len(INK):
                    finish()
                    return
                s['stage'] = 'setup'
        later()
    except Exception:
        finish(traceback.format_exc())


def original_module(name):
    return op('/project1/imagefx_demo/'+name)


def finish(error=None):
    s = STATE
    s['running'] = False
    report = dict(ok=error is None, checks=s['checks'], pixel_errors=s['pixel_errors'], error=error,
                  resolution=[s['width'],s['height']],
                  go_preload_call_ms=[round(x*1000,3) for x in s['queued']],
                  preparation_frame_max_ms=round(max(s['timings'],default=0)*1000,3),
                  physical_outputs_tested=False)
    folder = Path(s['qa'].par.Libraryroot.eval())/'build/envoy-validation'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'cue-playback.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    s['ext'].engine.stop()
    s['qa'].destroy()
    print('CUE PLAYBACK QA', json.dumps(report))
