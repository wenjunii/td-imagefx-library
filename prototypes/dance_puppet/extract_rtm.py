"""Offline RTMPose/YOLOX alternative for interacting dancers (17 observed joints)."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from extract_motion import assign_tracks

# Adapter to the prototype's 33-slot layout, NOT 33 independent observations.
COCO_TO_LAYOUT = [0,1,1,1,2,2,2,3,4,0,0,5,6,7,8,9,10,9,10,9,10,9,10,
                  11,12,13,14,15,16,15,16,15,16]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--start', type=float, default=4)
    p.add_argument('--duration', type=float, default=12)
    p.add_argument('--fps', type=float, default=30)
    p.add_argument('--mode', choices=['balanced','lightweight','performance'], default='balanced')
    p.add_argument('--model-dir', type=Path, help='Use existing local models only; never download')
    p.add_argument('--provider',choices=['cpu','directml','cuda'],default='cpu')
    p.add_argument('--gpu',type=int,default=0)
    a=p.parse_args()
    if a.start<0 or not 0<a.duration<=3600 or not 1<=a.fps<=60:
        p.error('Invalid clip range')
    import cv2
    import rtmlib
    from rtmlib.tools.file import download_checkpoint
    from rtmlib import Body
    model_dir=a.model_dir or a.output.parent/'rtm-models'
    model_dir.mkdir(parents=True,exist_ok=True)
    settings=Body.MODE[a.mode]
    if a.model_dir:
        paths={k:str(model_dir/Path(settings[k]).with_suffix('.onnx').name) for k in ('det','pose')}
        if not all(Path(path).is_file() for path in paths.values()):
            raise ValueError('Required local pose models are missing')
    else:
        paths={k:download_checkpoint(settings[k], dst_dir=model_dir) for k in ('det','pose')}
    from live_tracking import make_body
    model=make_body(paths,settings,a.provider,a.gpu)
    cap=cv2.VideoCapture(str(a.video))
    if not cap.isOpened(): raise RuntimeError('Cannot open video')
    source_fps=cap.get(cv2.CAP_PROP_FPS); width=int(cap.get(3)); height=int(cap.get(4))
    if not math.isfinite(source_fps) or source_fps <= 0 or a.fps > source_fps+1e-6:
        cap.release()
        raise ValueError('The source must have a valid frame rate; requested fps cannot exceed it')
    cap.set(cv2.CAP_PROP_POS_FRAMES,round(a.start*source_fps))
    next_source=round(a.start*source_fps); records=[]; previous=[None,None]
    initialized=False
    try:
        for n in range(round(a.duration*a.fps)):
            wanted=round((a.start+n/a.fps)*source_fps)
            while next_source<wanted: cap.grab(); next_source+=1
            ok,frame=cap.read(); next_source+=1
            if not ok: break
            keypoints,scores=model(frame)
            candidates=[]
            for joints,conf in zip(keypoints,scores):
                if float(conf[5:13].mean())<.3: continue
                points=[[float(joints[i,0]/width),float(joints[i,1]/height),0.,
                         float(conf[i]),float(conf[i])] for i in COCO_TO_LAYOUT]
                center=[(points[23][i]+points[24][i])/2 for i in (0,1)]
                candidates.append(dict(center=center,points=points))
            if not initialized:
                selected=sorted(candidates,key=lambda q:q['center'][0])[:2] if len(candidates)>=2 else [None,None]
                initialized=len(candidates)>=2
            else:
                selected=assign_tracks(candidates,previous)
            records.append(dict(time=round(n/a.fps,6),poses=[q['points'] if q else None for q in selected]))
            for i,q in enumerate(selected):
                if q: previous[i]=q
            if n%30==0: print(f'Frame {n}: {len(candidates)} people, assigned {[q is not None for q in selected]}',flush=True)
    finally: cap.release()
    if not initialized: raise RuntimeError('No valid two-person initialization')
    result=dict(schema_version=1,kind='imagefx.dance-puppet.motion',fps=a.fps,
                source_size=[width,height],source_fps=source_fps,source_start_seconds=a.start,
                source_name=a.video.name,duration=len(records)/a.fps,
                detector='RTMPose + YOLOX / rtmlib '+getattr(rtmlib,'__version__','0.0.16'),
                inference_provider=a.provider,inference_gpu=a.gpu,
                observed_landmark_count=17,landmark_layout='33-slot adapter; hand/foot/face slots repeated; no depth estimate',
                tracking='left-to-right initialization, nearest-hip association; review overlaps manually',
                model_sources={k:settings[k] for k in paths},
                model_sha256={k:hashlib.sha256(Path(path).read_bytes()).hexdigest() for k,path in paths.items()},
                detection_fraction=[sum(r['poses'][i] is not None for r in records)/len(records) for i in (0,1)],frames=records)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,separators=(',',':'),allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='frames'},indent=2))


if __name__=='__main__': main()
