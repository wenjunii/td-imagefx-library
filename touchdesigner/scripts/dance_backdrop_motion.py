"""Local, deterministic 2D pose playback for the dance-driven backdrop.

No character rig, AI inference, network access, or executable cache formats.
Coordinates in the cache are normalized video coordinates (Y points down).
"""
import json
import math
from pathlib import Path

import numpy as np

KIND = "tdimagefx.dance-backdrop.motion"
LANDMARKS = ((23, 24), (11, 12), (15,), (16,), (27,), (28,))
NAMES = ("hips", "shoulders", "left_hand", "right_hand", "left_foot", "right_foot")
MAX_BYTES = 64 * 1024 * 1024


def read_document(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Motion cache exceeds 64 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def convert_observations(doc):
    """Reuse only observed joints, never artwork or a puppet's solved motion."""
    if doc.get("kind") != "imagefx.dance-puppet.motion" or doc.get("schema_version") != 1:
        raise ValueError("Expected the original two-person observed-pose cache")
    frames = []
    for record in doc["frames"]:
        people = []
        for pose in record["poses"]:
            points = []
            for indices in LANDMARKS:
                if pose is None:
                    points.append([0.5, 0.5, 0.0])
                else:
                    entries = [pose[i] for i in indices]
                    score = min(p[3] for p in entries)
                    if not math.isfinite(score):
                        raise ValueError("Non-finite detector score")
                    points.append([sum(p[0] for p in entries) / len(entries),
                                   sum(p[1] for p in entries) / len(entries),
                                   max(0., min(1., score))])
            people.append(points)
        frames.append(people)
    result = {"schema_version": 1, "kind": KIND, "fps": doc["fps"],
              "source_size": doc["source_size"],
              "source_start_seconds": doc.get("source_start_seconds", 0),
              "landmarks": list(NAMES), "frames": frames,
              "tracking_note": "Observed 2D joints; identities initialized left/right. Review occlusions; no 3D depth."}
    MotionClip(result)  # Fail before writing an invalid converted cache.
    return result


class MotionClip:
    def __init__(self, doc):
        if doc.get("kind") != KIND or doc.get("schema_version") != 1:
            raise ValueError("Not a version-1 dance-backdrop motion cache")
        self.fps = float(doc["fps"])
        self.start = float(doc.get("source_start_seconds", 0))
        if not math.isfinite(self.fps) or not 1 <= self.fps <= 120:
            raise ValueError("Motion frame rate must be 1..120")
        if not math.isfinite(self.start) or self.start < 0:
            raise ValueError("Invalid source start time")
        self.raw = np.asarray(doc["frames"], dtype=np.float64)
        if self.raw.ndim != 4 or self.raw.shape[1:] != (2, 6, 3) or not 2 <= len(self.raw) <= 432000:
            raise ValueError("Expected at least two frames of two dancers, six XY-confidence points each")
        if not np.isfinite(self.raw).all():
            raise ValueError("Motion cache contains non-finite values")
        if np.any(self.raw[..., :2] < -1) or np.any(self.raw[..., :2] > 2):
            raise ValueError("Motion positions exceed normalized video bounds")
        if np.any(self.raw[..., 2] < 0) or np.any(self.raw[..., 2] > 1):
            raise ValueError("Motion confidence must be 0..1")
        self.duration = len(self.raw) / self.fps
        self.end = (len(self.raw) - 1) / self.fps
        self._settings = None

    def prepare(self, smoothing=.08, confidence=.25):
        settings = (round(float(smoothing), 6), round(float(confidence), 6))
        if settings == self._settings:
            return
        if not 0 <= settings[0] <= .5 or not 0 <= settings[1] <= 1:
            raise ValueError("Invalid smoothing / confidence threshold")
        pos = self.raw[..., :2].copy()
        valid = self.raw[..., 2] >= max(.0001, settings[1])
        # Fill position holes only for stable interpolation; their influence is
        # still suppressed by confidence. Never infer movement during dropout.
        indices = np.arange(len(pos))
        for dancer in range(2):
            for joint in range(6):
                mask = valid[:, dancer, joint]
                for axis in range(2):
                    pos[:, dancer, joint, axis] = (np.interp(indices, indices[mask], pos[mask, dancer, joint, axis])
                                                   if mask.any() else .5)
        radius = int(round(settings[0] * self.fps))
        if radius:
            kernel = np.hanning(radius * 2 + 3)[1:-1]
            kernel /= kernel.sum()
            padded = np.pad(pos, ((radius, radius), (0, 0), (0, 0), (0, 0)), mode="edge")
            pos = sum(padded[i:i+len(pos)] * weight for i, weight in enumerate(kernel))
        # TOP coordinates have Y up; flip positions and velocities exactly once.
        pos[..., 1] = 1 - pos[..., 1]
        velocity = np.gradient(pos, 1 / self.fps, axis=0)
        velocity *= np.minimum(1, 2 / np.maximum(1e-8, np.linalg.norm(velocity, axis=-1)))[..., None]
        # No temporal derivative across a missing detection.
        velocity *= (valid & np.roll(valid, 1, axis=0) & np.roll(valid, -1, axis=0))[..., None]
        self.pos, self.velocity = pos, velocity
        self.weights = np.where(valid, self.raw[..., 2], 0)
        self._settings = settings

    def sample(self, seconds, smoothing=.08, confidence=.25, reference=0):
        if not all(math.isfinite(float(v)) for v in (seconds, reference)):
            raise ValueError("Sample times must be finite")
        self.prepare(smoothing, confidence)

        def at(array, t):
            frame = max(0., min(self.end, float(t))) * self.fps
            lo = int(frame)
            hi = min(lo + 1, len(array) - 1)
            return array[lo] * (1 - frame + lo) + array[hi] * (frame - lo)

        pos, vel, weights = at(self.pos, seconds), at(self.velocity, seconds), at(self.weights, seconds)
        rest = at(self.pos, reference)
        return pos, pos-rest, vel, weights


def advance(position, dt, speed, duration, fps, loop=False, playing=True):
    if not all(math.isfinite(float(x)) for x in (position, dt, speed, duration, fps)) or duration <= 0 or fps <= 0:
        raise ValueError("Invalid transport values")
    end = max(0., duration - 1 / fps)
    position = min(duration if loop else end, max(0., position))
    if not playing:
        return position, False
    target = position + max(0., dt) * speed
    if loop:
        return target % duration, True
    return min(end, max(0., target)), bool(0 <= target <= end)


def vectors(clip, seconds, *, smoothing=.08, confidence=.25, reference=0,
            stagezoom=1.7, panx=0., pany=0., mirror=False, posegain=.7,
            velocitygain=.25, body=1., hands=1.2, feet=.5, dancer1=1., dancer2=1.):
    args = (stagezoom, panx, pany, posegain, velocitygain, body, hands, feet, dancer1, dancer2)
    if not all(math.isfinite(float(x)) for x in args):
        raise ValueError("Mapping values must be finite")
    pos, delta, velocity, weights = clip.sample(seconds, smoothing, confidence, reference)
    sign = np.array([-1. if mirror else 1., 1.])
    pos = (pos-.5) * stagezoom * sign + .5 + [panx, pany]
    delta *= stagezoom * sign
    velocity *= stagezoom * sign
    influence = np.array([body, body, hands, hands, feet, feet])[None, :] * np.array([dancer1, dancer2])[:, None]
    weights *= influence
    displacement = (delta * posegain + velocity * velocitygain) * weights[..., None]
    # A single joint cannot tear the whole picture apart after a tracker jump.
    displacement *= np.minimum(1, .28 / np.maximum(1e-8, np.linalg.norm(displacement, axis=-1)))[..., None]
    energy = np.clip(np.mean(np.linalg.norm(velocity, axis=-1) * weights, axis=1) * 3., 0, 1)
    return np.concatenate((pos, displacement), axis=-1).reshape(12, 4), energy
