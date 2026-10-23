"""Go Back and cue-owned blackout levels must not disturb live media/mapping."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class Backend:
    def __init__(self):
        self.events = []
        self.is_ready = True
    def prepare(self, cue): self.events.append(("prepare", cue["id"]))
    def prepare_replay(self, cue): self.events.append(("replay", cue["id"]))
    def ready(self, cue): return self.is_ready
    def start(self, cue, now): self.events.append(("start", cue["id"]))
    def tick(self, now): pass
    def finish(self, cue): self.events.append(("finish", cue["id"]))
    def pause(self, value): pass
    def stop_cue(self, cue): self.events.append(("stop", cue["id"]))
    def stop_all(self): self.events.append(("stop_all",))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.backend = Backend()

    def engine(self, *changes):
        return show.CueEngine([dict(show.new_cue(), **v) for v in changes],
                              self.backend, lambda: self.now)

    def test_blackout_schema_and_legacy_defaults(self):
        old = show.new_cue()
        del old["blackout_scope"]
        self.assertEqual(show.validate_cue(old)["blackout_scope"], "all")
        for scope in ("all", "track"):
            cue = dict(old, kind="blackout", blackout_scope=scope)
            document = show.validate_show(dict(kind=show.SHOW_KIND, schema_version=1, cues=[cue]))
            self.assertEqual(document["cues"][0]["blackout_scope"], scope)
        for invalid in ("projector", None, 1, []):
            with self.assertRaises(ValueError):
                show.validate_cue(dict(old, blackout_scope=invalid))

    def test_no_previous_is_noop(self):
        e = self.engine({})
        self.assertFalse(e.go_back())
        self.assertEqual(self.backend.events, [])
        e.go(0)
        self.assertFalse(e.go_back())
        self.assertIn(e.cues[0]["id"], e.pending)

    def test_previous_enabled_skips_disabled_and_replays_from_start(self):
        e = self.engine({}, {"enabled": False}, {})
        e.go(0); e.tick(); self.now = 3; e.go(2); e.tick()
        self.assertTrue(e.go_back())
        self.assertEqual(e.navigation_index, 0)
        self.assertEqual(e.elapsed, 3)
        self.assertIn(("replay", e.cues[0]["id"]), self.backend.events)
        e.tick()
        self.assertEqual(e.active[e.cues[0]["id"]][1], 3)
        self.assertFalse(e.go_back())
        self.assertNotIn(("stop_all",), self.backend.events)

    def test_selected_row_is_anchor_before_first_go(self):
        e = self.engine({}, {}, {})
        e.selected = 2
        e.go_back()
        self.assertEqual(e.navigation_index, 1)

    def test_paused_navigation_requires_resume(self):
        e = self.engine({}, {})
        e.go(1); e.pause()
        with self.assertRaisesRegex(ValueError, "Resume"):
            e.go_back()
        e.resume(); self.assertTrue(e.go_back())

    def test_pending_forward_and_old_follows_cancelled(self):
        e = self.engine({"duration": 0}, {"duration": 5, "follow": "follow"},
                        {"prewait": 50})
        e.go(0); e.tick(); e.go(1); e.tick(); e.go(2)
        e.go_back(); e.tick(); e.go_back(); e.tick()
        self.now = 100; e.tick(); e.tick()
        self.assertNotIn(e.cues[2]["id"], e.active)
        self.assertFalse(e.follows)
        self.assertFalse(e.pending)

    def test_forward_go_after_back_restarts_superseded_cue(self):
        e = self.engine({"duration": 0}, {"duration": 0})
        e.go(0); e.tick(); e.go(1); e.tick(); e.go_back(); e.tick()
        self.assertTrue(e.go(1)); e.tick()
        self.assertIn(("replay", e.cues[1]["id"]), self.backend.events)

    def test_prepare_failure_keeps_previous_output_and_navigation(self):
        e = self.engine({}, {})
        e.go(1); e.tick()
        self.backend.prepare_replay = Mock(side_effect=ValueError("missing"))
        with self.assertRaisesRegex(ValueError, "missing"): e.go_back()
        self.assertEqual(e.navigation_index, 1)
        self.assertIn(e.cues[1]["id"], e.active)
        self.assertFalse(any(v[0].startswith("stop") for v in self.backend.events))

    def test_stop_resets_navigation_history(self):
        e = self.engine({}, {})
        e.go(1); e.stop()
        self.assertIsNone(e.navigation_index)
        self.assertFalse(e._suppress_follows)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.ext = ShowControlExt.__new__(ShowControlExt)
        self.ext.model = show
        self.ext.prepared, self.ext.tracks, self.ext.audio, self.ext.automations = {}, {}, {}, {}
        self.ext._level_fades = {}
        self.ext._look_edit = None
        self.ext.ownerComp = Mock()
        self.ext.ownerComp.par = {"Track1level": 1., "Track2level": 1., "Track3level": 1.,
                                  "Masterblackout": True, "Audioenabled": False}
        self.ext._p = lambda name: self.ext.ownerComp.par[name]
        self.ext._release_audio = Mock()

    def blackout(self, **changes):
        cue = dict(show.new_cue(), kind="blackout", duration=0, **changes)
        self.ext.prepared[cue["id"]] = {"cue": cue}
        self.ext.start(cue, 0)
        return cue

    def test_all_tracks_fade_hold_and_do_not_touch_safety_or_audio(self):
        self.blackout(fade=2, easing="linear")
        self.ext.tick(1)
        self.assertEqual([self.ext._p("Track%dlevel" % i) for i in (1, 2, 3)], [.5]*3)
        self.ext.tick(2); self.ext.tick(100)
        self.assertEqual([self.ext._p("Track%dlevel" % i) for i in (1, 2, 3)], [0]*3)
        self.assertTrue(self.ext._p("Masterblackout"))
        self.assertFalse(self.ext._p("Audioenabled"))
        self.ext._release_audio.assert_not_called()

    def test_scope_and_zero_fade(self):
        self.blackout(track=2, blackout_scope="track", fade=0)
        self.assertEqual([self.ext._p("Track%dlevel" % i) for i in (1, 2, 3)], [1, 0, 1])
        self.assertFalse(self.ext._level_fades)

    def test_visual_after_blackout_fades_only_its_own_deck(self):
        old = {'cue': show.new_cue(), 'deck': Mock(), 'side': 0}
        self.ext.tracks[1] = old
        self.blackout(fade=0)
        cue = dict(show.new_cue(), fade=2, easing='linear')
        new = {'cue': cue, 'deck': Mock(), 'side': 1, 'movie': None}
        new['deck'].op.return_value.par.Manualtime = None
        self.ext.prepared[cue['id']] = new
        self.ext.start(cue, 10)
        self.assertIsNone(new['old'])
        self.assertFalse(old['deck'].allowCooking)
        self.assertEqual(self.ext._p('Track1level'), 1)
        self.assertEqual(self.ext._p('Track2level'), 0)
        self.assertEqual(self.ext.ownerComp.op.return_value.par.top, 'black')
        self.assertFalse(self.ext.ownerComp.op.return_value.lock)

    def test_normal_visual_transition_keeps_crossfade(self):
        old = {'cue': show.new_cue(), 'deck': Mock(), 'side': 0}
        self.ext.tracks[1] = old
        cue = dict(show.new_cue(), fade=2)
        new = {'cue': cue, 'deck': Mock(), 'side': 1, 'movie': None}
        self.ext.prepared[cue['id']] = new
        self.ext.start(cue, 10)
        self.assertIs(new['old'], old)

    def test_new_visual_restores_only_its_track_and_old_blackout_finish_is_safe(self):
        old = self.blackout(fade=10)
        self.ext.tick(5)
        cue = dict(show.new_cue(), fade=2, easing="linear")
        self.ext._fade_track_level(1, 1, cue, 5)
        self.ext.finish(old)
        self.ext.tick(6)
        self.assertEqual([self.ext._p("Track%dlevel" % i) for i in (1, 2, 3)], [.75, 0, 0])
        self.ext.tick(7)
        self.assertEqual(self.ext._p("Track1level"), 1)

    def test_stop_blackout_freezes_current_level_not_reveal(self):
        cue = self.blackout(fade=2, easing="linear")
        self.ext.tick(1); self.ext.stop_cue(cue); self.ext.tick(3)
        self.assertEqual(self.ext._p("Track1level"), .5)

    def test_pause_freezes_blackout_fade(self):
        now = [0]
        cue = dict(show.new_cue(), kind="blackout", fade=2, duration=0, easing="linear")
        self.ext._prepare(cue)
        self.ext.ready = Mock(return_value=True)
        self.ext.prepare = Mock()
        engine = show.CueEngine([cue], self.ext, lambda: now[0])
        engine.go(); engine.tick(); now[0] = 1; engine.pause()
        now[0] = 50; engine.tick()
        self.assertEqual(self.ext._p("Track1level"), .5)
        engine.resume(); now[0] = 51; engine.tick()
        self.assertEqual(self.ext._p("Track1level"), 0)

    def test_replay_held_visual_preserves_output_and_document(self):
        cue = show.new_cue(); snapshot = copy.deepcopy(cue)
        deck = Mock()
        held = {"cue": cue, "deck": deck, "fading": False}
        self.ext.tracks[1] = held
        voice = {"cue": cue}
        self.ext.audio[cue["id"]] = voice
        self.ext._prepare = Mock()
        self.ext.prepare_replay(cue)
        self.assertIs(self.ext.tracks[1], held)
        self.assertNotEqual(held["cue"]["id"], cue["id"])
        self.assertIs(self.ext.audio[held["cue"]["id"]], voice)
        self.assertEqual(cue, snapshot)
        self.ext.ownerComp.op.assert_not_called()
        self.ext._release_audio.assert_not_called()

    def test_replay_failure_restores_held_metadata_and_voice(self):
        cue = show.new_cue()
        held = {"cue": cue, "fading": False}
        voice = {"cue": cue}
        self.ext.tracks[1] = held
        self.ext.audio[cue["id"]] = voice
        self.ext._prepare = Mock(side_effect=ValueError("bad media"))
        with self.assertRaisesRegex(ValueError, "bad media"):
            self.ext.prepare_replay(cue)
        self.assertIs(held["cue"], cue)
        self.assertIs(self.ext.audio[cue["id"]], voice)
        self.assertEqual(len(self.ext.audio), 1)

    def test_replay_during_crossfade_rejected_without_changes(self):
        cue = show.new_cue()
        self.ext.tracks[1] = {"cue": cue, "fading": True}
        self.ext._prepare = Mock()
        with self.assertRaisesRegex(ValueError, "crossfade"):
            self.ext.prepare_replay(cue)
        self.ext._prepare.assert_not_called()
        self.assertIs(self.ext.tracks[1]["cue"], cue)

    def test_audio_replay_releases_old_voice_only_at_start(self):
        cue = dict(show.new_cue(), kind="audio")
        self.ext.audio[cue["id"]] = {"cue": cue}
        reader = Mock()
        def prepare(value):
            self.ext.prepared[value["id"]] = {"cue": value, "reader": reader}
        self.ext._prepare = prepare
        self.ext.prepare_replay(cue)
        old_id = self.ext.prepared[cue["id"]]["replay_voice"]
        self.ext._release_audio.assert_not_called()
        self.ext.start(cue, 10)
        self.ext._release_audio.assert_called_once_with(old_id)
        self.assertTrue(reader.par.play)

    def test_pause_caches_source_before_stopping_deck_and_resume_unlocks(self):
        cue = show.new_cue()
        source = Mock(lock=False)
        self.ext.ownerComp.op.return_value = source
        deck = Mock(allowCooking=True)
        self.ext.tracks[1] = {"cue": cue, "deck": deck, "side": 0}
        self.ext.pause(True)
        source.cook.assert_called_once_with(force=True)
        self.assertTrue(source.lock)
        self.assertFalse(deck.allowCooking)
        self.ext.pause(False)
        self.assertTrue(deck.allowCooking)
        self.assertFalse(source.lock)

    def test_finished_visual_holds_cached_source_until_reused(self):
        cue = dict(show.new_cue(), hold=True)
        source = Mock(lock=False)
        self.ext.ownerComp.op.return_value = source
        deck = Mock(allowCooking=True)
        self.ext.tracks[1] = {"cue": cue, "deck": deck, "side": 0}
        self.ext.finish(cue)
        self.assertTrue(source.lock)
        self.assertFalse(deck.allowCooking)
        self.ext._stop_track(1)
        self.assertFalse(source.lock)
        self.assertEqual(source.par.top, "black")


if __name__ == "__main__":
    unittest.main()
