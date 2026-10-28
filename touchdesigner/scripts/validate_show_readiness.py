"""Off-air native regression test. Run as a Text DAT module: start(repo_root).

Uses disposable Show Control/Wall Output copies and local test recordings.
Never saves TOE, opens audience windows, enables audio or changes the original
cue document or mapping. The recorder fixture must not inherit the real show's
blackout through a shared Wall Output component.
"""
import copy
import json
from pathlib import Path
import time

STATE = {}


def _require_safe_session(original):
    """Fail before copying or changing anything when the operator is on air."""
    ext = original.ext.ShowControlExt
    wall = original.parent().op('wall_output')
    if ext.engine.state != 'stopped' or ext._look_edit is not None:
        raise RuntimeError('Stop All and finish/cancel the look draft before readiness QA')
    if original.par.Audioenabled or not original.par.Masterblackout or not wall.par.Blackout:
        raise RuntimeError('Disarm audio and enable show/wall blackouts before readiness QA')
    if original.fetch('imagefx_export_job', None, search=False):
        raise RuntimeError('Finish/cancel video export before readiness QA')
    if original.fetch('imagefx_readiness_sample', None, search=False):
        raise RuntimeError('Wait for the performance sample before readiness QA')
    if original.parent().fetch('imagefx_deferred_controls_running', False):
        raise RuntimeError('Wait for the deferred control audit before readiness QA')
    if any(w is not None and w.isOpen for w in original.op('show_output_mode').module.windows(original)):
        raise RuntimeError('Close all physical output windows before readiness QA')


def _validate_control_values(show):
    """Exercise all new editable values on the disposable copy, not the show."""
    checks = []
    for name, values, default in (
            ('Cuewarmframes', (1, 6, 12), 3),
            ('Sampleduration', (1, 5, 30), 5),
            ('Wallrecordwarmup', (0, 2, 10), 2)):
        par = show.par[name]
        assert not par.readOnly and par.clampMin and par.clampMax, name
        assert (par.min, par.normMin, par.max, par.normMax) == (values[0], values[0], values[-1], values[-1]), name
        assert par.default == default, name
        before = par.eval()
        try:
            for value in values:
                par.val = value
                assert par.eval() == value, (name, value, par.eval())
        finally:
            par.val = before
        checks.append(name + ' minimum/midpoint/maximum, default and slider bounds')
    par = show.par.Targetfps
    expected = ['24', '25', '30', '50', '60']
    assert list(par.menuNames) == expected and list(par.menuLabels) == expected
    before = par.eval()
    try:
        for value in expected:
            par.val = value
            assert par.eval() == value
    finally:
        par.val = before
    checks.append('Every performance-target menu choice round-trips')
    for name in ('Readinessstatus', 'Readinessgpu', 'Readinessmedia', 'Readinessoutputs',
                 'Readinessaudio', 'Readinesspower', 'Readinessperformance'):
        assert show.par[name].readOnly, name
    checks.append('All seven diagnostic result values are read-only')
    return checks


def start(root):
    import td
    original=td.op('/project1/imagefx_demo/show_control')
    ext=original.ext.ShowControlExt
    _require_safe_session(original)
    original_wall=original.parent().op('wall_output')
    assert td.op('/project1/readiness_validation_host') is None
    host=td.op('/project1').create(td.baseCOMP,'readiness_validation_host')
    s=host.copy(original,name='show_control')
    wall=host.copy(original_wall,name='wall_output')
    s.initializeExtensions()
    STATE.update(root=Path(root),driver=me.path,host=host,original=original,show=s,wall=wall,
        original_wall=original_wall,
        document=copy.deepcopy(ext.document),checks=[],recordings=[],
        wall_pars={p.name:(p.val,p.expr,p.mode) for p in original_wall.customPars if not p.isPulse and not p.readOnly},
        deadline=time.monotonic()+240,stage='preflight',warm_index=0)
    for index,channel in enumerate(('r','g','b'),1):
        top=host.create(td.constantTOP,'qa_source'+str(index))
        top.par.colorr,top.par.colorg,top.par.colorb=0,0,0
        top.par['color'+channel]=1
        top.par.outputresolution='custom'
        top.par.resolutionw,top.par.resolutionh=1920,1080
        wall.par['Projector{}top'.format(index)]=top.path
    schedule()


def schedule():
    import td
    td.run("op(args[0]).module.poll()",STATE['driver'],delayFrames=1)


