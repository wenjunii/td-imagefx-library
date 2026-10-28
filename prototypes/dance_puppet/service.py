"""Local-only prerecorded preparation / explicit live-camera service.

No network listener, shell commands, credentials or camera auto-start on import.
Jobs write only inside their supplied local job folder. Models are preinstalled.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from integration import RecordedScene, Renderer, LiveScene


def atomic_json(path, value):
    path=Path(path); tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
    for attempt in range(20):
        try:
            os.replace(tmp,path); break
        except PermissionError:
            if attempt==19: raise
            time.sleep(.025)


def status(job, state, **fields):
    atomic_json(job/'status.json',dict(state=state,updated=time.time(),**fields))


def cancelled(job):
    return (job/'cancel').exists()


def build(job, config):
    import cv2
    motion=Path(config.get('motion',''))
    if config.get('analyze'):
        video=Path(config['video'])
        if not video.is_file(): raise ValueError('Choose an existing dancer video')
        cap=cv2.VideoCapture(str(video))
        fps=cap.get(cv2.CAP_PROP_FPS); frames=cap.get(cv2.CAP_PROP_FRAME_COUNT); cap.release()
        if not np.isfinite(fps+frames) or fps<=0 or frames<=0: raise ValueError('Cannot read video duration')
        if frames/fps>600: raise ValueError('Trim dancer videos to ten minutes or less per build')
        motion=job/'motion.json'
        status(job,'analyzing',progress=0)
        args=[sys.executable,str(Path(__file__).with_name('extract_rtm.py')),str(video),'--output',str(motion),
              '--start','0','--duration',str(frames/fps),'--fps',str(min(30,fps)),
              '--model-dir',config['models'],'--provider',config.get('provider','cpu'),'--gpu',str(config.get('gpu',0))]
        with (job/'analysis.log').open('w',encoding='utf-8') as log:
            proc=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while proc.poll() is None:
                if cancelled(job): proc.terminate(); proc.wait(); raise InterruptedError('Build cancelled')
                time.sleep(.1)
            if proc.returncode: raise RuntimeError('Pose analysis failed; see analysis.log')
    if not motion.is_file(): raise ValueError('Choose a motion cache or Analyze & Build a dancer video')
    if config.get('remove_camera_motion',True):
        from camera_motion import stabilize_cache
        status(job,'stabilizing_camera',progress=0)
        motion=stabilize_cache(config.get('video',''),motion,job/'motion-stabilized.json',
            progress=lambda value: status(job,'stabilizing_camera',progress=value),
            cancelled=lambda: cancelled(job))
    status(job,'loading_rig',progress=0)
    scene=RecordedScene(motion,config['profile'],fps=60)
    width,height=config.get('size',[1920,1080])
    if (width,height) not in {(1920,1080),(1280,720)}: raise ValueError('Unsupported preparation size')
    renderer=Renderer(scene.atlases,width,height,config.get('render_gpu',''))
    outputs={name:job/('puppet-'+name+'.mov') for name in ('alpha','fan','chain')}
    encoders=[]; logs=[]
    try:
        for name,output in outputs.items():
            log=(job/('encode-'+name+'.log')).open('w',encoding='utf-8'); logs.append(log)
            command=[config['ffmpeg'],'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgba',
                '-video_size',f'{width}x{height}','-framerate','60','-i','pipe:0','-vf','vflip','-an',
                '-c:v','hap','-format','hap_alpha','-chunks','4',str(output.with_suffix('.partial.mov'))]
            encoders.append(subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        for frame in range(scene.count):
            if cancelled(job): raise InterruptedError('Build cancelled; previous render is unchanged')
            packed=scene.packed(frame)
            for index,encoder in enumerate(encoders):
                center,half=scene.solo_cameras[index-1] if index else (scene.center,scene.half_height)
                raw=renderer.render(packed,center,half,slots=[index-1] if index else None)
                encoder.stdin.write(raw.tobytes())
            if frame%30==0: status(job,'rendering',progress=frame/scene.count,frame=frame,total=scene.count)
        for encoder in encoders: encoder.stdin.close()
        if any(encoder.wait()!=0 for encoder in encoders): raise RuntimeError('Alpha encoding failed; see encode logs')
        for output in outputs.values(): os.replace(output.with_suffix('.partial.mov'),output)
        status(job,'ready',progress=1,render=str(outputs['alpha']),renders={k:str(v) for k,v in outputs.items()},motion=str(motion),duration=scene.duration,
               frames=scene.count,fps=60,size=[width,height],alpha='premultiplied',renderer=renderer.ctx.info['GL_RENDERER'],
               provider=config.get('provider','cpu') if config.get('analyze') else 'cached_motion',gpu=config.get('gpu',0))
    finally:
        for encoder in encoders:
            if encoder.poll() is None: encoder.kill(); encoder.wait()
        for log in logs: log.close()
        renderer.close()


def live(job, config):
    import cv2
    from rtmlib import Body
    from extract_rtm import COCO_TO_LAYOUT
    from extract_motion import assign_tracks
    from live_tracking import PoseTracker, LatestCapture, make_body
    # Use the explicitly configured adapter, never silently fall back to CPU
    # for a live show. CPU remains available for diagnostics/offline machines.
    provider=config.get('provider','cpu')
    settings=Body.MODE['balanced']; models=Path(config['models'])
    paths={k:models/Path(settings[k]).with_suffix('.onnx').name for k in ('det','pose')}
    if not all(p.is_file() for p in paths.values()): raise ValueError('Install local RTMPose/YOLOX model files first')
    model=make_body(paths,settings,provider,int(config.get('gpu',0)))
    camera=int(config.get('camera',0))
    replay=config.get('diagnostic_replay')
    cap=cv2.VideoCapture(str(replay)) if replay else cv2.VideoCapture(camera,cv2.CAP_DSHOW)
    if not cap.isOpened(): cap.release(); raise RuntimeError('Camera could not be opened; check device index / Windows camera permission')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
    latest=LatestCapture(cap) if not replay else None
    tracker=PoseTracker(model,config.get('detect_interval',4))
    from camera_motion import BackgroundCamera, transform_pose
    camera_tracker=BackgroundCamera(width=640) if config.get('remove_camera_motion',True) else None
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='puppet-inference')
    capture_sequence=0
    def next_frame():
        nonlocal capture_sequence
        if latest:
            capture_sequence,result=latest.read(capture_sequence)
            return result
        ok,result=cap.read()
        if not ok: raise RuntimeError('Dancer video frame unavailable')
        return result
    def infer(frame):
        t=time.perf_counter(); poses=tracker(frame)
        transform=np.eye(3)
        if camera_tracker:
            h,w=frame.shape[:2]
            mask_poses=[[[float(points[i,0]/w),float(points[i,1]/h),0.,float(conf[i]),float(conf[i])] for i in COCO_TO_LAYOUT]
                        for points,conf in zip(*poses)]
            transform=camera_tracker.update(frame,mask_poses)
        return poses,time.perf_counter()-t,transform
    width,height=1280,720
    frame_map=np.memmap(job/'frames.rgba',mode='w+',dtype=np.uint8,shape=(2,3,height,width,4)); frame_map[:]=0
    header=np.memmap(job/'header.bin',mode='w+',dtype=np.int64,shape=(4,)); header[:]=0
    scene=None; renderer=None; renderer_name=''; previous=[None,None]; initialized=False; sequence=0
    started=time.perf_counter(); last_heartbeat=time.perf_counter(); timings=[]
    try:
        frame=next_frame(); future=executor.submit(infer,frame)
        while not cancelled(job):
            if replay and sequence>=int(config.get('diagnostic_frames',60)): break
            heartbeat=job/'heartbeat'
            if heartbeat.exists(): last_heartbeat=max(last_heartbeat,time.perf_counter()-max(0,time.time()-heartbeat.stat().st_mtime))
            if not replay and time.perf_counter()-last_heartbeat>15: raise InterruptedError('No TouchDesigner reader heartbeat; camera stopped')
            if scene is None:
                scene=LiveScene(config['profile'],frame.shape[1]/frame.shape[0],float(config.get('smoothing',.08)))
                renderer=Renderer(scene.atlases,width,height,config.get('render_gpu',''))
                renderer_name=renderer.ctx.info['GL_RENDERER']
            (joints,scores),inference_seconds,camera_transform=future.result()
            next_image=next_frame()
            # Inference on the next camera image overlaps rigging/rendering.
            # There is only one queued inference, never an unbounded backlog.
            future=executor.submit(infer,next_image)
            detected=time.perf_counter(); candidates=[]
            h,w=frame.shape[:2]
            for points,conf in zip(joints,scores):
                if float(conf[5:13].mean())<.3: continue
                p=[[float(points[i,0]/w),float(points[i,1]/h),0.,float(conf[i]),float(conf[i])] for i in COCO_TO_LAYOUT]
                p=transform_pose(p,camera_transform,(w,h))
                candidates.append(dict(points=p,center=[(p[23][i]+p[24][i])/2 for i in (0,1)]))
            if not initialized:
                selected=sorted(candidates,key=lambda q:q['center'][0])[:2] if len(candidates)>=2 else [None,None]
                initialized=len(candidates)>=2
            else: selected=assign_tracks(candidates,previous)
            for i,q in enumerate(selected):
                if q: previous[i]=q
            packed,opacity=scene.update([q['points'] if q else None for q in selected],time.perf_counter())
            rigged=time.perf_counter()
            pixels=[renderer.render(packed,scene.center,scene.half_height,opacity)]
            for slot in (0,1):
                # Fixed camera: retain stage-space travel, do not follow hips.
                center=scene.solo_centers[slot]
                pixels.append(renderer.render(packed,center,scene.half_height,opacity,slots=[slot]))
            rendered=time.perf_counter()
            timings.append([inference_seconds*1000,(rigged-detected)*1000,(rendered-rigged)*1000])
            # Double buffer + sequence fence: native readers reject torn frames.
            slot=(sequence+1)%2; header[0]=-(sequence+1)
            frame_map[slot]=pixels; sequence+=1
            header[1:]=[slot,width,height]; header[0]=sequence
            status(job,'live',frames=sequence,tracking=[q is not None for q in selected],
                   inference_ms=inference_seconds*1000,effective_fps=sequence/max(.001,time.perf_counter()-started),
                   size=[width,height],views=3,alpha='premultiplied',provider=provider,gpu=config.get('gpu',0),renderer=renderer_name)
            frame=next_image
    finally:
        if latest: latest.close()
        else: cap.release()
        executor.shutdown(wait=True,cancel_futures=True)
        if renderer is not None: renderer.close()
        del frame_map,header
    median=dict(zip(('inference','rig','render'),np.median(timings[5:] or timings,axis=0).tolist())) if timings else {}
    status(job,'stopped',frames=sequence,effective_fps=sequence/max(.001,time.perf_counter()-started),
           diagnostic=bool(replay),provider=provider,gpu=config.get('gpu',0),median_ms=median,renderer=renderer_name)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['build','live']); parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args(); job=args.job.resolve()
    try:
        config=json.loads((job/'config.json').read_text(encoding='utf-8'))
        (build if args.mode=='build' else live)(job,config)
    except InterruptedError as exc: status(job,'cancelled',message=str(exc))
    except Exception as exc:
        status(job,'error',message=str(exc)); raise


if __name__=='__main__': main()
