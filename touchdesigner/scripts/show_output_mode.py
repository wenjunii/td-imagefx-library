"""Physical delivery controls, independent of cue tracks and content routing.

Embedded in Show Control. All windows start closed; mode/display edits close
outputs and require an explicit Open. No action releases either blackout.
"""
from pathlib import Path

ACTIONS = ('Checkoutput', 'Openoutput', 'Closealloutputs')
DIRECT_NAMES = tuple('direct_window{}'.format(i) for i in (1, 2, 3))


def windows(show):
    wall = show.parent().op('wall_output')
    return [show.op(n) for n in (*DIRECT_NAMES, 'audience_window')] + [
        wall.op('wall_window') if wall is not None else None]


def close_all(show):
    for window in windows(show):
        if window is not None:
            window.par.winclose.pulse()


def direct_plan(indices, displays, allow_primary=False):
    """Validate the complete plan before opening any window; -1 is unused."""
    chosen = []
    for projector, index in enumerate(indices, 1):
        if index == -1:
            continue
        display = next((d for d in displays if d['index'] == index), None)
        if display is None:
            raise ValueError('P{}: display {} is not connected'.format(projector, index))
        if display['primary'] and not allow_primary:
            raise ValueError('P{}: primary/operator display is protected'.format(projector))
        if any(d['index'] == index for _, d in chosen):
            raise ValueError('Each projector must use a different display index')
        chosen.append((projector, display))
    if not chosen:
        raise ValueError('Select at least one Direct Display index; -1 means unused')
    return chosen


def _wall(show):
    wall = show.parent().op('wall_output')
    if wall is None:
        raise ValueError('Wall Output is unavailable')
    return wall


def summary(show):
    if show.par.Outputmode == 'wall':
        return '3840 x 2160 | TL=P1, TR=P2, BL=P3, BR=confidence | 1080p per tile'
    return 'Separate display windows | set display indices below; resolution on Output 1 / 2 / 3'


def window_status(show):
    opened = [w.name for w in windows(show) if w is not None and w.isOpen]
    return 'OPEN: ' + ', '.join(opened) if opened else 'All output windows closed'


def check(show):
    wall = _wall(show)
    controller = wall.op('controller').module
    if show.par.Outputmode == 'wall':
        problem = controller.check_display(wall)
        if problem:
            raise ValueError(problem)
        return None, '4K processor ready: 3840 x 2160; verify 2x2 / no overscan on hardware'
    if show.par.Outputmode != 'direct':
        raise ValueError('Choose Direct Displays or 4K Wall Processor')
    displays = controller.refresh_displays(wall)
    plan = direct_plan([int(show.par['Directdisplay{}'.format(i)]) for i in (1, 2, 3)],
                       displays, bool(show.par.Directallowprimary))
    details = []
    for i, display in plan:
        feed = show.op('out{}_projector'.format(i))
        feed.cook(force=True)
        if feed.errors(recurse=True):
            raise ValueError('P{} feed has errors; check source, shaders and license'.format(i))
        details.append('P{} {}x{} -> display {} {}x{}'.format(
            i, feed.width, feed.height, display['index'], display['width'], display['height']))
    return plan, ' | '.join(details)


def on_pulse(show, name):
    if name not in ACTIONS:
        return False
    try:
        if name == 'Closealloutputs':
            close_all(show)
            show.par.Outputstatus = 'All output windows closed; cue playback unchanged'
            return True
        if show.fetch('imagefx_export_job', None, search=False):
            raise ValueError('Finish/cancel video export or wall recording before opening or checking outputs')
        plan, message = check(show)
        if name == 'Openoutput':
            # Mutually exclusive routes. Failed validation leaves existing
            # outputs alone; a partial open failure closes the whole group.
            close_all(show)
            try:
                if show.par.Outputmode == 'wall':
                    wall = _wall(show)
                    wall.op('controller').module.action(wall, 'Openwall')
                    message = wall.par.Status.eval()
                else:
                    for i, _ in plan:
                        show.op('direct_window{}'.format(i)).par.winopen.pulse()
                    message = 'Opened direct displays | ' + message
            except Exception:
                close_all(show)
                raise
        show.par.Outputstatus = message + ' | Blackout unchanged'
        return True
    except Exception as exc:
        show.par.Outputstatus = 'NOT OPENED: ' + str(exc)[:600]
        return False


def changed(show, name):
    if name == 'Outputmode' or (show.par.Outputmode == 'direct' and
            (name.startswith('Direct') or name in {
                'Output{}{}'.format(i, size) for i in (1, 2, 3) for size in ('width', 'height')})):
        close_all(show)
        show.par.Outputstatus = 'Output setting changed: windows closed. Check, then Open Selected Output.'


def startup(show):
    close_all(show)
    show.par.Outputstatus = 'Safe startup: windows closed. Select mode, check, then open.'


