import json
import math
import unittest
from touchdesigner.scripts import projection_polygon as p
from touchdesigner.scripts import projection_mapping as mapping


class PolygonTests(unittest.TestCase):
    triangle=[(.1,.1),(.9,.1),(.5,.9)]
    def state(self,points=(),closed=False):
        return dict(target=1,points=list(points),closed=closed,selected=-1,drag=-1,undo=[])

    def test_triangle_both_windings(self):
        for points in (self.triangle,self.triangle[::-1]):
            self.assertEqual(p.validate_points(points),points)

    def test_concave(self):
        points=[(0,0),(1,0),(1,1),(.5,.4),(0,1)]
        self.assertEqual(p.validate_points(points),points)

    def test_32_points(self):
        points=[(.5+.4*math.cos(i*math.tau/32),.5+.4*math.sin(i*math.tau/32)) for i in range(32)]
        self.assertEqual(len(p.validate_points(points)),32)

    def test_too_many(self):
        with self.assertRaises(ValueError):p.validate_points([(0,0)]*33)

    def test_empty_allowed_only_for_inactive_storage(self):
        self.assertEqual(p.decode_polygon('[]'),())
        with self.assertRaises(ValueError):p.validate_points([])

    def test_crossing_rejected(self):
        with self.assertRaises(ValueError):p.validate_points([(0,0),(1,1),(0,1),(1,0)])

    def test_repeated_vertices_rejected(self):
        with self.assertRaises(ValueError):p.validate_points(self.triangle+[self.triangle[0]])

    def test_collinear_rejected(self):
        with self.assertRaises(ValueError):p.validate_points([(0,0),(.5,.5),(1,1)])

    def test_touching_nonadjacent_edge_rejected(self):
        with self.assertRaises(ValueError):p.validate_points([(0,0),(1,0),(1,1),(.5,0),(0,1)])

    def test_adjacent_reversal_rejected(self):
        with self.assertRaises(ValueError):p.validate_points([(0,0),(1,0),(.5,0),(1,1),(0,1)])

    def test_invalid_coordinates(self):
        for v in (float('nan'),float('inf'),-.1,1.1,'0.5',True,None):
            with self.subTest(v=v),self.assertRaises(ValueError):p.validate_points([(0,0),(1,0),(v,.5)])

    def test_malformed_json(self):
        for value in ('{','{}','null','"x"','[1,2,3]',' '*8193):
            with self.subTest(value=value[:20]),self.assertRaises(ValueError):p.decode_polygon(value)

    def test_json_roundtrip(self):
        self.assertEqual(p.decode_polygon(json.dumps(self.triangle)),tuple(self.triangle))

    def test_vertex_packing(self):
        self.assertEqual([p.packed(self.triangle,1,a) for a in range(4)],[.1,.1,.9,.1])
        self.assertEqual([p.packed(self.triangle,2,a) for a in range(4)],[.5,.9,0,0])
        self.assertEqual(p.packed(self.triangle,0,0),3)

    def test_click_adds_point_without_mutating_prior(self):
        old=self.state();new=p.gesture(old,'down',.3,.2)
        self.assertEqual(old['points'],[])
        self.assertEqual(new['points'],[[.3,.2]])

    def test_drag_moves_existing_point(self):
        s=p.gesture(self.state(self.triangle,True),'down',.5,.9)
        s=p.gesture(s,'move',.4,.8);s=p.gesture(s,'up',.4,.8)
        self.assertEqual(s['points'][2],[.4,.8]);self.assertEqual(s['drag'],-1)

    def test_first_point_closes(self):
        s=p.gesture(self.state(self.triangle),'down',.1,.1)
        self.assertTrue(s['closed']);self.assertEqual(len(s['points']),3)

    def test_closed_edge_insert(self):
        s=p.gesture(self.state(self.triangle,True),'down',.5,.1)
        self.assertEqual(s['points'][1],[.5,.1]);self.assertEqual(len(s['points']),4)

    def test_closed_empty_click_no_change(self):
        s=self.state(self.triangle,True)
        self.assertEqual(p.gesture(s,'down',.95,.9),s)

    def test_drag_clamps_to_canvas(self):
        s=p.gesture(self.state(self.triangle,True),'down',.5,.9)
        self.assertEqual(p.gesture(s,'move',2,-1)['points'][2],[1,0])

    def test_undo_records_one_gesture_not_each_move(self):
        s=p.gesture(self.state(self.triangle,True),'down',.5,.9)
        for i in range(10):s=p.gesture(s,'move',.5,.8+i*.005)
        self.assertEqual(len(s['undo']),1)

    def test_maximum_blocks_new_points(self):
        s=self.state([(.1,.1)]*32)
        self.assertEqual(len(p.gesture(s,'down',.8,.8)['points']),32)

    def test_polygon_fail_closed_before_inversion(self):
        self.assertLess(mapping.SHADER_MASK.index('if(uPolygon.x<3.)return 0.'),mapping.SHADER_MASK.index('if(uMask.z>.5)'))

    def test_shader_uses_output_frame_for_custom_polygon(self):
        self.assertIn('vUV.st-uMaskpose.xy',mapping.SHADER_MASK)
        self.assertIn('polygonDistance',mapping.POLYGON_SHADER)


if __name__=='__main__':unittest.main()
