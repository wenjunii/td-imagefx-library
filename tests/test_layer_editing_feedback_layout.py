import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


class MemoryComponent:
    def __init__(self):
        self.par=SimpleNamespace(Sourcemode='prepared',Time=0.,Duration=60.,
                                 Offset=0.,Loop=True,Feedbackenabled=True)
        self.storage={}
    def fetch(self,key,default=None,**kwargs): return self.storage.get(key,default)
    def store(self,key,value): self.storage[key]=value
    def storeStartupValue(self,*args): pass


class LayerFeedbackLayoutTests(unittest.TestCase):
    def setUp(self):
        self.runtime=runpy.run_path('touchdesigner/scripts/dance_puppet_runtime.py')
        self.clock=self.runtime['finish_clock']
        self.time=SimpleNamespace(seconds=100.,frame=1)
        self.clock.__globals__['absTime']=self.time
        self.component=MemoryComponent()

    def tick(self,delta,wall=None):
        self.component.par.Time+=delta
        self.time.seconds+=delta if wall is None else wall
        self.time.frame+=1
        return self.clock(self.component)

    def test_first_frame_resets_and_pause_holds(self):
        self.assertEqual(self.clock(self.component),(0.,1.,0.,0.))
        self.assertEqual(self.tick(0.,.04),(0.,0.,1.,0.))

    def test_low_fps_does_not_reset_or_cap_decay(self):
        self.clock(self.component)
        self.assertEqual(self.tick(.5),(.5,0.,0.,0.))
        self.assertEqual(self.tick(1.2),(1.2,0.,0.,0.))

    def test_fast_playback_does_not_reset(self):
        self.clock(self.component)
        self.assertEqual(self.tick(.4,.1),(.4,0.,0.,0.))

    def test_seek_reverse_and_loop_reset_history(self):
        self.clock(self.component)
        self.assertEqual(self.tick(10.,.02)[1],1.)
        self.assertEqual(self.tick(-1.,.02)[1],1.)
        self.component.par.Time=59.9
        self.tick(0.,.1)
        self.assertEqual(self.tick(.2)[1],1.)

    def test_frame_cache_and_disabled_reset(self):
        first=self.clock(self.component)
        self.assertIs(self.clock(self.component),first)
        self.component.par.Feedbackenabled=False
        self.assertEqual(self.tick(.03)[1],1.)

    def test_manual_time_change_in_same_frame_invalidates_cache(self):
        self.clock(self.component)
        self.component.par.Time=.1
        self.assertEqual(self.clock(self.component),(.1,0.,0.,0.))

    def test_layout_regions_never_overlap(self):
        layout=runpy.run_path('touchdesigner/scripts/show_panel_layout.py')
        boxes=layout['rectangles']()
        for name,(x,y,w,h) in boxes.items():
            self.assertTrue(0<=x<x+w<=1660 and 0<=y<y+h<=900,name)
            for other,(xx,yy,ww,hh) in boxes.items():
                if name>=other: continue
                overlap=min(x+w,xx+ww)>max(x,xx) and min(y+h,yy+hh)>max(y,yy)
                self.assertFalse(overlap,(name,other))
        for row in range(12):
            self.assertEqual(boxes['cue_row_'+str(row)][1::2],boxes['cue_notes_'+str(row)][1::2])

    def test_all_show_sections_accessible_in_selector(self):
        layout=runpy.run_path('touchdesigner/scripts/show_panel_layout.py')
        self.assertEqual(len(layout['SECTIONS']),13)
        self.assertEqual(len(set(layout['SECTIONS'])),13)
        for page in ('Cue Notes','Look Editor','Projection Mapping','Export Video'):
            self.assertIn(page,layout['SECTIONS'])

    def test_section_switch_rebuilds_native_inspector_list(self):
        layout=runpy.run_path('touchdesigner/scripts/show_panel_layout.py')
        for section in layout['SECTIONS']:
            with self.subTest(section=section):
                nav,inspector=Mock(),Mock()
                nav.par.Section.eval.return_value=section
                show=Mock(customPages=[SimpleNamespace(name=s) for s in layout['SECTIONS']])
                show.op.side_effect={'inspector_navigation':nav,'cue_inspector':inspector}.get
                layout['select_section'](show)
                self.assertEqual(inspector.par.pagescope,repr(section))
                self.assertEqual(inspector.par.op,'..')
                self.assertFalse(inspector.par.pagenames)
                self.assertFalse(inspector.par.syncpage)
                self.assertEqual(inspector.cook.call_count,2)
                show.initializeExtensions.assert_not_called()

    def test_unknown_section_leaves_native_inspector_untouched(self):
        layout=runpy.run_path('touchdesigner/scripts/show_panel_layout.py')
        nav,inspector,show=Mock(),Mock(),Mock()
        nav.par.Section.eval.return_value='Not a page'
        show.op.side_effect={'inspector_navigation':nav,'cue_inspector':inspector}.get
        with self.assertRaisesRegex(ValueError,'Unknown Show Control section'):
            layout['select_section'](show)
        inspector.cook.assert_not_called()

    def test_branch_editor_controls_are_navigation_only(self):
        layer=runpy.run_path('touchdesigner/scripts/layer_composite.py')
        pars={p['name']:p for p in layer['PARAMETERS']}
        for prefix in ('A','B'):
            self.assertFalse(pars[prefix+'module']['animatable'])
            for action in ('edit','workflow','preview'):
                self.assertEqual(pars[prefix+action]['type'],'pulse')
        self.assertTrue(pars['Editstatus']['read_only'])
