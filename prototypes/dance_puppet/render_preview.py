"""Render framing options from the same offline mesh-puppet animation.

Private artwork, model weights, footage and resulting videos stay under build/.
The reference footage's audio is deliberately not included in this visual test.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from puppet import Motion, Puppet, camera_transform, head_rolls


VERTEX = '''#version 330
in vec3 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() { gl_Position = vec4(in_pos, 1.0); uv = in_uv; }
'''
FRAGMENT = '''#version 330
uniform sampler2D art;
in vec2 uv;
out vec4 color;
void main() {
    vec4 a = texture(art, uv);
    // The generated art contains a translucent outer glow. The runtime matte
    // suppresses that glow while leaving the original PNG unmodified.
    a.a = smoothstep(0.72, 0.985, a.a);
    if (a.a < 0.02) discard;
    color = a;
}
'''
BACKGROUND = '''#version 330
in vec2 uv;
out vec4 color;
float hash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
void main() {
    float grain = hash(gl_FragCoord.xy) - .5;
    float fiber = sin(gl_FragCoord.x*.51+sin(gl_FragCoord.y*.29))*0.5;
    float edge = smoothstep(.30,.73,length((uv-.5)*vec2(1.1,1.)));
    vec3 blue = mix(vec3(.035,.099,.164),vec3(.017,.048,.090),edge*.7);
    color = vec4(blue + grain*.016 + fiber*.003,1.);
}
'''


def generate_animation(motion, puppets, strength=1., travel=.45, spacing=.68):
    animation = []
    for frame in range(motion.n):
        angles, roots = motion.sample(frame/motion.fps,loop=False)
        pair = []
        for slot, puppet in enumerate(puppets):
            # Preserve each character's drawn proportions; use the performer's
            # rotation, not fluctuating apparent image-space limb lengths.
            scale = puppet.lengths[0]/motion.body_scale[slot]
            offset = (roots[slot]-motion.roots[0,slot])*scale*travel
            xy, _ = puppet.deform(angles[slot],offset,strength)
            xy *= 1.7
            xy += [(-spacing if slot == 0 else spacing),-.05]
            pair.append(xy.astype('f4'))
        animation.append(pair)
    return np.asarray(animation,dtype='f4')


def generate_tracked_animation(motion,puppets):
    scales = [p.tracked_scale(motion.points[:,s]) for s,p in enumerate(puppets)]
    rolls = [head_rolls(motion.points[:,s]) for s in (0,1)]
    animation=[]; residuals=[]
    for frame in range(motion.n):
        pair=[]
        for slot,puppet in enumerate(puppets):
            xy,target = puppet.deform_tracked(motion.points[frame,slot],scales[slot],rolls[slot][frame])
            xy = xy.astype('f4')
            expected = np.array([target[k] for k in puppet.joint_names])
            residuals.extend(np.linalg.norm(xy[puppet.joint_indices]-expected,axis=1).tolist())
            pair.append(xy)
        animation.append(pair)
    error_pixels = np.asarray(residuals)*motion.data['source_size'][1]
    report = dict(thickness_scales=scales,maximum_mesh_anchor_error_pixels=float(error_pixels.max()),
        mean_mesh_anchor_error_pixels=float(error_pixels.mean()),
        note='Solver fit to tracked/interpolated joints, NOT an estimate of tracker accuracy or artistic quality.')
    return np.asarray(animation,dtype='f4'),report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--motion', type=Path, required=True)
    parser.add_argument('--fan', type=Path, required=True)
    parser.add_argument('--chain', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--retarget',choices=('tracked','angles'),default='tracked',
                        help='Tracked = shared source placement and joint fitting; angles = legacy v1')
    parser.add_argument('--strength', type=float, default=.85)
    parser.add_argument('--travel', type=float, default=.45)
    parser.add_argument('--smoothing', type=float, default=.035)
    parser.add_argument('--crop-zoom', type=float, default=1.45)
    parser.add_argument('--frames', type=int, default=0,
                        help='Optional render limit for a quick smoke test')
    a = parser.parse_args()
    if min(a.width,a.height)<64 or a.width%2 or a.height%2 or not 1<=a.crop_zoom<=3:
        parser.error('Use positive even dimensions >=64, crop zoom 1..3')
    if not 0 <= a.strength <= 1.5 or not 0 <= a.travel <= 2 or not 0 <= a.smoothing <= .5:
        parser.error('Invalid motion controls')
    import cv2
    import moderngl
    from PIL import Image
    a.output_dir.mkdir(parents=True,exist_ok=True)
    motion = Motion(a.motion,a.smoothing)
    puppets = [Puppet('fan',match_joints=a.retarget=='tracked'),
               Puppet('chain',match_joints=a.retarget=='tracked')]
    if a.retarget=='tracked':
        animation,fit_report = generate_tracked_animation(motion,puppets)
    else:
        animation = generate_animation(motion,puppets,a.strength,a.travel)
        fit_report = None
    images = [Image.open(p).convert('RGBA') for p in (a.fan,a.chain)]
    if any(im.size != (1024,1536) for im in images):
        raise ValueError('These manual rigs require 1024x1536 calibrated sprites')
    # Fit both full bodies throughout this exact clip, ignoring transparent mesh.
    bounds = []
    for slot,(im,puppet) in enumerate(zip(images,puppets)):
        pixels = np.asarray(im)
        indices = np.clip((puppet.uv*[1023,1535]).astype(int),[0,0],[1023,1535])
        visible = pixels[indices[:,1],indices[:,0],3] > 230
        bounds.append(animation[:,slot,visible].reshape(-1,2))
    all_points = np.concatenate(bounds)
    minimum,maximum = all_points.min(axis=0),all_points.max(axis=0)
    center = (minimum+maximum)/2
    aspect = a.width/a.height
    half_height = max((maximum[1]-minimum[1])/2,
                      (maximum[0]-minimum[0])/2/aspect)*1.09
    ctx = moderngl.create_standalone_context(require=330)
    print('Renderer:',ctx.info['GL_RENDERER'],flush=True)
    fb = ctx.simple_framebuffer((a.width,a.height),components=3)
    fb.use()
    program = ctx.program(vertex_shader=VERTEX,fragment_shader=FRAGMENT)
    bg = ctx.program(vertex_shader=VERTEX,fragment_shader=BACKGROUND)
    bg_buffer = ctx.buffer(np.array([[-1,-1,.99,0,0],[1,-1,.99,1,0],
        [-1,1,.99,0,1],[1,1,.99,1,1]],dtype='f4').tobytes())
    bg_vao = ctx.vertex_array(bg,[(bg_buffer,'3f 2f','in_pos','in_uv')])
    buffers=[]; vaos=[]; textures=[]
    # Artist-chosen shallow layer offsets: not monocular depth reconstruction.
    bone_depth = np.array([0,.08,.04,.05,.06,-.03,-.02,-.01,-.03,-.02,-.01,.02,.03,.04])
    for puppet,im in zip(puppets,images):
        buffer = ctx.buffer(reserve=len(puppet.vertices)*5*4)
        index_buffer = ctx.buffer(puppet.faces.tobytes())
        vaos.append(ctx.vertex_array(program,[(buffer,'3f 2f','in_pos','in_uv')],index_buffer))
        buffers.append(buffer)
        texture = ctx.texture(im.size,4,im.tobytes())
        texture.build_mipmaps(); texture.filter=(moderngl.LINEAR_MIPMAP_LINEAR,moderngl.LINEAR)
        textures.append(texture)
    count = min(a.frames,motion.n) if a.frames>0 else motion.n
    report = dict(motion=motion.report(),artwork='AI-assisted rigging reinterpretation of supplied references',
                  renderer=ctx.info['GL_RENDERER'],size=[a.width,a.height],
                  retarget=a.retarget,joint_fit=fit_report,
                  motion_strength=1 if a.retarget=='tracked' else a.strength,
                  root_travel=1 if a.retarget=='tracked' else a.travel,smoothing_seconds=a.smoothing,
                  camera_center=center.tolist(),camera_half_height=float(half_height),
                  cropped_zoom=a.crop_zoom,rendered_frames=count,
                  limitations=['Front-facing cards, no real turn-around',
                    'Robes and chains are part of the mesh, not independently simulated',
                    'Manual layer order; no inferred depth',
                    'No runtime pose inference or audio in the preview'])
    modes = ('full-body','cropped','source') if a.retarget=='tracked' else ('full-body','cropped')
    report['compositions'] = list(modes)
    for mode in modes:
        output = a.output_dir/f'dance-puppet-{mode}.mp4'
        zoom = a.crop_zoom if mode=='cropped' else 1.
        view_center = center+np.array([0,half_height*.18 if mode=='cropped' else 0])
        view_half_height = half_height
        if mode=='source':
            view_center = np.array([motion.aspect/2,-.5])
            view_half_height = max(.5,motion.aspect/(2*aspect))
        cmd = [str(a.ffmpeg),'-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pixel_format','rgb24','-video_size',f'{a.width}x{a.height}',
            '-framerate',str(motion.fps),'-i','pipe:0','-vf','vflip',
            '-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',
            '-movflags','+faststart',str(output)]
        proc = subprocess.Popen(cmd,stdin=subprocess.PIPE)
        samples=[]
        try:
            for frame in range(count):
                ctx.disable(moderngl.BLEND|moderngl.DEPTH_TEST)
                fb.clear(0,0,0,1)
                bg_vao.render(moderngl.TRIANGLE_STRIP)
                ctx.enable(moderngl.BLEND|moderngl.DEPTH_TEST)
                ctx.blend_func = moderngl.SRC_ALPHA,moderngl.ONE_MINUS_SRC_ALPHA
                for slot,puppet in enumerate(puppets):
                    clip = camera_transform(animation[frame,slot],aspect,view_center,view_half_height,zoom)
                    z = -(puppet.weights@bone_depth)-slot*.12
                    vertices = np.column_stack([clip,z,puppet.uv]).astype('f4')
                    buffers[slot].write(vertices.tobytes())
                    textures[slot].use(0)
                    vaos[slot].render(moderngl.TRIANGLES)
                rendered = fb.read(components=3,alignment=1)
                proc.stdin.write(rendered)
                if frame in {0,count//3,2*count//3,count-1}:
                    pixels = np.frombuffer(rendered,dtype='u1').reshape(a.height,a.width,3)[::-1]
                    samples.append(cv2.cvtColor(pixels,cv2.COLOR_RGB2BGR))
                if frame%90==0:
                    print(f'{mode}: {frame}/{count}',flush=True)
            proc.stdin.close()
            if proc.wait()!=0:
                raise RuntimeError('FFmpeg encoding failed')
        except BaseException:
            proc.kill(); proc.wait()
            raise
        if samples:
            thumbs = [cv2.resize(s,(640,360)) for s in samples]
            cv2.imwrite(str(a.output_dir/f'{mode}-qa.jpg'),np.hstack(thumbs))
        print(output,flush=True)
    # Store geometry for reproducible inspection / a later native rig adapter.
    np.savez_compressed(a.output_dir/'puppet-animation.npz',schema_version=2,positions=animation,
        uv_fan=puppets[0].uv,triangles_fan=puppets[0].faces,
        uv_chain=puppets[1].uv,triangles_chain=puppets[1].faces,fps=motion.fps)
    (a.output_dir/'preview-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
