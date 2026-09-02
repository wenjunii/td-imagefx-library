"""Deterministic show clock and projection geometry regression checks."""
import unittest

from tdimagefx.show import CueEngine, SHOW_KIND, inverse_quad, new_cue, timestamp, validate_cue, validate_show


class Backend:
    def __init__(self):
        self.events = []
        self.is_ready = True

    def prepare(self, cue): self.events.append(("prepare", cue["id"]))
    def ready(self, cue): return self.is_ready
    def start(self, cue, now): self.events.append(("start", cue["id"], now))
    def tick(self, now): pass
    def finish(self, cue): self.events.append(("finish", cue["id"]))
    def pause(self, value): self.events.append(("pause", value))
    def stop_cue(self, cue): self.events.append(("stop", cue["id"]))
    def stop_all(self): self.events.append(("stop_all",))


class ShowTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.backend = Backend()

    def engine(self, *changes):
        return CueEngine([dict(new_cue(), **c) for c in changes], self.backend, lambda: self.now)

    def test_timestamps(self):
        for value, expected in (("", None), ("1:02:03.5", 3723.5), ("02:03", 123), (12, 12)):
            self.assertEqual(timestamp(value), expected)
        for value in ("1:61", "-1", "nan", True, "1:2:3:4", "1:inf"):
            with self.assertRaises(ValueError): timestamp(value)

    def test_cue_schema(self):
        self.assertEqual(validate_cue(new_cue())["kind"], "visual")
        for fields in ({"id": 12}, {"track": True}, {"kind": []}, {"duration": float("nan")}, {"gain": 2}, {"follow": "follow", "duration": 0}, {"target": "../../Code"}, {"enabled": 1}, {"unknown": 1}):
            with self.assertRaises(ValueError): validate_cue(dict(new_cue(), **fields))

    def test_show_rejects_duplicate_ids_and_unknown_fields(self):
        cue = new_cue()
        with self.assertRaises(ValueError): validate_show(dict(kind=SHOW_KIND, schema_version=1, cues=[cue, cue]))
        with self.assertRaises(ValueError): validate_show(dict(kind=SHOW_KIND, schema_version=1, cues=[], script="unsafe"))

    def test_manual_prewait_pause_resume(self):
        e = self.engine({"prewait": 2, "duration": 10})
        e.go(); self.now = 1; e.tick(); self.assertFalse(e.active)
        e.pause(); self.now = 50; e.tick(); self.assertEqual(e.elapsed, 1)
        e.resume(); self.now = 51; e.tick(); self.assertEqual(len(e.active), 1)
        self.assertEqual(e.elapsed, 2)

    def test_schedule_runs_once_and_stop_resets(self):
        e = self.engine({"kind": "wait", "duration": 0}, {"at": 5, "duration": 1})
        e.go(0); self.now = 6; e.tick(); self.now = 8; e.tick(); e.tick()
        self.assertEqual(sum(event[0] == "start" for event in self.backend.events), 2)
        e.stop(); self.assertEqual(e.elapsed, 0); self.assertFalse(e.triggered)

    def test_follow_and_continue(self):
        e = self.engine({"duration": 2, "follow": "follow", "postwait": 1}, {"duration": 8, "follow": "continue"}, {"duration": 8})
        e.go(); e.tick(); self.now = 2; e.tick(); self.now = 3; e.tick(); e.tick()
        self.assertEqual(sum(event[0] == "start" for event in self.backend.events), 3)

    def test_stop_cue_cancels_pending_and_follow(self):
        e = self.engine({"follow": "continue", "postwait": 3}, {})
        e.go(); e.tick(); e.stop_cue(0); self.now = 5; e.tick()
        self.assertFalse(e.follows); self.assertFalse(e.active)
        self.assertEqual(sum(event[0] == "start" for event in self.backend.events), 1)

    def test_readiness_timeout_releases_standby(self):
        e = self.engine({})
        self.backend.is_ready = False
        e.go(); self.now = 31; e.tick()
        self.assertFalse(e.pending); self.assertTrue(e.errors)
        self.assertEqual(self.backend.events[-1][0], "stop")

    def test_prepare_failure_does_not_start_clock(self):
        e = self.engine({})
        def fail(_): raise ValueError("missing")
        self.backend.prepare = fail
        with self.assertRaises(ValueError): e.go()
        self.assertEqual(e.state, "stopped"); self.assertFalse(e.pending)

    def test_disabled_and_duplicate_go(self):
        e = self.engine({"enabled": False}, {})
        self.assertFalse(e.go()); self.assertEqual(e.selected, 1)
        e.go()
        with self.assertRaises(ValueError): e.go(1)
        e.pause()
        with self.assertRaises(ValueError): e.go(1)

    def test_follow_skips_disabled_rows(self):
        e = self.engine({"duration": 1, "follow": "follow"}, {"enabled": False}, {})
        e.go(); e.tick(); self.now = 1; e.tick(); e.tick()
        self.assertIn(e.cues[2]["id"], e.active)
        self.assertNotIn(e.cues[1]["id"], e.active)

    def test_stop_selected_disarms_future_timestamp_and_follow(self):
        e = self.engine({"follow": "continue", "postwait": 3}, {"at": 5})
        e.go(); e.tick(); e.stop_cue(1); self.now = 6; e.tick()
        self.assertNotIn(e.cues[1]["id"], e.active)
        self.assertNotIn(e.cues[1]["id"], e.pending)
        e.stop(); e.go(0); self.now = 12; e.tick()
        self.assertIn(e.cues[1]["id"], e.active)

    def test_stop_track_cancels_playing_pending_and_auto_follow(self):
        e = self.engine({"duration": 0, "follow": "continue", "postwait": 3},
                        {"prewait": 10}, {"track": 2, "duration": 0},
                        {"kind": "stop", "duration": 0})
        e.go(0); e.go(1); e.go(2); e.tick(); e.go(3); e.tick()
        self.now = 15; e.tick()
        self.assertEqual(set(e.active), {e.cues[2]["id"]})
        self.assertFalse(e.pending)
        self.assertFalse(e.follows)

    def test_stop_before_queued_cue_in_same_tick(self):
        e = self.engine({"kind": "stop", "duration": 0}, {})
        e.go(0); e.go(1); e.tick()
        self.assertFalse(e.active)
        self.assertFalse(e.pending)
        self.assertFalse(e.errors)
        self.assertNotIn(("start", e.cues[1]["id"], 0), self.backend.events)

    def test_mapping_identity_and_perspective(self):
        for points in (((0,0),(1,0),(1,1),(0,1)), ((.1,.2),(.9,.1),(.8,.9),(.2,.8))):
            m = inverse_quad(points)
            for (x,y), (u,v) in zip(points, ((0,0),(1,0),(1,1),(0,1))):
                d = m[6]*x + m[7]*y + m[8]
                self.assertAlmostEqual((m[0]*x + m[1]*y + m[2])/d, u)
                self.assertAlmostEqual((m[3]*x + m[4]*y + m[5])/d, v)

    def test_mapping_rejects_crossed_collapsed_nonfinite(self):
        for points in (((0,0),(1,1),(1,0),(0,1)), ((0,0),(0,0),(1,1),(0,1)), ((float("nan"),0),(1,0),(1,1),(0,1))):
            with self.assertRaises(ValueError): inverse_quad(points)


if __name__ == "__main__":
    unittest.main()
