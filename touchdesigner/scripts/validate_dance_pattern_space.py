"""Off-air GPU tests for pattern-local Dance Forces; no output/camera startup."""
import json
import math
from pathlib import Path
import runpy
import traceback
import numpy as np

STATE = {}


def start(root):
    if STATE:
        raise ValueError('Pattern-space validation already running')
    STATE['root'] = Path(root)
    STATE['generator'] = validate()
    advance()


def advance():
    try:
        next(STATE['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=1)
    except StopIteration:
        STATE.clear()


def expected(c, uv, aspect):
    """Independent numerical oracle for the renderer's coordinate transform."""
    angle = math.radians(float(c.par.Rotation))
    cosine, sine = math.cos(angle), math.sin(angle)
    rotation = np.array([[cosine, sine], [-sine, cosine]])
    metric = np.array([aspect, 1.])
    scale, stretch = float(c.par.Scale), float(c.par.Stretch)
    local = ((uv-.5)*metric-np.array([float(c.par.Centerx),float(c.par.Centery)]))@rotation.T*scale
    local[...,0] /= stretch
    local_uv = local/metric+.5
    edge = np.minimum(local_uv,1.-local_uv).min(axis=-1)
    weight = np.clip(edge/.06,0.,1.); weight = weight*weight*(3.-2.*weight)
    sampled = np.clip(local_uv,.5/512,1.-.5/512)
    field = np.stack((sampled[...,0]*.08,sampled[...,1]*.05,
                      sampled[...,0]*sampled[...,1]*.11),axis=-1)
    field[...,:2] = (field[...,:2]*np.array([stretch,1.]))@rotation/scale
    return field*weight[...,None], edge


def validate():
    root=STATE['root']; folder=root/'build/dance-forces/pattern-space-20261027'
    folder.mkdir(parents=True,exist_ok=True)
    demo=op('/project1/imagefx_demo'); show=demo.op('show_control'); ext=show.ext.ShowControlExt
    assert ext.engine.state=='stopped' and not ext.tracks and not ext.prepared and not ext._look_edit
    assert not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w)
    original=show.op('show_data').text
    original_look=ext._capture_look(demo,active=False)
    host=op('/project1').create(baseCOMP,'dance_pattern_space_qa')
    page=host.appendCustomPage('Fixture')
    for name in ('Inkdreamenabled','Inkbrushenabled','Inkradialenabled'):
        page.appendToggle(name)[0].val=True
    defs=runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    checks, measurements, errors = {}, {}, []

    def check(name,value):
        checks[name]=bool(value)
        assert value,name

    def pixels(node):
        node.cook(force=True)
        value=node.numpyArray(delayed=False)
        assert value is not None and np.isfinite(value).all(),node.path
        return value.copy()

    def shader(c,name,code,inputs,width=480,height=270):
        dat=c.create(textDAT,name+'_pixel'); dat.text=code
        top=c.create(glslTOP,name); top.par.pixeldat=dat.path
        top.par.glslversion='glsl460'; top.par.format='rgba32float'
        top.par.outputresolution='custom'; top.par.resolutionw=width; top.par.resolutionh=height
        top.par.compilebehavior='stalluntildone'; top.par.errorbehavior='showerror'
        for i,node in enumerate(inputs): node.outputConnectors[0].connect(top.inputConnectors[i])
        return top

    try:
        source=host.create(rampTOP,'input'); source.par.outputresolution='custom'
        source.par.resolutionw=480; source.par.resolutionh=270
        for name in defs['MODULES']:
            c=host.copy(demo.op(name),name=name)
            c.par.Enabled.mode=ParMode.CONSTANT; c.par.Enabled.bindExpr=''; c.par.Enabled=True
            source.outputConnectors[0].connect(c.inputConnectors[0])
            c.par.Autotime=False; c.par.Manualtime=3.7; c.par.Animationspeed=0.
            c.op('animation_clock').module.reset(c,phase=3.7)
            c.par.Feedbackenabled=False; c.par.Mix=1.; c.par.Danceenabled=False
            raw=c.op('dance_forces_switch').inputs[0]; yield
            original_pixels=pixels(raw)
            defs['install'](c,raw,root); yield
            check(name+'/default_pattern',c.par.Dancespace.eval()=='pattern')
            check(name+'/disabled_exact',np.array_equal(original_pixels,pixels(raw)))
            field=shader(c,'field_fixture','layout(location=0) out vec4 fragColor;\nvoid main(){vec2 q=vUV.st;fragColor=TDOutputSwizzle(vec4(.08*q.x,.05*q.y,.11*q.x*q.y,0.));}',[],512,512)
            field.outputConnectors[0].connect(raw.inputConnectors[1])
            c.par.Danceenabled=True; c.par.Dancefadein=0.; c.par.Danceamount=1.
            # This synthetic-field oracle tests coordinate conversion, not the
            # asynchronous recorded-source activation guard (covered separately).
            # Keep its gate stable across the old/new shader comparison.
            row=next(i for i in range(raw.seq.vec.numBlocks) if raw.par[f'vec{i}name'].eval()=='uDanceOutput')
            gate=raw.par[f'vec{row}valuex']; gate_expression=gate.expr
            gate.expr='int(parent().par.Danceenabled)'
            renderer=raw.par.pixeldat.eval(); current=renderer.text
            renderer.text=current.replace(defs['FLOW_HELPER'],defs['LEGACY_FLOW_HELPER']); yield
            legacy=pixels(raw)
            renderer.text=current; c.par.Dancespace='canvas'; yield
            check(name+'/canvas_exact_legacy',np.array_equal(legacy,pixels(raw)))
            probe=shader(c,'material_probe',
                'layout(location=0) out vec4 fragColor;\nuniform vec2 uCenter;\nuniform float uScale,uStretch,uRotation,uCheckUV;\n'+defs['FLOW_HELPER']+
                '\nvoid main(){if(uCheckUV>.5) fragColor=vec4(vUV.st,0.,1.); else fragColor=TDOutputSwizzle(vec4(danceMaterial(vUV.st),1.));}',[c.op('in1_image'),field])
            bindings=(('uDanceOutput',['1.','parent().par.Dancespace.menuIndex']),
                ('uCenter',['parent().par.Centerx','parent().par.Centery']),
                ('uScale',['parent().par.Scale']),('uStretch',['parent().par.Stretch']),
                ('uRotation',['parent().par.Rotation']),('uCheckUV',['1.']))
            probe.seq.vec.numBlocks=len(bindings)
            for i,(uniform,expressions) in enumerate(bindings):
                probe.par[f'vec{i}name']=uniform
                for axis,expression in zip('xyzw',expressions): probe.par[f'vec{i}value{axis}'].expr=expression
            yield
            uv=pixels(probe)[...,:2]; probe.par.vec5valuex=0.
            c.par.Dancespace='pattern'
            measurements[name]={}
            cases=((1.,1.,0.,0.,0.),(4.,1.,0.,0.,0.),(.2,1.,0.,0.,0.),
                   (6.,.25,90.,.35,-.15),(2.7,5.,-72.,-.4,.2),(3.,1.5,37.,.2,-.12))
            for aspect_name,width,height in (('hd',480,270),('panorama',1440,270)):
                source.par.resolutionw=width; source.par.resolutionh=height
                for i,(scale,stretch,rotation,x,y) in enumerate(cases):
                    c.par.Scale=scale; c.par.Stretch=stretch; c.par.Rotation=rotation
                    c.par.Centerx=x; c.par.Centery=y; yield
                    actual=pixels(probe)[...,:3]; oracle,edge=expected(c,uv,width/height)
                    error=float(np.max(np.abs(actual-oracle)))
                    measurements[name][aspect_name+'/'+str(i)]=error
                    check(name+'/'+aspect_name+'/transform/'+str(i),error<2e-5)
                    if np.any(edge<0): check(name+'/'+aspect_name+'/outside/'+str(i),not np.any(actual[edge<0]))
            source.par.resolutionw=480; source.par.resolutionh=270
            c.par.Scale=4.; c.par.Stretch=1.; c.par.Rotation=25.; c.par.Centerx=.2; c.par.Centery=.08
            yield
            affected=pixels(raw); _,edge=expected(c,uv,480/270)
            c.par.Danceenabled=False; yield
            unaffected=pixels(raw)
            delta=np.max(np.abs(affected-unaffected),axis=-1)
            check(name+'/renderer/outside_unchanged',not np.any(delta[edge<-.02]))
            check(name+'/renderer/inside_moves',np.max(delta[edge>.08])>1e-4)
            # Restore the real cached-motion graph and prove coordinate edits
            # neither rewind the dancer nor discard smoothed/material history.
            c.op('dance_motion_out').outputConnectors[0].connect(raw.inputConnectors[1])
            gate.expr=gate_expression
            c.par.Danceenabled=True; c.par.Danceoffset=12.; c.par.Danceresponse=.75
            c.par.Dancecache=str(root/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json')
            runtime=c.op('dance_forces_runtime').module; runtime.reset(c); yield
            pixels(c.op('dance_motion_out'))
            for _ in range(30):
                c.par.Manualtime=float(c.par.Manualtime)+1/30; yield
                pixels(c.op('dance_motion_out'))
            material=pixels(c.op('dance_motion_out')); response=pixels(c.op('dance_response_step'))
            check(name+'/recorded_response',np.abs(response).max()>1e-5)
            phase=runtime.motion_time(c)
            c.par.Scale=2.; c.par.Rotation=-40.; c.par.Centerx=-.3; c.par.Stretch=2.; yield
            check(name+'/edit/material_history',np.array_equal(material,pixels(c.op('dance_motion_out'))))
            check(name+'/edit/response_history',np.array_equal(response,pixels(c.op('dance_response_step'))))
            check(name+'/edit/no_clock_jump',abs(runtime.motion_time(c)-phase)<1e-6)
            check(name+'/renderer/live_scaled_motion',np.isfinite(pixels(raw)).all())
            check(name+'/native/no_errors',not c.errors(recurse=True))
            c.destroy()
        check('main/cues_unchanged',show.op('show_data').text==original)
        check('main/look_unchanged',ext._capture_look(demo,active=False)==original_look)
        check('main/outputs_closed',not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w))
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        host.destroy()
        report=dict(ok=not errors,checks=checks,measurements=measurements,errors=errors,gpu=sysinfo.GPUName)
        (folder/'native-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Pattern-local force checks:',report['ok'],len(checks),errors)
