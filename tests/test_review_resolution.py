"""Full-quality review output is separate from the embedded thumbnail branch."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from touchdesigner.scripts import show_review_export as review


class ReviewResolutionTests(unittest.TestCase):
    def show(self,mode='1080p',width=1920,height=1080):
        def par(value):return SimpleNamespace(eval=lambda:value)
        return SimpleNamespace(par=SimpleNamespace(Reviewresolution=par(mode),Reviewwidth=par(width),
            Reviewheight=par(height),Reviewprojector=par('all')),op=Mock())

    def test_default_is_full_hd_for_each_projector(self):
        self.assertEqual(review.REVIEW_RESOLUTIONS[0][0],'1080p')
        self.assertEqual(review.review_canvas_size(self.show()),(5760,1080))

    def test_preset_sizes_and_disabled_custom_values(self):
        for preset,size in [('720p',(1280,720)),('1080p',(1920,1080)),('4k',(3840,2160))]:
            self.assertEqual(review.review_panel_geometry(preset,-1,float('nan')),size)

    def test_custom_size_and_odd_pixels_remain_adjustable(self):
        self.assertEqual(review.review_canvas_size(self.show('custom',1500,1000)),(4500,1000))
        self.assertEqual(review.review_panel_geometry('custom',1919,1079),(1919,1079))

    def test_invalid_custom_sizes_and_modes_fail_closed(self):
        for size in ((0,1080),(1920,15),(4097,1080),(float('nan'),1080),(1920.5,1080)):
            with self.subTest(size=size),self.assertRaises(ValueError):
                review.review_panel_geometry('custom',*size)
        with self.assertRaises(ValueError):review.review_panel_geometry('bad')
        with self.assertRaises(ValueError):review.review_panel_geometry('native',native_sizes=[])

    def test_native_cells_fit_largest_feed_without_resizing_outputs(self):
        sizes=[(1920,1080),(3840,2160),(640,360)]
        self.assertEqual(review.review_panel_geometry('native',native_sizes=sizes),(3840,2160))
        self.assertEqual(sizes,[(1920,1080),(3840,2160),(640,360)])

    def test_thumbnail_is_small_and_preserves_cell_aspect_ratio(self):
        self.assertEqual(review.review_thumbnail_geometry(1920,1080),(288,162))
        self.assertEqual(review.review_thumbnail_geometry(3840,2160),(288,162))
        self.assertEqual(review.review_thumbnail_geometry(1000,1000),(162,162))

    def test_embedded_three_up_never_selects_full_layout(self):
        show=self.show();thumbnail=Mock();show.op.return_value=thumbnail
        with patch.object(review,'review_target') as full:
            self.assertIs(review.review_preview_target(show),thumbnail)
            full.assert_not_called()
        show.op.assert_called_once_with('projector_review_thumbnail')

    def test_embedded_dimensions_do_not_query_high_resolution_top(self):
        show=self.show('4k')
        show.par.Exportsource='review'
        with patch.object(review,'review_target') as full,patch.object(review,'review_export_target') as capture:
            self.assertEqual(review.review_size(show),(880,165))
            self.assertIn('11520 x 2160',review.export_description(show))
            full.assert_not_called()
            capture.assert_not_called()
        show.op.assert_not_called()

    def test_other_views_keep_their_native_target(self):
        show=self.show()
        with patch.object(review,'review_selection',return_value='wall'),patch.object(review,'review_target',return_value='actual-wall'):
            self.assertEqual(review.review_preview_target(show),'actual-wall')

    def test_quality_readout_explains_total_canvas_and_codec_limits(self):
        info=review.review_resolution_info(self.show())
        self.assertIn('5760 x 1080',info)
        self.assertIn('1920 x 1080 each',info)
        self.assertIn('H.265',info)
        self.assertIn('Motion JPEG',review.review_resolution_info(self.show('4k')))


if __name__=='__main__':unittest.main()
