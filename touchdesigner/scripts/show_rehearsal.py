"""Opt-in cue rehearsal logger. Observes the frame loop; never cooks a TOP."""

from pathlib import Path
import time
import uuid

from tdimagefx.jsonutil import atomic_write_json
from tdimagefx.rehearsal import RehearsalLog


ACTIONS = ('Rehearsalstart', 'Rehearsalsave', 'Rehearsalreport')
IDLE = 'Off — start before GO; stop transport and any recording before saving.'
JOB_KEY = 'imagefx_export_job'


class Capture:
    def __init__(self, show, ext):
        self.show, self.ext = show, ext
        self.engine = ext.engine
        self.history = RehearsalLog(float(show.par.Targetfps.eval()))
        self.perf = show.op('readiness_performance')
        self.sources = {(track, side): show.op('track{}_source{}'.format(track, side))
                        for track in (1, 2, 3) for side in (0, 1)}
        self.numbers = {cue['id']: index + 1 for index, cue in enumerate(self.engine.cues)}
        self.render_watermarks = {}
        self.context = dict(output_mode=show.par.Outputmode.eval(), routing=show.par.Routingmode.eval(),
                            render_width=int(show.par.Renderwidth), render_height=int(show.par.Renderheight),
                            master_blackout=bool(show.par.Masterblackout))
        self.directory = Path(show.par.Libraryroot.eval()).resolve()
        existing = show.fetch(JOB_KEY, None, search=False)
        if existing:
            self.recording(existing, preexisting=True)

    def attach(self):
        self.engine.rehearsal_observer = self.event

    def freeze(self, reason):
        self.history.freeze(reason)
        if self.engine.rehearsal_observer == self.event:
            self.engine.rehearsal_observer = None

    def failed(self):
        self.freeze('sampling_error')
        self.show.par.Rehearsalstatus = 'Log paused after a telemetry error; Stop & Save can keep the captured data.'

    def event(self, event, cue, index, detail):
        try:
            row = self.history.event(event, cue, index, detail)
            if row is None or event != 'started':
                return
            if cue['kind'] == 'visual':
                deck = self.ext.tracks[cue['track']]
                source = self.sources[cue['track'], deck['side']]
                if source is not None:
                    # Separate a new render from any cook during preloading.
                    # Frame End may observe the prior frame's render stamp.
                    self.render_watermarks[cue['id']] = source.cookAbsFrame
                previous = deck.get('old')
                if 'interpolation' in deck:
                    row.transition_type = 'parameter_interpolation'
                    row.from_cue = self.numbers.get(deck.get('previous_cue_id'))
                else:
                    row.transition_type = ('cut' if not cue['fade'] else 'crossfade' if previous else 'fade_in')
                    row.from_cue = self.numbers.get(previous['cue']['id']) if previous else None
            elif cue['kind'] == 'blackout':
                row.transition_type = 'blackout'
        except Exception:
            self.failed()

    def recording(self, job, outcome=None, *, preexisting=False):
        settings = job['settings']
        self.history.recording(job['id'], settings['source'], settings['fps'], job.get('index', 0),
                               job.get('dropped', 0), preexisting=preexisting, outcome=outcome)

    def sample(self):
        if self.history.ended is not None:
            return
        if self.ext.engine is not self.engine:
            self.freeze('cue_list_changed')
            self.show.par.Rehearsalstatus = 'Log paused because a different cue list loaded; Stop & Save to keep it.'
            return
        job = self.show.fetch(JOB_KEY, None, search=False)
        if job:
            self.recording(job)
        if self.engine.state != 'running':
            return
        import td
        frame = td.absTime.frame
        if frame == self.history.last_frame:
            return
        playing, transitions, rendered = set(), set(), set()
        for track, deck in self.ext.tracks.items():
            cue_id = deck['cue']['id']
            playing.add(cue_id)
            if deck.get('fading'):
                transitions.add(cue_id)
                if deck.get('old'):
                    playing.add(deck['old']['cue']['id'])
            row = self.history.started.get(cue_id)
            if row is not None and row.first_frame_s is None and cue_id in self.render_watermarks:
                # The on-air select TOP is also used by per-cue routing. Do
                # not mistake an earlier standby-deck warm-up for playback.
                source = self.sources[track, deck['side']]
                if source is not None and source.cookAbsFrame > self.render_watermarks[cue_id]:
                    rendered.add(cue_id)
                    self.render_watermarks.pop(cue_id)
        for fade in self.ext._level_fades.values():
            transitions.add(fade['cue']['id'])
        playing.update(cue_id for cue_id, item in self.ext.audio.items() if item['started'] is not None)
        if not (playing or transitions or self.engine.pending or self.ext.automations):
            return
        self.perf.cook()
        channels = [self.perf[name] for name in ('msec', 'dropped_frames', 'gpu_mem_used')]
        values = [float(channel[0]) if channel is not None else None for channel in channels]
        self.history.sample(frame, *values, playing, transitions, rendered)

    def report(self):
        return dict(self.history.report(), initial_context=self.context)


def start(show):
    ext = show.ext.ShowControlExt
    if ext._rehearsal is not None:
        raise ValueError('Use Stop & Save for the existing rehearsal log first.')
    capture = Capture(show, ext)
    capture.attach()
    ext._rehearsal = capture
    show.par.Rehearsalstatus = 'Capturing cue timings and performance — no video or audio is recorded.'


