"""Off-air integration test; uses temporary cues, restores show and mapping state.

Run in TouchDesigner, with both physical output windows closed and no look draft.
Exports small local test files under ignored build/export-tests; never uploads.
"""
from pathlib import Path
import copy
import json
import time
from datetime import datetime, timezone

STATE = {}


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
    STATE.update(root=root, show=s, ext=e, runtime=r, wall=wall,
                 original=original, document=copy.deepcopy(original.ext.ShowControlExt.document),
                 main=e._capture_look(s.parent()),
                 pars={p.name:p.eval() for p in original.customPars if not p.isPulse and not p.readOnly},
                 wall_pars={n:wall.par[n].eval() for n in ('Sourcemode','Projector1top','Projector2top','Projector3top','Blackout','Enabled','Testpattern')},
                 checks=[], exports=[], index=0, deadline=time.monotonic()+300)
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
        s.par.Reviewroute='wall'
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
            s.par.Reviewroute='atlas'
            assert r.review_path(s,i)==s.op('out{}_projector'.format(i)).path
        STATE['checks'].append('atlas taps post-mapping outputs')
        for name,value in STATE['wall_pars'].items(): wall.par[name]=value
        s.par.Reviewroute='wall'
        cue=e.model.new_cue()
        cue.update(name='Review export validation',look=e._capture_look(s.parent()))
        cue['look']['toggles']={key:False for key in cue['look']['toggles']}
        cue['look']['toggles'][e.model.MODULE_TOGGLES['calligraphic_shadow']]=True
        e._replace_cues([cue])
        e.SelectCue(1)
        s.par.Exportfolder=str(root/'build/export-tests')
        s.par.Exportfps='30'
        s.par.Exportstart=0
        STATE['cases']=[('1080p','h264',.2,'cue'),('4k','h264',.1,'cue'),
                        ('custom','mjpeg',.2,'cue'),('custom','h264',.2,'draft'),
                        ('custom','h264',.2,'movie')]
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
    s.par.Exportresolution=preset
    s.par.Exportwidth,s.par.Exportheight=640,360
    s.par.Exportcodec=codec
    s.par.Exportduration=duration
    s.par.Exportsource='cue' if source=='movie' else source
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
            STATE['await_start']=False
            schedule()
            return
        status=s.par.Exportstatus.eval()
        if not status.startswith('COMPLETE'): raise ValueError(status)
        case=STATE['cases'][STATE['index']]
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
