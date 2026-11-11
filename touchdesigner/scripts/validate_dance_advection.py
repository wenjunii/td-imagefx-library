"""Off-air GPU tests of dancer-driven material motion (not canvas warping)."""
import json
from pathlib import Path
import runpy
import traceback
import numpy as np

STATE={}

def start(root):
    if STATE: raise ValueError('Validation already running')
    STATE['root']=Path(root); STATE['generator']=validate(); advance()

def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path),delayFrames=1)
    except StopIteration: STATE.clear()

def validate():
    root=STATE['root']; folder=root/'build/dance-forces/advection-20261027'
    folder.mkdir(parents=True,exist_ok=True)
    demo=op('/project1/imagefx_demo'); show=demo.op('show_control'); ext=show.ext.ShowControlExt
    original=show.op('show_data').text
    assert ext.engine.state=='stopped' and not ext.tracks and not ext.prepared
    host=op('/project1').create(baseCOMP,'dance_advection_qa')
    page=host.appendCustomPage('Fixture')
    for n in ('Inkdreamenabled','Inkbrushenabled','Inkradialenabled'): page.appendToggle(n)[0].val=True
    defs=runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    checks={}; measurements={}; failures=[]
    def check(name,value):
        checks[name]=bool(value)
        if not value: raise AssertionError(name)
    def pixels(node):
        node.cook(force=True)
        a=node.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(),node.path
        assert not node.errors(),node.errors()
        return a.copy()
    def difference(a,b): return float(np.mean(np.abs(a-b)))
    def tick(c,frames=12):
        for i in range(frames):
            c.par.Manualtime=float(c.par.Manualtime)+1/30
            yield
            pixels(c.op('out1_image'))
    def force(top,x=.12,y=0.):
        for i in range(12):
            for axis,v in zip('xyzw',(.5,.5,x if i==0 else 0.,y if i==0 else 0.)):
                top.par[f'vec{i+1}value{axis}']=v
    try:
        source=host.create(rampTOP,'input')
        source.par.outputresolution='custom'; source.par.resolutionw=480; source.par.resolutionh=270
        for name in defs['MODULES']:
            c=host.copy(demo.op(name),name=name)
            c.par.Enabled.mode=ParMode.CONSTANT; c.par.Enabled.bindExpr=''; c.par.Enabled=True
            source.outputConnectors[0].connect(c.inputConnectors[0])
            c.par.Autotime=False; c.par.Manualtime=3.7; c.par.Animationspeed=0.
            c.par.Feedbackenabled=False; c.par.Mix=1.; c.par.Danceenabled=False
            c.op('animation_clock').module.reset(c,phase=3.7)
            raw=c.op('dance_forces_switch').inputs[0]
            # Reference before migration includes every original shader operation.
            yield
            legacy=pixels(raw)
            defs['install'](c,raw,root)
            yield
            output=c.op('out1_image'); runtime=c.op('dance_forces_runtime').module
            check(name+'/disabled_original_pixels',np.array_equal(legacy,pixels(raw)))
            step=c.op('dance_motion_step'); state=c.op('dance_motion_out')
            # These checks exercise the original analytic advection path. The
            # separate response validator checks nonzero delay and easing.
            c.par.Danceresponse=0.
            c.par.Danceenabled=True; c.par.Dancefadein=0.; c.par.Danceswirl=0.; c.par.Danceacceleration=0.
            force(step); runtime.reset_flow(c); yield
            pixels(output)
            check(name+'/starts_with_zero_field',np.max(np.abs(pixels(state)))==0.)
            yield from tick(c,24)
            right=pixels(state); changed=pixels(raw)
            check(name+'/rightward_velocity',right[67,120,0]>.01)
            check(name+'/flow_moves_at_frozen_base_time',difference(legacy,changed)>1e-5)
            measurements[name]={'foreground_change':difference(legacy,changed),'right_center':right[67,120,:3].tolist()}
            held=pixels(state); held_image=pixels(raw)
            yield; pixels(output); yield
            check(name+'/pause_holds_state',np.array_equal(held,pixels(state)))
            check(name+'/pause_holds_image',np.array_equal(held_image,pixels(raw)))
            yield from tick(c,4)
            check(name+'/resume_advances',difference(held,pixels(state))>1e-6)
            force(step,x=-.12); runtime.reset_flow(c); yield; pixels(output)
            yield from tick(c,24)
            left=pixels(state)
            check(name+'/leftward_velocity',left[67,120,0]<-.01)
            c.par.Dancepush=0.; c.par.Danceswirl=0.; c.par.Danceacceleration=1.
            runtime.reset_flow(c); yield; pixels(output)
            yield from tick(c,12)
            speed=pixels(state)
            check(name+'/speed_without_displacement',np.max(np.abs(speed[:,:,:2]))==0. and speed[:,:,2].max()>.01)
            check(name+'/speed_changes_flow',difference(legacy,pixels(raw))>1e-5)
            c.par.Danceacceleration=0.; c.par.Dancepush=1.; force(step)
            runtime.reset_flow(c); yield; pixels(output)
            yield from tick(c,12)
            # Source pixels and paper remain stationary with moving force history.
            toggles=('Liquidenabled','Particlesenabled','Patternenabled','Glitterenabled','Staticglitterenabled','Particlefieldenabled')
            saved={n:c.par[n].eval() for n in toggles}
            for n in toggles: c.par[n]=False
            for background in ('source','paper'):
                c.par.Background=background; yield
                still=pixels(raw); yield from tick(c,12)
                check(name+'/'+background+'_not_warped',np.array_equal(still,pixels(raw)))
            for n,v in saved.items(): c.par[n]=v
            c.par.Background='transparent'; c.par.Particlefieldenabled=True; c.par.Fieldspeed=0.
            yield
            grains=pixels(raw); yield from tick(c,12)
            check(name+'/particle_positions_move',difference(grains[:,:,3],pixels(raw)[:,:,3])>1e-5)
            c.par.Danceenabled=False; yield
            shader=raw.par.pixeldat.eval(); current=shader.text
            off=pixels(raw); shader.text=c.op('dance_forces_original_shader').text; yield
            check(name+'/off_after_history_matches_legacy',np.array_equal(off,pixels(raw)))
            shader.text=current; c.par.Particlefieldenabled=saved['Particlefieldenabled']; c.par.Background='paper'
            # Every numeric UI range still accepts both endpoints.
            for _,p,kind,default,lo,hi,_ in defs['PARAMETERS']:
                if kind in {'float','int'} and p!='Danceduration':
                    old=c.par[p].eval()
                    for v in (lo,hi):
                        c.par[p]=v
                        check(name+'/'+p+'/'+str(v),abs(float(c.par[p])-v)<1e-6)
                    c.par[p]=old
            # Restore real tracked motion (no analysis or camera launch).
            c.par.Danceenabled=True; c.par.Dancepush=1.; c.par.Danceswirl=.6; c.par.Danceacceleration=1.
            c.par.Dancecache=str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json')
            c.par.Danceoffset=12.; c.par.Dancefadein=0.
            for i in range(12):
                for axis,j in zip('xyzw',range(4)):
                    step.par[f'vec{i+1}value{axis}'].expr=f"parent().op('dance_forces_runtime').module.sample(parent())[{i}][{j}]"
            yield
            runtime.reset(c); yield; pixels(output)
            start=pixels(raw); yield from tick(c,30)
            check(name+'/real_recording_reacts',difference(start,pixels(raw))>1e-6)
            measurements[name]['recording_change']=difference(start,pixels(raw))
            raw.save(str(folder/(name+'-advection.png')))
            c.par.Dancerestart.pulse(); yield; pixels(output)
            check(name+'/restart_clears_history',np.max(np.abs(pixels(state)))==0.)
            check(name+'/restart_at_inpoint',abs(runtime.motion_time(c)-12.)<1e-6)
            # Confirm the material field remains small at production resolutions.
            for w,h in ((1920,1080),(3840,2160),(5760,1080)):
                source.par.resolutionw=w; source.par.resolutionh=h; yield
                result=pixels(raw)
                check(name+'/resolution/'+str(w),result.shape[:2]==(h,w))
                check(name+'/bounded_field/'+str(w),state.height==135 and state.width==round(135*w/h))
            source.par.resolutionw=480; source.par.resolutionh=270
            check(name+'/native_errors',not c.errors(recurse=True))
            c.destroy()
        check('original_cues_unchanged',show.op('show_data').text==original)
        check('audience_windows_closed',not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception: failures.append(traceback.format_exc())
    finally:
        report=dict(ok=not failures and all(checks.values()),checks=checks,measurements=measurements,errors=failures,gpu=sysinfo.GPUName)
        (folder/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        host.destroy()
        print('Dance material advection:',report['ok'],len(checks),'checks',failures)
