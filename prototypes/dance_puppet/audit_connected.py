"""Read-only asset audit and sampled GPU attachment coverage for v4.

Coverage checks alpha at rig attachments, not artistic seam quality or actual
tracking accuracy. No asset, capture, earlier render or TOE is rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path

import moderngl
import numpy as np

from connected_puppet import ConnectedPuppet, clean_motion
from layered_puppet import Atlas, LayeredPuppet
from puppet import Motion, camera_transform
from render_layered import LAYER_VERTEX,LAYER_FRAGMENT,pack


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    a=p.parse_args(); folder=a.root/'build/dance-puppet'
    motion=Motion(folder/'motion-rtm-full.json',0)
    torso=np.linalg.norm(motion.points[:,:,[11,12]].mean(axis=2)-motion.points[:,:,[23,24]].mean(axis=2),axis=2)
    scale=float(np.mean(np.percentile(torso,90,axis=0))/.15)
    ctx=moderngl.create_standalone_context(require=330)
    fb=ctx.simple_framebuffer((1280,720),components=4); fb.use()
    prog=ctx.program(vertex_shader=LAYER_VERTEX,fragment_shader=LAYER_FRAGMENT)
    buf=ctx.buffer(reserve=2_000_000)
    vao=ctx.vertex_array(prog,[(buf,'2f 2f 1f','in_pos','in_uv','in_opacity')])
    ctx.enable(moderngl.BLEND)
    # RGB uses straight alpha, but coverage must use Porter-Duff source-over.
    # Reusing SRC_ALPHA for the alpha channel would square source coverage and
    # incorrectly punch holes when a crossfading card covers an opaque joint.
    ctx.blend_func=(moderngl.SRC_ALPHA,moderngl.ONE_MINUS_SRC_ALPHA,
                   moderngl.ONE,moderngl.ONE_MINUS_SRC_ALPHA)
    result={'kind':'imagefx.dance-puppet.v4.audit','frame_count':motion.n,'fps':motion.fps,
            'sampled_attachments':[],'motion_cleanup':[],'preserved_files':{},'limitations':[
            'Attachment coverage is not a guarantee of invisible line-art seams.',
            'No 3D depth, measured cloth physics or ground-truth tracking certification.']}
    samples=[0,90,180,270,360,450,540,570,630,900,1200,1500,1800]
    for slot,name in enumerate(('fan','chain')):
        atlas=Atlas(folder/(name+'-atlas-v3.png'),name)
        tex=ctx.texture(atlas.image.size,4,atlas.image.tobytes())
        tex.filter=moderngl.LINEAR,moderngl.LINEAR; tex.repeat_x=False; tex.repeat_y=False
        source=motion.points[:,slot]
        cleaned=clean_motion(source,30,.05)
        old=LayeredPuppet(atlas,source,30,motion.valid[:,slot].astype(float))
        new=ConnectedPuppet(atlas,source,30,motion.valid[:,slot].astype(float),.65,smoothing=.05,scale=scale)
        raw_jerk=float(np.mean(np.linalg.norm(np.diff(source,n=3,axis=0),axis=2)))
        clean_jerk=float(np.mean(np.linalg.norm(np.diff(cleaned,n=3,axis=0),axis=2)))
        result['motion_cleanup'].append(dict(character=name,raw_mean_third_difference=raw_jerk,
              cleaned_mean_third_difference=clean_jerk,ratio=clean_jerk/raw_jerk,
              samples_unchanged=len(cleaned)==len(source),no_resampling=True))
        for version,rig in [('v3',old),('v4',new)]:
            for frame in samples:
                points=rig.points[frame]
                center=points[[23,24]].mean(axis=0)+[0,.04]
                data=pack(rig.parts(frame)); data[:,:2]=camera_transform(data[:,:2],1280/720,center,.38)
                fb.clear(0,0,0,0); buf.write(data.tobytes()); tex.use(0)
                vao.render(moderngl.TRIANGLES,vertices=len(data))
                pixels=np.frombuffer(fb.read(components=4,alignment=1),np.uint8).reshape(720,1280,4)
                joints=np.vstack([points[[11,12,13,14,15,16,23,24,25,26,27,28]],points[[11,12]].mean(axis=0)])
                xy=(camera_transform(joints,1280/720,center,.38)*.5+.5)*[1280,720]
                covered=[]
                for x,y in xy.astype(int):
                    region=pixels[max(0,y-2):min(720,y+3),max(0,x-2):min(1280,x+3),3]
                    covered.append(bool(region.size and region.max()>180))
                result['sampled_attachments'].append(dict(character=name,version=version,frame=frame,
                       covered=sum(covered),count=len(covered),uncovered_indices=np.flatnonzero(np.logical_not(covered)).tolist()))
    for version in ('v3','v4'):
        rows=[r for r in result['sampled_attachments'] if r['version']==version]
        result[version+'_attachment_fraction']=sum(r['covered'] for r in rows)/sum(r['count'] for r in rows)
    for relative in ('TD_ImageFX_Library.toe','build/dance-puppet/DancePuppet25D_Prototype_v3.toe'):
        result['preserved_files'][relative]=hashlib.sha256((a.root/relative).read_bytes()).hexdigest()
    result['ok']=(result['v4_attachment_fraction']==1 and all(r['ratio']<1 and r['samples_unchanged'] for r in result['motion_cleanup']))
    (folder/'v4-attachment-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sampled_attachments'},indent=2))
    if not result['ok']: raise SystemExit(1)


if __name__=='__main__': main()
