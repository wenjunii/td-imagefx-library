import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np

from integration import LiveScene, Renderer, load_profile, with_proportions
from connected_puppet import PROPORTIONS


class IntegrationTests(unittest.TestCase):
    def test_wrong_graphics_adapter_rejected_before_allocating_buffers(self):
        context=Mock(); context.info={'GL_RENDERER':'Intel Iris Xe'}
        with patch('moderngl.create_standalone_context',return_value=context):
            with self.assertRaisesRegex(RuntimeError,'expected RTX 3080 Ti'):
                Renderer([],16,16,'RTX 3080 Ti')
        context.release.assert_called_once()
        context.simple_framebuffer.assert_not_called()

    def test_scoped_proportions_restore_after_exception(self):
        from types import SimpleNamespace
        atlas=SimpleNamespace(name='fan',profile_proportions=PROPORTIONS['chain'])
        original=PROPORTIONS['fan']
        with self.assertRaises(RuntimeError):
            with_proportions(atlas,lambda: (_ for _ in ()).throw(RuntimeError()))
        self.assertIs(PROPORTIONS['fan'],original)

    def test_reject_unrecognized_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json'; path.write_text('{}')
            with self.assertRaises(ValueError): load_profile(path)

    def test_live_does_not_invent_a_pose_without_two_dancers(self):
        scene=LiveScene.__new__(LiveScene)
        scene.atlases=[None,None]; scene.aspect=16/9; scene.smoothing=.08
        scene.lost_hold=.5; scene.last=[None,None]; scene.seen=[None,None]
        scene.time=None; scene.history=[[],[]]; scene.scale=None
        packed,opacity=scene.update([None,None],0)
        self.assertEqual(opacity,[0,0]); self.assertTrue(all(np.all(p==0) for p in packed))
