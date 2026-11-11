"""Small, deterministic 2.5D mesh-puppet experiment (not a production rig).

Tracks are observed 2D joints. The artwork stays front-facing; there is no
inferred back view, clothing simulation, hand capture or reconstructed 3D body.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import Delaunay


# Pixel-space manual calibration of the generated 1024x1536 A-pose artwork.
# Anatomical right appears on the left of these front-facing sprites.
RIGS = {
    'fan': dict(root=(512,820), neck=(512,417), head=(512,270),
        rs=(393,455), re=(306,652), rw=(198,830), rh=(185,877),
        ls=(626,455), le=(727,652), lw=(825,830), lh=(842,877),
        rhip=(433,823), rk=(411,1135), ra=(368,1406), rf=(321,1473),
        lhip=(593,823), lk=(627,1135), la=(663,1406), lf=(706,1473)),
    'chain': dict(root=(512,807), neck=(512,419), head=(512,285),
        rs=(329,439), re=(265,620), rw=(240,795), rh=(257,834),
        ls=(695,439), le=(759,620), lw=(784,795), lh=(767,834),
        rhip=(400,823), rk=(336,1123), ra=(305,1365), rf=(259,1435),
        lhip=(624,823), lk=(688,1123), la=(719,1365), lf=(765,1435)),
}
BONES = [('root','neck'),('neck','head'),
         ('rs','re'),('re','rw'),('rw','rh'),
         ('ls','le'),('le','lw'),('lw','lh'),
         ('rhip','rk'),('rk','ra'),('ra','rf'),
         ('lhip','lk'),('lk','la'),('la','lf')]
# Two-dimensional source vectors for each bone. Hands/feet deliberately inherit
# their parent's angle because this tracker does not independently observe them.
POSE_BONES = [(None,None),(None,0),(12,14),(14,16),(14,16),
              (11,13),(13,15),(13,15),(24,26),(26,28),(26,28),
              (23,25),(25,27),(25,27)]
OBSERVED_JOINTS = dict(head=0,rs=12,re=14,rw=16,ls=11,le=13,lw=15,
                       rhip=24,rk=26,ra=28,lhip=23,lk=25,la=27)


def rotation(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c,-s],[s,c]])


def short_angle(angle):
    return (angle+np.pi)%(2*np.pi)-np.pi


def interpolate_confident(values, valid):
    """Fill missing samples for an offline test; keep the original cache intact."""
    result = np.asarray(values, dtype=float).copy()
    good = np.flatnonzero(valid)
    if not len(good):
        raise ValueError('A required joint has no confident observations')
    for axis in range(result.shape[1]):
        result[:,axis] = np.interp(np.arange(len(result)),good,result[good,axis])
    return result


class Motion:
    def __init__(self, path, smoothing_seconds=.07, confidence=.3):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('kind') != 'imagefx.dance-puppet.motion' or data.get('schema_version') != 1:
            raise ValueError('Unsupported motion cache')
        self.fps = float(data['fps'])
        if not np.isfinite(self.fps) or self.fps <= 0 or not data['frames']:
            raise ValueError('Invalid frame rate / empty motion')
        self.n = len(data['frames'])
        self.duration = self.n/self.fps
        self.aspect = data['source_size'][0]/data['source_size'][1]
        self.data = data
        raw = np.full((self.n,2,33,5),np.nan)
        for frame, r in enumerate(data['frames']):
            if len(r['poses']) != 2:
                raise ValueError('Exactly two track slots are required')
            for slot, pose in enumerate(r['poses']):
                if pose is not None:
                    a = np.asarray(pose)
                    if a.shape != (33,5) or not np.all(np.isfinite(a)):
                        raise ValueError('Non-finite or malformed pose')
                    raw[frame,slot] = a
        valid = np.isfinite(raw[:,:,:,0]) & (raw[:,:,:,3] >= confidence)
        self.valid = valid
        self.points = raw[:,:,:,:2].copy()
        for slot in range(2):
            for joint in range(33):
                self.points[:,slot,joint] = interpolate_confident(
                    self.points[:,slot,joint],valid[:,slot,joint])
        self.points[:,:,:,0] *= self.aspect
        self.points[:,:,:,1] *= -1
        self.observed_points = self.points.copy()
        if smoothing_seconds > 0:
            self.points = gaussian_filter1d(self.points,
                sigma=smoothing_seconds*self.fps,axis=0,mode='nearest')
            # An offline filter must not replace the actual opening / closing
            # pose with an average of later / earlier movement.
            self.points[0] = self.observed_points[0]
            self.points[-1] = self.observed_points[-1]
        self.roots = (self.points[:,:,23]+self.points[:,:,24])*.5
        shoulders = (self.points[:,:,11]+self.points[:,:,12])*.5
        vectors = shoulders-self.roots
        self.angles = np.zeros((self.n,2,len(BONES)))
        for k,(a,b) in enumerate(POSE_BONES):
            if k == 0:
                v = vectors
            elif k == 1:
                v = self.points[:,:,0]-shoulders
            else:
                v = self.points[:,:,b]-self.points[:,:,a]
            self.angles[:,:,k] = np.arctan2(v[:,:,1],v[:,:,0])
        # Angles are unwrapped in time before interpolation; avoid 360-degree pops.
        self.angles = np.unwrap(self.angles,axis=0)
        self.body_scale = np.median(np.linalg.norm(vectors,axis=2),axis=0)
        if np.any(self.body_scale < .015):
            raise ValueError('Degenerate body scale')

    def sample(self, seconds, loop=True):
        lo,hi,weight = self._indices(seconds,loop)
        return (self.angles[lo]*(1-weight)+self.angles[hi]*weight,
                self.roots[lo]*(1-weight)+self.roots[hi]*weight)

    def sample_points(self, seconds, loop=True):
        lo,hi,weight = self._indices(seconds,loop)
        return self.points[lo]*(1-weight)+self.points[hi]*weight

    def _indices(self, seconds, loop):
        seconds = float(seconds)
        if not np.isfinite(seconds):
            raise ValueError('Time must be finite')
        t = seconds % self.duration if loop else np.clip(seconds,0,(self.n-1)/self.fps)
        f = min(t*self.fps,self.n-1)
        lo = int(f); hi = min(lo+1,self.n-1); weight = f-lo
        return lo,hi,weight

    def report(self):
        watched = [0,11,12,13,14,15,16,23,24,25,26,27,28]
        return dict(frames=self.n,fps=self.fps,duration=self.duration,
            source_start_seconds=self.data.get('source_start_seconds',0),
            detection_fraction=self.data['detection_fraction'],
            confident_joint_fraction=[float(self.valid[:,s,watched].mean()) for s in (0,1)],
            note='Detection is not accuracy. Low-confidence joints are interpolated offline; review overlaps and crossings.')


class Puppet:
    def __init__(self, name, columns=65, rows=97, match_joints=False):
        self.name = name
        self.match_joints = match_joints
        pix = dict(RIGS[name])
        if match_joints:
            # Tracked slot 0 is the nose, not the crown / top of the face.
            pix['head'] = (512,312 if name=='fan' else 318)
        origin = np.array(pix['root'])
        self.origin = origin
        self.joint_names = list(pix)
        self.rest = {k:(np.array(v)-origin)*[1,-1]/1536 for k,v in pix.items()}
        self.rest_angles = np.array([np.arctan2(*(self.rest[b]-self.rest[a])[::-1]) for a,b in BONES])
        self.lengths = np.array([np.linalg.norm(self.rest[b]-self.rest[a]) for a,b in BONES])
        x,y = np.meshgrid(np.linspace(0,1024,columns),np.linspace(0,1536,rows))
        pixel_vertices = np.stack([x.ravel(),y.ravel()],axis=1)
        if match_joints:
            # Actual mesh vertices at calibrated joints allow a meaningful
            # positional-fit test, not just checking abstract rig endpoints.
            self.joint_indices = np.arange(len(pixel_vertices),len(pixel_vertices)+len(pix))
            pixel_vertices = np.vstack([pixel_vertices,list(pix.values())])
        self.uv = pixel_vertices/[1024,1536]
        self.vertices = (pixel_vertices-origin)*[1,-1]/1536
        faces = []
        for row in range(rows-1):
            for col in range(columns-1):
                i = row*columns+col
                faces += [(i,i+columns,i+1),(i+1,i+columns,i+columns+1)]
        self.faces = np.asarray(Delaunay(pixel_vertices).simplices if match_joints else faces,dtype='u4')
        self.weights = self._weights(pixel_vertices)
        if match_joints:
            controls = np.array([self.rest[k] for k in self.joint_names])
            self.control_weights = self._weights(np.array(list(pix.values())))
            sigma = .085
            kernel = np.exp(-np.sum((controls[:,None]-controls[None,:])**2,axis=2)/(2*sigma**2))
            vertex_kernel = np.exp(-np.sum((self.vertices[:,None]-controls[None,:])**2,axis=2)/(2*sigma**2))
            self.correction = vertex_kernel @ np.linalg.pinv(kernel,rcond=1e-12)
            # Keep the face/crown a rigid card even when the shoulder correction
            # is large (a bow or foreshortened neck). Its nose already matches.
            self.head_protection = np.clip((pix['neck'][1]-pixel_vertices[:,1])/48,0,1)

    def _weights(self, pixels):
        vertices = (pixels-self.origin)*[1,-1]/1536
        distances = []
        for a,b in BONES:
            start,end = self.rest[a],self.rest[b]
            delta = end-start
            t = np.clip((vertices-start)@delta/(delta@delta),0,1)
            distances.append(np.linalg.norm(vertices-start-t[:,None]*delta,axis=1))
        d = np.asarray(distances).T
        # Strong locality protects linework. Two-bone blending is concentrated
        # near the joints; this is a mesh test, not a finished segmented rig.
        weights = 1/np.maximum(d,.018)**3.5
        x,y = pixels[:,0],pixels[:,1]
        # Head/crown must remain a rigid card rather than stretch toward arms.
        head = np.clip((455-y)/85,0,1)
        # Torso owns the central upper garment.
        torso = (np.clip((y-410)/60,0,1)*np.clip((845-y)/80,0,1)*
                 np.clip((160-np.abs(x-512))/65,0,1))
        # Arms cannot drag the lower robe or vice versa.
        arm_fade = np.clip((960-y)/120,0,1)
        if self.name == 'fan':
            # Keep the whole fan rigid without a rectangular hard seam.
            left_fan = np.clip((320-x)/65,0,1)*np.clip((y-780)/75,0,1)*np.clip((1100-y)/80,0,1)
            right_fan = np.clip((x-704)/65,0,1)*np.clip((y-780)/75,0,1)*np.clip((1100-y)/80,0,1)
            arm_fade = np.maximum(arm_fade,np.maximum(left_fan,right_fan))
        weights[:,2:8] *= arm_fade[:,None]
        weights[:,8:14] *= np.clip((y-740)/100,0,1)[:,None]
        weights[:,:2] *= np.clip((1000-y)/150,0,1)[:,None]
        # Keep four smooth influences; abrupt per-vertex ownership creates
        # needle-shaped triangles when a sleeve rises past the torso.
        indices = np.argsort(weights,axis=1)[:,:-4]
        np.put_along_axis(weights,indices,0,axis=1)
        weights /= weights.sum(axis=1,keepdims=True)
        weights *= (1-torso)[:,None]
        weights[:,0] += torso
        weights *= (1-head)[:,None]
        weights[:,1] += head
        if self.name == 'fan':
            for mask,bone in [(left_fan,4),(right_fan,7)]:
                weights *= (1-mask)[:,None]
                weights[:,bone] += mask
        return weights

    def deform(self, source_angles, root_offset=(0,0), strength=1.0):
        if not 0 <= strength <= 1.5:
            raise ValueError('Motion strength must be between 0 and 1.5')
        target = np.asarray(source_angles,dtype=float).copy()
        if target.shape != self.rest_angles.shape or not np.all(np.isfinite(target)):
            raise ValueError('Invalid bone angles')
        # Tracker sees wrists/ankles, not prop orientation / foot roll.
        for child,parent in [(4,3),(7,6),(10,9),(13,12)]:
            target[child] += self.rest_angles[child]-self.rest_angles[parent]
        delta = short_angle(target-self.rest_angles)*strength
        # A backward head tilt in the footage is not a 90-degree flat-card roll.
        # Cap relative tilt for this front-facing approximation, explicitly not
        # claiming reconstruction of the unseen face/back of the head.
        delta[1] = delta[0]+np.clip(short_angle(delta[1]-delta[0]),-.65,.65)
        posed_angles = self.rest_angles+delta
        roots = {'root':np.asarray(root_offset,dtype=float)}
        matrices = []
        for i,(a,b) in enumerate(BONES):
            if a not in roots:
                roots[a] = roots['root']+rotation(delta[0])@self.rest[a]
            r = rotation(delta[i])
            matrices.append((r,roots[a]-r@self.rest[a]))
            roots[b] = roots[a]+self.lengths[i]*np.array([np.cos(posed_angles[i]),np.sin(posed_angles[i])])
        out = np.zeros_like(self.vertices)
        for i,(matrix,translation) in enumerate(matrices):
            out += (self.vertices@matrix.T+translation)*self.weights[:,i,None]
        return out, roots

    def tracked_scale(self, points):
        """Stable thickness scale, independent of a single foreshortened frame."""
        p = np.asarray(points)
        hips = (p[:,23]+p[:,24])*.5
        neck = (p[:,11]+p[:,12])*.5
        torso = np.linalg.norm(neck-hips,axis=1)
        legs = .5*(np.linalg.norm(p[:,24]-p[:,26],axis=1)+np.linalg.norm(p[:,26]-p[:,28],axis=1)+
                    np.linalg.norm(p[:,23]-p[:,25],axis=1)+np.linalg.norm(p[:,25]-p[:,27],axis=1))
        drawn = self.lengths[0]+.5*(sum(self.lengths[8:10])+sum(self.lengths[11:13]))
        return max(float(np.median(torso+legs)/drawn),.01)

    def deform_tracked(self, points, scale, head_roll=0.):
        """Fit the projected joints in ONE shared video coordinate system.

        Longitudinal bone scaling preserves foreshortening; a smooth residual
        field pins calibrated mesh joints after skin blending. This is still a
        deforming drawing, not depth recovery or a clothing simulation.
        """
        p = np.asarray(points,dtype=float)
        if not self.match_joints:
            raise ValueError('Construct Puppet with match_joints=True')
        if p.shape != (33,2) or not np.all(np.isfinite(p)) or not np.isfinite(scale) or scale<=0:
            raise ValueError('Invalid tracked pose or scale')
        if not np.isfinite(head_roll):
            raise ValueError('Invalid head roll')
        target = {name:p[j].copy() for name,j in OBSERVED_JOINTS.items()}
        target['root'] = (p[23]+p[24])*.5
        target['neck'] = (p[11]+p[12])*.5
        # The 17-point detector has no hands / toes: conservatively attach the
        # drawn props and feet to the wrist / ankle, without claiming capture.
        for parent,child,previous in [('rw','rh','re'),('lw','lh','le'),
                                      ('ra','rf','rk'),('la','lf','lk')]:
            rest_angle = np.arctan2(*(self.rest[parent]-self.rest[previous])[::-1])
            vector = target[parent]-target[previous]
            angle = np.arctan2(vector[1],vector[0])-rest_angle if np.linalg.norm(vector)>1e-8 else 0.
            target[child] = target[parent]+rotation(angle)@(self.rest[child]-self.rest[parent])*scale
        matrices = []
        for i,(a,b) in enumerate(BONES):
            rest_vector = self.rest[b]-self.rest[a]
            v = target[b]-target[a]
            if i==1:
                matrix = rotation(head_roll)*scale
                translation = target['head']-matrix@self.rest['head']
            else:
                rest_direction = rest_vector/self.lengths[i]
                rest_perp = np.array([-rest_direction[1],rest_direction[0]])
                length = np.linalg.norm(v)
                direction = v/length if length>1e-8 else rest_direction
                perp = np.array([-direction[1],direction[0]])
                width = scale
                if i==0:
                    # A side-on torso should narrow rather than keep a broad
                    # frontal chest and drag the arms away from their targets.
                    drawn_width = np.linalg.norm(self.rest['ls']-self.rest['rs'])
                    width = max(np.linalg.norm(p[11]-p[12])/drawn_width,scale*.2)
                matrix = np.outer(v/self.lengths[i],rest_direction)+np.outer(perp*width,rest_perp)
                translation = target[a]-matrix@self.rest[a]
            matrices.append((matrix,translation))
        def skin(vertices,weights):
            out = np.zeros_like(vertices)
            for i,(matrix,translation) in enumerate(matrices):
                out += (vertices@matrix.T+translation)*weights[:,i,None]
            return out
        controls = np.array([self.rest[k] for k in self.joint_names])
        desired = np.array([target[k] for k in self.joint_names])
        out = skin(self.vertices,self.weights)
        out += (self.correction@(desired-skin(controls,self.control_weights)))*(1-self.head_protection[:,None])
        return out,target


def head_rolls(points, smoothing_sigma=1.):
    """Face-axis roll, not neck-to-nose tilt; no invented back-facing head."""
    p = np.asarray(points,dtype=float)
    ears = p[:,7]-p[:,8]  # anatomical left ear minus right ear
    eyes = p[:,2]-p[:,5]
    # A turn-away can swap the projected ear order. Keep the front-facing card
    # upright instead of introducing an unsupported 180-degree face flip.
    ears = np.where((ears[:,0]<0)[:,None],-ears,ears)
    eyes = np.where((eyes[:,0]<0)[:,None],-eyes,eyes)
    # In profile, the projected ears nearly coincide and their tiny vertical
    # error becomes a huge false roll. Prefer the eye line in those frames.
    frontal = max(float(np.percentile(np.abs(ears[:,0]),80)),1e-6)
    ear_weight = np.clip((np.abs(ears[:,0])/frontal-.25)/.4,0,1)
    eye_valid = np.linalg.norm(eyes,axis=1)>1e-4
    ear_weight = np.where(eye_valid,ear_weight,1.)
    ears /= np.maximum(np.linalg.norm(ears,axis=1,keepdims=True),1e-8)
    eyes /= np.maximum(np.linalg.norm(eyes,axis=1,keepdims=True),1e-8)
    axis = ears*ear_weight[:,None]+eyes*(1-ear_weight[:,None])
    roll = np.clip(np.arctan2(axis[:,1],np.maximum(axis[:,0],1e-8)),-1.1,1.1)
    original = roll.copy()
    if smoothing_sigma>0:
        roll = gaussian_filter1d(roll,smoothing_sigma,mode='nearest')
        roll[0],roll[-1] = original[0],original[-1]
    return roll


def camera_transform(points, aspect, center=(0,0), half_height=1., zoom=1.):
    if aspect <= 0 or half_height <= 0 or zoom <= 0:
        raise ValueError('Invalid camera dimensions')
    return (np.asarray(points)-center)*zoom/[half_height*aspect,half_height]
