"""Real-time review capture taps existing outputs without seeking show cues."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from touchdesigner.scripts import show_review_export as review


class ProjectorReviewRecordingTests(unittest.TestCase):
    def settings(self, **changes):
        values=dict(source='review',preset='1080p',width=1920,height=1080,fps=30,
                    duration=1,start=42,codec='mjpeg')
        values.update(changes)
        return review.export_settings(**values)

    def target(self):
        target=Mock(family='TOP',width=864,height=162,path='/show/projector_review')
        target.errors.return_value=''
        return target

    def job(self):
        writer=Mock();writer.errors.return_value=''
        target=self.target()
        return dict(id='review-job',settings=self.settings(),target=target,writer=writer,deck=Mock(),
                    review_view='all',review_route='atlas',review_dimensions=(864,162),
                    index=0,dropped=0,stage='recording',info=Mock(),deadline=999999999.)

    def test_source_menu_preserves_legacy_indices(self):
        self.assertEqual([item[0] for item in review.EXPORT_SOURCES],['cue','draft','wall','review'])
        self.assertIn('review',review.REALTIME_SOURCES)

    def test_native_review_dimensions_ignore_disabled_size_and_seek_fields(self):
        for preset in dict(review.EXPORT_RESOLUTIONS):
            settings=self.settings(preset=preset,width=1,height=1,start=float('nan'))
            self.assertEqual((settings['width'],settings['height'],settings['start']),(864,162,0))
            self.assertFalse(settings['panoramic'])

    def test_review_encodes_selected_view_dimensions(self):
        for size in ((1920,1080),(3840,2160),(864,162)):
            result=self.settings(review_size=size)
            self.assertEqual((result['width'],result['height']),size)

    def test_odd_native_dimensions_are_padded_to_even(self):
        self.assertEqual(review.review_recording_size(1919,1079),(1920,1080))
        self.assertEqual(review.review_recording_size(1920,1080),(1920,1080))

    def test_invalid_native_dimensions_are_rejected(self):
        for size in ((0,1080),(1920,15),(1920.5,1080),(float('nan'),1080),(16385,1080)):
            with self.subTest(size=size),self.assertRaises(ValueError):
                self.settings(review_size=size)

    def test_native_review_still_obeys_codec_limits(self):
        with self.assertRaisesRegex(ValueError,'H.264'):
            self.settings(review_size=(5760,1080),codec='h264')
        self.assertEqual(self.settings(review_size=(5760,1080),codec='h265')['width'],5760)
        with self.assertRaisesRegex(ValueError,'8192'):
            self.settings(review_size=(9000,1080),codec='h265')

    def test_review_still_validates_duration_fps_and_menu_values(self):
        for changes in ({'duration':0},{'fps':29},{'codec':'bad'},{'preset':'bad'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.settings(**changes)

    def test_capture_taps_actual_review_without_cue_snapshot(self):
        show=Mock();target=self.target()
        with patch.object(review,'review_target',return_value=target):
            self.assertIs(review.review_export_target(show),target)
        target.cook.assert_called_once_with(force=True)
        show.ext.ShowControlExt._capture_look.assert_not_called()

    def test_review_capture_does_not_require_stopped_transport(self):
        show=Mock();target=self.target()
        for state in ('stopped','running','paused'):
            show.ext.ShowControlExt.engine.state=state
            with patch.object(review,'review_target',return_value=target):
                self.assertIs(review.review_export_target(show),target)
            self.assertEqual(show.ext.ShowControlExt.engine.state,state)

    def test_missing_wrong_family_and_black_fallback_fail_closed(self):
        show=Mock()
        for target in (None,Mock(family='CHOP'),show.op.return_value):
            with patch.object(review,'review_target',return_value=target),self.assertRaisesRegex(ValueError,'unavailable'):
                review.review_export_target(show)

    def test_shader_error_is_reported(self):
        target=self.target();target.errors.return_value='Shader compilation failed'
        with patch.object(review,'review_target',return_value=target),self.assertRaisesRegex(ValueError,'Shader compilation failed'):
            review.review_export_target(Mock())

    def test_review_writer_is_real_time_silent_and_local(self):
        parent=Mock();writer,selector,code,canvas=Mock(),Mock(),Mock(name='review-code'),Mock()
        parent.create.side_effect=[writer,selector,code,canvas]
        writer.par.videocodec.menuNames=['mjpa','h264']
        writer.inputConnectors=[Mock()];selector.outputConnectors=[Mock()]
        canvas.inputConnectors=[Mock()];canvas.outputConnectors=[Mock()]
        target=self.target()
        kinds=SimpleNamespace(moviefileoutTOP='movie',selectTOP='select',textDAT='text',glslTOP='glsl')
        with patch.dict('sys.modules',{'td':kinds}):
            review._writer(parent,target,Path('review.mov'),self.settings())
        self.assertEqual(writer.par.type,'movie')
        self.assertFalse(writer.par.pause)
        self.assertFalse(writer.par.record)
        self.assertEqual(writer.par.audiochop,'')
        self.assertEqual(selector.par.top,target.path)
        self.assertEqual((canvas.par.resolutionw,canvas.par.resolutionh),(864,162))
        self.assertEqual((canvas.par.vec0valuex,canvas.par.vec0valuey),(0,1))
        self.assertEqual(writer.par.lengthunit,'seconds')

    def test_review_step_uses_live_path_without_seeking_effects(self):
        show=Mock();job=self.job();show.fetch.return_value=job
        with patch.object(review,'_wall_step') as live,patch.object(review,'_set_time') as seek:
            review.step(show,'review-job')
            live.assert_called_once_with(show,job)
            seek.assert_not_called()

    def test_view_change_aborts_before_writing_frames(self):
        job=self.job();show=Mock();show.par.Reviewroute.eval.return_value='atlas'
        with patch.object(review,'_export_windows',return_value=[]),patch.object(review,'review_selection',return_value='2'):
            with self.assertRaisesRegex(ValueError,'view/output route changed'):
                review._wall_step(show,job)
        job['writer'].cook.assert_not_called()

    def test_resolution_change_aborts_before_writing_frames(self):
        job=self.job();show=Mock();show.par.Reviewroute.eval.return_value='atlas'
        target=job['target'];target.width=1920
        with patch.object(review,'_export_windows',return_value=[]),patch.object(review,'review_selection',return_value='all'),patch.object(review,'review_export_target',return_value=target):
            with self.assertRaisesRegex(ValueError,'target/resolution changed'):
                review._wall_step(show,job)
        job['writer'].cook.assert_not_called()

    def test_stop_and_save_accepts_review_recording(self):
        show=Mock();job=self.job();job['index']=7;show.fetch.return_value=job
        with patch.object(review,'_wall_counts'),patch.object(review,'finish_export') as finish:
            review.stop_wall_export(show)
            finish.assert_called_once_with(show,'COMPLETE')

    def test_review_progress_uses_encoder_counts_and_reports_drops(self):
        show=Mock();job=self.job();show.par.Reviewroute.eval.return_value='atlas'
        def counts(job): job.update(index=5,dropped=2)
        with patch.object(review,'_export_windows',return_value=[]),patch.object(review,'review_selection',return_value='all'),patch.object(review,'review_export_target',return_value=job['target']),patch.object(review,'_wall_counts',side_effect=counts),patch.object(review,'_later'):
            review._wall_step(show,job)
        self.assertIn('5/30 frames | 2 dropped',show.par.Exportstatus)
        self.assertEqual(job['index'],5)

    def test_complete_status_identifies_review_view_and_native_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            job=self.job();job['path']=Path(directory)/'review.mov';job['path'].write_bytes(b'movie')
            job.update(index=30,dropped=1)
            show=Mock();show.fetch.return_value=job
            review.finish_export(show,'COMPLETE')
            self.assertIn('Projector Review all | 864x162 | 1 dropped',show.par.Exportstatus)
            self.assertIn('WARNING',show.par.Exportstatus)
            job['deck'].destroy.assert_called_once()


if __name__=='__main__': unittest.main()
