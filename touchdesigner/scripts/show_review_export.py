"""Final projector review and isolated, frame-stepped silent cue export.

Installed as a self-contained Text DAT; no external package is needed at playback.
"""
import copy
import math
from pathlib import Path
import re
import time
import uuid

ACTIONS = ('Openprojectorreview', 'Startexport', 'Cancelexport')
JOB_KEY = 'imagefx_export_job'


def export_settings(source, preset, width, height, fps, duration, start, codec):
    if source not in ('cue', 'draft') or codec not in ('h264', 'mjpeg'):
        raise ValueError('Choose an export source and codec from the menus')
    sizes = {'1080p': (1920, 1080), '4k': (3840, 2160), '720p': (1280, 720)}
    if preset == 'custom':
        dims = (float(width), float(height))
        if any(not math.isfinite(n) or n != int(n) or n < 16 or n > 4096 or int(n) % 2 for n in dims):
            raise ValueError('Custom width/height must be even integers from 16 to 4096')
        size = tuple(int(n) for n in dims)
    elif preset in sizes:
        size = sizes[preset]
    else:
        raise ValueError('Choose a resolution preset')
    fps, duration, start = float(fps), float(duration), float(start)
    if not math.isfinite(fps) or fps not in (24, 25, 30, 50, 60):
        raise ValueError('Export FPS must be 24, 25, 30, 50, or 60')
    if not math.isfinite(duration) or not 0 < duration <= 3600:
        raise ValueError('Duration must be greater than zero and at most 3600 seconds')
    if not math.isfinite(start) or not 0 <= start <= 86400:
        raise ValueError('Start time must be between 0 and 86400 seconds')
    # Round half up; report actual duration after frame quantization.
    frames = max(1, int(math.floor(duration * fps + .5)))
    return dict(source=source, width=size[0], height=size[1], fps=int(fps),
                frames=frames, duration=frames / fps, start=start, codec=codec)


def selected_snapshot(show, source):
    ext = show.ext.ShowControlExt
    if ext.engine.state != 'stopped':
        raise ValueError('STOP ALL before exporting; export is an off-air operation')
    if source == 'draft':
        draft = ext._look_edit
        if not draft or draft['deck'] != show.op('look_editor'):
            raise ValueError('Recall Look first, or choose Selected Saved Cue')
        cue = copy.deepcopy(draft['cue'])
        cue['look'] = ext._capture_look(draft['deck'])
    elif source == 'cue':
        index = int(show.par.Selectedcue.eval()) - 1
        if not 0 <= index < len(ext.document['cues']):
            raise ValueError('Select a visual cue first')
        cue = copy.deepcopy(ext.document['cues'][index])
    else:
        raise ValueError('Unknown export source')
    if cue['kind'] != 'visual':
        raise ValueError('Only Visual cues can be exported; audio is not included')
    return cue


def review_path(show, index):
    if index not in (1, 2, 3):
        raise ValueError('Projector index must be 1, 2, or 3')
    if show.par.Reviewroute.eval() == 'wall':
        target = show.parent().op('wall_output/p{}_out'.format(index))
    else:
        target = show.op('out{}_projector'.format(index))
    return target.path if target is not None else show.op('black').path


def window_open(window):
    return bool(window is not None and window.isOpen)


def review_status(show):
    wall_mode = show.par.Reviewroute.eval() == 'wall'
    wall = show.parent().op('wall_output')
    if wall_mode and wall is None:
        return '4K WALL UNAVAILABLE — not showing another route'
    window = wall.op('wall_window') if wall_mode else show.op('audience_window')
    name = '4K WALL' if wall_mode else 'AUDIENCE ATLAS'
    black = bool(show.par.Masterblackout)
    if wall_mode:
        black = bool(wall.par.Blackout) or not bool(wall.par.Enabled) or (wall.par.Sourcemode == 'show' and black)
    return '{} | {} | {} | Software feed, not hardware confirmation'.format(
        name, 'WINDOW OPEN' if window_open(window) else 'WINDOW CLOSED',
        'BLACKOUT' if black else 'Feed active / per-output settings apply')


def _export_windows(show):
    wall = show.parent().op('wall_output')
    return [show.op('audience_window'), wall.op('wall_window') if wall else None]


