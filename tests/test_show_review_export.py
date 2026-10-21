import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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

    def test_wall_export_has_fixed_uhd_canvas(self):
        for preset in ('1080p', '4k', '720p', 'custom'):
            result = self.settings(source='wall', preset=preset, width=640, height=360, start=75)
            self.assertEqual((result['width'], result['height']), (3840, 2160))
            self.assertEqual(result['start'], 0)

    def test_wall_ignores_disabled_custom_dimensions(self):
        result = self.settings(source='wall', preset='custom', width=1919, height=1)
        self.assertEqual(result['width'], 3840)

    def test_wall_still_validates_duration_fps_codec_and_preset(self):
        for changes in ({'duration': 0}, {'fps': 29}, {'codec': 'bad'}, {'preset': 'bad'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.settings(source='wall', **changes)

    def wall_show(self):
        show = self.show()
        wall = show.parent().op.return_value
        wall.par.Monitorenabled = True
        target = wall.op.return_value
        target.family, target.width, target.height = 'TOP', 3840, 2160
        target.errors.return_value = ''
        return show, wall, target

    def test_wall_target_is_the_actual_final_canvas(self):
        show, wall, target = self.wall_show()
        self.assertIs(review.wall_export_target(show), target)
        show.parent().op.assert_called_with('wall_output')
        wall.op.assert_called_with('out1_wall_4k')
        show.ext.ShowControlExt._capture_look.assert_not_called()

    def test_wall_allows_running_show_without_recalling_a_cue(self):
        show, wall, target = self.wall_show()
        show.ext.ShowControlExt.engine.state = 'running'
        show.par.Selectedcue.eval.return_value = 0
        self.assertIs(review.wall_export_target(show), target)
        self.assertEqual(show.ext.ShowControlExt.engine.state, 'running')

    def test_wall_rejects_disabled_confidence_without_enabling_it(self):
        show, wall, target = self.wall_show()
        wall.par.Monitorenabled = False
        with self.assertRaisesRegex(ValueError, 'Enable Confidence'):
            review.wall_export_target(show)
        self.assertFalse(wall.par.Monitorenabled)

    def test_wall_missing_and_wrong_type_fail_closed(self):
        show, wall, target = self.wall_show()
        show.parent().op.return_value = None
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            review.wall_export_target(show)
        show.parent().op.return_value = wall
        target.family = 'CHOP'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            review.wall_export_target(show)

    def test_wall_rejects_license_limited_resolution(self):
        show, wall, target = self.wall_show()
        target.width = 1280
        with self.assertRaisesRegex(ValueError, '3840 x 2160'):
            review.wall_export_target(show)

    def test_wall_rejects_shader_errors(self):
        show, wall, target = self.wall_show()
        target.errors.return_value = 'Shader compilation failed'
        with self.assertRaisesRegex(ValueError, 'Shader compilation failed'):
            review.wall_export_target(show)

    def test_wall_reads_encoder_counts_not_callback_count(self):
        info = Mock()
        channels = {'total_frames_written': [42], 'total_frames_dropped': [3]}
        info.__getitem__ = Mock(side_effect=channels.get)
        job = {'info': info}
        review._wall_counts(job)
        self.assertEqual((job['index'], job['dropped']), (42, 3))

    def test_stale_callback_cannot_touch_a_new_export(self):
        show = self.show()
        show.fetch.return_value = {'id': 'new'}
        with patch.object(review, '_wall_step') as step:
            review.step(show, 'cancelled-old-job')
            step.assert_not_called()

    def test_wall_writer_bridges_comp_boundary_with_local_select(self):
        parent, writer, selector, target = Mock(), Mock(), Mock(), Mock(path='/demo/wall/out1_wall_4k')
        parent.create.side_effect = [writer, selector]
        writer.inputConnectors = [Mock()]
        selector.outputConnectors = [Mock()]
        with patch.dict('sys.modules', {'td': SimpleNamespace(moviefileoutTOP='movie', selectTOP='select')}):
            self.assertIs(review._writer(parent, target, Path('render.mp4'), self.settings(source='wall')), writer)
        self.assertEqual(selector.par.top, target.path)
        selector.outputConnectors[0].connect.assert_called_once_with(writer.inputConnectors[0])
        self.assertEqual(writer.par.type, 'movie')
        self.assertFalse(writer.par.pause)
        self.assertEqual(writer.par.lengthunit, 'seconds')
        self.assertEqual(writer.par.length, 10)
        self.assertEqual((writer.par.resolutionw, writer.par.resolutionh), (3840, 2160))
        self.assertEqual(writer.par.audiochop, '')

    def test_stop_wall_saves_valid_prefix(self):
        show = self.show()
        job = {'settings': {'source': 'wall'}, 'index': 8}
        show.fetch.return_value = job
        with patch.object(review, '_wall_counts'), patch.object(review, 'finish_export') as finish:
            review.stop_wall_export(show)
            finish.assert_called_once_with(show, 'COMPLETE')

    def test_stop_wall_does_not_claim_empty_file_complete(self):
        show = self.show()
        show.fetch.return_value = {'settings': {'source': 'wall'}, 'index': 0}
        with patch.object(review, '_wall_counts'), patch.object(review, 'finish_export') as finish:
            review.stop_wall_export(show)
            self.assertTrue(finish.call_args.args[1].startswith('CANCELLED'))

    def test_stop_and_save_does_not_interrupt_offline_export(self):
        show = self.show()
        show.fetch.return_value = {'settings': {'source': 'cue'}}
        with self.assertRaisesRegex(ValueError, 'only for a running 2x2'):
            review.stop_wall_export(show)

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

    def test_auto_review_follows_output_mode(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'auto'
        for route, selected in (('wall', 'wall'), ('atlas', 'all')):
            show.par.Reviewroute.eval.return_value = route
            self.assertEqual(review.review_selection(show), selected)

    def test_wall_review_uses_actual_packed_4k_output(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'wall'
        target = review.review_target(show)
        show.parent().op.assert_called_once_with('wall_output/out1_wall_4k')
        self.assertIs(target, show.parent().op.return_value)

    def test_confidence_review_uses_actual_monitor_quadrant(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'confidence'
        review.review_target(show)
        show.parent().op.assert_called_once_with('wall_output/comp_monitor_out')

    def test_side_by_side_review_remains_available(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'all'
        review.review_target(show)
        show.op.assert_called_once_with('projector_review')

    def test_single_projector_review_uses_selected_route(self):
        for i in (1, 2, 3):
            show = self.show()
            show.par.Reviewprojector.eval.return_value = str(i)
            show.par.Reviewroute.eval.return_value = 'wall'
            review.review_target(show)
            show.parent().op.assert_called_with('wall_output/p{}_out'.format(i))

    def test_missing_wall_review_is_black_not_another_route(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'wall'
        show.parent().op.return_value = None
        self.assertIs(review.review_target(show), show.op.return_value)
        show.op.assert_called_once_with('black')

    def test_review_size_preserves_aspect_and_fits_panel(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'wall'
        target = show.parent().op.return_value
        for width, height in ((3840, 2160), (864, 162), (1080, 1920), (5760, 1080)):
            target.width, target.height = width, height
            w, h = review.review_size(show)
            self.assertLessEqual(w, 880)
            self.assertLessEqual(h, 165)
            self.assertAlmostEqual(w / h, width / height, delta=.01)

    def test_wall_heading_explains_quadrants_and_inactive_route(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'wall'
        show.par.Reviewroute.eval.return_value = 'atlas'
        label = review.review_heading(show)
        self.assertIn('TL=P1', label)
        self.assertIn('BR=CONFIDENCE', label)
        self.assertIn('wall preview only', label)

    def test_enlarge_wall_opens_only_an_operator_viewer(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'wall'
        self.assertTrue(review.on_pulse(show, 'Openprojectorreview'))
        show.parent().op.return_value.openViewer.assert_called_once_with()
        show.Action.assert_not_called()
        show.op.assert_not_called()

    def test_invalid_review_view_is_rejected(self):
        show = self.show()
        show.par.Reviewprojector.eval.return_value = 'untrusted'
        with self.assertRaisesRegex(ValueError, 'Review View'):
            review.review_target(show)

    def test_embedded_runtime_compiles(self):
        text=Path(review.__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
        scope={}
        exec(compile(text,'embedded','exec'),scope)
        self.assertIn('start_export',scope)
        self.assertIn('startup',scope)
        self.assertNotIn('install',scope)

    def test_wall_aliases_cover_safety_and_source_controls(self):
        targets = [target for _, target, _ in review.WALL_BINDINGS]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(set(targets), {'Masterblackout', 'Enabled', 'Blackout',
            'Sourcemode', 'Mastertop', 'Projector1top', 'Projector2top',
            'Projector3top', 'Fit', 'Testpattern', 'Monitorenabled', 'Showstats',
            'Displayindex', 'Allowprimary'})

    def test_wall_buttons_delegate_once_to_existing_safety_controller(self):
        for alias, target in review.WALL_ACTIONS.items():
            with self.subTest(alias=alias):
                show = self.show()
                wall = show.parent().op.return_value
                self.assertTrue(review.on_pulse(show, alias))
                wall.op.assert_called_once_with('controller')
                wall.op.return_value.module.action.assert_called_once_with(wall, target)
                show.Action.assert_not_called()

    def test_wall_unavailable_fails_without_changing_export_status(self):
        show = self.show()
        show.parent().op.return_value = None
        original = show.par.Exportstatus
        self.assertFalse(review.on_pulse(show, 'Wallopen'))
        self.assertIn('unavailable', show.par.Wallactionstatus)
        self.assertIs(show.par.Exportstatus, original)

    def test_wall_controller_error_does_not_open_an_alternative_window(self):
        show = self.show()
        wall = show.parent().op.return_value
        wall.op.return_value.module.action.side_effect = ValueError('Display unavailable')
        self.assertFalse(review.on_pulse(show, 'Wallopen'))
        self.assertEqual(show.par.Wallactionstatus, 'Display unavailable')
        show.op.assert_not_called()

    def test_wall_alias_installer_requires_existing_output(self):
        show = self.show()
        show.parent().op.return_value = None
        with self.assertRaisesRegex(ValueError, 'Install wall_output'):
            review.install_wall_controls(show)
        show.appendCustomPage.assert_not_called()

    def test_unknown_review_action_is_not_dispatched(self):
        show = self.show()
        self.assertFalse(review.on_pulse(show, 'UnknownAction'))
        show.parent.assert_not_called()

    def test_wall_callback_guard_preserves_look_editor_actions(self):
        look = "    if par.name in ('Editlookcontrols', 'Openlookpreview'):\n        return\n"
        old = "    if par.name in ('Openprojectorreview', 'Startexport', 'Cancelexport'):\n        return\n"
        callback = 'def onPulse(par):\n' + look + old + '    parent().Action(par.name)\n'
        guarded = review.guard_show_actions(callback)
        self.assertIn(look, guarded)
        self.assertNotIn(old, guarded)
        self.assertIn("module.ACTIONS:", guarded)
        self.assertEqual(review.guard_show_actions(guarded), guarded)

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
