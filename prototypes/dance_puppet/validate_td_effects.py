"""Native v5 finish QA: actual pixels, controls, navigation and shader probes."""
import json
from pathlib import Path

import numpy as np


def begin(component,path):
    if me.name!='effects_validation': raise RuntimeError('Use an effects_validation Text DAT')
    me.store('qa',dict(component=component.path,path=str(path),stage=0,checks=[],errors=[]))
    # Automated QA must exercise temporal history even if the output viewer is
    # occluded by the Textport. Demand one finished frame on every TD frame.
    clock=me.parent().op('v5_finish_qa_clock') or me.parent().create(executeDAT,'v5_finish_qa_clock')
    clock.store('component',component.path)
    clock.store('validator',me.path); clock.store('countdown',15)
    # Count rendered frames, not absTime frames skipped during a cold movie seek.
    clock.text="""def onFrameEnd(frame):
    op(me.fetch('component')).op('out1').cook(force=True)
    count=me.fetch('countdown',15)-1
    me.store('countdown',count if count>0 else 30)
    if count<=0: op(me.fetch('validator')).module.step()
"""
    clock.par.frameend=True


def step():
    q=me.fetch('qa'); c=op(q['component']); p=c.par; stage=q['stage']
    def check(name,value):
        q['checks'].append(dict(name=name,passed=bool(value)))
        if not value: q['errors'].append(name)
    def pixels(name='out1'):
        top=c.op(name); top.cook(force=True)
        a=top.numpyArray(delayed=False)
        if a is None: raise RuntimeError('No GPU readback for '+name)
        return a.copy()
    def difference(a,b): return float(np.mean(abs(a-b)))
    def clean(): return difference(pixels(),pixels('framing'))<.00005
    def finish():
        me.parent().op('v5_finish_qa_clock').par.frameend=False
        p.Playing=False; p.Position=0; p.Composition='full'; p.Speed=1; p.Enabled=True
        p.Resetview.pulse(); p.Resetfx.pulse()
        q['status']='passed' if not q['errors'] else 'failed'
        report={k:v for k,v in q.items() if k not in ('held',)}
        Path(q['path']).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('V5 motion finish QA:',q['status'],len(q['checks']),q['errors'])
    try:
        if stage==0:
            check('Blur and feedback initially OFF',not p.Motionblur and not p.Feedbackenabled)
            p.Playing=False; p.Position=4
        elif stage==1:
            check('Both effects OFF equals clean render',clean())
            p.Motionblur=True; p.Bluramount=1; p.Playing=True
        elif stage==2:
            d=difference(pixels(),pixels('framing')); q['blur_pixel_difference']=d
            check('Motion blur changes moving pixels',d>.0001)
            p.Bluramount=0
        elif stage==3:
            check('Zero blur amount exactly bypasses',clean())
            p.Bluramount=1
        elif stage==4:
            p.Pause.pulse()
        elif stage==5:
            q['held']=pixels()
        elif stage==6:
            check('Pause holds blurred output',difference(pixels(),q['held'])<.00005)
            p.Cleartrails.pulse()
        elif stage==7:
            check('Clear History removes blur while paused',clean())
            p.Motionblur=False; p.Feedbackenabled=True; p.Trailamount=1; p.Trailhalf=.6
            p.Position=4; p.Playing=True
        elif stage==8:
            d=difference(pixels(),pixels('framing')); q['trail_pixel_difference']=d
            check('Feedback changes moving pixels',d>.0001)
            q['forward_history']=c.op('effects_runtime').module.sample(c).copy()
            check('History advances with nonzero time',q['forward_history']['dt']>0)
            p.Playing=False
        elif stage==9:
            q['held']=pixels()
        elif stage==10:
            check('Pause holds feedback output',difference(pixels(),q['held'])<.00005)
            p.Trailamount=.5
        elif stage==11:
            expected=(pixels('blur_select')+pixels('trail_accumulate'))*.5
            check('Feedback Mix slider blends actual pixels',difference(pixels(),expected)<.0002)
            p.Trailamount=0
        elif stage==12:
            check('Zero trail amount exactly bypasses',clean())
            p.Trailamount=1; p.Position=12
        elif stage==13:
            check('Seeking clears previous pose history',clean())
            p.Playing=True
        elif stage==14:
            p.Stop.pulse()
        elif stage==15:
            check('Stop rewinds and clears history',not p.Playing and p.Position==0 and clean())
            p.Go.pulse()
        elif stage==16:
            check('GO still advances with feedback',bool(p.Playing) and 0<float(p.Position)<2)
            p.Playing=False; p.Composition='cropped'
        elif stage==17:
            check('Framing change clears previous composition',clean())
            p.Panx=.1
        elif stage==18:
            check('Pan change clears old framing',clean())
            p.Resetview.pulse()
        elif stage==19:
            check('Reset View clears history',p.Panx==0 and p.Pany==0 and p.Zoom==1 and clean())
            p.Position=4; p.Speed=-1; p.Playing=True
        elif stage==20:
            q['reverse_history']=c.op('effects_runtime').module.sample(c).copy()
            check('Reverse playback supports feedback',float(p.Position)<4 and not q['reverse_history']['clear'])
            p.Speed=0
        elif stage==21:
            q['held']=pixels()
        elif stage==22:
            check('Speed zero holds finished output',difference(pixels(),q['held'])<.00005)
            p.Enabled=False
        elif stage==23:
            check('Preview disabled stays transparent with feedback',float(np.max(abs(pixels())))<.00001)
            p.Enabled=True; p.Playing=False
            p.Bluramount=100; p.Trailamount=100; p.Trailhalf=-1; p.Trailblur=100
            check('Finish numeric limits enforced',p.Bluramount==1 and p.Trailamount==1 and p.Trailhalf==.02 and p.Trailblur==8)
            check('Trail duration bound to shader',abs(float(c.op('trail_accumulate').par.vec0valuex)-.02)<1e-6)
            check('Trail softness bound to shader',float(c.op('trail_accumulate').par.vec0valuey)==8)
            p.Resetfx.pulse()
        elif stage==24:
            check('Reset Motion Finish restores OFF defaults',not p.Motionblur and not p.Feedbackenabled
                  and abs(float(p.Bluramount)-.35)<1e-6 and abs(float(p.Trailamount)-.25)<1e-6
                  and abs(float(p.Trailhalf)-.18)<1e-6 and p.Trailblur==0)
            check('Reset Motion Finish returns clean output',clean())
            errors=[(n.path,str(n.errors())) for n in c.findChildren() if n.errors()]
            q['operator_errors']=errors; check('No v5 operator errors',not errors)
            probe(c,check,q)
            finish(); return
        q['stage']+=1
    except Exception as exc:
        me.parent().op('v5_finish_qa_clock').par.frameend=False
        p.Playing=False
        Path(q['path']).write_text(json.dumps(dict(status='error',error=str(exc),stage=stage,checks=q['checks']),indent=2),encoding='utf-8')
        raise


