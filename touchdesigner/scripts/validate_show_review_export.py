"""Off-air integration test; uses temporary cues, restores show and mapping state.

Run as a Text DAT module in TouchDesigner using start(root), with physical
output windows closed and no look draft. The DAT stays alive until completion.
Exports small local test files under ignored build/export-tests; never uploads.
"""
from pathlib import Path
import copy
import json
import time
from datetime import datetime, timezone

STATE = {}
FLOW_MODULES = ('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow')


def flow_export_look(template, name, toggle_name):
    """Build a non-default animated test look without mutating its template."""
    if name not in FLOW_MODULES:
        raise ValueError('Unknown flow export module: ' + name)
    look = copy.deepcopy(template)
    look['toggles'] = {key: False for key in look.get('toggles', {})}
    look['toggles'][toggle_name] = True
    look['modules'] = {name: dict(
        Mix=1., Coverage=.7, Particlefieldenabled=True,
        Particlecolumns=64, Fielddensity=.65, Fieldsize=2.5, Fieldspeed=1.2,
        Feedbackenabled=True, Feedbackamount=.8, Feedbackdecay=.94,
        Feedbackzoom=1.005, Feedbackrotate=.3, Feedbackoffsetx=.002,
        Feedbackoffsety=-.001, Animationspeed=1.3)}
    look['animation'] = {name: dict(time=1., running=True, render_time=2., field_time=.75)}
    return look


def start(root=None):
    import td
    root = Path(root or Path(__file__).resolve().parents[2])
    original = td.op('/project1/imagefx_demo/show_control')
    s = original
    e = s.ext.ShowControlExt
    r = s.op('show_review_export').module
    assert e.engine.state == 'stopped' and e._look_edit is None
    assert not any(r.window_open(w) for w in r._export_windows(s))
    assert not s.fetch(r.JOB_KEY,None,search=False)
    wall = s.parent().op('wall_output')
    # Never populate the user's cue editor with generated test media. Testing
    # in a disposable copy also preserves unsaved editor fields and selection.
    s = original.parent().copy(original, name='show_review_export_qa')
    s.initializeExtensions()
    e = s.ext.ShowControlExt
    r = s.op('show_review_export').module
    STATE.update(root=root, driver=me.path, show=s, ext=e, runtime=r, wall=wall,
                 original=original, document=copy.deepcopy(original.ext.ShowControlExt.document),
                 main=e._capture_look(s.parent()),
                 pars={p.name:p.eval() for p in original.customPars if not p.isPulse and not p.readOnly},
                 wall_pars={n:wall.par[n].eval() for n in ('Sourcemode','Projector1top','Projector2top','Projector3top','Blackout','Enabled','Testpattern')},
                 checks=[], exports=[], index=0, deadline=time.monotonic()+600)
    try:
        for i,channel in enumerate(('r','g','b'),1):
            source=s.create(td.constantTOP,'review_validation_'+str(i))
            source.store('imagefx_show_runtime',True)
            source.par.colorr,source.par.colorg,source.par.colorb=0,0,0
            source.par['color'+channel]=1
            source.par.outputresolution='custom'
            source.par.resolutionw,source.par.resolutionh=64,36
            wall.par['Projector{}top'.format(i)]=source.path
        wall.par.Sourcemode='independent'
        wall.par.Blackout=False
        wall.par.Enabled=True
        wall.par.Testpattern=False
        s.par.Outputmode='wall'
        for i in (1,2,3):
            top=s.op('review_p'+str(i)); top.cook(force=True)
            arr=top.numpyArray(delayed=False)
            means=arr[:,:,:3].mean(axis=(0,1))
            assert int(means.argmax())==i-1 and means[i-1]>.9, (i,means)
            STATE['checks'].append('wall projector {} route/color'.format(i))
        top=s.op('projector_review'); top.cook(force=True)
        arr=top.numpyArray(delayed=False)
        for i in range(3):
            means=arr[:,i*288:(i+1)*288,:3].mean(axis=(0,1))
            assert int(means.argmax())==i,(i,means,list(top.inputs),arr.shape)
        STATE['checks'].append('3-up ordering is left / center / right')
        wall.par.Blackout=True
        for i in (1,2,3):
            top=s.op('review_p'+str(i)); top.cook(force=True)
            assert top.numpyArray(delayed=False)[:,:,:3].max()==0
        STATE['checks'].append('wall blackout is visible in every preview')
        for i in (1,2,3):
            s.par.Outputmode='direct'
            assert r.review_path(s,i)==s.op('out{}_projector'.format(i)).path
        STATE['checks'].append('direct displays tap post-mapping outputs')
        for name,value in STATE['wall_pars'].items(): wall.par[name]=value
        s.par.Outputmode='wall'
        cue=e.model.new_cue()
        cue.update(name='Review export validation',look=e._capture_look(s.parent()))
        cue['look']['toggles']={key:False for key in cue['look']['toggles']}
        cue['look']['toggles'][e.model.MODULE_TOGGLES['calligraphic_shadow']]=True
        e._replace_cues([cue])
        e.SelectCue(1)
        STATE['base_cue'] = copy.deepcopy(cue)
        s.par.Exportfolder=str(root/'build/export-tests')
        s.par.Exportfps='30'
        s.par.Exportstart=0
        STATE['cases']=[('1080p','h264',.2,'cue'),('4k','h264',.1,'cue'),
                        ('1080p','h265',.2,'cue'),('4k','h265',.1,'cue'),
                        ('custom','mjpeg',.2,'cue'),('custom','h264',.2,'draft'),
                        ('custom','h264',.2,'movie')]
        STATE['cases'] += [('custom', 'h264', .4, name) for name in FLOW_MODULES]
        STATE['cases'] += [('panoramic', 'mjpeg', .2, source) for source in
                           ('panorama_cue', 'panorama_draft', 'panorama_media', 'panorama_crop')]
        STATE['cases'] += [('panoramic', 'h265', .2, source) for source in
                           ('panorama_cue', 'panorama_draft', 'panorama_media', 'panorama_crop')]
        STATE['cases'] += [('panoramic', 'h265', .4, name) for name in FLOW_MODULES]
        td.run("op(args[0]).module.next_case()", STATE['driver'], delayFrames=2)
    except Exception as exc:
        finish(repr(exc))
        raise


