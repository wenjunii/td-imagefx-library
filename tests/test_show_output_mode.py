"""Output delivery safety and routing, without physical display side effects."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from touchdesigner.scripts import show_output_mode as mode
from touchdesigner.scripts import show_review_export as review


class OutputModeTests(unittest.TestCase):
    displays = [dict(index=i, primary=i == 0, width=3840 if i == 2 else 1920, height=2160 if i == 2 else 1080)
                for i in range(4)]

    def show(self, selected='direct'):
        nodes = {n: Mock(name=n, isOpen=False) for n in (*mode.DIRECT_NAMES, 'audience_window')}
        wall = Mock()
        wall.op.return_value = Mock(isOpen=False)
        show = Mock(par=SimpleNamespace(Outputmode=selected, Outputstatus='old', Masterblackout=True))
        show.op.side_effect = nodes.get
        show.parent.return_value.op.return_value = wall
        show.fetch.return_value = None
        return show, nodes, wall

    def test_three_independent_display_assignments(self):
        result = mode.direct_plan([1, 2, 3], self.displays)
        self.assertEqual([(p, d['index']) for p, d in result], [(1, 1), (2, 2), (3, 3)])

    def test_unused_outputs_are_not_opened(self):
        self.assertEqual([p for p, d in mode.direct_plan([-1, 2, -1], self.displays)], [2])

    def test_no_assignment_rejected(self):
        with self.assertRaisesRegex(ValueError, 'at least one'):
            mode.direct_plan([-1, -1, -1], self.displays)

    def test_disconnected_display_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not connected'):
            mode.direct_plan([1, 22, -1], self.displays)

    def test_duplicate_display_rejected_before_open(self):
        with self.assertRaisesRegex(ValueError, 'different display'):
            mode.direct_plan([1, 1, -1], self.displays)

    def test_primary_requires_explicit_override(self):
        with self.assertRaisesRegex(ValueError, 'protected'):
            mode.direct_plan([0, -1, -1], self.displays)
        self.assertEqual(mode.direct_plan([0, -1, -1], self.displays, True)[0][0], 1)

    def test_close_all_includes_legacy_and_both_routes(self):
        show, nodes, wall = self.show()
        self.assertTrue(mode.on_pulse(show, 'Closealloutputs'))
        for w in nodes.values():
            w.par.winclose.pulse.assert_called_once()
        wall.op.return_value.par.winclose.pulse.assert_called_once()
        self.assertTrue(show.par.Masterblackout)

    def test_mode_change_closes_without_changing_cues(self):
        show, nodes, wall = self.show()
        mode.changed(show, 'Outputmode')
        for w in nodes.values():
            w.par.winclose.pulse.assert_called_once()
            w.par.winopen.pulse.assert_not_called()
        show.ext.assert_not_called()
        self.assertTrue(show.par.Masterblackout)

    def test_direct_settings_do_not_interrupt_wall(self):
        show, nodes, wall = self.show('wall')
        mode.changed(show, 'Directdisplay1')
        show.op.assert_not_called()

    def test_direct_resolution_change_closes_windows(self):
        show, nodes, wall = self.show()
        mode.changed(show, 'Output2width')
        nodes['direct_window2'].par.winclose.pulse.assert_called_once()

    def test_unrelated_cue_edit_does_not_close_windows(self):
        show, nodes, wall = self.show()
        mode.changed(show, 'Track')
        show.op.assert_not_called()

    def test_open_is_blocked_during_export(self):
        show, nodes, wall = self.show()
        show.fetch.return_value = {'stage': 'rendering'}
        self.assertFalse(mode.on_pulse(show, 'Openoutput'))
        show.op.assert_not_called()
        self.assertIn('video export or wall recording', show.par.Outputstatus)

    def test_check_never_opens_or_closes_windows(self):
        show, nodes, wall = self.show()
        with patch.object(mode, 'check', return_value=([(2, self.displays[2])], 'ready')):
            self.assertTrue(mode.on_pulse(show, 'Checkoutput'))
        show.op.assert_not_called()

    def test_direct_open_only_opens_validated_selection(self):
        show, nodes, wall = self.show()
        with patch.object(mode, 'check', return_value=([(2, self.displays[2])], 'ready')):
            self.assertTrue(mode.on_pulse(show, 'Openoutput'))
        nodes['direct_window2'].par.winopen.pulse.assert_called_once()
        for n in ('direct_window1', 'direct_window3', 'audience_window'):
            nodes[n].par.winopen.pulse.assert_not_called()
        self.assertTrue(show.par.Masterblackout)

    def test_invalid_selection_does_not_fall_back_to_another_route(self):
        show, nodes, wall = self.show()
        with patch.object(mode, 'check', side_effect=ValueError('bad display')):
            self.assertFalse(mode.on_pulse(show, 'Openoutput'))
        show.op.assert_not_called()
        self.assertIn('bad display', show.par.Outputstatus)

    def test_partial_open_failure_closes_every_window(self):
        show, nodes, wall = self.show()
        nodes['direct_window2'].par.winopen.pulse.side_effect = RuntimeError('unplugged')
        with patch.object(mode, 'check', return_value=([(1, {}), (2, {})], 'ready')):
            self.assertFalse(mode.on_pulse(show, 'Openoutput'))
        for w in nodes.values():
            self.assertEqual(w.par.winclose.pulse.call_count, 2)

    def test_wall_open_delegates_to_existing_display_safety(self):
        show, nodes, wall = self.show('wall')
        wall.par.Status.eval.return_value = 'opened'
        with patch.object(mode, 'check', return_value=(None, 'ready')):
            self.assertTrue(mode.on_pulse(show, 'Openoutput'))
        wall.op.return_value.module.action.assert_called_once_with(wall, 'Openwall')
        for w in nodes.values():
            w.par.winopen.pulse.assert_not_called()

    def test_startup_never_opens_any_route(self):
        show, nodes, wall = self.show()
        mode.startup(show)
        for w in nodes.values():
            w.par.winclose.pulse.assert_called_once()
            w.par.winopen.pulse.assert_not_called()

    def test_unknown_action_is_ignored(self):
        show, nodes, wall = self.show()
        self.assertFalse(mode.on_pulse(show, 'Go'))
        show.op.assert_not_called()

    def test_export_interlock_includes_all_direct_windows(self):
        show, nodes, wall = self.show()
        result = review._export_windows(show)
        for w in nodes.values():
            self.assertIn(w, result)
        self.assertEqual(len(result), 5)

    def test_embedded_runtime_is_standalone(self):
        text = Path(mode.__file__).read_text(encoding='utf-8').split('\ndef install(show):')[0]
        scope = {}
        exec(compile(text, 'embedded_output_mode', 'exec'), scope)
        self.assertEqual(scope['ACTIONS'], mode.ACTIONS)
        self.assertNotIn('install', scope)


if __name__ == '__main__':
    unittest.main()
