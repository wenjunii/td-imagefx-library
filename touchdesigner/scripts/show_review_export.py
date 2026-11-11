"""Final projector review, frame-stepped cue export and UHD wall recording.

Installed as a self-contained Text DAT; no external package is needed at playback.
"""
import copy
import math
from pathlib import Path
import re
import time
import uuid

WALL_ACTIONS = {
    'Wallcheckdisplay': 'Checkdisplay',
    'Wallopen': 'Openwall',
    'Wallclose': 'Closewall',
}
ACTIONS = ('Openprojectorreview', 'Startexport', 'Stopexport', 'Cancelexport', *WALL_ACTIONS)
# These are aliases, not a second set of hardware settings. Relative bindings
# continue to resolve correctly when the complete ImageFX demo is copied.
WALL_BINDINGS = (
    ('Wallmasterblackout', 'Masterblackout', 'Show Master Blackout'),
    ('Wallenabled', 'Enabled', 'Enable Projector Feeds'),
    ('Wallblackout', 'Blackout', 'Wall Projector Blackout (keeps Q4)'),
    ('Wallsourcemode', 'Sourcemode', 'Wall Source Mode'),
    ('Wallmastertop', 'Mastertop', 'Master / Panorama TOP Path'),
    ('Wallprojector1top', 'Projector1top', 'Projector 1 TOP Path'),
    ('Wallprojector2top', 'Projector2top', 'Projector 2 TOP Path'),
    ('Wallprojector3top', 'Projector3top', 'Projector 3 TOP Path'),
    ('Wallfit', 'Fit', 'Source Fit'),
    ('Walltestpattern', 'Testpattern', 'Numbered Calibration Pattern'),
    ('Wallmonitorenabled', 'Monitorenabled', 'Enable Confidence Quadrant'),
    ('Wallshowstats', 'Showstats', 'Show Diagnostics'),
    ('Walldisplayindex', 'Displayindex', '4K Processor Display Index'),
    ('Wallallowprimary', 'Allowprimary', 'Allow Primary Display'),
)
JOB_KEY = 'imagefx_export_job'
EXPORT_SOURCES = (
    ('cue', 'Selected Saved Cue / Offline'),
    ('draft', 'Current Look Draft / Offline'),
    ('wall', '2x2 Wall + Confidence / Real-Time'),
    ('review', 'Projector Review / Real-Time'),
)
REALTIME_SOURCES = ('wall', 'review')
LIVE_ENCODER_QUALITIES = (
    ('balanced', 'Balanced / Real-Time (recommended)'),
    ('fast', 'Fast / More GPU Headroom'),
    ('high', 'High Quality / More GPU Cost'),
)
EXPORT_CHANNELS = (
    ('canvas', 'Full Cue Canvas / No Projector Split'),
    ('cue', 'Follow Cue Projection Routing / Separate Files'),
    ('1', 'Projector 1 / Left'), ('2', 'Projector 2 / Center'),
    ('3', 'Projector 3 / Right'), ('1_2', 'Projectors 1 + 2'),
    ('1_3', 'Projectors 1 + 3'), ('2_3', 'Projectors 2 + 3'),
    ('all', 'All Three Projectors / Separate Files'),
)
CHANNEL_SHADER = r'''
uniform vec4 uSlice;
layout(location=0) out vec4 fragColor;
void main() {
    vec2 size = uTD2DInfos[0].res.zw;
    vec2 sliceSize = vec2(size.x * (uSlice.y-uSlice.x), size.y);
    vec2 canvas = uTDOutputInfo.res.zw;
    float ratio = (sliceSize.x/max(sliceSize.y,1.)) / (canvas.x/max(canvas.y,1.));
    vec2 extent = vec2(min(1.,ratio), min(1.,1./ratio));
    vec2 uv = (vUV.st-(1.-extent)*.5)/extent;
    if (any(lessThan(uv,vec2(0))) || any(greaterThan(uv,vec2(1)))) {
        fragColor = TDOutputSwizzle(vec4(0,0,0,1)); return;
    }
    uv.x = mix(uSlice.x,uSlice.y,uv.x);
    vec2 halfTexel = .5/max(size,vec2(1));
    uv = clamp(uv,vec2(uSlice.x,0)+halfTexel,vec2(uSlice.y,1)-halfTexel);
    fragColor = TDOutputSwizzle(texture(sTD2DInputs[0],uv));
}
'''
EXPORT_RESOLUTIONS = (
    ('1080p', '1920 x 1080'), ('4k', '3840 x 2160'), ('720p', '1280 x 720'),
    ('panoramic', 'Panoramic / Full 3-Projector Canvas'), ('custom', 'Custom'),
)
EXPORT_CODECS = (
    ('h264', 'MP4 / H.264 (NVIDIA GPU, Commercial/Pro)'),
    ('mjpeg', 'MOV / Motion JPEG'),
    ('h265', 'MP4 / H.265 HEVC (NVIDIA GPU, Commercial/Pro)'),
)
GPU_CODEC_LIMITS = {'h264': 4096, 'h265': 8192}
REVIEW_VIEWS = (
    ('auto', 'Auto / Follow Output Mode'),
    ('all', 'Three Projectors / Side by Side'),
    ('wall', '2x2 Video Wall / Full 4K Canvas'),
    ('1', 'Projector 1 / Left'),
    ('2', 'Projector 2 / Center'),
    ('3', 'Projector 3 / Right'),
    ('confidence', 'Confidence Monitor / Quadrant 4'),
)
REVIEW_RESOLUTIONS = (
    ('1080p', '1080p Per Projector / 5760 x 1080 Total'),
    ('720p', '720p Per Projector / 3840 x 720 Total'),
    ('4k', '4K Per Projector / 11520 x 2160 Total'),
    ('native', 'Native / Largest Projector Feed'),
    ('custom', 'Custom Per-Projector Cell'),
)


def review_panel_geometry(preset, width=1920, height=1080, native_sizes=()):
    sizes = {'1080p': (1920,1080), '720p': (1280,720), '4k': (3840,2160)}
    if preset in sizes:
        return sizes[preset]
    if preset == 'native':
        if len(native_sizes) != 3:
            raise ValueError('Native review needs three projector feed sizes')
        checked = [review_panel_geometry('custom', *size) for size in native_sizes]
        return max(size[0] for size in checked), max(size[1] for size in checked)
    if preset != 'custom':
        raise ValueError('Choose Three-Up Resolution from the Projector Review menu')
    values = (float(width), float(height))
    if any(not math.isfinite(n) or n != int(n) or not 16 <= n <= 4096 for n in values):
        raise ValueError('Review cell dimensions must be integers from 16 to 4096')
    return tuple(int(n) for n in values)


def review_panel_size(show):
    preset = getattr(show.par, 'Reviewresolution', None)
    mode = preset.eval() if preset is not None else '1080p'
    native = []
    if mode == 'native':
        for i in (1,2,3):
            target = show.op(review_path(show, i))
            if target is None:
                raise ValueError('Projector feed unavailable for native review')
            native.append((target.width, target.height))
    width, height = getattr(show.par, 'Reviewwidth', None), getattr(show.par, 'Reviewheight', None)
    return review_panel_geometry(mode, width.eval() if width is not None else 1920,
                                 height.eval() if height is not None else 1080, native)


