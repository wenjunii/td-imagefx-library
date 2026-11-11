"""Remove 2D source-camera pan/roll/zoom using the static background.

Dancers are excluded from tracking. This is not a root lock: their travel and
relative spacing survive. Low-confidence estimates hold the last camera pose.
No video pixels or original pose caches are modified.
"""
import copy
import json
from pathlib import Path

import cv2
import numpy as np


def transform_pose(pose, reference_to_frame, size):
    if pose is None:
        return None
    result = np.asarray(pose, dtype=float).copy()
    width, height = size
    pixels = result[:, :2] * [width, height]
    inverse = np.linalg.inv(reference_to_frame)
    result[:, :2] = (pixels @ inverse[:2, :2].T + inverse[:2, 2]) / [width, height]
    return result.tolist()


class BackgroundCamera:
    def __init__(self, width=960):
        self.width = width
        self.previous = None
        self.points = self.anchors = None
        self.transform = np.eye(3)
        self.accepted = 0
        self.frames = 0
        self.last_quality = {}

    @staticmethod
    def mask(shape, poses):
        height, width = shape
        mask = np.full(shape, 255, np.uint8)
        # Avoid codec/letterbox boundary corners.
        mask[:8] = mask[-8:] = 0
        mask[:, :8] = mask[:, -8:] = 0
        for pose in poses or []:
            if pose is None:
                continue
            p = np.asarray(pose, float)
            valid = np.isfinite(p).all(axis=1) & (p[:, 3] >= .25)
            if valid.sum() < 3:
                continue
            xy = p[valid, :2] * [width, height]
            # Extra room covers clothes, props and moving shadows near feet.
            lo = np.floor(xy.min(axis=0) - [width*.06, height*.08]).astype(int)
            hi = np.ceil(xy.max(axis=0) + [width*.06, height*.12]).astype(int)
            cv2.rectangle(mask, tuple(np.maximum(lo, 0)), tuple(np.minimum(hi, [width-1,height-1])), 0, -1)
        return mask

    def update(self, frame, poses):
        h, w = frame.shape[:2]
        scale = min(1., self.width/w)
        gray = cv2.cvtColor(cv2.resize(frame, (round(w*scale),round(h*scale))), cv2.COLOR_BGR2GRAY)
        mask = self.mask(gray.shape, poses)
        accepted = self.previous is None
        inliers = 0
        residual = 0.
        if self.previous is not None and self.points is not None and len(self.points) >= 12:
            previous_points = self.points.copy()
            current, ok, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.points, None, winSize=(25,25), maxLevel=3)
            reverse, back_ok, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, current, None, winSize=(25,25), maxLevel=3)
            xy = current.reshape(-1,2)
            locations = np.rint(xy).astype(int)
            inside = (locations[:,0]>=0)&(locations[:,0]<gray.shape[1])&(locations[:,1]>=0)&(locations[:,1]<gray.shape[0])
            valid = ok.ravel().astype(bool) & back_ok.ravel().astype(bool) & inside
            valid &= np.linalg.norm((reverse-self.points).reshape(-1,2),axis=1)<1.
            valid[inside] &= mask[locations[inside,1],locations[inside,0]] > 0
            self.points = current[valid]
            self.anchors = self.anchors[valid]
            previous_points = previous_points[valid]
            if len(self.points)>=12:
                affine, good = cv2.estimateAffinePartial2D(self.anchors,self.points,method=cv2.RANSAC,ransacReprojThreshold=1.8,maxIters=2000,confidence=.995)
                if affine is not None and good is not None:
                    good = good.ravel().astype(bool)
                    inliers = int(good.sum())
                    candidate = np.vstack([affine,[0,0,1]])
                    delta = candidate @ np.linalg.inv(self.transform)
                    zoom = np.linalg.norm(delta[0,:2])
                    angle = abs(np.arctan2(delta[1,0],delta[0,0]))
                    expected = self.anchors.reshape(-1,2) @ affine[:,:2].T + affine[:,2]
                    residual = float(np.median(np.linalg.norm(expected[good]-self.points.reshape(-1,2)[good],axis=1))) if inliers else 999.
                    accepted = inliers>=12 and good.mean()>=.55 and residual<1.2 and .96<zoom<1.04 and angle<.06 and np.linalg.norm(delta[:2,2])<45
                    if accepted:
                        self.transform = candidate
                        self.points = self.points[good]
                        self.anchors = self.anchors[good]
                if not accepted:
                    # A moving camera sees parallax in a real room. Re-anchor
                    # only after a reliable short-baseline background estimate;
                    # never add anchors to an incorrect frozen transform.
                    step, good = cv2.estimateAffinePartial2D(previous_points,self.points,method=cv2.RANSAC,ransacReprojThreshold=1.2)
                    if step is not None and good is not None:
                        good=good.ravel().astype(bool)
                        inliers=int(good.sum())
                        expected=previous_points.reshape(-1,2)@step[:,:2].T+step[:,2]
                        residual=float(np.median(np.linalg.norm(expected[good]-self.points.reshape(-1,2)[good],axis=1))) if inliers else 999.
                        accepted=inliers>=12 and good.mean()>=.65 and residual<.8 and .96<np.linalg.norm(step[0,:2])<1.04 and abs(np.arctan2(step[1,0],step[0,0]))<.06 and np.linalg.norm(step[:,2])<45
                        if accepted:
                            self.transform=np.vstack([step,[0,0,1]])@self.transform
                            self.points=self.points[good]
                            inverse=np.linalg.inv(self.transform)
                            self.anchors=(self.points.reshape(-1,2)@inverse[:2,:2].T+inverse[:2,2]).astype(np.float32).reshape(-1,1,2)
        if accepted and (self.points is None or len(self.points)<200):
            detection_mask = mask.copy()
            if self.points is not None:
                for p in self.points.reshape(-1,2):
                    cv2.circle(detection_mask,tuple(np.rint(p).astype(int)),10,0,-1)
            new = cv2.goodFeaturesToTrack(gray,350 if self.points is None else max(1,350-len(self.points)),.008,10,mask=detection_mask)
            if new is not None:
                inverse = np.linalg.inv(self.transform)
                anchors = (new.reshape(-1,2) @ inverse[:2,:2].T + inverse[:2,2]).astype(np.float32).reshape(-1,1,2)
                self.points = new if self.points is None else np.concatenate([self.points,new])
                self.anchors = anchors if self.anchors is None else np.concatenate([self.anchors,anchors])
        self.previous = gray
        self.frames += 1
        self.accepted += int(accepted)
        self.last_quality = dict(accepted=bool(accepted),inliers=inliers,residual_px=residual)
        full = self.transform.copy()
        full[:2,2] /= scale
        return full


