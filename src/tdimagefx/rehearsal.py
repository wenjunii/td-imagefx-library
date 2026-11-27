"""Bounded, in-memory rehearsal telemetry. No TouchDesigner or show I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time


MAX_ATTEMPTS = 2000
MAX_RECORDINGS = 128


def _number(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


@dataclass
class Frames:
    frames: int = 0
    timing_samples: int = 0
    elapsed_ms: float = 0.0
    worst_ms: float | None = None
    over_budget: int = 0
    drop_samples: int = 0
    timeline_drops: int = 0
    peak_gpu_mb: float | None = None

    def add(self, ms, drops, gpu_mb, budget):
        self.frames += 1
        if ms is not None:
            self.timing_samples += 1
            self.elapsed_ms += ms
            self.worst_ms = max(self.worst_ms or 0, ms)
            self.over_budget += int(ms > budget)
        if drops is not None:
            self.drop_samples += 1
            self.timeline_drops += int(drops)
        if gpu_mb is not None:
            self.peak_gpu_mb = max(self.peak_gpu_mb or 0, gpu_mb)

    def as_dict(self):
        timed = self.timing_samples
        return dict(sampled_frames=self.frames, timing_samples=timed,
                    mean_ms=round(self.elapsed_ms / timed, 2) if timed else None,
                    worst_ms=round(self.worst_ms, 2) if timed else None,
                    over_budget_frames=self.over_budget if timed else None,
                    drop_samples=self.drop_samples,
                    timeline_drops=self.timeline_drops if self.drop_samples else None,
                    peak_gpu_mb=self.peak_gpu_mb)


@dataclass
class Attempt:
    cue_number: int
    name: str
    kind: str
    track: int
    trigger: str
    requested_s: float
    prewait_s: float
    fade_s: float
    status: str = "waiting"
    started_s: float | None = None
    first_frame_s: float | None = None
    transition_type: str | None = None
    from_cue: int | None = None
    waiting: Frames = field(default_factory=Frames)
    playing: Frames = field(default_factory=Frames)
    transition: Frames = field(default_factory=Frames)

    def as_dict(self):
        def delay(end):
            return round(1000 * max(0, end - self.requested_s), 2) if end is not None else None
        return dict(cue_number=self.cue_number, name=self.name, kind=self.kind, track=self.track,
                    trigger=self.trigger, status=self.status, request_offset_s=round(self.requested_s, 3),
                    configured_prewait_s=self.prewait_s, configured_fade_s=self.fade_s,
                    request_to_start_ms=delay(self.started_s),
                    request_to_first_render_ms=delay(self.first_frame_s),
                    transition_type=self.transition_type, from_cue=self.from_cue,
                    waiting=self.waiting.as_dict(), playing=self.playing.as_dict(),
                    transition=self.transition.as_dict())


class RehearsalLog:
    """Consume read-only cue events and uniquely identified render frames."""

    def __init__(self, target_fps, *, clock=time.monotonic):
        if _number(target_fps) is None or not 1 <= target_fps <= 240:
            raise ValueError("Target FPS must be between 1 and 240")
        self.clock = clock
        self.start_time = clock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.target_fps = target_fps
        self.budget = 1000 / target_fps
        self.total = Frames()
        self.attempts = []
        self.pending = {}
        self.started = {}
        self.last_frame = None
        self.recordings = {}
        self.attempt_limit_reached = False
        self.recording_limit_reached = False
        self.ended = None
        self.end_reason = None

    def elapsed(self):
        return max(0, self.clock() - self.start_time)

    def event(self, event, cue=None, index=None, detail=None):
        if self.ended is not None:
            return None
        if event == "stop_all":
            for row in (*self.pending.values(), *self.started.values()):
                if row.status in ("waiting", "started"):
                    row.status = "stopped"
            self.pending.clear()
            self.started.clear()
            return None
        cue_id = cue["id"]
        if event == "request":
            if len(self.attempts) >= MAX_ATTEMPTS:
                self.attempt_limit_reached = True
                return None
            row = Attempt(index + 1, cue["name"][:160], cue["kind"], cue["track"], detail,
                          self.elapsed(), cue["prewait"], cue["fade"])
            self.pending[cue_id] = row
            self.attempts.append(row)
            return row
        if event == "started":
            row = self.pending.pop(cue_id, None)
            old = self.started.pop(cue_id, None)
            if old is not None and old.status == "started":
                old.status = "replayed"
            if row is not None:
                row.status, row.started_s = "started", self.elapsed()
                self.started[cue_id] = row
            return row
        row = self.pending.get(cue_id) or self.started.get(cue_id)
        if row is not None:
            if event == "error":
                row.status = "error_" + detail
                self.pending.pop(cue_id, None)
            elif event == "stopped":
                row.status = "stopped"
                self.pending.pop(cue_id, None)
                self.started.pop(cue_id, None)
            elif event == "completed":
                row.status = "completed"
        return row

    def sample(self, frame, ms, drops, gpu_mb, playing, transitions, rendered):
        if self.ended is not None or frame == self.last_frame:
            return
        self.last_frame = frame
        values = (*map(_number, (ms, drops, gpu_mb)), self.budget)
        self.total.add(*values)
        for row in self.pending.values():
            row.waiting.add(*values)
        for cue_id in set(playing):
            if (row := self.started.get(cue_id)) is not None:
                row.playing.add(*values)
        for cue_id in set(transitions):
            if (row := self.started.get(cue_id)) is not None:
                row.transition.add(*values)
        for cue_id in rendered:
            row = self.started.get(cue_id)
            if row is not None and row.first_frame_s is None:
                row.first_frame_s = self.elapsed()

    def recording(self, job_id, source, fps, written, dropped, *, preexisting=False, outcome=None):
        if self.ended is not None or source not in {"wall", "review"}:
            return
        if job_id not in self.recordings:
            if len(self.recordings) >= MAX_RECORDINGS:
                self.recording_limit_reached = True
                return
            self.recordings[job_id] = dict(source=source, fps=fps, preexisting=preexisting,
                baseline_written=written if preexisting else 0, baseline_dropped=dropped if preexisting else 0,
                written=0, dropped=0, outcome="in_progress")
        row = self.recordings[job_id]
        row["written"] = max(row["written"], written - row["baseline_written"])
        row["dropped"] = max(row["dropped"], dropped - row["baseline_dropped"])
        if outcome is not None:
            row["outcome"] = outcome

    def freeze(self, reason):
        if self.ended is None:
            self.ended, self.end_reason = self.elapsed(), reason

    def report(self):
        attempts = [row.as_dict() for row in self.attempts]
        recordings = [{key: value for key, value in row.items() if not key.startswith("baseline_")}
                      for row in self.recordings.values()]
        return dict(kind="tdimagefx.rehearsal_log", schema_version=1, started_at=self.started_at,
                    duration_s=round(self.ended if self.ended is not None else self.elapsed(), 3),
                    end_reason=self.end_reason, target_fps=self.target_fps,
                    frame_budget_ms=round(self.budget, 3), playback=self.total.as_dict(),
                    limit_reached=self.attempt_limit_reached or self.recording_limit_reached,
                    cue_attempts=attempts, recordings=recordings)
