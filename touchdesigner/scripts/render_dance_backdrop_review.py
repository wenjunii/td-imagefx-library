"""Frame-stepped silent comparison export for the isolated backdrop audition.

Run as a Text DAT. The caller chooses a NEW local folder. No movie/audio device
is opened; PNGs can be encoded using ffmpeg outside TouchDesigner.
"""
import json
from pathlib import Path
import traceback

STATE = {}


def start(c, folder, start_seconds=10., duration=12., fps=30):
    global STATE
    folder=Path(folder)
    if STATE.get('running') or folder.exists():
        raise RuntimeError('Export running or destination exists; choose a new folder')
    if c.par.Playing:
        raise RuntimeError('Pause playback before frame-stepped export')
    clip=c.op('runtime').module.model(c)
    if not (0 <= start_seconds < clip.end and duration > 0 and 1 <= fps <= 60 and start_seconds+duration <= clip.duration):
        raise ValueError('Export range exceeds motion clip')
    folder.mkdir(parents=True)
    STATE=dict(running=True,c=c,folder=folder,frame=0,total=round(duration*fps),
               start=start_seconds,fps=fps,position=float(c.par.Position))
    c.par.Position=start_seconds
    c.op('runtime').module.refresh(c)
    later()


def later():
    run('op({!r}).module.step()'.format(me.path),delayFrames=3)


def step():
    s=STATE; c=s['c']
    try:
        if not s['running']:
            return
        for path in ('motion_warp','calligraphic_shadow/effect_glsl_calligraphic_shadow','comparison'):
            top=c.op(path)
            top.cook(force=True)
            if top.errors() or top.warnings():
                raise RuntimeError(str(top.errors())+str(top.warnings()))
        c.op('comparison').save(str(s['folder']/('frame_%05d.png'%s['frame'])))
        s['frame']+=1
        if s['frame']%30==0:
            print('Backdrop review frames',s['frame'],'/',s['total'])
        if s['frame'] >= s['total']:
            finish(True)
            return
        c.par.Position=s['start']+s['frame']/s['fps']
        c.op('runtime').module.refresh(c)
        later()
    except Exception:
        finish(False,traceback.format_exc())


def finish(ok,error=None):
    s=STATE
    s['running']=False
    s['c'].par.Playing=False
    s['c'].par.Position=s['position']
    s['c'].op('runtime').module.refresh(s['c'])
    (s['folder']/'export.json').write_text(json.dumps(dict(ok=ok,frames=s['frame'],
        fps=s['fps'],start=s['start'],error=error),indent=2),encoding='utf-8')
    print('Backdrop review export:',ok,error or '')
