"""Deterministic v5 rig regressions; visual quality is reviewed separately."""
import unittest

import numpy as np

from connected_puppet import neutral_pose
from fluid_puppet import FluidPuppet, smooth_angles, refine_rotations, stable_views, flex_joint
from layered_puppet import Part
from render_layered import pack
from test_layered import FakeAtlas


class FluidTests(unittest.TestCase):
    def setUp(self):
        self.p=np.repeat(neutral_pose(),120,axis=0)

    def test_angle_wrap_is_short_route(self):
        a=np.deg2rad(np.r_[np.linspace(170,179,40),np.linspace(-179,-170,40)])
        q=smooth_angles(a)
        self.assertLess(abs(np.diff(q)).max(),.06)

    def test_held_angle_stays_constant(self):
        np.testing.assert_allclose(smooth_angles(np.ones(30)*2.8),2.8)

    def test_angle_filter_keeps_peak_time(self):
        t=np.arange(101); q=smooth_angles(np.exp(-((t-50)/10)**2))
        self.assertEqual(int(q.argmax()),50)

    def test_ends_preserved(self):
        a=np.sin(np.arange(60)*.07)
        np.testing.assert_allclose(smooth_angles(a)[[0,-1]],a[[0,-1]])

    def test_zero_angle_filter_identity(self):
        a=np.linspace(-1,1,90)
        np.testing.assert_allclose(smooth_angles(a,seconds=0),a)

    def test_invalid_angles(self):
        for a in ([],[float('nan')],[[1,2]]):
            with self.assertRaises(ValueError): smooth_angles(a)
        with self.assertRaises(ValueError): smooth_angles([1,2],seconds=-1)

    def test_relative_refinement_keeps_lengths(self):
        self.p[:,13,0]+=.01*np.sin(np.arange(120)*.7)
        q=refine_rotations(self.p)
        for a,b in ((11,13),(13,15),(12,14),(14,16),(23,25),(25,27),(24,26),(26,28)):
            np.testing.assert_allclose(np.linalg.norm(q[:,b]-q[:,a],axis=1),np.linalg.norm(self.p[:,b]-self.p[:,a],axis=1),atol=1e-10)

    def test_refinement_keeps_mean_ankle_position(self):
        self.p[:,25,0]+=.01*np.sin(np.arange(120)*.7)
        q=refine_rotations(self.p)
        np.testing.assert_allclose(q[:,[27,28]].mean(axis=1),self.p[:,[27,28]].mean(axis=1),atol=1e-12)

    def test_no_mutation(self):
        p=self.p.copy(); refine_rotations(p)
        np.testing.assert_array_equal(p,self.p)

    def test_relative_refinement_translates_with_stage(self):
        d=np.array([.4,-.3])
        np.testing.assert_allclose(refine_rotations(self.p+d)-refine_rotations(self.p),np.broadcast_to(d,self.p.shape),atol=1e-12)

    def test_one_frame_view_excursion_removed(self):
        w=np.eye(5)[np.zeros(90,dtype=int)]; w[40]=np.eye(5)[1]
        np.testing.assert_array_equal(stable_views(w).argmax(axis=1),0)

    def test_sustained_turn_preserved(self):
        w=np.eye(5)[np.r_[np.zeros(45,dtype=int),np.ones(45,dtype=int)]]
        q=stable_views(w)
        self.assertEqual(q[20].argmax(),0); self.assertEqual(q[65].argmax(),1)
        np.testing.assert_allclose(q.sum(axis=1),1)
        self.assertTrue(np.all(q>=0))

    def test_flex_pins_joint_centers(self):
        xy=np.array([[0,0],[0,1],[.2,.2],[.2,.8]],float)
        part=Part('test',xy.copy(),np.zeros((4,2)),np.array([[0,1,2],[1,2,3]]))
        q=flex_joint(part,[0,0],[0,1],[1,0],[-1,0])
        np.testing.assert_allclose(q.xy[:2],xy[:2],atol=1e-10)
        self.assertGreater(np.max(abs(q.xy[2:]-xy[2:])),.001)

    def test_all_views_finite(self):
        for view in ('front','right','left','bow','back'):
            rig=FluidPuppet(FakeAtlas(),self.p,overrides=[dict(start=0,end=4,view=view)])
            self.assertTrue(np.isfinite(pack(rig.parts(30))).all())

    def test_unique_single_robe(self):
        parts=FluidPuppet(FakeAtlas(),self.p).parts(60)
        self.assertEqual(sum(p.name=='connected_robe' for p in parts),1)
        self.assertEqual(sum(p.name.endswith('_join') for p in parts),11)

    def test_refinement_keeps_prop_anchors(self):
        q=refine_rotations(self.p)
        np.testing.assert_array_equal(q[:,17],q[:,15])
        np.testing.assert_array_equal(q[:,18],q[:,16])


if __name__=='__main__': unittest.main()
