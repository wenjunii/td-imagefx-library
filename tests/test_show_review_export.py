import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from touchdesigner.scripts import show_review_export as review


class ReviewExportTests(unittest.TestCase):
    def settings(self, **changes):
        values = dict(source='cue', preset='1080p', width=1920, height=1080,
                      fps=30, duration=10, start=0, codec='h264')
        values.update(changes)
        return review.export_settings(**values)

    def test_default_export(self):
        self.assertEqual(self.settings()['frames'], 300)
        self.assertEqual(self.settings()['width'], 1920)

    def test_all_resolution_presets(self):
        for preset, size in [('1080p',(1920,1080)),('4k',(3840,2160)),('720p',(1280,720))]:
            result = self.settings(preset=preset)
            self.assertEqual((result['width'],result['height']),size)

    def test_custom_resolution(self):
        result = self.settings(preset='custom',width=2048,height=1080)
        self.assertEqual(result['width'],2048)

    def test_reject_invalid_dimensions(self):
        for n in (0,15,1919,4098,720.5,float('nan'),float('inf')):
            with self.subTest(n=n), self.assertRaises(ValueError):
                self.settings(preset='custom',width=n)

    def test_supported_framerates(self):
        for fps in (24,25,30,50,60):
            self.assertEqual(self.settings(fps=fps)['frames'],10*fps)

    def test_reject_invalid_timing(self):
        for key, values in [('fps',(0,29,120,float('nan'))),('duration',(0,-1,3601,float('inf'))),('start',(-1,86401,float('nan')))]:
            for value in values:
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    self.settings(**{key:value})

    def test_quantize_duration(self):
        self.assertEqual(self.settings(duration=.05)['frames'],2)
        self.assertAlmostEqual(self.settings(duration=.05)['duration'],2/30)

    def test_reject_untrusted_menu_values(self):
        for key in ('source','preset','codec'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.settings(**{key:'unknown'})

    def show(self):
        show = Mock(path='/show')
        cue = {'kind':'visual','name':'saved','look':{'toggles':{'Shadowenabled':True}}}
        show.ext.ShowControlExt = SimpleNamespace(engine=SimpleNamespace(state='stopped'),
            document={'cues':[cue]},_look_edit=None,_capture_look=Mock(return_value={'new':True}))
        show.par.Selectedcue.eval.return_value = 1
        return show

    def test_saved_cue_is_deep_copy(self):
        show = self.show()
        result = review.selected_snapshot(show,'cue')
        result['look']['toggles']['Shadowenabled'] = False
        self.assertTrue(show.ext.ShowControlExt.document['cues'][0]['look']['toggles']['Shadowenabled'])

    def test_missing_selected_cue(self):
        show = self.show()
        show.par.Selectedcue.eval.return_value = 0
        with self.assertRaisesRegex(ValueError,'Select a visual cue'):
            review.selected_snapshot(show,'cue')

    def test_nonvisual_cue_rejected(self):
        show=self.show()
        show.ext.ShowControlExt.document['cues'][0]['kind']='audio'
        with self.assertRaisesRegex(ValueError,'Only Visual'):
            review.selected_snapshot(show,'cue')

    def test_running_and_paused_rejected(self):
        for state in ('running','paused'):
            show=self.show()
            show.ext.ShowControlExt.engine.state=state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError,'STOP ALL'):
                review.selected_snapshot(show,'cue')

    def test_draft_requires_recall(self):
        with self.assertRaisesRegex(ValueError,'Recall Look'):
            review.selected_snapshot(self.show(),'draft')

    def test_draft_snapshot_without_commit(self):
        show=self.show()
        ext=show.ext.ShowControlExt
        original=copy.deepcopy(ext.document)
        ext._look_edit={'cue':ext.document['cues'][0],'deck':show.op.return_value}
        result=review.selected_snapshot(show,'draft')
        self.assertEqual(result['look'],{'new':True})
        self.assertEqual(ext.document,original)

    def test_review_taps_final_wall(self):
        show=self.show()
        show.par.Reviewroute.eval.return_value='wall'
        for i in (1,2,3):
            review.review_path(show,i)
            show.parent().op.assert_called_with('wall_output/p{}_out'.format(i))

    def test_review_taps_final_atlas(self):
        show=self.show()
        show.par.Reviewroute.eval.return_value='atlas'
        review.review_path(show,2)
        show.op.assert_called_with('out2_projector')

    def test_review_missing_route_is_black(self):
        show=self.show()
        show.par.Reviewroute.eval.return_value='wall'
        show.parent().op.return_value=None
        show.op.return_value.path='/show/black'
        self.assertEqual(review.review_path(show,1),'/show/black')

    def test_review_invalid_index(self):
        with self.assertRaises(ValueError):
            review.review_path(self.show(),4)

    def test_embedded_runtime_compiles(self):
        text=Path(review.__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
        scope={}
        exec(compile(text,'embedded','exec'),scope)
        self.assertIn('start_export',scope)
        self.assertIn('startup',scope)
        self.assertNotIn('install',scope)

    def test_export_does_not_change_global_clock_or_output_windows(self):
        source=Path(review.__file__).read_text(encoding='utf-8')
        for forbidden in ('project.cookRate =','project.realTime =','winopen.pulse','perform.pulse','Openoutputs('):
            self.assertNotIn(forbidden,source)
        self.assertIn("jobdir.mkdir(exist_ok=False)",source)

    def test_inspector_fits_fixed_design_canvas(self):
        nodes = {name: SimpleNamespace(par=SimpleNamespace()) for name in
                 ('header', 'status_display', 'cue_inspector')}
        class Parameters(SimpleNamespace):
            def __setitem__(self, name, value):
                setattr(self, name, value)
        show = SimpleNamespace(par=Parameters(), op=nodes.get)
        review.configure_panel_layout(show)
        inspector = nodes['cue_inspector'].par
        self.assertEqual((show.par.w, show.par.h), (1660, 900))
        self.assertFalse(show.par.sizefromwindow)
        self.assertEqual(show.par.fit, 'off')
        self.assertEqual(inspector.w, 720)
        self.assertEqual(inspector.compress, 1)
        # Built-in Container COMP parameters must not participate in the
        # embedded inspector's native field sizing (right-edge clipping).
        self.assertFalse(inspector.builtin)
        self.assertTrue(inspector.custom)
        self.assertEqual(show.par.marginr, 0)
        self.assertLessEqual(inspector.x + inspector.w, show.par.w - 20)
        self.assertLessEqual(inspector.y + inspector.h, show.par.h)
        self.assertEqual(nodes['header'].par.w, 1620)
        # This minimal stand-in deliberately has no show extension or custom
        # cue parameters: the UI-only helper must never access either.

    def test_layout_helper_is_safe_for_partially_built_panel(self):
        class Parameters(SimpleNamespace):
            def __setitem__(self, name, value):
                setattr(self, name, value)
        show = SimpleNamespace(par=Parameters(), op=lambda name: None)
        review.configure_panel_layout(show)
        self.assertEqual(show.par.fit, 'off')

    def test_native_audit_isolates_cue_editor_state(self):
        source = (Path(review.__file__).parent / 'validate_show_review_export.py').read_text(encoding='utf-8')
        self.assertIn("original.parent().copy(original, name='show_review_export_qa')", source)
        self.assertIn("original.ext.ShowControlExt.document==STATE['document']", source)
        self.assertIn("original.customPars", source)
        self.assertIn('s.destroy()', source)
        self.assertNotIn("e.SelectCue(1)\n    e.Refresh()", source)


if __name__ == '__main__':
    unittest.main()
