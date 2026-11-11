"""Embedded TouchDesigner controller. The motion math lives in a sibling DAT."""
import json
from pathlib import Path

_clip = None
_busy = False
_previous = None
_configured_clip = None


def model(c):
    global _clip, _configured_clip
    if _clip is None:
        _clip = c.op('motion_math').module.MotionClip(json.loads(c.op('motion_data').text))
    if _configured_clip is not _clip:
        # Parameter range edits rebuild TD's custom parameter interfaces. They
        # belong to clip loading, never to the per-frame transport path.
        p = c.par
        p.Duration = _clip.duration
        p.Framerate = _clip.fps
        p.Position.max = _clip.duration
        p.Position.normMax = _clip.duration
        p.Referencepose.max = _clip.end
        p.Referencepose.normMax = _clip.end
        _configured_clip = _clip
    return _clip


def refresh(c):
    global _busy
    if _busy:
        return
    _busy = True
    try:
        clip = model(c)
        p = c.par
        # Preserve fractional phase between the last sample and duration.
        # Sample/decode clamps to clip.end, while a loop's clock can wrap.
        seconds = min(clip.end, max(0., float(p.Position) + float(p.Motionoffset)))
        vec, energy = c.op('motion_math').module.vectors(
            clip, seconds, smoothing=float(p.Smoothing), confidence=float(p.Confidence),
            reference=float(p.Referencepose), stagezoom=float(p.Stagezoom),
            panx=float(p.Stagepanx), pany=float(p.Stagepany), mirror=bool(p.Mirror),
            posegain=float(p.Posefollow), velocitygain=float(p.Velocityresponse),
            body=float(p.Bodyweight), hands=float(p.Handweight), feet=float(p.Footweight),
            dancer1=float(p.Dancer1), dancer2=float(p.Dancer2))
        c.par.Energy1 = float(energy[0])
        c.par.Energy2 = float(energy[1])
        shader = c.op('motion_warp')
        for i, row in enumerate(vec):
            for axis, value in zip('xyzw', row):
                shader.par[f'vec{i+3}value{axis}'] = float(value)
        c.par.Status = ('PLAYING' if p.Playing else 'PAUSED') + f' | {float(p.Position):.2f} / {clip.duration:.2f}s | cached 2D motion; no audio'
    except Exception as exc:
        c.par.Playing = False
        c.par.Status = 'MOTION ERROR: ' + str(exc)
        # Fail to unwarped artwork, not the previous dancer's force field.
        for i in range(12):
            for axis in 'zw':
                c.op('motion_warp').par[f'vec{i+3}value{axis}'] = 0
        c.par.Energy1 = 0
        c.par.Energy2 = 0
    finally:
        _busy = False


def tick(c, now):
    global _previous, _busy
    previous = now if _previous is None else _previous
    _previous = now
    if _busy or not c.par.Playing:
        return
    try:
        clip = model(c)
        position, playing = c.op('motion_math').module.advance(
            float(c.par.Position), max(0, now-previous), float(c.par.Playbackspeed),
            clip.duration, clip.fps, bool(c.par.Loop), bool(c.par.Playing))
        _busy = True
        c.par.Position = position
        c.par.Playing = playing
        _busy = False
        refresh(c)
    except Exception as exc:
        _busy = False
        c.par.Playing = False
        c.par.Status = 'TRANSPORT ERROR: ' + str(exc)


def changed(c, name):
    if _busy:
        return
    if name == 'Position':
        c.store('backdrop_phase', float(c.par.Position))
    refresh(c)


def action(c, name):
    global _clip, _previous
    p = c.par
    _previous = None
    if name == 'Go':
        p.Position = 0 if p.Playbackspeed >= 0 else model(c).end
        c.store('backdrop_phase', float(p.Position))
        p.Playing = True
    elif name == 'Pause':
        p.Playing = not p.Playing
    elif name == 'Stop':
        p.Playing = False
        p.Position = 0
        c.store('backdrop_phase', 0.)
    elif name == 'Setreference':
        p.Referencepose = min(model(c).end, max(0., float(p.Position)+float(p.Motionoffset)))
    elif name == 'Reloadmotion':
        # Validate completely before replacing the working embedded data.
        try:
            path = str(p.Motionfile.eval()).strip()
            if not path:
                raise ValueError('Choose a converted motion JSON first')
            document = c.op('motion_math').module.read_document(Path(path))
            candidate = c.op('motion_math').module.MotionClip(document)
            text = json.dumps(document, separators=(',', ':'), allow_nan=False)
            c.op('motion_data').text = text
            _clip = candidate
            p.Playing = False
            p.Position = 0
            p.Referencepose = 0
            c.store('backdrop_phase', 0.)
        except Exception as exc:
            p.Status = 'RELOAD REJECTED (previous motion retained): ' + str(exc)
            return
    elif name == 'Reloadmedia':
        for node in ('backdrop_file', 'reference_video'):
            c.op(node).par.reloadpulse.pulse()
    elif name == 'Preview':
        c.op('out1_image').openViewer()
    elif name == 'Compare':
        c.op('comparison').openViewer()
    elif name == 'Resetmotion':
        for parname in ('Motionenabled', 'Strength', 'Radius', 'Posefollow', 'Velocityresponse',
                        'Smoothing', 'Confidence', 'Bodyweight', 'Handweight', 'Footweight',
                        'Dancer1', 'Dancer2', 'Stagezoom', 'Stagepanx', 'Stagepany', 'Mirror',
                        'Shadowresponse', 'Maxdisplacement', 'Motionoffset', 'Referencepose', 'Debug'):
            p[parname] = p[parname].default
    refresh(c)


def startup(c):
    global _clip, _previous
    _clip = None
    _previous = None
    c.par.Playing = False
    c.store('backdrop_phase', float(c.par.Position))
    refresh(c)
