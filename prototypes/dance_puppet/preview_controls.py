"""Dependency-free playback logic, embedded in the TouchDesigner prototype."""
import math


def advance(position, dt, speed, duration, fps, loop=False, playing=True, enabled=True):
    values = (position,dt,speed,duration,fps)
    if not all(math.isfinite(float(x)) for x in values) or duration <= 0 or fps <= 0:
        raise ValueError('Playback values must be finite; duration and fps positive')
    end = max(0.,duration-1./fps)
    # Keep sub-frame time between the last sample and clip duration in loop
    # mode; clamping it to the last frame each tick can freeze a 30fps clip
    # running in a 60fps TD project forever at its loop boundary.
    position = min(duration if loop else end,max(0.,position))
    if not playing or not enabled:
        return position,bool(playing)
    target = position + max(0.,dt)*speed
    if loop:
        return target % duration,True
    if target > end or target < 0:
        return min(end,max(0.,target)),False
    return target,True


def tick(component, now):
    previous = component.fetch('puppet_previous_time',now)
    component.store('puppet_previous_time',now)
    p = component.par
    pos,playing = advance(float(p.Position),max(0.,now-previous),float(p.Speed),
        float(p.Duration),float(p.Framerate),bool(p.Loop),bool(p.Playing),bool(p.Enabled))
    if abs(pos-float(p.Position)) > 1e-7:
        p.Position = pos
    if playing != bool(p.Playing):
        p.Playing = playing


def action(component, name):
    p = component.par
    if name == 'Go':
        p.Position = 0 if p.Speed >= 0 else max(0,float(p.Duration)-1/float(p.Framerate))
        p.Playing = True
    elif name == 'Pause':
        p.Playing = not p.Playing
    elif name == 'Stop':
        p.Playing = False
        p.Position = 0
    elif name == 'Resetview':
        p.Zoom = 1
        p.Panx = 0
        p.Pany = 0
    elif name == 'Preview':
        component.op('out1').openViewer()


def status(component):
    p = component.par
    state = 'hidden' if not p.Enabled else 'playing' if p.Playing else 'paused'
    return f'PROTOTYPE | {state} | {float(p.Position):.2f} / {float(p.Duration):.2f}s | cached 2.5D motion'
