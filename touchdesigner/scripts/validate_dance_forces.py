"""Off-air native pixel/clock/cue tests. Never starts a camera or changes cues."""
import copy
import json
from pathlib import Path
import runpy
import traceback
import numpy as np

STATE = {}


def start(root):
    # Current builds integrate motion inside the flow renderer. Keep the old
    # warp checks below only for diagnosing older, not-yet-migrated TOEs.
    if op('/project1/imagefx_demo/ink_dream_flow/dance_motion_step') is not None:
        driver=op('/project1/dance_advection_validation') or op('/project1').create(textDAT,'dance_advection_validation')
        driver.text=(Path(root)/'touchdesigner/scripts/validate_dance_advection.py').read_text(encoding='utf-8')
        driver.module.start(root)
        return
    if STATE: raise ValueError('Validation already running')
    STATE['root']=Path(root); STATE['generator']=validate(); advance()


def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path),delayFrames=2)
    except StopIteration: STATE.clear()


def validate():
    root=STATE['root']; folder=root/'build/dance-forces'; folder.mkdir(exist_ok=True)
    demo=op('/project1/imagefx_demo'); show=demo.op('show_control'); ext=show.ext.ShowControlExt
    original=show.op('show_data').text
    assert ext.engine.state=='stopped' and not ext.tracks and not ext.prepared
    host=op('/project1').create(baseCOMP,'dance_forces_qa')
    toggles=host.appendCustomPage('Fixture')
    for name in ('Inkdreamenabled','Inkbrushenabled','Inkradialenabled','Dancepuppetenabled'):
        toggles.appendToggle(name)[0].val=True
    defs=runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    checks={}; effects={}; failures=[]
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise AssertionError(name)
    def pixels(node):
        node.cook(force=True)
        a=node.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(),node.path
        assert not node.errors(),node.errors()
        return a.copy()
    def error(a,b): return float(np.mean(np.abs(a-b)))
    try:
        t=np.arange(240)/30
        frames=np.zeros((240,2,6,3)); frames[...,2]=.95
        for actor in range(2):
            for j in range(6):
                frames[:,actor,j,0]=.32+actor*.3+np.sin(t*(1.1+j*.2)+j)*.075
                frames[:,actor,j,1]=.28+j*.075+np.cos(t*(.9+j*.15)+j)*.06
        cache=folder/'synthetic-motion.json'
        cache.write_text(json.dumps(dict(kind='tdimagefx.dance-forces.motion',schema_version=1,fps=30,
            frames=frames.tolist(),camera_motion={'removed':True})),encoding='utf-8')
        source=host.create(constantTOP,'input'); source.par.outputresolution='custom'
        source.par.resolutionw=320; source.par.resolutionh=180
        source.par.colorr=.24; source.par.colorg=.12; source.par.colorb=.05
        for name in defs['MODULES']:
            c=host.copy(demo.op(name),name=name)
            c.par.Enabled.mode=ParMode.CONSTANT; c.par.Enabled.bindExpr=''; c.par.Enabled=True
            source.outputConnectors[0].connect(c.inputConnectors[0])
            for _,p,kind,default,*_ in defs['PARAMETERS']:
                if kind not in {'pulse','str'} and p!='Danceduration': c.par[p]=default
            c.par.Autotime=False; c.par.Manualtime=3.7; c.par.Feedbackenabled=False; c.par.Mix=1.
            c.op('animation_clock').module.reset(c,phase=3.7)
            c.par.Dancecache=str(cache); c.par.Dancefadein=0
            c.store('dance_force_clock',dict(raw=0.,phase=0.,speed=1.)); c.store('dance_force_activation',0.)
            output=c.op('out1_image'); raw=c.op('dance_forces_switch').inputs[0]
            yield
            check(name+'/off_exact',np.array_equal(pixels(output),pixels(raw)))
            c.par.Danceenabled=True; yield
            base=pixels(output); legacy=pixels(raw)
            check(name+'/movement_pixels',error(base,legacy)>1e-5)
            effects[name]={'difference':error(base,legacy)}
            base_params={p:c.par[p].eval() for _,p,kind,*_ in defs['PARAMETERS'] if kind not in {'pulse','str'} and p!='Danceduration'}
            # All spatial/filter sliders: individual, visible pixel differences.
            values={'Danceamount':.2,'Dancestrength':3.,'Danceradius':.65,'Dancepush':0.,'Danceswirl':-2.,
                'Dancesmooth':.8,'Dancedecay':2.5,'Dancethreshold':.25,'Danceconfidence':1.,
                'Dancebody':0.,'Dancehands':0.,'Dancefeet':0.,'Danceactor1':0.,'Danceactor2':0.,
                'Dancezoom':.5,'Dancepanx':.4,'Dancepany':.3,'Dancemirror':True,'Danceoffset':2.}
            for p,v in values.items():
                c.par[p]=v; yield
                changed=pixels(output)
                check(name+'/'+p,error(base,changed)>1e-7)
                c.par[p]=base_params[p]; yield
            for _,p,kind,default,lo,hi,_ in defs['PARAMETERS']:
                if kind in {'float','int'} and p!='Danceduration':
                    old=c.par[p].eval()
                    for v in (lo,hi):
                        c.par[p]=v
                        check(name+'/'+p+'/accepts/'+str(v),abs(float(c.par[p])-v)<1e-6)
                    c.par[p]=old
            c.par.Dancefadein=2.; c.store('dance_force_activation',3.7); yield
            start_pixels=pixels(output); start_raw=pixels(raw)
            effects[name]['fade_start']=dict(difference=error(start_pixels,start_raw),time=float(c.par.Time),
                activation=c.fetch('dance_force_activation'),force=c.op('dance_forces_runtime').module.sample(c),
                duration=float(c.par.Dancefadein))
            check(name+'/fade_start_exact',np.allclose(start_pixels,start_raw,atol=1e-5))
            # Hold the dance/pattern phase while measuring only the fade gain.
            c.store('dance_force_activation',2.7); c.op('dance_forces_runtime').module._sample_key=None; yield
            half=pixels(output)
            c.store('dance_force_activation',1.7); c.op('dance_forces_runtime').module._sample_key=None; yield
            full=pixels(output)
            check(name+'/fade_midpoint',error(half,legacy)>0 and error(half,legacy)<error(full,legacy))
            c.par.Dancefadein=0.; c.par.Dancerestart.pulse(); yield
            check(name+'/restart_zero',abs(c.op('dance_forces_runtime').module.motion_time(c)-float(c.par.Danceoffset))<1e-6)
            c.par.Manualtime=4.7; yield
            before=c.op('dance_forces_runtime').module.motion_time(c)
            c.par.Dancespeed=2.; yield
            check(name+'/speed_continuity',abs(before-c.op('dance_forces_runtime').module.motion_time(c))<1e-6)
            c.par.Manualtime=5.7; yield
            check(name+'/speed_progress',abs(before+2-c.op('dance_forces_runtime').module.motion_time(c))<1e-6)
            c.par.Dancecache='missing-motion.json'; yield
            check(name+'/missing_is_neutral',np.array_equal(pixels(output),pixels(raw)))
            check(name+'/missing_visible_status',''!=c.par.Dancestatus.eval())
            c.par.Dancesource='live'; yield
            check(name+'/live_not_started',np.array_equal(pixels(output),pixels(raw)))
            c.par.Dancesource='recorded'; c.par.Dancecache=str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json')
            c.par.Dancespeed=1.; yield
            c.store('dance_force_clock',dict(raw=0.,phase=0.,speed=1.)); c.par.Manualtime=12.; yield
            real=pixels(output)
            effects[name]['real_clip']=dict(status=c.par.Dancestatus.eval(),time=float(c.par.Time),
                motion_time=c.op('dance_forces_runtime').module.motion_time(c),
                force=c.op('dance_forces_runtime').module.sample(c),difference=error(real,pixels(raw)))
            check(name+'/real_clip_finite',np.isfinite(real).all())
            check(name+'/real_clip_reacts',error(real,pixels(raw))>1e-6)
            output.save(str(folder/(name+'-dance-forces.png')))
            check(name+'/no_errors',not c.errors(recurse=True))
        # Cue capture/recall on a disposable copy, including independent A/B.
        deck=host.copy(show.op('deck_template'),name='cue_test')
        deck.allowCooking=True; deck.op('fx_rack').initializeExtensions(); yield
        look=ext._capture_look(demo,active=False,capture_animation=True)
        look['toggles']['Inkdreamenabled']=True
        look['modules']['ink_dream_flow'].update(Danceenabled=True,Dancefadein=2.,Dancestrength=2.3,Danceoffset=10.)
        look['force_files']['ink_dream_flow']={'Dancecache':str(cache),'Dancevideo':''}
        ext._apply_look(deck,look); yield
        c=deck.op('ink_dream_flow')
        check('cue/files_restored',c.par.Dancecache.eval()==str(cache))
        check('cue/values_restored',float(c.par.Dancestrength)==2.3 and float(c.par.Dancefadein)==2.)
        check('cue/start_at_inpoint',abs(c.op('dance_forces_runtime').module.motion_time(c)-10.)<1e-6)
        c.par.Manualtime=float(c.par.Manualtime)+1.; yield
        check('cue/clock_advances',abs(c.op('dance_forces_runtime').module.motion_time(c)-11.)<1e-6)
        captured=ext._capture_look(deck,active=False,capture_animation=True)
        check('cue/capture_files',captured['force_files']['ink_dream_flow']['Dancecache']==str(cache))
        c.par.Dancestrength=3.; ext._restore_running_values(deck,captured); yield
        check('cue/discard_running_edit',float(c.par.Dancestrength)==2.3)
        check('cue/cancel_keeps_phase',abs(c.op('dance_forces_runtime').module.motion_time(c)-11.)<1e-6)
        puppet_look=ext._capture_look(demo,active=False,capture_animation=True)
        puppet_look['toggles']['Dancepuppetenabled']=True
        puppet_look['modules']['dance_puppet']['Fadein']=2.
        ext._apply_look(deck,puppet_look); yield
        cue_puppet=deck.op('dance_puppet')
        cue_runtime=cue_puppet.op('puppet_runtime').module
        check('puppet/cue_go_starts_zero',cue_runtime.fade_gain(cue_puppet)==0.)
        cue_puppet.par.Manualtime=float(cue_puppet.par.Manualtime)+1.; yield
        check('puppet/cue_halfway',abs(cue_runtime.fade_gain(cue_puppet)-.5)<1e-6)
        # Puppet alpha fade after feedback, using the existing prepared movie.
        p=host.copy(demo.op('dance_puppet'),name='puppet_test')
        p.par.Enabled.mode=ParMode.CONSTANT; p.par.Enabled.bindExpr=''; p.par.Enabled=True
        source.outputConnectors[0].connect(p.inputConnectors[0])
        p.par.Autotime=False; p.par.Manualtime=2.; p.par.Transparent=True; p.par.Opacity=1.; p.par.Fadein=2.
        p.par.Feedbackenabled=True; p.par.Trailamount=.7
        p.par.Renderfile=str(root/'build/dance-puppet/integration-default/puppet-alpha.mov')
        p.store('puppet_fade_start',2.); yield
        alpha0=pixels(p.op('puppet_rgba'))[:,:,3]
        p.store('puppet_fade_start',1.); yield
        alphaHalf=pixels(p.op('puppet_rgba'))[:,:,3]
        p.store('puppet_fade_start',0.); yield
        alpha1=pixels(p.op('puppet_rgba'))[:,:,3]
        check('puppet/fade_zero',float(alpha0.max())<1e-6)
        check('puppet/fade_half',float(alphaHalf.max())>.1 and np.allclose(alphaHalf,alpha1*.5,atol=.002))
        p.par.Fadein=0.; p.store('puppet_fade_start',2.); yield
        check('puppet/instant_option',np.allclose(pixels(p.op('puppet_rgba'))[:,:,3],alpha1,atol=.002))
        p.par.Fadein=2.; p.par.Enabled=False; p.par.Enabled=True; yield
        check('puppet/retrigger_fade',p.op('puppet_runtime').module.fade_gain(p)==0.)
        rt=p.op('puppet_runtime').module
        p.par.Manualtime=.6; p.store('puppet_fade_start',0.); yield
        before=rt.fade_gain(p)
        p.par.Resumepreview.pulse(); yield
        check('puppet/resume_keeps_fade',rt.fade_gain(p)>=before)
        p.par.Pausepreview.pulse(); yield
        paused=rt.fade_gain(p); yield
        check('puppet/pause_holds_fade',abs(rt.fade_gain(p)-paused)<1e-6)
        p.par.Autotime=True; yield
        check('puppet/animate_preview_restarts_fade',rt.fade_gain(p)<.1)
        p.par.Pausepreview.pulse(); yield
        check('original_cues_unchanged',show.op('show_data').text==original)
        check('audience_windows_closed',not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception:
        failures.append(traceback.format_exc())
    finally:
        report=dict(ok=not failures and all(checks.values()),checks=checks,effects=effects,errors=failures,gpu=sysinfo.GPUName)
        (folder/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        host.destroy()
        print('Dance Forces validation:',report['ok'],len(checks),'checks',failures)
