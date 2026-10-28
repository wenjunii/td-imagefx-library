"""Local CUDA pose-to-force analysis / explicit camera worker; no puppet renderer."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'prototypes/dance_puppet'))
sys.path.insert(0, str(ROOT / 'touchdesigner/scripts'))


def write(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    for _ in range(20):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            time.sleep(.025)
    raise RuntimeError('Local status file is busy')


class Tracking:
    def __init__(self, config):
        import numpy as np
        from rtmlib import Body
        from live_tracking import make_body, PoseTracker
        from camera_motion import BackgroundCamera
        settings = Body.MODE['balanced']
        paths = {k: Path(config['models']) / Path(settings[k]).with_suffix('.onnx').name for k in ('det', 'pose')}
        if not all(p.is_file() for p in paths.values()):
            raise ValueError('Required local YOLOX / RTMPose models are missing')
        self.model = make_body(paths, settings, 'cuda', int(config.get('gpu', 0)))
        self.tracker = PoseTracker(self.model, interval=4)
        self.camera = BackgroundCamera(width=640)
        self.base = np.eye(3)
        self.previous = [None, None]
        self.missed = [0, 0]
        self.failures = 0
        self.good = self.count = 0
        self.coverage = [0, 0]

    def step(self, frame):
        import numpy as np
        from camera_motion import transform_pose, BackgroundCamera
        from extract_motion import assign_tracks
        from extract_rtm import COCO_TO_LAYOUT
        from dance_forces_math import observations
        h, w = frame.shape[:2]
        joints, scores = self.tracker(frame)
        candidates = []
        for xy, confidence in zip(joints, scores):
            if float(confidence[5:13].mean()) < .3:
                continue
            p = [[float(xy[i, 0]/w), float(xy[i, 1]/h), 0., float(np.clip(confidence[i], 0, 1))] for i in COCO_TO_LAYOUT]
            center = [(p[23][a]+p[24][a])/2 for a in (0, 1)]
            visible = xy[confidence > .3] / [w, h]
            area = float(np.prod(np.maximum(.01, visible.max(axis=0)-visible.min(axis=0))))
            # Prefer the main central, full-size dancers over edge spectators.
            score = area / (1 + 4*abs(center[0]-.5))
            if not any(math.dist(center, q['center']) < .025 for q in candidates):
                candidates.append(dict(points=p, center=center, rank=score))
        if not any(self.previous):
            candidates.sort(key=lambda q: q['rank'], reverse=True)
            selected = sorted(candidates[:2], key=lambda q: q['center'][0])
            selected = (selected+[None, None])[:2]
        else:
            selected = assign_tracks(candidates, self.previous, max_distance=.18)
        for i, item in enumerate(selected):
            self.missed[i] = 0 if item else self.missed[i]+1
            if item:
                self.previous[i] = item
                self.coverage[i] += 1
            elif self.missed[i] > 60:
                self.previous[i] = None
        transform = self.camera.update(frame, [q['points'] for q in candidates]) @ self.base
        good = self.camera.last_quality.get('accepted', False)
        self.good += int(good); self.count += 1
        self.failures = 0 if good else self.failures+1
        poses = [transform_pose(q['points'], transform, (w, h)) if q else None for q in selected]
        points = observations(poses, quality=good and self.count > 1)
        if self.failures >= 6:
            # Re-anchor after a cut/occlusion. The invalid interval gates the
            # derivative, so a recovered transform cannot kick the pattern.
            self.base = transform
            self.camera = BackgroundCamera(width=640)
            self.failures = 0
        return points, good


def run(job, mode):
    import cv2
    from dance_forces_math import KIND, Clip
    from live_tracking import LatestCapture
    cv2.setNumThreads(2)
    cfg = json.loads((job/'config.json').read_text(encoding='utf-8'))
    def status(state, **kw):
        write(job/'status.json', dict(state=state, updated=time.time(), **kw))
    status('loading', message='Loading local CUDA detector and pose models')
    tracking = Tracking(cfg)
    live = mode == 'live'
    capture = cv2.VideoCapture(int(cfg.get('camera', 0)), cv2.CAP_DSHOW) if live else cv2.VideoCapture(cfg['video'])
    if not capture.isOpened():
        raise ValueError('Cannot open selected camera' if live else 'Cannot decode the selected video')
    if live:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    fps = min(float(cfg.get('fps', 24)), source_fps) if not live else 30
    if not math.isfinite(fps) or fps < 1:
        capture.release(); raise ValueError('Invalid source frame rate')
    width, height = int(capture.get(3)), int(capture.get(4))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if not live else 0
    if not live and (total < 2 or total/source_fps > 3600):
        capture.release(); raise ValueError('Choose a video between two frames and one hour')
    latest = LatestCapture(capture) if live else None
    sequence = 0; records = []; next_source = 0; n = 0
    start = time.monotonic()
    try:
        while True:
            if (job/'cancel').exists():
                status('cancelled', message='Stopped; previous cache retained'); return
            if live and (not (job/'heartbeat').exists() or time.time()-(job/'heartbeat').stat().st_mtime > 15):
                status('stopped', message='Camera owner disconnected'); return
            if live:
                sequence, frame = latest.read(sequence)
                timestamp = time.time()
            else:
                target = round(n * source_fps/fps)
                while next_source < target:
                    capture.grab(); next_source += 1
                ok, frame = capture.read(); next_source += 1
                if not ok: break
            points, accepted = tracking.step(frame)
            if live:
                write(job/'live.json', dict(points=points.tolist(), updated=timestamp, sequence=sequence,
                                           camera_ok=accepted, provider='CUDAExecutionProvider'))
            else:
                records.append(points.tolist())
            n += 1
            if n % 24 == 1:
                status('live' if live else 'analyzing', progress=min(1., next_source/max(1, total)),
                       frames=n, message=f'{n} frames; camera {tracking.good/max(1,n):.0%}; CUDA GPU {cfg.get("gpu",0)}')
        if len(records) < 2:
            raise ValueError('No usable video frames')
        fraction = tracking.good/max(1, n)
        if fraction < .5 or min(tracking.coverage)/n < .2:
            raise ValueError('Insufficient background / dancer coverage; use a wider, steady-camera video')
        doc = dict(kind=KIND, schema_version=1, fps=fps, frames=records, source_size=[width, height],
                   source_name=Path(cfg['video']).name, provider='CUDAExecutionProvider', gpu=cfg.get('gpu',0),
                   duration=n/fps, detection_fraction=[v/n for v in tracking.coverage],
                   camera_motion=dict(removed=True, method='masked-background-similarity; failed frames gated', accepted_fraction=fraction),
                   analysis_seconds=time.monotonic()-start)
        Clip(doc)
        output = job/'motion.json'; write(output, doc)
        status('ready', motion=str(output), duration=n/fps, frames=n,
               camera_fraction=fraction, detection_fraction=doc['detection_fraction'],
               message=f'Ready: {n/fps:.1f}s, camera {fraction:.0%}, CUDA')
    finally:
        if latest: latest.close()
        else: capture.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('analyze', 'live'))
    parser.add_argument('--job', required=True, type=Path)
    args = parser.parse_args(); job = args.job.resolve()
    try:
        run(job, args.mode)
    except Exception as exc:
        write(job/'status.json', dict(state='error', updated=time.time(), message=str(exc)))
        raise


if __name__ == '__main__':
    main()
