"""Off-air real-transport cue-row colors; no show save or audience outputs."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import traceback

ROOT = Path(__file__).resolve().parents[2]


class HighlightChecks:
    def __init__(self, inspect=False):
        import td
        self.td, self.inspect = td, inspect
        self.original = td.op('/project1/imagefx_demo/show_control')
        runpy.run_path(str(ROOT/'touchdesigner/scripts/validate_show_readiness.py'))['_require_safe_session'](self.original)
        if td.op('/project1/imagefx_sandbox') is not None:
            raise RuntimeError('Existing sandbox must not be overwritten')
        self.before = copy.deepcopy(self.original.ext.ShowControlExt.document)
        self.private = ROOT/'.imagefx/shows/current.json'
        self.private_hash = self.private_digest()
        self.base = td.op('/project1').create(td.baseCOMP, 'imagefx_sandbox')
        self.base.copy(self.original.parent().op('wall_output'), name='wall_output')
        self.host = self.base.copy(self.original, name='show_control')
        self.host.op('show_tick').par.active = False
        self.report = dict(ok=False, checks={}, samples={}, hardware_outputs_opened=False,
                           started_at=datetime.now(timezone.utc).isoformat(),
                           source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        self.clock, self.stage, self.wait = 100., 'setup', 0
        self.schedule(8)

    def private_digest(self):
        return hashlib.sha256(self.private.read_bytes()).hexdigest() if self.private.is_file() else None

    def schedule(self, frames=2):
        self.td.run('args[0].step()', self, delayFrames=frames)

    def check(self, name, value):
        self.report['checks'][name] = bool(value)
        if not value:
            raise AssertionError(name)

    def row(self, label, row, expected, selected=None):
        e, h = self.host.ext.ShowControlExt, self.host
        e.Refresh()
        style = e.CueRowStyle(row)
        self.check(label+'_state', style['state'] == expected)
        palette = {'running': (.08,.42,.23), 'fading': (.08,.42,.23),
                   'paused': (.55,.32,.04), 'held': (.07,.31,.36),
                   'error': (.50,.09,.12), 'disabled': (.10,.10,.11)}
        expected_color = palette.get(expected, (.10,.24,.48) if style['selected'] else (.18,.18,.20))
        self.check(label+'_palette', style['color'] == expected_color)
        if selected is not None:
            self.check(label+'_selection', style['selected'] is selected)
        for column in ('cue_row_', 'cue_notes_'):
            button = h.op(column+str(row))
            actual = tuple(float(button.par['color'+axis]) for axis in 'rgb')
            self.check(label+'_'+column+'color', all(abs(a-b)<1e-6 for a,b in zip(actual, style['color'])))
            background = tuple(float(button.par['bgcolor'+axis]) for axis in 'rgb')
            self.check(label+'_'+column+'background', all(abs(a-b)<1e-6 for a,b in zip(background, expected_color))
                       and float(button.par.bgalpha) == 1.)
            self.check(label+'_'+column+'border', all(button.par[edge].eval() == ('bordera' if style['selected'] else 'off')
                       for edge in ('leftborder','rightborder','topborder','bottomborder')))
        marker = {'running':'PLAY', 'fading':'FADE', 'paused':'PAUSE', 'held':'HOLD', 'replaced':'done'}.get(expected, expected)
        text = h.op('cue_row_'+str(row)).par.label.eval()
        self.check(label+'_text_state', not text if expected == 'empty' else text.endswith('| '+marker))
        self.report['samples'][label] = dict(style, label=h.op('cue_row_'+str(row)).par.label.eval())

    def go(self, index, after):
        e = self.host.ext.ShowControlExt
        e.SelectCue(index+1); e.Go()
        self.target, self.after, self.wait, self.stage = index, after, 0, 'wait'

    def finish(self, error=None):
        self.report['original_cues_unchanged'] = self.original.ext.ShowControlExt.document == self.before
        self.report['private_show_unchanged'] = self.private_digest() == self.private_hash
        retain = self.inspect and error is None
        if retain:
            self.host.openViewer()
        else:
            self.host.ext.ShowControlExt.Stopall()
            self.base.destroy()
        self.report['sandbox_retained_for_inspection'] = retain
        self.report['sandbox_removed'] = not retain
        self.report['ok'] = not error and all(self.report['checks'].values()) and self.report['original_cues_unchanged'] and self.report['private_show_unchanged']
        if error:
            self.report['error'] = error
        self.write()

    def write(self):
        self.report['generated_at'] = datetime.now(timezone.utc).isoformat()
        path = ROOT/'build/cue-highlight/native-validation.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.report, indent=2), encoding='utf-8')
        print('CUE HIGHLIGHT:', self.report['ok'], len(self.report['checks']), self.report.get('error'))

    def close_inspection(self):
        """Close the QA viewer first, then remove its disposable network."""
        self.host.ext.ShowControlExt.Stopall()
        self.base.destroy()
        self.report.update(sandbox_removed=True, sandbox_retained_for_inspection=False)
        self.write()

    def step(self):
        try:
            h, e = self.host, self.host.ext.ShowControlExt
            if self.stage == 'setup':
                h.par.Renderwidth, h.par.Renderheight = 160, 90
                self.cues = [dict(e.model.new_cue(), name='Highlight QA '+str(i+1), track=i%3+1,
                                 fade=0, duration=0, notes='Cue note '+str(i+1)) for i in range(15)]
                self.cues[3]['fade'] = 2.
                self.cues[4].update(duration=.5, hold=True)
                e._replace_cues(self.cues)
                e.engine.clock = lambda: self.clock
                e.engine._last = self.clock
                self.go(0, 'first')
            elif self.stage == 'wait':
                e.Tick(); self.wait += 1
                item = e.tracks.get(self.cues[self.target]['track'])
                if (item and item['cue']['id'] == self.cues[self.target]['id']
                        and self.cues[self.target]['id'] not in e.engine.pending):
                    self.stage = self.after
                elif self.wait > 900:
                    raise RuntimeError('GO timed out: '+str(e.engine.errors))
            elif self.stage == 'first':
                self.row('running_not_selected', 0, 'running', False)
                self.row('selected_standby', 1, 'ready', True)
                self.go(1, 'second')
            elif self.stage == 'second':
                self.row('track_one', 0, 'running')
                self.row('track_two', 1, 'running')
                e.Pause()
                self.row('paused_one', 0, 'paused')
                self.row('paused_two', 1, 'paused')
                e.Resume()
                self.row('resumed_one', 0, 'running')
                self.go(2, 'third')
            elif self.stage == 'third':
                self.row('track_three', 2, 'running')
                self.go(3, 'fade')
            elif self.stage == 'fade':
                self.row('outgoing_fade', 0, 'fading')
                self.row('incoming_fade', 3, 'running')
                self.clock += 3.; e.Tick()
                self.row('retired_fade', 0, 'replaced')
                self.row('new_track_one', 3, 'running')
                e.GoBack(); self.target, self.after, self.wait, self.stage = 2, 'back', 0, 'wait'
            elif self.stage == 'back':
                self.row('go_back', 2, 'running')
                self.go(4, 'hold')
            elif self.stage == 'hold':
                self.clock += 1.; e.Tick()
                self.row('held_frame', 4, 'held')
                self.row('replaced_track_two', 1, 'replaced')
                h.par.Cuepage = 2
                self.go(12, 'page')
            elif self.stage == 'page':
                self.row('page_two_running', 0, 'running', False)
                self.row('page_two_selected', 1, 'ready', True)
                self.row('unused_row', 11, 'empty', False)
                e.Stopall()
                self.row('stop_clears_play', 0, 'ready', False)
                h.par.Cuepage = 1
                self.row('page_one_no_stale_play', 0, 'ready')
                self.check('no_native_errors_or_warnings', not h.errors(recurse=True) and not h.warnings(recurse=True))
                self.check('transport_disarmed', e.engine.state == 'stopped' and h.par.Masterblackout and not h.par.Audioenabled)
                if self.inspect:
                    self.go(0, 'inspect_first')
                else:
                    self.finish(); return
            elif self.stage == 'inspect_first':
                self.go(1, 'inspect_second')
            elif self.stage == 'inspect_second':
                e.SelectCue(3)
                self.finish(); return
            self.schedule()
        except Exception:
            self.finish(traceback.format_exc())


def start(inspect=False):
    return HighlightChecks(inspect)
