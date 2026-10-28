"""Profile the actual live worker using a local recording, never a camera.

Timing wrappers exist only in this diagnostic process. No TD settings, worker
code, media, model files, or existing reports are modified.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import threading
import time
from unittest.mock import patch


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


class Timings:
    def __init__(self):
        self.samples = []
        self.lock = threading.Lock()

    def record(self, name, start, end):
        with self.lock:
            self.samples.append((name, start, end))

    def wrap(self, name, callback):
        def timed(*args, **kwargs):
            start = time.perf_counter()
            try:
                return callback(*args, **kwargs)
            finally:
                self.record(name, start, time.perf_counter())
        return timed

    def summarize(self, start, end):
        grouped = {}
        for name, before, after in self.samples:
            if before >= start and after <= end:
                grouped.setdefault(name, []).append((after - before) * 1000)
        return {name: dict(calls=len(values), median_ms=statistics.median(values),
                           p95_ms=percentile(values, .95), mean_ms=statistics.mean(values),
                           total_ms=sum(values)) for name, values in sorted(grouped.items())}


def diagnostic_config(config, video, frames, warmup):
    video = Path(video).resolve()
    if not video.is_file():
        raise ValueError('Choose an existing local prerecorded video, not a camera')
    if not 1 <= warmup < frames <= 1800:
        raise ValueError('Require 1 <= warmup < frames <= 1800')
    result = dict(config)
    result.update(diagnostic_replay=str(video), diagnostic_frames=frames, analyze=False)
    if result.get('provider') != 'cuda' or not result.get('render_gpu'):
        raise ValueError('Use explicit CUDA inference and a required RTX render_gpu')
    for name in ('profile', 'models'):
        if not result.get(name) or not Path(result[name]).exists():
            raise ValueError('Missing local ' + name)
    return result


def run(config, video, output, frames=180, warmup=15):
    config = diagnostic_config(config, video, frames, warmup)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    import cv2
    import moderngl
    import service
    import live_tracking
    import camera_motion

    timings = Timings()
    boundaries = []
    frame_info = {}
    last_render = [None]
    native_capture = cv2.VideoCapture
    native_body = live_tracking.make_body
    native_render = service.Renderer.render
    native_status = service.status

    class Capture:
        def __init__(self, source, *args, **kwargs):
            if not isinstance(source, str) or Path(source).resolve() != Path(config['diagnostic_replay']):
                raise ValueError('This diagnostic only permits its explicitly selected local video')
            self.inner = native_capture(source, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def read(self):
            ok, frame = timings.wrap('capture_decode', self.inner.read)()
            if ok:
                frame_info['input_size'] = [int(frame.shape[1]), int(frame.shape[0])]
            return ok, frame

    def body(*args, **kwargs):
        model = native_body(*args, **kwargs)
        model.det_model = timings.wrap('person_detection', model.det_model)
        model.pose_model = timings.wrap('pose_estimation', model.pose_model)
        return model

    def render(*args, **kwargs):
        result = timings.wrap('render_including_readback_per_view', native_render)(*args, **kwargs)
        last_render[0] = time.perf_counter()
        return result

    def status(job, state, **fields):
        now = time.perf_counter()
        if state == 'live':
            boundaries.append(now)
            if last_render[0] is not None:
                timings.record('publish_copy_and_bookkeeping', last_render[0], now)
            frame_info.update(renderer=fields.get('renderer'), provider=fields.get('provider'),
                              gpu=fields.get('gpu'), output_size=fields.get('size'), views=fields.get('views'),
                              last_tracking=fields.get('tracking'))
        return timings.wrap('status_file_write', native_status)(job, state, **fields)

    error = ''
    try:
        with ExitStack() as stack:
            for obj, name, value in (
                (cv2, 'VideoCapture', Capture),
                (live_tracking, 'make_body', body),
                (live_tracking.PoseTracker, '__call__', timings.wrap('tracking_total', live_tracking.PoseTracker.__call__)),
                (camera_motion.BackgroundCamera, 'update', timings.wrap('camera_stabilization', camera_motion.BackgroundCamera.update)),
                (service.LiveScene, 'update', timings.wrap('rig_deformation', service.LiveScene.update)),
                (service.Renderer, 'render', render),
                (moderngl.Framebuffer, 'read', timings.wrap('framebuffer_readback_per_view', moderngl.Framebuffer.read)),
                (service, 'status', status),
            ):
                stack.enter_context(patch.object(obj, name, value))
            service.live(output, config)
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        start = boundaries[warmup - 1] if len(boundaries) >= warmup else 0
        end = boundaries[-1] if boundaries else 0
        elapsed = end - start
        measured = max(0, len(boundaries) - warmup)
        report = dict(ok=not error and measured > 0, error=error,
                      generated_at=datetime.now(timezone.utc).isoformat(),
                      input='local prerecorded replay; no camera opened',
                      frames=len(boundaries), warmup=warmup, measured_frames=measured,
                      steady_updates_per_second=measured / elapsed if measured and elapsed > 0 else None,
                      camera_stabilization=bool(config.get('remove_camera_motion', True)),
                      frame_interval_p95_ms=percentile([(b-a)*1000 for a,b in zip(boundaries[warmup-1:-1],boundaries[warmup:])], .95),
                      stages=timings.summarize(start, end), **frame_info,
                      notes=['Host wall-clock spans, not GPU kernel timings.',
                             'Inference overlaps rig/render work; do not add stage medians.',
                             'Tracking includes detection/pose; rendering includes readback.',
                             'Render/readback spans are per view; each update has three views.',
                             'Readback includes waiting for queued GPU work, not just copying bytes.',
                             'Steady throughput excludes model loading and warmup; not a camera/venue FPS guarantee.'])
        (output / 'profile.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    if not report['ok']:
        raise RuntimeError('Not enough completed frames for a steady-state measurement')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New local report folder; never overwritten')
    parser.add_argument('--frames', type=int, default=180)
    parser.add_argument('--warmup', type=int, default=15)
    args = parser.parse_args()
    report = run(json.loads(args.config.read_text(encoding='utf-8')), args.video, args.output, args.frames, args.warmup)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
