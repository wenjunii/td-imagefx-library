import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tdimagefx.show import composition_activity, validate_look_media, resolve_puppet_files

RUNTIME=runpy.run_path('touchdesigner/scripts/dance_puppet_runtime.py')


class ClockComponent:
    def __init__(self):
        self.par=SimpleNamespace(Autotime=False,Manualtime=20.,Timescale=1.)
        self.storage={}
    def fetch(self,name,default=None,**kwargs): return self.storage.get(name,default)
    def store(self,name,value): self.storage[name]=value
    def storeStartupValue(self,*args): pass


class NewPuppetAndCompositeTests(unittest.TestCase):
    def test_time_expression_does_not_touch_dependent_storage(self):
        c=ClockComponent(); c.par.Autotime=True
        def forbidden(*args,**kwargs):
            raise AssertionError('Time must not read/write operator storage')
        c.fetch=c.store=c.storeStartupValue=forbidden
        runtime=runpy.run_path('touchdesigner/scripts/dance_puppet_runtime.py')
        value=runtime['preview_time']
        now=SimpleNamespace(seconds=100.)
        with patch.dict(value.__globals__,absTime=now):
            self.assertEqual(value(c),0.)
            now.seconds=102.
            self.assertEqual(value(c),2.)

    def test_copied_runtime_clock_starts_independently(self):
        first=runpy.run_path('touchdesigner/scripts/dance_puppet_runtime.py')
        second=runpy.run_path('touchdesigner/scripts/dance_puppet_runtime.py')
        a=ClockComponent(); b=ClockComponent()
        a.par.Autotime=b.par.Autotime=True
        first['clock_state'](a,100.)
        self.assertEqual(second['clock_state'](b,200.)['origin'],200.)
        self.assertEqual(first['clock_state'](a,201.)['origin'],100.)

    def test_fade_bounds_and_zero_duration(self):
        c=ClockComponent(); c.par.Time=2.; c.par.Sourcemode='recorded'; c.par.Fadein=2.
        c.store('puppet_fade_start',2.)
        gain=RUNTIME['fade_gain']
        self.assertEqual(gain(c),0.)
        c.par.Time=3.; self.assertEqual(gain(c),.5)
        c.par.Time=9.; self.assertEqual(gain(c),1.)
        c.par.Fadein=0.; self.assertEqual(gain(c),1.)

    def test_resume_callback_does_not_restart_fade(self):
        c=ClockComponent(); c.par.Autotime=True; c.par.Time=.6
        c.par.Sourcemode='recorded'; c.par.Fadein=2.
        c.store('puppet_preview_clock',dict(origin=100.,phase=.6,speed=1.,running=True))
        c.store('puppet_fade_start',0.); c.store('puppet_fade_resuming',True)
        changed=RUNTIME['on_value']
        with patch.dict(changed.__globals__,absTime=SimpleNamespace(seconds=100.),reset_history=lambda c:None):
            changed(c,'Autotime',False)
        self.assertEqual(c.fetch('puppet_fade_start'),0.)
        self.assertFalse(c.fetch('puppet_fade_resuming'))

    def test_animate_preview_callback_restarts_fade(self):
        c=ClockComponent(); c.par.Autotime=True; c.par.Time=0.
        c.par.Sourcemode='recorded'; c.store('puppet_fade_start',27.)
        changed=RUNTIME['on_value']
        with patch.dict(changed.__globals__,absTime=SimpleNamespace(seconds=100.),reset_history=lambda c:None):
            changed(c,'Autotime',False)
        self.assertEqual(c.fetch('puppet_fade_start'),0.)

    def test_toggle_starts_at_zero_not_uptime(self):
        c=ClockComponent(); clock=RUNTIME['clock_state']
        clock(c,5000.)
        c.par.Autotime=True
        state=clock(c,6000.)
        self.assertEqual(state['phase'],0.)
        self.assertEqual(state['origin'],6000.)

    def test_speed_changes_keep_phase(self):
        c=ClockComponent(); c.par.Autotime=True; clock=RUNTIME['clock_state']
        clock(c,100.)
        c.par.Timescale=2.
        self.assertEqual(clock(c,103.)['phase'],3.)
        c.par.Timescale=.5
        self.assertEqual(clock(c,105.)['phase'],7.)

    def test_pause_snapshot_and_manual_cue_ownership(self):
        c=ClockComponent(); c.par.Autotime=True; clock=RUNTIME['clock_state']
        clock(c,50.); c.par.Autotime=False
        state=clock(c,52.)
        self.assertEqual(state['phase'],2.)
        self.assertEqual(c.par.Manualtime,20.)

    def test_layer_branches_active_without_layout(self):
        look={'toggles':{'Layercompositeenabled':True},'modules':{'layer_composite':{'Backdropsource':'effects_a','Topsource':'effects_b'}}}
        self.assertEqual(composition_activity(look),dict(A=True,B=True))
        self.assertEqual(composition_activity(look,False),dict(A=False,B=False))
        look['modules']['image_composition']={'Avisible':False}
        self.assertEqual(composition_activity(look),dict(A=False,B=True))

    def test_layer_cycles_and_recursive_sources_rejected(self):
        look={'toggles':{'Layercompositeenabled':True},'modules':{'layer_composite':{'Topsource':'effects_b'}}}
        with self.assertRaises(ValueError): composition_activity(look,branch=True)
        look['order']=['layer_composite','image_composition']
        with self.assertRaises(ValueError): composition_activity(look)

    def test_nested_puppet_validated_for_independent_layer(self):
        look={'toggles':{'Layercompositeenabled':True},'modules':{'layer_composite':{'Topsource':'effects_b'}},
              'branches':{'b_effects':{'toggles':{'Dancepuppetenabled':True}}}}
        with self.assertRaisesRegex(ValueError,'prepared'): validate_look_media(look,'.')
        look['toggles']['Layercompositeenabled']=False
        validate_look_media(look,'.')

    def test_separate_character_needs_its_own_alpha_movie(self):
        for mode,field in [('fan','Fanrenderfile'),('chain','Chainrenderfile')]:
            with self.assertRaisesRegex(ValueError,mode): resolve_puppet_files({},'.',selections={'Characters':mode})
            result=resolve_puppet_files({field:'local.mov'},'.',selections={'Characters':mode},enabled=False)
            self.assertTrue(result[field].endswith('local.mov'))

    def test_top_canvas_default_and_source_modes(self):
        module=runpy.run_path('touchdesigner/scripts/layer_composite.py')
        parameters={p['name']:p for p in module['PARAMETERS']}
        self.assertEqual(parameters['Topcanvas']['default'],'full')
        self.assertEqual(parameters['Topcanvas']['menu_names'],['full','left','center','right'])
        runtime={}; exec(module['STATUS'],runtime)
        self.assertEqual(runtime['source_index']('effects_a',False,1,0),5)
        self.assertEqual(runtime['source_index']('effects_b',False,1,1),6)
