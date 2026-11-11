"""Native A/B editor, alpha trail and Show Control layout regression.

Uses disposable deck copies; never opens outputs, audio, cameras or saves TOE.
"""
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
    original=op('/project1/imagefx_demo/show_control')
    before=original.op('show_data').text
    assert original.ext.ShowControlExt.engine.state=='stopped'
    assert original.ext.ShowControlExt._look_edit is None
    qa=op('/project1').copy(original.op('deck_template'),name='layer_editing_feedback_qa')
    qa.allowCooking=True
    checks={}; samples={}; error=None
    def check(name,value):
        checks[name]=bool(value)
        assert value,name
    def pixels(node):
        node.cook(force=True); image=node.numpyArray(delayed=False)
        assert image is not None and np.isfinite(image).all(),node.path
        assert not node.errors(),node.errors()
        return image.copy()
    def old_pixel(layer):
        image=pixels(layer.op('out1_image'))
        return image[image.shape[0]//2,image.shape[1]//4]
    try:
        yield
        qa.par.Customwidth=320; qa.par.Customheight=180
        for name in original.ext.ShowControlExt.model.TOGGLES:
            if qa.par[name] is not None: qa.par[name]=False
        layer=qa.op('layer_composite')
        layer.par.Setupab.pulse(); yield
        check('setup_button_enables_layer',bool(layer.par.Enabled) and bool(qa.par.Layercompositeenabled))
        check('setup_button_selects_independent_sources',layer.par.Backdropsource=='effects_a' and layer.par.Topsource=='effects_b')
        status=layer.op('media_status').module
        for prefix in ('A','B'):
            branch=qa.op('image_composition/'+prefix.lower()+'_effects')
            menu=layer.par[prefix+'module']
            for name,path,label in status.edit_targets(layer):
                menu.val=name
                target=status.edit_target(layer,prefix)
                expected=branch if path=='.' else branch.op(path)
                check(prefix+'_'+name+'_scoped',target==expected and target.path.startswith(branch.path))
            try: status.edit_target(layer,prefix,'../../imagefx_demo')
            except ValueError: rejected=True
            else: rejected=False
            check(prefix+'_invalid_target_rejected',rejected)
            for name in ('module','edit','workflow','preview'):
                check(prefix+'_'+name+'_enabled',layer.par[prefix+name].enable)
            for name in ('edit','workflow','preview'):
                check(prefix+'_'+name+'_pulse_dispatch',prefix+name in layer.op('media_callbacks').par.pars.eval().split())
        a=qa.op('image_composition/a_effects/color_adjustment'); b=qa.op('image_composition/b_effects/color_adjustment')
        # Editing actual branch values must neither cross to the other branch
        # nor change the main workflow. Use a shared standard grading control.
        parameter=next(p.name for p in a.customPars if not p.readOnly and p.isFloat and p.name not in ('Time','Manualtime'))
        original_b=b.par[parameter].eval(); a.par[parameter]=a.par[parameter].min
        check('branch_values_independent',b.par[parameter].eval()==original_b)
        for branch in ('a_effects','b_effects'):
            nested=qa.op('image_composition/'+branch+'/layer_composite')
            check(branch+'_recursive_editor_disabled',not nested.par.Amodule.enable and not nested.par.Bedit.enable)

        layer.par.Backdropsource='transparent'; layer.par.Topsource='effects_b'
        branch=qa.op('image_composition/b_effects')
        for name in original.ext.ShowControlExt.model.TOGGLES:
            if branch.par[name] is not None: branch.par[name]=False
        puppet=branch.op('dance_puppet'); puppet.par.Enabled=True; puppet.par.Composite=False
        puppet.par.Monochrome=False; puppet.par.Transparent=True; puppet.par.Autotime=False
        puppet.par.Fadein=0.  # The analytic trail oracle excludes entrance fade.
        puppet.par.Manualtime=0.; puppet.par.Time.expr='me.par.Manualtime'
        code=puppet.create(textDAT,'qa_shader')
        code.text='layout(location=0) out vec4 fragColor; uniform float phase; void main(){float x=phase<.025?.25:.75; float a=float(abs(vUV.s-x)<.04&&abs(vUV.t-.5)<.1); fragColor=TDOutputSwizzle(vec4(0.,1.,0.,a));}'
        fixture=puppet.create(glslTOP,'qa_fixture'); fixture.par.pixeldat=code.name
        fixture.par.outputresolution='custom'; fixture.par.resolutionw=320; fixture.par.resolutionh=180
        fixture.par.compilebehavior='stalluntildone'; fixture.par.vec0name='phase'; fixture.par.vec0valuex.expr='parent().par.Time'
        fixture.outputConnectors[0].connect(puppet.op('puppet_style').inputConnectors[0])
        for opaque in (False,True):
            puppet.par.Transparent=not opaque; puppet.par.Feedbackenabled=True
            puppet.par.Trailamount=.25; puppet.par.Trailhalf=1.; puppet.par.Trailsoftness=0
            puppet.par.Backgroundr=0.; puppet.par.Backgroundg=0.; puppet.par.Backgroundb=0.
            puppet.par.Manualtime=0.; puppet.par.Clearhistory.pulse(); yield
            old_pixel(layer); yield
            sequence=[]
            for phase in (.05,.10,.15,.20):
                puppet.par.Manualtime=phase; yield
                pixel=old_pixel(layer); sequence.append(pixel.tolist())
                expected=.25*2**(-phase)
                actual=pixel[1] if opaque else pixel[3]
                check(('opaque' if opaque else 'transparent')+'_trail_'+str(phase),abs(float(actual)-expected)<.015)
            samples['opaque' if opaque else 'transparent']=sequence
        puppet.par.Transparent=True
        previous=old_pixel(layer); yield; yield
        check('paused_trail_holds',np.allclose(old_pixel(layer),previous,atol=.005))
        puppet.par.Trailamount=.5; yield
        samples['amount_change']=dict(before=previous.tolist(),after=old_pixel(layer).tolist(),clock=puppet.fetch('puppet_finish_clock',None,search=False))
        check('amount_adjusts_without_clearing',abs(float(old_pixel(layer)[3])-float(previous[3])*2)<.01 and previous[3]>.1)
        puppet.par.Trailhalf=.5; puppet.par.Manualtime=.7; yield
        check('half_life_uses_elapsed_seconds',abs(float(old_pixel(layer)[3])-.25*2**(-.2))<.015)
        puppet.par.Trailamount=0.; yield
        check('zero_amount_exact_current_frame',float(old_pixel(layer)[3])<.001)
        puppet.par.Feedbackenabled=False; puppet.par.Trailamount=.5; yield
        check('disabled_feedback_has_no_old_alpha',float(old_pixel(layer)[3])<.001)
        puppet.par.Feedbackenabled=True; puppet.par.Manualtime=0.; puppet.par.Clearhistory.pulse(); yield
        old_pixel(layer); yield
        puppet.par.Manualtime=.1; yield; old_pixel(layer); yield
        puppet.par.Clearhistory.pulse(); yield
        check('clear_history_removes_trail',float(old_pixel(layer)[3])<.001)
        check('feedback_target_is_accumulator',puppet.op('puppet_history').par.top.eval()==puppet.op('puppet_trail_accum'))

        # Native scope strings must select one real page, with no crowded tabs.
        nav=original.op('inspector_navigation'); inspector=original.op('cue_inspector')
        selected=nav.par.Section.eval()
        try:
            for section in nav.par.Section.menuNames:
                nav.par.Section=section; yield
                check('page_'+section,inspector.par.pagescope.eval()==repr(section) and section in [p.name for p in original.customPages])
            check('single_page_no_crowded_tabs',not inspector.par.pagenames.eval())
        finally: nav.par.Section=selected
        boxes=original.op('show_panel_layout').module.rectangles()
        for name,box in boxes.items():
            node=(next((n for n in original.children if n.fetch('show_action',None,search=False)==name[7:]),None)
                  if name.startswith('action:') else original.op(name))
            check('layout_'+name,node is not None and tuple(int(node.par[x]) for x in 'xywh')==box)
        check('new_nodes_no_errors',not puppet.errors(recurse=True) and not layer.errors(recurse=True))
    except Exception: error=traceback.format_exc()
    finally: qa.destroy()
    checks['original_cues_preserved']=original.op('show_data').text==before
    report=dict(ok=error is None and all(checks.values()),checks=checks,samples=samples,error=error)
    (RUN['root']/'build/dance-puppet/layer-editing-feedback.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('LAYER EDITING / FEEDBACK QA',report['ok'],len(checks),error)
