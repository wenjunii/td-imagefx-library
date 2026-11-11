"""Frame-based cue destinations: native editor callbacks and GO, no forced cooks.

Runs off-air in a disposable Show Control / wall copy. Unlike the synchronous
pixel sweep, this test primes native expression caches before changing cues and
lets ordinary frame invalidation update all selectors and shader uniforms.
"""
import copy
import json
from pathlib import Path
import runpy
import traceback

ROOT = Path(__file__).resolve().parents[2]


class RoutingFrames:
    def __init__(self, patch=False):
        import td
        self.td = td
        self.original = td.op('/project1/imagefx_demo/show_control')
        ext = self.original.ext.ShowControlExt
        if ext.engine.state != 'stopped' or ext._look_edit is not None:
            raise RuntimeError('Stop All and finish Look Editor before the off-air test')
        self.before = copy.deepcopy(ext.document)
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('Existing sandbox must not be overwritten')
        self.base = td.op('/project1').create(td.baseCOMP, 'imagefx_sandbox')
        self.wall = self.base.copy(self.original.parent().op('wall_output'), name='wall_output')
        self.host = self.base.copy(self.original, name='show_control')
        if patch:
            runpy.run_path(str(ROOT / 'touchdesigner/scripts/cue_projection.py'))['upgrade'](self.host)
        self.host.op('show_tick').par.active = False
        self.ext = self.host.ext.ShowControlExt
        groups = ('1', '2', '3', '1_2', '1_3', '2_3', 'all')
        self.cases = [(mode, track, group, 'p2') for mode in ('cue','independent','identical','panoramic')
                      for track in (1,2,3) for group in groups]
        self.cases += [('cue',track,group,'panoramic') for track in (1,2,3) for group in ('2','1_3','all')]
        self.index = 0
        self.stage = 'setup'
        self.wait = 0
        self.report = dict(ok=False, patched=patch, cases=[], hardware_outputs_opened=False)
        self.schedule(8)

    def schedule(self, frames=1):
        self.td.run('args[0].step()', self, delayFrames=frames)

    def require(self, value, message):
        if not value:
            raise AssertionError(message)

    def sample(self, node):
        import numpy as np
        a = node.numpyArray(delayed=False)
        self.require(a is not None and np.isfinite(a).all(), node.path + ': unusable frame')
        return a[a.shape[0]//2,a.shape[1]//2,:3]

    def finish(self, error=None):
        self.report['original_cues_preserved'] = self.original.ext.ShowControlExt.document == self.before
        self.report['ok'] = error is None and self.report['original_cues_preserved']
        if error:
            self.report['error'] = error
            self.report['diagnostics'] = {
                'case':self.cases[self.index],
                'revision':self.host.par.Cueroutingrevision.eval(),
                'tracks':list(self.ext.tracks),
                'outputs':[{ 'output':i,
                    'expected_input':self.ext.ProjectionInput(i,1),
                    'native_input':str(self.host.op('cue_projection'+str(i)+'_source1').par.top.eval()),
                    'native_blend':[self.host.op('cue_projection'+str(i)).par['vec0value'+a].eval() for a in 'xyz'],
                    'expected_blend':[self.ext.ProjectionBlend(i,j) for j in range(3)],
                    'native_sample':[self.host.op('cue_projection'+str(i)).par['vec2value'+a].eval() for a in 'xyz'],
                    'expected_sample':self.ext.ProjectionSample(i,1),
                } for i in (1,2,3)],
            }
        self.ext.engine.stop()
        self.base.destroy()
        target = ROOT / 'build/cue-projection/routing-frames.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print('Frame-based cue routing:',self.report['ok'],'cases:',len(self.report['cases']))
        if error: print(error)

    def step(self):
        import numpy as np
        try:
            h, e, w = self.host, self.ext, self.wall
            if self.stage == 'setup':
                h.par.Renderwidth,h.par.Renderheight = 160,90
                h.par.Sharedtrack = 1
                w.par.Enabled,w.par.Blackout,w.par.Testpattern = True,False,False
                for i in (1,2,3):
                    h.par['Output'+str(i)+'track'] = i
                    h.par['Output'+str(i)+'width'],h.par['Output'+str(i)+'height'] = 160,90
                    h.par['Output'+str(i)+'blackout'] = False
                code=h.create(self.td.textDAT,'channel_frame_fixture_code')
                code.text='layout(location=0) out vec4 fragColor; void main(){fragColor=TDOutputSwizzle(vec4(vUV.x,0.5,0.25,1));}'
                self.fixture=h.create(self.td.glslTOP,'channel_frame_fixture')
                self.fixture.par.pixeldat=code.name
                self.fixture.par.outputresolution='custom'
                self.fixture.par.resolutionw,self.fixture.par.resolutionh=480,90
                self.stage='case'
            elif self.stage == 'case':
                if self.index == len(self.cases):
                    self.require(not h.errors(recurse=True) and not w.errors(recurse=True),'Native output error')
                    self.finish(); return
                mode,track,channels,route=self.cases[self.index]
                e.engine.stop()
                h.par.Routingmode=mode
                w.par.Sourcemode=mode if mode != 'cue' else 'show'
                e._replace_cues([dict(e.model.new_cue(),fade=0,duration=0)]);e.SelectCue(1)
                # Prime caches while stopped and before the desired track exists.
                e.UpdateCueRouting()
                for i in (1,2,3):
                    for side in (0,1): h.op('cue_projection'+str(i)+'_source'+str(side)).par.top.eval()
                    for block in (0,1,2):
                        for axis in 'xyz': h.op('cue_projection'+str(i)).par['vec'+str(block)+'value'+axis].eval()
                    self.sample(h.op('out'+str(i)+'_projector'))
                self.stage='edit'
            elif self.stage == 'edit':
                mode,track,channels,route=self.cases[self.index]
                h.par.Track,h.par.Cuechannels,h.par.Cueprojection=track,channels,route
                self.stage='apply'
            elif self.stage == 'apply':
                mode,track,channels,route=self.cases[self.index]
                self.require(e.document['cues'][0]['channels']==channels,'Real channel callback did not commit')
                self.require(e.document['cues'][0]['projection']==route,'Real route callback did not commit')
                e.ApplyCue()
                self.require(e.document['cues'][0]['track']==track,'Playback lane not committed')
                e.Preload();self.wait=0;self.stage='preload'
            elif self.stage == 'preload':
                e._service_preloads()
                item=e.prepared[e.document['cues'][0]['id']]
                self.require(not item.get('error'),'Preload: '+str(item.get('error')))
                self.wait+=1
                self.require(self.wait < 600,'Preload timeout')
                if not item.get('loading'):
                    deck=item['deck']
                    selected=deck.op('channel_frame_input') or deck.create(self.td.selectTOP,'channel_frame_input')
                    selected.par.top=self.fixture.path
                    selected.outputConnectors[0].connect(deck.op('source_image').inputConnectors[0])
                    deck.op('source_image').par.index=0
                    h.par.Masterblackout=False
                    e.Go();self.stage='playing';self.wait=0
            elif self.stage == 'playing':
                e.Tick();self.wait+=1
                if self.wait >= 4: self.stage='measure'
            elif self.stage == 'measure':
                e.Tick()
                mode,track,channels,route=self.cases[self.index]
                outputs=e.model.OUTPUT_CHANNELS[channels]
                values=[]
                for i in (1,2,3):
                    actual=self.sample(h.op('out'+str(i)+'_projector'));values.append([float(n) for n in actual])
                    x=(outputs.index(i)+.5)/len(outputs) if route=='panoramic' and i in outputs else .5
                    expected=(x,.5,.25) if i in outputs else (0,0,0)
                    self.require(np.allclose(actual,expected,atol=.025),str((mode,track,channels,route,i,values[-1],expected)))
                packed=w.op('out1_wall_4k').numpyArray(delayed=False)
                self.require(packed is not None and packed.shape[:2]==(2160,3840),'4K wall frame missing')
                for i,(x,y) in enumerate(((960,1620),(2880,1620),(960,540))):
                    self.require(np.allclose(packed[y,x,:3],values[i],atol=.025),'Wall quadrant differs from cue channel '+str(i+1))
                self.report['cases'].append(dict(mode=mode,track=track,channels=channels,route=route,pixels=values))
                self.index+=1;self.stage='case'
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(patch=False):
    return RoutingFrames(patch)
