"""Asset-independent regression tests for v4. Visual approval is separate."""
import unittest
import numpy as np

from connected_puppet import (PROPORTIONS, ConnectedPuppet, clean_motion,
    neutral_pose, projected_vectors, retarget, robe_surface, torso_surface, joined_bone)
from layered_puppet import Sprite
from render_layered import pack
from test_layered import FakeAtlas


class ConnectedTests(unittest.TestCase):
    def setUp(self):
        self.p=np.repeat(neutral_pose(),90,axis=0)
        self.atlas=FakeAtlas()

    def test_no_source_mutation(self):
        before=self.p.copy()
        ConnectedPuppet(self.atlas,self.p)
        np.testing.assert_array_equal(self.p,before)

    def test_character_proportions_are_distinct(self):
        f,c=PROPORTIONS['fan'],PROPORTIONS['chain']
        self.assertGreater(f.torso+f.thigh+f.shin,c.torso+c.thigh+c.shin)
        self.assertGreater(c.shoulders,f.shoulders*1.4)
        self.assertGreater(c.torso_width,f.torso_width*1.4)

    def test_same_pose_retains_character_lengths(self):
        for name in ('fan','chain'):
            q=retarget(self.p,name,1)
            self.assertAlmostEqual(np.linalg.norm(q[30,13]-q[30,11]),PROPORTIONS[name].upper_arm)
            self.assertAlmostEqual(np.linalg.norm(q[30,27]-q[30,25]),PROPORTIONS[name].shin)

    def test_stable_pose_stays_still(self):
        q=retarget(clean_motion(self.p),'fan',1)
        np.testing.assert_allclose(q,np.broadcast_to(q[0],q.shape),atol=1e-12)

    def test_cleanup_zero_is_identity(self):
        np.testing.assert_array_equal(clean_motion(self.p,seconds=0),self.p)

    def test_cleanup_preserves_ends_and_frame_count(self):
        p=self.p.copy(); p[:,:,0]+=np.sin(np.arange(90)*.12)[:,None]*.03
        q=clean_motion(p)
        self.assertEqual(q.shape,p.shape)
        np.testing.assert_array_equal(q[[0,-1]],p[[0,-1]])

    def test_spike_rejection(self):
        p=self.p.copy(); p[40,15,0]+=.2
        q=clean_motion(p)
        self.assertLess(abs(q[40,15,0]-self.p[40,15,0]),.005)

    def test_symmetric_filter_does_not_delay_peak(self):
        t=np.arange(90); p=self.p.copy()
        p[:,:,0]+=np.exp(-((t-45)/10)**2)[:,None]*.10
        q=clean_motion(p)
        self.assertEqual(int(q[:,15,0].argmax()),45)

    def test_fast_motion_is_not_removed(self):
        p=self.p.copy(); p[:,:,0]+=(np.arange(90)*.004)[:,None]
        q=clean_motion(p)
        np.testing.assert_allclose(q[15:75],p[15:75],atol=.0001)

    def test_invalid_settings_rejected(self):
        for value in (-.1,.31,float('nan')):
            with self.assertRaises(ValueError): clean_motion(self.p,seconds=value)
        with self.assertRaises(ValueError): clean_motion(self.p,fps=0)
        with self.assertRaises(ValueError): clean_motion(self.p[:,:,:1])
        with self.assertRaises(ValueError): retarget(self.p,'unknown',1)
        with self.assertRaises(ValueError): retarget(self.p,'fan',0)

    def test_foreshortening_is_bounded(self):
        v=np.column_stack([np.linspace(0,1,90),np.zeros(90)])
        lengths=np.linalg.norm(projected_vectors(v,.1,30),axis=1)
        self.assertTrue(np.all(lengths<=.100001))
        self.assertTrue(np.all(lengths>=.039999))

    def test_collapsed_points_finite(self):
        q=retarget(np.zeros_like(self.p),'fan',1)
        self.assertTrue(np.isfinite(q).all())

    def test_stage_translation_preserved(self):
        shift=np.array([.42,-.17])
        a=retarget(self.p,'fan',1)
        b=retarget(self.p+shift,'fan',1)
        np.testing.assert_allclose(b-a,np.broadcast_to(shift,a.shape),atol=1e-12)

    def test_ankle_pair_stays_on_source_stage(self):
        q=retarget(self.p,'chain',1)
        np.testing.assert_allclose(q[:,[27,28]].mean(axis=1),self.p[:,[27,28]].mean(axis=1),atol=1e-12)

    def test_prop_slots_share_wrist(self):
        q=retarget(self.p,'fan',1)
        np.testing.assert_array_equal(q[:,17],q[:,15])
        np.testing.assert_array_equal(q[:,18],q[:,16])

    def test_one_connected_lower_robe(self):
        rig=ConnectedPuppet(self.atlas,self.p)
        parts=rig.parts(30)
        self.assertEqual([p.name for p in parts if 'robe' in p.name],['connected_robe'])
        self.assertEqual(len([p for p in parts if p.name.endswith('_join')]),11)

    def test_seam_underlays_have_visible_width(self):
        rig=ConnectedPuppet(self.atlas,self.p)
        for part in rig.parts(30):
            if part.name.endswith('_join'):
                self.assertTrue(np.isfinite(part.xy).all())
                self.assertGreater(float(np.ptp(part.xy,axis=0).max()),.004)

    def test_cloth_does_not_move_skeleton(self):
        p=self.p.copy(); p[:,:,0]+=np.sin(np.arange(90)*.1)[:,None]*.02
        a=ConnectedPuppet(self.atlas,p,cloth_amount=0)
        b=ConnectedPuppet(self.atlas,p,cloth_amount=2)
        np.testing.assert_array_equal(a.points,b.points)
        self.assertGreater(np.max(abs(b.lag)),0)

    def test_joint_fades_pack_without_nan(self):
        s=Sprite('limb',np.array([0,0,1,1]),.8)
        p=joined_bone(s,(.5,.05),(.5,.7),[0,0],[0,-1],.2,'arm')
        a=pack([p])
        self.assertTrue(np.isfinite(a).all())
        self.assertEqual(a[:,4].min(),0)
        self.assertEqual(a[:,4].max(),1)

    def test_all_views_have_finite_geometry(self):
        for view in ('front','left','right','bow','back'):
            rig=ConnectedPuppet(self.atlas,self.p,overrides=[dict(start=0,end=3,view=view)])
            parts=rig.parts(30)
            self.assertTrue(np.isfinite(pack(parts)).all())
            self.assertIn('head_'+view,[p.name for p in parts])


if __name__=='__main__': unittest.main()