def stabilize_cache(video, motion, output, *, progress=None, cancelled=None):
    data = json.loads(Path(motion).read_text(encoding='utf-8'))
    if data.get('camera_motion',{}).get('removed'):
        # Rebuilding a stabilized cache must not compensate a second time.
        return Path(motion)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError('Select the original dancers video to remove camera motion')
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if list(size) != list(data['source_size']):
        cap.release()
        raise ValueError('Dancer video size does not match the analyzed motion cache')
    result = copy.deepcopy(data)
    tracker = BackgroundCamera()
    transforms = []
    source_start = float(data.get('source_start_seconds',0))
    previous_index = -1
    frame = None
    try:
        for index, record in enumerate(result['frames']):
            if cancelled and cancelled():
                raise InterruptedError('Camera stabilization cancelled')
            target = round((source_start+index/data['fps'])*fps)
            if previous_index<0:
                cap.set(cv2.CAP_PROP_POS_FRAMES,target)
                ok,frame=cap.read()
            else:
                ok = True
                for _ in range(max(0,target-previous_index)):
                    ok,frame=cap.read()
                    if not ok: break
            if not ok or frame is None:
                raise ValueError('Dancer video ended before the motion cache')
            previous_index = target
            transform = tracker.update(frame, record['poses'])
            record['poses'] = [transform_pose(p,transform,size) for p in record['poses']]
            transforms.append(transform.tolist())
            if progress and index%30==0: progress(index/len(result['frames']))
    finally:
        cap.release()
    fraction = tracker.accepted/max(1,tracker.frames)
    if fraction < .7:
        raise ValueError('Not enough static background for reliable camera removal; use a locked-camera recording')
    result['camera_motion'] = dict(removed=True,method='masked-background-similarity',accepted_fraction=fraction,
                                  reference_frame=0,reference_to_frame=transforms)
    Path(output).write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    return Path(output)
