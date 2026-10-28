"""Audit v5 attachment coverage from its rendered 60fps source-point cache.

Checks opacity around articulated attachments, not artistic seam quality.
Only writes the new v5 audit report; all atlases and native projects are read-only.
"""
import hashlib
import json
from pathlib import Path

import moderngl
import numpy as np

from fluid_puppet import FluidPuppet
from layered_puppet import Atlas
from puppet import camera_transform
from render_layered import LAYER_VERTEX,LAYER_FRAGMENT,pack


def main():
    root=Path(__file__).resolve().parents[2]; folder=root/'build/dance-puppet'
    with np.load(folder/'preview-v5/layered-motion.npz',allow_pickle=False) as cache:
        source=cache['points'].copy(); expected=cache['retargeted_points'].copy()
        fps=float(cache['fps'])
        assert int(cache['schema_version'])==5
    torso=np.linalg.norm(source[:,:,[11,12]].mean(axis=2)-source[:,:,[23,24]].mean(axis=2),axis=2)
    scale=float(np.mean(np.percentile(torso,90,axis=0))/.15)
    ctx=moderngl.create_standalone_context(require=330)
    fb=ctx.simple_framebuffer((1280,720),components=4); fb.use()
    prog=ctx.program(vertex_shader=LAYER_VERTEX,fragment_shader=LAYER_FRAGMENT)
    buf=ctx.buffer(reserve=2_000_000)
    vao=ctx.vertex_array(prog,[(buf,'2f 2f 1f','in_pos','in_uv','in_opacity')])
    ctx.enable(moderngl.BLEND)
    ctx.blend_func=(moderngl.SRC_ALPHA,moderngl.ONE_MINUS_SRC_ALPHA,moderngl.ONE,moderngl.ONE_MINUS_SRC_ALPHA)
    rows=[]; matches=[]
    for slot,name in enumerate(('fan','chain')):
        atlas=Atlas(folder/(name+'-atlas-v3.png'),name)
        tex=ctx.texture(atlas.image.size,4,atlas.image.tobytes())
        tex.filter=moderngl.LINEAR,moderngl.LINEAR; tex.repeat_x=False; tex.repeat_y=False
        rig=FluidPuppet(atlas,source[:,slot],fps,np.ones((len(source),33)),.65,smoothing=.05,scale=scale)
        matches.append(bool(np.allclose(rig.points,expected[slot],atol=1e-6)))
        for seconds in (0,3,6,9,12,15,18,19,21,30,40,50,60):
            frame=round(seconds*fps); points=rig.points[frame]
            center=points[[23,24]].mean(axis=0)+[0,.04]
            data=pack(rig.parts(frame)); data[:,:2]=camera_transform(data[:,:2],1280/720,center,.38)
            fb.clear(0,0,0,0); buf.write(data.tobytes()); tex.use(0)
            vao.render(moderngl.TRIANGLES,vertices=len(data))
            pixels=np.frombuffer(fb.read(components=4,alignment=1),np.uint8).reshape(720,1280,4)
            joints=np.vstack([points[[11,12,13,14,15,16,23,24,25,26,27,28]],points[[11,12]].mean(axis=0)])
            xy=(camera_transform(joints,1280/720,center,.38)*.5+.5)*[1280,720]
            coverage=[]
            for x,y in xy.astype(int):
                region=pixels[max(0,y-2):min(720,y+3),max(0,x-2):min(1280,x+3),3]
                coverage.append(bool(region.size and region.max()>180))
            rows.append(dict(character=name,frame=frame,covered=sum(coverage),count=len(coverage),
                             uncovered_indices=np.flatnonzero(np.logical_not(coverage)).tolist()))
    preserved={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in (
        'TD_ImageFX_Library.toe','build/dance-puppet/DancePuppet25D_Prototype_v3.toe',
        'build/dance-puppet/DancePuppet25D_Prototype_v4.toe')}
    total=sum(r['count'] for r in rows); covered=sum(r['covered'] for r in rows)
    report=dict(kind='imagefx.dance-puppet.v5.audit',frames=len(source),fps=fps,
                cached_rig_matches=matches,covered=covered,sampled=total,samples=rows,
                preserved_files=preserved,ok=covered==total and all(matches),
                limitation='Opaque attachment samples do not certify invisible seams, tracking accuracy or 3D anatomy.')
    (folder/'v5-attachment-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
    if not report['ok']: raise SystemExit(1)


if __name__=='__main__': main()
