"""Off-air native Output Mode checks. Never opens any physical output."""
import copy
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(write_report=True):
    original = op('/project1/imagefx_demo/show_control')
    document = copy.deepcopy(original.ext.ShowControlExt.document)
    host = op('/project1').create(baseCOMP, 'output_mode_qa')
    wall = host.copy(original.parent().op('wall_output'), name='wall_output')
    show = host.copy(original, name='show_control')
    show.op('show_tick').par.active = False
    runtime = show.op('show_output_mode').module
    checks = {}
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(), hardware_output_tested=False)
    try:
        checks['default_wall_mode'] = show.par.Outputmode.eval() == 'wall'
        checks['two_clear_mode_labels'] = list(show.par.Outputmode.menuNames) == ['direct', 'wall']
        checks['output_page_second'] = [p.name for p in show.customPages][:2] == ['Transport', 'Output Mode']
        checks['output_page_visible'] = "'Output Mode'" in show.op('cue_inspector').par.pagescope.eval()
        checks['master_blackout_alias'] = show.par.Outputblackout.bindMaster == show.par.Masterblackout
        checks['processor_display_alias'] = show.par.Outputwalldisplay.bindMaster == wall.par.Displayindex
        checks['wall_blackout_alias'] = show.par.Outputwallblackout.bindMaster == wall.par.Blackout
        for selected in ('direct', 'wall'):
            show.par.Outputmode = selected
            checks['review_follows_' + selected] = show.par.Reviewroute.eval() == ('atlas' if selected == 'direct' else 'wall')
            checks['mode_description_' + selected] = bool(show.par.Outputsummary.eval())
            checks['direct_settings_enabled_' + selected] = bool(show.par.Directdisplay1.enable) == (selected == 'direct')
            checks['wall_settings_enabled_' + selected] = bool(show.par.Outputwalldisplay.enable) == (selected == 'wall')
        checks['review_route_readonly'] = show.par.Reviewroute.readOnly
        show.par.Outputmode = 'direct'
        for i in (1, 2, 3):
            w = show.op('direct_window{}'.format(i))
            checks['direct_feed_' + str(i)] = w.par.winop.eval() == show.op('out{}_projector'.format(i))
            checks['window_native_fill_' + str(i)] = w.par.size == 'fill' and w.par.dpiscaling == 'native' and not w.par.borders
            for value in (-1, 0, 31):
                show.par['Directdisplay{}'.format(i)] = value
                checks['display_{}_{}'.format(i, value)] = w.par.display.eval() == max(0, value)
            show.par['Directdisplay{}'.format(i)] = -1
            for width, height in ((1920, 1080), (3840, 2160), (1280, 720)):
                show.par['Output{}width'.format(i)] = width
                show.par['Output{}height'.format(i)] = height
                feed = show.op('out{}_projector'.format(i))
                feed.cook(force=True)
                checks['resolution_{}_{}'.format(i, width)] = (feed.width, feed.height) == (width, height)
        for action in ('Checkoutput', 'Openoutput'):
            checks['unassigned_direct_' + action] = runtime.on_pulse(show, action) is False
        show.par.Outputmode = 'wall'
        wall.par.Displayindex = -1
        for action in ('Checkoutput', 'Openoutput'):
            checks['unassigned_wall_' + action] = runtime.on_pulse(show, action) is False
        checks['close_all_dispatch'] = runtime.on_pulse(show, 'Closealloutputs') is True
        checks['all_windows_closed'] = not any(w is not None and w.isOpen for w in runtime.windows(show))
        checks['blackouts_preserved'] = bool(show.par.Masterblackout) and bool(wall.par.Blackout)
        before = copy.deepcopy(show.ext.ShowControlExt.document)
        path = ROOT / 'touchdesigner/scripts/show_output_mode.py'
        scope = dict(globals(), __file__=str(path), __name__='_output_reinstall')
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), scope)
        count = len(show.customPars)
        scope['install'](show)
        checks['reinstall_no_duplicate_parameters'] = len(show.customPars) == count
        checks['reinstall_preserves_cues'] = show.ext.ShowControlExt.document == before
        checks['original_cues_untouched'] = original.ext.ShowControlExt.document == document
        checks['no_operator_errors'] = not show.errors(recurse=True)
        report['ok'] = all(checks.values())
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        report['checks'] = checks
        host.destroy()
    if write_report:
        target = ROOT / 'build/envoy-validation/output-mode.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def validate_deferred():
    """Exercise real parameter/pulse events over TD frames, no window opens."""
    original = op('/project1/imagefx_demo/show_control')
    host = op('/project1').create(baseCOMP, 'output_mode_events_qa')
    wall = host.copy(original.parent().op('wall_output'), name='wall_output')
    show = host.copy(original, name='show_control')
    show.op('show_tick').par.active = False
    runtime = show.op('show_output_mode').module
    checks, closes, pulses = {}, [], []
    close = runtime.close_all
    dispatch = runtime.on_pulse
    def record_close(owner):
        closes.append(owner.path)
        return close(owner)
    def record_pulse(owner, name):
        pulses.append(name)
        return dispatch(owner, name)
    runtime.close_all, runtime.on_pulse = record_close, record_pulse
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(), hardware_output_tested=False)
    def events():
        yield
        yield
        closes.clear(); pulses.clear()
        show.par.Outputmode = 'direct'
        yield
        checks['mode_event_closes_once'] = len(closes) == 1
        checks['review_updates_on_mode_event'] = show.par.Reviewroute == 'atlas'
        closes.clear()
        show.par.Directdisplay1 = 31
        yield
        checks['display_change_closes_once'] = len(closes) == 1
        show.par.Directdisplay1 = -1
        yield
        show.par.Openoutput.pulse()
        yield
        checks['direct_open_dispatched_once'] = pulses == ['Openoutput']
        checks['direct_invalid_stays_closed'] = show.par.Outputstatus.eval().startswith('NOT OPENED:')
        pulses.clear()
        show.par.Outputmode = 'wall'
        wall.par.Displayindex = -1
        yield
        show.par.Checkoutput.pulse()
        yield
        checks['check_dispatched_once'] = pulses == ['Checkoutput']
        pulses.clear()
        show.par.Openoutput.pulse()
        yield
        checks['wall_open_dispatched_once'] = pulses == ['Openoutput']
        checks['wall_invalid_stays_closed'] = show.par.Outputstatus.eval().startswith('NOT OPENED:')
        pulses.clear()
        show.par.Closealloutputs.pulse()
        yield
        checks['close_dispatched_once'] = pulses == ['Closealloutputs']
        checks['blackouts_unchanged'] = bool(show.par.Masterblackout) and bool(wall.par.Blackout)
        checks['no_window_opened'] = not any(w is not None and w.isOpen for w in runtime.windows(show))
        checks['no_callback_errors'] = not show.errors(recurse=True)
    sequence = events()
    def finish():
        report['checks'] = checks
        report['ok'] = not report.get('error') and all(checks.values())
        runtime.close_all, runtime.on_pulse = close, dispatch
        host.destroy()
        (ROOT / 'build/envoy-validation/output-mode-events.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('OUTPUT MODE NATIVE EVENTS:', report)
    def advance():
        try:
            next(sequence)
        except StopIteration:
            finish()
        except Exception:
            report['error'] = traceback.format_exc()
            finish()
        else:
            run('args[0]()', advance, delayFrames=1)
    run('args[0]()', advance, delayFrames=1)


if __name__ == '__main__':
    print(validate())