def _publish(show, report):
    def cell(value):
        return '—' if value is None else str(value)

    table = show.op('rehearsal_report')
    table.clear()
    table.appendRow(['Rehearsal Log', 'Target FPS', report['target_fps'],
                     'Render frame budget (ms)', report['frame_budget_ms']])
    playback = report['playback']
    table.appendRow(['Playback across all tracks', 'Frames sampled', playback['sampled_frames'],
                     'Timeline drops', cell(playback['timeline_drops']),
                     'Peak GPU MB', cell(playback['peak_gpu_mb'])])
    table.appendRow(['Cue', 'Title', 'Trigger', 'Result', 'GO → start ms', 'GO → rendered ms',
                     'Worst playing ms', 'Timeline drops while playing', 'Peak GPU MB while playing',
                     'Transition', 'Worst transition ms', 'Timeline drops during transition', 'Peak GPU MB during transition'])
    for row in report['cue_attempts']:
        playing, transition = row['playing'], row['transition']
        table.appendRow([cell(value) for value in (
            row['cue_number'], row['name'], row['trigger'], row['status'], row['request_to_start_ms'],
            row['request_to_first_render_ms'], playing['worst_ms'], playing['timeline_drops'],
            playing['peak_gpu_mb'], row['transition_type'], transition['worst_ms'],
            transition['timeline_drops'], transition['peak_gpu_mb'])])
    if report['recordings']:
        table.appendRow(['Real-time recorder', 'FPS', 'Frames written', 'Encoder drops', 'Result'])
    for row in report['recordings']:
        table.appendRow([row[key] for key in ('source', 'fps', 'written', 'dropped', 'outcome')])
    if report['limit_reached']:
        table.appendRow(['Capture limit reached; newer attempts or recording jobs were omitted.'])


def save(show):
    ext = show.ext.ShowControlExt
    capture = ext._rehearsal
    if capture is None:
        raise ValueError('There is no rehearsal log to save.')
    if ext.engine.state != 'stopped' or show.fetch(JOB_KEY, None, search=False):
        raise ValueError('Stop transport and finish or stop any recording before saving. Log retained.')
    capture.freeze('operator_stop')
    report = capture.report()
    folder = (capture.directory / '.imagefx' / 'rehearsals').resolve()
    if not folder.is_relative_to(capture.directory):
        raise ValueError('Rehearsal folder must stay inside the local library checkout.')
    path = folder / ('rehearsal-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex + '.json')
    atomic_write_json(path, report)
    ext._rehearsal = None
    show.par.Rehearsalresult = str(path.relative_to(capture.directory))
    show.par.Rehearsalstatus = 'Saved: {} cue attempts and {} recording jobs{}'.format(
        len(report['cue_attempts']), len(report['recordings']), ' (capture limit reached)' if report['limit_reached'] else '')
    _publish(show, report)
    return path


def on_pulse(show, name):
    try:
        if name == 'Rehearsalstart':
            start(show)
        elif name == 'Rehearsalsave':
            save(show)
        elif name == 'Rehearsalreport':
            if not show.par.Rehearsalresult.eval():
                raise ValueError('Save a rehearsal log before opening the report.')
            show.op('rehearsal_report').openViewer()
    except Exception as exc:
        # Use the logger's own status line, never overwrite transport errors.
        show.par.Rehearsalstatus = ('Log could not be saved; captured data retained. Try Stop & Save again.'
                                    if isinstance(exc, OSError) else str(exc)[:300])


def install(show):
    import td
    page = next(p for p in show.customPages if p.name == 'Pre-Show Check')
    for name, label in zip(ACTIONS, ('Start Rehearsal Log', 'Stop & Save Rehearsal Log', 'Open Rehearsal Log')):
        if show.par[name] is None:
            page.appendPulse(name, label=label)
    for name, label, default in (('Rehearsalstatus', 'Rehearsal Log Status', IDLE), ('Rehearsalresult', 'Last Local Log', '')):
        if show.par[name] is None:
            par = page.appendStr(name, label=label)[0]
            par.default = par.val = default
            par.readOnly = True
    runtime = show.op('show_rehearsal') or show.create(td.textDAT, 'show_rehearsal')
    runtime.text = Path(__file__).read_text(encoding='utf-8')
    if show.op('rehearsal_report') is None:
        show.create(td.tableDAT, 'rehearsal_report')
    callback = show.op('rehearsal_callbacks') or show.create(td.parameterexecuteDAT, 'rehearsal_callbacks')
    callback.par.active = False
    callback.par.op, callback.par.pars = '..', ' '.join(ACTIONS)
    callback.par.custom, callback.par.builtin = True, False
    callback.par.valuechange, callback.par.onpulse = False, True
    callback.text = "def onPulse(par):\n    parent().op('show_rehearsal').module.on_pulse(parent(), par.name)\n"
    callback.par.active = True
    legacy = show.op('show_parameters')
    guard = "    if par.name in " + repr(ACTIONS) + ":\n        return\n"
    if guard not in legacy.text:
        legacy.text = legacy.text.replace('def onPulse(par):\n', 'def onPulse(par):\n' + guard, 1)
    return runtime
