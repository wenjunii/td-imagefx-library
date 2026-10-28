"""Bounded-latency helpers; no camera or inference starts on import."""
import threading
import time
import numpy as np


def make_body(paths, settings, provider='cpu', gpu=0, profile_prefix=None):
    """Construct RTMLib with explicit local models and bounded execution."""
    import onnxruntime as ort
    from rtmlib import Body
    providers={'cpu':'CPUExecutionProvider','directml':'DmlExecutionProvider','cuda':'CUDAExecutionProvider'}
    if provider not in providers: raise ValueError('Unknown inference provider')
    if isinstance(gpu,bool) or int(gpu)!=gpu or gpu<0: raise ValueError('GPU index must be a nonnegative integer')
    expected=providers[provider]
    if expected not in ort.get_available_providers():
        raise ValueError(f'{expected} is not installed in this Python environment')
    if provider=='cuda':
        # CUDA/cuDNN are private pip dependencies, not installed into TD or
        # added to the machine PATH. Do not import torch just to locate DLLs.
        ort.preload_dlls(directory='')
    original=ort.InferenceSession
    def session(*args,**kwargs):
        options=ort.SessionOptions(); options.intra_op_num_threads=2; options.inter_op_num_threads=1
        if profile_prefix:
            options.enable_profiling=True; options.profile_file_prefix=str(profile_prefix)
        if provider=='directml':
            options.enable_mem_pattern=False
            options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            kwargs['providers']=[('DmlExecutionProvider',{'device_id':int(gpu)}),'CPUExecutionProvider']
            kwargs.pop('provider_options',None)
        elif provider=='cuda':
            kwargs['providers']=[('CUDAExecutionProvider',{'device_id':int(gpu)}),'CPUExecutionProvider']
            kwargs.pop('provider_options',None)
        else:
            kwargs['providers']=['CPUExecutionProvider']
            kwargs.pop('provider_options',None)
        kwargs['sess_options']=options
        result=original(*args,**kwargs)
        if result.get_providers()[0]!=expected:
            raise RuntimeError(f'Requested {expected} adapter {gpu} could not be initialized; CPU fallback rejected')
        # Reject runtime re-creation on CPU after a CUDA/DirectML execution
        # failure. Small CPU shape operations within a GPU session are normal.
        if provider!='cpu': result.disable_fallback()
        return result
    ort.InferenceSession=session
    try:
        return Body(det=str(paths['det']),det_input_size=settings['det_input_size'],pose=str(paths['pose']),
                    pose_input_size=settings['pose_input_size'],backend='onnxruntime',device='cpu',to_openpose=False)
    finally: ort.InferenceSession=original


class PoseTracker:
    """Refresh person detection regularly; track full-body crops in between."""
    def __init__(self, model, interval=4):
        self.model=model; self.interval=max(1,int(interval)); self.count=0; self.boxes=None

    def __call__(self, image):
        if self.boxes is None or self.count%self.interval==0:
            self.boxes=self.model.det_model(image)
        points,scores=self.model.pose_model(image,bboxes=self.boxes)
        self.count+=1
        boxes=[]; h,w=image.shape[:2]
        for p,s in zip(points,scores):
            good=p[s>.3]
            if len(good)<8: continue
            lo=good.min(axis=0); hi=good.max(axis=0)
            size=np.maximum(hi-lo,[30,60])
            lo=np.maximum([0,0],lo-size*[.25,.20])
            hi=np.minimum([w-1,h-1],hi+size*[.25,.20])
            boxes.append([*lo,*hi])
        # Re-detect immediately after a dropout, not after several stale crops.
        self.boxes=np.asarray(boxes,dtype=np.float32) if len(boxes)>=2 else None
        return points,scores


class LatestCapture:
    """Keep only the newest camera image so slow inference cannot queue latency."""
    def __init__(self, capture):
        self.capture=capture; self.lock=threading.Lock(); self.stop=threading.Event()
        self.frame=None; self.sequence=0; self.error=None
        self.thread=threading.Thread(target=self._read,daemon=True,name='puppet-camera')
        self.thread.start()

    def _read(self):
        try:
            while not self.stop.is_set():
                ok,frame=self.capture.read()
                if not ok: self.error='Camera frame unavailable'; return
                with self.lock: self.frame=frame; self.sequence+=1
        finally: self.capture.release()

    def read(self, after=0, timeout=3.):
        deadline=time.perf_counter()+timeout
        while time.perf_counter()<deadline and not self.stop.is_set():
            with self.lock:
                if self.sequence>after: return self.sequence,self.frame
            if self.error: raise RuntimeError(self.error)
            time.sleep(.001)
        raise RuntimeError('Camera did not supply a fresh frame')

    def close(self):
        self.stop.set(); self.thread.join(timeout=3.)
