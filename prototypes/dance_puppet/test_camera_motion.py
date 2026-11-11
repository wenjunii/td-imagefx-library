import unittest
import cv2
import numpy as np
from camera_motion import BackgroundCamera, transform_pose


class CameraMotionTests(unittest.TestCase):
    def test_inverse_keeps_choreography(self):
        camera=np.array([[1.1,0,30],[0,1.1,-12],[0,0,1.]])
        pose=[[.3,.4,0,1,1],[.4,.7,0,1,1]]
        observed=np.asarray(pose,float)
        observed[:,:2]=(observed[:,:2]*[640,360]@camera[:2,:2].T+camera[:2,2])/[640,360]
        np.testing.assert_allclose(transform_pose(observed,camera,(640,360)),pose,atol=1e-12)
        self.assertIsNone(transform_pose(None,camera,(640,360)))

    def test_static_background_not_moving_foreground(self):
        rng=np.random.default_rng(12)
        frame=cv2.GaussianBlur(rng.integers(0,255,(360,640,3),dtype=np.uint8),(3,3),0)
        tracker=BackgroundCamera()
        pose=[[.4,.3,0,1,1],[.6,.8,0,1,1]]
        tracker.update(frame,[pose])
        for step in range(1,20):
            camera=np.array([[1,0,step*.4],[0,1,step*.2]],np.float32)
            image=cv2.warpAffine(frame,camera,(640,360))
            cv2.rectangle(image,(240+step,100),(365+step,285),(255,0,0),-1)
            transform=tracker.update(image,[pose])
        np.testing.assert_allclose(transform[:2,2],[7.6,3.8],atol=.4)
        self.assertGreater(tracker.accepted/tracker.frames,.9)

    def test_featureless_background_holds_camera(self):
        tracker=BackgroundCamera()
        for _ in range(3):
            transform=tracker.update(np.zeros((120,200,3),np.uint8),[])
        np.testing.assert_array_equal(transform,np.eye(3))
        self.assertFalse(tracker.last_quality['accepted'])
