"""Reusable RGBA renderer for baked show media and live pose frames.

Artwork is read-only. Monochrome styling is applied in TouchDesigner, not baked
into the atlas. Rendered frames are premultiplied RGBA, including opaque bodies.
"""
import copy
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from connected_puppet import PROPORTIONS, Proportions
from fluid_puppet import FluidPuppet
from layered_puppet import Atlas, Sprite
from puppet import Motion, camera_transform
from render_layered import LAYER_VERTEX, pack


FRAGMENT = '''#version 330
uniform sampler2D art;
in vec2 uv;
in float opacity;
out vec4 color;
void main(){
    vec4 a=texture(art,uv);
    a.a=smoothstep(.35,.94,a.a)*opacity;
    if(a.a<.005) discard;
    color=vec4(a.rgb*a.a,a.a);
}
'''


def load_profile(path):
    path = Path(path).resolve()
    if path.stat().st_size > 256_000:
        raise ValueError('Character profile is too large')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('kind') != 'imagefx.puppet.profile' or data.get('version') != 1:
        raise ValueError('Unsupported puppet profile')
    entries = data.get('characters')
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError('Profile needs exactly two calibrated characters')
    atlases = []
    for entry in entries:
        if set(entry) - {'rig', 'atlas', 'name', 'proportions', 'sprites'}:
            raise ValueError('Unknown character profile field')
        rig = entry.get('rig')
        if rig not in PROPORTIONS:
            raise ValueError('Supported rig templates: fan, chain')
        atlas_path = Path(entry['atlas'])
        if not atlas_path.is_absolute(): atlas_path = path.parent / atlas_path
        # A new character must supply a calibrated sheet, not a flat painting.
        atlas = Atlas(atlas_path, rig)
        atlas.profile_proportions = PROPORTIONS[rig]
        values = entry.get('proportions', {})
        if set(values) - set(vars(PROPORTIONS[rig])):
            raise ValueError('Unknown proportion')
        if any(isinstance(v, bool) or not isinstance(v, (int,float)) or
               not np.isfinite(v) or not .005 <= v <= .5 for v in values.values()):
            raise ValueError('Proportions must be finite, .005 .. .5')
        atlas.profile_proportions = Proportions(**(vars(PROPORTIONS[rig]) | values))
        for name, rect in entry.get('sprites', {}).items():
            a = np.asarray(rect, float)
            if name not in atlas.sprites or a.shape != (4,) or not np.isfinite(a).all() or np.any(a<0) or np.any(a>1) or np.any(a[2:]<=a[:2]):
                raise ValueError('Invalid sprite calibration: '+name)
            atlas.sprites[name] = Sprite(name, a, (a[2]-a[0])/(a[3]-a[1]))
        atlases.append(atlas)
    return atlases


def with_proportions(atlas, action):
    """The legacy rig uses a module table; scope overrides to one synchronous call."""
    old = PROPORTIONS[atlas.name]
    try:
        PROPORTIONS[atlas.name] = atlas.profile_proportions
        return action()
    finally:
        PROPORTIONS[atlas.name] = old


class RecordedScene:
    def __init__(self, motion, profile, fps=60, smoothing=.035, cloth=1.):
        self.motion = Motion(motion, 0)
        self.atlases = load_profile(profile)
        m = self.motion
        self.fps, self.duration = fps, m.duration
        self.count = max(1, round(m.duration*fps))
        sample = np.minimum(np.arange(self.count)/fps, (m.n-1)/m.fps)
        if m.n > 1:
            self.points = PchipInterpolator(np.arange(m.n)/m.fps, m.points, axis=0)(sample)
        else:
            self.points = np.repeat(m.points, self.count, axis=0)
        valid = m.valid[np.minimum(np.rint(sample*m.fps).astype(int), m.n-1)]
        torso = np.linalg.norm(self.points[:,:,[11,12]].mean(axis=2)-self.points[:,:,[23,24]].mean(axis=2),axis=2)
        scale = float(np.mean(np.percentile(torso,90,axis=0))/.15)
        self.rigs = [with_proportions(a, lambda a=a,s=s: FluidPuppet(a,self.points[:,s],fps,valid[:,s].astype(float),cloth,None,smoothing,scale)) for s,a in enumerate(self.atlases)]
        # Stable camera over the whole choreography, not auto-zoom on each frame.
        bounds = np.concatenate([r.points.reshape(-1,2) for r in self.rigs])
        lo,hi = bounds.min(axis=0),bounds.max(axis=0)
        margin = .18*scale
        self.center = (lo+hi)*.5 + [0, margin*.15]
        self.half_height = max((hi[1]-lo[1])*.5+margin,(hi[0]-lo[0])*.5/(16/9)+margin)
        self.solo_cameras=[]
        for rig in self.rigs:
            bounds=rig.points.reshape(-1,2); lo,hi=bounds.min(axis=0),bounds.max(axis=0)
            self.solo_cameras.append(((lo+hi)*.5+[0,margin*.15],
                max((hi[1]-lo[1])*.5+margin,(hi[0]-lo[0])*.5/(16/9)+margin)))

    def packed(self, frame):
        return [with_proportions(a,lambda r=r: pack(r.parts(frame))) for a,r in zip(self.atlases,self.rigs)]


