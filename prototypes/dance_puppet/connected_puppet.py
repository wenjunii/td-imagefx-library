"""V4: character-space retargeting and overlapping, connected 2.5D pieces.

The measured choreography is 2D, not reconstructed 3D. Source joint positions
are never used as independent artwork anchors: a single articulated skeleton
owns every attachment. Original motion caches and texture atlases are read-only.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter

from layered_puppet import (Part, VIEWS, bone, chain_curve, classify_views,
                            neck_bridge, rigid, unit)
from puppet import head_rolls, rotation


@dataclass(frozen=True)
class Proportions:
    torso: float
    shoulders: float
    hips: float
    upper_arm: float
    forearm: float
    thigh: float
    shin: float
    neck: float
    head: float
    torso_width: float
    sleeve_width: float
    forearm_width: float
    shin_width: float
    robe_width: float


# Artistic rest proportions, independent of the two performers' anatomy.
# These are deliberately not estimates of anatomy from a crouching drawing.
PROPORTIONS = {
    'fan': Proportions(.170, .092, .062, .102, .091, .126, .116,
                       .041, .150, .133, .078, .042, .049, .135),
    'chain': Proportions(.133, .140, .096, .084, .077, .096, .091,
                         .035, .160, .205, .111, .055, .065, .180),
}
LIMBS = {'r': (12, 14, 16, 24, 26, 28), 'l': (11, 13, 15, 23, 25, 27)}


def clean_motion(points, fps=30., seconds=.05):
    """Offline, centered adaptive filtering: no causal playback delay.

    A three-frame median rejects isolated spikes, not sustained gestures.
    Fast movement receives less smoothing; quiet joints receive more. This
    cleans observations, but cannot certify identity or occluded joint accuracy.
    """
    p = np.asarray(points, dtype=float)
    if p.ndim != 3 or p.shape[1:] != (33, 2) or not np.isfinite(p).all():
        raise ValueError('Expected finite time x 33 x 2 points')
    if not np.isfinite(fps) or fps <= 0 or not np.isfinite(seconds) or not 0 <= seconds <= .3:
        raise ValueError('Invalid motion cleanup settings')
    if seconds == 0 or len(p) < 3:
        return p.copy()
    med = median_filter(p, size=(3, 1, 1), mode='nearest')
    residual = np.linalg.norm(p-med, axis=2)
    threshold = np.maximum(.004, np.median(residual, axis=0)*7)
    clean = np.where((residual > threshold)[..., None], med, p)
    speed = np.linalg.norm(np.gradient(clean, axis=0)*fps, axis=2)
    amount = 1/(1+(speed/.20)**2)
    fine = gaussian_filter1d(clean, max(.35, seconds*fps*.35), axis=0, mode='nearest')
    smooth = gaussian_filter1d(clean, max(.5, seconds*fps), axis=0, mode='nearest')
    out = smooth*amount[..., None]+fine*(1-amount[..., None])
    out[0], out[-1] = p[0], p[-1]
    return out


def projected_vectors(v, rest_length, fps, min_projection=.40):
    """Stable rest length with bounded measured foreshortening, not rubber bones."""
    lengths = np.linalg.norm(v, axis=1)
    reference = max(float(np.percentile(lengths, 90)), 1e-6)
    ratio = np.clip(lengths/reference, min_projection, 1.0)
    # Avoid a single almost-coincident joint flipping the next bone by 180 deg.
    angles = np.arctan2(v[:, 1], v[:, 0])
    good = np.flatnonzero(lengths > reference*.08)
    if len(good):
        angles = np.interp(np.arange(len(v)), good, np.unwrap(angles[good]))
    else:
        angles[:] = -np.pi/2
    if len(v) > 2:
        angles = gaussian_filter1d(angles, max(.25, fps*.012), mode='nearest')
        ratio = gaussian_filter1d(ratio, max(.35, fps*.020), mode='nearest')
    return np.column_stack([np.cos(angles), np.sin(angles)])*(rest_length*ratio)[:, None]


def retarget(points, character, scale, fps=30.):
    """One FK hierarchy per character; keep source timing and stage travel.

    Length changes between characters are intentional. A shared translation
    fits the ankle pair (biased toward the slower foot), keeping the character
    on the same stage without independently pulling apart its body parts.
    """
    p = np.asarray(points, float)
    if character not in PROPORTIONS or scale <= 0 or not np.isfinite(scale):
        raise ValueError('Invalid character/scale')
    q = p.copy()
    c = PROPORTIONS[character]
    root = (p[:, 23]+p[:, 24])*.5
    shoulder = (p[:, 11]+p[:, 12])*.5
    neck = root+projected_vectors(shoulder-root, c.torso*scale, fps, .48)
    shoulder_axis = projected_vectors(p[:, 11]-p[:, 12], c.shoulders*scale, fps, .25)
    hip_axis = projected_vectors(p[:, 23]-p[:, 24], c.hips*scale, fps, .32)
    q[:, 11], q[:, 12] = neck+shoulder_axis*.5, neck-shoulder_axis*.5
    q[:, 23], q[:, 24] = root+hip_axis*.5, root-hip_axis*.5
    for _, (s, e, w, h, k, a) in LIMBS.items():
        q[:, e] = q[:, s]+projected_vectors(p[:, e]-p[:, s], c.upper_arm*scale, fps)
        q[:, w] = q[:, e]+projected_vectors(p[:, w]-p[:, e], c.forearm*scale, fps)
        q[:, k] = q[:, h]+projected_vectors(p[:, k]-p[:, h], c.thigh*scale, fps)
        q[:, a] = q[:, k]+projected_vectors(p[:, a]-p[:, k], c.shin*scale, fps)
    head_delta = projected_vectors(p[:, 0]-shoulder, c.neck*scale, fps, .7)
    q[:, 0] = neck+head_delta
    # Face offsets are only cues for view/roll, not an independently scaled body.
    for j in range(1, 11):
        q[:, j] = q[:, 0]+(p[:, j]-p[:, 0])
    speed = np.zeros((len(p), 2))
    if len(p) > 1:
        speed = np.linalg.norm(np.gradient(p[:, [27, 28]], axis=0)*fps, axis=2)
    weights = .20+np.exp(-(speed/.12)**2)
    weights /= weights.sum(axis=1, keepdims=True)
    correction = ((p[:, [27, 28]]-q[:, [27, 28]])*weights[..., None]).sum(axis=1)
    if len(p) > 2:
        correction = gaussian_filter1d(correction, max(.5, fps*.025), axis=0, mode='nearest')
    q += correction[:, None, :]
    for dst, src in ((17, 15), (19, 15), (21, 15), (18, 16), (20, 16), (22, 16),
                     (29, 27), (31, 27), (30, 28), (32, 28)):
        q[:, dst] = q[:, src]
    return q


def neutral_pose():
    """Design review pose, separate from (and never written into) the capture."""
    p = np.zeros((1, 33, 2))
    for i, xy in {0:(0,.48), 7:(.025,.48), 8:(-.025,.48), 2:(.015,.49), 5:(-.015,.49),
                  11:(.05,.42),12:(-.05,.42),13:(.09,.32),14:(-.09,.32),
                  15:(.13,.22),16:(-.13,.22),23:(.035,.27),24:(-.035,.27),
                  25:(.045,.145),26:(-.045,.145),27:(.05,.025),28:(-.05,.025)}.items():
        p[0,i] = xy
    return p


def seam(sprite, start, end, width, name):
    part = neck_bridge(sprite, start, end, width)
    part.name = name
    return part


@lru_cache(maxsize=16)
def grid_faces(rows, columns):
    result=[]
    for y in range(rows-1):
        for x in range(columns-1):
            i=y*columns+x
            result.extend(((i,i+columns,i+1),(i+1,i+columns,i+columns+1)))
    faces=np.array(result,dtype='u4')
    faces.flags.writeable=False
    return faces


def torso_surface(sprite, neck, hip, width, scale, mirror=False, name='torso', shoulders=None, hips=None):
    """Calibrated shoulder row, collar and waist share the articulated body."""
    u=np.linspace(0,1,9); v=np.linspace(0,1,29)
    axis=unit(neck-hip,(0,1)); normal=np.array([axis[1],-axis[0]])
    length=np.linalg.norm(neck-hip)
    height=np.interp(v,[0,.27,.85,1],[length+.038*scale,length,0,-.025*scale])
    centers=hip+height[:,None]*axis
    cross=np.tile(normal*width,(len(v),1))
    if shoulders is not None and hips is not None:
        sa=np.asarray(shoulders[0])-shoulders[1]
        ha=np.asarray(hips[0])-hips[1]
        if sa@normal<0: sa=-sa
        if ha@normal<0: ha=-ha
        blend=np.clip((v-.27)/.58,0,1)
        cross=sa[None,:]*1.60*(1-blend[:,None])+ha[None,:]*1.85*blend[:,None]
    xy=(centers[:,None,:]+cross[:,None,:]*(u[None,:,None]-.5)).reshape(-1,2)
    uv=np.stack(np.meshgrid(1-u if mirror else u,v),axis=-1).reshape(-1,2)
    return Part(name,xy,sprite.texture_uv(uv),grid_faces(len(v),len(u)))


def joined_bone(sprite, a, b, start, end, width, name):
    """Subdivided limb with its open top cap tucked softly into the parent."""
    base=bone(sprite,a,b,start,end,width,name=name)
    u=np.linspace(0,1,7); v=np.linspace(0,1,21)
    uv=np.stack(np.meshgrid(u,v),axis=-1).reshape(-1,2)
    xy=base.xy[0]+uv[:,0,None]*(base.xy[1]-base.xy[0])+uv[:,1,None]*(base.xy[2]-base.xy[0])
    fade=np.clip((uv[:,1]-.025)/.10,0,1)
    fade=fade*fade*(3-2*fade)
    return Part(name,xy,sprite.texture_uv(uv),grid_faces(len(v),len(u)),fade)


def robe_surface(atlas, hip, knees, ankles, hip_width, width, sway, scale):
    """One connected skirt with a shared waist, knee-driven bend and tapered hem.

    Runtime UV rows fit the existing opaque artwork silhouette; atlas pixels
    are neither painted nor rewritten. Unlike v3, the same whole skirt is not
    copied once per leg and again at the pelvis.
    """
    sprite=atlas['robe']; u=np.linspace(0,1,13); v=np.linspace(.02,1,33)
    end=hip+(ankles-hip)*(.88 if atlas.name=='fan' else .80)
    axis=unit(end-hip); normal=np.array([-axis[1],axis[0]])
    length=max(float(np.linalg.norm(end-hip)),.025*scale)
    t=np.linspace(0,1,len(v))
    bend=np.clip(float((knees-(hip+end)*.5)@normal),-.035*scale,.035*scale)
    center=hip+axis*(length*t-.020*scale*(1-t))[:,None]
    center+=normal*(np.sin(t*np.pi)*(bend+sway))[:,None]
    left=np.zeros(len(v)); right=np.ones(len(v))
    if hasattr(atlas,'_v4_robe_rows'):
        left,right=atlas._v4_robe_rows
    elif hasattr(atlas,'image'):
        alpha=np.asarray(atlas.image)[:,:,3]
        h,w=alpha.shape
        uvrows=sprite.texture_uv(np.column_stack([np.zeros(len(v)),v]))
        x0,x1=(sprite.rect[[0,2]]*w).astype(int)
        for i,row in enumerate(np.clip((uvrows[:,1]*h).astype(int),0,h-1)):
            xs=np.flatnonzero(alpha[row,max(0,x0):min(w,x1+1)]>180)
            if len(xs):
                left[i]=max(0,(xs.min()-1)/max(1,x1-x0))
                right[i]=min(1,(xs.max()+1)/max(1,x1-x0))
        left=gaussian_filter1d(left,1,mode='nearest')
        right=gaussian_filter1d(right,1,mode='nearest')
        atlas._v4_robe_rows=(left,right)
    # Retain the artwork's irregular flowing silhouette, including hem tips.
    silhouette=np.clip((right-left)/(.26+.74*t),.18,1.10)
    breadth=(hip_width*(1-t)+width*t)*silhouette
    xy=(center[:,None,:]+normal*(u[None,:,None]-.5)*breadth[:,None,None]).reshape(-1,2)
    uv=np.stack([left[:,None]+(right-left)[:,None]*u[None,:],np.broadcast_to(v[:,None],(len(v),len(u)))],axis=-1).reshape(-1,2)
    return Part('connected_robe',xy,sprite.texture_uv(uv),grid_faces(len(v),len(u)))


class ConnectedPuppet:
    def __init__(self, atlas, points, fps=30., confidence=None, cloth_amount=.65,
                 overrides=None, smoothing=.05, scale=1.):
        if not 0 <= cloth_amount <= 2:
            raise ValueError('Cloth amount must be 0..2')
        self.atlas, self.name = atlas, atlas.name
        self.scale, self.fps, self.cloth_amount = scale, fps, cloth_amount
        self.source = clean_motion(points, fps, smoothing)
        self.points = retarget(self.source, self.name, scale, fps)
        # Infer facing from original observations, not artistic width changes.
        self.views = classify_views(self.source, confidence, fps)
        self.body_views = classify_views(self.source, confidence, fps, body=True)
        for e in overrides or []:
            if e['view'] not in VIEWS or e['end'] <= e['start']:
                raise ValueError('Invalid view override')
            a,b = max(0,round(e['start']*fps)), min(len(points),round(e['end']*fps))
            self.views[a:b] = np.eye(5)[VIEWS.index(e['view'])]
            self.body_views[a:b] = self.views[a:b]
        self.rolls = head_rolls(self.source, max(.5, fps*.035))
        root = self.points[:, [23,24]].mean(axis=1)
        self.lag = np.zeros_like(root)
        for i in range(1, len(root)):
            self.lag[i] = self.lag[i-1]*np.exp(-1/(fps*.12))+(root[i-1]-root[i])*.5
        self.lag = np.clip(self.lag, -.012*scale, .012*scale)*cloth_amount

    def parts(self, frame):
        p, s, c, atlas = self.points[frame], self.scale, PROPORTIONS[self.name], self.atlas
        neck, hip = p[[11,12]].mean(axis=0), p[[23,24]].mean(axis=0)
        w, hw = self.body_views[frame], self.views[frame]
        profile = w[1]+w[2]
        right = w[1] >= w[2]
        far, near = ('r','l') if right else ('l','r')
        legs, sleeves, forearms, under = {}, {}, {}, {}
        for side,(shoulder,elbow,wrist,h,knee,ankle) in LIMBS.items():
            shin_name = 'shin_side' if profile > .5 else 'shin_front'
            legs[side] = bone(atlas[shin_name], (.5,.08), (.5,.82), p[knee],p[ankle],
                              c.shin_width*s, mirror=profile>.5 and not right, name=side+'_shin')
            if self.name == 'fan':
                a,b = ((.83,.065),(.30,.36)) if side=='r' else ((.17,.065),(.70,.36))
                fa = (.35,.04) if side=='r' else (.65,.04)
                fb = (.72,.72) if side=='r' else (.28,.72)
            else:
                a,b = ((.83,.045),(.69,.69)) if side=='r' else ((.17,.045),(.31,.69))
                fa,fb = (.5,.04),(.5,.74)
            sleeves[side] = joined_bone(atlas['upper_'+side],a,b,p[shoulder],p[elbow],c.sleeve_width*s,name=side+'_sleeve')
            forearms[side] = joined_bone(atlas['fore_'+side],fa,fb,p[elbow],p[wrist],c.forearm_width*s,name=side+'_forearm')
            under[side] = [
                seam(atlas['neck'],neck,p[shoulder],.012*s,side+'_shoulder_join'),
                seam(atlas['neck'],p[shoulder],p[elbow],.013*s,side+'_upper_join'),
                seam(atlas['neck'],p[elbow],p[wrist],.012*s,side+'_elbow_join'),
                seam(atlas['neck'],p[h],p[knee],.018*s,side+'_thigh_join'),
                seam(atlas['neck'],p[knee],p[ankle],.014*s,side+'_knee_join'),
            ]
        parts = under[far]+under[near]+[legs[far],legs[near],
                                       sleeves[far],forearms[far],sleeves[near]]
        knees = p[[25,26]].mean(axis=0)
        ankles = p[[27,28]].mean(axis=0)
        spread=float(np.linalg.norm(p[27]-p[28]))
        parts.append(robe_surface(atlas,hip,knees,ankles,c.hips*s*1.6,
                                 max(c.robe_width*s,spread*.8+c.shin_width*s),float(self.lag[frame,0]),s))
        # Keep collar close to the neck. Heads pivot from a chin attachment,
        # rather than a tracked nose floating independently above the torso.
        head_angle = self.rolls[frame]
        head_base = neck+(p[0]-neck)*.64
        parts.append(seam(atlas['neck'],neck,head_base,.020*s,'neck_join'))
        for i,view in enumerate(VIEWS):
            if w[i] < .015:
                continue
            suffix = 'side' if view in ('right','left') else view
            width = c.torso_width*s*(.68 if suffix=='side' else 1.)
            torso = torso_surface(atlas['torso_'+suffix],neck,hip,width,s,
                                  mirror=view=='left',name='torso_'+view,shoulders=p[[11,12]],hips=p[[23,24]])
            torso.opacity = float(w[i]); parts.append(torso)
        if profile < .5:
            parts.append(forearms[far])
        parts.append(forearms[near])
        if self.name == 'fan':
            for side,(_,e,wr,*_) in LIMBS.items():
                d = unit(p[wr]-p[e]); angle = np.arctan2(d[1],d[0])+np.pi/2
                parts.append(rigid(atlas['prop'],(.5,.055),p[wr],.095*s,angle,name=side+'_fan'))
        else:
            curve = chain_curve(p[16],p[15],.040*s)
            for i,point in enumerate(curve):
                d = unit(curve[min(i+1,len(curve)-1)]-curve[max(i-1,0)])
                part = rigid(atlas['prop'],(.5,.5),point,.015*s,np.arctan2(d[1],d[0])+np.pi/2,name='chain_'+str(i))
                if i%2:
                    n = np.array([-d[1],d[0]]); delta = part.xy-point
                    part.xy = point+(delta@d)[:,None]*d+(delta@n)[:,None]*n*.42
                parts.append(part)
        for i,view in enumerate(VIEWS):
            if hw[i] < .015:
                continue
            suffix = 'side' if view in ('right','left') else view
            anchor = (.67,.80) if suffix=='side' else (.5,.79)
            if suffix=='bow': anchor=(.5,.78)
            part = rigid(atlas['head_'+suffix],anchor,head_base,c.head*s,head_angle*(.5 if suffix=='bow' else 1.),
                         mirror=view=='left',opacity=float(hw[i]),name='head_'+view)
            parts.append(part)
        return parts

    def report(self):
        c = PROPORTIONS[self.name]
        return dict(character=self.name,scale=self.scale,rest_proportions=vars(c),
                    nominal_height=(c.torso+c.thigh+c.shin+c.head*.8)*self.scale,
                    cloth_amount=self.cloth_amount,
                    views={v:int((self.views.argmax(axis=1)==i).sum()) for i,v in enumerate(VIEWS)},
                    retarget='Character-space FK with bounded projection and weighted ankle-pair anchoring',
                    connections='Shared skeleton plus opaque overlapping seam underlays',
                    limitations='2D view heuristics, no measured depth or exact contact/cloth simulation')