def poll():
    try:
        s=STATE['show']; e=s.ext.ShowControlExt; wall=STATE['wall']; stage=STATE['stage']
        if time.monotonic()>STATE['deadline']: raise ValueError('Readiness validation timed out: '+stage)
        if stage=='preflight':
            STATE['checks'].extend(_validate_control_values(s))
            before=copy.deepcopy(e.document)
            protected={n:s.par[n].eval() for n in ('Masterblackout','Audioenabled','Audiomute','Selectedcue')}
            s.par.Readinesscheck.pulse()
            STATE.update(before=before,protected=protected,stage='checked')
        elif stage=='checked':
            assert e.document==STATE['before']
            assert {n:s.par[n].eval() for n in STATE['protected']}==STATE['protected']
            assert s.op('readiness_report').numRows>5
            assert 'NVIDIA' in s.par.Readinessgpu.eval()
            assert not any(w is not None and w.isOpen for w in s.op('show_output_mode').module.windows(s))
            STATE['checks'].append('Preflight pulse fills report without cue/blackout/audio/window mutations')
            s.op('inspector_navigation').par.Section='Pre-Show Check'
            s.op('show_panel_layout').module.select_section(s)
            assert s.op('cue_inspector').par.pagescope.eval()==repr('Pre-Show Check')
            STATE['checks'].append('Pre-Show Check is accessible in native section selector')
            s.par.Sampleduration=1; s.par.Readinesssample.pulse(); STATE['stage']='sample'
        elif stage=='sample':
            if s.fetch('imagefx_readiness_sample',None,search=False): schedule(); return
            assert 'FPS average' in s.par.Readinessperformance.eval(),s.par.Readinessperformance.eval()
            STATE['performance']=s.par.Readinessperformance.eval()
            STATE['checks'].append('Performance pulse completes actual multi-frame FPS/memory sample')
            STATE['stage']='prepare'
        elif stage=='prepare':
            e.Stopall()
            frames=(1,3,12)[STATE['warm_index']]
            s.par.Cuewarmframes=frames
            cue=e.model.new_cue(); cue.update(name='Readiness QA',duration=10,fade=0)
            cue['look']=e._capture_look(STATE['original'].parent())
            e._replace_cues([cue]); e.SelectCue(1); e.Preload()
            STATE.update(cue=cue,frames=frames,stage='ready')
        elif stage=='ready':
            item=e.prepared[STATE['cue']['id']]
            if item.get('error'): raise ValueError(item['error'])
            if item.get('loading'): schedule(); return
            assert item['warm_count']==STATE['frames'],item
            e.Go(); STATE['stage']='go'
        elif stage=='go':
            if not e.tracks: schedule(); return
            assert e.tracks[1]['cue']['id']==STATE['cue']['id']
            STATE['checks'].append('Cue preload/GO works with {} rendered warm-up frames'.format(STATE['frames']))
            e.Stopall(); STATE['warm_index']+=1
            STATE['stage']='prepare' if STATE['warm_index']<3 else 'record_start'
        elif stage=='record_start':
            index=len(STATE['recordings'])
            wall.par.Enabled=True; wall.par.Blackout=False; wall.par.Testpattern=False; wall.par.Monitorenabled=True
            wall.par.Sourcemode='independent'
            wall.op('out1_wall_4k').cook(force=True)
            pixels=wall.op('out1_wall_4k').numpyArray(delayed=False)
            assert pixels is not None and pixels.shape==(2160,3840,4)
            # numpy TOP rows start at bottom: Q1/Q2 are in the upper half.
            for y,x,channel in ((1620,960,0),(1620,2880,1),(540,960,2)):
                assert pixels[y,x,channel]>.9,(y,x,pixels[y,x].tolist())
            assert pixels[:1080,1920:,:3].max()>.1,'Confidence monitor is blank'
            s.par.Exportsource='wall'; s.par.Exportcodec='h264'; s.par.Exportfps='30'; s.par.Exportduration=3
            s.par.Exportfolder=str(STATE['root']/'build/show-readiness/recordings')
            s.par.Wallrecordwarmup=(0,2)[index]
            s.par.Startexport.pulse(); STATE.update(stage='recording',saw_warm=False,saw_record=False)
        elif stage=='recording':
            job=s.fetch('imagefx_export_job',None,search=False)
            if job:
                if job['stage']=='warming':
                    assert not bool(job['writer'].par.record)
                    assert job['index']==0
                    STATE['saw_warm']=True
                if job['stage']=='recording': STATE['saw_record']=True
                schedule(); return
            status=s.par.Exportstatus.eval()
            assert status.startswith('COMPLETE'),status
            assert STATE['saw_warm'] and STATE['saw_record']
            STATE['recordings'].append(dict(status=status,path=s.par.Exportresult.eval(),warmup=float(s.par.Wallrecordwarmup)))
            STATE['checks'].append('UHD H264 recording completed after visible warm-up phase')
            STATE['stage']='record_start' if len(STATE['recordings'])<2 else 'cancel_start'
        elif stage=='cancel_start':
            s.par.Wallrecordwarmup=10; s.par.Startexport.pulse(); STATE['stage']='cancel'
        elif stage=='cancel':
            assert s.fetch('imagefx_export_job',None,search=False)['stage']=='warming'
            s.par.Cancelexport.pulse(); STATE['stage']='cancelled'
        elif stage=='cancelled':
            assert not s.par.Exportbusy
            assert s.par.Exportstatus.eval().startswith('CANCELLED')
            STATE['checks'].append('Cancel during warm-up cleans up without marking an empty movie complete')
            finish(); return
        schedule()
    except Exception as exc:
        finish(repr(exc))


def finish(error=''):
    s=STATE['show']
    if s.fetch('imagefx_export_job',None,search=False): s.op('show_review_export').module.finish_export(s,'CANCELLED')
    s.ext.ShowControlExt.Stopall()
    original_wall=STATE['original_wall']
    if any((original_wall.par[name].val,original_wall.par[name].expr,original_wall.par[name].mode)!=value
           for name,value in STATE['wall_pars'].items()): error=error or 'Original wall parameters changed'
    if STATE['original'].ext.ShowControlExt.document!=STATE['document']: error=error or 'Original cues changed'
    if not error: STATE['checks'].append('Original cue document preserved; no audience windows/audio started')
    if not error: STATE['checks'].append('Original wall values, expressions and modes preserved; calibration pixels verified')
    STATE['host'].destroy()
    report={key:STATE.get(key) for key in ('checks','recordings','performance')}
    report.update(ok=not error,error=error)
    path=STATE['root']/'build/show-readiness/native-validation.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('SHOW READINESS VALIDATION:',report['ok'],error,str(path))
