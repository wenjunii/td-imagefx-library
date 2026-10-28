"""Asset-independent regression tests for the v3 articulated rig."""
import unittest

import numpy as np

from layered_puppet import (Sprite, LayeredPuppet, NAMES, VIEWS, bone,
                            chain_curve, classify_views, cloth_panel, rigid)


class FakeAtlas:
    name = 'fan'
    def __getitem__(self, name):
        if name not in NAMES+('neck',):
            raise KeyError(name)
        return Sprite(name, np.array([0., 0., 1., 1.]), .8)


def pose():
    p = np.zeros((33, 2))
    p[0] = [.5, .83]
    p[7], p[8] = [.52, .83], [.48, .83]
    p[2], p[5] = [.51, .84], [.49, .84]
    p[11], p[12] = [.55, .75], [.45, .75]
    p[13], p[14] = [.59, .65], [.41, .65]
    p[15], p[16] = [.61, .56], [.39, .56]
    p[23], p[24] = [.54, .60], [.46, .60]
    p[25], p[26] = [.56, .43], [.44, .43]
    p[27], p[28] = [.57, .25], [.43, .25]
    return p


class LayeredTests(unittest.TestCase):
    def setUp(self):
        self.sprite = FakeAtlas()['robe']

    def test_rigid_card_keeps_shape(self):
        a = rigid(self.sprite, (.5,.5), [0,0], .2)
        b = rigid(self.sprite, (.5,.5), [2,3], .2, 1.2)
        np.testing.assert_allclose(np.linalg.norm(a.xy[:,None]-a.xy[None,:],axis=2),
                                   np.linalg.norm(b.xy[:,None]-b.xy[None,:],axis=2),atol=1e-12)

    def test_mirror_keeps_rigid_size(self):
        a=rigid(self.sprite,(.3,.4),[1,1],.2,mirror=False)
        b=rigid(self.sprite,(.3,.4),[1,1],.2,mirror=True)
        np.testing.assert_allclose(a.xy[:,0]-1,1-b.xy[:,0])
        np.testing.assert_allclose(a.xy[:,1],b.xy[:,1])

    def test_bone_anchors_match(self):
        # Top-left and bottom-left corners are calibrated anchors here.
        part=bone(self.sprite,(0,0),(0,1),[.2,.3],[.6,.1],.1)
        np.testing.assert_allclose(part.xy[[0,2]],[[.2,.3],[.6,.1]])

    def test_collapsed_limb_remains_finite(self):
        part=bone(self.sprite,(.5,.1),(.5,.8),[1,1],[1,1],.1)
        self.assertTrue(np.isfinite(part.xy).all())
        self.assertLess(np.ptp(part.xy,axis=0).max(),.2)

    def test_cloth_never_inverts_across_bends(self):
        for angle in np.linspace(-np.pi,np.pi,39):
            for length in (.0,.005,.05,.2):
                end=np.array([np.cos(angle),np.sin(angle)])*length
                for sway in (-10.,0.,10.):
                    part=cloth_panel(self.sprite,[0,0],end,.1,sway)
                    tri=part.xy[part.faces]
                    d1,d2=tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]
                    area=d1[:,0]*d2[:,1]-d1[:,1]*d2[:,0]
                    self.assertTrue(np.all(area>0))

    def test_cloth_attachment_stays_fixed(self):
        a=cloth_panel(self.sprite,[0,0],[0,-1],.1,-.02)
        b=cloth_panel(self.sprite,[0,0],[0,-1],.1,.02)
        np.testing.assert_allclose(a.xy[:5],b.xy[:5])
        np.testing.assert_allclose(a.xy[-5:],b.xy[-5:],atol=1e-12)
        self.assertGreater(np.max(abs(a.xy-b.xy)),.01)

    def test_chain_pins_both_wrists(self):
        curve=chain_curve([.3,.7],[.6,.8],.05)
        np.testing.assert_allclose(curve[[0,-1]],[[.3,.7],[.6,.8]])
        self.assertLess(curve[len(curve)//2,1],.75)

    def test_static_pose_has_exactly_one_view(self):
        points=np.repeat(pose()[None],50,axis=0)
        views=classify_views(points)
        np.testing.assert_array_equal(views.argmax(axis=1),np.zeros(50))
        np.testing.assert_allclose(views[:,0],1)

    def test_true_profile_selects_side(self):
        p=pose(); p[0,0]=.55; p[11,0]=.505; p[12,0]=.495
        views=classify_views(np.repeat(p[None],50,axis=0))
        self.assertTrue(np.all(views.argmax(axis=1)==VIEWS.index('right')))

    def test_deep_bow_selects_bow_not_zero_scale(self):
        p=pose(); points=np.repeat(p[None],120,axis=0)
        points[60:,11:13,1]=.63; points[60:,0,1]=.61
        views=classify_views(points)
        self.assertEqual(views[-1].argmax(),VIEWS.index('bow'))
        rig=LayeredPuppet(FakeAtlas(),points)
        self.assertTrue(all(np.isfinite(p.xy).all() for p in rig.parts(90)))

    def test_head_turn_does_not_turn_frontal_chest(self):
        p=pose(); p[0,0]=.56
        points=np.repeat(p[None],30,axis=0)
        self.assertEqual(classify_views(points)[-1].argmax(),VIEWS.index('right'))
        self.assertEqual(classify_views(points,body=True)[-1].argmax(),VIEWS.index('front'))

    def test_no_other_limb_can_drag_head(self):
        original=pose(); changed=original.copy()
        changed[[13,14,15,16,25,26,27,28]] += [.3,-.2]
        rig=LayeredPuppet(FakeAtlas(),np.array([original,changed]))
        a=next(p for p in rig.parts(0) if p.name=='head_front')
        b=next(p for p in rig.parts(1) if p.name=='head_front')
        np.testing.assert_allclose(a.xy,b.xy)

    def test_back_requires_missing_face_evidence(self):
        p=pose(); p[[11,12]]=p[[12,11]]
        points=np.repeat(p[None],20,axis=0)
        confidence=np.ones((20,33)); confidence[:,0]=0
        self.assertTrue(np.all(classify_views(points,confidence).argmax(axis=1)==4))
        self.assertTrue(np.all(classify_views(points).argmax(axis=1)!=4))

    def test_explicit_view_override(self):
        rig=LayeredPuppet(FakeAtlas(),np.repeat(pose()[None],90,axis=0),
                          overrides=[dict(start=1.,end=2.,view='left')])
        self.assertEqual(rig.views[45].argmax(),VIEWS.index('left'))
        self.assertEqual(rig.views[0].argmax(),VIEWS.index('front'))

    def test_parameter_bounds(self):
        points=np.repeat(pose()[None],10,axis=0)
        for value in (-.1,2.1):
            with self.assertRaises(ValueError):
                LayeredPuppet(FakeAtlas(),points,cloth_amount=value)
        with self.assertRaises(ValueError):
            cloth_panel(self.sprite,[0,0],[1,1],0)


if __name__=='__main__':
    unittest.main()
