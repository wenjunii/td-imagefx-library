"""Seekable, bounded movement forces. Pure NumPy; no capture/inference on import."""
import json
import math
import os
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import sys
import time
import types
import numpy as np

KIND = 'tdimagefx.dance-forces.motion'
LANDMARKS = ((23, 24), (11, 12), (15,), (16,), (27,), (28,))


def fade_in(elapsed, duration):
    if not math.isfinite(elapsed) or not math.isfinite(duration):
        raise ValueError('Non-finite fade time')
    if duration <= 0: return 1.
    x = min(1., max(0., elapsed/duration))
    return x*x*(3-2*x)


def observations(poses, quality=True):
    out = np.zeros((2, 6, 3), dtype=float)
    out[..., :2] = .5
    for actor, pose in enumerate(poses[:2]):
        if pose is None:
            continue
        p = np.asarray(pose, float)
        for joint, ids in enumerate(LANDMARKS):
            out[actor, joint, :2] = p[list(ids), :2].mean(axis=0)
            out[actor, joint, 2] = np.clip(p[list(ids), 3].min(), 0, 1) if quality else 0
    # Convert video (Y-down) into TOP coordinates exactly once.
    out[..., 1] = 1 - out[..., 1]
    out[..., :2] = np.clip(out[..., :2], -4, 5)
    return out


class Filter:
    """Velocity-only force with damping: stationary bodies do not hold a warp."""
    def __init__(self):
        self.previous = None
        self.velocity = np.zeros((2, 6, 2))
        self.force = np.zeros((2, 6, 2))

    def step(self, points, dt, smoothing=.12, decay=.65, confidence=.3, threshold=.015):
        points = np.asarray(points, float)
        if points.shape != (2, 6, 3) or not np.isfinite(points).all():
            raise ValueError('Expected two people, six finite XY-confidence points')
        if not all(math.isfinite(x) for x in (dt, smoothing, decay, confidence, threshold)):
            raise ValueError('Non-finite filter setting')
        dt = min(.25, max(.001, dt))
        valid = points[..., 2] >= max(.001, confidence)
        velocity = np.zeros_like(self.velocity)
        if self.previous is not None:
            delta = points[..., :2] - self.previous[..., :2]
            valid &= self.previous[..., 2] >= max(.001, confidence)
            # Reacquisition / identity jumps are not dancer impulses.
            valid &= np.linalg.norm(delta, axis=-1) < max(.06, dt * 2.)
            velocity = delta / dt
            speed = np.linalg.norm(velocity, axis=-1)
            velocity *= (np.maximum(0, speed - threshold) / np.maximum(speed, 1e-9))[..., None]
        velocity *= valid[..., None]
        alpha = 1 - math.exp(-dt / max(.015, smoothing))
        self.velocity += alpha * (velocity - self.velocity)
        # Suppress extrapolation through a lost/camera-invalid observation.
        self.velocity *= valid[..., None]
        retention = math.exp(-dt / max(.03, decay))
        self.force = self.force * retention + self.velocity * (1 - retention) * min(1., decay)
        length = np.linalg.norm(self.force, axis=-1)
        self.force *= np.minimum(1, .22 / np.maximum(1e-9, length))[..., None]
        self.previous = points.copy()
        return self.force.copy()