def probe(c,check,q):
    """Constant history pattern isolates duration/softness from dance changes."""
    folder=c.parent().create(baseCOMP,'v5_finish_shader_probe')
    current=folder.create(constantTOP,'current'); current.par.colorr=0; current.par.colorg=0; current.par.colorb=0
    current.par.outputresolution='custom'; current.par.resolutionw=128; current.par.resolutionh=128
    dat=folder.create(textDAT,'edge_shader')
    dat.text='layout(location=0) out vec4 fragColor; void main(){ float a=step(.5,vUV.x); fragColor=TDOutputSwizzle(vec4(a,a,a,1.)); }'
    edge=folder.create(glslTOP,'edge'); edge.par.pixeldat=dat.name
    current.outputConnectors[0].connect(edge.inputConnectors[0])
    source=folder.create(textDAT,'trail_shader'); source.text=c.op('trail_accumulate_pixel').text
    top=folder.create(glslTOP,'probe'); top.par.pixeldat=source.name; top.par.format='rgba16float'
    current.outputConnectors[0].connect(top.inputConnectors[0]); edge.outputConnectors[0].connect(top.inputConnectors[1])
    top.par.vec0name='uTrail'; top.par.vec0valuex=.1; top.par.vec0valuey=0; top.par.vec0valuez=.1; top.par.vec0valuew=0
    def data():
        top.cook(force=True); return top.numpyArray(delayed=False).copy()
    a=data(); top.par.vec0valuex=1.; b=data()
    check('Trail duration changes rendered retention',float(b[:,:,:3].mean())>float(a[:,:,:3].mean())+.1)
    check('Half-life shader matches 50 percent decay',abs(float(a[64,100,0])-.5)<.002)
    top.par.vec0valuey=4.; soft=data()
    check('Trail Softness slider changes edge pixels',float(np.mean(abs(soft-b)))>.001)
    top.par.vec0valuew=1.; cleared=data()
    check('Clear shader ignores bright history',float(np.max(abs(cleared[:,:,:3])))<.00001)
    q['shader_probe_errors']=str(top.errors())
    check('Finish probe shader compiles',not top.errors())
    folder.allowCooking=False