def review_canvas_size(show):
    width, height = review_panel_size(show)
    return 3 * width, height


def review_thumbnail_geometry(width, height):
    scale = min(288. / width, 162. / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def review_thumbnail_size(show):
    return review_thumbnail_geometry(*review_panel_size(show))


def review_resolution_info(show):
    try:
        width, height = review_canvas_size(show)
        return '{} x {} three-up | {} x {} each | Thumbnail stays small; no cue/output resizing.{}'.format(
            width, height, width // 3, height, panorama_codec_hint(width, height))
    except ValueError as exc:
        return str(exc)


def panorama_size(panel_width, panel_height, overlap):
    """Same three-panel geometry as live routing, rounded to even movie pixels."""
    width, height, overlap = float(panel_width), float(panel_height), float(overlap)
    if (not all(math.isfinite(n) for n in (width, height, overlap))
            or width != int(width) or height != int(height)
            or not 16 <= width <= 4096 or not 16 <= height <= 4096
            or not 0 <= overlap <= .5):
        raise ValueError('Panorama needs panel dimensions 16–4096 and overlap 0–0.5')
    # Live routing truncates its width first; at most one extra pixel is needed.
    return tuple(n + n % 2 for n in (int(width * (3 - 2 * overlap)), int(height)))


def export_settings(source, preset, width, height, fps, duration, start, codec,
                    panorama=(5760, 1080), review_size=(864, 162)):
    if source not in dict(EXPORT_SOURCES) or codec not in dict(EXPORT_CODECS):
        raise ValueError('Choose an export source and codec from the menus')
    sizes = {'1080p': (1920, 1080), '4k': (3840, 2160), '720p': (1280, 720)}
    if preset not in dict(EXPORT_RESOLUTIONS):
        raise ValueError('Choose a resolution preset')
    if source == 'wall':
        size = sizes['4k']  # Fixed hardware contract; ignore disabled size fields.
        start = 0         # Record current playback; never seek the live show.
    elif source == 'review':
        size = review_recording_size(*review_size)
        start = 0         # Record the current review, not a selected cue snapshot.
    elif preset == 'panoramic':
        dims = tuple(float(n) for n in panorama)
        if len(dims) != 2 or any(not math.isfinite(n) or n != int(n)
                                or not 16 <= n <= 16384 or int(n) % 2 for n in dims):
            raise ValueError('Panoramic dimensions must be even integers from 16 to 16384')
        size = tuple(int(n) for n in dims)
    elif preset == 'custom':
        dims = (float(width), float(height))
        if any(not math.isfinite(n) or n != int(n) or n < 16 or n > 4096 or int(n) % 2 for n in dims):
            raise ValueError('Custom width/height must be even integers from 16 to 4096')
        size = tuple(int(n) for n in dims)
    elif preset in sizes:
        size = sizes[preset]
    if codec == 'h264' and max(size) > 4096:
        raise ValueError('H.264 supports at most 4096 pixels per axis. Choose MP4 / H.265 HEVC '
                         'up to 8192 pixels, or MOV / Motion JPEG; the canvas will not be resized.')
    if codec == 'h265' and max(size) > GPU_CODEC_LIMITS['h265']:
        raise ValueError('H.265 GPU export supports at most 8192 pixels per axis. '
                         'Choose MOV / Motion JPEG for this larger panorama; the canvas will not be resized.')
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
                frames=frames, duration=frames / fps, start=start, codec=codec,
                panoramic=source not in REALTIME_SOURCES and preset == 'panoramic')


def review_recording_size(width, height):
    values = (float(width), float(height))
    if any(not math.isfinite(n) or n != int(n) or not 16 <= n <= 16384 for n in values):
        raise ValueError('Review resolution must be integer dimensions from 16 to 16384')
    # Movie encoders require even pixels. The local capture canvas letterboxes
    # the native picture instead of stretching an odd-sized review image.
    return tuple(int(n) + int(n) % 2 for n in values)


def export_suffix(codec):
    if codec not in dict(EXPORT_CODECS):
        raise ValueError('Unknown export codec')
    return '.mp4' if codec in GPU_CODEC_LIMITS else '.mov'


def wall_warmup_seconds(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 10:
        raise ValueError('Wall render warm-up must be between 0 and 10 seconds')
    return value


def writer_codec(codec, menu_names):
    """Resolve TD's versioned codec tokens without falling back to a CPU codec."""
    if codec not in dict(EXPORT_CODECS):
        raise ValueError('Unknown export codec')
    candidates = ('mjpa',) if codec == 'mjpeg' else (codec + 'nvgpu', codec)
    for name in candidates:
        if name in menu_names:
            return name
    raise ValueError('The selected codec is unavailable in this TouchDesigner build: ' + codec)


def upgrade_codec_menu(show):
    """Preserve existing choices, including old serialized menu indices."""
    par = show.par.Exportcodec
    selected = par.eval()
    par.menuNames = [name for name, _ in EXPORT_CODECS]
    par.menuLabels = [label for _, label in EXPORT_CODECS]
    par.val = selected if selected in par.menuNames else 'h264'


def panorama_codec_hint(width, height):
    if max(width, height) > GPU_CODEC_LIMITS['h265']:
        return ' Above 8192 pixels: use MOV / Motion JPEG.'
    if max(width, height) > GPU_CODEC_LIMITS['h264']:
        return ' Use MP4 / H.265 HEVC for NVIDIA GPU encoding, or MOV / Motion JPEG.'
    return ''


def current_panorama_size(show):
    return panorama_size(show.par.Renderwidth.eval(), show.par.Renderheight.eval(),
                         show.par.Panoramaoverlap.eval())


def export_media_fit(show, panoramic):
    fit = show.par.Cuemediafit.eval()
    if fit == 'auto':
        return 'cover' if panoramic or show.par.Routingmode == 'panoramic' else 'contain'
    if fit not in ('contain', 'cover', 'stretch'):
        raise ValueError('Choose a valid Canvas Media Fit in Output Mode')
    return fit


def projection_export_plan(cue, selection, layout, output_tracks, width, height, overlap=0.):
    """Select existing cue feeds, never reroute or redistribute a panorama."""
    from tdimagefx.show import cue_canvas_layout, cue_projection_sample, cue_render_width
    if selection not in dict(EXPORT_CHANNELS):
        raise ValueError('Choose Export Projection Channels from the menu')
    if selection == 'canvas':
        return None
    # Validate geometry even when this cue is not panoramic.
    panorama_size(width, height, overlap)
    if layout not in ('cue', 'identical', 'independent', 'panoramic'):
        raise ValueError('Unknown show routing layout')
    if len(output_tracks) != 3 or any(type(t) is not int or t not in (1,2,3) for t in output_tracks):
        raise ValueError('Invalid show output tracks')
    samples = {i: cue_projection_sample(cue, i, layout, output_tracks, overlap) for i in (1,2,3)}
    routed = tuple(i for i in samples if samples[i][0])
    requested = routed if selection == 'cue' else (1,2,3) if selection == 'all' else tuple(int(i) for i in selection.split('_'))
    if not requested:
        raise ValueError('This cue is not routed to a projector; update its routing or export Full Cue Canvas')
    missing = [i for i in requested if i not in routed]
    if missing:
        raise ValueError('Cue is not routed to projector(s) {}; choose Follow Cue Projection Routing or edit the cue'.format(
            ', '.join(str(i) for i in missing)))
    return dict(channels=requested, samples={i: samples[i][1:] for i in requested},
                render_width=cue_render_width(cue, layout, width, overlap), render_height=int(height),
                panoramic=cue_canvas_layout(cue, layout) == 'panoramic')


def selected_projection_plan(show, cue):
    parameter = getattr(show.par, 'Exportchannels', None)
    selection = parameter.eval() if parameter is not None else 'canvas'
    if selection == 'canvas':
        return None
    return projection_export_plan(cue, selection, show.par.Routingmode.eval(),
        show.ext.ShowControlExt._output_tracks(), int(show.par.Renderwidth), int(show.par.Renderheight),
        float(show.par.Panoramaoverlap))


def selected_snapshot(show, source):
    ext = show.ext.ShowControlExt
    if ext.engine.state != 'stopped':
        raise ValueError('STOP ALL before exporting; export is an off-air operation')
    if source == 'draft':
        draft = ext._look_edit
        if not draft or draft['deck'] != show.op('look_editor'):
            raise ValueError('Recall Look first, or choose Selected Saved Cue')
        cue = copy.deepcopy(draft['cue'])
        cue['look'] = ext._capture_look(draft['deck'], capture_animation=True)
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


def review_selection(show):
    selected = show.par.Reviewprojector.eval()
    if selected == 'auto':
        return 'wall' if show.par.Reviewroute.eval() == 'wall' else 'all'
    if selected not in {name for name, _ in REVIEW_VIEWS}:
        raise ValueError('Choose a Review View from the menu')
    return selected


def review_target(show):
    """Use the actual packed output, not a second approximation of the wall."""
    selected = review_selection(show)
    if selected in ('wall', 'confidence'):
        path = 'out1_wall_4k' if selected == 'wall' else 'comp_monitor_out'
        target = show.parent().op('wall_output/' + path)
    elif selected == 'all':
        target = show.op('projector_review')
    else:
        target = show.op(review_path(show, int(selected)))
    return target if target is not None else show.op('black')


def review_preview_target(show):
    """The embedded panel must not pull the high-resolution three-up branch."""
    if review_selection(show) == 'all':
        return show.op('projector_review_thumbnail') or show.op('black')
    return review_target(show)


def review_size(show):
    if review_selection(show) == 'all':
        width, height = review_canvas_size(show)
    else:
        target = review_target(show)
        width, height = max(1, target.width), max(1, target.height)
    scale = min(880.0 / width, 165.0 / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def review_heading(show):
    selected = review_selection(show)
    if selected == 'wall':
        label = '2x2 VIDEO WALL:  TL=P1  |  TR=P2  |  BL=P3  |  BR=CONFIDENCE'
    elif selected == 'confidence':
        label = 'CONFIDENCE MONITOR / QUADRANT 4'
    elif selected == 'all':
        label = 'PROJECTOR REVIEW:  1 / LEFT                         2 / CENTER                         3 / RIGHT'
    else:
        label = 'PROJECTOR ' + selected + ' / FINAL FEED'
    if selected in ('wall', 'confidence') and show.par.Reviewroute.eval() != 'wall':
        label += '  [Direct output active; wall preview only]'
    return label


def window_open(window):
    return bool(window is not None and window.isOpen)


def review_status(show):
    wall_mode = show.par.Reviewroute.eval() == 'wall'
    wall = show.parent().op('wall_output')
    if wall_mode and wall is None:
        return '4K WALL UNAVAILABLE — not showing another route'
    candidates = ([wall.op('wall_window')] if wall_mode else
                  [show.op('audience_window')] + [show.op('direct_window{}'.format(i)) for i in (1, 2, 3)])
    name = '4K WALL' if wall_mode else 'DIRECT DISPLAYS'
    black = bool(show.par.Masterblackout)
    if wall_mode:
        override=getattr(show,'HasCueOutputRouting',None)
        revision=getattr(show.par,'Cueroutingrevision',None)
        if revision is not None: revision.eval()
        uses_show=wall.par.Sourcemode == 'show' or (callable(override) and override() is True)
        black = bool(wall.par.Blackout) or not bool(wall.par.Enabled) or (uses_show and black)
    return '{} | {} | {} | Software feed, not hardware confirmation'.format(
        name, 'WINDOW OPEN' if any(window_open(w) for w in candidates) else 'WINDOW CLOSED',
        'BLACKOUT' if black else 'Feed active / per-output settings apply')


def _export_windows(show):
    wall = show.parent().op('wall_output')
    return ([show.op('audience_window'), wall.op('wall_window') if wall else None] +
            [show.op('direct_window{}'.format(i)) for i in (1, 2, 3)])


def _later(show):
    import td
    job = show.fetch(JOB_KEY, None, search=False)
    if job:
        td.run("owner=op(args[0]); runtime=owner.op('show_review_export') if owner else None; "
               "runtime.module.step(owner, args[1]) if runtime else None",
               show.path, job['id'], delayFrames=1 if job['settings']['source'] in REALTIME_SOURCES else 2,
               fromOP=show)


def wall_export_target(show, cook=True):
    wall = show.parent().op('wall_output')
    if wall is None:
        raise ValueError('Wall Output is unavailable')
    if not bool(wall.par.Monitorenabled):
        raise ValueError('Enable Confidence Quadrant on Wall Output before recording')
    target = wall.op('out1_wall_4k')
    if target is None or target.family != 'TOP':
        raise ValueError('The packed 2x2 wall TOP is unavailable')
    if cook:
        target.cook(force=True)
    if (target.width, target.height) != (3840, 2160):
        raise ValueError('Wall recording requires a 3840 x 2160 TOP; check license/resolution')
    errors = target.errors(recurse=True)
    if errors:
        raise ValueError('Wall output error: ' + str(errors))
    return target


def review_export_target(show, cook=True):
    """Capture the selected review TOP, never the operator controls/window UI."""
    target = review_target(show)
    if target is None or target == show.op('black') or target.family != 'TOP':
        raise ValueError('The selected Projector Review view is unavailable')
    if cook:
        target.cook(force=True)
    review_recording_size(target.width, target.height)
    if target.fetch('imagefx_review_full_canvas', False, search=False) is True:
        expected = review_canvas_size(show)
        if (target.width, target.height) != expected:
            raise ValueError('High-resolution review requires {} x {}; check license/GPU resolution limits'.format(*expected))
    errors = target.errors(recurse=True)
    if errors:
        raise ValueError('Projector Review error: ' + str(errors))
    return target


def export_description(show):
    if show.par.Exportsource == 'wall':
        return ('3840 x 2160 fixed | TL=P1 TR=P2 BL=P3 BR=confidence | '
                'Silent real-time; windows CLOSED. Wait for RECORDING before GO; '
                'warm-up is not recorded. Blackouts are recorded.')
    if show.par.Exportsource == 'review':
        try:
            if review_selection(show) == 'all' and getattr(show.par, 'Reviewresolution', None) is not None:
                # A text readout is not a reason to cook a 6K/12K layout.
                # start_export still cooks and verifies its actual dimensions.
                width, height = review_recording_size(*review_canvas_size(show))
            else:
                target = review_export_target(show, cook=False)
                width, height = review_recording_size(target.width, target.height)
            return ('Projector Review: {} | {} x {} native view (even-pixel pad if needed) | '
                    'Silent real-time; windows CLOSED. Wait for RECORDING before GO. '
                    'Mapping/blackouts are included; no Show Control buttons.').format(
                        review_selection(show), width, height) + panorama_codec_hint(width, height)
        except ValueError as exc:
            return str(exc)
    channels = getattr(show.par, 'Exportchannels', None)
    if channels is not None and channels.eval() != 'canvas':
        try:
            ext = show.ext.ShowControlExt
            if show.par.Exportsource == 'draft':
                if not ext._look_edit:
                    return 'Recall Look first, or choose Selected Saved Cue'
                cue = ext._look_edit['cue']
            else:
                index = int(show.par.Selectedcue) - 1
                if not 0 <= index < len(ext.document['cues']):
                    return 'Select a visual cue first'
                cue = ext.document['cues'][index]
            if cue['kind'] != 'visual':
                return 'Only Visual cues can be exported'
            plan = selected_projection_plan(show, cue)
            return ('P{} | one file per projector, same frames/time | {} | Clean feeds, no calibration/audio. '
                    'Resolution is per file; use Full Cue Canvas for the Panoramic preset.').format(
                        ', P'.join(str(i) for i in plan['channels']),
                        'Panoramic slices' if plan['panoramic'] else 'Identical cue image')
        except (ValueError, IndexError) as exc:
            return str(exc)
    if show.par.Exportresolution == 'panoramic':
        try:
            width, height = current_panorama_size(show)
            return ('{} x {} panorama | Full cue canvas, no confidence or projector mapping | '
                    'Offline; Auto = Fill/Crop, no stretching.{}').format(
                        width, height, panorama_codec_hint(width, height))
        except ValueError as exc:
            return str(exc)
    return 'Offline cue/draft render | STOP ALL and close output windows | Silent video'


def configure_export_canvas(show, deck, settings):
    """Change only our render copy; never the designer, show routing or live deck."""
    deck.par.Resolutionpreset = 'custom'
    plan = settings.get('projection')
    for name, key in (('Customwidth', 'width'), ('Customheight', 'height')):
        value = plan['render_' + key] if plan else settings[key]
        deck.par[name].max = max(deck.par[name].max, value)
        deck.par[name].val = value
    settings['fit'] = export_media_fit(show, plan['panoramic'] if plan else settings['panoramic'])
    if getattr(deck.par, 'Sourcefit', None) is not None:
        deck.par.Sourcefit = settings['fit']


def export_render_target(show, deck, settings):
    """Freeze media fit; preserve final-crop proportions on the panoramic canvas."""
    import td
    fitted = deck.op('cue_media_fit')
    if fitted is not None:
        fitted.par.vec0valuex = ('contain', 'cover', 'stretch').index(settings['fit'])
    output = deck.op('out1_image')
    plan = settings.get('projection')
    if not settings['panoramic'] and not plan:
        return output
    code = deck.create(td.textDAT, 'export_canvas_code')
    code.text = show.op('show_output_mode').module.CUE_MEDIA_SHADER
    target = deck.create(td.glslTOP, 'export_canvas')
    target.par.pixeldat = code.name
    target.par.outputresolution = 'custom'
    target.par.resolutionw, target.par.resolutionh = ((plan['render_width'], plan['render_height']) if plan
                                                   else (settings['width'], settings['height']))
    target.seq.vec.numBlocks = 1
    target.par.vec0name = 'uFit'
    target.par.vec0valuex = ('contain', 'cover', 'stretch').index(settings['fit'])
    output.outputConnectors[0].connect(target.inputConnectors[0])
    return target


def projection_render_targets(deck, output, settings):
    import td
    code = deck.create(td.textDAT, 'export_channel_code')
    code.text = CHANNEL_SHADER
    targets = []
    for channel in settings['projection']['channels']:
        target = deck.create(td.glslTOP, 'export_projector' + str(channel))
        target.par.pixeldat = code.name
        target.par.outputresolution = 'custom'
        target.par.resolutionw, target.par.resolutionh = settings['width'], settings['height']
        target.seq.vec.numBlocks = 1
        target.par.vec0name = 'uSlice'
        target.par.vec0valuex, target.par.vec0valuey = settings['projection']['samples'][channel]
        output.outputConnectors[0].connect(target.inputConnectors[0])
        targets.append(target)
    return targets


def _writer(parent, target, path, settings, name='export_writer'):
    import td
    writer = parent.create(td.moviefileoutTOP, name)
    writer.par.record = False
    writer.par.file = str(path)
    live = settings['source'] in REALTIME_SOURCES
    writer.par.type = 'movie' if live else 'stopframemovie'
    writer.par.videocodec = writer_codec(settings['codec'], writer.par.videocodec.menuNames)
    writer.par.pause = not live
    writer.par.avgbitrate = 20000 if settings['width'] <= 1920 else 50000
    writer.par.peakbitrate = 30000 if settings['width'] <= 1920 else 70000
    writer.par.fps = settings['fps']
    writer.par.outputresolution = 'custom'
    writer.par.resolutionw, writer.par.resolutionh = settings['width'], settings['height']
    writer.par.resmult = False
    writer.par.audiochop = ''
    # Preserve the first image and exact file length. This can still cause a
    # startup repeat in real-time mode; never hide it with an asynchronous open
    # that omits head frames while its progress counter claims a complete file.
    if getattr(writer.par, 'stallforopen', None) is not None:
        writer.par.stallforopen = True
    if live:
        # TD defaults to high quality and four B-frames, which can saturate
        # NVENC at 60 FPS on a wide review canvas. This is a visible operator
        # choice, never a resolution/FPS reduction or CPU encoder fallback.
        quality = settings.get('live_quality', 'balanced')
        if quality not in dict(LIVE_ENCODER_QUALITIES):
            raise ValueError('Choose a valid Live Encoder Quality')
        quality_par = getattr(writer.par, 'qualitymode', None)
        options = getattr(quality_par, 'menuNames', None)
        if isinstance(options, (list,tuple)) and quality in options:
            writer.par.qualitymode = quality
        if getattr(writer.par, 'maxbframes', None) is not None:
            writer.par.maxbframes = 0
        writer.par.limitlength = True
        # TD's frame unit uses the project rate, not Movie FPS. Seconds keeps
        # the requested duration correct at (for example) 30 FPS in a 60 Hz project.
        writer.par.lengthunit = 'seconds'
        writer.par.length = settings['duration']
        # TD connections cannot cross COMP boundaries. Reference the live wall
        # from a local Select TOP instead of attempting an invalid direct wire.
        source = parent.create(td.selectTOP, 'export_source')
        source.par.top = target.path
        needs_pad = (settings['width'],settings['height']) != (target.width,target.height)
        target = source
        # An exact-size review is already fitted. Another full-canvas pass at
        # 5760x1080 wastes bandwidth; only odd native sizes need the even pad.
        if settings['source'] == 'review' and needs_pad:
            code = parent.create(td.textDAT, 'review_recording_code')
            code.text = CHANNEL_SHADER
            canvas = parent.create(td.glslTOP, 'review_recording_canvas')
            canvas.par.pixeldat = code.name
            canvas.par.outputresolution = 'custom'
            canvas.par.resolutionw, canvas.par.resolutionh = settings['width'], settings['height']
            canvas.seq.vec.numBlocks = 1
            canvas.par.vec0name = 'uSlice'
            canvas.par.vec0valuex, canvas.par.vec0valuey = 0, 1
            source.outputConnectors[0].connect(canvas.inputConnectors[0])
            target = canvas
    target.outputConnectors[0].connect(writer.inputConnectors[0])
    return writer


def _set_time(deck, modules, seconds):
    from tdimagefx.show import animation_time
    animation = deck.fetch('imagefx_look_animation', {}, search=False)
    for name in (*modules, 'fx_rack'):
        component = deck.op(name)
        if component is not None and component.par['Manualtime'] is not None:
            component.par.Autotime = False
            scale = getattr(component.par, 'Timescale', None)
            component.par.Manualtime = animation_time(animation, name, seconds,
                                                      float(scale.eval()) if scale is not None else 1.0)
    if deck.fetch('imagefx_cue_playback',False,search=False) is True:
        deck.parent().ext.ShowControlExt._tick_puppet_cue_clocks(deck,seconds)


def start_export(show):
    import td
    if show.fetch(JOB_KEY, None, search=False):
        raise ValueError('An export is already running')
    values = [show.par[name].eval() for name in (
        'Exportsource', 'Exportresolution', 'Exportwidth', 'Exportheight', 'Exportfps',
        'Exportduration', 'Exportstart', 'Exportcodec')]
    live = values[0] in REALTIME_SOURCES
    target = (wall_export_target(show) if values[0] == 'wall' else
              review_export_target(show) if values[0] == 'review' else None)
    panorama = current_panorama_size(show) if not live and values[1] == 'panoramic' else (5760, 1080)
    dimensions = (target.width, target.height) if values[0] == 'review' else (864,162)
    settings = export_settings(*values, panorama=panorama, review_size=dimensions)
    if live:
        quality = getattr(show.par, 'Liveencoderquality', None)
        settings['live_quality'] = quality.eval() if quality is not None else 'balanced'
        if settings['live_quality'] not in dict(LIVE_ENCODER_QUALITIES):
            raise ValueError('Choose a valid Live Encoder Quality')
    warmup = getattr(show.par, 'Wallrecordwarmup', None)
    settings['warmup'] = wall_warmup_seconds(warmup.eval() if warmup is not None else 2) if live else 0
    cue = None if live else selected_snapshot(show, settings['source'])
    settings['projection'] = None if live else selected_projection_plan(show, cue)
    if settings['projection'] and settings['panoramic']:
        raise ValueError('Choose a per-projector resolution (1080p/4K/Custom), or Full Cue Canvas for the Panoramic preset')
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
    name = ('wall-2x2-confidence' if values[0] == 'wall' else 'projector-review-' + review_selection(show)
            if values[0] == 'review' else cue['name'])
    safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '-', name).strip('-')[:60] or 'cue'
    suffix = export_suffix(settings['codec'])
    # A separate unique directory is atomically reserved; never overwrite a file.
    jobdir = folder / (safe_name + '-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    jobdir.mkdir(exist_ok=False)
    path = jobdir if settings['projection'] else jobdir / ('render' + suffix)
    ext = show.ext.ShowControlExt
    job = dict(id=uuid.uuid4().hex, settings=settings, cue=cue, path=path, index=0, deck=None, writer=None,
               stage='loading', deadline=time.monotonic() + 90)
    show.store(JOB_KEY, job)
    show.par.Exportbusy = True
    show.par.Exportprogress = 0
    show.par.Exportstatus = 'Preparing separate render copy (silent)...'
    show.par.Exportresult = str(path)
    try:
        if live:
            # Tap the final packed TOP. No copied cue, routing edits, transport
            # changes, opened windows, or automatic release of blackouts.
            deck = show.create(td.baseCOMP, 'export_live_' + job['id'][:8])
            deck.store('imagefx_show_runtime', True)
            job['deck'] = deck
            job['writer'] = _writer(deck, target, path, settings)
            info = deck.create(td.infoCHOP, 'encoder_info')
            info.par.op = 'export_writer'
            job.update(info=info, target=target, dropped=0, stage='warming',
                       warm_until=time.monotonic()+settings['warmup'], warm_frames=0)
            if settings['source'] == 'review':
                job.update(review_view=review_selection(show), review_route=show.par.Reviewroute.eval(),
                           review_dimensions=(target.width,target.height))
            show.par.Exportstatus = 'WARMING live render pipeline — not recording yet; wait for RECORDING before GO'
            _later(show)
            return
        deck = ext._new_deck('export_render_' + uuid.uuid4().hex[:8])
        job['deck'] = deck
        ext._apply_look(deck, ext._prepare_cue_look(deck,cue['look']))
        configure_export_canvas(show, deck, settings)
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
        output = export_render_target(show, deck, settings)
        if settings['projection']:
            job['targets'] = projection_render_targets(deck, output, settings)
            channels = settings['projection']['channels']
            job['paths'] = [jobdir / ('projector-{}{}'.format(i, suffix)) for i in channels]
            job['writers'] = []
            for i, target, file in zip(channels, job['targets'], job['paths']):
                job['writers'].append(_writer(deck, target, file, settings, 'export_writer_p' + str(i)))
            job['target'], job['writer'] = job['targets'][0], job['writers'][0]
        else:
            job['target'] = output
            job['writer'] = _writer(deck, output, path, settings)
        _later(show)
    except Exception:
        finish_export(show, 'FAILED')
        raise


def finish_export(show, outcome):
    job = show.fetch(JOB_KEY, None, search=False)
    if not job:
        show.par.Exportbusy = False
        return
    deck = job.get('deck')
    error = ''
    writers = job.get('writers') or [job.get('writer')]
    for writer in writers:
        if writer is None:
            continue
        try:
            writer.par.record = False
            writer.cook(force=True)
            error = error or writer.errors()
        except Exception as exc:
            error = str(exc)
    path = job['path']
    paths = job.get('paths') or [path]
    if outcome == 'COMPLETE' and (error or any(not p.is_file() or not p.stat().st_size for p in paths)):
        outcome = 'FAILED: encoder did not produce a valid file. ' + str(error)
    if outcome == 'COMPLETE' and job['settings'].get('projection'):
        try:
            from tdimagefx.jsonutil import atomic_write_json
            settings = job['settings']
            atomic_write_json(path / 'export.json', dict(cue=job['cue']['name'],
                cue_id=job['cue']['id'], fps=settings['fps'], frames=job['index'], start=settings['start'],
                width=settings['width'], height=settings['height'],
                panoramic=settings['projection']['panoramic'], calibration_included=False, audio_included=False,
                files={str(i): p.name for i, p in zip(settings['projection']['channels'], paths)}))
        except Exception as exc:
            outcome = 'FAILED: could not write channel export manifest: ' + str(exc)
    show.unstore(JOB_KEY)
    if deck is not None:
        try:
            deck.destroy()  # only the copy created and owned by this job
        except Exception:
            pass  # it may already have been removed by a project reinitialization
    show.par.Exportbusy = False
    if outcome == 'COMPLETE':
        show.par.Exportprogress = 1
        status = 'COMPLETE — {} frames, {:.3f}s, silent video'.format(
            job['index'], job['index'] / job['settings']['fps'])
        if job['settings'].get('panoramic'):
            status += ' | {}x{} full panorama'.format(
                job['settings']['width'], job['settings']['height'])
        if job['settings'].get('projection'):
            settings = job['settings']
            status += ' | P{} | {} synchronized files'.format(
                ', P'.join(str(i) for i in settings['projection']['channels']), len(paths))
        if job['settings']['source'] == 'wall':
            dropped = job.get('dropped', 0)
            status += ' | 3840x2160 wall + confidence | {} dropped frames{}'.format(
                dropped, ' — WARNING: review recording for stutter' if dropped else '')
        elif job['settings']['source'] == 'review':
            dropped = job.get('dropped', 0)
            status += ' | Projector Review {} | {}x{} | {} dropped frames{}'.format(
                job['review_view'], job['settings']['width'], job['settings']['height'], dropped,
                ' — WARNING: review recording for stutter' if dropped else '')
        show.par.Exportstatus = status
    else:
        show.par.Exportstatus = outcome + ' — partial output retained; not a finished export'
    show.par.Exportresult = str(path)


def _wall_counts(job):
    job['info'].cook(force=True)
    previous_dropped = job.get('dropped', 0)
    for key, channel in (('index', 'total_frames_written'), ('dropped', 'total_frames_dropped')):
        value = job['info'][channel]
        if value is None:
            raise ValueError('Encoder progress channel unavailable: ' + channel)
        job[key] = int(value[0])
    if job['dropped'] > previous_dropped:
        events = job.setdefault('drop_events', [])
        if len(events) < 16:
            events.append(dict(written=job['index'], dropped=job['dropped']))


def stop_wall_export(show):
    job = show.fetch(JOB_KEY, None, search=False)
    if not job or job['settings']['source'] not in REALTIME_SOURCES:
        raise ValueError('Stop & Save is only for a running 2x2 wall or Projector Review recording')
    _wall_counts(job)
    finish_export(show, 'COMPLETE' if job['index'] else 'CANCELLED: no frames recorded')


def _wall_step(show, job):
    if any(window_open(w) for w in _export_windows(show)):
        raise ValueError('Close audience/output windows while recording (shared GPU)')
    if job['settings'].get('source', 'wall') == 'review':
        if review_selection(show) != job['review_view'] or show.par.Reviewroute.eval() != job['review_route']:
            raise ValueError('Projector Review view/output route changed during recording')
        target = review_export_target(show, cook=False)
        if target != job['target'] or (target.width,target.height) != job['review_dimensions']:
            raise ValueError('Projector Review target/resolution changed during recording')
        label = 'Projector Review ' + job['review_view']
    else:
        if wall_export_target(show, cook=False) != job['target']:
            raise ValueError('Wall output changed during recording')
        label = '2x2 wall + confidence'
    writer, settings = job['writer'], job['settings']
    if job['stage'] == 'warming':
        # Warm the WHOLE local capture branch (including any padding shader),
        # not just its source. Normal cooks reuse this frame's rendered textures.
        # Never force a second traversal of the live effect graph for validation.
        writer.cook(force=False)
        import td
        frame = td.absTime.frame
        if job.get('warm_frame') != frame:
            job['warm_frame'] = frame
            job['warm_frames'] += 1
        remaining = max(0, job['warm_until']-time.monotonic())
        show.par.Exportstatus = 'WARMING — {:.1f}s remaining, {} rendered frames; not recorded'.format(
            remaining,job['warm_frames'])
        if remaining == 0 and job['warm_frames'] >= 2:
            writer.par.record = True
            writer.cook(force=False)
            if writer.errors():
                raise ValueError(str(writer.errors()))
            job['stage'] = 'recording'
            job['deadline'] = time.monotonic() + settings['duration'] + 90
            show.par.Exportstatus = 'RECORDING {} — ready for GO; silent, real-time'.format(label)
        _later(show)
        return
    writer.cook(force=False)
    if writer.errors():
        raise ValueError(str(writer.errors()))
    _wall_counts(job)
    show.par.Exportprogress = min(1, job['index'] / settings['frames'])
    show.par.Exportstatus = 'Recording {}: {}/{} frames | {} dropped | silent, real-time'.format(
        label, job['index'], settings['frames'], job['dropped'])
    if job['index'] >= settings['frames']:
        finish_export(show, 'COMPLETE')
    elif time.monotonic() > job['deadline']:
            raise ValueError('Live recorder timed out before its requested frame count')
    else:
        _later(show)


def export_reader_ready(reader):
    reader.cook(force=True)
    if reader.isInvalid:
        raise ValueError('A media source could not be decoded: ' + reader.name)
    # An open file can still have a black GPU texture, especially just after
    # preload. Wait for decoded pixels before writing even the very first frame.
    return bool(reader.isOpen and reader.isFullyPreRead)


def step(show, job_id=None):
    job = show.fetch(JOB_KEY, None, search=False)
    if not job or (job_id is not None and job['id'] != job_id):
        return
    try:
        if job['settings']['source'] in REALTIME_SOURCES:
            _wall_step(show, job)
            return
        ext = show.ext.ShowControlExt
        if ext.engine.state != 'stopped' or any(window_open(w) for w in _export_windows(show)):
            raise ValueError('Export cancelled because show playback/output was opened')
        deck, writer, settings = job['deck'], job['writer'], job['settings']
        writers, targets = job.get('writers') or [writer], job.get('targets') or [job['target']]
        if job['index'] >= settings['frames']:
            finish_export(show, 'COMPLETE')
            return
        seconds = settings['start'] + job['index'] / settings['fps']
        _set_time(deck, ext.model.MODULES, seconds)
        if job['movie'] is not None:
            job['movie'].par.index = job['cue']['media_in'] + seconds * job['cue']['speed']
        for reader in job['readers']:
            if not export_reader_ready(reader):
                if time.monotonic() > job['deadline']:
                    raise ValueError('Media preload timed out')
                _later(show)
                return
        for output in targets:
            output.cook(force=True)
            if (settings['panoramic'] or settings.get('projection')) and (output.width, output.height) != (settings['width'], settings['height']):
                raise ValueError('Export resolution unavailable; check TouchDesigner license and GPU limits')
        errors = deck.errors(recurse=True)
        if errors:
            raise ValueError(str(errors))
        if job['stage'] == 'loading':
            for encoder in writers:
                encoder.par.record = True
            job['stage'] = 'rendering'
        for encoder in writers:
            encoder.par.addframe.pulse()
            encoder.cook(force=True)
            if encoder.errors():
                raise ValueError(encoder.errors())
        job['index'] += 1
        job['deadline'] = time.monotonic() + 90
        show.par.Exportprogress = job['index'] / settings['frames']
        show.par.Exportstatus = 'Rendering {}/{} frames — silent, off-air'.format(job['index'], settings['frames'])
        _later(show)
    except Exception as exc:
        finish_export(show, 'FAILED: ' + str(exc)[:350])


def on_pulse(show, name):
    try:
        if name in WALL_ACTIONS:
            wall = show.parent().op('wall_output')
            if wall is None:
                raise ValueError('Wall Output is unavailable in this project')
            # Keep the existing UHD/display safety checks. Do not open a
            # Window COMP directly or release either blackout automatically.
            wall.op('controller').module.action(wall, WALL_ACTIONS[name])
            show.par.Wallactionstatus = 'Linked to wall_output; opening never clears blackout'
        elif name == 'Openprojectorreview':
            review_target(show).openViewer()
        elif name == 'Startexport':
            start_export(show)
        elif name == 'Cancelexport':
            finish_export(show, 'CANCELLED')
        elif name == 'Stopexport':
            stop_wall_export(show)
        else:
            return False
        return True
    except Exception as exc:
        if name in WALL_ACTIONS:
            show.par.Wallactionstatus = str(exc)[:500]
        else:
            show.par.Exportstatus = str(exc)[:500]
        return False


def startup(show):
    # A saved TOE must never resume an interrupted render or retain runtime OPs.
    show.unstore(JOB_KEY)
    show.par.Exportbusy = False
    show.par.Exportprogress = 0
    show.par.Exportstatus = 'Idle — choose cue/draft render, Projector Review or 2x2 wall recording'


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
    layout = show.op('show_panel_layout')
    if layout is not None:
        layout.module.configure(show)


def install_wall_controls(show):
    """Add a two-way wall control surface without changing output/cue state."""
    wall = show.parent().op('wall_output')
    if wall is None:
        raise ValueError('Install wall_output before the Show Control wall tab')
    page = next((p for p in show.customPages if p.name == 'Wall Output'), None)
    if page is None:
        page = show.appendCustomPage('Wall Output')
    for alias, target, label in WALL_BINDINGS:
        master = show.par[target] if target == 'Masterblackout' else wall.par[target]
        item = show.par[alias]
        if item is None:
            item = getattr(page, 'append' + master.style)(alias, label=label)[0]
        item.label = label
        item.default = master.default
        if master.isMenu:
            item.menuNames, item.menuLabels = master.menuNames, master.menuLabels
        if master.isInt or master.isFloat:
            item.min, item.max = master.min, master.max
            item.normMin, item.normMax = master.normMin, master.normMax
            item.clampMin, item.clampMax = master.clampMin, master.clampMax
        item.readOnly = False
        # Never assign item.val here: on a repeat install it may already be
        # bound and would write through to the real output controls.
        item.bindExpr = ('me.par.Masterblackout' if target == 'Masterblackout'
                         else "me.parent().op('wall_output').par." + target)
        item.mode = type(item.mode).BIND
    for name, label in (
        ('Wallcheckdisplay', 'Check Display / Refresh List'),
        ('Wallopen', 'OPEN 4K WALL (Perform Mode)'),
        ('Wallclose', 'CLOSE 4K WALL'),
    ):
        if show.par[name] is None:
            page.appendPulse(name, label=label)
    for name, target, label in (
        ('Wallstatus', 'Status', 'Wall / Display Status'),
        ('Walldisplays', 'Displays', 'Connected Displays'),
        ('Wallsourcesstatus', 'Sourcesstatus', 'Source Status'),
    ):
        item = show.par[name]
        if item is None:
            item = page.appendStr(name, label=label)[0]
        item.expr = "me.parent().op('wall_output').par.{}.eval()".format(target)
        item.readOnly = True
    if show.par['Wallactionstatus'] is None:
        item = page.appendStr('Wallactionstatus', label='Control Status')[0]
        item.val = 'Linked to wall_output; opening never clears blackout'
        item.readOnly = True
    return page


def guard_show_actions(text):
    """Exclude our pulses from the generic dispatcher, preserving other guards."""
    guard = "    if par.name in parent().op('show_review_export').module.ACTIONS:\n        return\n"
    text = re.sub(r"    if par\.name in \('Openprojectorreview',[^\n]*\):\n        return\n", '', text)
    return text if guard in text else text.replace('def onPulse(par):\n', 'def onPulse(par):\n' + guard, 1)


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
    install_wall_controls(show)
    p = page('Projector Review')
    par(p, 'Reviewroute', 'Output Route', 'Menu', 'wall', menu=[('wall', '4K Wall Processor'), ('atlas', 'Direct Displays')], readonly=show.par['Outputmode'] is not None)
    view = par(p, 'Reviewprojector', 'Review View', 'Menu', 'auto', menu=REVIEW_VIEWS)
    # Upgrade an existing menu as well as a new one, without losing its selection.
    selected = view.eval()
    view.menuNames, view.menuLabels = [x[0] for x in REVIEW_VIEWS], [x[1] for x in REVIEW_VIEWS]
    view.label, view.default = 'Review View', 'auto'
    view.val = selected if selected in view.menuNames else 'auto'
    view.enableExpr = "not me.par.Exportbusy or me.par.Exportsource != 'review'"
    quality = par(p, 'Reviewresolution', 'Three-Up Resolution / Per Projector', 'Menu', '1080p', menu=REVIEW_RESOLUTIONS)
    selected = quality.eval()
    quality.menuNames, quality.menuLabels = [x[0] for x in REVIEW_RESOLUTIONS], [x[1] for x in REVIEW_RESOLUTIONS]
    quality.val = selected if selected in quality.menuNames else '1080p'
    quality.enableExpr = view.enableExpr
    for name, label, default in (('Reviewwidth', 'Custom Cell Width', 1920), ('Reviewheight', 'Custom Cell Height', 1080)):
        item = par(p, name, label, 'Int', default, (16,4096))
        item.enableExpr = "me.par.Reviewresolution == 'custom' and (not me.par.Exportbusy or me.par.Exportsource != 'review')"
    par(p, 'Reviewcanvasinfo', 'Three-Up Canvas / Export Codec', 'Str', '', readonly=True).expr = "me.op('show_review_export').module.review_resolution_info(me)"
    par(p, 'Openprojectorreview', 'Open Projector Review', 'Pulse')
    par(p, 'Reviewstatus', 'Signal Status', 'Str', '', readonly=True).expr = "me.op('show_review_export').module.review_status(me)"
    review_order = ['Reviewroute','Reviewprojector','Reviewresolution','Reviewwidth','Reviewheight',
                    'Reviewcanvasinfo','Openprojectorreview','Reviewstatus']
    p.sort(*review_order, *[item.name for item in p.pars if item.name not in review_order])
    p = page('Export Video')
    source = par(p, 'Exportsource', 'Export Source', 'Menu', 'cue', menu=EXPORT_SOURCES)
    selected = source.eval()
    source.menuNames, source.menuLabels = [x[0] for x in EXPORT_SOURCES], [x[1] for x in EXPORT_SOURCES]
    source.val = selected if selected in source.menuNames else 'cue'
    channels = par(p, 'Exportchannels', 'Export Projection Channels', 'Menu', 'canvas', menu=EXPORT_CHANNELS)
    selected = channels.eval()
    channels.menuNames, channels.menuLabels = [x[0] for x in EXPORT_CHANNELS], [x[1] for x in EXPORT_CHANNELS]
    channels.val = selected if selected in channels.menuNames else 'canvas'
    channels.enableExpr = "not me.par.Exportbusy and me.par.Exportsource not in ('wall','review')"
    order = [item.name for item in p.pars if item.name != 'Exportchannels']
    order.insert(order.index('Exportsource') + 1, 'Exportchannels')
    p.sort(*order)
    par(p, 'Exportinfo', 'Export Mode / Canvas', 'Str', '', readonly=True).expr = "me.op('show_review_export').module.export_description(me)"
    par(p, 'Exportfolder', 'Export Folder', 'Folder', '.imagefx/exports')
    par(p, 'Exportcodec', 'Format', 'Menu', 'h264', menu=EXPORT_CODECS)
    upgrade_codec_menu(show)
    resolution = par(p, 'Exportresolution', 'Resolution', 'Menu', '1080p', menu=EXPORT_RESOLUTIONS)
    selected = resolution.eval()
    resolution.menuNames, resolution.menuLabels = [x[0] for x in EXPORT_RESOLUTIONS], [x[1] for x in EXPORT_RESOLUTIONS]
    resolution.val = selected if selected in resolution.menuNames else '1080p'
    for name, label, default in [('Exportwidth','Width',1920), ('Exportheight','Height',1080)]:
        par(p, name, label, 'Int', default, (16,4096)).enableExpr = "not me.par.Exportbusy and me.par.Exportsource not in ('wall','review') and me.par.Exportresolution == 'custom'"
    par(p, 'Exportfps', 'Frames / Second', 'Menu', '30', menu=[(str(n),str(n)) for n in (24,25,30,50,60)])
    quality = par(p, 'Liveencoderquality', 'Live Encoder Quality', 'Menu', 'balanced', menu=LIVE_ENCODER_QUALITIES)
    quality.enableExpr = "not me.par.Exportbusy and me.par.Exportsource in ('wall','review') and me.par.Exportcodec in ('h264','h265')"
    par(p, 'Exportduration', 'Duration (seconds)', 'Float', 10, (.02,3600))
    par(p, 'Exportstart', 'Effect Start (seconds)', 'Float', 0, (0,86400))
    warmup = par(p, 'Wallrecordwarmup', 'Live Render Warm-up (seconds)', 'Float', 2, (0,10))
    warmup.label = 'Live Render Warm-up (seconds)'
    warmup.enableExpr = "not me.par.Exportbusy and me.par.Exportsource in ('wall','review')"
    par(p, 'Startexport', 'Export Video (Silent)', 'Pulse').enableExpr = 'not me.par.Exportbusy'
    stop = par(p, 'Stopexport', 'Stop Recording & Save', 'Pulse')
    stop.label = 'Stop Recording & Save'
    stop.enableExpr = "bool(me.par.Exportbusy) and me.par.Exportsource in ('wall','review')"
    par(p, 'Cancelexport', 'Cancel Export', 'Pulse').enableExpr = 'bool(me.par.Exportbusy)'
    par(p, 'Exportbusy', 'Export Running', 'Toggle', False, readonly=True)
    par(p, 'Exportprogress', 'Progress', 'Float', 0, (0,1), readonly=True)
    par(p, 'Exportstatus', 'Export Status', 'Str', 'Idle — export is silent and off-air', readonly=True)
    par(p, 'Exportresult', 'Last Output File', 'Str', '', readonly=True)
    for name in ('Exportsource','Exportfolder','Exportcodec','Exportresolution','Exportfps','Exportduration','Exportstart'):
        show.par[name].enableExpr = 'not me.par.Exportbusy'
    for name in ('Exportresolution', 'Exportstart'):
        show.par[name].enableExpr = "not me.par.Exportbusy and me.par.Exportsource not in ('wall','review')"
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
    actions.text = guard_show_actions(actions.text)
    # Native Select TOP aliases feed two independent fit/layout branches. Only
    # the small branch is referenced by the embedded panel; the full branch is
    # demanded by enlarged review or recording, not by reading its dimensions.
    fit_code = node('textDAT', 'review_fit_code')
    fit_code.text = CHANNEL_SHADER
    for i in (1,2,3):
        feed = node('selectTOP','review_p{}'.format(i))
        feed.par.top.expr = "parent().op('show_review_export').module.review_path(parent(), {})".format(i)
        feed.par.outputresolution = 'useinput'
        feed.par.resmult = False
        for prefix, size_function in (('review_full_p', 'review_panel_size'), ('review_thumbnail_p', 'review_thumbnail_size')):
            fitted = node('glslTOP', prefix + str(i))
            fitted.par.pixeldat = fit_code.name
            fitted.par.outputresolution = 'custom'
            fitted.par.resmult = False
            for axis, index in (('w',0),('h',1)):
                fitted.par['resolution' + axis].expr = "parent().op('show_review_export').module.{}(parent())[{}]".format(size_function,index)
            fitted.seq.vec.numBlocks = 1
            fitted.par.vec0name = 'uSlice'
            fitted.par.vec0valuex, fitted.par.vec0valuey = 0, 1
            feed.outputConnectors[0].connect(fitted.inputConnectors[0])
    for name, prefix, size_function in (('projector_review', 'review_full_p', 'review_panel_size'),
                                        ('projector_review_thumbnail', 'review_thumbnail_p', 'review_thumbnail_size')):
        layout = node('layoutTOP', name)
        for connector in list(layout.inputConnectors):
            connector.disconnect()
        for i in (1,2,3):
            show.op(prefix + str(i)).outputConnectors[0].connect(layout.inputConnectors[i-1])
        layout.par.outputresolution = 'custom'
        layout.par.resmult = False
        layout.par.resolutionw.expr = "3 * parent().op('show_review_export').module.{}(parent())[0]".format(size_function)
        layout.par.resolutionh.expr = "parent().op('show_review_export').module.{}(parent())[1]".format(size_function)
        layout.par.align = 'horizlr'
        layout.par.scaleres = False
        layout.par.fit = 'fitbest'
        layout.par.outputaspect = 'resolution'
    show.op('projector_review').store('imagefx_review_full_canvas', True)
    selected_preview = node('selectTOP', 'review_selected')
    selected_preview.par.top.expr = "parent().op('show_review_export').module.review_preview_target(parent()).path"
    selected_preview.par.outputresolution = 'custom'
    for axis, index in (('w', 0), ('h', 1)):
        selected_preview.par['resolution' + axis].expr = "parent().op('show_review_export').module.review_size(parent())[{}]".format(index)
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
    panel.par.y = 12
    panel.par.w.expr = "op('review_selected').width"
    panel.par.h.expr = "op('review_selected').height"
    panel.par.x.expr = "20 + (880 - me.par.w) / 2"
    panel.par.top = 'review_selected'
    label = node('textCOMP','review_heading')
    label.par.x,label.par.y,label.par.w,label.par.h = 20,174,880,22
    label.par.fontsize = 14
    label.par.text.expr = "parent().op('show_review_export').module.review_heading(parent())"
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
    priority = ('Transport', 'Output Mode', 'Wall Output', 'Projection Mapping', 'Cue Editor', 'Cue Notes', 'Look Editor',
                'Projector Review', 'Export Video', 'Routing',
                'Output 1', 'Output 2', 'Output 3')
    existing_pages = [p.name for p in show.customPages]
    show.sortCustomPages(*([p for p in priority if p in existing_pages] +
                           [p for p in existing_pages if p not in priority]))
    inspector = show.op('cue_inspector')
    # Review/export refreshes must keep the mapping navigation installed by
    # projection_mapping.install(); a hidden tab looks like missing controls.
    inspector.par.pagescope = "Transport 'Output Mode' 'Wall Output' 'Projection Mapping' 'Cue Editor' 'Cue Notes' 'Look Editor' 'Projector Review' 'Export Video' Routing 'Output 1' 'Output 2' 'Output 3'"
    inspector.par.op = ''
    inspector.cook(force=True)
    inspector.par.op = '..'
    inspector.cook(force=True)
    configure_panel_layout(show)
    return runtime
