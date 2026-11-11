"""Cue-routed channel exports share one render clock and preserve live routing."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tdimagefx import show as model
from touchdesigner.scripts import show_review_export as review


class ProjectionExportTests(unittest.TestCase):
    def plan(self, selection='cue', **changes):
        cue = dict(model.new_cue(), projection='all', track=2)
        cue.update(changes.pop('cue', {}))
        values = dict(cue=cue, selection=selection, layout='independent', output_tracks=[1,2,3],
                      width=1920, height=1080, overlap=0.)
        values.update(changes)
        return review.projection_export_plan(**values)

    def test_menu_has_canvas_follow_cue_singles_pairs_and_all(self):
        self.assertEqual(set(dict(review.EXPORT_CHANNELS)), {'canvas','cue','1','2','3','1_2','1_3','2_3','all'})

    def test_legacy_canvas_does_not_split(self):
        self.assertIsNone(self.plan('canvas'))

    def test_all_singles_are_independent_of_playback_track(self):
        for i in (1,2,3):
            for track in (1,2,3):
                result = self.plan(str(i), cue=dict(projection='p'+str(i), track=track))
                self.assertEqual(result['channels'], (i,))
                self.assertEqual(result['samples'][i], (0.,1.))

    def test_pairs_and_all_follow_cue_destinations(self):
        for route, channels in [('p1_p2',(1,2)),('p1_p3',(1,3)),('p2_p3',(2,3)),('all',(1,2,3))]:
            self.assertEqual(self.plan(cue=dict(projection=route))['channels'], channels)
            selection = 'all' if len(channels)==3 else '_'.join(str(i) for i in channels)
            self.assertEqual(self.plan(selection, cue=dict(projection=route))['channels'], channels)

    def test_explicit_cue_overrides_global_identical_routing(self):
        self.assertEqual(self.plan(layout='identical', output_tracks=[1,1,1], cue=dict(projection='p2'))['channels'], (2,))

    def test_visual_channel_override_has_priority(self):
        result = self.plan(cue=dict(projection='p1', channels='2_3'))
        self.assertEqual(result['channels'], (2,3))

    def test_inherited_independent_routing_uses_output_tracks(self):
        result = self.plan(cue=dict(projection='inherit'), output_tracks=[2,1,2])
        self.assertEqual(result['channels'], (1,3))

    def test_inherited_shared_track_matches_live_fallback(self):
        self.assertEqual(self.plan(layout='identical', output_tracks=[2,2,2], cue=dict(projection='inherit'))['channels'], (1,2,3))
        with self.assertRaisesRegex(ValueError, 'not routed'):
            self.plan(layout='identical', output_tracks=[1,1,1], cue=dict(projection='inherit'))

    def test_panorama_exports_original_three_slices(self):
        result = self.plan(cue=dict(projection='panoramic'))
        self.assertEqual((result['render_width'], result['render_height']), (5760,1080))
        self.assertTrue(result['panoramic'])
        for i in (1,2,3):
            self.assertEqual(result['samples'][i], ((i-1)/3,i/3))

    def test_two_channel_panorama_can_use_nonadjacent_outputs(self):
        result = self.plan(cue=dict(projection='panoramic',channels='1_3'))
        self.assertEqual(result['channels'], (1,3))
        self.assertEqual(result['render_width'],3840)
        self.assertEqual(result['samples'], {1:(0.,.5),3:(.5,1.)})

    def test_single_slice_selection_never_redistributes_panorama(self):
        result = self.plan('2', cue=dict(projection='panoramic'))
        self.assertEqual(result['render_width'],5760)
        self.assertEqual(result['channels'],(2,))
        self.assertEqual(result['samples'][2],(1/3,2/3))

    def test_overlap_uses_the_same_geometry_as_live_output(self):
        result = self.plan(cue=dict(projection='panoramic'), overlap=.25)
        self.assertEqual(result['render_width'],4800)
        self.assertEqual(result['samples'][2],(.3,.7))

    def test_unrouted_requested_output_fails_clearly_instead_of_exporting_black(self):
        for selection in ('2','1_2','all'):
            with self.assertRaisesRegex(ValueError,'not routed to projector'):
                self.plan(selection, cue=dict(projection='p1'))

    def test_invalid_menus_geometry_and_tracks_are_rejected(self):
        for changes in (dict(selection='bad'),dict(width=0),dict(height=float('nan')),
                        dict(overlap=.7),dict(output_tracks=[1,4,3]),dict(layout='bad')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.plan(**changes)

    def test_planning_never_edits_cue_or_saved_look(self):
        cue = dict(model.new_cue(),projection='panoramic',look={'modules':{'ink_dream_flow':{'Scale':3.}}})
        before = copy.deepcopy(cue)
        self.plan('1_3',cue=cue)
        self.assertEqual(cue,before)

    def test_canvas_configuration_uses_live_composition_but_per_file_resolution(self):
        pars = {n:Mock(max=4096) for n in ('Customwidth','Customheight')}
        deck = Mock()
        deck.par.__getitem__ = Mock(side_effect=pars.get)
        show = SimpleNamespace(par=SimpleNamespace(Cuemediafit=Mock(),Routingmode='identical'))
        show.par.Cuemediafit.eval.return_value='auto'
        settings = dict(width=1280,height=720,panoramic=False,projection=self.plan(cue=dict(projection='panoramic')))
        review.configure_export_canvas(show,deck,settings)
        self.assertEqual((pars['Customwidth'].val,pars['Customheight'].val),(5760,1080))
        self.assertEqual((settings['width'],settings['height']),(1280,720))
        self.assertEqual(settings['fit'],'cover')

    def job(self, folder, channels=(1,3)):
        writers = [Mock() for _ in channels]
        for writer in writers: writer.errors.return_value=''
        paths = [folder/('projector-{}.mov'.format(i)) for i in channels]
        settings = review.export_settings('cue','custom',320,180,30,.2,0,'mjpeg')
        settings['projection']=dict(channels=channels,panoramic=False)
        return dict(id='job',settings=settings,cue=dict(model.new_cue(),name='Test'),path=folder,
                    paths=paths,writer=writers[0],writers=writers,deck=Mock(),index=6)

    def test_complete_checks_all_files_and_writes_channel_manifest(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); job=self.job(folder)
            for path in job['paths']: path.write_bytes(b'movie')
            show=Mock(); show.fetch.return_value=job
            show.par.Exportstatus.eval.return_value='COMPLETE'
            review.finish_export(show,'COMPLETE')
            result=json.loads((folder/'export.json').read_text())
            self.assertEqual(result['files'],{'1':'projector-1.mov','3':'projector-3.mov'})
            self.assertEqual(result['frames'],6)
            self.assertFalse(result['calibration_included'])
            self.assertEqual(show.par.Exportresult,str(folder))
            job['deck'].destroy.assert_called_once()
            self.assertTrue(all(writer.par.record is False for writer in job['writers']))

    def test_one_missing_channel_file_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            job=self.job(Path(directory)); job['paths'][0].write_bytes(b'movie')
            show=Mock(); show.fetch.return_value=job
            review.finish_export(show,'COMPLETE')
            self.assertTrue(show.par.Exportstatus.startswith('FAILED'))
            self.assertFalse((job['path']/'export.json').exists())

    def test_cancel_closes_every_writer_and_retains_partial_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            job=self.job(Path(directory),channels=(1,2,3))
            job['paths'][0].write_bytes(b'partial')
            show=Mock(); show.fetch.return_value=job
            review.finish_export(show,'CANCELLED')
            self.assertTrue(job['paths'][0].exists())
            self.assertTrue(all(writer.par.record is False for writer in job['writers']))
            job['deck'].destroy.assert_called_once()
            self.assertTrue(show.par.Exportstatus.startswith('CANCELLED'))

    def test_each_step_advances_every_channel_once_on_one_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            job=self.job(Path(directory),channels=(1,2,3))
            job.update(index=0,stage='loading',movie=None,readers=[],targets=[Mock(width=320,height=180) for _ in range(3)])
            show=Mock(); show.fetch.return_value=job
            show.ext.ShowControlExt.engine.state='stopped'
            job['deck'].errors.return_value=''
            with patch.object(review,'_export_windows',return_value=[]), patch.object(review,'_set_time') as clock, patch.object(review,'_later'):
                review.step(show,'job')
            self.assertEqual(job['index'],1)
            clock.assert_called_once()
            for writer in job['writers']:
                writer.par.addframe.pulse.assert_called_once()
                self.assertTrue(writer.par.record)


if __name__=='__main__': unittest.main()
