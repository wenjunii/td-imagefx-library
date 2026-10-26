"""Physical delivery controls, independent of cue tracks and content routing.

Embedded in Show Control. All windows start closed; mode/display edits close
outputs and require an explicit Open. No action releases either blackout.
"""
from pathlib import Path

ACTIONS = ('Checkoutput', 'Openoutput', 'Closealloutputs')
DIRECT_NAMES = tuple('direct_window{}'.format(i) for i in (1, 2, 3))
CANVAS_PARAMETERS = ('Routingmode', 'Sharedtrack', 'Renderwidth', 'Renderheight', 'Panoramaoverlap', 'Cuemediafit')


def canvas_size(layout, panel_width, panel_height, overlap=0.):
    """Render one continuous image before splitting it into projector feeds."""
    factor = 3 - 2 * float(overlap) if layout == 'panoramic' else 1
    return int(float(panel_width) * factor), int(panel_height)


def cue_media_fit(show):
    fit = show.par.Cuemediafit.eval()
    if fit == 'auto':
        return 'cover' if show.par.Routingmode == 'panoramic' else 'contain'
    return fit


def workflow_show(demo):
    """Standalone copies and cue decks keep their own manual resolution."""
    follow = getattr(demo.par, 'Followshowcanvas', None)
    if follow is None or not follow or demo.fetch('imagefx_show_runtime', False):
        return None
    return demo.op('show_control')


def workflow_size(demo):
    show = workflow_show(demo)
    if show is not None:
        return canvas_size(show.par.Routingmode.eval(), int(show.par.Renderwidth),
                           int(show.par.Renderheight), float(show.par.Panoramaoverlap))
    preset = demo.par.Resolutionpreset.eval()
    if preset == 'hd': return 1920, 1080
    if preset == 'uhd4k': return 3840, 2160
    return int(demo.par.Customwidth), int(demo.par.Customheight)


def workflow_fit(demo):
    show = workflow_show(demo)
    return cue_media_fit(show) if show is not None else demo.par.Sourcefit.eval()


def workflow_summary(demo):
    width, height = workflow_size(demo)
    fit = {'contain': 'Fit / Letterbox', 'cover': 'Fill / Crop (no stretching)', 'stretch': 'Stretch'}[workflow_fit(demo)]
    return '{} x {} | {} | {}'.format(width, height, fit,
        'Show Control > Output Mode' if workflow_show(demo) is not None else 'Manual canvas')


CUE_MEDIA_SHADER = r'''
uniform vec4 uFit;
layout(location=0) out vec4 fragColor;
void main() {
    vec2 size = uTD2DInfos[0].res.zw;
    vec2 canvas = uTDOutputInfo.res.zw;
    float ratio = (size.x / max(size.y, 1.)) / (canvas.x / max(canvas.y, 1.));
    vec2 extent = vec2(1.);
    if (uFit.x < .5) extent = vec2(min(1., ratio), min(1., 1. / ratio));
    else if (uFit.x < 1.5) extent = vec2(max(1., ratio), max(1., 1. / ratio));
    vec2 uv = (vUV.st - (1. - extent) * .5) / extent;
    if (any(lessThan(uv, vec2(0.))) || any(greaterThan(uv, vec2(1.)))) {
        fragColor = TDOutputSwizzle(vec4(0., 0., 0., 1.)); return;
    }
    vec2 halfTexel = .5 / max(size, vec2(1.));
    fragColor = TDOutputSwizzle(texture(sTD2DInputs[0], clamp(uv, halfTexel, 1. - halfTexel)));
}
'''


