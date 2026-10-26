"""Shared-canvas routing and in-place resolution updates, without TD/GPU."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from touchdesigner.extensions.ShowControlExt import ShowControlExt
from touchdesigner.scripts.show_output_mode import (
    canvas_summary, canvas_size, cue_media_fit, workflow_size, workflow_fit, workflow_summary,
)
from touchdesigner.scripts.source_media import fit_extent


class Value:
    def __init__(self, value): self.value = value
    def eval(self): return self.value
    def __int__(self): return int(self.value)
    def __float__(self): return float(self.value)
    def __bool__(self): return bool(self.value)
    def __eq__(self, other): return self.value == other
    def __ne__(self, other): return self.value != other


class PanoramaTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.values = dict(Routingmode='panoramic', Renderwidth=1920, Renderheight=1080,
                           Panoramaoverlap=0., Output1track=3, Output2track=2, Output3track=1)
        self.ext._p = self.values.__getitem__
        self.ext.ownerComp = Mock(par=SimpleNamespace(Sharedtrack=Value(2)))

    def test_shared_track_any_cue_track_both_non_independent_layouts(self):
        for layout in ('identical', 'panoramic'):
            self.values['Routingmode'] = layout
            for track in (1, 2, 3):
                self.ext.ownerComp.par.Sharedtrack = Value(track)
                self.assertEqual([self.ext.OutputTrack(i) for i in (1,2,3)], [track]*3)

    def test_independent_track_assignments_unchanged(self):
        self.values['Routingmode'] = 'independent'
        self.assertEqual([self.ext.OutputTrack(i) for i in (1,2,3)], [3,2,1])

    def test_legacy_toe_without_shared_selector_uses_track_one(self):
        self.ext.ownerComp.par = SimpleNamespace()
        self.assertEqual(self.ext.OutputTrack(3), 1)

    def test_set_resolution_1080_4k_and_overlap(self):
        for width, height, overlap, expected in ((1920,1080,0,5760), (3840,2160,0,11520),
                                                (1920,1080,.25,4800), (1920,1080,.5,3840)):
            with self.subTest(width=width, overlap=overlap):
                self.values.update(Renderwidth=width, Renderheight=height, Panoramaoverlap=overlap)
                deck = Mock()
                self.ext._set_deck_resolution(deck)
                self.assertEqual(deck.par.Customwidth, expected)
                self.assertEqual(deck.par.Customheight, height)
                self.assertEqual(deck.par.Resolutionpreset, 'custom')
                deck.op.assert_not_called()

    def test_resize_live_prepared_and_editor_without_restarting(self):
        decks = {name: Mock(par=SimpleNamespace(Resolutionpreset=Value('custom'),
                         Customwidth=Value(1920), Customheight=Value(1080)))
                 for name in ('deck1_0', 'deck2_1', 'look_editor')}
        self.ext.ownerComp.op.side_effect = decks.get
        self.ext._set_deck_resolution = Mock()
        self.ext._sync_canvas_resolution()
        self.assertEqual(self.ext._set_deck_resolution.call_count, 3)
        for deck in decks.values():
            deck.op.assert_not_called()
            deck.destroy.assert_not_called()
        self.ext.ownerComp.initializeExtensions.assert_not_called()

    def test_unchanged_dimensions_are_not_reassigned(self):
        deck = Mock(par=SimpleNamespace(Resolutionpreset=Value('custom'),
                                        Customwidth=Value(5760), Customheight=Value(1080)))
        self.ext.ownerComp.op.side_effect = lambda name: deck if name == 'deck1_0' else None
        self.ext._set_deck_resolution = Mock()
        self.ext._sync_canvas_resolution()
        self.ext._set_deck_resolution.assert_not_called()

    def test_summary_layout_and_delivery_are_independent(self):
        show = Mock(par=SimpleNamespace(**{k:Value(v) for k,v in self.values.items()},
                    Sharedtrack=Value(2), Outputmode=Value('direct')))
        wall = Mock(par=SimpleNamespace(Sourcemode=Value('show')))
        show.parent.return_value.op.return_value = wall
        for delivery in ('direct', 'wall'):
            show.par.Outputmode = Value(delivery)
            self.assertIn('5760 x 1080 panorama', canvas_summary(show))
            self.assertIn('Track 2 -> P1 left / P2 center / P3 right', canvas_summary(show))
        wall.par.Sourcemode = Value('independent')
        self.assertIn('Wall source override', canvas_summary(show))

    def test_auto_size_for_all_layouts_and_overlap(self):
        for layout, overlap, width in (('panoramic',0,5760), ('panoramic',.25,4800),
                                        ('identical',0,1920), ('independent',0,1920)):
            self.assertEqual(canvas_size(layout,1920,1080,overlap), (width,1080))
        self.assertEqual(canvas_size('panoramic',3840,2160), (11520,2160))

    def test_auto_fit_crops_panorama_without_changing_other_modes(self):
        show = SimpleNamespace(par=SimpleNamespace(Cuemediafit=Value('auto'), Routingmode=Value('panoramic')))
        self.assertEqual(cue_media_fit(show), 'cover')
        for layout in ('identical', 'independent'):
            show.par.Routingmode = Value(layout)
            self.assertEqual(cue_media_fit(show), 'contain')
        for fit in ('contain', 'cover', 'stretch'):
            show.par.Cuemediafit = Value(fit)
            self.assertEqual(cue_media_fit(show), fit)

    def test_crop_uses_uniform_scale_for_landscape_portrait_and_wide_sources(self):
        canvas = (5760,1080)
        for source in ((1920,1080),(1080,1920),(7680,1080),(5760,1080)):
            extent = fit_extent(source,canvas,'cover')
            self.assertAlmostEqual(extent[0]*canvas[0]/source[0], extent[1]*canvas[1]/source[1])
            self.assertGreaterEqual(min(extent), 1)
        self.assertEqual(fit_extent((1920,1080), canvas, 'cover'), (1,3))

    def test_workflow_follows_canvas_without_overwriting_manual_preferences(self):
        show = SimpleNamespace(par=SimpleNamespace(Routingmode=Value('panoramic'),
            Renderwidth=Value(1920),Renderheight=Value(1080),Panoramaoverlap=Value(0),Cuemediafit=Value('auto')))
        demo = Mock(par=SimpleNamespace(Followshowcanvas=Value(True), Resolutionpreset=Value('custom'),
            Customwidth=Value(1234), Customheight=Value(678), Sourcefit=Value('contain')))
        demo.fetch.return_value = False
        demo.op.return_value = show
        self.assertEqual(workflow_size(demo), (5760,1080))
        self.assertEqual(workflow_fit(demo), 'cover')
        self.assertIn('Fill / Crop (no stretching)', workflow_summary(demo))
        demo.par.Followshowcanvas = Value(False)
        self.assertEqual(workflow_size(demo), (1234,678))
        self.assertEqual(workflow_fit(demo), 'contain')
        for preset, size in (('hd',(1920,1080)),('uhd4k',(3840,2160))):
            demo.par.Resolutionpreset = Value(preset)
            self.assertEqual(workflow_size(demo), size)

    def test_standalone_copy_and_runtime_deck_use_manual_size_and_fit(self):
        demo = Mock(par=SimpleNamespace(Followshowcanvas=Value(True), Resolutionpreset=Value('custom'),
            Customwidth=Value(960), Customheight=Value(180), Sourcefit=Value('cover')))
        demo.op.return_value = None
        demo.fetch.return_value = False
        self.assertEqual(workflow_size(demo), (960,180))
        self.assertEqual(workflow_fit(demo), 'cover')
        demo.fetch.return_value = True
        demo.op.return_value = Mock()
        self.assertEqual(workflow_size(demo), (960,180))
        self.assertEqual(workflow_fit(demo), 'cover')


if __name__ == '__main__':
    unittest.main()