def schedule():
    import td
    td.run("op(args[0]).module.poll()", STATE['driver'],delayFrames=6)


def next_case():
    s,e=STATE['show'],STATE['ext']
    if STATE['index']>=len(STATE['cases']):
        s.par.Exportduration=60
        s.par.Exportsource='cue'
        if e._look_edit: e.CancelLook()
        STATE['runtime'].start_export(s)
        assert s.par.Exportbusy
        s.par.Cancelexport.pulse()
        STATE['cancel']=True
        schedule()
        return
    preset,codec,duration,source=STATE['cases'][STATE['index']]
    if preset == 'panoramic':
        s.par.Renderwidth, s.par.Renderheight, s.par.Panoramaoverlap = 1920, 1080, 0
        s.par.Routingmode, s.par.Cuemediafit = 'identical', 'auto'
    STATE['flow_observed'] = False
    STATE['flow_samples'] = []
    if source in FLOW_MODULES:
        if e._look_edit: e.CancelLook()
        cue = copy.deepcopy(STATE['base_cue'])
        cue['name'] = 'Particle feedback export ' + source
        cue['source'] = ''
        cue['look'] = flow_export_look(cue['look'], source, e.model.MODULE_TOGGLES[source])
        e._replace_cues([cue])
        e.SelectCue(1)
    if source=='movie':
        if e._look_edit: e.CancelLook()
        cue=copy.deepcopy(e.document['cues'][0])
        cue['source']=STATE['exports'][0]['path']
        cue['media_in']=.03
        cue['speed']=.5
        e._replace_cues([cue])
        e.SelectCue(1)
    if source=='draft':
        e.RecallLook()
        STATE['draft']=e._capture_look(e._look_edit['deck'])
    if source.startswith('panorama_'):
        import td
        if e._look_edit: e.CancelLook()
        s.par.Renderwidth, s.par.Renderheight, s.par.Panoramaoverlap = 1920, 1080, 0
        # The preset must work without changing the actual output layout.
        s.par.Routingmode, s.par.Cuemediafit = 'identical', 'auto'
        cue = copy.deepcopy(STATE['base_cue'])
        if source in ('panorama_media', 'panorama_crop'):
            cue['look']['toggles'] = {key: False for key in cue['look']['toggles']}
            code = s.op('aspect_fixture_code') or s.create(td.textDAT, 'aspect_fixture_code')
            code.text = ('layout(location=0) out vec4 fragColor; void main(){'
                         'vec2 p=(vUV.st-.5)*vec2(1920.,1080.);'
                         'vec3 c=length(p)<120. ? vec3(1.,0.,0.) : vec3(.05);'
                         'fragColor=TDOutputSwizzle(vec4(c,1.));}')
            fixture = s.op('aspect_fixture') or s.create(td.glslTOP, 'aspect_fixture')
            fixture.par.pixeldat = code.name
            fixture.par.outputresolution = 'custom'
            fixture.par.resolutionw, fixture.par.resolutionh = 1920, 1080
            fixture.cook(force=True)
            assert not fixture.errors(), fixture.errors()
            fixture_path = STATE['root'] / 'build/export-tests/panorama-circle.png'
            fixture.save(str(fixture_path))
            cue['source'] = str(fixture_path)
            if source == 'panorama_crop':
                cue['look']['toggles'][e.model.MODULE_TOGGLES['final_crop']] = True
                cue['look']['modules']['final_crop'] = dict(Aspect='16x9', Outputmode='crop')
        e._replace_cues([cue])
        e.SelectCue(1)
        if source == 'panorama_draft':
            e.RecallLook()
            STATE['draft'] = e._capture_look(e._look_edit['deck'])
    s.par.Exportresolution=preset
    s.par.Exportwidth,s.par.Exportheight=640,360
    s.par.Exportcodec=codec
    s.par.Exportduration=duration
    s.par.Exportsource = ('draft' if source in ('draft', 'panorama_draft') else 'cue')
    s.par.Startexport.pulse()
    STATE['await_start']=True
    schedule()