def fit_cue_media(show, deck, movie):
    """Fit original decoded pixels before effects; never resize/restart the reader."""
    import td
    code = deck.op('cue_media_fit_code') or deck.create(td.textDAT, 'cue_media_fit_code')
    code.text = CUE_MEDIA_SHADER
    fitted = deck.op('cue_media_fit') or deck.create(td.glslTOP, 'cue_media_fit')
    fitted.par.pixeldat = 'cue_media_fit_code'
    fitted.par.outputresolution = 'custom'
    fitted.par.resolutionw.expr = 'int(parent().par.Customwidth)'
    fitted.par.resolutionh.expr = 'int(parent().par.Customheight)'
    fitted.seq.vec.numBlocks = 1
    fitted.par.vec0name = 'uFit'
    fitted.par.vec0valuex.expr = "('contain','cover','stretch').index(parent().parent().op('show_output_mode').module.cue_media_fit(parent().parent()))"
    movie.outputConnectors[0].connect(fitted.inputConnectors[0])
    fitted.outputConnectors[0].connect(deck.op('source_image').inputConnectors[1])
    return fitted


def install_workflow_canvas(show):
    """Follow Show Control without overwriting the user's manual size/fit values."""
    import inspect
    import td
    demo = show.parent()
    if getattr(demo.par, 'Resolutionpreset', None) is None or demo.op('source_image') is None:
        return
    page = next(p for p in demo.customPages if p.name == 'Output')
    if demo.par['Followshowcanvas'] is None:
        p = page.appendToggle('Followshowcanvas', label='Follow Show Canvas Resolution / Fit')[0]
        p.default, p.val = True, True
    if demo.par['Canvasresolution'] is None:
        page.appendStr('Canvasresolution', label='Effective Canvas / Media Fit')
    code = demo.op('workflow_canvas') or demo.create(td.textDAT, 'workflow_canvas')
    code.text = '\n\n'.join(inspect.getsource(f) for f in (
        canvas_size, cue_media_fit, workflow_show, workflow_size, workflow_fit, workflow_summary))
    demo.par.Canvasresolution.expr = "me.op('workflow_canvas').module.workflow_summary(me)"
    demo.par.Canvasresolution.readOnly = True
    manual = "me.op('workflow_canvas').module.workflow_show(me) is None"
    demo.par.Resolutionpreset.enableExpr = manual
    for name in ('Customwidth', 'Customheight'):
        demo.par[name].enableExpr = manual + " and me.par.Resolutionpreset == 'custom'"
    for name, axis in (('resolutionw', 0), ('resolutionh', 1)):
        demo.op('source_image').par[name].expr = "parent().op('workflow_canvas').module.workflow_size(parent())[{}]".format(axis)
    if getattr(demo.par, 'Sourcefit', None) is not None:
        demo.par.Sourcefit.enableExpr = manual + " and not me.fetch('imagefx_show_runtime', False)"
        demo.op('source_image').par.vec1valuey.expr = "('contain','cover','stretch').index(parent().op('workflow_canvas').module.workflow_fit(parent()))"
    first = ('Followshowcanvas', 'Canvasresolution', 'Resolutionpreset', 'Customwidth', 'Customheight')
    page.sort(*first, *(p.name for p in page.pars if p.name not in first))


