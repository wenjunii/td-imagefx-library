"""Local, non-arming pre-show diagnostics. A snapshot is not show certification."""
import math
from pathlib import Path
import time
import uuid

SAMPLE_KEY = 'imagefx_readiness_sample'
ACTION_NAMES = ('Readinesscheck', 'Readinesssample', 'Readinessreport')
CHANNELS = ('fps', 'msec', 'dropped_frames', 'gpu_mem_used', 'total_gpu_mem', 'ac_line_status')


def performance_report(samples, target):
    """Evaluate actual measurements; missing data is never treated as zero."""
    target = float(target)
    if not math.isfinite(target) or not 1 <= target <= 240:
        raise ValueError('Target FPS must be between 1 and 240')
    rows = []
    def values(name):
        return [float(s[name]) for s in samples if s.get(name) is not None
                and math.isfinite(float(s[name])) and float(s[name]) >= 0]
    fps, ms = values('fps'), values('msec')
    if not fps or not ms:
        rows.append(('WARN', 'Performance', 'No valid FPS/frame-time samples; run the sample again'))
    else:
        ordered = sorted(ms)
        p95 = ordered[max(0, math.ceil(len(ordered)*.95)-1)]
        average = sum(fps)/len(fps)
        level = 'WARN' if average < target*.95 or p95 > 1000/target else 'PASS'
        rows.append((level, 'Performance', '{:.1f} FPS average; {:.1f} minimum; {:.2f} ms p95; target {:.0f} FPS'.format(
            average, min(fps), p95, target)))
    dropped = values('dropped_frames')
    rows.append(('WARN' if not dropped or sum(dropped) else 'PASS', 'Dropped frames',
                 '{} timeline frames during sample (not encoder frames)'.format(int(sum(dropped)))
                 if dropped else 'Dropped-frame counter unavailable'))
    used, total = values('gpu_mem_used'), values('total_gpu_mem')
    if used and total and min(total) > 0:
        ratio = max(used)/min(total)
        rows.append(('WARN' if ratio >= .9 else 'PASS', 'GPU memory',
                     '{:.0f} / {:.0f} MB peak reported usage ({:.0%})'.format(max(used), min(total), ratio)))
    else:
        rows.append(('WARN', 'GPU memory', 'GPU memory telemetry unavailable'))
    return rows


def summary(rows):
    return '{} errors, {} warnings | snapshot only; verify physical outputs/audio'.format(
        sum(row[0] == 'ERROR' for row in rows), sum(row[0] == 'WARN' for row in rows))


def _publish(show, rows):
    table = show.op('readiness_report')
    table.clear()
    table.appendRow(['Level', 'Check', 'Result'])
    table.appendRow(['INFO', 'Checked locally', time.strftime('%Y-%m-%d %H:%M:%S')])
    for row in rows:
        table.appendRow(list(row))
    show.par.Readinessstatus = summary(rows)
    show.par.Status = 'Pre-show: ' + summary(rows)
    show.store('imagefx_readiness_rows', list(rows))


