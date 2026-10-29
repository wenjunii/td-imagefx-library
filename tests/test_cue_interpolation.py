"""Cue morphing changes values without replacing the live deck or its clock."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


def look(value=.2):
    return {"toggles": {"Inkdreamenabled": True}, "order": ["ink_dream_flow"],
            "modules": {"ink_dream_flow": {"Coverage": value, "Seed": 4, "Timescale": 1}},
            "animation": {"ink_dream_flow": {"time": 3, "running": True}}}


class InterpolationPlanTests(unittest.TestCase):
    def test_legacy_shows_default_to_crossfade_and_roundtrip_new_choice(self):
        old = show.new_cue(); del old["transition"]
        self.assertEqual(show.validate_cue(old)["transition"], "crossfade")
        self.assertEqual(show.validate_cue(dict(old, transition="interpolate"))["transition"], "interpolate")
        for value in (None, [], "morph", 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                show.validate_cue(dict(old, transition=value))

    def test_numeric_plan_and_saved_clock_phase_do_not_mutate_looks(self):
        old, new = look(), look(.8)
        new["animation"]["ink_dream_flow"]["time"] = 900
        snapshot = copy.deepcopy((old, new))
        self.assertEqual(show.look_interpolation_changes(old, new), [("ink_dream_flow", "Coverage", .2, .8)])
        self.assertEqual((old, new), snapshot)

    def test_incompatible_selectors_assets_order_seed_and_clock_use_fallback(self):
        for change in (lambda v: v["toggles"].update(Inkdreamenabled=False),
                       lambda v: v.update(order=[]),
                       lambda v: v.update(layer_files={"Topfile": "other.png"}),
                       lambda v: v["modules"]["ink_dream_flow"].update(Seed=5),
                       lambda v: v["modules"]["ink_dream_flow"].update(Timescale=2),
                       lambda v: v["animation"]["ink_dream_flow"].update(running=False),
                       lambda v: v["modules"]["ink_dream_flow"].update(Coverage=True),
                       lambda v: v["modules"]["ink_dream_flow"].update(Coverage=float("nan"))):
            new = look(); change(new)
            with self.subTest(new=new), self.assertRaises(ValueError):
                show.look_interpolation_changes(look(), new)

    def test_branches_and_rack_values_resolve_to_existing_parameters(self):
        old = {"branches": {"a_effects": look()}}
        new = {"branches": {"a_effects": look(.7)}}
        slot = {"index": 2, "package": {"id": "effect", "version": "1.0.0"}, "enabled": True,
                "mix": .2, "modulation": {"state": "sine", "depth": .1, "rate": 1}, "parameters": {"Amount": .3}}
        old["rack"] = {"time": 1, "slots": [slot]}
        new["rack"] = copy.deepcopy(old["rack"])
        new["rack"]["time"] = 10
        new["rack"]["slots"][0].update(mix=.8, parameters={"Amount": .9})
        changes = show.look_interpolation_changes(old, new)
        self.assertIn(("fx_rack", "Slot2mix", .2, .8), changes)
        self.assertIn(("fx_rack/slot2", "Amount", .3, .9), changes)
        self.assertIn(("image_composition/a_effects/ink_dream_flow", "Coverage", .2, .7), changes)
        new["rack"]["slots"][0]["package"]["version"] = "2.0.0"
        with self.assertRaises(ValueError): show.look_interpolation_changes(old, new)


class InterpolationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.ext.ownerComp = Mock()
        self.ext.ownerComp.par = {}
        self.ext._p = Mock(return_value=1)
        self.ext._status = Mock()
        self.ext._detach_running_look = Mock()
        self.ext._halt_deck = Mock()
        self.ext._release_audio = Mock()
        self.ext._level_fades = {}
        self.ext.audio = {}
        self.ext.automations = {}
        self.current = dict(show.new_cue(), duration=0, fade=0)
        self.cue = dict(show.new_cue(), duration=0, fade=2, transition="interpolate", easing="linear")
        self.live = Mock(id=123)
        self.standby = Mock(id=456)
        self.live.fetch.return_value = self.standby.fetch.return_value = {}
        # Clock component is separate from interpolated custom controls.
        self.component = SimpleNamespace(par=SimpleNamespace(Manualtime=0))
        self.live.op.return_value = self.component
        self.old = dict(cue=self.current, deck=self.live, side=0, started=2, movie=Mock(), fading=False)
        self.item = dict(cue=self.cue, deck=self.standby, side=1, track=1, movie=Mock())
        self.ext.tracks = {1: self.old}
        self.ext.prepared = {self.cue["id"]: self.item}
        self.parameter = SimpleNamespace(val=.2, isMenu=False, isToggle=False, isInt=False)
        self.ext._validate_assignment = Mock(return_value=self.parameter)
        self.ext._capture_look = Mock(side_effect=lambda d, **kw: look(.2 if d is self.live else .8))

    def test_start_reuses_live_media_network_and_continuous_clock(self):
        movie = self.old["movie"]
        self.ext.start(self.cue, 10)
        self.assertIs(self.ext.tracks[1]["deck"], self.live)
        self.assertIs(self.ext.tracks[1]["movie"], movie)
        self.assertEqual(self.item["clock_started"], 2)
        self.assertEqual(self.ext.ownerComp.par["Track1blend"], 0)
        self.ext._halt_deck.assert_called_once_with(self.item)
        movie.par.assert_not_called()
        self.assertFalse(self.ext.prepared)
        self.ext.tick(11)
        self.assertAlmostEqual(self.parameter.val, .5)
        self.assertEqual(self.component.par.Manualtime, 9)
        self.assertTrue(self.item["fading"])
        self.ext.tick(12)
        self.assertEqual(self.parameter.val, .8)
        self.assertFalse(self.item["fading"])
        self.assertEqual(self.ext.ownerComp.par["Track1blend"], 0)

    def test_smooth_easing_and_integer_controls_reach_exact_target(self):
        self.cue["easing"] = "smooth"
        self.parameter.isInt = True
        self.ext._capture_look.side_effect = lambda d, **kw: look(2 if d is self.live else 10)
        self.ext.start(self.cue, 10)
        self.ext.tick(10.5)
        self.assertEqual(self.parameter.val, 3)
        self.ext.tick(12)
        self.assertEqual(self.parameter.val, 10)

    def test_media_change_falls_back_without_writing_running_values(self):
        self.cue["source"] = "other.mp4"
        self.ext.start(self.cue, 10)
        self.assertIs(self.item["deck"], self.standby)
        self.assertIs(self.item["old"], self.old)
        self.assertNotIn("interpolation", self.item)
        self.assertEqual(self.parameter.val, .2)
        self.ext._capture_look.assert_not_called()

    def test_all_discrete_controls_are_checked_before_any_mutation(self):
        destination = look(.8)
        destination["modules"]["ink_dream_flow"]["Seed"] = 5
        self.ext._capture_look.side_effect = lambda d, **kw: look() if d is self.live else destination
        self.ext.start(self.cue, 10)
        self.assertNotIn("interpolation", self.item)
        self.assertEqual(self.parameter.val, .2)
        self.ext._halt_deck.assert_not_called()

    def test_zero_transition_and_short_hold_finish_at_destination(self):
        self.cue["fade"] = 0
        self.ext.start(self.cue, 10)
        self.assertEqual(self.parameter.val, .8)
        self.parameter.val = .3
        self.item["interpolation"] = [(self.parameter, .2, .8, False)]
        self.ext.finish(self.cue)
        self.assertEqual(self.parameter.val, .8)
        self.assertTrue(self.item["finished"])

    def test_other_tracks_and_saved_cues_are_unchanged(self):
        other = dict(cue=dict(show.new_cue(), track=2), deck=Mock(), side=1, started=0, finished=True)
        self.ext.tracks[2] = other
        saved = copy.deepcopy((self.current, self.cue))
        self.ext.start(self.cue, 10); self.ext.tick(11)
        self.assertIs(self.ext.tracks[2], other)
        self.assertEqual((self.current, self.cue), saved)

    def test_stop_clears_interpolation_and_blocks_competing_automation(self):
        self.ext.start(self.cue, 10)
        with self.assertRaisesRegex(ValueError, "interpolation"):
            self.ext._target(dict(show.new_cue(), kind="parameters"))
        self.ext.stop_cue(self.cue)
        self.assertFalse(self.ext.tracks)

    def test_blackout_or_held_visual_uses_normal_transition(self):
        for field in ("blackout", "finished"):
            with self.subTest(field=field):
                self.setUp()
                if field == "blackout": self.ext._p.return_value = 0
                else: self.old["finished"] = True
                self.ext.start(self.cue, 10)
                self.assertNotIn("interpolation", self.item)

    def test_pause_resume_uses_show_clock_without_advancing_interpolation(self):
        now = [0.0]
        self.old["started"] = 0
        self.ext.prepare = Mock()
        self.ext.ready = Mock(return_value=True)
        self.ext.pause = Mock()
        engine = show.CueEngine([self.cue], self.ext, lambda: now[0])
        engine.go(); engine.tick()
        now[0] = 1; engine.pause()
        self.assertAlmostEqual(self.parameter.val, .5)
        now[0] = 100; engine.tick()
        self.assertAlmostEqual(self.parameter.val, .5)
        engine.resume(); now[0] = 101; engine.tick()
        self.assertEqual(self.parameter.val, .8)


if __name__ == "__main__":
    unittest.main()
