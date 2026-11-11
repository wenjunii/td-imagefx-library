"""V5 rotation continuity, stable view transitions and bendable joint regions.

An offline 2D refinement, not invented 3D tracking. V4 remains reproducible.
"""
import copy

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter

from connected_puppet import ConnectedPuppet, LIMBS, PROPORTIONS
from layered_puppet import VIEWS, bone, rigid, unit


def smooth_angles(angles, fps=30., seconds=.065):
    """Unwrap before centered filtering; retain timing, ends and held poses."""
    a=np.asarray(angles,float)
    if a.ndim!=1 or not len(a) or not np.isfinite(a).all():
        raise ValueError('Expected a finite nonempty angle series')
    if not np.isfinite(fps+seconds) or fps<=0 or not 0<=seconds<=.25:
        raise ValueError('Invalid angle smoothing')
    a=np.unwrap(a)
    if len(a)<3 or seconds==0: return a.copy()
    med=median_filter(a,size=3,mode='nearest')
    # Only reject isolated angular spikes. Sustained turns remain observations.
    clean=np.where(abs(a-med)>.28,med,a)
    velocity=abs(np.gradient(clean)*fps)
    blend=1/(1+(velocity/3.)**2)
    fine=gaussian_filter1d(clean,max(.35,seconds*fps*.35),mode='nearest')
    broad=gaussian_filter1d(clean,max(.5,seconds*fps),mode='nearest')
    result=fine+(broad-fine)*blend
    # Bound the correction; this must not erase deliberate fast choreography.
    result=clean+np.clip(result-clean,-.16,.16)
    result[0],result[-1]=a[0],a[-1]
    return result


def refine_rotations(points,fps=30.,seconds=.065):
    """Filter relative joint angles, then rebuild one hierarchy with same lengths."""
    p=np.asarray(points,float)
    if p.ndim!=3 or p.shape[1:]!=(33,2) or not np.isfinite(p).all():
        raise ValueError('Expected finite time x 33 x 2 points')
    q=p.copy()
    torso=p[:,[11,12]].mean(axis=1)-p[:,[23,24]].mean(axis=1)
    trunk=np.unwrap(np.arctan2(torso[:,1],torso[:,0]))
    for _,(shoulder,elbow,wrist,hip,knee,ankle) in LIMBS.items():
        for root,mid,end in ((shoulder,elbow,wrist),(hip,knee,ankle)):
            upper=p[:,mid]-p[:,root]; lower=p[:,end]-p[:,mid]
            upper_a=np.unwrap(np.arctan2(upper[:,1],upper[:,0]))
            lower_a=np.unwrap(np.arctan2(lower[:,1],lower[:,0]))
            upper_new=trunk+smooth_angles(upper_a-trunk,fps,seconds)
            lower_new=upper_new+smooth_angles(lower_a-upper_a,fps,seconds*.85)
            for a,b,angle,v in ((root,mid,upper_new,upper),(mid,end,lower_new,lower)):
                q[:,b]=q[:,a]+np.column_stack([np.cos(angle),np.sin(angle)])*np.linalg.norm(v,axis=1)[:,None]
    # Do not pull feet away independently: translate the whole connected body.
    shift=(p[:,[27,28]]-q[:,[27,28]]).mean(axis=1)
    q+=shift[:,None,:]
    for dst,src in ((17,15),(19,15),(21,15),(18,16),(20,16),(22,16),
                    (29,27),(31,27),(30,28),(32,28)):
        q[:,dst]=q[:,src]
    return q


def stable_views(weights,fps=30.,hold=.16,transition=.10):
    """Reject short view excursions; ease transitions around their original time.

    Full turns survive. No causal wait is added to the rendered choreography.
    """
    w=np.asarray(weights,float)
    if w.ndim!=2 or w.shape[1]!=5 or not len(w) or not np.isfinite(w).all():
        raise ValueError('Expected finite time x 5 view weights')
    if fps<=0 or min(hold,transition)<0 or not np.isfinite(fps+hold+transition):
        raise ValueError('Invalid view timing')
    labels=w.argmax(axis=1)
    minimum=max(1,round(hold*fps))
    # Fill only short interior excursions, never erase an opening/closing pose.
    edges=np.r_[0,np.flatnonzero(np.diff(labels))+1,len(labels)]
    for a,b in zip(edges[:-1],edges[1:]):
        if a>0 and b<len(labels) and b-a<minimum and labels[a-1]==labels[b]:
            labels[a:b]=labels[a-1]
    result=np.eye(5)[labels]
    radius=max(1,round(transition*fps*.5))
    for boundary in np.flatnonzero(np.diff(labels))+1:
        lo=max(0,boundary-radius); hi=min(len(labels),boundary+radius+1)
        x=np.linspace(0,1,hi-lo); t=x*x*(3-2*x)
        result[lo:hi]=np.eye(5)[labels[boundary-1]]*(1-t[:,None])+np.eye(5)[labels[boundary]]*t[:,None]
    result[0],result[-1]=np.eye(5)[labels[0]],np.eye(5)[labels[-1]]
    return result


