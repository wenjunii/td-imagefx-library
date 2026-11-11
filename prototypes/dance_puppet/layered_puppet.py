"""V3: independent view sprites, articulated garments and wrist-driven props.

The pose input is still monocular 2D. View selection and shallow overlap order
are artistic heuristics, not recovered depth. No limb can deform another part.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d

from puppet import head_rolls, rotation


VIEWS = ('front', 'right', 'left', 'bow', 'back')
NAMES = ('head_front', 'head_side', 'head_bow', 'head_back',
         'torso_front', 'torso_side', 'torso_bow', 'torso_back',
         'upper_r', 'upper_l', 'fore_r', 'fore_l',
         'robe', 'shin_front', 'shin_side', 'prop')


def unit(v, fallback=(0., -1.)):
    v = np.asarray(v, dtype=float)
    length = np.linalg.norm(v)
    return v / length if length > 1e-8 else np.array(fallback, dtype=float)


@dataclass
class Sprite:
    name: str
    rect: np.ndarray  # source texture UV rectangle; original PNG never rewritten
    aspect: float

    def texture_uv(self, local):
        return self.rect[:2] + np.asarray(local) * (self.rect[2:] - self.rect[:2])


class Atlas:
    """Read-only sampler for the two calibrated generated 1254-square sheets."""
    def __init__(self, path, character):
        if character not in ('fan', 'chain'):
            raise ValueError('Unknown atlas character')
        self.image = Image.open(Path(path)).convert('RGBA')
        if self.image.size != (1254, 1254):
            raise ValueError('V3 atlas calibration requires the saved 1254x1254 sheets')
        self.name = character
        alpha = np.asarray(self.image)[:, :, 3]
        # Image generation does not guarantee equal cells; use calibrated gutters.
        rows = [0, 372, 648, 944, 1254] if character == 'fan' else [0, 340, 628, 925, 1254]
        cols = [0, 334, 642, 938, 1254]
        self.sprites = {}
        for i, name in enumerate(NAMES):
            row, col = divmod(i, 4)
            x0, x1 = cols[col:col+2]; y0, y1 = rows[row:row+2]
            y, x = np.where(alpha[y0:y1, x0:x1] > 180)
            if not len(x):
                raise ValueError('Empty atlas region: ' + name)
            # Half-pixel inset prevents adjacent sprites bleeding into a crop.
            bounds = np.array([x0+x.min()+.5, y0+y.min()+.5,
                               x0+x.max()+.5, y0+y.max()+.5])
            self.sprites[name] = Sprite(name, bounds/1254,
                                       (bounds[2]-bounds[0])/(bounds[3]-bounds[1]))
        torso = self.sprites['torso_front']
        # Sample solid collar cloth below the open top, not another hollow ring.
        neck_rect = torso.texture_uv([[.38, .10], [.62, .29]]).ravel()
        self.sprites['neck'] = Sprite('neck', neck_rect, torso.aspect*.24/.19)
        # Sample solid navy cloth for the bridge instead of magnifying a tiny
        # patch's linework. This only changes runtime UVs; no image is edited.
        pixels = np.asarray(self.image)
        x0,y0,x1,y1 = (neck_rect*1254).astype(int)
        region = pixels[y0:y1,x0:x1].astype(float)
        cost = np.sum((region[:,:,:3]-[10,27,48])**2,axis=2)+(255-region[:,:,3])*10000
        iy,ix = np.unravel_index(cost.argmin(),cost.shape)
        uv = np.array([x0+ix+.5,y0+iy+.5])/1254
        self.sprites['neck'] = Sprite('neck',np.tile(uv,2),1.)

    def __getitem__(self, name):
        return self.sprites[name]


@dataclass
class Part:
    name: str
    xy: np.ndarray
    uv: np.ndarray
    faces: np.ndarray
    opacity: float = 1.


QUAD = np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
FACES = np.array([[0, 2, 1], [1, 2, 3]], dtype='u4')


def rigid(sprite, anchor, target, height, angle=0., mirror=False, opacity=1., name=None):
    """A face/prop card: rigid, uniform scale, absolutely no joint skinning."""
    if height <= 0 or not np.isfinite(height):
        raise ValueError('Positive finite sprite height required')
    local = (QUAD-np.asarray(anchor))*[sprite.aspect*height, -height]
    if mirror:
        local[:, 0] *= -1
    xy = local @ rotation(angle).T + target
    return Part(name or sprite.name, xy, sprite.texture_uv(QUAD), FACES, opacity)


def bone(sprite, a, b, start, end, width, mirror=False, name=None):
    """Independent two-anchor affine piece, with stable transverse thickness."""
    local = QUAD * [sprite.aspect, 1.]
    a, b = np.asarray(a)*[sprite.aspect, 1.], np.asarray(b)*[sprite.aspect, 1.]
    along = unit(b-a, (0., 1.)); normal = np.array([along[1], -along[0]])
    relative = local-a
    longitudinal = relative @ along / max(np.linalg.norm(b-a), 1e-6)
    transverse = relative @ normal
    span = max(np.ptp(local @ normal), 1e-6)
    direction = unit(np.asarray(end)-start)
    across = np.array([-direction[1], direction[0]]) * (-1 if mirror else 1)
    xy = (np.asarray(start) + longitudinal[:, None]*(np.asarray(end)-start)
          + transverse[:, None]*across*width/span)
    return Part(name or sprite.name, xy, sprite.texture_uv(QUAD), FACES)


def cloth_panel(sprite, start, end, width, sway=0., mirror=False, rows=17, name='robe'):
    """Bounded strip warp: monotone along its own bone, so it cannot invert.

    The thigh panels overlap separate shin pieces at the knees. This avoids
    folding a single connected skirt through itself during a deep squat.
    Secondary sway affects the hem, never the tracked hips or knees.
    """
    if rows < 2 or width <= 0 or not np.isfinite(width+sway):
        raise ValueError('Invalid cloth panel controls')
    start, end = np.asarray(start, float), np.asarray(end, float)
    axis = unit(end-start)
    length = max(float(np.linalg.norm(end-start)), .004)
    end = start+axis*length
    normal = np.array([-axis[1], axis[0]])
    t = np.linspace(0, 1, rows)
    sway = np.clip(sway, -width*.25, width*.25)
    center = start+(end-start)*t[:, None]+normal*(np.sin(t*np.pi)*sway)[:, None]
    # Waist narrow, flowing hem broad, all widths strictly positive.
    breadth = width*(.50+.50*t)
    u = np.array([0., .25, .5, .75, 1.])
    xy = (center[:, None, :]+normal*(u[None, :, None]-.5)*breadth[:, None, None]).reshape(-1, 2)
    uv = np.stack(np.meshgrid(u, t), axis=-1).reshape(-1, 2)
    if mirror:
        uv[:, 0] = 1-uv[:, 0]
    faces = []
    for row in range(rows-1):
        for col in range(4):
            i = row*5+col
            faces.extend(((i, i+5, i+1), (i+1, i+5, i+6)))
    return Part(name, xy, sprite.texture_uv(uv), np.array(faces, dtype='u4'))


def chain_curve(left, right, sag, count=23):
    """A bounded hanging chain; endpoints stay pinned to the actual wrists."""
    left, right = np.asarray(left, float), np.asarray(right, float)
    if count < 2 or sag < 0:
        raise ValueError('Invalid chain settings')
    t = np.linspace(0, 1, count)
    return left[None, :]*(1-t[:, None])+right[None, :]*t[:, None]+np.column_stack(
        [np.zeros(count), -4*sag*t*(1-t)])


def neck_bridge(sprite, start, end, width):
    """Rounded collar cloth; no rectangular texture-card corners can protrude."""
    start, end = np.asarray(start), np.asarray(end)
    axis = unit(end-start); normal = np.array([-axis[1],axis[0]])
    radius = width*.5
    angles = np.linspace(np.pi/2,3*np.pi/2,9)
    boundary = [start+radius*(np.cos(t)*axis+np.sin(t)*normal) for t in angles]
    angles = np.linspace(-np.pi/2,np.pi/2,9)
    boundary += [end+radius*(np.cos(t)*axis+np.sin(t)*normal) for t in angles]
    xy = np.vstack([(start+end)*.5,boundary])
    # Sample a narrow interior of the original opaque cloth.
    delta = xy-start
    uv = np.column_stack([.5+(delta@normal)/max(width,1e-6)*.7,
                          .25+np.clip((delta@axis)/max(np.linalg.norm(end-start),1e-6),0,1)*.5])
    faces = np.array([(0,i+1,(i+1)%len(boundary)+1) for i in range(len(boundary))],dtype='u4')
    return Part('neck',xy,sprite.texture_uv(uv),faces)


def classify_views(points, confidence=None, fps=30., body=False):
    """Soft, temporally filtered front/profile/bow/back choices.

    Nose-to-ear offset indicates a profile; contracted shoulder projection
    helps disambiguate it. A low nose plus shortened spine indicates a bow.
    Back is only inferred when facial landmarks are missing AND shoulders
    reverse. Optional authored overrides can replace these estimates.
    """
    p = np.asarray(points)
    shoulders = (p[:, 11]+p[:, 12])*.5
    hips = (p[:, 23]+p[:, 24])*.5
    torso = np.linalg.norm(shoulders-hips, axis=1)
    rest = max(np.percentile(torso, 85), .035)
    width = np.abs(p[:, 11, 0]-p[:, 12, 0])
    normal_width = max(np.percentile(width, 85), .03)
    face_offset = p[:, 0, 0]-(p[:, 7, 0]+p[:, 8, 0])*.5
    facing = np.clip(np.abs(face_offset)/(.24*normal_width), 0, 1)
    narrow = np.clip(1-width/normal_width, 0, 1)
    profile = np.clip((facing-.30)/.50, 0, 1)*np.clip(.35+narrow, 0, 1)
    # A convincing face profile can occur while the shoulders are still front.
    profile = np.maximum(profile, np.clip((facing-.82)/.18, 0, 1)*.85)
    if body:
        # Turning only the head must not replace a frontal chest with a profile.
        profile *= np.clip((.90-width/normal_width)/.35, 0, 1)
    bow = np.clip((shoulders[:, 1]+rest*.06-p[:, 0, 1])/(rest*.22), 0, 1)
    bow *= np.clip((1.03-torso/rest)/.35, 0, 1)
    result = np.zeros((len(p), 5))
    result[:, 3] = bow
    result[:, 1] = profile*(face_offset>=0)*(1-bow)
    result[:, 2] = profile*(face_offset<0)*(1-bow)
    result[:, 0] = 1-result.sum(axis=1)
    if confidence is not None:
        back = ((p[:, 11, 0] < p[:, 12, 0]) & (np.asarray(confidence)[:, 0] < .3))
        result[back] = [0, 0, 0, 0, 1]
    # Make a categorical decision with hysteresis first. Continuously mixing
    # several faces would produce double eyes/crowns even in a held pose.
    selected = np.zeros_like(result)
    current = int(result[0].argmax())
    for i, scores in enumerate(result):
        best = int(scores.argmax())
        if scores[best] > scores[current]+.14:
            current = best
        selected[i, current] = 1
    # Crossfade only the short boundary between distinct view cards.
    result = gaussian_filter1d(selected, max(.025*fps, .5), axis=0, mode='nearest')
    result /= result.sum(axis=1, keepdims=True)
    return result


class LayeredPuppet:
    def __init__(self, atlas, points, fps=30., confidence=None, cloth_amount=1., overrides=None):
        self.atlas = atlas
        self.name = atlas.name
        self.points = np.asarray(points, dtype=float)
        if self.points.ndim != 3 or self.points.shape[1:] != (33, 2) or not np.isfinite(self.points).all():
            raise ValueError('Expected finite time x 33 x 2 points')
        if not 0 <= cloth_amount <= 2:
            raise ValueError('Cloth amount must be 0..2')
        self.fps = fps
        self.cloth_amount = cloth_amount
        p = self.points
        torso = np.linalg.norm((p[:, 11]+p[:, 12]-p[:, 23]-p[:, 24])*.5, axis=1)
        self.scale = float(max(np.percentile(torso, 85), .06)/.15)
        self.views = classify_views(p, confidence, fps)
        self.body_views = classify_views(p, confidence, fps, body=True)
        for entry in overrides or []:
            if entry['view'] not in VIEWS or entry['end'] <= entry['start']:
                raise ValueError('Invalid view override')
            start = max(0, round(entry['start']*fps))
            end = min(len(p), round(entry['end']*fps))
            self.views[start:end] = np.eye(5)[VIEWS.index(entry['view'])]
            self.body_views[start:end] = self.views[start:end]
        self.rolls = head_rolls(p)
        # Causal garment lag from projected hip velocity, not a physics claim.
        root = (p[:, 23]+p[:, 24])*.5
        lag = np.zeros_like(root)
        for i in range(1, len(root)):
            lag[i] = lag[i-1]*np.exp(-1/(fps*.13))+(root[i-1]-root[i])*.7
        self.lag = np.clip(lag, -.015*self.scale, .015*self.scale)*cloth_amount

    def parts(self, frame):
        p = self.points[frame]; s = self.scale; atlas = self.atlas
        neck, hip = (p[11]+p[12])*.5, (p[23]+p[24])*.5
        weights = self.body_views[frame]
        head_weights = self.views[frame]
        profile = weights[1]+weights[2]
        right = weights[1] >= weights[2]
        # Side-facing body's far arm is the one on its back edge.
        far = 'r' if right else 'l'
        limbs = {'r': (12, 14, 16, 24, 26, 28), 'l': (11, 13, 15, 23, 25, 27)}
        legs, sleeves, forearms, robes = {}, {}, {}, {}
        for side, (shoulder, elbow, wrist, h, knee, ankle) in limbs.items():
            shin_name = 'shin_side' if profile > .5 else 'shin_front'
            legs[side] = bone(atlas[shin_name], (.5, .06), (.5, .82), p[knee], p[ankle],
                              .046*s, mirror=profile>.5 and not right, name=side+'_shin')
            end = p[knee]+(p[knee]-p[h])*.12
            axis = unit(end-p[h]); normal = np.array([-axis[1], axis[0]])
            robes[side] = cloth_panel(atlas['robe'], p[h]-(p[h]-hip)*.28, end,
                (.088 if self.name=='fan' else .096)*s,
                float(self.lag[frame]@normal), mirror=side=='l', name=side+'_robe')
            if self.name == 'fan':
                a, b = ((.83, .065), (.30, .36)) if side=='r' else ((.17, .065), (.70, .36))
            else:
                a, b = ((.83, .045), (.69, .69)) if side=='r' else ((.17, .045), (.31, .69))
            sleeves[side] = bone(atlas['upper_'+side], a, b, p[shoulder], p[elbow],
                                 .070*s, name=side+'_sleeve')
            # Wrist is above the hand tips, so the hand remains visible beyond it.
            a = (.35, .04) if self.name=='fan' and side=='r' else (.65, .04) if self.name=='fan' else (.5, .04)
            b = (.72, .72) if self.name=='fan' and side=='r' else (.28, .72) if self.name=='fan' else (.5, .74)
            forearms[side] = bone(atlas['fore_'+side], a, b, p[elbow], p[wrist],
                                 .044*s, name=side+'_forearm')
        near = 'l' if far=='r' else 'r'
        parts = [legs[far], robes[far], sleeves[far], forearms[far],
                 legs[near], robes[near], sleeves[near]]
        # A separate collar/neck joins the head to the shoulders during a bow.
        # It never receives an arm or garment deformation weight.
        head_angle = self.rolls[frame]*(1-head_weights[3]*.7)
        head_base = p[0]+rotation(head_angle)@np.array([0., -.032*s])
        for index, view in enumerate(VIEWS):
            opacity = weights[index]
            if opacity < .015:
                continue
            suffix = 'side' if view in ('right', 'left') else view
            torso = bone(atlas['torso_'+suffix], (.5, .15), (.5, .85), neck, hip,
                         (.066 if suffix=='side' else .11 if self.name=='fan' else .13)*s,
                         mirror=view=='left', name='torso_'+view)
            torso.opacity = float(opacity)
            parts.append(torso)
        parts.append(neck_bridge(atlas['neck'], neck, head_base, .030*s))
        # Both forearms in front for frontal bows: no face/torso mesh can drag them.
        if profile < .5:
            parts.append(forearms[far])
        parts.append(forearms[near])
        if self.name == 'fan':
            for side, (_, elbow, wrist, *_) in limbs.items():
                direction = unit(p[wrist]-p[elbow])
                angle = np.arctan2(direction[1], direction[0])+np.pi/2
                parts.append(rigid(atlas['prop'], (.5, .055), p[wrist], .075*s,
                                   angle, name=side+'_fan'))
        else:
            curve = chain_curve(p[16], p[15], .035*s)
            for i, point in enumerate(curve):
                direction = unit(curve[min(i+1,len(curve)-1)]-curve[max(i-1,0)])
                angle = np.arctan2(direction[1], direction[0])+np.pi/2
                link = rigid(atlas['prop'], (.5, .5), point, .013*s,
                             angle, name='chain_'+str(i))
                # Alternating link planes suggest depth without invented hand data.
                if i%2:
                    normal = np.array([-direction[1], direction[0]])
                    d = link.xy-point
                    link.xy = point+(d@direction)[:,None]*direction+(d@normal)[:,None]*normal*.42
                parts.append(link)
        for index, view in enumerate(VIEWS):
            if head_weights[index] < .015:
                continue
            suffix = 'side' if view in ('right', 'left') else view
            anchor = (.83, .56) if suffix=='side' else (.5, .61 if self.name=='chain' else .55)
            if suffix=='bow':
                anchor = (.5, .62)
            parts.append(rigid(atlas['head_'+suffix], anchor, p[0],
                (.119 if self.name=='fan' else .116)*s, self.rolls[frame]*(.3 if suffix=='bow' else 1),
                mirror=view=='left', opacity=float(head_weights[index]), name='head_'+view))
        return parts

    def report(self):
        return dict(character=self.name, thickness_scale=self.scale, cloth_amount=self.cloth_amount,
                    dominant_view_frames={v:int((self.views.argmax(axis=1)==i).sum()) for i,v in enumerate(VIEWS)},
                    body_view_frames={v:int((self.body_views.argmax(axis=1)==i).sum()) for i,v in enumerate(VIEWS)},
                    view_selection='2D heuristic with short crossfades; not captured 3D depth',
                    garment_model='Independent overlapping thigh panels with bounded causal sway')
