"""Verify real CUDA kernels and OpenGL GPU using a local prerecorded video.

No camera, downloads, network listener or changes to cue media/settings.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New local report folder')
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--frames',type=int,default=12)
    parser.add_argument('--gpu',type=int,default=0)
    parser.add_argument('--renderer',default='RTX 3080 Ti')
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output folder already exists')
    if not 3<=args.frames<=600 or not 0<=args.start<=3600: parser.error('Invalid diagnostic range')
    import cv2
    import moderngl
    from rtmlib import Body
    from live_tracking import make_body
    config=Body.MODE['balanced']
    models={k:args.models/Path(config[k]).with_suffix('.onnx').name for k in ('det','pose')}
    if not args.video.is_file() or not all(p.is_file() for p in models.values()):
        parser.error('Video or local models are missing')
    args.output.mkdir(parents=True)
    context=moderngl.create_standalone_context(require=330)
    try: renderer=context.info['GL_RENDERER']
    finally: context.release()
    if args.renderer.casefold() not in renderer.casefold():
        raise RuntimeError(f'Wrong OpenGL device: {renderer}; expected {args.renderer}')
    body=make_body(models,config,'cuda',args.gpu,profile_prefix=args.output/'ort')
    cap=cv2.VideoCapture(str(args.video)); timings=[]; people=[]
    try:
        if not cap.isOpened(): raise RuntimeError('Cannot read the selected video')
        cap.set(cv2.CAP_PROP_POS_MSEC,args.start*1000)
        for _ in range(args.frames):
            ok,frame=cap.read()
            if not ok: raise RuntimeError('Video ended before the diagnostic finished')
            started=time.perf_counter(); points,_=body(frame)
            timings.append(time.perf_counter()-started); people.append(len(points))
    finally: cap.release()
    profiles={}
    for name,model in [('detector',body.det_model),('pose',body.pose_model)]:
        session=model.session
        events=json.loads(Path(session.end_profiling()).read_text(encoding='utf-8'))
        counts=Counter(e.get('args',{}).get('provider') for e in events if e.get('args',{}).get('provider'))
        if not counts['CUDAExecutionProvider']: raise RuntimeError(f'{name} executed no CUDA kernels')
        profiles[name]={'providers':session.get_providers(),'kernel_events':dict(counts)}
    report={'ok':True,'renderer':renderer,'profiles':profiles,'gpu':args.gpu,
            'frames':len(timings),'people_per_frame':people,
            'mean_warm_inference_ms':sum(timings[2:])/len(timings[2:])*1000}
    (args.output/'gpu-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
