"""Embedded Dance Forces runtime. Only explicit pulse actions launch processes."""
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid
import numpy as np

_clip = None
_clip_key = None
_sample_key = None
_sample = np.zeros((12,4)).tolist()
_live_filter = None
_live_key = None
_live_points = None
_live_force = None
_poll_at = 0.


def root(c): return Path(c.fetch('imagefx_dance_forces_root', '', search=False) or project.folder).resolve()


def read(path):
    try:
        if Path(path).stat().st_size > 1024*1024: return {}
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def session(c):
    value = read(root(c)/'.imagefx/dance-forces-live.json').get('job', '')
    if not value: return None
    path = Path(value).resolve()
    if path.parent != (root(c)/'.imagefx/dance-forces-jobs').resolve():
        raise ValueError('Invalid Dance Forces camera session')
    return path


def reset(c):
    global _sample_key, _live_filter, _live_key
    _sample_key = _live_filter = _live_key = None
    c.store('dance_force_clock', dict(raw=float(c.par.Time), phase=0., speed=float(c.par.Dancespeed)))
    c.storeStartupValue('dance_force_clock', None)
    c.store('dance_force_activation', float(c.par.Time))
    c.storeStartupValue('dance_force_activation', None)
    c.store('dance_force_gate', None)
    c.storeStartupValue('dance_force_gate', None)
    c.store('dance_force_ready', False)
    c.storeStartupValue('dance_force_ready', None)
    reset_flow(c)


def reset_flow(c):
    """Discard material history on GO/restart/seek, never on a force edit."""
    c.store('dance_flow_clock', None)
    c.storeStartupValue('dance_flow_clock', None)
    for name in ('dance_motion_history', 'dance_response_history'):
        history = c.op(name)
        if history is not None:
            history.par.resetpulse.pulse()


def flow_step(c):
    """One integration step per cooked frame; cue pauses hold the field exactly."""
    raw = float(c.par.Time)
    frame = int(absTime.frame)
    source = c.op('in1_image')
    size = (source.width, source.height) if source is not None else (0, 0)
    state = c.fetch('dance_flow_clock', None, search=False)
    stamp = (frame, raw, size)
    if state is not None and state['stamp'] == stamp:
        return state
    delta = 0. if state is None else raw - state['raw']
    # A seek or a previously uncooked deck must not integrate a huge time step.
    reset = state is None or size != state['size'] or delta < -1e-6 or delta > .5
    state = dict(stamp=stamp, raw=raw, size=size, reset=int(reset),
                 dt=0. if reset else min(.1, max(0., delta)))
    c.store('dance_flow_clock', state)
    c.storeStartupValue('dance_flow_clock', None)
    return state


def motion_time(c):
    raw = float(c.par.Time); speed = float(c.par.Dancespeed)
    state = c.fetch('dance_force_clock', None, search=False)
    if state is None:
        state = dict(raw=raw, phase=0., speed=speed)
    phase = state['phase'] + (raw-state['raw'])*state['speed']
    if speed != state['speed']:
        state = dict(raw=raw, phase=phase, speed=speed)
    c.store('dance_force_clock', state); c.storeStartupValue('dance_force_clock', None)
    return max(0., phase) + float(c.par.Danceoffset)


def output_enabled(c):
    """Arm synchronously before connecting history, even before DAT callbacks.

    A re-enabled Switch TOP can expose its cached previous output on the same
    frame. Keep that activation frame on the exact zero-field path, clear both
    histories, then begin integration on subsequent frames.
    """
    global _sample_key
    enabled = bool(c.par.Enabled and c.par.Mix > 0 and c.par.Danceenabled and c.par.Danceamount > 0)
    state = c.fetch('dance_force_gate', None, search=False)
    if state is None or state['enabled'] != enabled:
        state = dict(enabled=enabled, frame=int(absTime.frame))
        c.store('dance_force_gate', state)
        c.storeStartupValue('dance_force_gate', None)
        _sample_key = None
        if enabled:
            if c.fetch('dance_force_clock', None, search=False) is None:
                c.store('dance_force_clock', dict(raw=float(c.par.Time), phase=0., speed=float(c.par.Dancespeed)))
                c.storeStartupValue('dance_force_clock', None)
            c.store('dance_force_activation', float(c.par.Time))
            c.storeStartupValue('dance_force_activation', None)
            c.store('dance_force_ready', False)
            c.storeStartupValue('dance_force_ready', None)
            reset_flow(c)
    return int(enabled and int(absTime.frame) > state['frame'])


