"""Normal-frame pixel tests for independent A/B edits inside cue Look Editor."""
import copy
import json
from pathlib import Path
import traceback
import runpy

ROOT=Path(__file__).resolve().parents[2]


class LayerPreviewChecks:
    def __init__(self,patch=False):
        import td
        self.td=td
        self.original=td.op('/project1/imagefx_demo/show_control')
        e=self.original.ext.ShowControlExt
        if e.engine.state!='stopped' or e._look_edit is not None:
            raise RuntimeError('Stop All and finish the current Look Editor before the off-air test')
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('Existing sandbox must not be overwritten')
        self.before=copy.deepcopy(e.document)
        self.before_main_invert=float(self.original.parent().op('image_composition/a_effects/color_adjustment').par.Invert)
        self.base=td.op('/project1').create(td.baseCOMP,'imagefx_sandbox')
        self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.host=self.base.copy(self.original,name='show_control')
        self.host.op('show_tick').par.active=False
        self.ext=self.host.ext.ShowControlExt
        if patch:
            install=runpy.run_path(str(ROOT/'touchdesigner/scripts/layer_composite.py'))['install_independent_sources']
            template=self.host.op('deck_template')
            previous=template.allowCooking
            template.allowCooking=True
            try: install(template.op('layer_composite'))
            finally: template.allowCooking=previous
        self.report=dict(ok=False,patched=patch,checks={},samples={},hardware_outputs_opened=False)
        self.patch=patch
        self.has_controls=self.host.op('deck_template/layer_composite').par['Aenable'] is not None
        self.stage='recall'; self.prefix='A'
        self.schedule(8)

    def schedule(self,frames=2):
        self.td.run('args[0].step()',self,delayFrames=frames)

    def check(self,name,value):
        self.report['checks'][name]=bool(value)
        if not value: raise AssertionError(name)

    def sample(self,node):
        import numpy as np
        a=node.numpyArray(delayed=False)
        if a is None or not np.isfinite(a).all(): raise AssertionError('Unusable output: '+node.path)
        return a[a.shape[0]//2,a.shape[1]//2,:].copy()

    def finish(self,error=None):
        self.report['original_cues_preserved']=self.original.ext.ShowControlExt.document==self.before
        self.report['ok']=error is None and self.report['original_cues_preserved']
        if error:
            self.report['error']=error
            self.report['debug']={
                'branch':self.prefix,'stage':self.stage,
                # The edited deck is intentionally deleted by UpdateLook.
                # Never dereference its cached OPs while reporting a later error.
                'transport':self.host.par.Transport.eval(),
                'status':self.host.par.Status.eval(),
                'errors':self.host.errors(recurse=True),
            }
        self.base.destroy()
        target=ROOT/'build/layer-preview/native-validation.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('Layer Preview:',self.report['ok'],len(self.report['checks']),error)

    def step(self):
        import numpy as np
        try:
            e,h=self.ext,self.host
            if self.stage=='recall':
                h.par.Renderwidth,h.par.Renderheight=160,90
                look=dict(toggles={'Layercompositeenabled':True},modules={
                    'layer_composite':{'Backdropsource':'effects_a','Topsource':'transparent'},
                    'image_composition':{'Avisible':True,'Bvisible':True}},branches={
                    p+'_effects':dict(toggles={'Coloradjustmentenabled':True},modules={'color_adjustment':{'Invert':0.}})
                    for p in ('a','b')})
                e._replace_cues([dict(e.model.new_cue(),look=look,fade=0,duration=0)])
                e.SelectCue(1);e.RecallLook()
                self.deck=e._look_edit['deck'];self.layer=self.deck.op('layer_composite')
                fixture=self.deck.create(self.td.constantTOP,'layer_preview_fixture')
                fixture.par.colorr,fixture.par.colorg,fixture.par.colorb=.2,.4,.7
                fixture.par.outputresolution='custom';fixture.par.resolutionw,fixture.par.resolutionh=160,90
                fixture.outputConnectors[0].connect(self.deck.op('source_image').inputConnectors[0])
                fixture.outputConnectors[0].connect(self.deck.op('image_composition').inputConnectors[1])
                self.deck.op('source_image').par.index=0
                self.stage='baseline'
            elif self.stage=='baseline':
                self.layer.par[self.prefix+'module']='color_adjustment'
                self.target=self.layer.op('media_status').module.edit_target(self.layer,self.prefix,'color_adjustment')
                self.check(self.prefix+'_target_stays_in_recalled_deck',self.target.path.startswith(self.deck.path+'/'))
                self.check(self.prefix+'_module_enabled',bool(self.target.par.Enabled))
                if self.has_controls:
                    self.target.par.Enabled=False
                    self.check(self.prefix+'_status_reports_bypass','OFF / BYPASSED' in self.layer.par[self.prefix+'status'].eval())
                    self.layer.par[self.prefix+'enable'].pulse()
                    self.stage='enabled'
                else:
                    self.stage='edit'
            elif self.stage=='enabled':
                self.check(self.prefix+'_enable_button_enables_only_selected_module',bool(self.target.par.Enabled))
                self.check(self.prefix+'_enable_retains_two_way_binding',str(self.target.par.Enabled.mode).lower().endswith('bind'))
                self.check(self.prefix+'_enable_updates_branch_switch',bool(self.target.parent().par.Coloradjustmentenabled))
                self.check(self.prefix+'_status_reports_live_route','ON' in self.layer.par[self.prefix+'status'].eval() and 'used as backdrop' in self.layer.par[self.prefix+'status'].eval())
                self.stage='edit'
            elif self.stage=='edit':
                self.before_pixel=self.sample(h.op('look_preview'))
                self.report['samples'][self.prefix+'_before']=[float(v) for v in self.before_pixel]
                self.target.par.Invert=1.
                self.stage='edited'
            elif self.stage=='edited':
                pixel=self.sample(h.op('look_preview'))
                self.report['samples'][self.prefix+'_after']=[float(v) for v in pixel]
                branch=self.deck.op('image_composition/'+self.prefix.lower()+'_effects/out1_image')
                self.report['samples'][self.prefix+'_branch']=[float(v) for v in self.sample(branch)]
                self.check(self.prefix+'_edit_changes_full_look_preview',float(np.max(np.abs(pixel-self.before_pixel)))>.1)
                self.check(self.prefix+'_invert_reaches_preview',np.allclose(pixel[:3],1.-self.before_pixel[:3],atol=.04))
                other=self.deck.op('image_composition/'+('b' if self.prefix=='A' else 'a')+'_effects/color_adjustment')
                if self.prefix=='A':
                    self.check('A_edit_does_not_change_B',float(other.par.Invert)==0.)
                    self.prefix='B';self.layer.par.Backdropsource='effects_b';self.stage='baseline'
                else:
                    self.check('original_workflow_not_edited',float(self.original.parent().op('image_composition/a_effects/color_adjustment').par.Invert)==self.before_main_invert)
                    self.prefix='A';self.layer.par.Backdropsource='effects_a'
                    self.deck.op('image_composition/a_effects/color_adjustment').par.Enabled=False
                    self.flows=iter(('ink_dream_flow','ink_brush_flow','ink_radial_flow'))
                    self.stage='flow'
            elif self.stage=='flow':
                if hasattr(self,'flow'): self.flow.par.Enabled=False
                name=next(self.flows,None)
                if name is None:
                    e.UpdateLook();self.stage='after_update'
                else:
                    self.layer.par.Amodule=name
                    self.flow=self.layer.op('media_status').module.edit_target(self.layer,'A')
                    self.layer.par.Aenable.pulse()
                    self.flow.par.Scale=.2
                    self.stage='flow_baseline'
            elif self.stage=='flow_baseline':
                self.check(self.flow.name+'_enabled_by_button',bool(self.flow.par.Enabled))
                self.check(self.flow.name+'_parent_switch_enabled',bool(self.flow.parent().par[e.model.MODULE_TOGGLES[self.flow.name]]))
                self.check(self.flow.name+'_two_way_binding_retained',str(self.flow.par.Enabled.mode).lower().endswith('bind'))
                self.before_flow=np.array(h.op('look_preview').numpyArray(delayed=False),copy=True)
                self.flow.par.Scale=6.
                self.stage='flow_edit'
            elif self.stage=='flow_edit':
                after=h.op('look_preview').numpyArray(delayed=False)
                delta=float(np.mean(np.abs(after-self.before_flow)))
                self.report['samples'][self.flow.name+'_scale_change_delta']=delta
                self.check(self.flow.name+'_scale_changes_full_preview',delta>.002)
                self.stage='flow'
            elif self.stage=='after_update':
                # These are separate GUI actions on separate rendered frames.
                # UpdateLook deletes the draft network; TD may re-init the
                # stopped extension. Resolve it just as the GO button does.
                self.ext=h.ext.ShowControlExt
                e=self.ext
                self.check('update_keeps_saved_cue_and_closes_draft',len(e.document['cues'])==1 and e._look_edit is None)
                e.SelectCue(1);e.Go();self.wait=0;self.stage='go'
            elif self.stage=='go':
                e.Tick();self.wait+=1
                self.check('go_has_no_cue_errors',not e.engine.errors)
                if e.engine.active and not e.tracks[1].get('fading'):
                    e.SelectCue(1);e.EditRunningLook()
                    self.deck=e._look_edit['deck'];self.layer=self.deck.op('layer_composite')
                    self.layer.par.Amodule='color_adjustment'
                    self.layer.par.Aenable.pulse()
                    self.target=self.layer.op('media_status').module.edit_target(self.layer,'A')
                    self.target.par.Invert=0.
                    self.stage='live_baseline'
                elif self.wait>600: raise AssertionError('GO timeout')
            elif self.stage=='live_baseline':
                e.Tick()
                self.before_flow=np.array(h.op('look_preview').numpyArray(delayed=False),copy=True)
                self.target.par.Invert=1.
                self.stage='live_edit'
            elif self.stage=='live_edit':
                e.Tick()
                after=h.op('look_preview').numpyArray(delayed=False)
                self.check('running_cue_A_edits_change_live_preview',float(np.mean(np.abs(after-self.before_flow)))>.03)
                self.check('preview_has_no_native_errors',not self.deck.errors(recurse=True))
                self.finish();return
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(patch=False):
    return LayerPreviewChecks(patch)
