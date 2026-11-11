"""Per-cue routes, old-show compatibility and projector selection without TD."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt
from touchdesigner.scripts import cue_projection
from touchdesigner.scripts.show_output_mode import cue_media_fit


class CueProjectionTests(unittest.TestCase):
    def test_routing_expressions_read_revision_value_not_discarded_par_object(self):
        expression=cue_projection.routing_expression('parent().ProjectionInput(2, 1)')
        self.assertEqual(expression,'(parent().par.Cueroutingrevision.eval(), parent().ProjectionInput(2, 1))[1]')
        class Revision:
            def __init__(self): self.reads=0
            def eval(self): self.reads+=1; return self.reads
        revision=Revision()
        parent=SimpleNamespace(par=SimpleNamespace(Cueroutingrevision=revision),ProjectionInput=lambda *args:'track1_source1')
        self.assertEqual(eval(expression,{'parent':lambda:parent}),'track1_source1')
        self.assertEqual(revision.reads,1)

    def test_legacy_default_and_all_routes_roundtrip(self):
        cue = show.new_cue(); del cue['projection']
        self.assertEqual(show.validate_cue(cue)['projection'], 'inherit')
        self.assertEqual(set(cue_projection.ROUTES), set(show.PROJECTION_ROUTES))
        self.assertEqual(len(cue_projection.ROUTES), len(cue_projection.LABELS))
        for route in show.PROJECTION_ROUTES:
            document = dict(kind=show.SHOW_KIND, schema_version=1, cues=[dict(cue, projection=route)])
            self.assertEqual(show.validate_show(json.loads(json.dumps(document)))['cues'][0]['projection'], route)
        for value in (None, [], {}, 1, True, 'wall', 'p4'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                show.validate_cue(dict(cue, projection=value))

    def test_destinations_exhaustive_under_each_global_layout(self):
        for layout in ('cue', 'independent', 'identical', 'panoramic'):
            tracks = [1, 2, 3] if layout in {'cue', 'independent'} else [2, 2, 2]
            for route, outputs in show.PROJECTION_ROUTES.items():
                cue = dict(show.new_cue(), track=2, projection=route)
                actual = tuple(i for i in (1, 2, 3) if show.cue_projection_sample(cue, i, layout, tracks)[0])
                self.assertEqual(actual, tuple(i for i in (1, 2, 3) if tracks[i-1] == 2) if outputs is None else outputs)

    def test_explicit_single_and_repeated_content_not_sliced_by_global_panorama(self):
        for route in ('p1', 'p2', 'p3', 'all'):
            cue = dict(show.new_cue(), projection=route)
            for output in (1, 2, 3):
                self.assertEqual(show.cue_projection_sample(cue, output, 'panoramic', [1]*3)[1:], (0, 1))

    def test_panorama_slices_and_overlap(self):
        cue = dict(show.new_cue(), projection='panoramic')
        for overlap in (0., .25, .5):
            factor = 3-2*overlap
            for i in (1, 2, 3):
                active, start, end = show.cue_projection_sample(cue, i, 'independent', [1,2,3], overlap)
                self.assertEqual(active, 1)
                self.assertAlmostEqual(start, (i-1)*(1-overlap)/factor)
                self.assertAlmostEqual(end-start, 1/factor)
            self.assertAlmostEqual(end, 1)

    def test_simultaneous_tracks_and_newest_wins(self):
        items = {i: dict(cue=dict(show.new_cue(), track=i, projection='p'+str(i)), route_order=i) for i in (1,2,3)}
        original = copy.deepcopy(items)
        self.assertEqual([show.cue_output_track(items, i, 'identical', [1]*3) for i in (1,2,3)], [1,2,3])
        self.assertEqual(items, original)
        items[2]['cue']['projection'] = 'all'
        self.assertEqual([show.cue_output_track(items, i, 'identical', [1]*3) for i in (1,2,3)], [2,2,3])
        items[1]['route_order'] = 4
        self.assertEqual(show.cue_output_track(items, 1, 'identical', [1]*3), 1)

    def test_explicit_cue_has_priority_over_newer_global_fallback(self):
        items = {
            1: dict(cue=dict(show.new_cue(),track=1),route_order=100),
            2: dict(cue=dict(show.new_cue(),track=2,projection='p2'),route_order=1),
        }
        self.assertEqual([show.cue_output_track(items,i,'identical',[1]*3) for i in (1,2,3)], [1,2,1])
        items[2]['cue']['projection']='panoramic'
        self.assertEqual([show.cue_output_track(items,i,'identical',[1]*3) for i in (1,2,3)], [2,2,2])

    def test_follow_show_mode_has_nonrecursive_track_fallback(self):
        ext=ShowControlExt.__new__(ShowControlExt)
        ext.model=show
        values=dict(Routingmode='cue',Output1track=3,Output2track=1,Output3track=2,
                    Renderwidth=1920,Renderheight=1080,Panoramaoverlap=0)
        ext._p=values.__getitem__
        ext.ownerComp=SimpleNamespace(par=SimpleNamespace())
        ext.tracks={}
        self.assertEqual([ext.OutputTrack(i) for i in (1,2,3)],[3,1,2])
        for track in (1,2,3):
            self.assertEqual(ext.TrackCanvasWidth(track),1920)
        self.assertIn('cue',cue_projection.SHOW_MODES)
        self.assertEqual(len(cue_projection.SHOW_MODES),len(cue_projection.SHOW_LABELS))

    def test_route_selection_commits_only_route_without_selecting_or_applying_editor(self):
        ext=ShowControlExt.__new__(ShowControlExt)
        ext.model=show; ext._busy=False
        ext.document=dict(cues=[show.new_cue()])
        ext._p={'Selectedcue':1,'Cueprojection':'p2'}.__getitem__
        ext._guard_edit=Mock(); ext._replace_cues=Mock(); ext._status=Mock()
        before=copy.deepcopy(ext.document['cues'][0])
        ext.SetCueProjection()
        ext._replace_cues.assert_called_once_with([dict(before,projection='p2')])
        self.assertEqual(ext.document['cues'][0],before)
        ext._busy=True; ext.SetCueProjection()
        self.assertEqual(ext._replace_cues.call_count,1)

    def test_channel_schema_legacy_defaults_and_roundtrip(self):
        old=show.new_cue(); del old['channels']
        self.assertEqual(show.validate_cue(old)['channels'],'routing')
        self.assertEqual(set(cue_projection.CHANNELS),set(show.OUTPUT_CHANNELS))
        for channels in show.OUTPUT_CHANNELS:
            cue=show.validate_cue(dict(old,channels=channels))
            self.assertEqual(show.validate_cue(json.loads(json.dumps(cue))),cue)
        for invalid in (None,[],[1,2],3,True,'1,2','all_tracks'):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                show.validate_cue(dict(old,channels=invalid))

    def test_explicit_channels_override_route_and_playback_lane(self):
        for layout in ('cue','identical','panoramic','independent'):
            for track in (1,2,3):
                for route in show.PROJECTION_ROUTES:
                    for channels, outputs in show.OUTPUT_CHANNELS.items():
                        if outputs is None: continue
                        cue=dict(show.new_cue(),track=track,projection=route,channels=channels)
                        actual=tuple(i for i in (1,2,3) if show.cue_projection_sample(cue,i,layout,[1,2,3])[0])
                        self.assertEqual(actual,outputs)
                        items={track:dict(cue=cue,side=1)}
                        for i in outputs:
                            self.assertEqual(show.cue_output_track(items,i,layout,[1,1,1]),track)

    def test_panorama_fits_only_selected_channels_without_gaps(self):
        for channels,outputs in show.OUTPUT_CHANNELS.items():
            if outputs is None: continue
            cue=dict(show.new_cue(),projection='panoramic',channels=channels)
            for overlap in (0,.25,.5):
                factor=len(outputs)-(len(outputs)-1)*overlap
                self.assertEqual(show.cue_render_width(cue,'identical',1920,overlap),int(1920*factor))
                for position,i in enumerate(outputs):
                    enabled,start,end=show.cue_projection_sample(cue,i,'identical',[1,1,1],overlap)
                    self.assertEqual(enabled,1)
                    self.assertAlmostEqual(start,position*(1-overlap)/factor)
                    self.assertAlmostEqual(end-start,1/factor)
                self.assertAlmostEqual(end,1)

    def test_channel_change_commits_only_channels(self):
        ext=ShowControlExt.__new__(ShowControlExt); ext.model=show; ext._busy=False
        cue=dict(show.new_cue(),track=3,projection='panoramic')
        ext.document=dict(cues=[cue]); ext._p={'Selectedcue':1,'Cuechannels':'1_3'}.__getitem__
        ext._guard_edit=Mock(); ext._replace_cues=Mock(); ext._status=Mock()
        ext.SetCueProjection('Cuechannels')
        ext._replace_cues.assert_called_once_with([dict(cue,channels='1_3')])

    def test_excluded_destinations_black_not_global_leak(self):
        items = {1: dict(cue=dict(show.new_cue(), projection='p1'), started=2)}
        self.assertEqual([show.cue_output_track(items, i, 'identical', [1]*3) for i in (1,2,3)], [1,0,0])
        self.assertEqual(show.cue_output_track({}, 2, 'independent', [1,2,3]), 2)

    def test_old_route_remains_available_only_during_fade(self):
        old = dict(cue=dict(show.new_cue(), projection='p1'))
        item = dict(cue=dict(show.new_cue(), projection='p2'), old=old, fading=True)
        self.assertEqual(show.cue_output_track({1:item}, 1, 'identical', [1]*3), 1)
        item['fading'] = False
        self.assertEqual(show.cue_output_track({1:item}, 1, 'identical', [1]*3), 0)

    def test_runtime_samples_old_and_new_destinations_independently(self):
        ext = ShowControlExt.__new__(ShowControlExt)
        ext.model = show
        values = dict(Routingmode='identical', Sharedtrack=1, Panoramaoverlap=0, Renderwidth=1920, Renderheight=1080)
        ext._p = values.__getitem__
        ext.ownerComp = SimpleNamespace(par=SimpleNamespace(Sharedtrack=SimpleNamespace(eval=lambda:1)))
        ext.tracks = {1:dict(cue=dict(show.new_cue(), projection='p2'), side=1, fading=True,
                             old=dict(cue=dict(show.new_cue(), projection='p1')))}
        self.assertEqual(ext.ProjectionSample(1,0), (1,0,1))
        self.assertEqual(ext.ProjectionSample(1,1), (0,0,1))
        self.assertEqual(ext.ProjectionSample(2,0), (0,0,1))
        self.assertEqual(ext.ProjectionSample(2,1), (1,0,1))
        self.assertEqual(ext.ProjectionInput(3,1), 'black')
        ext.tracks[1]['cue']['projection']='panoramic'
        self.assertEqual(ext.TrackCanvasWidth(1), 5760)
        ext.tracks[1]['cue']['projection']='p2'
        values['Routingmode']='panoramic'
        self.assertEqual(ext.TrackCanvasWidth(1), 1920)
        revision=SimpleNamespace(val=0)
        revision.eval=lambda:revision.val
        ext.ownerComp.par.Cueroutingrevision=revision
        ext.UpdateCueRouting()
        self.assertEqual(revision.val,1)
        ext.UpdateCueRouting()
        self.assertEqual(revision.val,1)
        ext.tracks[1]['cue']['projection']='p3'
        ext.UpdateCueRouting()
        self.assertEqual(revision.val,2)

    def test_deck_auto_media_fit_uses_cue_route(self):
        host = SimpleNamespace(par=SimpleNamespace(Cuemediafit=SimpleNamespace(eval=lambda:'auto'), Routingmode='panoramic'))
        deck = Mock()
        for route, expected in (('inherit','cover'), ('p1','contain'), ('all','contain'), ('panoramic','cover')):
            deck.fetch.return_value=route
            self.assertEqual(cue_media_fit(host, deck), expected)
        host.par.Routingmode='independent'; deck.fetch.return_value='panoramic'
        self.assertEqual(cue_media_fit(host, deck), 'cover')


if __name__ == '__main__':
    unittest.main()