def changed(c, name, previous):
    global _sample_key, _clip_key
    if name in {'Dancestatus', 'Danceduration'}: return
    _sample_key = None
    if name == 'Dancespeed': motion_time(c)
    elif name in {'Dancecache', 'Dancesource'}:
        _clip_key = None; reset(c)
    elif name in {'Enabled', 'Danceenabled', 'Danceamount'}:
        output_enabled(c)
    elif name == 'Danceoffset':
        reset_flow(c)


def start(c, mode):
    settings = read(root(c)/'.imagefx/puppet-settings.json')
    python = Path(settings.get('python','')); models = Path(settings.get('models',''))
    if not python.is_file() or not models.is_dir():
        raise ValueError('Configure the private CUDA Python and local models first (see Dance Forces guide)')
    if mode == 'analyze' and not Path(c.par.Dancevideo.eval()).is_file():
        raise ValueError('Select a local dancers video first')
    old = session(c) if mode == 'live' else c.fetch('dance_force_job', None, search=False)
    if old:
        state = read(Path(old)/'status.json')
        if state.get('state') not in {'ready','error','cancelled','stopped'} and time.time()-state.get('updated',0) < 30:
            raise ValueError('A worker is already running; stop/cancel it first')
    # Avoid stealing a camera already owned by the separate puppet worker.
    if mode == 'live':
        puppet = read(root(c)/'.imagefx/puppet-live.json').get('job','')
        if puppet:
            state = read(Path(puppet)/'status.json')
            if time.time()-state.get('updated',0) < 15 and state.get('state') not in {'error','stopped','cancelled'}:
                raise ValueError('Stop the puppet camera before starting Dance Forces')
    job = root(c)/'.imagefx/dance-forces-jobs'/uuid.uuid4().hex
    job.mkdir(parents=True)
    write(job/'config.json', dict(video=c.par.Dancevideo.eval(), models=str(models),
        camera=int(c.par.Dancecamera), gpu=int(settings.get('live_gpu',0)), fps=24))
    write(job/'status.json', dict(state='starting', updated=time.time()))
    (job/'heartbeat').touch()
    with (job/'worker.log').open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([str(python),str(root(c)/'prototypes/dance_forces/service.py'),mode,'--job',str(job)],
            cwd=str(root(c)),stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    key = 'dance_force_camera_owner' if mode == 'live' else 'dance_force_job'
    c.store(key, str(job)); c.storeStartupValue(key, None)
    if mode == 'live': write(root(c)/'.imagefx/dance-forces-live.json',dict(job=str(job),pid=proc.pid))
    c.par.Dancestatus = 'Starting CUDA '+mode+'; original look is retained'


def pulse(c, name):
    try:
        if name == 'Danceanalyze': start(c, 'analyze')
        elif name == 'Dancestartcamera': start(c, 'live')
        elif name == 'Dancestopcamera':
            job = session(c)
            if job: (job/'cancel').touch()
            c.par.Dancestatus = 'Camera stop requested'
        elif name == 'Dancecancel':
            job = c.fetch('dance_force_job', None, search=False)
            if job: (Path(job)/'cancel').touch()
        elif name == 'Dancerestart': reset(c)
        elif name == 'Danceuselatest':
            latest = read(root(c)/'.imagefx/dance-forces-latest.json')
            path = Path(latest.get('motion',''))
            if not path.is_file(): raise ValueError('No completed analysis yet')
            c.op('dance_forces_math').module.Clip.read(path)
            c.par.Dancecache = str(path); c.par.Danceduration = latest.get('duration',0)
            c.par.Dancestatus = 'Prepared motion selected; enable Dance Forces to use it'
    except Exception as exc: c.par.Dancestatus = str(exc)


def poll(c):
    global _poll_at
    if time.monotonic()-_poll_at < .3: return
    _poll_at = time.monotonic()
    for key in ('dance_force_job','dance_force_camera_owner'):
        job = c.fetch(key, None, search=False)
        if not job: continue
        job = Path(job); state = read(job/'status.json')
        c.par.Dancestatus = state.get('message',state.get('state','Starting'))
        if key == 'dance_force_camera_owner': (job/'heartbeat').touch()
        if state.get('state') == 'ready' and key == 'dance_force_job':
            c.par.Dancecache = state['motion']; c.par.Danceduration = state['duration']
            write(root(c)/'.imagefx/dance-forces-latest.json',state)
        if state.get('state') in {'ready','error','stopped','cancelled'}: c.store(key,None)


def sample(c):
    global _clip, _clip_key, _sample_key, _sample, _live_filter, _live_key, _live_points, _live_force
    if not output_enabled(c):
        return np.zeros((12,4)).tolist()
    mathmod = c.op('dance_forces_math').module
    names = ('Dancesmooth','Dancedecay','Danceconfidence','Dancethreshold','Dancezoom','Dancepanx','Dancepany',
             'Dancemirror','Dancebody','Dancehands','Dancefeet','Danceactor1','Danceactor2','Dancestrength','Danceloop','Dancefadein')
    values = tuple(c.par[n].eval() for n in names)
    settings = dict(zip(names,values)); t = motion_time(c)
    stamp = (int(absTime.frame),t,c.par.Dancesource.eval(),c.par.Dancecache.eval(),values)
    if stamp == _sample_key: return _sample
    _sample_key = stamp
    try:
        filtering = dict(smoothing=values[0],decay=values[1],confidence=values[2],threshold=values[3])
        if c.par.Dancesource == 'recorded':
            path = Path(c.par.Dancecache.eval())
            # Never parse/filter the entire movie on the render thread. The
            # shared worker does no TD API calls and never starts inference.
            key, prepared = mathmod.prepared_clips().request(path, values[:4])
            if prepared is not None:
                _clip = prepared; _clip_key = key
                c.par.Danceduration = _clip.duration
            elif _clip is None or _clip_key is None or _clip_key[0] != key[0]:
                c.par.Dancestatus = 'Preparing force playback in background; pattern continues'
                _sample = np.zeros((12,4)).tolist()
                return _sample
            # During filter edits, keep the previous valid force until the new
            # settings are ready. Do not invoke the synchronous filter rebuild.
            points, forces = _clip.sample(t,loop=bool(c.par.Danceloop),
                **dict(zip(('smoothing','decay','confidence','threshold'),_clip.settings)))
            c.par.Dancestatus = f'Recorded forces {t:.1f}s / {_clip.duration:.1f}s — camera compensated'
        else:
            job = session(c); data = read(job/'live.json') if job else {}
            age = time.time()-data.get('updated',0)
            if age > 1. or age < -.1: raise ValueError('Live forces unavailable/stale — use Start Camera')
            newkey = (str(job), data['sequence'])
            if _live_filter is None or (_live_key and _live_key[0] != str(job)):
                _live_filter = mathmod.Filter(); _live_key = None
            if newkey != (_live_key[:2] if _live_key else None):
                dt = min(.25,max(.001,data['updated']-(_live_key[2] if _live_key else data['updated']-1/30)))
                _live_points = np.asarray(data['points'],float)
                _live_force = _live_filter.step(_live_points,dt,**filtering)
                _live_key = (*newkey,data['updated'])
            points, forces = _live_points, _live_force * math.exp(-max(0.,age-.15)/.2)
            c.par.Dancestatus = 'Live camera forces — camera compensated'
        origin = c.fetch('dance_force_activation', None, search=False)
        if origin is None or not c.fetch('dance_force_ready', False, search=False):
            origin = float(c.par.Time); c.store('dance_force_activation',origin); c.storeStartupValue('dance_force_activation',None)
            c.store('dance_force_ready', True); c.storeStartupValue('dance_force_ready',None)
        forces = forces * mathmod.fade_in(max(0.,float(c.par.Time)-origin),float(c.par.Dancefadein))
        _sample = mathmod.map_forces(points,forces,zoom=values[4],panx=values[5],pany=values[6],mirror=values[7],
            body=values[8],hands=values[9],feet=values[10],actor1=values[11],actor2=values[12],strength=values[13]).tolist()
    except Exception as exc:
        c.par.Dancestatus = str(exc)
        _sample = np.zeros((12,4)).tolist()
    return _sample


def active(c):
    # Incoming velocity activity only. The integrated material state must keep
    # its position after the force releases, rather than switching to old UVs.
    if float(c.par.Dancepush)==0 and float(c.par.Danceswirl)==0 and float(c.par.Danceacceleration)==0: return False
    return any(abs(v)>1e-9 for row in sample(c) for v in row[2:])