def _cooperative_document(text):
    """Parse frame-sized JSON pieces so a worker never owns the GIL for a movie.

    The motion schema's only large field is frames. Ordinary metadata retains
    the standard JSON decoder and all data still goes through Clip validation.
    """
    decoder = json.JSONDecoder()
    length = len(text)
    def ws(at):
        while at < length and text[at].isspace(): at += 1
        return at
    at = ws(0)
    if at >= length or text[at] != '{': raise ValueError('Expected motion object')
    at += 1; doc = {}
    while True:
        at = ws(at)
        if at < length and text[at] == '}': at += 1; break
        key, at = decoder.raw_decode(text,at)
        if not isinstance(key,str): raise ValueError('Expected motion key')
        at = ws(at)
        if at >= length or text[at] != ':': raise ValueError('Expected colon')
        at = ws(at+1)
        if key == 'frames' and at < length and text[at] == '[':
            frames = []; at = ws(at+1)
            while at < length and text[at] != ']':
                value, at = decoder.raw_decode(text,at); frames.append(value)
                if len(frames) > 216000: raise ValueError('Too many force frames')
                if len(frames) % 16 == 0: time.sleep(0)
                at = ws(at)
                if at < length and text[at] == ',':
                    at = ws(at+1)
                    if at < length and text[at] == ']': raise ValueError('Trailing comma')
                elif at >= length or text[at] != ']': raise ValueError('Expected frame separator')
            if at >= length: raise ValueError('Unclosed force frames')
            at += 1
            # Converting a single giant list can also block the render thread.
            value = np.empty((len(frames),2,6,3),dtype=float)
            for first in range(0,len(frames),64):
                chunk = np.asarray(frames[first:first+64],float)
                if chunk.shape != (min(64,len(frames)-first),2,6,3):
                    raise ValueError('Invalid Dance Forces cache dimensions')
                value[first:first+64] = chunk
                time.sleep(0)
        else:
            value, at = decoder.raw_decode(text,at)
        doc[key] = value
        at = ws(at)
        if at < length and text[at] == ',':
            at = ws(at+1)
            if at < length and text[at] == '}': raise ValueError('Trailing comma')
        elif at < length and text[at] == '}': at += 1; break
        else: raise ValueError('Expected motion separator')
    if ws(at) != length: raise ValueError('Trailing motion data')
    return doc


class Clip:
    def __init__(self, doc):
        if doc.get('kind') != KIND or doc.get('schema_version') != 1:
            raise ValueError('Not a Dance Forces v1 cache; analyze the video first')
        self.fps = float(doc['fps'])
        self.points = np.asarray(doc['frames'], float)
        if not math.isfinite(self.fps) or not 1 <= self.fps <= 60:
            raise ValueError('Cache frame rate must be 1..60')
        if self.points.ndim != 4 or self.points.shape[1:] != (2, 6, 3) or not 2 <= len(self.points) <= 216000:
            raise ValueError('Invalid Dance Forces cache dimensions')
        if not np.isfinite(self.points).all() or np.any(np.abs(self.points[..., :2]) > 5):
            raise ValueError('Invalid force positions')
        if np.any(self.points[..., 2] < 0) or np.any(self.points[..., 2] > 1):
            raise ValueError('Confidence must be 0..1')
        if not doc.get('camera_motion', {}).get('removed'):
            raise ValueError('This cache has not had camera movement removed')
        self.duration = len(self.points) / self.fps
        self.settings = None

    @classmethod
    def read(cls, path, *, cooperative=False):
        path = Path(path)
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Motion cache exceeds 64 MiB')
        text = path.read_text(encoding='utf-8')
        return cls(_cooperative_document(text) if cooperative else json.loads(text))

    def prepare(self, settings, *, cooperative=False):
        if settings == self.settings: return
        filt = Filter()
        forces = np.empty(self.points.shape[:3]+(2,),dtype=float)
        for i,p in enumerate(self.points):
            forces[i] = filt.step(p,1/self.fps,*settings)
            if cooperative and i % 16 == 0: time.sleep(0)
        self.forces = forces
        self.settings = settings

    def sample(self, seconds, *, loop=True, smoothing=.12, decay=.65, confidence=.3, threshold=.015):
        if not math.isfinite(seconds):
            raise ValueError('Invalid motion time')
        settings = (float(smoothing), float(decay), float(confidence), float(threshold))
        if not (.015 <= settings[0] <= 1 and .03 <= settings[1] <= 3 and 0 <= settings[2] <= 1 and 0 <= settings[3] <= 1):
            raise ValueError('Invalid force filter controls')
        if settings != self.settings:
            self.prepare(settings)
        t = max(0., seconds)
        if loop:
            t %= self.duration
        frame = min(len(self.points)-1, t * self.fps)
        lo = int(frame); hi = min(lo+1, len(self.points)-1); mix = frame-lo
        points = self.points[lo] * (1-mix) + self.points[hi] * mix
        force = self.forces[lo] * (1-mix) + self.forces[hi] * mix
        # Fade at loop seam; no last-to-first derivative / teleport impulse.
        if loop:
            force *= min(1., t/.15, max(0., self.duration-t)/.15)
        elif t > self.duration:
            force *= math.exp(-(t-self.duration)/decay)
        return points, force


