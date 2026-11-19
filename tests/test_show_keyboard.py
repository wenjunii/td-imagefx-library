"""Exercise the exact callback embedded in the TouchDesigner project."""
import runpy
from types import SimpleNamespace
import unittest


class SpaceGoTests(unittest.TestCase):
    def setUp(self):
        builder = runpy.run_path('touchdesigner/scripts/build_show_control.py')
        scope = {}
        exec(builder['SPACE_GO_CALLBACKS'], scope)
        self.on_key = scope['onKey']
        self.viewer_title_matches = scope['viewer_title_matches']
        self.in_foreground = False
        scope['foreground_viewer'] = lambda _: self.in_foreground
        self.actions, self.storage = [], {}
        self.focus_returns = []
        self.panels = {
            name: SimpleNamespace(panel=SimpleNamespace(focusselect=False))
            for name in ('cue_inspector', 'inspector_selector')
        }
        self.show = SimpleNamespace(panel=SimpleNamespace(focusselect=True),
                                    op=self.panels.get, Action=self.actions.append,
                                    setFocus=self.restore_focus)
        self.dat = SimpleNamespace(parent=lambda: self.show, store=self.storage.__setitem__,
                                   fetch=lambda name, default, **_: self.storage.get(name, default))
        scope = dict(parent=lambda: self.show)
        exec(builder['SHOW_PARAMETER_CALLBACKS'], scope)
        self.on_pulse = scope['onPulse']

    def restore_focus(self):
        self.focus_returns.append(True)
        self.panels['cue_inspector'].panel.focusselect = False

    def key(self, down, *, key='space', ctrl=False, shift=False, alt=False, cmd=False):
        self.on_key(self.dat, key, ' ' if key == 'space' else key,
                    alt, False, False, ctrl, False, False, shift, False, False,
                    down, 0, cmd)

    def test_one_go_per_space_even_with_repeated_key_down(self):
        self.key(False)
        for _ in range(5):
            self.key(True)
        self.assertEqual(self.actions, [])
        self.key(False)
        self.key(False)
        self.assertEqual(self.actions, ['Gocue'])
        self.key(True)
        self.key(False)
        self.assertEqual(self.actions, ['Gocue', 'Gocue'])

    def test_no_go_in_inspector_dropdown_or_another_window(self):
        for name in self.panels:
            self.panels[name].panel.focusselect = True
            self.key(True)
            self.key(False)
            self.panels[name].panel.focusselect = False
        self.key(True)
        self.show.panel.focusselect = False
        self.key(False)
        self.key(True)
        self.show.panel.focusselect = True
        self.key(False)
        self.assertEqual(self.actions, [])

    def test_modified_space_or_other_keys_do_not_go(self):
        for modifier in ('alt', 'ctrl', 'shift', 'cmd'):
            self.key(True, **{modifier: True})
            self.key(False)
        self.key(True, key='a')
        self.key(False, key='a')
        self.assertEqual(self.actions, [])

    def test_clicked_transport_pulse_returns_focus_for_the_next_space(self):
        for action in ('Gocue', 'Preload', 'Loadshow', 'Savecuenotes'):
            with self.subTest(action=action):
                self.panels['cue_inspector'].panel.focusselect = True
                self.actions.clear()
                self.on_pulse(SimpleNamespace(name=action))
                self.key(True)
                self.key(False)
                self.assertEqual(self.actions, [action, 'Gocue'])
        self.assertEqual(len(self.focus_returns), 4)

    def test_editing_and_external_parameter_pulses_do_not_steal_focus(self):
        self.panels['cue_inspector'].panel.focusselect = True
        self.on_pulse(SimpleNamespace(name='Applycue'))
        self.key(True)
        self.key(False)
        self.show.panel.focusselect = False
        self.on_pulse(SimpleNamespace(name='Gocue'))
        self.assertEqual(self.actions, ['Applycue', 'Gocue'])
        self.assertEqual(self.focus_returns, [])

    def test_foreground_fallback_works_without_requiring_a_panel_click(self):
        self.storage['space_windows_fallback'] = True
        self.show.panel.focusselect = False
        self.in_foreground = True
        self.key(True)
        self.key(True)
        self.key(False)
        self.assertEqual(self.actions, ['Gocue'])

    def test_fallback_never_bypasses_editing_other_windows_or_primary_listener(self):
        self.storage['space_windows_fallback'] = True
        self.show.panel.focusselect = False
        self.key(True)  # The press originated elsewhere.
        self.in_foreground = True
        self.key(False)
        self.key(True)
        self.in_foreground = False
        self.key(False)
        self.in_foreground = True
        for panel in self.panels.values():
            panel.panel.focusselect = True
            self.key(True)
            self.key(False)
            panel.panel.focusselect = False
        self.show.panel.focusselect = True
        self.key(True)
        self.key(False)
        self.assertEqual(self.actions, [])

    def test_foreground_title_must_be_the_exact_show_control_viewer(self):
        path = '/project1/imagefx_demo/show_control'
        self.assertTrue(self.viewer_title_matches(path + ' (1660,900) (1660,900) ', path))
        for title in ('TouchDesigner: ' + path, path + '/preview (1660,900)',
                      path + '2 (1660,900)', path + ' (unexpected)', path):
            self.assertFalse(self.viewer_title_matches(title, path))
