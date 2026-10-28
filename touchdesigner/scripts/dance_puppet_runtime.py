"""Embedded native puppet controls. All process launch is explicit and local.

Cue playback reads a baked Hap Alpha clip. Camera cues only read an already
started local camera session; loading a show cannot turn a camera on.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

# Process-local handles must never enter serialized operator storage. Each
# copied DAT gets its own cache; a cue copy cannot pickle or share live buffers.
_live_maps=None
_preview_owner=None
_preview_state=None


def clock_state(c, now=None):
    """Preview-only clock. Cue/branch Manualtime is never overwritten here."""
    global _preview_owner, _preview_state
    now=float(absTime.seconds if now is None else now)
    running=bool(c.par.Autotime)
    speed=float(c.par.Timescale)
    # Time evaluates this function while the component is cooking. Keep this
    # ephemeral clock in its own DAT module, not dependent operator storage;
    # fetch/store here creates a cook loop on a freshly opened project.
    state=_preview_state if _preview_owner == c else None
    if state is None:
        state=dict(origin=now,phase=0. if running else float(c.par.Manualtime),speed=speed,running=running)
    elif running != state['running']:
        phase=0. if running else state['phase']+(now-state['origin'])*state['speed']
        state=dict(origin=now,phase=phase,speed=speed,running=running)
    elif speed != state['speed']:
        phase=state['phase']+(now-state['origin'])*state['speed'] if running else float(c.par.Manualtime)
        state=dict(origin=now,phase=phase,speed=speed,running=running)
    _preview_owner, _preview_state=c,state
    return state


def preview_time(c):
    state=clock_state(c)
    if not c.par.Autotime: return float(c.par.Manualtime)
    return state['phase']+(float(absTime.seconds)-state['origin'])*state['speed']


def preview_transport(c, running, restart=False):
    global _preview_owner, _preview_state
    # Branches inherit the composition clock and running cue decks inherit the
    # show clock. Their preview buttons must not detach that ownership.
    if c.parent().fetch('imagefx_branch',False) or c.parent().name.startswith('deck'):
        c.par.Status='Use the parent composition / Show Control transport for this instance'
        return
    phase=0. if restart else preview_time(c)
    _preview_owner=c
    _preview_state=dict(origin=float(absTime.seconds),phase=phase,
        speed=float(c.par.Timescale),running=bool(running))
    c.par.Manualtime=phase
    # Parameter callbacks arrive on the next frame. Mark only a real resume
    # edge, so its callback cannot be confused with Animate Preview (restart).
    c.store('puppet_fade_resuming',bool(running and not restart and not c.par.Autotime))
    c.storeStartupValue('puppet_fade_resuming',False)
    c.par.Autotime=running
    if restart:
        reset_history(c)
        reset_fade(c)


def on_value(c, name, previous):
    if name=='Enabled' and c.par.Enabled: reset_fade(c)
    if name=='Autotime':
        resuming=c.fetch('puppet_fade_resuming',False,search=False)
        c.store('puppet_fade_resuming',False)
        old=_preview_state if _preview_owner == c else None
        state=clock_state(c)
        # A direct toggle OFF freezes at the current frame; toggling ON starts
        # from zero. Resume is a separate pulse and has already set its state.
        if old and old['running'] and not c.par.Autotime:
            if not c.parent().fetch('imagefx_branch',False) and not c.parent().name.startswith('deck'):
                c.par.Manualtime=state['phase']
        if c.par.Autotime and not resuming:
            reset_fade(c)
    elif name=='Timescale': clock_state(c)
    if name not in ('Time','Manualtime','Ready','Status','Duration','Buildstatus','Timescale','Pausepreview','Resumepreview',
                    'Trailamount','Trailhalf','Trailsoftness','Transparent','Backgroundr','Backgroundg','Backgroundb','Fadein'):
        reset_history(c)


def root(c):
    return Path(c.fetch('imagefx_puppet_root', '', search=False) or project.folder).resolve()


def local_settings(c):
    path=root(c)/'.imagefx'/'puppet-settings.json'
    if not path.is_file(): raise ValueError('Puppet backend is not configured: .imagefx/puppet-settings.json')
    return json.loads(path.read_text(encoding='utf-8'))


def read_json(path):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}


def atomic_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    # Readers never hold the status file between polls. A virus scanner may
    # briefly open it without Windows delete-sharing; retry on the next tick.
    try: os.replace(temp,path)
    except PermissionError: raise ValueError('Local job file is busy; try again')


def session(c):
    value=read_json(root(c)/'.imagefx'/'puppet-live.json').get('job','')
    if not value: return None
    path=Path(value).resolve(); jobs=(root(c)/'.imagefx'/'puppet-jobs').resolve()
    if path.parent!=jobs: raise ValueError('Invalid local camera session')
    return path


def start(c, mode, analyze=False):
    settings=local_settings(c)
    python=Path(settings.get('live_python',settings['python']) if mode=='live' else settings['python'])
    service=root(c)/'prototypes'/'dance_puppet'/'service.py'
    if not python.is_file() or not service.is_file(): raise ValueError('Puppet Python runtime is missing')
    if not Path(c.par.Characterprofile.eval()).is_file(): raise ValueError('Select a calibrated Character Profile')
    if mode=='live':
        old=session(c)
        previous=read_json(old/'status.json') if old else {}
        fresh=time.time()-previous.get('updated',0)<30
        if old and fresh and previous.get('state') not in {'error','cancelled','stopped'}:
            raise ValueError('Stop Camera before starting another camera session')
    else:
        old=c.fetch('puppet_build_job',None,search=False)
        if old and read_json(Path(old)/'status.json').get('state') not in {'ready','error','cancelled'}:
            raise ValueError('A build is already running; cancel it or wait')
    job=root(c)/'.imagefx'/'puppet-jobs'/uuid.uuid4().hex; job.mkdir(parents=True)
    data=dict(profile=c.par.Characterprofile.eval(),models=settings['models'],ffmpeg=settings['ffmpeg'],
              video=c.par.Dancevideo.eval(),motion=c.par.Motioncache.eval(),analyze=analyze,
              camera=int(c.par.Cameraindex),smoothing=float(c.par.Livesmoothing),size=[1920,1080],
              remove_camera_motion=bool(c.par.Removecamera),
              provider=settings.get('live_provider','cpu'),gpu=int(settings.get('live_gpu',0)),
              render_gpu=settings.get('render_gpu',''))
    atomic_json(job/'config.json',data); atomic_json(job/'status.json',{'state':'starting','updated':time.time()})
    log=(job/'worker.log').open('w',encoding='utf-8')
    try:
        proc=subprocess.Popen([str(python),str(service),mode,'--job',str(job)],cwd=str(root(c)),
                              stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    finally: log.close()
    if mode=='live':
        try: atomic_json(root(c)/'.imagefx'/'puppet-live.json',{'job':str(job),'pid':proc.pid})
        except Exception:
            (job/'cancel').touch()
            raise
        c.store('puppet_camera_owner',str(job)); c.storeStartupValue('puppet_camera_owner',None)
        (job/'heartbeat').touch()
        c.par.Status='Camera starting; it will stop if TouchDesigner disconnects'
    else:
        c.store('puppet_build_job',str(job)); c.storeStartupValue('puppet_build_job',None)
        c.par.Buildstatus='Starting local preparation; previous render retained until success'


def on_pulse(c, name):
    try:
        if name=='Analyzevideo': start(c,'build',True)
        elif name=='Buildmotion': start(c,'build',False)
        elif name=='Startcamera': start(c,'live')
        elif name=='Stopcamera':
            job=session(c)
            if job: (job/'cancel').touch()
            c.par.Status='Camera stop requested'
        elif name=='Cancelbuild':
            job=c.fetch('puppet_build_job',None,search=False)
            if job: (Path(job)/'cancel').touch()
        elif name=='Clearhistory': reset_history(c)
        elif name=='Restartmotion': preview_transport(c,False,restart=True)
        elif name=='Pausepreview': preview_transport(c,False)
        elif name=='Resumepreview': preview_transport(c,True)
        elif name=='Openpuppet': c.op('puppet_rgba').openViewer()
    except Exception as exc:
        c.par.Status=str(exc)
        if name in {'Analyzevideo','Buildmotion','Cancelbuild'}: c.par.Buildstatus=str(exc)


def poll(c):
    now=time.monotonic()
    if now-c.fetch('puppet_last_poll',0,search=False)<.25: return
    c.store('puppet_last_poll',now); c.storeStartupValue('puppet_last_poll',0)
    job=c.fetch('puppet_build_job',None,search=False)
    if job:
        data=read_json(Path(job)/'status.json'); state=data.get('state','starting')
        c.par.Buildstatus=state+': '+data.get('message',str(round(data.get('progress',0)*100))+'%')
        if state=='ready':
            c.par.Renderfile=data['render']; c.par.Motioncache=data['motion']; c.par.Duration=data['duration']
            c.par.Fanrenderfile=data.get('renders',{}).get('fan','')
            c.par.Chainrenderfile=data.get('renders',{}).get('chain','')
            c.store('puppet_build_job',None); reset_history(c)
        elif state in {'error','cancelled'}: c.store('puppet_build_job',None)
    camera=c.fetch('puppet_camera_owner',None,search=False)
    if camera: (Path(camera)/'heartbeat').touch()
    if c.par.Sourcemode.eval()=='live':
        job=session(c); data=read_json(job/'status.json') if job else {}
        fresh=time.time()-data.get('updated',0)<5
        profile=read_json(job/'config.json').get('profile','') if job else ''
        matches=bool(profile and Path(profile).resolve()==Path(c.par.Characterprofile.eval()).resolve())
        c.par.Ready=bool(fresh and data.get('state')=='live' and matches)
        c.par.Status=('Live camera: '+str(round(data.get('effective_fps',0),1))+' tracking FPS; '+str(data.get('tracking',[]))
                      +'; '+data.get('provider','?').upper()+' / '+data.get('renderer','graphics device pending')
                      if c.par.Ready else data.get('message','Start Camera explicitly before GO'))
        if fresh and data.get('state')=='live' and not matches:
            c.par.Status='Camera character profile differs; stop and restart camera with this profile'
    else:
        movie=c.op('recorded_motion'); path=c.par[{'both':'Renderfile','fan':'Fanrenderfile','chain':'Chainrenderfile'}[c.par.Characters.eval()]].eval()
        c.par.Ready=bool(path and Path(path).is_file() and not movie.errors())
        c.par.Status='Recorded RGBA motion ready' if c.par.Ready else 'Build motion or choose a prepared RGBA movie'
        if path and c.fetch('puppet_duration_file',None,search=False)!=path:
            metadata=read_json(Path(path).parent/'status.json')
            prepared=[metadata.get('render',''),*metadata.get('renders',{}).values()]
            if metadata.get('state')=='ready' and any(value and Path(value).resolve()==Path(path).resolve() for value in prepared):
                c.par.Duration=float(metadata.get('duration',0))
            else: c.par.Duration=0
            c.store('puppet_duration_file',path); c.storeStartupValue('puppet_duration_file',None)


def copy_live(c, script):
    global _live_maps
    import numpy as np
    job=session(c)
    if job is None or time.time()-read_json(job/'status.json').get('updated',0)>3:
        script.copyNumpyArray(np.zeros((2,2,4),dtype=np.uint8)); return
    data=read_json(job/'status.json')
    profile=read_json(job/'config.json').get('profile','')
    if data.get('state')!='live' or not profile or Path(profile).resolve()!=Path(c.par.Characterprofile.eval()).resolve():
        script.copyNumpyArray(np.zeros((2,2,4),dtype=np.uint8)); return
    views=int(data.get('views',1)); key=(str(job),views); cached=_live_maps
    if not cached or cached[0]!=key:
        header=np.memmap(job/'header.bin',mode='r',dtype=np.int64,shape=(4,))
        shape=(2,3,720,1280,4) if views==3 else (2,720,1280,4)
        pixels=np.memmap(job/'frames.rgba',mode='r',dtype=np.uint8,shape=shape)
        cached=(key,header,pixels); _live_maps=cached
    before=int(cached[1][0]); slot=int(cached[1][1])
    view={'both':0,'fan':1,'chain':2}[c.par.Characters.eval()]
    if views!=3 and view:
        script.copyNumpyArray(np.zeros((2,2,4),dtype=np.uint8)); return
    if before>0 and slot in (0,1) and c.fetch('puppet_live_sequence',None,search=False)!=(key,before,view):
        pixels=(cached[2][slot,view] if views==3 else cached[2][slot]).copy()
        if int(cached[1][0])==before:
            script.copyNumpyArray(pixels)
            c.store('puppet_live_sequence',(key,before,view)); c.storeStartupValue('puppet_live_sequence',None)
    (job/'heartbeat').touch()


def reset_history(c):
    c.store('puppet_finish_clock',None); c.storeStartupValue('puppet_finish_clock',None)
    history=c.op('puppet_history')
    if history is not None: history.par.resetpulse.pulse()


def reset_fade(c):
    value=float(absTime.seconds if c.par.Sourcemode=='live' else c.par.Time)
    c.store('puppet_fade_start',value); c.storeStartupValue('puppet_fade_start',None)


def fade_gain(c):
    duration=float(c.par.Fadein)
    if duration<=0: return 1.
    current=float(absTime.seconds if c.par.Sourcemode=='live' else c.par.Time)
    origin=c.fetch('puppet_fade_start',None,search=False)
    if origin is None:
        reset_fade(c); origin=current
    x=max(0.,min(1.,(current-origin)/duration))
    return x*x*(3-2*x)


def finish_clock(c):
    current=float(absTime.seconds if c.par.Sourcemode=='live' else c.par.Time)
    old=c.fetch('puppet_finish_clock',None,search=False)
    frame=int(absTime.frame)
    if old and old['frame']==frame and old['time']==current: return old['value']
    dt=0 if old is None else current-old['time']
    duration=float(c.par.Duration)
    cycle=int((current+float(c.par.Offset))/duration) if duration>0 and bool(c.par.Loop) else 0
    wall=float(absTime.seconds)
    elapsed=max(0.,wall-old.get('wall',wall)) if old else 0.
    # Low render FPS is not a seek. Allow the full elapsed time (and supported
    # playback rates); decay by seconds, not by an arbitrary .25-second cap.
    jumped=dt>max(1.,elapsed*8.+.1)
    reset=old is None or dt<0 or jumped or not bool(c.par.Feedbackenabled) or old.get('cycle',cycle)!=cycle
    value=(max(0,dt),float(reset),float(dt==0 and old is not None),0.)
    c.store('puppet_finish_clock',dict(frame=frame,time=current,wall=wall,value=value,cycle=cycle)); c.storeStartupValue('puppet_finish_clock',None)
    return value
