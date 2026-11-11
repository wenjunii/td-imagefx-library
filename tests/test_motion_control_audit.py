from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MotionControlAuditTests(unittest.TestCase):
    def test_motion_inventory_is_part_of_full_native_audit(self):
        suite = runpy.run_path(str(ROOT/'touchdesigner/scripts/validate_live_suite.py'))
        self.assertIn(('motion_controls', 'validate_motion_controls.py'), suite['VALIDATORS'])

    def test_saved_motion_roots_follow_relocated_project(self):
        for filename, key in (('dance_puppet_runtime.py','imagefx_puppet_root'),
                              ('dance_forces_runtime.py','imagefx_dance_forces_root')):
            with self.subTest(filename=filename):
                scope = runpy.run_path(str(ROOT/'touchdesigner/scripts'/filename),
                                      init_globals={'project':SimpleNamespace(folder=str(ROOT))})
                component = SimpleNamespace(fetch=lambda *a,**k:'')
                self.assertEqual(scope['root'](component), ROOT.resolve())
                component.fetch = lambda *a,**k:str(ROOT/'tests')
                self.assertEqual(scope['root'](component), (ROOT/'tests').resolve())

    def test_builders_clear_machine_local_root_at_startup(self):
        for filename, key, owner in (('dance_puppet.py','imagefx_puppet_root','c'),
                                     ('dance_forces.py','imagefx_dance_forces_root','component')):
            source = (ROOT/'touchdesigner/scripts'/filename).read_text(encoding='utf-8')
            self.assertIn(owner+".storeStartupValue('"+key+"', '')", source)

    def test_motion_audit_does_not_launch_analysis_or_camera(self):
        source = (ROOT/'touchdesigner/scripts/validate_motion_controls.py').read_text(encoding='utf-8')
        self.assertNotIn('.pulse()', source)
        self.assertNotIn('subprocess', source)
        self.assertIn('complete_inventory', source)
        self.assertIn('wiring_only_buttons', source)

    def test_clean_show_and_independent_racks_follow_project_folder(self):
        show = (ROOT/'touchdesigner/scripts/build_show_control.py').read_text(encoding='utf-8')
        composition = (ROOT/'touchdesigner/scripts/image_composition.py').read_text(encoding='utf-8')
        self.assertIn("show.par.Libraryroot.expr = 'project.folder'", show)
        self.assertIn('".imagefx/shows/current.json"', show)
        self.assertIn("child.par.Rootfolder=''", composition)
