"""Off-air UHD recorder test in disposable show/wall copies, not the user's show.

Run start(root, driver_path) from a Text DAT containing this script. Reports and
test movies stay under ignored build/. Decode the completed files separately
with ffprobe/ffmpeg to confirm dimensions, quadrant order and frame count.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import json
import time
import traceback

STATE = {}


def later():
    import td
    td.run('op(args[0]).module.poll()', STATE['driver'], delayFrames=3)


def start(root, driver):
    import td
    original = td.op('/project1/imagefx_demo/show_control')
    runtime = original.op('show_review_export').module
    assert not any(runtime.window_open(w) for w in runtime._export_windows(original))
    assert not original.fetch(runtime.JOB_KEY, None, search=False)
    assert td.op('/project1/wall_export_qa') is None
    host = td.op('/project1').create(td.baseCOMP, 'wall_export_qa')
    STATE.update(root=Path(root), driver=driver, host=host, original=original,
                 document=copy.deepcopy(original.ext.ShowControlExt.document),
                 pars={p.name:p.eval() for p in original.customPars if not p.isPulse and not p.readOnly},
                 checks=[], exports=[], case=0, deadline=time.monotonic()+180)
    try:
        show = host.copy(original, name='show_control')
        wall = host.copy(original.parent().op('wall_output'), name='wall_output')
        show.initializeExtensions()
        r = show.op('show_review_export').module
        STATE.update(show=show, wall=wall, runtime=r)
        for i, channel in enumerate(('r', 'g', 'b'), 1):
            top = host.create(td.constantTOP, 'qa_source'+str(i))
            top.par.colorr, top.par.colorg, top.par.colorb = 0, 0, 0
            top.par['color'+channel] = 1
            top.par.outputresolution = 'custom'
            top.par.resolutionw, top.par.resolutionh = 1920, 1080
            wall.par['Projector{}top'.format(i)] = top.path
        # Animate a channel to ensure the recording is not a frozen screenshot.
        host.op('qa_source1').par.colorg.expr = '(absTime.seconds * 0.6) % 0.5'
        wall.par.Sourcemode = 'independent'
        wall.par.Blackout = False
        wall.par.Enabled = True
        wall.par.Testpattern = False
        wall.par.Monitorenabled = True
        wall.par.Showstats = True
        show.par.Exportsource = 'wall'
        show.par.Exportresolution = 'custom'
        show.par.Exportwidth, show.par.Exportheight = 640, 360
        show.par.Exportstart = 45  # Ignored in wall mode, no transport seek.
        show.par.Exportfolder = str(STATE['root']/'build/export-tests')
        for name in ('Exportresolution', 'Exportwidth', 'Exportheight', 'Exportstart'):
            assert not show.par[name].enable, name
        assert '3840 x 2160' in show.par.Exportinfo.eval()
        STATE['checks'].append('wall source menu, fixed-UHD readout and disabled offline fields')
        wall.par.Monitorenabled = False
        assert not r.on_pulse(show, 'Startexport')
        assert 'Enable Confidence' in show.par.Exportstatus.eval()
        assert not show.fetch(r.JOB_KEY, None, search=False)
        wall.par.Monitorenabled = True
        STATE['checks'].append('disabled confidence fails before creating an export job')
        STATE['cases'] = [('h264', 30, 1, 'complete'), ('mjpeg', 25, .4, 'complete'),
                          ('h264', 24, 60, 'stop'), ('h264', 60, 60, 'cancel')]
        next_case()
    except Exception as exc:
        finish(traceback.format_exc())
        raise


def next_case():
    s = STATE['show']
    codec, fps, duration, action = STATE['cases'][STATE['case']]
    s.par.Exportcodec, s.par.Exportfps, s.par.Exportduration = codec, str(fps), duration
    # Running transport must remain running throughout wall recording. These
    # independent test sources do not need to play or mutate a real cue.
    s.ext.ShowControlExt.engine.state = 'running'
    assert STATE['runtime'].on_pulse(s, 'Startexport'), s.par.Exportstatus.eval()
    job = s.fetch(STATE['runtime'].JOB_KEY, None, search=False)
    assert job['target'] == STATE['wall'].op('out1_wall_4k')
    assert (int(job['writer'].par.resolutionw), int(job['writer'].par.resolutionh)) == (3840, 2160)
    assert not job['writer'].par.audiochop.val, job['writer'].par.audiochop.val
    STATE['job_deck'] = job['deck'].path
    STATE['action_done'] = False
    later()


def poll():
    try:
        s, r = STATE['show'], STATE['runtime']
        if time.monotonic() > STATE['deadline']:
            raise ValueError('Wall export validation timed out: '+s.par.Exportstatus.eval())
        codec, fps, duration, action = STATE['cases'][STATE['case']]
        job = s.fetch(r.JOB_KEY, None, search=False)
        if job and action != 'complete' and not STATE['action_done']:
            r._wall_counts(job)
            if job['index'] >= 4:
                name = 'Stopexport' if action == 'stop' else 'Cancelexport'
                s.par[name].pulse()  # Deliver the real Parameter Execute event.
                STATE['action_done'] = True
        if s.par.Exportbusy:
            later()
            return
        status = s.par.Exportstatus.eval()
        assert status.startswith('CANCELLED' if action == 'cancel' else 'COMPLETE'), status
        assert not s.fetch(r.JOB_KEY, None, search=False)
        assert s.op(STATE['job_deck']) is None
        assert s.ext.ShowControlExt.engine.state == 'running'
        assert not STATE['wall'].par.Blackout
        assert not any(r.window_open(w) for w in r._export_windows(s))
        STATE['exports'].append(dict(codec=codec, fps=fps, duration=duration, action=action,
                                     path=s.par.Exportresult.eval(), status=status))
        STATE['checks'].append('{} {} FPS {}: cleanup, unchanged transport/routing and closed windows'.format(codec, fps, action))
        STATE['case'] += 1
        if STATE['case'] == len(STATE['cases']):
            finish()
        else:
            next_case()
    except Exception as exc:
        finish(traceback.format_exc())


def finish(error=''):
    s = STATE.get('show')
    if s and s.fetch('imagefx_export_job', None, search=False):
        STATE['runtime'].finish_export(s, 'CANCELLED')
    original = STATE['original']
    try:
        assert original.ext.ShowControlExt.document == STATE['document']
        assert {p.name:p.eval() for p in original.customPars if not p.isPulse and not p.readOnly} == STATE['pars']
        STATE['checks'].append('original show document and all editable parameters unchanged')
    except Exception as exc:
        error = error or repr(exc)
    STATE['host'].destroy()
    result = dict(ok=not error, error=error, generated_at=datetime.now(timezone.utc).isoformat(),
                  checks=STATE['checks'], exports=STATE['exports'])
    path = STATE['root']/'build/envoy-validation/wall-export.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('WALL EXPORT VALIDATION:', result['ok'], error, path)
