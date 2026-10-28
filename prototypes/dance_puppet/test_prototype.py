"""Focused tests for the optional experiment, run in its separate venv."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from extract_motion import assign_tracks
from preview_controls import advance
from puppet import Motion, Puppet, OBSERVED_JOINTS, camera_transform, interpolate_confident, head_rolls


class PlaybackTests(unittest.TestCase):
    def test_pause(self):
        self.assertEqual(advance(2,.5,1,12,30,playing=False),(2,False))

    def test_disabled_freezes(self):
        self.assertEqual(advance(2,.5,1,12,30,enabled=False),(2,True))

    def test_speed(self):
        self.assertEqual(advance(2,.5,2,12,30),(3,True))

    def test_reverse(self):
        self.assertEqual(advance(2,.5,-1,12,30),(1.5,True))

    def test_stop_at_end(self):
        pos,playing=advance(11.8,1,1,12,30)
        self.assertAlmostEqual(pos,12-1/30)
        self.assertFalse(playing)

    def test_reverse_start(self):
        self.assertEqual(advance(.1,1,-1,12,30),(0,False))

    def test_loop(self):
        pos,playing=advance(11.9,.3,1,12,30,loop=True)
        self.assertAlmostEqual(pos,.2)
        self.assertTrue(playing)

    def test_invalid_value(self):
        with self.assertRaises(ValueError): advance(float('nan'),.1,1,12,30)
        with self.assertRaises(ValueError): advance(0,.1,1,0,30)

    def test_30fps_clip_loops_at_60fps(self):
        pos,_=advance(12-1/30,1/60,1,12,30,loop=True)
        self.assertAlmostEqual(pos,12-1/60)
        pos,_=advance(pos,1/60,1,12,30,loop=True)
        self.assertAlmostEqual(pos,0)


class RigTests(unittest.TestCase):
    def test_weight_partition(self):
        for name in ('fan','chain'):
            rig=Puppet(name)
            self.assertTrue(np.isfinite(rig.weights).all())
            np.testing.assert_allclose(rig.weights.sum(axis=1),1,atol=1e-12)
            self.assertTrue((rig.weights>=0).all())

    def test_zero_strength_preserves_art(self):
        for name in ('fan','chain'):
            rig=Puppet(name)
            result,_=rig.deform(np.zeros(14),strength=0)
            np.testing.assert_allclose(result,rig.vertices,atol=1e-12)

    def test_translation(self):
        rig=Puppet('fan')
        result,_=rig.deform(np.zeros(14),root_offset=(.2,.1),strength=0)
        np.testing.assert_allclose(result,rig.vertices+[.2,.1],atol=1e-12)

    def test_extreme_angles_finite(self):
        rig=Puppet('chain')
        for angle in (-np.pi,0,np.pi):
            result,_=rig.deform(np.repeat(angle,14),strength=1.5)
            self.assertTrue(np.isfinite(result).all())

    def test_camera_modes_share_geometry(self):
        points=np.array([[0.,0.],[.1,.2]])
        full=camera_transform(points,16/9,zoom=1)
        crop=camera_transform(points,16/9,zoom=1.45)
        np.testing.assert_allclose(crop,full*1.45)

    def test_camera_rejects_invalid_zoom(self):
        with self.assertRaises(ValueError): camera_transform([[0,0]],1,zoom=0)


class TrackingTests(unittest.TestCase):
    def test_missing_interpolation(self):
        values=np.array([[0.,0.],[np.nan,np.nan],[2.,4.]])
        filled=interpolate_confident(values,[True,False,True])
        np.testing.assert_allclose(filled[1],[1,2])

    def test_all_missing_rejected(self):
        with self.assertRaises(ValueError): interpolate_confident([[0,0]], [False])

    def test_persistent_slot_order(self):
        left=dict(center=[.3,.5]); right=dict(center=[.7,.5])
        self.assertEqual(assign_tracks([right,left],[left,right]),[left,right])

    def test_disappeared_track_not_duplicated(self):
        left=dict(center=[.3,.5]); right=dict(center=[.7,.5])
        result=assign_tracks([left],[left,right])
        self.assertEqual(result,[left,None])

    def test_bad_cache_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.json'
            path.write_text(json.dumps(dict(kind='not-motion',schema_version=1)),encoding='utf-8')
            with self.assertRaises(ValueError): Motion(path)


class PositionRetargetTests(unittest.TestCase):
    @staticmethod
    def pose(rig,offset=(.8,-.6),scale=.5):
        pose=np.zeros((33,2))
        for name,j in OBSERVED_JOINTS.items():
            pose[j]=rig.rest[name]*scale+offset
        pose[7]=pose[0]+[.018,0]; pose[8]=pose[0]-[.018,0]
        return pose

    def test_calibrated_joints_are_mesh_vertices(self):
        for name in ('fan','chain'):
            rig=Puppet(name,match_joints=True)
            expected=np.array([rig.rest[k] for k in rig.joint_names])
            np.testing.assert_allclose(rig.vertices[rig.joint_indices],expected,atol=1e-12)

    def test_projected_joints_fit_after_skinning(self):
        for name in ('fan','chain'):
            rig=Puppet(name,match_joints=True)
            p=self.pose(rig)
            p[14]+=[.05,.15]; p[16]+=[.11,.32]
            p[25]+=[-.12,.04]; p[0]+=[.08,-.12]
            out,target=rig.deform_tracked(p,.5,.3)
            np.testing.assert_allclose(out[rig.joint_indices],
                [target[k] for k in rig.joint_names],atol=1e-10)

    def test_shared_stage_preserves_relative_hip_spacing(self):
        rigs=[Puppet(n,match_joints=True) for n in ('fan','chain')]
        roots=[]; desired=[]
        for slot,rig in enumerate(rigs):
            p=self.pose(rig,offset=(.8+slot*.12,-.6+slot*.03))
            out,_=rig.deform_tracked(p,.5)
            roots.append(out[rig.joint_indices[rig.joint_names.index('root')]])
            desired.append((p[23]+p[24])*.5)
        np.testing.assert_allclose(roots[1]-roots[0],desired[1]-desired[0],atol=1e-12)

    def test_degenerate_projected_limb_is_finite(self):
        rig=Puppet('chain',match_joints=True); p=self.pose(rig)
        p[16]=p[14]; p[28]=p[26]
        out,_=rig.deform_tracked(p,.5)
        self.assertTrue(np.isfinite(out).all())

    def test_head_card_stays_rigid_during_bow(self):
        rig=Puppet('chain',match_joints=True); p=self.pose(rig)
        p[0]+=[.05,-.2]; p[11]+=[-.02,-.12]; p[12]+=[.02,-.12]
        out,_=rig.deform_tracked(p,.5,.6)
        ids=np.flatnonzero((rig.head_protection==1)&(rig.weights[:,1]>.999))
        pair=ids[[len(ids)//3,2*len(ids)//3]]
        self.assertAlmostEqual(np.linalg.norm(out[pair[0]]-out[pair[1]]),
            .5*np.linalg.norm(rig.vertices[pair[0]]-rig.vertices[pair[1]]),places=10)

    def test_front_facing_head_does_not_flip_on_ear_swap(self):
        p=np.zeros((3,33,2)); p[:,7]=[.1,.03]; p[:,8]=[-.1,-.03]
        p[1,7],p[1,8]=p[1,8].copy(),p[1,7].copy()
        np.testing.assert_allclose(head_rolls(p),np.repeat(np.arctan2(.06,.2),3))

    def test_profile_ear_collapse_uses_eye_line(self):
        p=np.zeros((5,33,2)); p[:,7]=[.025,0]; p[:,8]=[-.025,0]
        p[:,2]=[.01,0]; p[:,5]=[-.01,0]
        p[2,7]=[.001,.01]; p[2,8]=[-.001,-.01]
        self.assertAlmostEqual(float(head_rolls(p,smoothing_sigma=0)[2]),0.)

    def test_tracked_mode_rejects_invalid_input(self):
        rig=Puppet('fan',match_joints=True); p=self.pose(rig)
        with self.assertRaises(ValueError): rig.deform_tracked(p,0)
        with self.assertRaises(ValueError): rig.deform_tracked(p,.5,float('nan'))
        with self.assertRaises(ValueError): rig.deform_tracked(np.full((33,2),np.nan),.5)
        with self.assertRaises(ValueError): Puppet('fan').deform_tracked(p,.5)

    def test_smoothing_preserves_opening_pose(self):
        rig=Puppet('fan',match_joints=True); p=self.pose(rig)
        p[:,0]/=16/9; p[:,1]*=-1
        frames=[]
        for f in range(5):
            pose=np.column_stack([p+[f*.01,0],np.zeros(33),np.ones((33,2))]).tolist()
            frames.append(dict(time=f/30,poses=[pose,pose]))
        data=dict(kind='imagefx.dance-puppet.motion',schema_version=1,fps=30,
                  source_size=[1920,1080],frames=frames,detection_fraction=[1,1])
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'motion.json'; path.write_text(json.dumps(data),encoding='utf-8')
            motion=Motion(path,smoothing_seconds=.1)
            np.testing.assert_allclose(motion.sample_points(0),motion.observed_points[0])
            np.testing.assert_allclose(motion.sample_points(100,loop=False),motion.observed_points[-1])

    def test_source_camera_matches_normalized_video_position(self):
        world=np.array([[0,0],[16/9,-1],[8/9,-.5]])
        clip=camera_transform(world,16/9,center=(8/9,-.5),half_height=.5)
        np.testing.assert_allclose(clip,[[-1,1],[1,-1],[0,0]])


if __name__=='__main__': unittest.main()