def canvas_summary(show):
    mode = show.par.Routingmode.eval()
    width, height = int(show.par.Renderwidth), int(show.par.Renderheight)
    if mode == 'panoramic':
        width = int(width * (3 - 2 * float(show.par.Panoramaoverlap)))
        content = '{} x {} panorama | Track {} -> P1 left / P2 center / P3 right'.format(
            width, height, int(show.par.Sharedtrack))
    elif mode == 'identical':
        content = '{} x {} | Track {} repeated on P1/P2/P3'.format(width, height, int(show.par.Sharedtrack))
    else:
        content = '{} x {} per track | separate canvases; assign tracks on Output 1/2/3'.format(width, height)
    wall = show.parent().op('wall_output')
    if show.par.Outputmode == 'wall' and wall is not None and wall.par.Sourcemode != 'show':
        content += ' | Wall source override: choose Show Control on Wall Output'
    return content


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
    if name in CANVAS_PARAMETERS:
        show.UpdateMapping()
    if name == 'Outputmode' or name in CANVAS_PARAMETERS or (show.par.Outputmode == 'direct' and
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
    routing = next(p for p in show.customPages if p.name == 'Routing')
    if show.par['Sharedtrack'] is None:
        shared = routing.appendInt('Sharedtrack', label='Shared Canvas Cue Track')[0]
        shared.default, shared.val = 1, 1
        shared.min, shared.max, shared.normMin, shared.normMax = 1, 3, 1, 3
        shared.clampMin = shared.clampMax = True
    if show.par['Cuemediafit'] is None:
        fit = routing.appendMenu('Cuemediafit', label='Canvas Media Fit')[0]
        fit.menuNames = ['auto', 'contain', 'cover', 'stretch']
        fit.menuLabels = ['Auto (Panorama: Crop / Others: Fit)', 'Fit / Letterbox (no stretching)',
                          'Fill / Crop (no stretching)', 'Stretch (changes proportions)']
        fit.default, fit.val = 'auto', 'auto'
    layout = show.par.Routingmode
    saved_layout = layout.eval()
    layout.menuLabels = ['Identical (repeat one cue)', 'Panoramic (one wide canvas)', 'Independent (separate canvases)']
    layout.val = saved_layout
    show.par.Sharedtrack.enableExpr = "me.par.Routingmode != 'independent'"
    show.par.Panoramaoverlap.enableExpr = "me.par.Routingmode == 'panoramic'"
    for alias, target, label in (
        ('Outputlayout', 'Routingmode', 'Canvas Layout'),
        ('Outputsharedtrack', 'Sharedtrack', 'Shared Canvas Cue Track'),
        ('Outputpanelwidth', 'Renderwidth', 'Canvas Render Width Per Panel'),
        ('Outputpanelheight', 'Renderheight', 'Canvas Render Height'),
        ('Outputoverlap', 'Panoramaoverlap', 'Panorama Shared Edge Overlap'),
        ('Outputmediafit', 'Cuemediafit', 'Canvas Media Fit'),
    ):
        master = show.par[target]
        p = parameter('Menu' if master.isMenu else master.style, alias, label)
        if master.isMenu:
            p.menuNames, p.menuLabels = master.menuNames, master.menuLabels
        elif master.isNumber:
            p.min, p.max, p.normMin, p.normMax = master.min, master.max, master.normMin, master.normMax
            p.clampMin, p.clampMax = master.clampMin, master.clampMax
        p.bindExpr = 'me.par.' + target
        p.mode = type(p.mode).BIND
        if target in ('Sharedtrack', 'Panoramaoverlap'):
            p.enableExpr = master.enableExpr
    parameter('Str', 'Outputcanvas', 'Canvas Summary').expr = "me.op('show_output_mode').module.canvas_summary(me)"
    show.par.Outputcanvas.readOnly = True
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
    first = ('Outputmode', 'Outputlayout', 'Outputsharedtrack', 'Outputpanelwidth',
             'Outputpanelheight', 'Outputoverlap', 'Outputmediafit', 'Outputcanvas')
    page.sort(*first, *(p.name for p in page.pars if p.name not in first))
    for i in (1, 2, 3):
        w = show.op('direct_window{}'.format(i)) or show.create(td.windowCOMP, 'direct_window{}'.format(i))
        w.par.winop = 'out{}_projector'.format(i)
        w.par.justifyoffsetto = 'specifydisplay'
        w.par.display.expr = "max(0, int(parent().par.Directdisplay{}))".format(i)
        w.par.size, w.par.dpiscaling = 'fill', 'native'
        w.par.borders, w.par.cursorvisible = False, 'nocursor'
    runtime = show.op('show_output_mode') or show.create(td.textDAT, 'show_output_mode')
    runtime.text = Path(__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
    install_workflow_canvas(show)
    for name in ['deck{}_{}'.format(t, s) for t in (1, 2, 3) for s in (0, 1)] + ['look_editor']:
        deck = show.op(name)
        if deck is not None and deck.op('media') is not None:
            fit_cue_media(show, deck, deck.op('media'))
    callback = show.op('output_mode_callbacks') or show.create(td.parameterexecuteDAT, 'output_mode_callbacks')
    callback.par.active = False
    callback.par.op, callback.par.pars = '..', ' '.join(ACTIONS + CANVAS_PARAMETERS) + ' Outputmode Direct* Output1width Output1height Output2width Output2height Output3width Output3height'
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