def flex_joint(part,start,end,incoming,outgoing,amount=.45):
    """Bend a subdivided limb locally, keeping both joint centers fixed."""
    start,end=np.asarray(start,float),np.asarray(end,float)
    axis=unit(end-start); normal=np.array([-axis[1],axis[0]])
    length=max(float(np.linalg.norm(end-start)),1e-6)
    relative=part.xy-start
    t=relative@axis/length; lateral=relative@normal
    angle=lambda v: float(np.clip(np.arctan2(axis[0]*v[1]-axis[1]*v[0],axis@v),-.65,.65))*amount
    d0,d1=angle(unit(incoming)),angle(unit(outgoing))
    ease=lambda x: (lambda u:u*u*(3-2*u))(np.clip(x,0,1))
    a=d0*(1-ease(t/.4))+d1*ease((t-.6)/.4)
    normals=normal*np.cos(a[:,None])-axis*np.sin(a[:,None])
    tc=np.clip(t,0,1)
    bend=length*.06*np.sin(np.pi*tc)*((1-tc)*np.sin(d0)-tc*np.sin(d1))
    part.xy=start+axis*(t*length)[:,None]+normal*bend[:,None]+normals*lateral[:,None]
    return part


class FluidPuppet(ConnectedPuppet):
    def __init__(self,*args,rotation_smoothing=.065,**kwargs):
        super().__init__(*args,**kwargs)
        self.v4_points=self.points.copy()
        self.points=refine_rotations(self.points,self.fps,rotation_smoothing)
        self.rotation_smoothing=rotation_smoothing
        self.original_views=self.views.copy(); self.original_body_views=self.body_views.copy()
        self.views=stable_views(self.views,self.fps)
        self.body_views=stable_views(self.body_views,self.fps)
        trunk=self.points[:,[11,12]].mean(axis=1)-self.points[:,[23,24]].mean(axis=1)
        lean=np.unwrap(np.arctan2(trunk[:,1],trunk[:,0]))-np.pi/2
        self.rolls=lean+smooth_angles(self.rolls-lean,self.fps,rotation_smoothing)

    def parts(self,frame):
        # Reuse v4 attachment calibration, then replace thresholded layer choices.
        items=super().parts(frame)
        by_name={part.name:part for part in items}
        p=self.points[frame]; w=self.body_views[frame]; hw=self.views[frame]
        c=PROPORTIONS[self.name]; s=self.scale; atlas=self.atlas
        neck=p[[11,12]].mean(axis=0)
        under=[part for part in items if part.name.endswith('_join')]
        legs=[]; arms=[]; overlays=[]
        for side,(shoulder,elbow,wrist,hip,knee,ankle) in LIMBS.items():
            for view,weight in (('front',1-w[1]-w[2]),('right',w[1]),('left',w[2])):
                if weight<1e-5: continue
                part=bone(atlas['shin_front' if view=='front' else 'shin_side'],(.5,.08),(.5,.82),
                          p[knee],p[ankle],c.shin_width*s,mirror=view=='left',name=side+'_shin_'+view)
                part.opacity=float(weight); legs.append(part)
            upper=flex_joint(by_name[side+'_sleeve'],p[shoulder],p[elbow],
                             p[shoulder]-neck,p[wrist]-p[elbow])
            fore=flex_joint(by_name[side+'_forearm'],p[elbow],p[wrist],
                            p[elbow]-p[shoulder],p[wrist]-p[elbow])
            arms.extend([upper,fore])
            front=copy.copy(fore)
            visibility=1-w[1 if side=='r' else 2]
            front.opacity=np.asarray(fore.opacity)*visibility
            front.name=side+'_forearm_front'
            overlays.append(front)
        # Fixed layer order, with continuous occlusion weights instead of a .5 switch.
        body=[part for part in items if part.name.startswith('torso_')]
        props=[part for part in items if part.name.endswith('_fan') or part.name.startswith('chain_')]
        heads=[]; head_base=neck+(p[0]-neck)*.64
        # All view cards share one roll while blending: no angle jump on a bow.
        angle=self.rolls[frame]*(1-.5*hw[3])
        for view,weight in zip(VIEWS,hw):
            if weight<1e-5: continue
            suffix='side' if view in ('right','left') else view
            anchor=(.67,.80) if suffix=='side' else (.5,.78 if suffix=='bow' else .79)
            heads.append(rigid(atlas['head_'+suffix],anchor,head_base,c.head*s,angle,
                               mirror=view=='left',opacity=float(weight),name='head_'+view))
        return under+legs+arms+[by_name['connected_robe']]+body+overlays+props+heads

    def report(self):
        result=super().report()
        count=lambda w:int(np.count_nonzero(np.diff(w.argmax(axis=1))))
        result.update(rotation_smoothing_seconds=self.rotation_smoothing,
                      view_changes=dict(head_before=count(self.original_views),head_after=count(self.views),
                                        body_before=count(self.original_body_views),body_after=count(self.body_views)),
                      refinement='Centered relative-angle filtering, eased view weights, continuous limb occlusion and local joint bending')
        return result
