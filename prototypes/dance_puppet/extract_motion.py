"""Offline two-person pose extraction. No media is uploaded or bundled.

Optional dependencies live in a separate environment, not the ImageFX core.
The cache retains detection confidence and missing-data flags for honest QA.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


def assign_tracks(candidates, previous, max_distance=0.25):
    """Two persistent slots, initialized left-to-right; never re-sort each frame."""
    if not any(p is not None for p in previous):
        ordered = sorted(candidates, key=lambda p: p['center'][0])
        return (ordered + [None, None])[:2]
    best, best_cost = [None, None], float('inf')
    for ids in itertools.product(range(-1, len(candidates)), repeat=2):
        if ids[0] >= 0 and ids[0] == ids[1]:
            continue
        cost = 0.0
        for slot, index in enumerate(ids):
            if index < 0:
                cost += max_distance
            elif previous[slot] is None:
                cost += 0.04
            else:
                a, b = previous[slot]['center'], candidates[index]['center']
                distance = math.dist(a, b)
                cost += distance if distance <= max_distance else 100.0
        if cost < best_cost:
            best_cost = cost
            best = [candidates[i] if i >= 0 else None for i in ids]
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--start', type=float, default=4.0)
    parser.add_argument('--duration', type=float, default=12.0)
    parser.add_argument('--fps', type=float, default=30.0)
    parser.add_argument('--roi', nargs=4, type=float, default=[0, 0, 1, 1],
                        metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    args = parser.parse_args()
    if not 0 <= args.start or not 0 < args.duration <= 3600 or not 1 <= args.fps <= 120:
        parser.error('Invalid time/rate bounds')
    x, y, w, h = args.roi
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00001 or y+h > 1.00001:
        parser.error('ROI must be inside normalized image bounds')
    import cv2
    import numpy as np
    import mediapipe as mp
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError('Cannot decode the input video')
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(source_fps) or source_fps <= 0 or args.fps > source_fps+1e-6:
        cap.release()
        raise ValueError('The source must have a valid frame rate; requested fps cannot exceed it')
    width, height = int(cap.get(3)), int(cap.get(4))
    x0, y0 = round(x*width), round(y*height)
    x1, y1 = round((x+w)*width), round((y+h)*height)
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=2, min_pose_detection_confidence=0.35,
        min_pose_presence_confidence=0.35, min_tracking_confidence=0.4,
    )
    previous = [None, None]
    records = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, round(args.start * source_fps))
    next_source = round(args.start * source_fps)
    try:
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as model:
            for n in range(round(args.duration * args.fps)):
                wanted = round((args.start+n/args.fps)*source_fps)
                while next_source < wanted:
                    cap.grab()
                    next_source += 1
                ok, frame = cap.read()
                next_source += 1
                if not ok:
                    break
                crop = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
                img = mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=np.ascontiguousarray(crop))
                result = model.detect_for_video(img, round(n*1000/args.fps))
                candidates = []
                for landmarks in result.pose_landmarks:
                    points = [[(p.x*(x1-x0)+x0)/width,
                               (p.y*(y1-y0)+y0)/height,
                               p.z*(x1-x0)/width,
                               p.visibility, p.presence] for p in landmarks]
                    center = [(points[23][a]+points[24][a])/2 for a in (0, 1)]
                    candidate = dict(center=center, points=points)
                    if not any(math.dist(center, p['center']) < .025 for p in candidates):
                        candidates.append(candidate)
                selected = assign_tracks(candidates, previous)
                records.append(dict(time=round(n/args.fps, 6),
                                    poses=[p['points'] if p else None for p in selected]))
                for i, item in enumerate(selected):
                    if item is not None:
                        previous[i] = item
                if n % 60 == 0:
                    print(f'Frame {n}: {len(candidates)} detections', flush=True)
    finally:
        cap.release()
    if not records or not all(any(r['poses'][i] for r in records) for i in (0, 1)):
        raise RuntimeError('Both dancers must be detected; no usable cache was written')
    report = dict(schema_version=1, kind='imagefx.dance-puppet.motion',
                  fps=args.fps, source_size=[width, height], source_fps=source_fps,
                  source_start_seconds=args.start,
                  source_name=args.video.name,
                  duration=len(records)/args.fps,
                  model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                  detector='MediaPipe Pose Landmarker '+mp.__version__,
                  tracking='nearest previous hip; initialize left to right; manual review required',
                  detection_fraction=[sum(r['poses'][i] is not None for r in records)/len(records)
                                      for i in (0, 1)],
                  frames=records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='frames'}, indent=2))


if __name__ == '__main__':
    main()
