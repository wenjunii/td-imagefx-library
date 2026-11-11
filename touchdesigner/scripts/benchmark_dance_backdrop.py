"""Run as a DAT module in the isolated audition; measures real-frame playback.

GPU readback is outside timed samples. The clean backdrop and the synchronized
comparison are cooked separately at their saved resolutions. User values are
restored at completion; this never saves the project or opens output windows.
"""
import json
from pathlib import Path
import time

_state = None


def start(c, output, frames=180):
    global _state
    if _state is not None:
        raise RuntimeError('Benchmark already running')
    if c.path != '/project1/dance_driven_backdrop':
        raise RuntimeError('Run only in the isolated backdrop audition')
    if op('/project1/imagefx_demo') or op('/project1/td_imagefx'):
        raise RuntimeError('Never benchmark in the production/harness session')
    if frames < 60:
        raise ValueError('Use at least 60 frames per stage')
    output = Path(output)
    if output.exists():
        raise RuntimeError('Choose a new report path')
    _state = dict(c=c, output=output, frames=frames, stage=0, sample=0,
                  rows=[], last=time.perf_counter(),
                  saved={name:c.par[name].eval() for name in ('Position','Playing','Loop','Playbackspeed')},
                  modes=('out1_image','comparison'), errors=[], starts={})
    c.par.Playing = False
    c.par.Position = 10.
    c.par.Playbackspeed = 1.
    c.par.Loop = True
    c.par.Playing = True
    _schedule()


def _schedule():
    run("op(args[0]).module.step()", me.path, delayFrames=1)


def step():
    global _state
    s = _state
    if s is None:
        return
    c = s['c']
    try:
        name = s['modes'][s['stage']]
        node = c.op(name)
        if s['sample'] == 0:
            s['starts'][name] = node.totalCooks
        node.cook(force=True)
        now = time.perf_counter()
        s['rows'].append(dict(mode=name, sample=s['sample'], dt_ms=(now-s['last'])*1000,
                              position=float(c.par.Position), cooks=node.totalCooks,
                              width=node.width, height=node.height))
        s['last'] = now
        s['sample'] += 1
        if s['sample'] >= s['frames']:
            s['stage'] += 1
            s['sample'] = 0
        if s['stage'] < len(s['modes']):
            _schedule()
            return
        checks = {}
        summary = {}
        for name in s['modes']:
            rows = [r for r in s['rows'] if r['mode'] == name]
            warm = rows[15:]
            durations = sorted(r['dt_ms'] for r in warm)
            mean = sum(durations)/len(durations)
            summary[name] = dict(fps=1000/mean, mean_ms=mean,
                                 p95_ms=durations[int((len(durations)-1)*.95)],
                                 cooks=rows[-1]['cooks']-s['starts'][name],
                                 resolution=[rows[-1]['width'],rows[-1]['height']])
            checks[name+'_cooked'] = summary[name]['cooks'] >= s['frames']-1
            checks[name+'_motion_advanced'] = rows[-1]['position'] > rows[0]['position']
            # A practical single-output regression threshold, not a show guarantee.
            checks[name+'_at_least_30fps'] = summary[name]['fps'] >= 30
        checks['clean'] = not c.errors(recurse=True) and not c.warnings(recurse=True)
        report = dict(ok=all(checks.values()), checks=checks, summary=summary, rows=s['rows'])
        s['output'].parent.mkdir(parents=True, exist_ok=True)
        s['output'].write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('BACKDROP PLAYBACK BENCHMARK', report['ok'], summary)
    except Exception as exc:
        s['errors'].append(str(exc))
        print('BACKDROP BENCHMARK FAILED:', str(exc))
    finally:
        if _state is not None and (s['stage'] >= len(s['modes']) or s['errors']):
            c.par.Playing = False
            for name,value in s['saved'].items():
                c.par[name] = value
            _state = None
