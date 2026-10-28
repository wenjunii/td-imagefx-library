"""History must not survive navigation or change when paused."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from preview_effects_runtime import retention,history_state,clock_change_matches
import preview_effects_runtime as runtime


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.storage={}
        self.clock=SimpleNamespace(frame=1,seconds=0.)
        self.pars=SimpleNamespace(Composition=SimpleNamespace(eval=lambda:'full'),Zoom=1.,Panx=0.,Pany=0.,
                  Enabled=True,Motionblur=False,Bluramount=.35,Feedbackenabled=True,Trailamount=.25,
                  Speed=1.,Position=0.,Playing=True)
        self.component=SimpleNamespace(par=self.pars,
            fetch=lambda key,default=None,search=False:self.storage.get(key,default),
            store=lambda key,value:self.storage.__setitem__(key,value),
            storeStartupValue=lambda key,value:None)

    def test_same_frame_recalculation_keeps_elapsed_time(self):
        with patch.object(runtime,'absTime',self.clock,create=True):
            runtime.sample(self.component)
            self.clock.frame=2; self.clock.seconds=1/60
            self.pars.Position=.01
            first=runtime.sample(self.component)
            self.pars.Position=1/60
            second=runtime.sample(self.component)
        self.assertAlmostEqual(first['dt'],1/60)
        self.assertAlmostEqual(second['dt'],1/60)
        self.assertFalse(second['clear'])

    def test_style_change_within_frame_clears(self):
        with patch.object(runtime,'absTime',self.clock,create=True):
            runtime.sample(self.component)
            self.clock.frame=2; self.clock.seconds=1/60
            runtime.sample(self.component)
            self.pars.Zoom=2.
            self.assertTrue(runtime.sample(self.component)['clear'])

    def test_deferred_clock_callback_preserves_history(self):
        with patch.object(runtime,'absTime',self.clock,create=True):
            runtime.sample(self.component)
            self.storage['puppet_clock_change']=dict(before=0.,after=1/60)
            self.pars.Position=1/60
            runtime.changed(self.component,'Position',0.)
        self.assertIsNotNone(self.storage[runtime.KEY])
        self.assertIsNone(self.storage['puppet_clock_change'])

    def test_explicit_small_seek_clears_history(self):
        with patch.object(runtime,'absTime',self.clock,create=True):
            runtime.sample(self.component)
            self.storage['puppet_clock_change']=dict(before=0.,after=1/60)
            self.pars.Position=.02
            runtime.changed(self.component,'Position',0.)
        self.assertIsNone(self.storage[runtime.KEY])
        self.assertEqual(self.storage['puppet_v5_clear_until'],4)


class HistoryTests(unittest.TestCase):
    def test_deferred_clock_change_with_float32_previous(self):
        self.assertTrue(clock_change_matches(4.016666889190674,4.0333333333,
                        dict(before=4.01666666667,after=4.0333333333)))

    def test_external_small_seek_is_not_a_clock_write(self):
        self.assertFalse(clock_change_matches(4.0,4.02,dict(before=4.0,after=4.01666667)))

    def test_old_clock_write_cannot_hide_new_seek(self):
        self.assertFalse(clock_change_matches(9.,4.01666667,dict(before=4.,after=4.01666667)))

    def test_missing_clock_stamp_never_matches(self):
        self.assertFalse(clock_change_matches(1.,2.,None))

    def state(self,previous=None,**changes):
        values=dict(frame=1,now=0.,position=0.,playing=True,speed=1.,style=('full',1))
        values.update(changes)
        return history_state(previous,**values)

    def test_first_frame_clears(self):
        self.assertTrue(self.state()['clear'])

    def test_playback_accumulates(self):
        p=self.state(); q=self.state(p,frame=2,now=1/60,position=1/60)
        self.assertFalse(q['clear']); self.assertAlmostEqual(q['dt'],1/60)

    def test_pause_holds(self):
        q=self.state(self.state(),frame=2,now=1/60,playing=False)
        self.assertTrue(q['hold']); self.assertEqual(q['dt'],0)

    def test_zero_speed_holds(self):
        q=self.state(self.state(),frame=2,now=1/60,speed=0)
        self.assertTrue(q['hold']); self.assertEqual(q['dt'],0)

    def test_seek_clears(self):
        self.assertTrue(self.state(self.state(),frame=2,now=1/60,position=12)['clear'])

    def test_small_explicit_seek_clears(self):
        self.assertTrue(self.state(self.state(),frame=2,now=1/60,position=.01,clear_until=5)['clear'])

    def test_composition_change_clears(self):
        self.assertTrue(self.state(self.state(),frame=2,now=1/60,style=('crop',1))['clear'])

    def test_gap_clears(self):
        self.assertTrue(self.state(self.state(),frame=20,now=.3,position=.3)['clear'])

    def test_forward_wrap_clears(self):
        p=self.state(position=61.5)
        self.assertTrue(self.state(p,frame=2,now=1/60,position=0)['clear'])

    def test_reverse_playback_does_not_clear_each_frame(self):
        p=self.state(position=4,speed=-1)
        q=self.state(p,frame=2,now=1/60,position=4-1/60,speed=-1)
        self.assertFalse(q['clear']); self.assertGreater(q['dt'],0)

    def test_reverse_wrap_clears(self):
        p=self.state(position=0,speed=-1)
        self.assertTrue(self.state(p,frame=2,now=1/60,position=61.5,speed=-1)['clear'])

    def test_half_life_definition(self):
        self.assertAlmostEqual(retention(.18,.18),.5)

    def test_retention_frame_rate_independence(self):
        self.assertAlmostEqual(retention(1/30,.18)**30,retention(1/60,.18)**60)

    def test_bad_retention_rejected(self):
        for dt,half in ((-1,.2),(.1,0),(float('nan'),1)):
            with self.assertRaises(ValueError): retention(dt,half)


if __name__=='__main__': unittest.main()
