from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from touchdesigner.scripts import show_review_export as review


class PanoramaExportTests(unittest.TestCase):
    def settings(self, **changes):
        values = dict(source='cue', preset='panoramic', width=640, height=360,
                      fps=30, duration=.2, start=2, codec='mjpeg')
        values.update(changes)
        return review.export_settings(**values)

    def test_resolution_menu_keeps_old_choices_and_adds_panorama(self):
        self.assertEqual(set(dict(review.EXPORT_RESOLUTIONS)),
                         {'1080p', '4k', '720p', 'custom', 'panoramic'})

    def test_full_panorama_defaults_and_timing(self):
        result = self.settings()
        self.assertEqual((result['width'], result['height']), (5760, 1080))
        self.assertEqual((result['frames'], result['fps'], result['start']), (6, 30, 2))
        self.assertTrue(result['panoramic'])

    def test_saved_cue_and_draft_both_support_panorama(self):
        for source in ('cue', 'draft'):
            self.assertEqual(self.settings(source=source)['width'], 5760)

    def test_geometry_matches_three_projectors_and_overlap(self):
        self.assertEqual(review.panorama_size(1920, 1080, 0), (5760, 1080))
        self.assertEqual(review.panorama_size(1920, 1080, .25), (4800, 1080))
        self.assertEqual(review.panorama_size(3840, 2160, 0), (11520, 2160))

    def test_odd_canvas_is_rounded_by_at_most_one_pixel(self):
        self.assertEqual(review.panorama_size(1920, 1081, .001), (5756, 1082))
        self.assertEqual(review.panorama_size(1921, 1080, 0), (5764, 1080))

    def test_bad_geometry_is_rejected(self):
        for args in ((0, 1080, 0), (1920.5, 1080, 0), (1920, float('nan'), 0),
                     (1920, 1080, -.1), (1920, 1080, .51), (8192, 1080, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                review.panorama_size(*args)

    def test_h264_wide_canvas_fails_with_actionable_message(self):
        with self.assertRaisesRegex(ValueError, 'MOV / Motion JPEG'):
            self.settings(codec='h264')
        self.assertEqual(self.settings(codec='h264', panorama=(3840, 720))['width'], 3840)

    def test_h265_keeps_full_panorama_for_cue_and_draft(self):
        for source in ('cue', 'draft'):
            result = self.settings(source=source, codec='h265')
            self.assertEqual((result['width'], result['height']), (5760, 1080))
            self.assertEqual((result['codec'], result['frames'], result['start']), ('h265', 6, 2))

    def test_h265_8192_limit_is_inclusive_on_each_axis(self):
        for size in ((8192, 1080), (1920, 8192)):
            result = self.settings(codec='h265', panorama=size)
            self.assertEqual((result['width'], result['height']), size)
        for size in ((8194, 1080), (1920, 8194), (11520, 2160)):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, '8192.*MOV / Motion JPEG'):
                self.settings(codec='h265', panorama=size)

    def test_h265_wall_remains_fixed_uhd(self):
        result = self.settings(codec='h265', source='wall', panorama=(11520, 2160))
        self.assertEqual((result['width'], result['height'], result['start']), (3840, 2160, 0))
        self.assertFalse(result['panoramic'])

    def test_movie_suffix_is_mp4_for_both_gpu_codecs(self):
        for codec in ('h264', 'h265'):
            self.assertEqual(review.export_suffix(codec), '.mp4')
        self.assertEqual(review.export_suffix('mjpeg'), '.mov')
        with self.assertRaises(ValueError):
            review.export_suffix('unknown')

    def test_gpu_writer_tokens_support_old_and_new_td_versions(self):
        for codec in ('h264', 'h265'):
            self.assertEqual(review.writer_codec(codec, ['mjpa', codec]), codec)
            self.assertEqual(review.writer_codec(codec, [codec, codec+'nvgpu']), codec+'nvgpu')
            self.assertEqual(review.writer_codec(codec, [codec+'nvgpu']), codec+'nvgpu')
        self.assertEqual(review.writer_codec('mjpeg', ['mjpa']), 'mjpa')

    def test_unavailable_codec_never_falls_back(self):
        for codec, menus in (('h265', ['mjpa', 'h264']), ('h264', []), ('mjpeg', ['h265'])):
            with self.subTest(codec=codec), self.assertRaisesRegex(ValueError, 'unavailable'):
                review.writer_codec(codec, menus)
        with self.assertRaises(ValueError):
            review.writer_codec('unknown', ['unknown'])

    def test_codec_menu_upgrade_preserves_old_values_and_indices(self):
        self.assertEqual([x[0] for x in review.EXPORT_CODECS][:2], ['h264', 'mjpeg'])
        for selected in ('h264', 'mjpeg', 'h265'):
            par = Mock()
            par.eval.return_value = selected
            show = SimpleNamespace(par=SimpleNamespace(Exportcodec=par))
            review.upgrade_codec_menu(show)
            self.assertEqual(par.val, selected)
            self.assertEqual(par.menuNames, ['h264', 'mjpeg', 'h265'])

    def test_unknown_old_menu_value_uses_existing_default(self):
        par = Mock()
        par.eval.return_value = 'unknown'
        review.upgrade_codec_menu(SimpleNamespace(par=SimpleNamespace(Exportcodec=par)))
        self.assertEqual(par.val, 'h264')

    def test_panorama_hint_respects_codec_width_limits(self):
        self.assertEqual(review.panorama_codec_hint(1920, 1080), '')
        self.assertIn('H.265', review.panorama_codec_hint(5760, 1080))
        self.assertIn('Above 8192', review.panorama_codec_hint(11520, 2160))

    def test_offline_h265_writer_retains_native_panorama_and_frame_step(self):
        parent, writer, target = Mock(), Mock(), Mock()
        parent.create.return_value = writer
        writer.par.videocodec.menuNames = ['h264', 'h265', 'mjpa']
        writer.inputConnectors = [Mock()]
        target.outputConnectors = [Mock()]
        with patch.dict('sys.modules', {'td': SimpleNamespace(moviefileoutTOP='movie')}):
            review._writer(parent, target, Path('render.mp4'), self.settings(codec='h265'))
        self.assertEqual(writer.par.videocodec, 'h265')
        self.assertEqual(writer.par.type, 'stopframemovie')
        self.assertTrue(writer.par.pause)
        self.assertFalse(writer.par.record)
        self.assertEqual((writer.par.resolutionw, writer.par.resolutionh), (5760, 1080))
        self.assertEqual(writer.par.audiochop, '')

    def test_custom_panel_size_uses_entire_canvas(self):
        result = self.settings(panorama=review.panorama_size(3840, 2160, 0))
        self.assertEqual((result['width'], result['height']), (11520, 2160))

    def test_invalid_movie_dimensions_rejected(self):
        for size in ((5759, 1080), (5760, 0), (16386, 1080), (float('inf'), 1080), (5760,)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.settings(panorama=size)

    def test_wall_remains_fixed_even_if_panorama_preset_selected(self):
        result = self.settings(source='wall', codec='h264', panorama=(11520, 2160))
        self.assertEqual((result['width'], result['height'], result['start']), (3840, 2160, 0))
        self.assertFalse(result['panoramic'])

    def test_auto_panorama_fit_is_proportional_even_in_identical_layout(self):
        show = SimpleNamespace(par=SimpleNamespace(Cuemediafit=Mock(), Routingmode='identical'))
        show.par.Cuemediafit.eval.return_value = 'auto'
        self.assertEqual(review.export_media_fit(show, True), 'cover')
        self.assertEqual(review.export_media_fit(show, False), 'contain')
        self.assertEqual(show.par.Routingmode, 'identical')

    def test_explicit_fit_choice_is_preserved(self):
        show = SimpleNamespace(par=SimpleNamespace(Cuemediafit=Mock(), Routingmode='panoramic'))
        for fit in ('contain', 'cover', 'stretch'):
            show.par.Cuemediafit.eval.return_value = fit
            self.assertEqual(review.export_media_fit(show, True), fit)
        show.par.Cuemediafit.eval.return_value = 'bad'
        with self.assertRaises(ValueError):
            review.export_media_fit(show, True)

    def test_open_reader_must_have_decoded_pixels_before_export(self):
        reader = Mock(isInvalid=False, isOpen=True, isFullyPreRead=False)
        self.assertFalse(review.export_reader_ready(reader))
        reader.cook.assert_called_once_with(force=True)
        reader.isFullyPreRead = True
        self.assertTrue(review.export_reader_ready(reader))
        reader.isOpen = False
        self.assertFalse(review.export_reader_ready(reader))

    def test_bad_media_fails_without_rendering_empty_pixels(self):
        reader = Mock(isInvalid=True)
        reader.name = 'source'
        with self.assertRaisesRegex(ValueError, 'could not be decoded: source'):
            review.export_reader_ready(reader)


if __name__ == '__main__':
    unittest.main()
