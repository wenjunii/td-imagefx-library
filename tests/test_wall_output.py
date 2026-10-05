"""Portable checks for the wall coordinate contract and display safety gate."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'touchdesigner/scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wall=load('wall_output')
controller=load('wall_output_controller')


class WallOutputTests(unittest.TestCase):
    def test_quadrant_centres_follow_processor_scan_order(self):
        self.assertEqual([wall.quadrant_at(x,y) for x,y in ((960,540),(2880,540),(960,1620),(2880,1620))],[1,2,3,4])

    def test_edges_have_no_gutter_or_overlap(self):
        self.assertEqual([wall.quadrant_at(x,y) for x,y in ((0,0),(1919,1079),(1920,1079),(1919,1080),(1920,1080),(3839,2159))],[1,1,2,3,4,4])

    def test_outside_pixels_rejected(self):
        for point in ((-1,0),(0,-1),(3840,0),(0,2160)):
            with self.assertRaises(ValueError): wall.quadrant_at(*point)

    def test_unassigned_or_disconnected_display_blocked(self):
        self.assertTrue(controller.display_problem(-1,[]))
        self.assertTrue(controller.display_problem(3,[dict(index=1,width=3840,height=2160,primary=False)]))

    def test_non_uhd_display_blocked_even_with_primary_override(self):
        for w,h in ((1920,1080),(4096,2160),(3840,1080),(2160,3840)):
            self.assertTrue(controller.display_problem(0,[dict(index=0,width=w,height=h,primary=True)],True))

    def test_primary_is_protected_and_override_is_explicit(self):
        displays=[dict(index=0,width=3840,height=2160,primary=True)]
        self.assertTrue(controller.display_problem(0,displays))
        self.assertEqual(controller.display_problem(0,displays,True),'')

    def test_valid_processor_display_accepted(self):
        self.assertEqual(controller.display_problem(1,[dict(index=1,width=3840,height=2160,primary=False)]),'')

    def test_modes_include_show_and_all_three_content_mappings(self):
        self.assertEqual(wall.SOURCE_MODES,('show','identical','panoramic','independent'))
