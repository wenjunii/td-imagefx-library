"""Off-air real-time review recordings with three actual running cue feeds."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]


class ReviewRecordingChecks:
    def __init__(self,patch=True):
        import td
        self.td=td
        self.original=td.op('/project1/imagefx_demo/show_control')
        original=self.original.ext.ShowControlExt
        if original.engine.state!='stopped' or original._look_edit is not None:
            raise RuntimeError('Stop All and finish Look Editor before validation')
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('Sandbox already exists')
        self.before=copy.deepcopy(original.document)
        self.show_path=ROOT/'.imagefx/shows/current.json'
        self.show_hash=hashlib.sha256(self.show_path.read_bytes()).hexdigest() if self.show_path.is_file() else None
        self.task='review-recording-'+uuid.uuid4().hex[:8]
        self.folder=ROOT/'build/task-artifacts'/self.task
        self.folder.mkdir(parents=True)
        self.base=td.op('/project1').create(td.baseCOMP,'imagefx_sandbox')
        self.wall=self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.host=self.base.copy(self.original,name='show_control')
        if patch:
            runpy.run_path(str(ROOT/'touchdesigner/scripts/install_projection_export.py'))['install'](self.host)
        self.ext=self.host.ext.ShowControlExt
        self.runtime=self.host.op('show_review_export').module
        self.report=dict(ok=False,checks={},exports=[],task=self.task,patched=patch,hardware_outputs_opened=False)
        self.stage='setup';self.cue_index=0;self.case_index=0
        self.schedule(6)

    def schedule(self,frames=2):
        self.td.run('args[0].step()',self,delayFrames=frames)

    def check(self,name,value):
        self.report['checks'][name]=bool(value)
        if not value: raise AssertionError(name)

    def finish(self,error=None):
        if self.host.fetch(self.runtime.JOB_KEY,None,search=False):
            self.runtime.finish_export(self.host,'CANCELLED')
        self.ext.Stopall()
        self.report['main_cues_unchanged']=self.original.ext.ShowControlExt.document==self.before
        after_hash=hashlib.sha256(self.show_path.read_bytes()).hexdigest() if self.show_path.is_file() else None
        self.report['user_show_json_unchanged']=after_hash==self.show_hash
        self.base.destroy()
        self.report['sandbox_removed']=self.td.op('/project1/imagefx_sandbox') is None
        self.report['ok']=not error and all(self.report['checks'].values()) and all(self.report[k] for k in
            ('main_cues_unchanged','user_show_json_unchanged','sandbox_removed'))
        if error:self.report['error']=error
        path=ROOT/'build/review-recording/native-validation.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('Review recording:',self.report['ok'],len(self.report['checks']),error)

    def step(self):
        try:
            h,e,r=self.host,self.ext,self.runtime
            if self.stage=='setup':
                self.check('review_source_menu',h.par.Exportsource.menuNames[-1]=='review')
                h.par.Renderwidth,h.par.Renderheight=320,180
                h.par.Outputmode='direct'
                h.par.Routingmode='cue'
                h.par.Masterblackout=False
                h.par.Audioenabled=False
                for i in (1,2,3):
                    h.par['Output'+str(i)+'width']=320
                    h.par['Output'+str(i)+'height']=180
                self.wall.par.Enabled=True;self.wall.par.Blackout=False
                self.wall.par.Sourcemode='show';self.wall.par.Monitorenabled=True
                cues=[]
                for i,channel in enumerate(('r','g','b'),1):
                    source=self.base.create(self.td.constantTOP,'color'+str(i))
                    source.par.colorr,source.par.colorg,source.par.colorb=0,0,0
                    source.par['color'+channel]=1
                    source.par.outputresolution='custom'
                    source.par.resolutionw,source.par.resolutionh=320,180
                    source.cook(force=True)
                    path=self.folder/('color'+str(i)+'.png');source.save(str(path))
                    cues.append(dict(e.model.new_cue(),name='Review color '+str(i),source=str(path),
                                     track=i,projection='p'+str(i),duration=120,fade=0,look={}))
                e._replace_cues(cues)
                h.par.Masterblackout=False
                h.par.Exportfolder=str(self.folder/'exports')
                h.par.Exportsource='review'
                h.par.Exportcodec='h264'
                h.par.Exportfps='30';h.par.Exportduration=.4
                h.par.Wallrecordwarmup=0
                e.SelectCue(1);e.Go()
                self.deadline=time.monotonic()+90;self.stage='cues'
            elif self.stage=='cues':
                if time.monotonic()>self.deadline:raise RuntimeError('Cue preload timed out')
                item=e.tracks.get(self.cue_index+1)
                if item and not item.get('fading'):
                    self.cue_index+=1
                    if self.cue_index<3:
                        e.SelectCue(self.cue_index+1);e.Go()
                    else:
                        self.check('three_live_cue_tracks',len(e.tracks)==3 and e.engine.state=='running')
                        self.geometry=[('720p',(3840,720)),('4k',(11520,2160)),('native',(960,180)),
                                       ('custom',(3000,600)),('1080p',(5760,1080))]
                        self.geometry_index=0;self.stage='geometry_set'
            elif self.stage=='geometry_set':
                h.par.Reviewresolution=self.geometry[self.geometry_index][0]
                h.par.Reviewwidth,h.par.Reviewheight=1000,600
                self.stage='geometry_check'
                self.schedule(3);return
            elif self.stage=='geometry_check':
                quality,size=self.geometry[self.geometry_index]
                full=h.op('projector_review');full.cook(force=True)
                self.check('review_resolution_'+quality,(full.width,full.height)==size and not full.errors())
                self.geometry_index+=1
                if self.geometry_index<len(self.geometry):self.stage='geometry_set'
                else:
                    h.par.Reviewprojector='all'
                    self.check('embedded_selects_thumbnail',r.review_preview_target(h)==h.op('projector_review_thumbnail'))
                    thumb=h.op('projector_review_thumbnail');thumb.cook(force=True)
                    self.check('thumbnail_stays_864_by_162',(thumb.width,thumb.height)==(864,162))
                    self.cases=[('three_up','all','direct','full'),('center','2','direct','full'),
                                ('confidence','confidence','wall','full'),('wall','wall','wall','full'),
                                ('stop_save','all','direct','stop'),('change_view','all','direct','change')]
                    self.stage='begin'
            elif self.stage=='begin':
                name,view,mode,kind=self.cases[self.case_index]
                h.par.Outputmode=mode;h.par.Reviewprojector=view
                h.par.Wallrecordwarmup=2 if name=='three_up' else 0
                width,height=r.review_recording_size(r.review_target(h).width,r.review_target(h).height)
                h.par.Exportcodec='h265' if max(width,height)>4096 else 'h264'
                h.par.Exportduration=2 if kind!='full' else .4
                self.live_document=copy.deepcopy(e.document)
                self.started=e.engine.elapsed
                r.start_export(h)
                self.deadline=time.monotonic()+90;self.sampled=False;self.triggered=False
                self.stage='record'
            elif self.stage=='record':
                name,view,mode,kind=self.cases[self.case_index]
                job=h.fetch(r.JOB_KEY,None,search=False)
                if job:
                    if time.monotonic()>self.deadline:raise RuntimeError('Review recording timed out')
                    if job['stage']=='recording' and not self.sampled:
                        self.sampled=True
                        self.check(name+'_live_mode_no_cue_copy',job['cue'] is None and job['settings']['source']=='review')
                        self.check(name+'_captures_selected_target',job['target']==r.review_target(h))
                        self.check(name+'_native_dimensions',tuple((job['settings']['width'],job['settings']['height']))==r.review_recording_size(job['target'].width,job['target'].height))
                        self.check(name+'_native_shader_encoder_clean',not job['deck'].errors(recurse=True))
                        if name=='three_up':
                            pixels=job['target'].numpyArray(delayed=False)
                            self.check('full_hd_review_export',(job['settings']['width'],job['settings']['height'])==(5760,1080))
                            self.check('full_hd_review_uses_hevc',job['writer'].par.videocodec.eval() in ('h265','h265nvgpu'))
                            cell=pixels.shape[1]//3
                            for i in (1,2,3):
                                mean=pixels[:,(i-1)*cell:i*cell,:3].mean(axis=(0,1))
                                self.check('review_three_up_color_'+str(i),int(mean.argmax())==i-1 and mean[i-1]>.95)
                        if name=='center':
                            mean=job['target'].numpyArray(delayed=False)[:,:,:3].mean(axis=(0,1))
                            self.check('review_center_is_green',int(mean.argmax())==1 and mean[1]>.95)
                    if kind!='full' and job['stage']=='recording' and job['index']>=3 and not self.triggered:
                        self.triggered=True
                        if kind=='stop':r.stop_wall_export(h)
                        else:h.par.Reviewprojector='2'
                    self.schedule();return
                status=h.par.Exportstatus.eval()
                self.check(name+'_sampled_recording',self.sampled)
                self.check(name+'_expected_outcome',status.startswith('FAILED: Projector Review view/output route changed') if kind=='change' else status.startswith('COMPLETE'))
                self.check(name+'_cue_document_unchanged',e.document==self.live_document)
                self.check(name+'_transport_keeps_running',e.engine.state=='running' and e.engine.elapsed>=self.started)
                path=Path(h.par.Exportresult.eval())
                self.check(name+'_movie_file_written',path.is_file() and path.stat().st_size>0)
                self.report['exports'].append(dict(case=name,path=str(path),status=status))
                self.case_index+=1
                if self.case_index==len(self.cases):self.finish();return
                self.stage='begin'
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(patch=True):return ReviewRecordingChecks(patch=patch)
