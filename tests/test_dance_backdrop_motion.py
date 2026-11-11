"""Optional-NumPy tests for the TD-native motion math (no private fixtures)."""
import importlib.util
import json
from pathlib import Path
import unittest

try:
    import numpy as np
except ImportError:
    np = None

ROOT = Path(__file__).resolve().parents[1]
if np is not None:
    spec = importlib.util.spec_from_file_location('dance_backdrop_motion',ROOT/'touchdesigner/scripts/dance_backdrop_motion.py')
    motion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(motion)


@unittest.skipIf(np is None, 'NumPy is supplied by TouchDesigner; not a package-core dependency')
class MotionTests(unittest.TestCase):
    def document(self):
        data = np.zeros((30,2,6,3))
        data[...,:2] = .5
        data[...,2] = .9
        data[:,0,:,0] += np.arange(30)[:,None] * .005
        data[:,1,:,1] -= np.arange(30)[:,None] * .003
        return dict(schema_version=1,kind=motion.KIND,fps=30,frames=data.tolist())

    def test_metadata_and_fractional_interpolation(self):
        clip = motion.MotionClip(self.document())
        p,d,v,w = clip.sample(.15,smoothing=0)
        self.assertEqual(clip.duration,1.)
        self.assertAlmostEqual(p[0,0,0],.5225)
        self.assertAlmostEqual(d[1,0,1],.0135)
        self.assertAlmostEqual(v[0,0,0],.15)
        self.assertEqual(w.shape,(2,6))

    def test_neutral_pose_preserves_zero_position_displacement(self):
        clip = motion.MotionClip(self.document())
        _,d,_,_ = clip.sample(.4,reference=.4)
        np.testing.assert_array_equal(d,0.)

    def test_missing_people_fail_to_zero_influence(self):
        doc = self.document()
        data = np.asarray(doc['frames'])
        data[:,1,:,2] = 0
        doc['frames'] = data.tolist()
        vec,energy = motion.vectors(motion.MotionClip(doc),.4)
        np.testing.assert_array_equal(vec[6:,2:],0.)
        self.assertEqual(energy[1],0.)

    def test_person_weights_independent(self):
        clip = motion.MotionClip(self.document())
        vec,energy = motion.vectors(clip,.4,dancer1=0)
        np.testing.assert_array_equal(vec[:6,2:],0.)
        self.assertGreater(np.linalg.norm(vec[6:,2:]),0.)
        self.assertEqual(energy[0],0.)

    def test_mapping_mirrors_x_but_not_y(self):
        clip = motion.MotionClip(self.document())
        a,_ = motion.vectors(clip,.4)
        b,_ = motion.vectors(clip,.4,mirror=True)
        np.testing.assert_allclose(a[:,0],1-b[:,0])
        np.testing.assert_allclose(a[:,2],-b[:,2])
        np.testing.assert_allclose(a[:,[1,3]],b[:,[1,3]])

    def test_hand_and_foot_weights(self):
        vec,_ = motion.vectors(motion.MotionClip(self.document()),.4,hands=0,feet=0)
        np.testing.assert_array_equal(vec[[2,3,4,5,8,9,10,11],2:],0.)
        self.assertGreater(np.linalg.norm(vec[[0,1,6,7],2:]),0.)

    def test_bounded_force_and_energy(self):
        vec,energy = motion.vectors(motion.MotionClip(self.document()),.8,stagezoom=4,
                                    posegain=3,velocitygain=1,dancer1=2,dancer2=2)
        self.assertLessEqual(np.linalg.norm(vec[:,2:],axis=1).max(),.28000001)
        self.assertTrue(np.all((energy>=0)&(energy<=1)))

    def test_smoothing_reduces_jitter_and_is_seek_deterministic(self):
        doc = self.document()
        data = np.asarray(doc['frames'])
        data[:,0,2,0] += np.where(np.arange(30)%2, .05,-.05)
        doc['frames'] = data.tolist()
        clip = motion.MotionClip(doc)
        raw = clip.sample(.5,smoothing=0)[0]
        smooth = clip.sample(.5,smoothing=.2)[0]
        self.assertLess(abs(smooth[0,2,0]-.575),abs(raw[0,2,0]-.575))
        clip.sample(.2)
        np.testing.assert_array_equal(smooth,clip.sample(.5,smoothing=.2)[0])

    def test_rejects_nonfinite_and_malformed_caches(self):
        for key,value in [('fps',0),('fps',float('nan')),('kind','invalid'),('frames',[])]:
            doc=self.document(); doc[key]=value
            with self.assertRaises(ValueError): motion.MotionClip(doc)
        doc=self.document(); doc['frames'][0][0][0][0]=float('inf')
        with self.assertRaises(ValueError): motion.MotionClip(doc)

    def test_confidence_gate_and_bad_settings(self):
        clip=motion.MotionClip(self.document())
        v,e=motion.vectors(clip,.3,confidence=1.)
        np.testing.assert_array_equal(v[:,2:],0.)
        for kw in ({'smoothing':-1},{'confidence':2}):
            with self.assertRaises(ValueError): clip.sample(.2,**kw)

    def test_pause_reverse_speed_zero_and_boundaries(self):
        self.assertEqual(motion.advance(.5,.1,1,1,30,playing=False),(.5,False))
        self.assertEqual(motion.advance(.5,.1,0,1,30),(.5,True))
        self.assertAlmostEqual(motion.advance(.5,.1,-1,1,30)[0],.4)
        self.assertEqual(motion.advance(.95,.1,1,1,30),(1-1/30,False))
        self.assertEqual(motion.advance(.01,.1,-1,1,30),(0.,False))

    def test_loop_preserves_subframe_phase(self):
        pos=.96
        for _ in range(5): pos,playing=motion.advance(pos,1/120,1,1,30,loop=True)
        self.assertLess(pos,.02)
        self.assertTrue(playing)
        self.assertAlmostEqual(motion.advance(.01,.1,-1,1,30,loop=True)[0],.91)

    def test_conversion_uses_observations_and_clamps_detector_scores(self):
        pose=[[.4,.6,0.,1.2,1.2] for _ in range(33)]
        doc=dict(kind='imagefx.dance-puppet.motion',schema_version=1,fps=30,
                 source_size=[1920,1080],frames=[dict(poses=[pose,None])]*2)
        converted=motion.convert_observations(doc)
        self.assertEqual(converted['frames'][0][0][0],[.4,.6,1.])
        self.assertEqual(converted['frames'][0][1][0],[.5,.5,0.])

    def test_cache_roundtrip_without_pickle(self):
        doc=json.loads(json.dumps(self.document(),allow_nan=False))
        self.assertEqual(motion.MotionClip(doc).raw.shape,(30,2,6,3))


if __name__ == '__main__':
    unittest.main()
