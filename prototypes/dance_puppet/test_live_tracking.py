import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import numpy as np
from live_tracking import PoseTracker, make_body
from connected_puppet import grid_faces


class LiveTrackingTests(unittest.TestCase):
    def fake_runtime(self, providers, actual):
        session=Mock(); session.get_providers.return_value=actual
        ort=SimpleNamespace(get_available_providers=lambda:providers,preload_dlls=Mock(),
            SessionOptions=SimpleNamespace,InferenceSession=Mock(return_value=session),
            ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=1))
        body=Mock(side_effect=lambda **kw: ort.InferenceSession('model',providers=['CPUExecutionProvider']))
        return ort,body,session

    def test_cuda_loads_private_dlls_and_selects_device(self):
        ort,body,session=self.fake_runtime(['CUDAExecutionProvider'],['CUDAExecutionProvider','CPUExecutionProvider'])
        original=ort.InferenceSession
        with patch.dict('sys.modules',{'onnxruntime':ort,'rtmlib':SimpleNamespace(Body=body)}):
            make_body({'det':'d','pose':'p'},{'det_input_size':(640,640),'pose_input_size':(192,256)},'cuda',0)
        ort.preload_dlls.assert_called_once_with(directory='')
        self.assertEqual(original.call_args.kwargs['providers'][0],('CUDAExecutionProvider',{'device_id':0}))
        session.disable_fallback.assert_called_once()
        self.assertIs(ort.InferenceSession,original)

    def test_cuda_rejects_silent_cpu_fallback_and_restores_factory(self):
        ort,body,session=self.fake_runtime(['CUDAExecutionProvider'],['CPUExecutionProvider'])
        original=ort.InferenceSession
        with patch.dict('sys.modules',{'onnxruntime':ort,'rtmlib':SimpleNamespace(Body=body)}):
            with self.assertRaisesRegex(RuntimeError,'CPU fallback rejected'):
                make_body({'det':'d','pose':'p'},{'det_input_size':(640,640),'pose_input_size':(192,256)},'cuda',0)
        self.assertIs(ort.InferenceSession,original)

    def test_missing_cuda_does_not_attempt_cpu(self):
        ort,body,session=self.fake_runtime(['CPUExecutionProvider'],['CPUExecutionProvider'])
        with patch.dict('sys.modules',{'onnxruntime':ort,'rtmlib':SimpleNamespace(Body=body)}):
            with self.assertRaisesRegex(ValueError,'not installed'): make_body({}, {}, 'cuda',0)
        ort.InferenceSession.assert_not_called()

    def test_directml_keeps_explicit_adapter_and_sequential_execution(self):
        ort,body,session=self.fake_runtime(['DmlExecutionProvider'],['DmlExecutionProvider','CPUExecutionProvider'])
        original=ort.InferenceSession
        with patch.dict('sys.modules',{'onnxruntime':ort,'rtmlib':SimpleNamespace(Body=body)}):
            make_body({'det':'d','pose':'p'},{'det_input_size':(640,640),'pose_input_size':(192,256)},'directml',1)
        self.assertEqual(original.call_args.kwargs['providers'][0],('DmlExecutionProvider',{'device_id':1}))
        self.assertFalse(original.call_args.kwargs['sess_options'].enable_mem_pattern)
        ort.preload_dlls.assert_not_called()

    def test_reuses_crops_and_refreshes_detector(self):
        model=Mock()
        model.det_model.return_value=np.array([[10,10,90,90],[110,10,190,90]],dtype=np.float32)
        points=np.stack([np.linspace([20,20],[80,80],17),np.linspace([120,20],[180,80],17)])
        model.pose_model.return_value=(points,np.ones((2,17)))
        tracker=PoseTracker(model,4)
        for _ in range(8): tracker(np.zeros((100,200,3),dtype=np.uint8))
        self.assertEqual(model.det_model.call_count,2)
        self.assertEqual(model.pose_model.call_count,8)
        self.assertTrue(np.all(tracker.boxes[:,[0,2]]>=0))
        self.assertTrue(np.all(tracker.boxes[:,[0,2]]<200))

    def test_dropout_triggers_redetection(self):
        model=Mock(); model.det_model.return_value=np.zeros((2,4))
        model.pose_model.return_value=(np.zeros((2,17,2)),np.zeros((2,17)))
        tracker=PoseTracker(model,4)
        for _ in range(3): tracker(np.zeros((100,200,3),dtype=np.uint8))
        self.assertEqual(model.det_model.call_count,3)
        self.assertIsNone(tracker.boxes)

    def test_cached_mesh_indices_are_immutable(self):
        a=grid_faces(21,7)
        self.assertIs(a,grid_faces(21,7))
        self.assertFalse(a.flags.writeable)
        self.assertEqual(a.shape,(240,3))
