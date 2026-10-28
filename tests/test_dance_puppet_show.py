import json
from pathlib import Path
import runpy
import tempfile
import unittest

from tdimagefx import show

FLOW=runpy.run_path(str(Path(__file__).resolve().parents[1]/'touchdesigner/scripts/workflow.py'))


class PuppetShowTests(unittest.TestCase):
    def test_old_orders_migrate_without_moving_existing_stages(self):
        for branch in (False,True):
            order=list(FLOW['BRANCH_ORDER'] if branch else FLOW['DEFAULT_ORDER'])
            old=[x for x in reversed(order) if x!='dance_puppet']
            migrated=FLOW['validate_order'](old,branch)
            self.assertEqual([x for x in migrated if x!='dance_puppet'],old)
            self.assertEqual(migrated[migrated.index('layer_composite')-1],'dance_puppet')

    def test_legacy_order_and_branch_migration(self):
        for branch in (False,True):
            order=FLOW['validate_order'](FLOW['LEGACY_ORDER'],branch)
            self.assertIn('dance_puppet',order)
            self.assertEqual('image_composition' in order,not branch)

    def test_old_look_does_not_need_any_puppet_media(self):
        show.validate_look_media({},'.')
        self.assertEqual(show.resolve_puppet_files({},'.',enabled=False)['Renderfile'],'')

    def test_puppet_cue_needs_prepared_movie_not_original_video(self):
        with tempfile.TemporaryDirectory() as directory:
            movie=Path(directory)/'rgba.mov'; movie.touch()
            result=show.resolve_puppet_files({'Renderfile':'rgba.mov','Dancevideo':'no-longer-present.mp4'},directory)
            # macOS /var aliases and Windows 8.3 temp paths resolve canonically.
            self.assertEqual(result['Renderfile'],str(movie.resolve()))
            with self.assertRaises(ValueError): show.resolve_puppet_files({},directory)

    def test_only_passive_local_files(self):
        for values in ({'Python':'bad.py'},{'Renderfile':'http://remote/movie.mov'},{'Renderfile':12},{'Renderfile':'bad\x00.mov'}):
            with self.subTest(values=values),self.assertRaises(ValueError): show.resolve_puppet_files(values,'.',enabled=False)

    def test_live_has_no_prerecorded_requirement(self):
        show.resolve_puppet_files({},'.',selections={'Sourcemode':'live'})
        with self.assertRaises(ValueError): show.resolve_puppet_files({},'.',selections={'Sourcemode':'execute'})

    def test_look_animation_and_parameter_cue_support(self):
        look={'animation':{'dance_puppet':{'time':2.,'running':True}}}
        show.validate_look_animation(look)
        self.assertEqual(show.animation_time(look['animation'],'dance_puppet',3),5)
        cue=dict(show.new_cue(),kind='parameters',target='dance_puppet/Opacity',value=.4)
        self.assertEqual(show.validate_cue(cue)['value'],.4)

    def test_pulses_not_in_capture_controls(self):
        source=Path('touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
        self.assertIn('not parameter.isPulse',source)
        self.assertIn('"puppet_files"',source)
        module=runpy.run_path('touchdesigner/scripts/dance_puppet.py')
        controls=module['PARAMETERS']; names=[p[1] for p in controls]
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(next(p[3] for p in controls if p[1]=='Enabled'))
        self.assertFalse(next(p[3] for p in controls if p[1]=='Feedbackenabled'))
        self.assertTrue(next(p[3] for p in controls if p[1]=='Transparent'))

    def test_live_callbacks_and_internal_links_are_copy_safe(self):
        source=Path('touchdesigner/scripts/dance_puppet.py').read_text(encoding='utf-8')
        self.assertIn("live.par.callbacks='live_callbacks'",source)
        self.assertIn('c=scriptOp.parent()',source)
        self.assertIn('top.par.pixeldat=dat.name',source)
        self.assertIn('history.par.top=accumulation.name',source)
        self.assertNotIn('history.par.top=finished.name',source)
        # Store unattenuated transparent history; strength/background are a
        # display operation, never fed back recursively into the trail.
        module=runpy.run_path('touchdesigner/scripts/dance_puppet.py')
        self.assertNotIn('p=mix(a,p,uTrail.y)',module['TRAIL'])
        self.assertIn('uFinish',module['FINISH'])

    def test_live_buffers_not_serialized_with_cues(self):
        source=Path('touchdesigner/scripts/dance_puppet_runtime.py').read_text(encoding='utf-8')
        self.assertIn('global _live_maps',source)
        self.assertNotIn("c.store('puppet_live_maps'",source)
