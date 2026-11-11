"""Native audition checks; does not save projects, arm windows, or play sound."""
from datetime import datetime, timezone
from pathlib import Path
import json
import traceback
import numpy as np

STATE = {}


def validate(c, report_path):
    checks = {}
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(),
                  scope='isolated backdrop audition; not show/hardware certification')
    saved = {p.name:p.eval() for p in c.customPars if not p.isPulse and not p.readOnly}
    warp = c.op('motion_warp')
    size = (warp.par.resolutionw.eval(),warp.par.resolutionh.eval())
    c.op('tick').par.active = False
    c.par.Playing = False
    runtime = c.op('runtime').module

    def setvalues(values):
        for name,value in values.items():
            c.par[name] = value
        runtime.refresh(c)

    def pixels(node=None):
        runtime.refresh(c)
        for shader in (warp,c.op('calligraphic_shadow/effect_glsl_calligraphic_shadow')):
            shader.cook(force=True)
            if shader.errors() or shader.warnings():
                raise RuntimeError(str(shader.errors())+str(shader.warnings()))
        node = node or c.op('out1_image')
        node.cook(force=True)
        data = node.numpyArray(delayed=False)
        if data is None or not np.isfinite(data).all():
            raise RuntimeError('Missing / non-finite rendered pixels')
        return data.copy()

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    try:
        check('full_hd_output',pixels().shape==(1080,1920,4))
        warp.par.resolutionw,warp.par.resolutionh = 384,216
        baseline = dict(saved,Position=17.,Playing=False,Enabled=True,Motionenabled=True,
                        Shadowenabled=True,Debug=False,Useinput=False)
        setvalues(baseline)
        a = pixels()
        check('nonblank_color_image',np.std(a[:,:,:3])>.05 and np.mean(a[:,:,0])>.03)
        c.par.Strength = 0
        b = pixels()
        check('motion_changes_pixels',np.mean(np.abs(a-b))>1e-4)
        setvalues(baseline)
        c.par.Enabled=False
        bypass=pixels()
        c.par.Enabled=True; c.par.Motionenabled=False; c.par.Shadowenabled=False
        check('complete_bypass_unwarped_art',np.max(np.abs(pixels()-bypass))<=1e-6)
        c.par.Enabled=False; c.par.Debug=True
        check('debug_never_leaks_when_disabled',np.max(np.abs(pixels()-bypass))<=1e-6)
        setvalues(baseline)
        c.par.Autotime=False; c.par.Manualtime=.5
        a=pixels(); c.par.Position=31.
        check('pose_changes_independently_of_shader_clock',np.mean(np.abs(a-pixels()))>1e-4)
        setvalues(baseline)
        c.par.Position=8.; c.par.Timescale=2.
        check('auto_time_follows_clip_clock',abs(float(c.par.Time)-16.)<1e-6)
        c.par.Autotime=False; c.par.Manualtime=3.
        check('manual_time_remains_available',float(c.par.Time)==3.)
        setvalues(baseline)
        c.par.Dancer1=0.; c.par.Dancer2=0.; pixels()
        check('both_dancers_off_zero_motion',float(c.par.Energy1)==0 and float(c.par.Energy2)==0 and
              all(warp.par[f'vec{i+3}value{axis}'].eval()==0 for i in range(12) for axis in 'zw'))
        setvalues(baseline)
        before=pixels()
        c.par.Debug=True
        check('diagnostic_points_visible',np.mean(np.abs(before-pixels()))>1e-5)
        # Every actual editable numeric component, including RGB/alpha values.
        endpoints={}
        for par in c.customPars:
            if not par.isNumber or par.isToggle or par.isMenu or par.isPulse or par.readOnly:
                continue
            endpoints[par.name]=[]
            for endpoint in (float(par.min),float(par.max)):
                setvalues(baseline)
                par.val=endpoint
                arr=pixels()
                accepted=abs(float(par.eval())-endpoint)<1e-5
                endpoints[par.name].append(bool(accepted and np.isfinite(arr).all()))
            check('endpoint_'+par.name,all(endpoints[par.name]))
        report['numeric_endpoints']=endpoints
        for par in c.customPars:
            if par.isMenu:
                for choice in par.menuNames:
                    setvalues(baseline); par.val=choice
                    check('menu_'+par.name+'_'+choice,np.isfinite(pixels()).all() and par.eval()==choice)
            elif par.isToggle and not par.readOnly:
                if par.name == 'Useinput':
                    # A connected input is supplied for the alternate-source test.
                    source=c.parent().create(constantTOP,'backdrop_test_source')
                    source.par.colorr=.1; source.par.colorg=.8; source.par.colorb=.3
                    source.outputConnectors[0].connect(c.inputConnectors[0])
                for value in (False,True):
                    setvalues(baseline); par.val=value
                    check('toggle_'+par.name+'_'+str(value),np.isfinite(pixels()).all() and bool(par.eval())==value)
                if par.name == 'Useinput':
                    setvalues(baseline)
                    c.inputConnectors[0].disconnect()
                    source.destroy()
        setvalues(baseline)
        c.par.Strength=.35
        c.par.Resetmotion.pulse()
        # Dispatch may be deferred; actual pulses are checked below on frames.
        check('all_shadow_controls_promoted',all(c.par[p.name] is not None for p in c.op('calligraphic_shadow').customPars if p.name!='Enabled'))
        check('no_recursive_errors_or_warnings',not c.errors(recurse=True) and not c.warnings(recurse=True))
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        setvalues(saved)
        c.par.Playing=False
        warp.par.resolutionw,warp.par.resolutionh=size
        c.op('tick').par.active=True
        report['checks']=checks
        Path(report_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Backdrop native checks:',report['ok'],len(checks),report.get('error',''))
    return report


def start_events(c, report_path):
    """Call from a Text DAT, allowing real Parameter Execute/frame callbacks."""
    global STATE
    if STATE.get('running'):
        raise RuntimeError('Backdrop event checks already running')
    STATE=dict(running=True,c=c,path=str(report_path),checks={},stage=0,
               saved={p.name:p.eval() for p in c.customPars if not p.isPulse and not p.readOnly})
    c.par.Playing=False
    c.par.Playbackspeed=1.
    c.par.Loop=False
    later()


def later():
    run('op({!r}).module.events()'.format(me.path),delayFrames=10)


def events():
    s=STATE; c=s['c']; p=c.par; stage=s['stage']; checks=s['checks']

    def require(name,condition):
        checks[name]=bool(condition)
        if not condition:
            raise AssertionError(name)

    try:
        if stage==0:
            p.Go.pulse()
        elif stage==1:
            require('go_advances_clip',p.Playing and float(p.Position)>0)
            p.Pause.pulse()
        elif stage==2:
            require('pause_stops_transport',not p.Playing)
            s['paused']=float(p.Position)
            s['image']=c.op('out1_image').numpyArray(delayed=False).copy()
        elif stage==3:
            require('paused_clock_and_pixels_frozen',float(p.Position)==s['paused'] and np.array_equal(s['image'],c.op('out1_image').numpyArray(delayed=False)))
            p.Pause.pulse()
        elif stage==4:
            require('resume_advances',p.Playing and float(p.Position)>s['paused'])
            p.Stop.pulse()
        elif stage==5:
            require('stop_rewinds',not p.Playing and float(p.Position)==0.)
            p.Position=17.; p.Setreference.pulse()
        elif stage==6:
            require('reference_pose_button',float(p.Referencepose)==17.)
            p.Strength=.2; p.Mirror=True; p.Resetmotion.pulse()
        elif stage==7:
            require('reset_motion_button',float(p.Strength)==p.Strength.default and not p.Mirror)
            s['data']=c.op('motion_data').text
            p.Motionfile=''; p.Reloadmotion.pulse()
        elif stage==8:
            require('bad_reload_keeps_embedded_motion',c.op('motion_data').text==s['data'] and 'REJECTED' in p.Status.eval())
            p.Reloadmedia.pulse()
        elif stage==9:
            require('media_reload_decodes',c.op('backdrop_file').isOpen and c.op('reference_video').isOpen)
            p.Playbackspeed=-1.; p.Go.pulse()
        elif stage==10:
            require('reverse_go_plays_from_end',p.Playing and float(p.Position)>float(p.Duration)-3.)
            p.Playbackspeed=1.; p.Loop=True; p.Position=float(p.Duration)-.02
        elif stage==11:
            require('loop_crosses_boundary',p.Playing and float(p.Position)<3.)
            p.Stop.pulse()
        elif stage==12:
            require('events_clean',not c.errors(recurse=True) and not c.warnings(recurse=True))
            finish(True)
            return
        s['stage']+=1
        later()
    except Exception:
        finish(False,traceback.format_exc())


def finish(ok,error=None):
    s=STATE; c=s['c']
    for name,value in s['saved'].items():
        c.par[name]=value
    c.par.Playing=False
    c.op('runtime').module.refresh(c)
    result=dict(ok=ok,checks=s['checks'],error=error,generated_at=datetime.now(timezone.utc).isoformat())
    Path(s['path']).write_text(json.dumps(result,indent=2),encoding='utf-8')
    s['running']=False
    print('Backdrop event checks:',ok,len(s['checks']),error or '')
