"""Native, asynchronous preview checks. Run from an embedded Text DAT."""
import json
from pathlib import Path

import numpy as np


def begin(component,report_path):
    if me.name != 'preview_validation':
        raise RuntimeError('Load this script into a preview_validation Text DAT first')
    saved={p.name:p.eval() for p in component.customPars if not p.readOnly and not p.isPulse}
    component.par.Playing=False
    component.par.Enabled=True
    component.par.Composition='full'
    component.par.Position=0
    component.par.Zoom=1; component.par.Panx=0; component.par.Pany=0
    me.store('qa',dict(component=component.path,report_path=str(report_path),saved=saved,
                       stage=0,checks=[],errors=[]))
    run("op(args[0]).module.step()",me.path,delayFrames=15)


def step():
    q=me.fetch('qa'); c=op(q['component']); p=c.par; stage=q['stage']
    def check(label,condition):
        q['checks'].append(dict(name=label,passed=bool(condition)))
        if not condition: q['errors'].append(label)
    def pixels():
        c.op('out1').cook(force=True)
        data=c.op('out1').numpyArray(delayed=False)
        if data is None: raise RuntimeError('TOP readback unavailable')
        return data.copy()
    def finish():
        q['status']='passed' if not q['errors'] else 'failed'
        q['manual_checks']=['Open Preview button / viewer requires separate inspection']
        result={k:v for k,v in q.items() if k not in ('base','time4','saved')}
        Path(q['report_path']).write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('Puppet preview QA:',q['status'],len(q['checks']),'checks',q['errors'])
    try:
        if stage==0:
            errors=[(n.path,str(n.errors())) for n in c.findChildren() if n.errors()]
            check('No operator errors',not errors)
            q['operator_errors']=errors
            a=pixels(); q['base']=a
            q['output_size']=[a.shape[1],a.shape[0]]
            check('1080p decoded output',a.shape[:2]==(1080,1920))
            check('Visible full-body image',float(np.std(a[:,:,:3]))>.005)
            p.Composition='cropped'
        elif stage==1:
            a=pixels()
            check('Composition switch changes pixels',float(np.mean(abs(a-q['base'])))>.005)
            p.Composition='full'; p.Position=4
        elif stage==2:
            a=pixels(); q['time4']=a
            check('Seek changes decoded frame',float(np.mean(abs(a-q['base'])))>.0005)
            decoders=[n for n in ('movie_full_body','movie_cropped','movie_source') if c.op(n) is not None]
            check('All decoders use same requested time',all(abs(float(c.op(n).par.index)-4)<1e-5 for n in decoders))
            p.Zoom=1.3
        elif stage==3:
            check('Zoom changes pixels',float(np.mean(abs(pixels()-q['time4'])))>.001)
            p.Zoom=1; p.Panx=.1
        elif stage==4:
            check('Pan X changes pixels',float(np.mean(abs(pixels()-q['time4'])))>.001)
            p.Panx=0; p.Pany=.1
        elif stage==5:
            check('Pan Y changes pixels',float(np.mean(abs(pixels()-q['time4'])))>.001)
            p.Enabled=False
        elif stage==6:
            check('Disabled output transparent',float(np.max(abs(pixels())))<1e-6)
            p.Enabled=True; p.Zoom=2; p.Panx=.2; p.Pany=.2
            p.Resetview.pulse()
        elif stage==7:
            check('Reset View pulse',p.Zoom==1 and p.Panx==0 and p.Pany==0)
            p.Speed=1; p.Loop=False; p.Go.pulse()
        elif stage==8:
            check('GO restarts near beginning',p.Playing and 0<=float(p.Position)<1)
            q['go_position']=float(p.Position)
        elif stage==9:
            check('Native clock advances playback',p.Playing and float(p.Position)>q['go_position'])
            p.Pause.pulse(); q['paused']=float(p.Position)
        elif stage==10:
            check('Pause disables playback',not p.Playing)
            q['paused']=float(p.Position)
        elif stage==11:
            check('Pause holds position',not p.Playing and abs(float(p.Position)-q['paused'])<1e-6)
            p.Pause.pulse()
        elif stage==12:
            check('Pause toggles resume',bool(p.Playing))
            p.Stop.pulse()
        elif stage==13:
            check('Stop rewinds',not p.Playing and p.Position==0)
            p.Position=1; p.Speed=-1; p.Playing=True
        elif stage==14:
            check('Negative speed reverses',float(p.Position)<1)
            p.Playing=False; p.Speed=2; p.Position=0; p.Playing=True
        elif stage==15:
            check('Positive speed advances',float(p.Position)>0)
            p.Playing=False; p.Speed=1; p.Loop=True
            p.Position=float(p.Duration)-1/float(p.Framerate); p.Playing=True
            q['loop_start_position']=float(p.Position)
            q['loop_start_time']=float(absTime.seconds)
        elif stage==16:
            elapsed=float(absTime.seconds)-q['loop_start_time']
            duration=float(p.Duration)
            expected=(q['loop_start_position']+elapsed)%duration
            error=abs((float(p.Position)-expected+duration*.5)%duration-duration*.5)
            q['loop_position']=float(p.Position); q['loop_elapsed']=elapsed
            # Initial movie seeking can stall a realtime project. Check the
            # correct wrapped clock, not an arbitrary position-under-two-seconds.
            check('Loop wraps end',p.Playing and elapsed>=1/float(p.Framerate) and error<.075)
            p.Playing=False; p.Loop=False
            p.Position=float(p.Duration)-1/float(p.Framerate); p.Playing=True
        elif stage==17:
            check('Nonlooping playback stops at end',not p.Playing)
            p.Position=2; p.Playing=True; p.Enabled=False
            q['disabled_position']=float(p.Position)
        elif stage==18:
            check('Hidden preview freezes playback',abs(float(p.Position)-q['disabled_position'])<1e-6)
            p.Playing=False; p.Enabled=True
            p.Zoom=100; p.Panx=-100; p.Pany=100; p.Speed=100; p.Position=100
            check('Numeric bounds are enforced',p.Zoom==3 and p.Panx==-.5 and p.Pany==.5 and p.Speed==2 and p.Position<=float(p.Duration))
            # Back to safe defaults for the local demonstration.
            p.Zoom=1; p.Panx=0; p.Pany=0; p.Speed=1; p.Position=0
            p.Composition='full'; p.Loop=False
        elif stage==19:
            check('Final output remains valid',float(np.std(pixels()[:,:,:3]))>.005)
            if c.op('movie_source') is None:
                finish()
                return
            p.Composition='source'
        elif stage==20:
            check('Source framing changes actual pixels',float(np.mean(abs(pixels()-q['base'])))>.001)
            check('Source framing keeps opening pose time',p.Position==0 and float(c.op('movie_source').par.index)==0)
            p.Composition='full'
        elif stage==21:
            finish()
            return
        q['stage']+=1
        run("op(args[0]).module.step()",me.path,delayFrames=15)
    except Exception as exc:
        p.Playing=False
        result=dict(status='error',error=str(exc),checks=q['checks'],stage=stage)
        Path(q['report_path']).write_text(json.dumps(result,indent=2),encoding='utf-8')
        raise
