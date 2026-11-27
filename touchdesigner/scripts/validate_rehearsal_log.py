"""Exercise the shipped logger, real cue frames, and recorder in an off-air copy."""

import copy
import json
from pathlib import Path
import runpy
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT/'build/rehearsal-log/native-validation.json'


class Audit:
    def __init__(self):
        import td
        self.td = td
        self.original = td.op('/project1/imagefx_demo/show_control')
        runpy.run_path(str(ROOT/'touchdesigner/scripts/validate_show_readiness.py'))['_require_safe_session'](self.original)
        assert self.original.ext.ShowControlExt._rehearsal is None, 'Save the current rehearsal log first'
        project = td.op('/project1')
        assert project.op('rehearsal_log_qa') is None, 'Rehearsal QA already exists'
        self.document = copy.deepcopy(self.original.ext.ShowControlExt.document)
        self.original_data = self.original.op('show_data').text
        self.task = 'rehearsal-log-' + uuid.uuid4().hex[:8]
        self.folder = ROOT/'build/task-artifacts'/self.task
        self.folder.mkdir(parents=True)
        self.base = project.create(td.baseCOMP, 'rehearsal_log_qa')
        self.base.copy(self.original.parent().op('wall_output'), name='wall_output')
        self.show = self.base.copy(self.original, name='show_control')
        self.export = self.show.op('show_review_export').module
        self.checks, self.measurements = {}, {}
        self.deadline = time.monotonic() + 90
        self.steps = self.cases()
        self.schedule(8)

    def check(self, name, condition):
        self.checks[name] = bool(condition)
        assert condition, name

    def schedule(self, frames=1):
        self.td.run('args[0].advance()', self, delayFrames=frames)

    def advance(self):
        try:
            assert time.monotonic() < self.deadline, 'Rehearsal test timed out'
            next(self.steps)
        except StopIteration:
            self.finish()
        except Exception:
            self.finish(traceback.format_exc())
        else:
            self.schedule()

    def wait_for(self, predicate, *, render=False):
        while not predicate():
            if render:
                # Simulate a consumer, independent of the logger. Nothing is
                # connected to an audience window in this disposable network.
                self.show.op('mapped1').cook(force=True)
            yield

    def cases(self):
        show = self.show
        ext = show.ext.ShowControlExt
        self.check('clean_default_log_off', ext._rehearsal is None and not show.par.Rehearsalresult.eval())
        show.par.Renderwidth, show.par.Renderheight = 320, 180
        show.par.Masterblackout, show.par.Audioenabled = True, False
        show.par.Output1width, show.par.Output1height = 320, 180
        show.par.Targetfps = '30'
        cues = [
            dict(ext.model.new_cue(), name='Fixture: manual', prewait=.2, duration=0, fade=0, follow='continue', postwait=.3),
            dict(ext.model.new_cue(), name='Fixture: continuation', duration=0, fade=.45),
            dict(ext.model.new_cue(), name='Fixture: blackout', kind='blackout', duration=0, fade=.2),
        ]
        ext._replace_cues(cues)
        initial = copy.deepcopy(ext.document)
        show.par.Rehearsalstart.pulse()
        yield from self.wait_for(lambda: ext._rehearsal is not None)
        capture = ext._rehearsal
        capture.directory = self.folder.resolve()  # Sandbox only; do not write private .imagefx logs.
        self.check('observer_attached_on_pulse', ext.engine.rehearsal_observer == capture.event)
        self.check('start_never_arms_playback', not ext.engine.triggered and ext.engine.state == 'stopped'
                   and show.par.Masterblackout and not show.par.Audioenabled)
        show.par.Rehearsalstart.pulse()
        yield
        self.check('duplicate_start_preserves_capture', ext._rehearsal is capture and 'existing' in show.par.Rehearsalstatus.eval())

        show.par.Gocue.pulse()
        yield from self.wait_for(lambda: ext.engine.state == 'running', render=True)
        show.par.Rehearsalsave.pulse()
        yield
        self.check('save_during_transport_is_guarded', ext._rehearsal is capture
                   and capture.history.ended is None and 'Stop transport' in show.par.Rehearsalstatus.eval())
        first, second, blackout = [cue['id'] for cue in cues]
        def rendered(cue_id):
            row = capture.history.started.get(cue_id)
            return row is not None and row.first_frame_s is not None
        yield from self.wait_for(lambda: rendered(first) and rendered(second), render=True)
        yield from self.wait_for(lambda: not ext.tracks[1]['fading'], render=True)
        self.check('manual_then_continue_still_running', not ext.engine.errors
                   and ext.tracks[1]['cue']['id'] == second and int(show.par.Selectedcue) == 3)
        measured = capture.history.report()
        a, b = measured['cue_attempts']
        self.check('manual_request_and_real_frame', a['trigger'] == 'go' and a['request_to_start_ms'] >= 180
                   and a['request_to_first_render_ms'] >= a['request_to_start_ms'])
        self.check('continuation_request_and_real_frame', b['trigger'] == 'auto_next'
                   and b['request_to_first_render_ms'] >= b['request_to_start_ms'] >= 0)
        self.check('crossfade_wait_and_render_separate', a['waiting']['sampled_frames'] > 0
                   and b['transition']['sampled_frames'] > 0 and b['transition_type'] == 'crossfade'
                   and b['from_cue'] == 1 and b['playing']['worst_ms'] > 0)

        show.par.Reviewprojector = '1'
        show.par.Exportsource, show.par.Exportcodec, show.par.Exportfps = 'review', 'h264', '30'
        show.par.Exportduration, show.par.Wallrecordwarmup = 1, 0
        show.par.Exportfolder = str(self.folder/'recordings')
        show.par.Startexport.pulse()
        yield from self.wait_for(lambda: (show.fetch(self.export.JOB_KEY, {}, search=False) or {}).get('stage') == 'recording'
                                 or 'FAILED' in show.par.Exportstatus.eval())
        self.check('actual_review_writer_started', bool(show.fetch(self.export.JOB_KEY, None, search=False)))
        show.par.Gocue.pulse()
        yield from self.wait_for(lambda: blackout in ext.engine.completed_blackouts, render=True)
        yield from self.wait_for(lambda: not show.fetch(self.export.JOB_KEY, None, search=False))
        self.check('native_recorder_finished', show.par.Exportstatus.eval().startswith('COMPLETE'))
        show.par.Stopall.pulse()
        yield from self.wait_for(lambda: ext.engine.state == 'stopped')
        show.par.Rehearsalsave.pulse()
        yield from self.wait_for(lambda: bool(show.par.Rehearsalresult.eval()))
        path = self.folder/show.par.Rehearsalresult.eval()
        payload = json.loads(path.read_text(encoding='utf-8'))
        self.check('save_detaches_and_writes_valid_report', ext._rehearsal is None
                   and ext.engine.rehearsal_observer is None and payload['end_reason'] == 'operator_stop')
        self.check('table_contains_log', show.op('rehearsal_report').numRows >= 8)
        black = payload['cue_attempts'][2]
        self.check('blackout_has_transition_but_no_fake_first_frame', black['status'] == 'completed'
                   and black['transition']['sampled_frames'] > 0 and black['request_to_first_render_ms'] is None)
        recording, = payload['recordings']
        status = show.par.Exportstatus.eval()
        self.check('encoder_final_counts_not_mixed_with_timeline', recording['source'] == 'review'
                   and recording['outcome'] == 'complete' and recording['written'] == 30
                   and '{} dropped frames'.format(recording['dropped']) in status
                   and payload['playback']['drop_samples'] > 0)
        self.check('document_and_safety_unchanged', initial == ext.document and show.par.Masterblackout
                   and not show.par.Audioenabled and self.base.op('wall_output').par.Blackout)
        self.check('runtime_errors_empty', not show.errors(recurse=True))
        self.measurements.update(playback=payload['playback'], recorder=recording,
                                 cue_attempts=payload['cue_attempts'], export_path=show.par.Exportresult.eval())

    def finish(self, error=None):
        try:
            if self.show.fetch(self.export.JOB_KEY, None, search=False):
                self.export.finish_export(self.show, 'CANCELLED')
            self.show.ext.ShowControlExt.engine.stop()
        finally:
            self.base.destroy()
        self.checks['original_show_unchanged'] = (self.original.ext.ShowControlExt.document == self.document
                                                and self.original.op('show_data').text == self.original_data)
        result = dict(ok=not error and all(self.checks.values()), error=error, task=self.task,
                      checks=self.checks, measurements=self.measurements, hardware_outputs_opened=False,
                      audio_auditioned=False)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('REHEARSAL LOG:', result['ok'], len(self.checks), str(REPORT), error)


def start():
    return Audit()
