"""Render a local pose-QA contact sheet; detections are not an accuracy claim."""
import argparse
import json
from pathlib import Path

EDGES = [(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),
         (23,24),(23,25),(25,27),(24,26),(26,28)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('motion', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    import cv2
    import numpy as np
    data = json.loads(a.motion.read_text(encoding='utf-8'))
    cap = cv2.VideoCapture(str(a.video))
    tiles = []
    indices = np.linspace(0, len(data['frames'])-1, 12).astype(int)
    colors = [(255,220,80),(80,150,255)]
    try:
        for index in indices:
            r = data['frames'][index]
            sec = data['source_start_seconds'] + r['time']
            cap.set(cv2.CAP_PROP_POS_MSEC, sec*1000)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f'Cannot decode QA frame {index}')
            frame = cv2.resize(frame, (640,360))
            for slot, pose in enumerate(r['poses']):
                if pose is None:
                    continue
                xy = [(round(q[0]*640),round(q[1]*360)) for q in pose]
                for x,y in EDGES:
                    if min(pose[x][3],pose[y][3]) >= .3:
                        cv2.line(frame,xy[x],xy[y],colors[slot],2,cv2.LINE_AA)
                for j in sorted(set(sum(([x,y] for x,y in EDGES), []))):
                    if pose[j][3] >= .3:
                        cv2.circle(frame,xy[j],3,colors[slot],-1,cv2.LINE_AA)
                at = ((xy[23][0]+xy[24][0])//2,(xy[23][1]+xy[24][1])//2)
                cv2.putText(frame,str(slot+1),at,cv2.FONT_HERSHEY_SIMPLEX,.7,colors[slot],2)
            cv2.rectangle(frame,(0,0),(640,24),(20,20,20),-1)
            cv2.putText(frame,f'{sec:.2f}s | cyan=track 1, orange=track 2',
                        (8,17),cv2.FONT_HERSHEY_SIMPLEX,.45,(240,240,240),1,cv2.LINE_AA)
            tiles.append(frame)
    finally:
        cap.release()
    sheet = np.vstack([np.hstack(tiles[i:i+3]) for i in range(0,12,3)])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(a.output),sheet):
        raise RuntimeError('Cannot write QA sheet')
    print(a.output)


if __name__ == '__main__':
    main()
