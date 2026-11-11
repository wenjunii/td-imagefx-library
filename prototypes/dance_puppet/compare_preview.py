"""Make a local, synchronized side-by-side reference / puppet review video."""
import argparse
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--render-dir',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    a=parser.parse_args()
    report=json.loads((a.render_dir/'preview-report.json').read_text(encoding='utf-8'))
    fps=float(report['motion']['fps']); count=int(report['rendered_frames'])
    start=float(report['motion']['source_start_seconds'])
    source=cv2.VideoCapture(str(a.source))
    puppet=cv2.VideoCapture(str(a.render_dir/'dance-puppet-source.mp4'))
    if not source.isOpened() or not puppet.isOpened():
        raise RuntimeError('Both source and source-framed puppet render must be readable')
    source_fps=source.get(cv2.CAP_PROP_FPS)
    source_count=int(source.get(cv2.CAP_PROP_FRAME_COUNT))
    if source_fps<=0:
        raise ValueError('Invalid source frame rate')
    output=a.render_dir/'dance-puppet-comparison.mp4'
    command=[str(a.ffmpeg),'-hide_banner','-loglevel','error','-y',
             '-f','rawvideo','-pixel_format','bgr24','-video_size','1920x620',
             '-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264',
             '-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    encoder=subprocess.Popen(command,stdin=subprocess.PIPE)
    samples=[]
    source_frame=-1
    try:
        for frame in range(count):
            # An interpolated final output sample can round beyond the final
            # observed source frame. Hold that last observation, never read EOF.
            wanted=min(source_count-1,round((start+frame/fps)*source_fps))
            if wanted!=source_frame:
                if wanted!=source_frame+1:
                    source.set(cv2.CAP_PROP_POS_FRAMES,wanted)
                ok,left=source.read()
            ok2,right=puppet.read()
            if not ok or not ok2:
                raise RuntimeError(f'Comparison decode failed at frame {frame}')
            source_frame=wanted
            canvas=np.full((620,1920,3),(20,16,12),dtype='u1')
            canvas[45:585,:960]=cv2.resize(left,(960,540))
            canvas[45:585,960:]=cv2.resize(right,(960,540))
            label=f'SOURCE  |  {start+frame/fps:05.2f} s'
            cv2.putText(canvas,label,(20,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(235,235,235),1,cv2.LINE_AA)
            version=report.get('version','v2')
            cv2.putText(canvas,f'2.5D {version}  |  Source timing / character-space retargeting',(980,30),cv2.FONT_HERSHEY_SIMPLEX,.6,(235,235,235),1,cv2.LINE_AA)
            caption=('V5 clean render: refined rotations and view transitions. Live blur / feedback are optional in the TOE. No audio.'
                     if version=='v5' else 'Character proportions preserved, connected robe and joints; retargeted 2D, not full 3D. No audio.'
                     if version=='v4' else 'Layered view cards, independent garments / props; inferred 2D overlap, not full 3D. No audio.'
                     if version=='v3' else 'Experimental front-facing artwork; robes / occlusion still need rig cleanup. No audio.')
            cv2.putText(canvas,caption,(20,609),cv2.FONT_HERSHEY_SIMPLEX,.55,(205,205,205),1,cv2.LINE_AA)
            encoder.stdin.write(canvas.tobytes())
            if frame in (0,count//3,2*count//3,count-1):
                samples.append(cv2.resize(canvas,(1440,465)))
        encoder.stdin.close()
        if encoder.wait()!=0:
            raise RuntimeError('Comparison encoding failed')
    except BaseException:
        encoder.kill(); encoder.wait()
        raise
    finally:
        source.release(); puppet.release()
    cv2.imwrite(str(a.render_dir/'comparison-qa.jpg'),np.vstack(samples))
    print(output)


if __name__=='__main__':
    main()
