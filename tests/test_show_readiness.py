import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from touchdesigner.scripts import show_readiness as readiness
from touchdesigner.scripts import show_review_export as export
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class ShowReadinessTests(unittest.TestCase):
    def samples(self, **changes):
        return [dict(fps=60,msec=10,dropped_frames=0,gpu_mem_used=2000,total_gpu_mem=16000,**changes)]

    def test_good_performance(self):
        rows=readiness.performance_report(self.samples(),30)
        self.assertTrue(all(row[0]=='PASS' for row in rows))

    def test_missing_measurements_warn_not_pass(self):
        self.assertTrue(all(row[0]=='WARN' for row in readiness.performance_report([],30)))

    def test_nonfinite_measurements_are_missing(self):
        sample={name:float('nan') for name in readiness.CHANNELS}
        self.assertTrue(all(row[0]=='WARN' for row in readiness.performance_report([sample],30)))

    def test_slow_frames_warn(self):
        samples=self.samples(); samples[0].update(fps=20,msec=50)
        self.assertEqual(readiness.performance_report(samples,30)[0][0],'WARN')

    def test_high_memory_warns(self):
        samples=self.samples(); samples[0]['gpu_mem_used']=15000
        self.assertEqual(readiness.performance_report(samples,30)[2][0],'WARN')

    def test_drops_accumulated_from_per_frame_channel(self):
        samples=self.samples()*2
        samples=[dict(s,dropped_frames=2) for s in samples]
        row=readiness.performance_report(samples,30)[1]
        self.assertEqual(row[0],'WARN'); self.assertIn('4 timeline',row[2])

    def test_invalid_target(self):
        for value in (0,241,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError): readiness.performance_report([],value)

    def test_summary_never_claims_hardware_certified(self):
        text=readiness.summary([('ERROR','a','x'),('WARN','b','y')])
        self.assertIn('1 errors, 1 warnings',text)
        self.assertIn('verify physical',text)

    def test_stale_sample_does_not_touch_new_job(self):
        show=Mock(); show.fetch.return_value={'id':'new'}
        with patch.dict('sys.modules',{'td':SimpleNamespace()}): readiness.sample_step(show,'old')
        show.op.assert_not_called(); show.unstore.assert_not_called()

    def test_sample_does_not_start_twice(self):
        show=Mock(); show.fetch.return_value={'id':'running'}
        with self.assertRaisesRegex(ValueError,'already running'): readiness.sample_start(show)

    def test_readiness_pulses_bypass_legacy_dispatch_once(self):
        source = 'def onPulse(par):\n    parent().Action(par.name)\n'
        guarded = readiness.guard_legacy_callback(source)
        self.assertEqual(readiness.guard_legacy_callback(guarded), guarded)
        show = Mock()
        show.op.return_value.module.ACTION_NAMES = readiness.ACTION_NAMES
        namespace = {'parent': lambda: show}
        exec(guarded, namespace)
        for name in readiness.ACTION_NAMES:
            namespace['onPulse'](SimpleNamespace(name=name))
        show.Action.assert_not_called()
        namespace['onPulse'](SimpleNamespace(name='Preflight'))
        show.Action.assert_called_once_with('Preflight')

    def test_cue_warmup_requires_distinct_frames_without_time_edits(self):
        ext=ShowControlExt.__new__(ShowControlExt)
        ext.ownerComp=Mock(); ext.ownerComp.par.Cuewarmframes.eval.return_value=3
        deck=Mock(); item={'deck':deck}; clock=SimpleNamespace(frame=10)
        with patch('touchdesigner.extensions.ShowControlExt.absTime',clock,create=True):
            steps=ext._warm_prepared_deck(item)
            next(steps); next(steps); next(steps)
            self.assertEqual(item['warm_count'],1)
            clock.frame=11; next(steps)
            clock.frame=12; next(steps)
            clock.frame=13
            with self.assertRaises(StopIteration): next(steps)
        self.assertEqual(deck.op.return_value.cook.call_count,3)
        self.assertEqual(deck.par.mock_calls,[])

    def test_cue_warmup_rejects_invalid_values(self):
        ext=ShowControlExt.__new__(ShowControlExt); ext.ownerComp=Mock()
        ext.ownerComp.par.Cuewarmframes.eval.return_value=0
        with self.assertRaises(ValueError): next(ext._warm_prepared_deck({'deck':Mock()}))

    def test_timeout_does_not_stop_on_air_deck(self):
        ext=ShowControlExt.__new__(ShowControlExt)
        live=Mock(); ext.tracks={1:live}
        item={'loading':True,'prepare_started':0,'cue':{'id':'standby'},'deck':Mock()}
        ext.prepared={'standby':item}; ext._halt_deck=Mock(); ext._release_audio=Mock(); ext._status=Mock()
        with patch('touchdesigner.extensions.ShowControlExt.time.monotonic',return_value=91): ext._service_preloads()
        self.assertIn('timed out',item['error']); self.assertIs(ext.tracks[1],live)
        ext._halt_deck.assert_called_once_with(item)

    def test_wall_warmup_bounds(self):
        for value in (0,2,10): self.assertEqual(export.wall_warmup_seconds(value),value)
        for value in (-1,11,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError): export.wall_warmup_seconds(value)

    def test_wall_warmup_never_records_early(self):
        show=Mock(); writer=Mock(); target=Mock(); job={'stage':'warming','writer':writer,
            'settings':{'duration':10},'target':target,'warm_until':12,'warm_frames':0}
        with patch.dict('sys.modules',{'td':SimpleNamespace(absTime=SimpleNamespace(frame=1))}), \
             patch.object(export,'_export_windows',return_value=[]), \
             patch.object(export,'wall_export_target',return_value=target), \
             patch.object(export.time,'monotonic',return_value=10),patch.object(export,'_later'):
            export._wall_step(show,job)
        self.assertEqual(job['stage'],'warming'); self.assertEqual(job['warm_frames'],1)
        writer.cook.assert_not_called()

    def test_wall_warmup_start_needs_two_frames_even_when_zero_seconds(self):
        show=Mock(); writer=Mock(); writer.errors.return_value=''; target=Mock()
        clock=SimpleNamespace(frame=1)
        job={'stage':'warming','writer':writer,'settings':{'duration':10},'target':target,'warm_until':0,'warm_frames':0}
        with patch.dict('sys.modules',{'td':SimpleNamespace(absTime=clock)}), \
             patch.object(export,'_export_windows',return_value=[]), \
             patch.object(export,'wall_export_target',return_value=target), \
             patch.object(export.time,'monotonic',return_value=10),patch.object(export,'_later'):
            export._wall_step(show,job); export._wall_step(show,job)
            self.assertEqual(job['stage'],'warming'); self.assertEqual(job['warm_frames'],1)
            clock.frame=2; export._wall_step(show,job)
        self.assertEqual(job['stage'],'recording'); self.assertTrue(writer.par.record)


if __name__ == '__main__': unittest.main()
