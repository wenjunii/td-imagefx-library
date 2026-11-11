import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]


class PuppetGpuConfigTests(unittest.TestCase):
    def test_native_job_retains_cuda_device_and_renderer_requirement(self):
        spec=importlib.util.spec_from_file_location('puppet_gpu_runtime',ROOT/'touchdesigner/scripts/dance_puppet_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'prototypes/dance_puppet').mkdir(parents=True)
            (root/'prototypes/dance_puppet/service.py').touch()
            python=root/'worker.exe'; python.touch()
            profile=root/'profile.json'; profile.write_text('{}')
            settings={'python':str(python),'models':'models','ffmpeg':'ffmpeg','live_provider':'cuda','live_gpu':0,'render_gpu':'RTX 3080 Ti'}
            par=lambda v:SimpleNamespace(eval=lambda:v)
            component=SimpleNamespace(par=SimpleNamespace(Characterprofile=par(str(profile)),Dancevideo=par('dance.mp4'),
                Motioncache=par('motion.json'),Cameraindex=0,Livesmoothing=.08,Removecamera=True),
                fetch=lambda *a,**k:None,store=lambda *a:None,storeStartupValue=lambda *a:None)
            with patch.object(runtime,'root',return_value=root),patch.object(runtime,'local_settings',return_value=settings), \
                 patch.object(runtime.subprocess,'Popen') as spawn:
                runtime.start(component,'build',True)
            jobs=list((root/'.imagefx/puppet-jobs').iterdir())
            self.assertEqual(len(jobs),1)
            config=json.loads((jobs[0]/'config.json').read_text())
            self.assertEqual((config['provider'],config['gpu'],config['render_gpu']),('cuda',0,'RTX 3080 Ti'))
            self.assertTrue(config['analyze'])
            self.assertEqual(spawn.call_args.args[0][0],str(python))
            self.assertNotIn('shell',spawn.call_args.kwargs)

    def test_cuda_install_manifest_avoids_cpu_runtime_collision(self):
        text=(ROOT/'prototypes/dance_puppet/requirements-cuda.txt').read_text()
        packages=[line.strip() for line in text.splitlines() if line.strip() and not line.startswith('#')]
        self.assertTrue(any(line.startswith('onnxruntime-gpu[cuda,cudnn]==') for line in packages))
        self.assertFalse(any(line.startswith('onnxruntime==') for line in packages))
        self.assertFalse(any(line.startswith('rtmlib==') for line in packages))

    def test_launcher_targets_explicit_bus_without_closing_other_projects(self):
        text=(ROOT/'tools/start_imagefx_rtx.ps1').read_text()
        self.assertIn("'-gpubusid'",text)
        self.assertIn('nvidia-smi --query-gpu=name,pci.bus_id',text)
        self.assertNotIn('Stop-Process',text)
        self.assertNotIn('Disable-PnpDevice',text)
