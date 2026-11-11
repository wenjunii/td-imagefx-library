"""Render isolated v3/v4/v5 rigs without touching earlier previews or production."""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from layered_puppet import Atlas, LayeredPuppet
from puppet import Motion, camera_transform
from render_preview import VERTEX, BACKGROUND


LAYER_VERTEX = '''#version 330
in vec2 in_pos;
in vec2 in_uv;
in float in_opacity;
out vec2 uv;
out float opacity;
void main() { gl_Position=vec4(in_pos,0.,1.); uv=in_uv; opacity=in_opacity; }
'''
LAYER_FRAGMENT = '''#version 330
uniform sampler2D art;
in vec2 uv;
in float opacity;
out vec4 color;
void main() {
    vec4 a=texture(art,uv);
    a.a=smoothstep(.35,.94,a.a)*opacity;
    if(a.a<.005) discard;
    color=a;
}
'''


def pack(parts):
    result = []
    for part in parts:
        indices = part.faces.ravel()
        opacity=np.broadcast_to(part.opacity,(len(part.xy),))[indices]
        result.append(np.column_stack([part.xy[indices], part.uv[indices],opacity]))
    return np.concatenate(result).astype('f4')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('motion','fan','chain','output-dir','ffmpeg'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--width',type=int,default=1920)
    parser.add_argument('--height',type=int,default=1080)
    parser.add_argument('--smoothing',type=float,default=.035)
    parser.add_argument('--cloth',type=float,default=1.)
    parser.add_argument('--crop-zoom',type=float,default=1.45)
    parser.add_argument('--frames',type=int,default=0)
    parser.add_argument('--stills-only',action='store_true')
    parser.add_argument('--overrides',type=Path,help='Optional JSON: fan/chain lists of start,end,view entries')
    parser.add_argument('--version',choices=['v3','v4','v5'],default='v3')
    parser.add_argument('--neutral',action='store_true',help='V4/V5 proportion review only, not captured choreography')
    parser.add_argument('--output-fps',type=float,default=0,help='V5 only: interpolated output FPS, 0 keeps capture FPS')
    a = parser.parse_args()
    if min(a.width,a.height)<64 or a.width%2 or a.height%2:
        parser.error('Use even dimensions >=64')
    smoothing_max = .3 if a.version in ('v4','v5') else .5
    if not 0<=a.cloth<=2 or not 0<=a.smoothing<=smoothing_max or not 1<=a.crop_zoom<=3:
        parser.error('Invalid cloth, smoothing or crop controls')
    import moderngl
    from PIL import Image, ImageDraw
    a.output_dir.mkdir(parents=True,exist_ok=True)
    previous_report = a.output_dir/'preview-report.json'
    if previous_report.exists() and json.loads(previous_report.read_text(encoding='utf-8')).get('version') != a.version:
        raise RuntimeError('Use a separate output directory; never overwrite another prototype version')
    if a.neutral and a.version not in ('v4','v5'):
        parser.error('Neutral review is a v4/v5-only option')
    if a.output_fps and (a.version!='v5' or not 24<=a.output_fps<=60):
        parser.error('V5 interpolated output FPS must be 24..60')
    motion = Motion(a.motion,0 if a.version in ('v4','v5') else a.smoothing)
    capture_fps, capture_frames=motion.fps,motion.n
    if a.neutral:
        from connected_puppet import neutral_pose
        points = np.stack([neutral_pose()[:,0:33].copy(),neutral_pose().copy()],axis=1)
        points[:,0,:,0] -= .22
        points[:,1,:,0] += .22
        motion.points=points; motion.valid=np.ones((1,2,33),dtype=bool); motion.n=1; motion.duration=1/motion.fps
    elif a.output_fps and a.output_fps!=motion.fps:
        from scipy.interpolate import PchipInterpolator
        original=np.arange(motion.n)/motion.fps
        sample=np.minimum(np.arange(round(motion.duration*a.output_fps))/a.output_fps,original[-1])
        motion.points=PchipInterpolator(original,motion.points,axis=0)(sample)
        motion.valid=motion.valid[np.minimum(np.rint(sample*motion.fps).astype(int),motion.n-1)]
        motion.n=len(sample); motion.fps=a.output_fps
    count = min(a.frames,motion.n) if a.frames>0 else motion.n
    overrides = json.loads(a.overrides.read_text(encoding='utf-8')) if a.overrides else {}
    atlases = [Atlas(a.fan,'fan'), Atlas(a.chain,'chain')]
    if a.version in ('v4','v5'):
        from connected_puppet import ConnectedPuppet
        from fluid_puppet import FluidPuppet
        rig_class=FluidPuppet if a.version=='v5' else ConnectedPuppet
        torso=np.linalg.norm(motion.points[:,:,[11,12]].mean(axis=2)-motion.points[:,:,[23,24]].mean(axis=2),axis=2)
        scale=float(np.mean(np.percentile(torso,90,axis=0))/.15)
        rigs=[rig_class(atlas,motion.points[:,slot],motion.fps,motion.valid[:,slot].astype(float),
                              a.cloth,overrides.get(atlas.name),a.smoothing,scale)
              for slot,atlas in enumerate(atlases)]
    else:
        rigs = [LayeredPuppet(atlas,motion.points[:,slot],motion.fps,
                             motion.valid[:,slot].astype(float), a.cloth, overrides.get(atlas.name))
                for slot,atlas in enumerate(atlases)]
    frames=[]; bounds=[]; minimum_area=1.; finite=True
    for frame in range(count):
        pair=[]
        for rig in rigs:
            parts=rig.parts(frame)
            for part in parts:
                finite = finite and bool(np.isfinite(part.xy).all())
                if part.name.endswith('_robe'):
                    tri=part.xy[part.faces]
                    d1,d2=tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]
                    signed=d1[:,0]*d2[:,1]-d1[:,1]*d2[:,0]
                    # All panels share winding; a sign change is an inversion.
                    minimum_area=min(minimum_area,float(signed.min()))
            packed=pack(parts)
            pair.append(packed)
            bounds.append(packed[:,:2])
        frames.append(pair)
    if not finite or minimum_area<=0:
        raise RuntimeError(f'Invalid geometry: finite={finite}, minimum cloth area={minimum_area}')
    bounds=np.concatenate(bounds)
    lo,hi=bounds.min(axis=0),bounds.max(axis=0)
    center=(lo+hi)*.5; aspect=a.width/a.height
    half_height=max((hi[1]-lo[1])*.5,(hi[0]-lo[0])*.5/aspect)*1.06
    ctx=moderngl.create_standalone_context(require=330)
    print('Renderer:',ctx.info['GL_RENDERER'],flush=True)
    fb=ctx.simple_framebuffer((a.width,a.height),components=3); fb.use()
    bg=ctx.program(vertex_shader=VERTEX,fragment_shader=BACKGROUND)
    bg_buffer=ctx.buffer(np.array([[-1,-1,0,0,0],[1,-1,0,1,0],[-1,1,0,0,1],[1,1,0,1,1]],'f4').tobytes())
    bg_vao=ctx.vertex_array(bg,[(bg_buffer,'3f 2f','in_pos','in_uv')])
    prog=ctx.program(vertex_shader=LAYER_VERTEX,fragment_shader=LAYER_FRAGMENT)
    capacity=max(max(p.nbytes for p in f) for f in frames)
    buffer=ctx.buffer(reserve=capacity)
    vao=ctx.vertex_array(prog,[(buffer,'2f 2f 1f','in_pos','in_uv','in_opacity')])
    textures=[]
    for atlas in atlases:
        t=ctx.texture(atlas.image.size,4,atlas.image.tobytes())
        t.filter=(moderngl.LINEAR,moderngl.LINEAR)
        t.repeat_x=False; t.repeat_y=False
        textures.append(t)
    report=dict(version=a.version,neutral_review=a.neutral,motion=motion.report(),rendered_frames=count,
                capture_fps=capture_fps,capture_frames=capture_frames,interpolated_output=motion.fps!=capture_fps,
                renderer=ctx.info['GL_RENDERER'],size=[a.width,a.height],
                compositions=['full-body','cropped','source'],
                camera_center=center.tolist(),camera_half_height=float(half_height),
                cropped_zoom=a.crop_zoom,smoothing_seconds=a.smoothing,
                rigs=[r.report() for r in rigs],
                geometry=dict(finite=finite,minimum_signed_cloth_triangle_area=minimum_area),
                artwork='AI-assisted separated front/profile/bow/back atlases; not exact reference cutouts',
                limitations=['2D inferred views and overlap order, not reconstructed 3D',
                    'Bounded stylized cloth deformation, not physical collision simulation',
                    'Finger motion and prop rotation not observed; props inherit forearms',
                    'Native component plays cached renders, not live mocap; no audio'])
    times=[0,3,6,9,12,15,18,19,21,30,40,50,60]
    sample_frames={min(count-1,round(t*motion.fps)):t for t in times if t < count/motion.fps}
    for mode in report['compositions']:
        view_center=center+np.array([0,half_height*.18 if mode=='cropped' else 0])
        view_height=half_height
        zoom=a.crop_zoom if mode=='cropped' else 1.
        if mode=='source':
            view_center=np.array([motion.aspect/2,-.5]); view_height=max(.5,motion.aspect/(2*aspect))
        output=a.output_dir/f'dance-puppet-{mode}.mp4'
        encoder=None
        if not a.stills_only:
            encoder=subprocess.Popen([str(a.ffmpeg),'-hide_banner','-loglevel','error','-y',
                '-f','rawvideo','-pixel_format','rgb24','-video_size',f'{a.width}x{a.height}',
                '-framerate',str(motion.fps),'-i','pipe:0','-vf','vflip','-an','-c:v','libx264',
                '-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
        thumbs=[]
        try:
            for frame in range(count):
                if a.stills_only and frame not in sample_frames:
                    continue
                ctx.disable(moderngl.BLEND|moderngl.DEPTH_TEST)
                fb.clear(); bg_vao.render(moderngl.TRIANGLE_STRIP)
                ctx.enable(moderngl.BLEND)
                ctx.blend_func=moderngl.SRC_ALPHA,moderngl.ONE_MINUS_SRC_ALPHA
                # Lower on the stage is in front; stable for this non-crossing clip.
                depth=[float(motion.points[frame,s,[27,28],1].mean()) for s in (0,1)]
                for slot in sorted((0,1),key=lambda s:-depth[s]):
                    data=frames[frame][slot].copy()
                    data[:,:2]=camera_transform(data[:,:2],aspect,view_center,view_height,zoom)
                    buffer.write(data.tobytes()); textures[slot].use(0)
                    vao.render(moderngl.TRIANGLES,vertices=len(data))
                raw=fb.read(components=3,alignment=1)
                if encoder:
                    encoder.stdin.write(raw)
                if frame in sample_frames:
                    im=Image.fromarray(np.frombuffer(raw,'u1').reshape(a.height,a.width,3)[::-1])
                    im.save(a.output_dir/f'{mode}-{frame/motion.fps:05.2f}s.png')
                    thumb=im.resize((640,360)); ImageDraw.Draw(thumb).text((12,12),f'{frame/motion.fps:.2f}s',fill='white')
                    thumbs.append(thumb)
                if frame%180==0:
                    print(f'{mode}: {frame}/{count}',flush=True)
            if encoder:
                encoder.stdin.close()
                if encoder.wait()!=0:
                    raise RuntimeError('FFmpeg failed')
        except BaseException:
            if encoder:
                encoder.kill(); encoder.wait()
            raise
        contact=Image.new('RGB',(640*3,360*((len(thumbs)+2)//3)),(4,15,30))
        for i,im in enumerate(thumbs):
            contact.paste(im,((i%3)*640,(i//3)*360))
        contact.save(a.output_dir/f'{mode}-qa.jpg')
    report['stills_only']=a.stills_only
    np.savez_compressed(a.output_dir/'layered-motion.npz',schema_version=int(a.version[1:]),
                        points=motion.points[:count],retargeted_points=np.stack([r.points[:count] for r in rigs]),views=np.stack([r.views[:count] for r in rigs]),
                        body_views=np.stack([r.body_views[:count] for r in rigs]),
                        head_rolls=np.stack([r.rolls[:count] for r in rigs]),fps=motion.fps)
    (a.output_dir/'preview-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
