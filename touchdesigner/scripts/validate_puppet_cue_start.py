"""Off-air GO/replay checks using the generated AV fixture, or explicit movies."""
import copy
import json
from pathlib import Path
import runpy
import traceback

ROOT=Path(__file__).resolve().parents[2]


class PuppetCueStartChecks:
    def __init__(self,patch=False,files=None):
        import td
        self.td=td
        self.original=td.op('/project1/imagefx_demo/show_control')
        e=self.original.ext.ShowControlExt
        if e.engine.state!='stopped' or e._look_edit is not None:
            raise RuntimeError('Stop All and finish Look Editor before validation')
        if td.op('/project1/imagefx_sandbox') is not None: raise RuntimeError('Sandbox already exists')
        self.before=copy.deepcopy(e.document)
        self.base=td.op('/project1').create(td.baseCOMP,'imagefx_sandbox')
        self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.host=self.base.copy(self.original,name='show_control')
        if patch: runpy.run_path(str(ROOT/'touchdesigner/scripts/install_puppet_cue_start.py'))['install'](self.host)
        self.host.op('show_tick').par.active=False
        self.ext=self.host.ext.ShowControlExt
        self.report=dict(ok=False,patched=patch,checks={},samples={},hardware_outputs_opened=False)
        self.clock=100.
        self.files=files
        self.index=0;self.stage='setup';self.wait=0
        self.schedule(8)

    def schedule(self,frames=2):
        self.td.run('args[0].step()',self,delayFrames=frames)

    def check(self,name,value):
        self.report['checks'][name]=bool(value)
        if not value: raise AssertionError(name)

    def module(self):
        deck=self.ext.tracks[1]['deck']
        path=('dance_puppet','image_composition/a_effects/dance_puppet','image_composition/b_effects/dance_puppet')[self.index]
        return deck.op(path)

    def pixels(self):
        import numpy as np
        p=self.module();p.op('recorded_motion').par.frametimeout=5000
        a=p.op('recorded_motion').numpyArray(delayed=False)
        self.check(self.label+'_finite_decoded_frame',a is not None and np.isfinite(a).all())
        return np.array(a,copy=True)

    def finish(self,error=None):
        self.report['original_cues_preserved']=self.original.ext.ShowControlExt.document==self.before
        self.report['ok']=error is None and self.report['original_cues_preserved']
        if error: self.report['error']=error
        self.ext.Stopall();self.base.destroy()
        path=ROOT/'build/puppet-cue-start/native-validation.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('Puppet Cue Start:',self.report['ok'],len(self.report['checks']),error)

    def step(self):
        import numpy as np
        try:
            e,h=self.ext,self.host
            if self.stage=='setup':
                h.par.Renderwidth,h.par.Renderheight=320,180
                h.par.Audioenabled=False;h.par.Masterblackout=True
                files=self.files or dict.fromkeys(('Renderfile','Fanrenderfile','Chainrenderfile'),
                    str(ROOT/'build/envoy-validation/show-av-fixture.mp4'))
                for path in files.values():
                    if not Path(path).is_file(): raise RuntimeError('Generate the AV fixture before puppet cue validation')
                self.cues=[]
                for index,location in enumerate(('main','A','B')):
                    child=dict(toggles={'Dancepuppetenabled':True},puppet_files=files,
                        modules={'dance_puppet':dict(Sourcemode='recorded',Composite=False,Fadein=0.,Timescale=.5,
                                                    Offset=1.25 if index==1 else 0.,Feedbackenabled=True)},
                        animation={'dance_puppet':dict(time=34.,running=False)})
                    look=child if index==0 else dict(toggles={'Layercompositeenabled':True},modules={
                        'layer_composite':dict(Backdropsource='effects_a' if index==1 else 'transparent',
                                               Topsource='effects_b' if index==2 else 'transparent')},
                        animation={'image_composition':dict(time=300.,running=False)},
                        branches={('a_effects' if index==1 else 'b_effects'):child})
                    look.setdefault('animation',{})['ink_dream_flow']=dict(time=71.,running=False)
                    self.cues.append(dict(e.model.new_cue(),name='QA '+location,track=1,duration=0,fade=0,
                                          projection='p2',channels='2',look=look))
                self.cues.append(dict(e.model.new_cue(),name='QA next',duration=0,fade=0))
                e._replace_cues(self.cues)
                e.engine.clock=lambda:self.clock;e.engine._last=self.clock
                self.stage='begin'
            elif self.stage=='begin':
                self.label=('main','A','B')[self.index]
                e.Stopall();e.SelectCue(self.index+1);e.Go();self.wait=0;self.stage='ready'
            elif self.stage in ('ready','forward','back'):
                e.Tick();self.wait+=1
                wanted=self.index+1 if self.stage=='forward' else self.index
                item=e.tracks.get(1)
                if item and item['cue']['id']==self.cues[wanted]['id'] and not item.get('fading'):
                    if self.stage=='forward':
                        e.GoBack();self.stage='back';self.wait=0
                    elif self.stage=='back':
                        self.check(self.label+'_go_back_restarts_clock',abs(float(self.module().par.Time))<1e-6)
                        self.check(self.label+'_go_back_decodes_same_opening',np.allclose(self.pixels(),self.opening,atol=.01))
                        finished=self.module().op('puppet_rgba').numpyArray(delayed=False)
                        self.check(self.label+'_go_back_clears_previous_feedback',np.allclose(finished,self.opening_finished,atol=.01))
                        deck=item['deck'];export=h.op('show_review_export').module
                        export._set_time(deck,e.model.MODULES,2.)
                        self.check(self.label+'_export_same_zero_based_speed',abs(float(self.module().par.Time)-1.)<1e-6)
                        self.index+=1
                        if self.index==3:
                            self.check('no_native_errors_or_warnings',not h.errors(recurse=True) and not h.warnings(recurse=True))
                            self.finish();return
                        self.stage='begin'
                    else:
                        p=self.module()
                        self.check(self.label+'_go_starts_at_zero_not_saved_phase',abs(float(p.par.Time))<1e-6)
                        self.check(self.label+'_motion_inpoint_preserved',abs(float(p.op('recorded_motion').par.index)-float(p.par.Offset))<1e-6)
                        self.check(self.label+'_speed_preserved',float(p.par.Timescale)==.5)
                        self.check(self.label+'_other_effect_phase_preserved',float(item['deck'].op('ink_dream_flow').par.Manualtime)==71.)
                        self.opening=self.pixels()
                        self.opening_finished=np.array(p.op('puppet_rgba').numpyArray(delayed=False),copy=True)
                        self.clock+=4.;e.Tick();self.stage='advanced'
                elif self.wait>900: raise AssertionError('Timed out: '+self.stage)
            elif self.stage=='advanced':
                self.check(self.label+'_cue_drives_motion',abs(float(self.module().par.Time)-2.)<1e-6)
                self.check(self.label+'_decoded_animation_advances',float(np.mean(np.abs(self.pixels()-self.opening)))>.0001)
                e.Pause();self.held=self.pixels();self.clock+=5.;e.Tick();self.stage='paused'
            elif self.stage=='paused':
                self.check(self.label+'_pause_holds_time',abs(float(self.module().par.Time)-2.)<1e-6)
                self.check(self.label+'_pause_holds_pixels',np.allclose(self.pixels(),self.held,atol=.01))
                e.Resume();self.clock+=2.;e.Tick();self.stage='resumed'
            elif self.stage=='resumed':
                self.check(self.label+'_resume_continues_not_restarts',abs(float(self.module().par.Time)-3.)<1e-6)
                e.SelectCue(self.index+2);e.Go();self.wait=0;self.stage='forward'
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(patch=False,files=None):
    return PuppetCueStartChecks(patch,files)