def install(show):
    """Additive installer: never initializes extensions or changes cue data."""
    import td
    if any(w is not None and w.isOpen for w in windows(show)):
        raise ValueError('Close output windows before installing Output Mode')
    if show.fetch('imagefx_export_job', None, search=False):
        raise ValueError('Finish/cancel export before installing Output Mode')
    page = next((p for p in show.customPages if p.name == 'Output Mode'), None)
    if page is None:
        page = show.appendCustomPage('Output Mode')
    def parameter(kind, name, label, default=None):
        p = show.par[name]
        if p is None:
            p = getattr(page, 'append' + kind)(name, label=label)[0]
            if default is not None and kind != 'Menu':
                p.default, p.val = default, default
        p.label = label
        return p
    new_mode = show.par['Outputmode'] is None
    mode = parameter('Menu', 'Outputmode', 'Output Mode')
    mode.menuNames = ['direct', 'wall']
    mode.menuLabels = ['Direct Displays (separate projectors)', '4K Wall Processor (2x2 + confidence)']
    mode.default = 'wall'
    if new_mode:
        mode.val = 'direct' if show.par.Reviewroute == 'atlas' else 'wall'
    for name, label in zip(ACTIONS, ('Check Selected Output', 'OPEN SELECTED OUTPUT', 'CLOSE ALL OUTPUTS')):
        parameter('Pulse', name, label)
    parameter('Str', 'Outputsummary', 'Format').expr = "me.op('show_output_mode').module.summary(me)"
    parameter('Str', 'Outputwindows', 'Windows').expr = "me.op('show_output_mode').module.window_status(me)"
    parameter('Str', 'Outputstatus', 'Output Status', 'Select mode, check, then open; blackout stays unchanged')
    for name in ('Outputsummary', 'Outputwindows', 'Outputstatus'):
        show.par[name].readOnly = True
    black = parameter('Toggle', 'Outputblackout', 'Show Master Blackout')
    black.bindExpr = 'me.par.Masterblackout'
    black.mode = type(black.mode).BIND
    for i in (1, 2, 3):
        p = parameter('Int', 'Directdisplay{}'.format(i), 'Direct P{} Display (-1 = unused)'.format(i), -1)
        p.min, p.max, p.normMin, p.normMax = -1, 31, -1, 31
        p.clampMin = p.clampMax = True
        p.enableExpr = "me.par.Outputmode == 'direct'"
    parameter('Toggle', 'Directallowprimary', 'Direct: Allow Operator Display', False).enableExpr = "me.par.Outputmode == 'direct'"
    for alias, target, label in (
        ('Outputwalldisplay', 'Displayindex', 'Wall: 4K Processor Display Index'),
        ('Outputwallblackout', 'Blackout', 'Wall: Projector Blackout'),
    ):
        master = _wall(show).par[target]
        p = parameter(master.style, alias, label)
        p.bindExpr = "me.parent().op('wall_output').par." + target
        p.mode = type(p.mode).BIND
        p.enableExpr = "me.par.Outputmode == 'wall'"
        if master.isInt:
            p.min, p.max, p.normMin, p.normMax = -1, 31, -1, 31
            p.clampMin = p.clampMax = True
    parameter('Str', 'Outputdisplays', 'Connected Displays').expr = "me.parent().op('wall_output').par.Displays.eval()"
    show.par.Outputdisplays.readOnly = True
    for i in (1, 2, 3):
        w = show.op('direct_window{}'.format(i)) or show.create(td.windowCOMP, 'direct_window{}'.format(i))
        w.par.winop = 'out{}_projector'.format(i)
        w.par.justifyoffsetto = 'specifydisplay'
        w.par.display.expr = "max(0, int(parent().par.Directdisplay{}))".format(i)
        w.par.size, w.par.dpiscaling = 'fill', 'native'
        w.par.borders, w.par.cursorvisible = False, 'nocursor'
    runtime = show.op('show_output_mode') or show.create(td.textDAT, 'show_output_mode')
    runtime.text = Path(__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
    callback = show.op('output_mode_callbacks') or show.create(td.parameterexecuteDAT, 'output_mode_callbacks')
    callback.par.active = False
    callback.par.op, callback.par.pars = '..', ' '.join(ACTIONS) + ' Outputmode Direct* Output*width Output*height'
    callback.par.custom, callback.par.builtin = True, False
    callback.par.onpulse, callback.par.valuechange = True, True
    callback.text = "def onPulse(par):\n    parent().op('show_output_mode').module.on_pulse(parent(), par.name)\ndef onValueChange(par, prev):\n    parent().op('show_output_mode').module.changed(parent(), par.name)\n"
    callback.par.active = True
    start = show.op('output_mode_startup') or show.create(td.executeDAT, 'output_mode_startup')
    start.par.start = True
    start.text = "def onStart():\n    parent().op('show_output_mode').module.startup(parent())\n"
    guard = "    if parent().op('show_output_mode') is not None and par.name in parent().op('show_output_mode').module.ACTIONS:\n        return\n"
    actions = show.op('show_parameters')
    if guard not in actions.text:
        actions.text = actions.text.replace('def onPulse(par):\n', 'def onPulse(par):\n' + guard, 1)
    show.par.Reviewroute.expr = "'wall' if me.par.Outputmode == 'wall' else 'atlas'"
    show.par.Reviewroute.readOnly = True
    show.par.Reviewroute.label = 'Follows Output Mode'
    show.par.Openoutputs.label = 'OPEN SELECTED OUTPUT'
    show.par.Closeoutputs.label = 'CLOSE ALL OUTPUTS'
    for name in ('Wallopen', 'Wallcheckdisplay'):
        show.par[name].enableExpr = "me.par.Outputmode == 'wall'"
    names = [p.name for p in show.customPages if p.name not in ('Transport', 'Output Mode')]
    show.sortCustomPages('Transport', 'Output Mode', *names)
    inspector = show.op('cue_inspector')
    scope = inspector.par.pagescope.eval()
    if "'Output Mode'" not in scope:
        inspector.par.pagescope = scope.replace('Transport', "Transport 'Output Mode'", 1)
    inspector.par.op = ''
    inspector.cook(force=True)
    inspector.par.op = '..'
    inspector.cook(force=True)
    return runtime