class Renderer:
    def __init__(self, atlases, width, height, required_renderer=''):
        import moderngl
        self.gl = moderngl
        self.ctx = moderngl.create_standalone_context(require=330)
        if required_renderer and required_renderer.casefold() not in self.ctx.info['GL_RENDERER'].casefold():
            actual=self.ctx.info['GL_RENDERER']; self.ctx.release()
            raise RuntimeError(f'Puppet graphics device is {actual}; expected {required_renderer}. '
                               'Set this Python executable to High performance in Windows Graphics settings, then restart the worker.')
        self.width,self.height = width,height
        self.fb = self.ctx.simple_framebuffer((width,height), components=4)
        self.program = self.ctx.program(vertex_shader=LAYER_VERTEX,fragment_shader=FRAGMENT)
        self.buffer = self.ctx.buffer(reserve=4_000_000)
        self.vao = self.ctx.vertex_array(self.program,[(self.buffer,'2f 2f 1f','in_pos','in_uv','in_opacity')])
        self.textures=[]
        for a in atlases:
            t=self.ctx.texture(a.image.size,4,a.image.tobytes())
            t.filter=(moderngl.LINEAR,moderngl.LINEAR); t.repeat_x=t.repeat_y=False
            self.textures.append(t)

    def render(self, packed, center, half_height, opacity=None, slots=None):
        gl=self.gl; self.fb.use(); self.fb.clear(0,0,0,0)
        self.ctx.disable(gl.DEPTH_TEST); self.ctx.enable(gl.BLEND)
        self.ctx.blend_func = gl.ONE,gl.ONE_MINUS_SRC_ALPHA
        for slot,p in enumerate(packed):
            if slots is not None and slot not in slots: continue
            p=p.copy(); p[:,:2]=camera_transform(p[:,:2],self.width/self.height,center,half_height)
            if opacity is not None: p[:,4]*=opacity[slot]
            if p.nbytes>self.buffer.size: raise ValueError('Puppet geometry exceeds render budget')
            self.buffer.write(p.tobytes()); self.textures[slot].use(0)
            self.vao.render(gl.TRIANGLES,vertices=len(p))
        return np.frombuffer(self.fb.read(components=4,alignment=1),np.uint8).reshape(self.height,self.width,4).copy()

    def close(self):
        for x in [self.vao,self.buffer,self.program,*self.textures,self.fb]: x.release()
        self.ctx.release()


class LiveScene:
    """Causal bounded-history rig. No future samples or offline look-ahead.

    Missing observations hold briefly then fade. Reacquisition is eased; it
    cannot infer hidden joints or guarantee identities during dancer crossings.
    """
    def __init__(self, profile, aspect=16/9, smoothing=.08, lost_hold=.5):
        self.atlases=load_profile(profile); self.aspect=aspect
        self.smoothing=smoothing; self.lost_hold=lost_hold
        self.last=[None,None]; self.seen=[None,None]; self.time=None
        self.history=[[],[]]; self.scale=None
        self.center=np.array([aspect/2,-.5]); self.half_height=.66
        self.solo_centers=[self.center.copy(),self.center.copy()]

    def update(self, poses, now):
        dt = 1/30 if self.time is None else float(np.clip(now-self.time,.001,.5))
        self.time=now; alpha=1-np.exp(-dt/max(.001,self.smoothing))
        result=[]; opacity=[]
        for s,pose in enumerate(poses):
            if pose is not None:
                raw=np.asarray(pose,float)
                if raw.shape!=(33,5) or not np.isfinite(raw).all(): raise ValueError('Invalid live pose')
                p=raw[:,:2]*[self.aspect,-1]
                if self.last[s] is None: self.last[s]=p
                else:
                    valid=raw[:,3]>=.25
                    self.last[s][valid]+=(p[valid]-self.last[s][valid])*alpha
                self.seen[s]=now
            if self.last[s] is None:
                result.append(None); opacity.append(0.); continue
            age=max(0,now-self.seen[s]); opacity.append(float(np.clip(1-(age-self.lost_hold)/.35,0,1)))
            history=self.history[s]; history.append(self.last[s].copy()); del history[:-18]
            result.append(np.asarray(history))
        if self.scale is None and all(p is not None for p in result):
            p=np.stack([p[-1] for p in result])
            torso=np.linalg.norm(p[:,[11,12]].mean(axis=1)-p[:,[23,24]].mean(axis=1),axis=1)
            self.scale=float(np.clip(np.mean(torso)/.15,.25,3.))
            for slot in (0,1): self.solo_centers[slot][0]=float(p[slot,[23,24],0].mean())
        packed=[]
        for a,p in zip(self.atlases,result):
            if p is None or self.scale is None: packed.append(np.zeros((3,5),dtype='f4')); continue
            r=with_proportions(a,lambda: FluidPuppet(a,p,1/dt,np.ones((len(p),33)),1.,None,0.,self.scale,rotation_smoothing=0))
            packed.append(with_proportions(a,lambda: pack(r.parts(len(p)-1))))
        return packed,opacity