def poll():
    try:
        s,e=STATE['show'],STATE['ext']
        if time.monotonic()>STATE['deadline']: raise ValueError('Native validation timed out')
        if STATE.get('cancel'):
            assert not s.par.Exportbusy
            assert s.par.Exportstatus.eval().startswith('CANCELLED'),s.par.Exportstatus.eval()
            assert not s.fetch(STATE['runtime'].JOB_KEY,None,search=False)
            STATE['checks'].append('Cancel pulse releases only its render copy')
            finish()
            return
        if s.par.Exportbusy:
            name = STATE['cases'][STATE['index']][3]
            if STATE['cases'][STATE['index']][0] == 'panoramic':
                job = s.fetch(STATE['runtime'].JOB_KEY, None, search=False)
                if job and job['index'] >= 1:
                    assert (job['target'].width, job['target'].height) == (5760, 1080)
                    if job['settings']['codec'] == 'h265':
                        assert job['writer'].par.videocodec.eval() in ('h265', 'h265nvgpu')
                        assert job['path'].suffix == '.mp4'
                    assert (int(job['deck'].par.Customwidth), int(job['deck'].par.Customheight)) == (5760, 1080)
                    assert s.par.Routingmode == 'identical' and job['settings']['fit'] == 'cover'
                    if name in ('panorama_media', 'panorama_crop'):
                        assert job['deck'].op('cue_media_fit').par.vec0valuex.eval() == 1
                    if name == 'panorama_media':
                        arr = job['target'].numpyArray(delayed=False)
                        mask = (arr[:, :, 0] > .8) & (arr[:, :, 1] < .1)
                        ys, xs = mask.nonzero()
                        assert len(xs), 'Panorama media was not rendered'
                        w, h = int(xs.max()-xs.min()+1), int(ys.max()-ys.min()+1)
                        assert abs(w-h) <= 2 and 710 <= w <= 730, (w,h)
                    STATE['panorama_observed'] = True
            if name in FLOW_MODULES:
                job = s.fetch(STATE['runtime'].JOB_KEY, None, search=False)
                if job and job['deck'] is not None and job['index'] >= 2:
                    module = job['deck'].op(name)
                    expected = e.document['cues'][0]['look']['modules'][name]
                    assert module.par.Enabled, name + ' export module disabled'
                    differences = {key: (value, module.par[key].eval()) for key, value in expected.items()
                                   if module.par[key].eval() != value}
                    assert not differences, (name, differences)
                    history = module.fetch('imagefx_flow_feedback_state', None, search=False)
                    STATE['flow_samples'].append(dict(index=job['index'], history=history))
                    # A delayed enable/reset event can clear the initial frame.
                    # Require observed accumulation later, not on the first poll.
                    if history and history['active'] and not history['clear']:
                        STATE['flow_observed'] = True
            STATE['await_start']=False
            schedule()
            return
        status=s.par.Exportstatus.eval()
        if not status.startswith('COMPLETE'): raise ValueError(status)
        case=STATE['cases'][STATE['index']]
        if case[0] == 'panoramic':
            assert STATE.pop('panorama_observed', False), 'Panoramic render dimensions were not observed'
            STATE['checks'].append(case[3] + ' full canvas, frozen proportional fit, unchanged routing')
        if case[3] in FLOW_MODULES:
            assert STATE['flow_observed'], ('Particle motion/history were not observed', case[3], STATE['flow_samples'])
            STATE['checks'].append(case[3] + ' custom values and active GPU history in export copy')
        STATE['exports'].append(dict(preset=case[0],codec=case[1],duration=case[2],source=case[3],
            path=s.par.Exportresult.eval(),status=status))
        STATE['checks'].append('export '+str(case))
        if e._look_edit:
            assert e._capture_look(e._look_edit['deck'])==STATE['draft']
            STATE['checks'].append('export left active draft unchanged')
        STATE['index']+=1
        next_case()
    except Exception as exc:
        finish(repr(exc))


def finish(error=''):
    s,e=STATE['show'],STATE['ext']
    if s.fetch(STATE['runtime'].JOB_KEY,None,search=False):
        STATE['runtime'].finish_export(s,'CANCELLED')
    if e._look_edit: e.CancelLook()
    for n,v in STATE['wall_pars'].items(): STATE['wall'].par[n]=v
    original=STATE['original']
    try:
        assert e._capture_look(s.parent())==STATE['main']
        assert original.ext.ShowControlExt.document==STATE['document']
        assert {p.name:p.eval() for p in original.customPars if not p.isPulse and not p.readOnly}==STATE['pars']
        STATE['checks'].append('main look, saved document, selection and unsaved editor fields unchanged')
    except Exception as exc:
        error=error or 'State preservation failed: '+repr(exc)
    finally:
        s.destroy()
    report=dict(ok=not error,error=error,generated_at=datetime.now(timezone.utc).isoformat(),
                checks=STATE['checks'],exports=STATE['exports'])
    path=STATE['root']/'build/envoy-validation/show-review-export.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('REVIEW / EXPORT VALIDATION:',report['ok'],error,'report:',path)