class PreparedClips:
    """Bounded, shared preparation; workers touch only files and NumPy, never TD.

    request() never waits on a Future. A returned clip is already filtered and
    immutable for its settings, so all decks can sample it without rebuilding.
    """
    def __init__(self, capacity=8, loader=None, check_interval=1.):
        self.capacity = capacity
        self.check_interval = check_interval
        self.loader = loader or (lambda path: Clip.read(path,cooperative=True))
        self.ready = OrderedDict()
        self.pending = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ImageFX-force-prepare')

    def _prepare(self, path, settings, previous):
        resolved = Path(path).resolve()
        stat = resolved.stat()
        key = (path,stat.st_mtime_ns,stat.st_size,tuple(settings))
        if previous is not None and previous[0] == key and not isinstance(previous[1],Exception):
            return key, previous[1]
        clip = self.loader(resolved)
        # Validate filter controls before preparation, without a synchronous
        # first sample rebuilding the full clip on the caller's thread.
        if not (.015 <= settings[0] <= 1 and .03 <= settings[1] <= 3 and 0 <= settings[2] <= 1 and 0 <= settings[3] <= 1):
            raise ValueError('Invalid force filter controls')
        clip.prepare(tuple(settings),cooperative=True)
        return key, clip

    def request(self, path, settings):
        # Lexical normalization only. Even stat()/resolve() can block on a cold
        # Windows volume or antivirus scan: all filesystem work belongs below
        # _prepare(), off the TouchDesigner render thread.
        path = os.path.normcase(os.path.abspath(str(path)))
        request = (path,tuple(settings))
        for job, future in list(self.pending.items()):
            if not future.done():
                continue
            try:
                key, value = future.result()
            except Exception as exc:
                key, value = (job[0],None,None,job[1]), exc
            self.ready[job] = (key,value,time.monotonic())
            del self.pending[job]
        while len(self.ready) > self.capacity:
            self.ready.popitem(last=False)
        previous = self.ready.get(request)
        if previous is not None: self.ready.move_to_end(request)
        # Bound pending work during rapid slider drags. The next rendered frame
        # requests the newest settings once a slot is free; no unbounded queue.
        stale = previous is None or time.monotonic()-previous[2] >= self.check_interval
        if stale and request not in self.pending and len(self.pending) < 2:
            self.pending[request] = self.executor.submit(self._prepare,path,tuple(settings),previous)
        if previous is not None:
            key,value,_ = previous
            if isinstance(value,Exception): raise ValueError(str(value)) from value
            return key,value
        return (path,None,None,tuple(settings)), None

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def prepared_clips():
    # DAT modules are separate per component. Keep one bounded preparation
    # service for the process rather than a thread and duplicate cache per deck.
    name = '_tdimagefx_prepared_dance_forces_v3'
    if name not in sys.modules:
        service = types.ModuleType(name)
        service.cache = PreparedClips()
        sys.modules[name] = service
    return sys.modules[name].cache


def map_forces(points, forces, *, zoom=1.5, panx=0, pany=0, mirror=False,
               body=.65, hands=1., feet=.65, actor1=1., actor2=1., strength=1.):
    settings = (zoom, panx, pany, body, hands, feet, actor1, actor2, strength)
    if not all(math.isfinite(float(v)) for v in settings):
        raise ValueError('Non-finite force mapping')
    sign = np.array([-1 if mirror else 1, 1])
    center = (points[..., :2]-.5) * zoom * sign + .5 + [panx, pany]
    weights = np.array([body, body, hands, hands, feet, feet])[None, :] * np.array([actor1, actor2])[:, None]
    force = forces * weights[..., None] * sign * zoom * strength
    force *= np.minimum(1, .25/np.maximum(1e-9, np.linalg.norm(force, axis=-1)))[..., None]
    return np.concatenate((center, force), axis=-1).reshape(12, 4)
