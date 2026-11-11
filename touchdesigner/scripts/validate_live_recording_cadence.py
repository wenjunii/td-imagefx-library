"""Off-air 30/60 FPS wall/review throughput test, without capture-time readbacks.

This is a synthetic renderer/encoder benchmark, not a full-show qualification.
Run via runpy.run_path(... )['start']('baseline', patch=False) in TD Textport.
"""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
SHADER = '''
uniform float uTime;
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    float x = fract(uv.x + uTime * .15);
    vec3 c = .5 + .45 * cos(vec3(0.,2.,4.) + uv.y * 12. + x * 24.);
    c *= .4 + .6 * step(.08, fract(x * 20.));
    fragColor = TDOutputSwizzle(vec4(c,1.));
}
'''


class CadenceChecks:
    def __init__(self, label, patch, duration=5, rates=(60,30), repeats=1):
        import td
        self.td = td
        self.original = td.op('/project1/imagefx_demo/show_control')
        runpy.run_path(str(ROOT/'touchdesigner/scripts/validate_show_readiness.py'))['_require_safe_session'](self.original)
        if td.op('/project1/recording_cadence_qa') is not None:
            raise RuntimeError('Recording cadence QA already exists')
        self.before = copy.deepcopy(self.original.ext.ShowControlExt.document)
        self.private = ROOT/'.imagefx/shows/current.json'
        self.private_hash = hashlib.sha256(self.private.read_bytes()).hexdigest() if self.private.is_file() else None
        self.task = 'recording-cadence-'+uuid.uuid4().hex[:8]
        self.folder = ROOT/'build/task-artifacts'/self.task
        self.folder.mkdir(parents=True)
        self.base = td.op('/project1').create(td.baseCOMP,'recording_cadence_qa')
        self.wall = self.base.copy(self.original.parent().op('wall_output'),name='wall_output')
        self.show = self.base.copy(self.original,name='show_control')
        if patch:
            runpy.run_path(str(ROOT/'touchdesigner/scripts/install_projection_export.py'))['install'](self.show)
        self.runtime = self.show.op('show_review_export').module
        self.report = dict(label=label,task=self.task,patch=patch,cases=[],ok=False,
                           hardware_outputs_opened=False,synthetic_benchmark=True)
        self.result = ROOT/'build/recording-cadence'/(label+'.json')
        self.duration = duration
        self.cases = [(source,fps,codec) for _ in range(repeats) for fps in rates
                      for source,codec in (('wall','h264'),('review','h265'))]
        self.report['duration_per_case'] = duration
        self.index = 0
        self.stage = 'setup'
        self.schedule(8)

    def schedule(self, frames=1):
        self.td.run('args[0].step()', self, delayFrames=frames)

    def finish(self, error=None):
        if self.show.fetch(self.runtime.JOB_KEY,None,search=False):
            self.runtime.finish_export(self.show,'CANCELLED')
        self.report['main_cues_unchanged'] = self.original.ext.ShowControlExt.document == self.before
        now_hash = hashlib.sha256(self.private.read_bytes()).hexdigest() if self.private.is_file() else None
        self.report['private_show_unchanged'] = now_hash == self.private_hash
        self.base.destroy()
        self.report['sandbox_removed'] = self.td.op('/project1/recording_cadence_qa') is None
        self.report['ok'] = not error and all(self.report[k] for k in
            ('main_cues_unchanged','private_show_unchanged','sandbox_removed'))
        if error:
            self.report['error'] = error
        self.result.parent.mkdir(parents=True,exist_ok=True)
        self.result.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('RECORDING CADENCE:',self.report['ok'],str(self.result),error)

    def step(self):
        try:
            h,r,w = self.show,self.runtime,self.wall
            if self.stage == 'setup':
                code = self.base.create(self.td.textDAT,'moving_test_code')
                code.text = SHADER
                for i in (1,2,3):
                    source = self.base.create(self.td.glslTOP,'moving_test'+str(i))
                    source.par.pixeldat = code.path
                    source.par.outputresolution = 'custom'
                    source.par.resolutionw,source.par.resolutionh = 1920,1080
                    source.seq.vec.numBlocks = 1
                    source.par.vec0name = 'uTime'
                    source.par.vec0valuex.expr = 'absTime.seconds + '+str(i)
                    w.par['Projector'+str(i)+'top'] = source.path
                w.par.Sourcemode = 'independent'
                w.par.Enabled = True
                w.par.Blackout = False
                w.par.Testpattern = False
                w.par.Monitorenabled = True
                h.par.Masterblackout = False
                h.par.Audioenabled = False
                h.par.Outputmode = 'wall'
                h.par.Reviewroute = 'wall'
                h.par.Reviewprojector = 'all'
                h.par.Reviewresolution = '1080p'
                h.par.Exportfolder = str(self.folder/'recordings')
                h.par.Exportduration = self.duration
                h.par.Wallrecordwarmup = 2
                if h.par['Liveencoderquality'] is not None:
                    quality = h.par.Liveencoderquality
                    assert list(quality.menuNames) == ['balanced','fast','high']
                    for value in quality.menuNames:
                        quality.val = value
                        assert quality.eval() == value
                    h.par.Liveencoderquality = 'balanced'
                    self.report['encoder_quality_menu_roundtrip'] = True
                self.stage = 'begin'
                self.schedule(15)
                return
            if self.stage == 'begin':
                source,fps,codec = self.cases[self.index]
                h.par.Exportsource,h.par.Exportfps,h.par.Exportcodec = source,str(fps),codec
                r.start_export(h)
                self.deadline = time.monotonic()+110
                self.intervals = []
                self.last_tick = None
                self.last_job = None
                self.warmup_written = 0
                self.stage = 'record'
            elif self.stage == 'record':
                job = h.fetch(r.JOB_KEY,None,search=False)
                if job:
                    if time.monotonic() > self.deadline:
                        raise RuntimeError('Live recorder timeout: '+str(h.par.Exportstatus.eval()))
                    if job['stage'] == 'warming' and 'encoder_parameters' not in self.report:
                        self.report['encoder_parameters'] = [{
                            'name':p.name,'value':str(p.eval()),'menu':list(p.menuNames or [])
                        } for p in job['writer'].pars() if p.page is not None and p.page.name not in ('Common','EXR')]
                    if job['stage'] == 'warming':
                        r._wall_counts(job)
                        self.warmup_written = max(self.warmup_written,job['index'])
                        assert job['index'] == 0, 'Warm-up must not write frames'
                    if job['stage'] == 'recording':
                        now = time.perf_counter()
                        if self.last_tick is not None:
                            self.intervals.append(now-self.last_tick)
                        self.last_tick = now
                        self.last_job = job
                    self.schedule()
                    return
                source,fps,codec = self.cases[self.index]
                values = sorted(self.intervals)
                self.report['cases'].append(dict(source=source,fps=fps,codec=codec,
                    path=h.par.Exportresult.eval(),status=h.par.Exportstatus.eval(),
                    frames=self.last_job.get('index') if self.last_job else None,
                    dropped=self.last_job.get('dropped') if self.last_job else None,
                    drop_events=self.last_job.get('drop_events',[]) if self.last_job else [],
                    warmup_frames_written=self.warmup_written,
                    render_gap_ms_max=max(values,default=0)*1000,
                    render_gap_ms_p95=values[int(.95*(len(values)-1))]*1000 if values else None,
                    observed_render_fps=len(values)/sum(values) if values else None))
                if not str(h.par.Exportstatus.eval()).startswith('COMPLETE'):
                    raise RuntimeError(h.par.Exportstatus.eval())
                self.index += 1
                if self.index == len(self.cases):
                    self.finish()
                    return
                self.stage = 'begin'
                self.schedule(15)
                return
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(label='baseline', patch=False, duration=5, rates=(60,30), repeats=1):
    return CadenceChecks(label, patch, duration, rates, repeats)