def check(show, media_problems):
    """Inspect only: no cue changes, seeks, output opens, unmute or blackout release."""
    import td
    rows = [('ERROR', 'Media', str(problem)) for problem in media_problems]
    if not media_problems:
        rows.append(('PASS', 'Media', 'Referenced files and saved workflow orders validated; decoding requires Preload'))
    cues = show.ext.ShowControlExt.document['cues']
    if not cues:
        rows.append(('WARN', 'Cues', 'Show has no cues'))
    show.par.Readinessmedia = '{} cue(s); {} media/order problem(s)'.format(len(cues),len(media_problems))
    gpu = str(getattr(td.sysinfo, 'GPUName', '') or 'Unavailable')
    show.par.Readinessgpu = gpu
    rows.append(('PASS' if 'nvidia' in gpu.lower() else 'WARN', 'Render GPU',
                 gpu + ' | renderer identity only; CUDA workers require their own status checks'))
    try:
        _, outputs = show.op('show_output_mode').module.check(show)
        rows.append(('PASS', 'Output configuration', outputs))
    except Exception as exc:
        outputs = str(exc)
        rows.append(('ERROR', 'Output configuration', outputs))
    show.par.Readinessoutputs = outputs[:500]
    if bool(show.par.Masterblackout):
        rows.append(('WARN', 'Blackout', 'Master blackout is ON (left unchanged)'))
    wall = show.parent().op('wall_output')
    if show.par.Outputmode == 'wall' and wall is not None:
        if not bool(wall.par.Enabled) or bool(wall.par.Blackout):
            rows.append(('WARN', 'Wall feeds', 'Wall feeds are disabled or blacked out'))
        if wall.par.Sourcemode != 'show':
            rows.append(('WARN', 'Wall source', 'Wall source is not Show Control'))
        if bool(wall.par.Testpattern):
            rows.append(('WARN', 'Calibration', 'Wall calibration pattern is ON'))
        if not bool(wall.par.Monitorenabled):
            rows.append(('WARN', 'Confidence monitor', 'Confidence quadrant is disabled'))
    if not any(w is not None and w.isOpen for w in show.op('show_output_mode').module.windows(show)):
        rows.append(('WARN', 'Output windows', 'All output windows are closed (left unchanged)'))
    audio_cues = any(c['enabled'] and (c['kind']=='audio' or c.get('movie_audio')) for c in cues)
    audio_ready = bool(show.par.Audioenabled) and not bool(show.par.Audiomute) and float(show.par.Mastervolume)>0
    audio = ('Audio cues present; ' if audio_cues else 'No enabled audio cues; ') + (
        'software audio enabled; speakers/headphone routing still need audition' if audio_ready else 'audio disabled/muted/zero level')
    show.par.Readinessaudio = audio
    rows.append(('WARN' if audio_cues and not audio_ready else 'INFO', 'Stereo audio', audio))
    perf = show.op('readiness_performance')
    perf.cook(force=True)
    channel = perf['ac_line_status']
    power = float(channel[0]) if channel is not None else None
    show.par.Readinesspower = 'AC connected' if power == 1 else 'Battery / AC disconnected' if power == 0 else 'Power telemetry unavailable'
    rows.append(('PASS' if power == 1 else 'WARN', 'Power', show.par.Readinesspower.eval()))
    for index, state in show.ext.ShowControlExt.prepared.items():
        if state.get('error'):
            rows.append(('ERROR', 'Preload', str(state['error'])))
        elif state.get('loading'):
            rows.append(('WARN', 'Preload', 'A cue is still preparing'))
    rows.append(('INFO', 'Performance', 'Run Sample Performance with representative cues; idle/blackout measurements are not a show test'))
    rows.append(('INFO', 'Hardware', 'Verify projector order, masks, focus, EDID/refresh and stereo audio in rehearsal'))
    show.par.Readinessperformance = 'Not sampled for this check'
    _publish(show, rows)
    return rows


def _later(show, token):
    import td
    td.run("s=op(args[0]); r=s.op('show_readiness') if s else None; "
           "r.module.sample_step(s,args[1]) if r else None", show.path, token,
           delayFrames=1, fromOP=show)


def sample_start(show):
    if show.fetch(SAMPLE_KEY, None, search=False):
        raise ValueError('A performance sample is already running')
    duration, target = float(show.par.Sampleduration), float(show.par.Targetfps.eval())
    if not math.isfinite(duration) or not 1 <= duration <= 30:
        raise ValueError('Sample duration must be 1 to 30 seconds')
    performance_report([], target)  # Validate without changing runtime configuration.
    job = dict(id=uuid.uuid4().hex, end=time.monotonic()+duration, samples=[], target=target, frame=None)
    show.store(SAMPLE_KEY,job)
    show.par.Readinessperformance = 'Sampling current workload; cues and output settings are unchanged...'
    _later(show,job['id'])


