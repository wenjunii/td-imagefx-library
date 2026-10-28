"""Focused native regression: preview, solo cues, A/B layers and panorama."""
import copy
import json
from pathlib import Path
import traceback
import numpy as np

RUN={}

def start(root):
    if RUN: raise ValueError('Validation already running')
    RUN.update(root=Path(root),generator=validate())
    advance()

def advance():
    try:
        next(RUN['generator'])
        run("op({!r}).module.advance()".format(me.path),delayFrames=2)
    except StopIteration: RUN.clear()

def validate():
    root=RUN['root']; original=op('/project1/imagefx_demo/show_control')
    before=original.op('show_data').text
    assert original.ext.ShowControlExt.engine.state=='stopped'
    assert original.ext.ShowControlExt._look_edit is None
    qa=original.parent().copy(original,name='puppet_layers_qa')
    qa.op('show_tick').par.active=False; qa.initializeExtensions()
    ext=qa.ext.ShowControlExt; clock=[0.]; checks={}; debug={}; error=None
    def check(name,value):
        checks[name]=bool(value)
        assert value,name
    def pixels(top):
        top.cook(force=True); a=top.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(),top.path
        assert not top.errors(),top.errors()
        return a.copy()
    def tick(dt=0):
        clock[0]+=dt; ext.Tick(); ext.UpdateMapping()
        assert not ext.engine.errors,str(ext.engine.errors)
    def until(predicate):
        for _ in range(900):
            tick(); yield
            if predicate(): return
        raise AssertionError('Timed out waiting for cue')
    try:
        yield
        qa.par.Renderwidth=640; qa.par.Renderheight=360; qa.par.Masterblackout=False
        qa.par.Audioenabled=False; qa.par.Testpattern=False; qa.par.Routingmode='independent'
        for i in (1,2,3):
            qa.par['Output%dwidth'%i]=640; qa.par['Output%dheight'%i]=360
            qa.par['Output%dtrack'%i]=i; qa.par['Output%dblackout'%i]=False
        folder=root/'build/dance-puppet'; data=json.loads((folder/'camera-fixed-separated/status.json').read_text())
        files=dict(Renderfile=data['render'],Fanrenderfile=data['renders']['fan'],Chainrenderfile=data['renders']['chain'],
                   Motioncache=data['motion'],Characterprofile=str(folder/'characters-default.json'),Dancevideo='')
        def cue(mode,track):
            return dict(ext.model.new_cue(),name='QA '+mode,track=track,duration=0,fade=0,
                look={'toggles':{'Dancepuppetenabled':True},'modules':{'dance_puppet':{'Characters':mode,'Composite':False,'Fadein':0.}},
                      'puppet_files':files,'animation':{'dance_puppet':{'time':0.,'running':True}}})
        cues=[cue('both',2),cue('fan',1),cue('chain',3)]
        ext._replace_cues(cues); ext.engine.clock=lambda:clock[0]; ext.engine._last=clock[0]
        ext.engine.go(0); yield from until(lambda:cues[0]['id'] in ext.engine.active)
        p=ext.tracks[2]['deck'].op('dance_puppet')
        both=pixels(p.op('puppet_rgba'))
        check('both_cue_center_track',pixels(qa.op('mapped2'))[:,:,:3].max()>.5)
        check('both_has_alpha',both[:,:,3].min()<.01 and both[:,:,3].max()>.99)
        ext.Stopall(); ext.engine.go(1); ext.engine.go(2)
        yield from until(lambda:all(c['id'] in ext.engine.active for c in cues[1:]))
        fan=ext.tracks[1]['deck'].op('dance_puppet'); chain=ext.tracks[3]['deck'].op('dance_puppet')
        check('solo_files_selected',fan.op('recorded_motion').par.file.eval()==files['Fanrenderfile'] and chain.op('recorded_motion').par.file.eval()==files['Chainrenderfile'])
        check('side_cues_same_phase',float(fan.par.Time)==float(chain.par.Time)==0)
        check('side_characters_distinct',not np.allclose(pixels(fan.op('puppet_rgba')),pixels(chain.op('puppet_rgba'))))
        tick(.5); yield
        check('side_cues_advance_together',float(fan.par.Time)==float(chain.par.Time)==.5)
        ext.Pause(); tick(.5); yield
        check('side_cues_pause_together',float(fan.par.Time)==float(chain.par.Time)==.5)
        ext.Resume(); tick(.2); yield
        check('side_cues_resume_together',abs(float(fan.par.Time)-.7)<.001 and abs(float(chain.par.Time)-.7)<.001)
        ext.Stopall(); ext.SelectCue(2); ext.RecallLook(); yield
        editor=ext._look_edit['deck']; p=editor.op('dance_puppet')
        p.par.Autotime=False; p.par.Manualtime=20.; yield
        p.par.Autotime=True; yield
        check('animate_preview_starts_at_opening',0<=float(p.par.Time)<.5)
        for _ in range(6): yield
        p.par.Pausepreview.pulse(); yield
        held=float(p.par.Time); still=pixels(p.op('puppet_rgba'))
        for _ in range(6): yield
        check('preview_pause_holds_time_and_pixels',held==float(p.par.Time) and np.allclose(still,pixels(p.op('puppet_rgba'))))
        p.par.Resumepreview.pulse(); yield
        check('preview_resume_keeps_phase',held<=float(p.par.Time)<held+.5)
        phase=float(p.par.Time); p.par.Timescale=2.; yield
        check('preview_speed_has_no_jump',phase<=float(p.par.Time)<phase+.5)
        p.par.Restartmotion.pulse(); yield
        check('preview_reset_zero_paused',not p.par.Autotime and float(p.par.Time)==0)
        ext.CancelLook(); ext.SelectCue(1); ext.RecallLook(); yield
        editor=ext._look_edit['deck']
        for name in ext.model.TOGGLES:
            if editor.par[name] is not None: editor.par[name]=False
        layer=editor.op('layer_composite'); composition=editor.op('image_composition')
        layer.par.Setupab.pulse(); yield
        check('setup_ab_selects_both_independent_sources',layer.par.Backdropsource=='effects_a' and layer.par.Topsource=='effects_b' and bool(layer.par.Enabled))
        check('layout_remains_bypassed',not composition.par.Enabled)
        # Independent transparent-canvas procedural effects: A red, B green.
        for prefix,color in [('a',(1.,0.,0.)),('b',(0.,1.,0.))]:
            branch=composition.op(prefix+'_effects')
            for name in ext.model.TOGGLES:
                if branch.par[name] is not None: branch.par[name]=False
            puppet=branch.op('dance_puppet'); branch.par.Dancepuppetenabled=True
            for name,value in files.items(): puppet.par[name]=value
            puppet.par.Characters='fan' if prefix=='a' else 'chain'
            puppet.par.Composite=False; puppet.par.Transparent=False
            puppet.par.Fadein=0.  # Test layer colors/viewport, not entrance opacity.
            for group in ('Bodycolor','Linecolor','Background'):
                for suffix,value in zip('rgb',color): puppet.par[group+suffix]=value
            puppet.par.Autotime=False; puppet.par.Manualtime=0
        layer.par.Opacity=.5; yield
        a=pixels(composition.op('a_effects/out1_image')); b=pixels(composition.op('b_effects/out1_image'))
        output=pixels(layer.op('out1_image'))
        check('independent_a_red',a[:,:,0].mean()>.99 and a[:,:,1].max()<.01)
        check('independent_b_green',b[:,:,1].mean()>.99 and b[:,:,0].max()<.01)
        check('both_effects_composite_pixels',abs(output[:,:,0].mean()-.5)<.02 and abs(output[:,:,1].mean()-.5)<.02)
        captured=ext._capture_look(editor,capture_animation=True)
        check('captured_both_effect_branches',captured['branches']['a_effects']['modules']['dance_puppet']['Characters']=='fan' and captured['branches']['b_effects']['modules']['dance_puppet']['Characters']=='chain')
        ext.model.validate_look_media(captured,project.folder)
        check('branch_movies_preloaded_even_layout_off',len(list(ext._look_readers(editor)))==2)
        # 5760x1080 exact viewport edges. No hardware outputs are opened.
        editor.par.Customwidth=5760; editor.par.Customheight=1080
        layer.par.Opacity=1.; layer.par.Topfit='cover'
        for position,index in [('left',0),('center',1),('right',2)]:
            layer.par.Topcanvas=position; yield
            output=pixels(layer.op('out1_image'))
            check('panorama_resolution/'+position,output.shape[:2]==(1080,5760))
            green=output[:,:,1].mean(axis=0); red=output[:,:,0].mean(axis=0)
            selected=slice(index*1920,(index+1)*1920)
            check('1080_top_exact_region/'+position,green[selected].min()>.99 and np.count_nonzero(green>.5)==1920)
            check('panorama_backdrop_remains/'+position,np.count_nonzero(red>.5)==3840)
            check('top_branch_is_1080/'+position,composition.op('b_effects/out1_image').width==1920 and composition.op('b_effects/out1_image').height==1080)
        layer.par.Topcanvas='full'; yield
        check('full_canvas_default_still_works',pixels(layer.op('out1_image'))[:,:,1].min()>.99)
        code=editor.create(textDAT,'circle_fixture_code')
        code.text='layout(location=0) out vec4 fragColor; void main(){vec2 p=(vUV.st-.5)*vec2(16./9.,1.);fragColor=TDOutputSwizzle(vec4(0.,1.,0.,float(length(p)<.25)));}'
        fixture=editor.create(glslTOP,'circle_fixture'); fixture.par.pixeldat=code.name
        fixture.par.outputresolution='custom'; fixture.par.resolutionw=1920; fixture.par.resolutionh=1080
        fixture.par.compilebehavior='stalluntildone'
        sample=pixels(fixture)
        assert sample[:,:,3].max()>.99, fixture.errors()
        fixture.outputConnectors[0].connect(layer.inputConnectors[1]); layer.par.Topsource='second'
        for position,index in [('left',0),('center',1),('right',2)]:
            layer.par.Topcanvas=position; yield
            output=pixels(layer.op('out1_image')); y,x=np.where(output[:,:,1]>.5)
            assert len(x), {'source':layer.par.Topstatus.eval(),'inputs':[n.path for n in layer.inputs],
                'top_pixels':pixels(layer.op('top_source')).max(axis=(0,1)).tolist(),'fixture':sample.max(axis=(0,1)).tolist()}
            check('no_aspect_distortion/'+position,abs((x.max()-x.min())-(y.max()-y.min()))<=2)
            check('original_1080_circle_size/'+position,abs((x.max()-x.min()+1)-540)<=2 and abs(x.mean()-(index*1920+959.5))<1)
        layer.par.Topsource='effects_b'
        workflow=editor.op('workflow').module; order=workflow.current(editor)
        bad=list(order); bad.remove('image_composition'); bad.append('image_composition')
        workflow.apply_order(editor,bad); yield
        check('cycle_guard_reports_order',layer.par.Topstatus.eval().startswith('ERROR:'))
        pixels(layer.op('out1_image'))
        check('cycle_guard_avoids_cook_error',not editor.errors(recurse=True))
        workflow.apply_order(editor,order); yield
        # Cue update/recall round-trip keeps branch files and viewport selection.
        layer.par.Topcanvas='right'; ext.UpdateLook(); yield
        ext.Stopall(); ext.SelectCue(1); ext.RecallLook(); yield
        restored=ext._look_edit['deck']
        check('cue_recall_keeps_top_viewport',restored.op('layer_composite').par.Topcanvas=='right')
        check('cue_recall_keeps_independent_character',restored.op('image_composition/b_effects/dance_puppet').par.Characters=='chain')
        check('cue_recall_keeps_solo_movie',restored.op('image_composition/b_effects/dance_puppet').par.Chainrenderfile.eval()==files['Chainrenderfile'])
        check('no_native_errors',not qa.errors(recurse=True))
        check('original_cues_unchanged',original.op('show_data').text==before)
        check('no_hardware_windows',not any(w.isOpen for w in qa.op('show_output_mode').module.windows(qa) if w))
    except Exception:
        error=traceback.format_exc(); debug['errors']=qa.errors(recurse=True); debug['status']=qa.par.Status.eval()
    finally:
        ext.Stopall()
        if ext._look_edit is not None: ext.CancelLook()
        qa.destroy()
    result=dict(ok=error is None,checks=checks,error=error,debug=debug)
    (root/'build/dance-puppet/native-puppet-layers-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PUPPET / LAYER QA:',len(checks),'PASS' if error is None else error)
