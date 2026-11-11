"""Real off-air channel files and panoramic pixels in an isolated show copy."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


class ProjectionExportChecks:
    def __init__(self, patch=True):
        import td
        self.td = td
        self.original = td.op('/project1/imagefx_demo/show_control')
        original = self.original.ext.ShowControlExt
        if original.engine.state != 'stopped' or original._look_edit is not None:
            raise RuntimeError('Stop All and finish Look Editor before validation')
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('Sandbox is already in use')
        self.before = copy.deepcopy(original.document)
        self.show_path = ROOT/'.imagefx/shows/current.json'
        self.show_hash = hashlib.sha256(self.show_path.read_bytes()).hexdigest() if self.show_path.is_file() else None
        self.task = 'projection-export-' + uuid.uuid4().hex[:8]
        self.folder = ROOT/'build/task-artifacts'/self.task
        self.folder.mkdir(parents=True)
        self.base = td.op('/project1').create(td.baseCOMP,'imagefx_sandbox')
        self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.host = self.base.copy(self.original,name='show_control')
        if patch:
            runpy.run_path(str(ROOT/'touchdesigner/scripts/install_projection_export.py'))['install'](self.host)
        self.host.op('show_tick').par.active = False
        self.ext = self.host.ext.ShowControlExt
        self.runtime = self.host.op('show_review_export').module
        self.report = dict(ok=False, checks={}, exports=[], task=self.task, patched=patch,
                           hardware_outputs_opened=False)
        self.index = 0
        self.stage = 'setup'
        self.schedule(6)

    def schedule(self, frames=2):
        self.td.run('args[0].step()',self,delayFrames=frames)

    def check(self, name, value):
        self.report['checks'][name] = bool(value)
        if not value:
            raise AssertionError(name)

    def finish(self, error=None):
        if self.host.fetch(self.runtime.JOB_KEY,None,search=False):
            self.runtime.finish_export(self.host,'CANCELLED')
        self.report['main_cues_unchanged'] = self.original.ext.ShowControlExt.document == self.before
        after_hash = hashlib.sha256(self.show_path.read_bytes()).hexdigest() if self.show_path.is_file() else None
        self.report['user_show_json_unchanged'] = after_hash == self.show_hash
        self.base.destroy()
        self.report['sandbox_removed'] = self.td.op('/project1/imagefx_sandbox') is None
        self.report['ok'] = not error and all(self.report['checks'].values()) and all(self.report[k] for k in
            ('main_cues_unchanged','user_show_json_unchanged','sandbox_removed'))
        if error:
            self.report['error'] = error
        path = ROOT/'build/projection-export/native-validation.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('Projection export:',self.report['ok'],len(self.report['checks']),error)

    def step(self):
        try:
            h,e,r = self.host,self.ext,self.runtime
            if self.stage == 'setup':
                self.check('new_channel_menu_available',set(h.par.Exportchannels.menuNames)==set(dict(r.EXPORT_CHANNELS)))
                self.check('legacy_canvas_remains_default',h.par.Exportchannels.eval()=='canvas')
                h.par.Renderwidth,h.par.Renderheight = 320,180
                h.par.Routingmode,h.par.Cuemediafit = 'identical','auto'
                h.par.Exportfolder = str(self.folder/'exports')
                h.par.Exportresolution = 'custom'
                h.par.Exportwidth,h.par.Exportheight = 320,180
                h.par.Exportfps,h.par.Exportduration,h.par.Exportstart = '30',.2,0
                code=self.base.create(self.td.textDAT,'bands_code')
                code.text='layout(location=0) out vec4 fragColor; void main(){ int i=int(vUV.x*3.); vec3 c=i==0?vec3(1,0,0):i==1?vec3(0,1,0):vec3(0,0,1); fragColor=TDOutputSwizzle(vec4(c,1)); }'
                source=self.base.create(self.td.glslTOP,'bands')
                source.par.pixeldat=code.name
                source.par.outputresolution='custom'
                source.par.resolutionw,source.par.resolutionh=960,180
                source.cook(force=True)
                self.media=self.folder/'bands.png'
                source.save(str(self.media))
                self.cases=[('pair','p1_p3','routing','cue',(1,3),'mjpeg'),
                            ('panorama','panoramic','all','cue',(1,2,3),'mjpeg'),
                            ('center_slice','panoramic','all','2',(2,),'mjpeg'),
                            ('pair_panorama','panoramic','1_3','cue',(1,3),'h264'),
                            ('hd3','panoramic','all','cue',(1,2,3),'h264'),
                            ('square','panoramic','all','2',(2,),'mjpeg'),
                            ('canvas','panoramic','all','canvas',(),'mjpeg')]
                self.stage='begin'
            elif self.stage == 'begin':
                name,route,channels,selection,outputs,codec=self.cases[self.index]
                h.par.Renderwidth,h.par.Renderheight = (1920,1080) if name=='hd3' else (320,180)
                h.par.Exportwidth,h.par.Exportheight = (1920,1080) if name=='hd3' else (320,320) if name=='square' else (320,180)
                cue=dict(e.model.new_cue(),name='Channel export '+name,track=3,projection=route,
                         channels=channels,source=str(self.media),duration=0,fade=0,look={})
                e._replace_cues([cue]);e.SelectCue(1)
                h.par.Exportsource,h.par.Exportchannels,h.par.Exportcodec='cue',selection,codec
                r.start_export(h)
                self.deadline=time.monotonic()+90
                self.sampled=False
                self.stage='export'
            elif self.stage == 'export':
                name,route,channels,selection,outputs,codec=self.cases[self.index]
                job=h.fetch(r.JOB_KEY,None,search=False)
                if job:
                    if time.monotonic()>self.deadline:
                        raise RuntimeError('Export timed out')
                    if job['index']>=1 and not self.sampled:
                        self.sampled=True
                        if outputs:
                            self.check(name+'_one_writer_per_channel',len(job['writers'])==len(outputs))
                            expected=e.model.cue_render_width(job['cue'],'identical',int(h.par.Renderwidth),0)
                            self.check(name+'_original_cue_canvas',int(job['deck'].par.Customwidth)==expected)
                            if name in ('panorama','center_slice'):
                                for channel,target in zip(outputs,job['targets']):
                                    pixels=target.numpyArray(delayed=False)
                                    mean=pixels[:,:,:3].mean(axis=(0,1))
                                    self.check(name+'_projector_'+str(channel)+'_correct_slice',int(mean.argmax())==channel-1 and mean[channel-1]>.95)
                            if name=='square':
                                pixels=job['targets'][0].numpyArray(delayed=False)
                                ys,xs=(pixels[:,:,1]>.8).nonzero()
                                self.check('square_letterboxes_without_stretch',len(xs)>0 and xs.max()-xs.min()+1==320 and ys.max()-ys.min()+1==180)
                            if name=='hd3':
                                self.check('three_1080p_gpu_encoders',len(job['writers'])==3 and all(
                                    writer.par.videocodec.eval() in ('h264','h264nvgpu') for writer in job['writers']))
                        self.check(name+'_native_no_errors',not job['deck'].errors(recurse=True))
                    self.schedule();return
                self.check(name+'_completed',h.par.Exportstatus.eval().startswith('COMPLETE'))
                self.check(name+'_frames_sampled',self.sampled)
                result=Path(h.par.Exportresult.eval())
                if outputs:
                    manifest=json.loads((result/'export.json').read_text())
                    self.check(name+'_manifest_channels',set(manifest['files'])=={str(i) for i in outputs})
                    self.check(name+'_manifest_frames',manifest['frames']==6 and manifest['fps']==30)
                    files=[result/manifest['files'][str(i)] for i in outputs]
                else:
                    files=[result]
                self.check(name+'_all_files_nonempty',all(path.is_file() and path.stat().st_size>0 for path in files))
                self.report['exports'].append(dict(case=name,files=[str(p) for p in files],status=h.par.Exportstatus.eval()))
                self.index+=1
                if self.index==len(self.cases):
                    self.check('show_stays_stopped',e.engine.state=='stopped')
                    self.check('master_blackout_and_audio_safe',bool(h.par.Masterblackout) and not bool(h.par.Audioenabled))
                    self.finish();return
                self.stage='begin'
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(patch=True):
    return ProjectionExportChecks(patch=patch)
