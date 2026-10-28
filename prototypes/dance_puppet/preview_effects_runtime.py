"""V5 finite blur / trail history timing, embedded in a Text DAT."""
import math

KEY='puppet_v5_history'


def retention(dt,half_life):
    if not math.isfinite(dt+half_life) or dt<0 or half_life<=0:
        raise ValueError('Finite nonnegative elapsed time and positive half-life required')
    return math.pow(.5,dt/half_life)


def history_state(previous,frame,now,position,playing,speed,style,clear_until=-1):
    """Pure decision function: no history from another seek, look or run."""
    elapsed=0. if previous is None else max(0.,now-previous['now'])
    delta=0. if previous is None else position-previous['position']
    clear=(previous is None or frame<=clear_until or style!=previous['style']
           or frame-previous['frame']>4 or elapsed>.25
           or abs(delta)>max(.10,abs(speed)*elapsed*3+.03)
           or (speed>0 and delta<-.001) or (speed<0 and delta>.001))
    hold=not playing or abs(speed)<1e-8
    return dict(frame=frame,now=now,position=position,style=style,clear=clear,
                hold=hold,dt=0. if hold or clear else elapsed)


def clear(component):
    component.store('puppet_v5_clear_until',int(absTime.frame)+3)
    component.storeStartupValue('puppet_v5_clear_until',None)
    component.store(KEY,None)
    component.storeStartupValue(KEY,None)
    component.store('puppet_clock_change',None)
    component.storeStartupValue('puppet_clock_change',None)


def sample(component):
    p=component.par
    style=(p.Composition.eval(),float(p.Zoom),float(p.Panx),float(p.Pany),
           bool(p.Enabled),bool(p.Motionblur and p.Bluramount>0),
           bool(p.Feedbackenabled and p.Trailamount>0),float(p.Speed))
    stamp=(int(absTime.frame),float(p.Position),bool(p.Playing),style)
    previous=component.fetch(KEY,None,search=False)
    if previous is not None and previous.get('stamp')==stamp: return previous
    until=component.fetch('puppet_v5_clear_until',-1,search=False)
    until=-1 if until is None else until
    # Parameter evaluations can happen both before and after the playback clock
    # in one TD frame. Recompute from the preceding frame, not a zero-time
    # intermediate evaluation in the current frame.
    base=previous
    if previous is not None and previous['frame']==int(absTime.frame):
        base=previous.get('frame_previous')
    state=history_state(base,int(absTime.frame),float(absTime.seconds),
                        float(p.Position),bool(p.Playing),float(p.Speed),style,until)
    state['stamp']=stamp
    state['frame_previous']=None if base is None else {k:base[k] for k in ('frame','now','position','style')}
    component.store(KEY,state)
    component.storeStartupValue(KEY,None)
    return state


def clock_change_matches(previous,current,clock):
    # Parameter Execute DAT callbacks are deferred and their previous value is
    # float32, so a temporary in-tick flag alone cannot identify clock writes.
    return (clock is not None and previous is not None
            and abs(float(previous)-clock['before'])<1e-5
            and abs(float(current)-clock['after'])<1e-5)


def changed(component,name,previous=None):
    if name=='Position':
        clock=component.fetch('puppet_clock_change',None,search=False)
        if component.fetch('puppet_internal_tick',False,search=False) or clock_change_matches(previous,float(component.par.Position),clock):
            component.store('puppet_clock_change',None)
            return
    clear(component)


def action(component,name):
    if name=='Resetfx':
        p=component.par
        p.Motionblur=False; p.Bluramount=.35
        p.Feedbackenabled=False; p.Trailamount=.25; p.Trailhalf=.18; p.Trailblur=0.
    if name in ('Go','Stop','Resetview','Cleartrails','Resetfx'):
        clear(component)