def sample_step(show, token):
    import td
    job = show.fetch(SAMPLE_KEY,None,search=False)
    if not job or job['id'] != token:
        return
    try:
        perf=show.op('readiness_performance')
        perf.cook(force=True)
        frame=td.absTime.frame
        if frame != job['frame']:
            job['frame']=frame
            job['samples'].append({name: float(perf[name][0]) if perf[name] is not None else None for name in CHANNELS})
        if time.monotonic()<job['end']:
            _later(show,token)
            return
        rows=performance_report(job['samples'],job['target'])
        show.par.Readinessperformance=' | '.join(row[2] for row in rows)[:1000]
        base=[row for row in show.fetch('imagefx_readiness_rows',[],search=False)
              if row[1] not in ('Performance','Dropped frames','GPU memory')]
        _publish(show,base+rows+[('INFO','Sample scope','Current workload only; repeat after cue/output changes; physical rehearsal still required')])
    except Exception as exc:
        show.par.Readinessperformance='Sample failed: '+str(exc)[:500]
    show.unstore(SAMPLE_KEY)


def on_pulse(show,name):
    try:
        if name == 'Readinesscheck': show.ext.ShowControlExt.Preflight()
        elif name == 'Readinesssample': sample_start(show)
        elif name == 'Readinessreport': show.op('readiness_report').openViewer()
    except Exception as exc:
        show.par.Readinessstatus='Check failed: '+str(exc)[:500]


def guard_legacy_callback(text):
    guard = "    if par.name in parent().op('show_readiness').module.ACTION_NAMES:\n        return\n"
    return text if guard in text else text.replace('def onPulse(par):\n', 'def onPulse(par):\n' + guard, 1)


def install(show):
    import td
    page=next((p for p in show.customPages if p.name=='Pre-Show Check'),None) or show.appendCustomPage('Pre-Show Check')
    for name,label in (('Readinesscheck','Run Pre-Show Check'),('Readinesssample','Sample Current Performance'),('Readinessreport','Open Full Report')):
        if show.par[name] is None: page.appendPulse(name,label=label)
    for name,label,default in (('Readinessstatus','Readiness Snapshot','Not checked'),('Readinessgpu','Selected Render GPU','Not checked'),
            ('Readinessmedia','Media / Workflow','Not checked'),('Readinessoutputs','Output Configuration','Not checked'),
            ('Readinessaudio','Stereo Audio','Not checked'),('Readinesspower','Power Supply','Not checked'),
            ('Readinessperformance','Sample Results','Not sampled')):
        if show.par[name] is None:
            p=page.appendStr(name,label=label)[0]; p.default=p.val=default; p.readOnly=True
    for name,label,kind,default,low,high in (('Cuewarmframes','Cue Warm-up (rendered frames)','Int',3,1,12),
                                          ('Sampleduration','Performance Sample (seconds)','Float',5,1,30)):
        if show.par[name] is None:
            p=getattr(page,'append'+kind)(name,label=label)[0]
            p.default=p.val=default; p.min=p.normMin=low; p.max=p.normMax=high; p.clampMin=p.clampMax=True
    if show.par['Targetfps'] is None:
        p=page.appendMenu('Targetfps',label='Performance Target FPS')[0]
        p.menuNames=p.menuLabels=['24','25','30','50','60']; p.default=p.val='30'
    runtime=show.op('show_readiness') or show.create(td.textDAT,'show_readiness')
    runtime.name='show_readiness'; runtime.text=Path(__file__).read_text(encoding='utf-8')
    table=show.op('readiness_report') or show.create(td.tableDAT,'readiness_report')
    table.name='readiness_report'
    perf=show.op('readiness_performance') or show.create(td.performCHOP,'readiness_performance')
    perf.name='readiness_performance'
    for name in ('fps','msec','droppedframes','gpumemused','totalgpumem','aclinestatus'):
        if perf.par[name] is not None: perf.par[name]=True
    callback=show.op('readiness_callbacks') or show.create(td.parameterexecuteDAT,'readiness_callbacks')
    callback.name='readiness_callbacks'; callback.par.active=False
    callback.par.op='..'; callback.par.pars='Readinesscheck Readinesssample Readinessreport'
    callback.par.custom=True; callback.par.builtin=False; callback.par.valuechange=False; callback.par.onpulse=True
    callback.text="def onPulse(par):\n    parent().op('show_readiness').module.on_pulse(parent(),par.name)\n"
    callback.par.active=True
    legacy = show.op('show_parameters')
    if legacy is not None:
        legacy.text = guard_legacy_callback(legacy.text)
    show.par.Preflight.label='Run Pre-Show Check'
    show.unstore(SAMPLE_KEY)
    return runtime