def _later(show):
    import td
    td.run("op(args[0]).op('show_review_export').module.step(op(args[0]))", show.path,
           delayFrames=2, fromOP=show)


def _set_time(deck, modules, seconds):
    for name in (*modules, 'fx_rack'):
        component = deck.op(name)
        if component is not None and component.par['Manualtime'] is not None:
            component.par.Autotime = False
            component.par.Manualtime = seconds


def start_export(show):
    import td
    if show.fetch(JOB_KEY, None, search=False):
        raise ValueError('An export is already running')
    values = [show.par[name].eval() for name in (
        'Exportsource', 'Exportresolution', 'Exportwidth', 'Exportheight', 'Exportfps',
        'Exportduration', 'Exportstart', 'Exportcodec')]
    settings = export_settings(*values)
    cue = selected_snapshot(show, settings['source'])
    if any(window_open(w) for w in _export_windows(show)):
        raise ValueError('Close audience/wall output windows before exporting (shared GPU)')
    folder_text = show.par.Exportfolder.eval().strip()
    if not folder_text or '://' in folder_text:
        raise ValueError('Choose a local export folder')
    folder = Path(folder_text).expanduser()
    if not folder.is_absolute():
        folder = Path(show.par.Libraryroot.eval()) / folder
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '-', cue['name']).strip('-')[:60] or 'cue'
    suffix = '.mp4' if settings['codec'] == 'h264' else '.mov'
    # A separate unique directory is atomically reserved; never overwrite a file.
    jobdir = folder / (safe_name + '-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    jobdir.mkdir(exist_ok=False)
    path = jobdir / ('render' + suffix)
    ext = show.ext.ShowControlExt
    job = dict(settings=settings, cue=cue, path=path, index=0, deck=None, writer=None,
               stage='loading', deadline=time.monotonic() + 90)
    show.store(JOB_KEY, job)
    show.par.Exportbusy = True
    show.par.Exportprogress = 0
    show.par.Exportstatus = 'Preparing separate render copy (silent)...'
    show.par.Exportresult = str(path)
    try:
        deck = ext._new_deck('export_render_' + uuid.uuid4().hex[:8])
        job['deck'] = deck
        ext._apply_look(deck, cue['look'])
        deck.par.Resolutionpreset = 'custom'
        deck.par.Customwidth, deck.par.Customheight = settings['width'], settings['height']
        movie = ext._load_deck_media(deck, cue, ext._media_path(cue))
        job['movie'] = movie
        if movie is not None:
            movie.par.playmode = 'specify'
            movie.par.indexunit = 'seconds'
            movie.par.play = True
        deck.allowCooking = True
        _set_time(deck, ext.model.MODULES, settings['start'])
        job['readers'] = list(ext._look_readers(deck)) + ([movie] if movie else [])
        for reader in job['readers']:
            reader.par.frametimeout = 5000
            reader.par.alwaysloadinitial = True
            reader.preload()
        writer = deck.create(td.moviefileoutTOP, 'export_writer')
        job['writer'] = writer
        writer.par.record = False
        writer.par.file = str(path)
        writer.par.type = 'stopframemovie'
        writer.par.videocodec = 'mjpa' if settings['codec'] == 'mjpeg' else settings['codec']
        writer.par.pause = True
        writer.par.avgbitrate = 20000 if settings['width'] <= 1920 else 50000
        writer.par.peakbitrate = 30000 if settings['width'] <= 1920 else 70000
        writer.par.fps = settings['fps']
        writer.par.outputresolution = 'custom'
        writer.par.resolutionw, writer.par.resolutionh = settings['width'], settings['height']
        writer.par.audiochop = ''
        deck.op('out1_image').outputConnectors[0].connect(writer.inputConnectors[0])
        _later(show)
    except Exception:
        finish_export(show, 'FAILED')
        raise


def finish_export(show, outcome):
    job = show.fetch(JOB_KEY, None, search=False)
    if not job:
        show.par.Exportbusy = False
        return
    writer, deck = job.get('writer'), job.get('deck')
    error = ''
    if writer is not None:
        try:
            writer.par.record = False
            writer.cook(force=True)
            error = writer.errors()
        except Exception as exc:
            error = str(exc)
    path = job['path']
    if outcome == 'COMPLETE' and (error or not path.is_file() or not path.stat().st_size):
        outcome = 'FAILED: encoder did not produce a valid file. ' + str(error)
    show.unstore(JOB_KEY)
    if deck is not None:
        try:
            deck.destroy()  # only the copy created and owned by this job
        except Exception:
            pass  # it may already have been removed by a project reinitialization
    show.par.Exportbusy = False
    if outcome == 'COMPLETE':
        show.par.Exportprogress = 1
        show.par.Exportstatus = 'COMPLETE — {} frames, {:.3f}s, silent video'.format(
            job['index'], job['index'] / job['settings']['fps'])
    else:
        show.par.Exportstatus = outcome + ' — partial output retained; not a finished export'
    show.par.Exportresult = str(path)


def step(show):
    job = show.fetch(JOB_KEY, None, search=False)
    if not job:
        return
    try:
        ext = show.ext.ShowControlExt
        if ext.engine.state != 'stopped' or any(window_open(w) for w in _export_windows(show)):
            raise ValueError('Export cancelled because show playback/output was opened')
        deck, writer, settings = job['deck'], job['writer'], job['settings']
        if job['index'] >= settings['frames']:
            finish_export(show, 'COMPLETE')
            return
        seconds = settings['start'] + job['index'] / settings['fps']
        _set_time(deck, ext.model.MODULES, seconds)
        if job['movie'] is not None:
            job['movie'].par.index = job['cue']['media_in'] + seconds * job['cue']['speed']
        for reader in job['readers']:
            reader.cook(force=True)
            if reader.isInvalid:
                raise ValueError('A media source could not be decoded: ' + reader.name)
            if not reader.isOpen:
                if time.monotonic() > job['deadline']:
                    raise ValueError('Media preload timed out')
                _later(show)
                return
        output = deck.op('out1_image')
        output.cook(force=True)
        errors = deck.errors(recurse=True)
        if errors:
            raise ValueError(str(errors))
        if job['stage'] == 'loading':
            writer.par.record = True
            job['stage'] = 'rendering'
        writer.par.addframe.pulse()
        writer.cook(force=True)
        if writer.errors():
            raise ValueError(writer.errors())
        job['index'] += 1
        show.par.Exportprogress = job['index'] / settings['frames']
        show.par.Exportstatus = 'Rendering {}/{} frames — silent, off-air'.format(job['index'], settings['frames'])
        _later(show)
    except Exception as exc:
        finish_export(show, 'FAILED: ' + str(exc)[:350])


def on_pulse(show, name):
    try:
        if name == 'Openprojectorreview':
            selected = show.par.Reviewprojector.eval()
            target = show.op('projector_review') if selected == 'all' else show.op(review_path(show, int(selected)))
            target.openViewer()
        elif name == 'Startexport':
            start_export(show)
        elif name == 'Cancelexport':
            finish_export(show, 'CANCELLED')
        else:
            return False
        return True
    except Exception as exc:
        show.par.Exportstatus = str(exc)[:500]
        return False


def startup(show):
    # A saved TOE must never resume an interrupted render or retain runtime OPs.
    show.unstore(JOB_KEY)
    show.par.Exportbusy = False
    show.par.Exportprogress = 0
    show.par.Exportstatus = 'Idle — STOP ALL, choose a visual cue, then Export Video'


def configure_panel_layout(show):
    """Fit the full inspector, including its right-edge menus, in the viewer.

    Only custom show-control parameters belong in this inspector. Including
    the container's built-in parameters makes the native widget size fields
    beyond its visible right edge, even with those pages scoped out. Explicitly
    exclude them; widening or compressing the panel alone is not a reliable fix.
    Keep a readable, uncompressed inspector within the fixed design canvas.
    Only built-in layout parameters are changed; cue/transport values are not.
    """
    show.par.w, show.par.h = 1660, 900
    show.par.sizefromwindow = False
    show.par.fit = 'off'
    for name in ('marginl', 'marginr', 'marginb', 'margint'):
        show.par[name] = 0
    for name in ('header', 'status_display'):
        item = show.op(name)
        if item is not None:
            item.par.w = 1620
    inspector = show.op('cue_inspector')
    if inspector is not None:
        inspector.par.x, inspector.par.y = 920, 20
        inspector.par.w, inspector.par.h = 720, 750
        inspector.par.builtin = False
        inspector.par.custom = True
        inspector.par.compress = 1


def install(show):
    """Add nodes/parameters only; preserves show extension, cue data and drafts."""
    import td
    if show.fetch(JOB_KEY, None, search=False):
        raise ValueError('Finish/cancel export before upgrading review controls')
    def page(name):
        return next((p for p in show.customPages if p.name == name), None) or show.appendCustomPage(name)
    def par(p, name, label, kind, default=None, limits=None, menu=None, readonly=False):
        item = show.par[name]
        if item is None:
            item = getattr(p, 'append' + kind)(name, label=label)[0]
            if menu:
                item.menuNames = [x[0] for x in menu]
                item.menuLabels = [x[1] for x in menu]
            if default is not None:
                item.default = default
                item.val = default
        if limits:
            item.min, item.max = limits
            item.normMin, item.normMax = limits
            item.clampMin = item.clampMax = True
        item.readOnly = readonly
        return item
    p = page('Projector Review')
    par(p, 'Reviewroute', 'Output Route', 'Menu', 'wall', menu=[('wall', '4K Wall Processor'), ('atlas', 'Audience Atlas')])
    par(p, 'Reviewprojector', 'Enlarge Feed', 'Menu', 'all', menu=[('all', 'All Three'), ('1', '1 / Left'), ('2', '2 / Center'), ('3', '3 / Right')])
    par(p, 'Openprojectorreview', 'Open Projector Review', 'Pulse')
    par(p, 'Reviewstatus', 'Signal Status', 'Str', '', readonly=True).expr = "me.op('show_review_export').module.review_status(me)"
    p = page('Export Video')
    par(p, 'Exportsource', 'Export Source', 'Menu', 'cue', menu=[('cue', 'Selected Saved Cue'), ('draft', 'Current Look Draft')])
    par(p, 'Exportfolder', 'Export Folder', 'Folder', '.imagefx/exports')
    par(p, 'Exportcodec', 'Format', 'Menu', 'h264', menu=[('h264', 'MP4 / H.264 (Commercial/Pro)'), ('mjpeg', 'MOV / Motion JPEG')])
    par(p, 'Exportresolution', 'Resolution', 'Menu', '1080p', menu=[('1080p', '1920 x 1080'), ('4k', '3840 x 2160'), ('720p', '1280 x 720'), ('custom', 'Custom')])
    for name, label, default in [('Exportwidth','Width',1920), ('Exportheight','Height',1080)]:
        par(p, name, label, 'Int', default, (16,4096)).enableExpr = "not me.par.Exportbusy and me.par.Exportresolution == 'custom'"
    par(p, 'Exportfps', 'Frames / Second', 'Menu', '30', menu=[(str(n),str(n)) for n in (24,25,30,50,60)])
    par(p, 'Exportduration', 'Duration (seconds)', 'Float', 10, (.02,3600))
    par(p, 'Exportstart', 'Effect Start (seconds)', 'Float', 0, (0,86400))
    par(p, 'Startexport', 'Export Video (Silent)', 'Pulse').enableExpr = 'not me.par.Exportbusy'
    par(p, 'Cancelexport', 'Cancel Export', 'Pulse').enableExpr = 'bool(me.par.Exportbusy)'
    par(p, 'Exportbusy', 'Export Running', 'Toggle', False, readonly=True)
    par(p, 'Exportprogress', 'Progress', 'Float', 0, (0,1), readonly=True)
    par(p, 'Exportstatus', 'Export Status', 'Str', 'Idle — export is silent and off-air', readonly=True)
    par(p, 'Exportresult', 'Last Output File', 'Str', '', readonly=True)
    for name in ('Exportsource','Exportfolder','Exportcodec','Exportresolution','Exportfps','Exportduration','Exportstart'):
        show.par[name].enableExpr = 'not me.par.Exportbusy'
    def node(kind, name):
        existing = show.op(name)
        if existing is not None:
            return existing
        created = show.create(getattr(td, kind), name)
        created.name = name
        return created
    runtime = node('textDAT', 'show_review_export')
    runtime.text = Path(__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
    callback = node('parameterexecuteDAT','review_export_callbacks')
    callback.par.active = False
    callback.par.op, callback.par.pars = '..', ' '.join(ACTIONS)
    callback.par.custom, callback.par.builtin = True, False
    callback.par.onpulse, callback.par.valuechange = True, False
    callback.text = "def onPulse(par):\n    parent().op('show_review_export').module.on_pulse(parent(), par.name)\n"
    callback.par.active = True
    startup_dat = node('executeDAT', 'review_export_startup')
    startup_dat.par.start = True
    startup_dat.text = "def onStart():\n    parent().op('show_review_export').module.startup(parent())\n"
    actions = show.op('show_parameters')
    guard = "    if par.name in {!r}:\n        return\n".format(ACTIONS)
    if guard not in actions.text:
        actions.text = actions.text.replace('def onPulse(par):\n', 'def onPulse(par):\n' + guard, 1)
    # Fixed-cost, low-resolution preview taps; no duplicate effect networks.
    for i in (1,2,3):
        feed = node('selectTOP','review_p{}'.format(i))
        feed.par.top.expr = "parent().op('show_review_export').module.review_path(parent(), {})".format(i)
        feed.par.outputresolution = 'custom'
        feed.par.resolutionw, feed.par.resolutionh = 288, 162
    layout = node('layoutTOP','projector_review')
    for connector in list(layout.inputConnectors):
        connector.disconnect()
    for i in (1,2,3):
        show.op('review_p{}'.format(i)).outputConnectors[0].connect(layout.inputConnectors[i-1])
    layout.par.outputresolution = 'custom'
    layout.par.resolutionw, layout.par.resolutionh = 864,162
    layout.par.align = 'horizlr'
    layout.par.scaleres = False
    layout.par.fit = 'fitbest'
    layout.par.outputaspect = 'resolution'
    # Keep all 12 cue rows and the off-air Look Preview visible.
    for i in range(12):
        item = show.op('cue_row_{}'.format(i))
        if item:
            item.par.y, item.par.h = 686-i*27,25
    for action in ('recalllook','updatelook','savelookasnew','cancellook'):
        item = show.op('button_'+action) or show.op('button_'+action+'1')
        if item is not None:
            item.par.y = 348
            item.par.h = 38
    show.op('look_preview_panel').par.y = 196
    show.op('help').par.y = 306
    for i in range(4):
        show.op('look_help_{}'.format(i)).par.y = 278-i*28
    panel = node('containerCOMP','projector_review_panel')
    panel.par.x, panel.par.y, panel.par.w, panel.par.h = 20,12,880,165
    panel.par.top = 'projector_review'
    label = node('textCOMP','review_heading')
    label.par.x,label.par.y,label.par.w,label.par.h = 20,174,880,22
    label.par.fontsize = 14
    label.par.text = 'PROJECTOR REVIEW:  1 / LEFT                         2 / CENTER                         3 / RIGHT'
    for action,label_text,x in [('Openprojectorreview','Enlarge Projector Review',20), ('Startexport','Export Video',322)]:
        button = node('buttonCOMP','button_'+action.lower())
        button.par.x,button.par.y,button.par.w,button.par.h = x,114,282,28
        # Put these in the helper area above the preview, not over the images.
        button.par.y = 198
        button.par.label = label_text
        button.par.fontsize = 14
        clicked = button.op('clicked') or button.create(td.panelexecuteDAT,'clicked')
        clicked.name = 'clicked'
        clicked.par.panels,clicked.par.panelvalue,clicked.par.offtoon = button.path,'lselect',True
        clicked.par.active = True
        clicked.text = "def onOffToOn(panelValue):\n    c=parent().parent()\n    c.op('show_review_export').module.on_pulse(c, {!r})\n".format(action)
    # Condense obsolete help, leaving an explicit on-air/off-air distinction.
    show.op('look_help_2').par.text.expr = "parent().par.Reviewstatus.eval().split(' | Software')[0]"
    show.op('look_help_2').par.fontsize = 12
    show.op('look_help_3').par.text = ''
    show.op('look_help_3').par.display = False
    inspector = show.op('cue_inspector')
    inspector.par.pagescope = "Transport 'Cue Editor' 'Look Editor' 'Projector Review' 'Export Video' Routing 'Output 1' 'Output 2' 'Output 3'"
    inspector.par.op = ''
    inspector.cook(force=True)
    inspector.par.op = '..'
    inspector.cook(force=True)
    configure_panel_layout(show)
    return runtime
