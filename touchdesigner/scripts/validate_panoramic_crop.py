"""Compare Final Crop recall/GO with projector pixels in an off-air copy."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


class CropChecks:
    def __init__(self,reproduce=False):
        import td
        self.td=td
        self.reproduce=reproduce
        self.original=td.op('/project1/imagefx_demo/show_control')
        runpy.run_path(str(ROOT/'touchdesigner/scripts/validate_show_readiness.py'))['_require_safe_session'](self.original)
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('An ImageFX sandbox already exists')
        self.before=copy.deepcopy(self.original.ext.ShowControlExt.document)
        self.private=ROOT/'.imagefx/shows/current.json'
        self.private_hash=hashlib.sha256(self.private.read_bytes()).hexdigest() if self.private.is_file() else None
        self.task='panoramic-crop-'+uuid.uuid4().hex[:8]
        self.folder=ROOT/'build/task-artifacts'/self.task
        self.folder.mkdir(parents=True)
        self.base=td.op('/project1').create(td.baseCOMP,'imagefx_sandbox')
        self.wall=self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.host=self.base.copy(self.original,name='show_control')
        self.report=dict(ok=False,task=self.task,checks={},measurements=[],hardware_outputs_opened=False)
        self.stage='setup';self.schedule(8)

    def schedule(self,frames=2):
        self.td.run('args[0].step()',self,delayFrames=frames)

    def check(self,name,value):
        self.report['checks'][name]=bool(value)
        if not value:raise AssertionError(name)

    def finish(self,error=None):
        self.host.ext.ShowControlExt.Stopall()
        self.report['main_cues_unchanged']=self.original.ext.ShowControlExt.document==self.before
        after=hashlib.sha256(self.private.read_bytes()).hexdigest() if self.private.is_file() else None
        self.report['private_show_unchanged']=after==self.private_hash
        self.base.destroy()
        self.report['sandbox_removed']=self.td.op('/project1/imagefx_sandbox') is None
        self.report['ok']=not error and all(self.report['checks'].values()) and all(self.report[k] for k in
            ('main_cues_unchanged','private_show_unchanged','sandbox_removed'))
        if error:self.report['error']=error
        output=ROOT/'build/panoramic-crop-fix/native-validation.json'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('PANORAMIC CROP:',self.report['ok'],len(self.report['checks']),error)

    def compare(self,name,deck,expect_match=True):
        import numpy as np
        h,e=self.host,self.host.ext.ShowControlExt
        source=deck.op('out1_image');source.cook(force=True)
        self.reference_source.par.top=source.path
        self.reference.cook(force=True)
        expected=self.reference.numpyArray(delayed=False)[:,:,:3]
        e.UpdateCueRouting();e.UpdateMapping()
        frames=[]
        for i in (1,2,3):
            top=h.op('out'+str(i)+'_projector');top.cook(force=True)
            self.check(name+'_p'+str(i)+'_size',(top.width,top.height)==(320,180))
            frames.append(top.numpyArray(delayed=False)[:,:,:3])
        actual=np.concatenate(frames,axis=1)
        self.check(name+'_finite',np.isfinite(actual).all() and np.isfinite(expected).all())
        self.check(name+'_reference_not_black',expected.max()>.1)
        error=float(np.abs(actual-expected).mean())
        self.report['measurements'].append(dict(case=name,crop_size=(source.width,source.height),mean_error=error,
                                               master_blackout=bool(h.par.Masterblackout)))
        self.check(name+'_matches' if expect_match else name+'_reproduced',error<.012 if expect_match else error>.04)
        self.export_canvas.cook(force=True)
        export_pixels=self.export_canvas.numpyArray(delayed=False)[:,:,:3]
        self.check(name+'_offline_canvas_preserves_crop',np.abs(export_pixels-expected).mean()<.002)

    def step(self):
        try:
            h,e=self.host,self.host.ext.ShowControlExt
            if self.stage=='setup':
                h.par.Renderwidth,h.par.Renderheight=320,180
                h.par.Routingmode='cue';h.par.Outputmode='direct'
                h.par.Masterblackout=False;h.par.Audioenabled=False
                self.wall.par.Enabled=True;self.wall.par.Blackout=False;self.wall.par.Sourcemode='show'
                for i in (1,2,3):
                    h.par['Output'+str(i)+'width'],h.par['Output'+str(i)+'height']=320,180
                    h.par['Output'+str(i)+'blackout']=False
                self.reference_source=self.base.create(self.td.selectTOP,'reference_source')
                self.reference_source.par.top=h.op('black').path
                code=self.base.create(self.td.textDAT,'contain_code')
                code.text=h.op('show_output_mode').module.CUE_MEDIA_SHADER
                self.reference=self.base.create(self.td.glslTOP,'expected_crop_canvas')
                self.reference.par.pixeldat=code.path
                self.reference.par.outputresolution='custom'
                self.reference.par.resolutionw,self.reference.par.resolutionh=960,180
                self.reference.par.vec0name='uFit';self.reference.par.vec0valuex=0
                self.reference_source.outputConnectors[0].connect(self.reference.inputConnectors[0])
                offline=self.base.create(self.td.baseCOMP,'offline_canvas_test')
                selected=offline.create(self.td.selectTOP,'out1_image');selected.par.top=self.reference_source.path
                runtime=self.base.create(self.td.textDAT,'export_runtime')
                runtime.text=(ROOT/'touchdesigner/scripts/show_review_export.py').read_text(encoding='utf-8')
                self.export_canvas=runtime.module.export_render_target(h,offline,
                    dict(panoramic=True,projection=None,width=960,height=180,fit='cover'))
                self.stage='recall';self.schedule(6);return
            if self.stage=='recall':
                look=dict(toggles=dict(Inkdreamenabled=True,Finalcropenabled=True),
                          modules=dict(final_crop=dict(Aspect='free',Left=25.,Right=25.,Top=0.,Bottom=0.,Outputmode='crop')),
                          animation=dict(ink_dream_flow=dict(time=0.,running=False)))
                cue=dict(e.model.new_cue(),name='Panoramic Crop QA',track=1,projection='panoramic',channels='all',
                         duration=0,fade=0,look=look)
                e._replace_cues([cue]);e.SelectCue(1);e.RecallLook();e.ShowLiveLook()
                self.stage='baseline';self.schedule(8);return
            if self.stage=='baseline':
                self.compare('old_stretch' if self.reproduce else 'installed_crop',e._look_edit['deck'],
                             expect_match=not self.reproduce)
                h.op('cue_projection').text=runpy.run_path(str(ROOT/'touchdesigner/scripts/cue_projection.py'))['SHADER']
                self.stage='fixed';self.schedule(4);return
            if self.stage=='fixed':
                self.compare('recalled_horizontal_crop',e._look_edit['deck'])
                self.cases=[('vertical',dict(Left=0,Right=0,Top=25,Bottom=25,Aspect='free',Outputmode='crop')),
                            ('square',dict(Top=0,Bottom=0,Aspect='1x1')),
                            ('mask',dict(Aspect='free',Left=25,Right=25,Outputmode='mask')),
                            ('fit',dict(Outputmode='fit')),
                            ('uncropped',dict(Left=0,Right=0,Outputmode='crop')),
                            ('saved_horizontal',dict(Left=25,Right=25))]
                self.index=0;self.stage='set_case'
            elif self.stage=='set_case':
                crop=e._look_edit['deck'].op('final_crop')
                for key,value in self.cases[self.index][1].items():crop.par[key]=value
                self.stage='check_case';self.schedule(3);return
            elif self.stage=='check_case':
                self.compare('live_'+self.cases[self.index][0],e._look_edit['deck'])
                self.index+=1
                if self.index<len(self.cases):self.stage='set_case'
                else:
                    self.reference.save(str(self.folder/'cropped-panorama.png'))
                    e.UpdateLook();self.stage='go'
                self.schedule(3);return
            elif self.stage=='go':
                # Update Look may reinitialize the native extension after its
                # draft-tree edit; resolve it on this later GUI-equivalent frame
                # and explicitly release only the QA copy's safety blackout.
                h.par.Masterblackout=False
                e.SelectCue(1);e.Go();self.stage='playing';self.deadline=time.monotonic()+60
            elif self.stage=='playing':
                if e.engine.errors:raise RuntimeError(str(e.engine.errors))
                if not e.tracks or e.tracks[1].get('fading'):
                    if time.monotonic()>self.deadline:raise RuntimeError('GO timed out')
                    self.schedule();return
                self.compare('go_saved_crop',e.tracks[1]['deck'])
                self.check('shader_compiles',not any(h.op('cue_projection'+str(i)).errors() for i in (1,2,3)))
                self.wall.par.Enabled=True;self.wall.par.Blackout=False;self.wall.par.Sourcemode='show'
                wall=self.wall.op('out1_wall_4k');wall.cook(force=True)
                pixels=wall.numpyArray(delayed=False)
                self.check('wall_stays_3840x2160',(wall.width,wall.height)==(3840,2160))
                self.report['wall_samples']=[]
                for i,(x,y) in enumerate(((0,1080),(1920,1080),(0,0)),1):
                    source=h.op('out'+str(i)+'_projector').numpyArray(delayed=False)
                    import numpy as np
                    actual=pixels[y:y+1080,x:x+1920,:3].mean(axis=(0,1))
                    expected=source[:,:,:3].mean(axis=(0,1))
                    self.report['wall_samples'].append(dict(projector=i,actual=actual.tolist(),
                        expected=expected.tolist(),enabled=bool(self.wall.par.Enabled),
                        blackout=bool(self.wall.par.Blackout)))
                    self.check('wall_crop_channel_'+str(i),np.allclose(actual,expected,atol=.02))
                self.finish();return
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(reproduce=False):return CropChecks(reproduce)
