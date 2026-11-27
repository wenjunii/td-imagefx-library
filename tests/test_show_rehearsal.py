import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tdimagefx import rehearsal, show
from touchdesigner.extensions.ShowControlExt import ShowControlExt
from touchdesigner.scripts import show_rehearsal as runtime


class RehearsalLogTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.log = rehearsal.RehearsalLog(60, clock=lambda: self.now)
        self.a = dict(show.new_cue(), name="Cue A", prewait=.25, fade=1)
        self.b = dict(show.new_cue(), name="Cue B", track=2)

    def request(self, cue, i=0):
        return self.log.event("request", cue, i, "go")

    def started(self, cue):
        return self.log.event("started", cue)

    def test_delay_includes_wait_and_only_observed_renders_count(self):
        a = self.a["id"]
        self.request(self.a)
        self.log.sample(2, 72, 3, 2400, (), (), ())
        self.now += .30
        self.started(self.a)
        self.log.sample(3, 8, 0, 1900, [a], [a], ())
        self.assertIsNone(self.log.report()["cue_attempts"][0]["request_to_first_render_ms"])
        self.now += .02
        self.log.sample(4, 18, 1, 2300, [a], [a], [a])
        self.log.sample(4, 99, 100, 9000, [a], [a], [a])
        row = self.log.report()["cue_attempts"][0]
        self.assertEqual(row["request_to_start_ms"], 300)
        self.assertEqual(row["request_to_first_render_ms"], 320)
        self.assertEqual(row["configured_prewait_s"], .25)
        self.assertEqual(row["waiting"]["timeline_drops"], 3)
        self.assertEqual(row["playing"]["mean_ms"], 13)
        self.assertEqual(row["transition"]["over_budget_frames"], 1)
        self.assertEqual(row["transition"]["peak_gpu_mb"], 2300)

    def test_overlap_is_attributed_to_both_but_counted_once_globally(self):
        self.request(self.a)
        self.request(self.b, 1)
        self.started(self.a)
        self.started(self.b)
        self.log.sample(1, 31, 2, 1800, [self.a["id"], self.a["id"], self.b["id"]],
                        [self.b["id"]], ())
        result = self.log.report()
        a, b = result["cue_attempts"]
        self.assertEqual(result["playback"]["timeline_drops"], 2)
        self.assertEqual(a["playing"]["timeline_drops"], 2)
        self.assertEqual(b["playing"]["timeline_drops"], 2)
        self.assertEqual(a["transition"]["sampled_frames"], 0)
        self.assertEqual(b["transition"]["sampled_frames"], 1)

    def test_missing_telemetry_is_not_zero(self):
        self.log.sample(1, None, float("nan"), -1, (), (), ())
        result = self.log.report()["playback"]
        self.assertEqual(result["sampled_frames"], 1)
        for name in ("mean_ms", "worst_ms", "timeline_drops", "peak_gpu_mb"):
            self.assertIsNone(result[name])
        self.assertEqual(result["drop_samples"], 0)

    def test_stop_and_replay_keep_distinct_attempts(self):
        self.request(self.a)
        self.started(self.a)
        self.log.event("stop_all")
        self.log.event("request", self.a, 0, "go_back")
        self.started(self.a)
        a, b = self.log.report()["cue_attempts"]
        self.assertEqual((a["status"], b["status"]), ("stopped", "started"))
        self.assertEqual((a["trigger"], b["trigger"]), ("go", "go_back"))

    def test_pending_error_does_not_pollute_first_frame(self):
        self.request(self.a)
        self.log.event("error", self.a, 0, "prepare")
        self.log.sample(1, 20, 0, 500, (), (), [self.a["id"]])
        row = self.log.report()["cue_attempts"][0]
        self.assertEqual(row["status"], "error_prepare")
        self.assertIsNone(row["request_to_first_render_ms"])
        self.assertEqual(row["waiting"]["sampled_frames"], 0)

    def test_recording_counts_have_a_baseline_and_a_separate_total(self):
        self.log.recording("a", "wall", 60, 15, 2, preexisting=True)
        self.log.recording("a", "wall", 60, 45, 3, outcome="complete")
        self.log.recording("b", "review", 30, 8, 2, outcome="cancelled")
        self.log.recording("c", "saved", 30, 100, 100)
        self.log.sample(1, 15, 0, 1000, (), (), ())
        result = self.log.report()
        a, b = result["recordings"]
        self.assertEqual(a, dict(source="wall", fps=60, written=30, dropped=1,
                                 preexisting=True, outcome="complete"))
        self.assertEqual(b["dropped"], 2)
        self.assertEqual(result["playback"]["timeline_drops"], 0)

    def test_freeze_and_limits_do_not_accumulate_more_attempts(self):
        self.request(self.a)
        with patch.object(rehearsal, "MAX_ATTEMPTS", 1), patch.object(rehearsal, "MAX_RECORDINGS", 1):
            self.request(self.b)
            self.log.recording("a", "wall", 60, 1, 0)
            self.log.recording("b", "wall", 60, 1, 0)
        self.log.freeze("cue_list_changed")
        self.now += 1
        self.log.event("stop_all")
        result = self.log.report()
        self.assertTrue(result["limit_reached"])
        self.assertEqual(result["end_reason"], "cue_list_changed")
        self.assertEqual(result["duration_s"], 0)
        self.assertEqual(len(result["cue_attempts"]), 1)
        self.assertEqual(len(result["recordings"]), 1)

    def test_observer_follows_real_scheduler_events(self):
        backend = Mock()
        engine = show.CueEngine([dict(self.a, prewait=0, follow="continue", postwait=0), self.b],
                                backend, clock=lambda: self.now)
        engine.rehearsal_observer = self.log.event
        engine.go(0); engine.tick(); engine.tick()
        engine.stop()
        a, b = self.log.report()["cue_attempts"]
        self.assertEqual((a["trigger"], b["trigger"]), ("go", "auto_next"))
        self.assertEqual((a["status"], b["status"]), ("stopped", "stopped"))
        self.assertEqual(backend.start.call_count, 2)

    def test_scheduler_remains_usable_if_the_observer_raises(self):
        backend = Mock()
        engine = show.CueEngine([self.a], backend, clock=lambda: self.now)
        observer = Mock(side_effect=RuntimeError("diagnostics error"))
        engine.rehearsal_observer = observer
        self.assertTrue(engine.go(0))
        self.now += .5
        engine.tick()
        backend.start.assert_called_once()
        self.assertEqual([call.args[0] for call in observer.call_args_list], ["request", "started"])
        self.assertFalse(engine.errors)


class RehearsalAdapterTests(unittest.TestCase):
    def capture_fixture(self):
        cue = show.new_cue()
        ext = SimpleNamespace(
            engine=SimpleNamespace(cues=[cue], state="running", pending={}, rehearsal_observer=None),
            tracks={}, audio={}, automations={}, _level_fades={})
        parameters = SimpleNamespace(Targetfps=Mock(**{"eval.return_value": "30"}),
            Outputmode=Mock(**{"eval.return_value": "wall"}), Routingmode=Mock(**{"eval.return_value": "cue"}),
            Renderwidth=1920, Renderheight=1080, Masterblackout=True,
            Libraryroot=Mock(**{"eval.return_value": str(Path.cwd())}))
        perf = Mock()
        source = Mock(cookAbsFrame=6)
        values = {"msec": [16], "dropped_frames": [0], "gpu_mem_used": [3200]}
        performance = type("Performance", (), {"cook": perf, "__getitem__": lambda _, name: values.get(name)})()
        nodes = {"readiness_performance": performance, "track1_source1": source}
        owner = SimpleNamespace(par=parameters, op=nodes.get, fetch=Mock(return_value=None))
        return runtime.Capture(owner, ext), cue, perf, source

    def test_frame_observer_does_not_count_preload_or_force_a_top(self):
        capture, cue, perf, source = self.capture_fixture()
        cue_id = cue["id"]
        clock = SimpleNamespace(frame=6)
        capture.ext.tracks[1] = dict(cue=cue, side=1, fading=False)
        with patch.dict("sys.modules", {"td": SimpleNamespace(absTime=clock)}):
            capture.event("request", cue, 0, "go")
            capture.event("started", cue, 0, None)
            capture.sample()  # A warm cook on the same frame as start.
            clock.frame = 7
            capture.sample()  # Only the old cook is visible; still no timing.
            self.assertIsNone(capture.history.started[cue_id].first_frame_s)
            clock.frame, source.cookAbsFrame = 9, 8  # Frame End can observe the prior frame's cook.
            capture.sample()
            capture.sample()  # Same frame is not counted twice.
        source.cook.assert_not_called()
        self.assertEqual(perf.call_count, 3)
        self.assertIsNotNone(capture.history.started[cue_id].first_frame_s)
        self.assertEqual(capture.report()["playback"]["peak_gpu_mb"], 3200)

    def test_replacing_cue_list_freezes_log_but_does_not_change_transport(self):
        capture, _, perf, _ = self.capture_fixture()
        capture.attach()
        former = capture.engine
        capture.ext.engine = SimpleNamespace(state="stopped", rehearsal_observer=None)
        capture.sample()
        self.assertIsNone(former.rehearsal_observer)
        self.assertEqual(capture.report()["end_reason"], "cue_list_changed")
        self.assertEqual(capture.ext.engine.state, "stopped")
        perf.assert_not_called()

    def test_log_save_guard_leaves_capture_attached(self):
        capture = Mock()
        ext = SimpleNamespace(engine=SimpleNamespace(state="running"), _rehearsal=capture)
        component = Mock()
        component.ext.ShowControlExt = ext
        with self.assertRaisesRegex(ValueError, "Stop transport"):
            runtime.save(component)
        capture.freeze.assert_not_called()
        self.assertIs(ext._rehearsal, capture)

    def test_save_is_local_unique_and_does_not_include_media_or_cue_notes(self):
        with tempfile.TemporaryDirectory() as root:
            ext = SimpleNamespace(engine=SimpleNamespace(state="stopped"), _rehearsal=None)
            component = Mock()
            component.ext.ShowControlExt = ext
            component.fetch.return_value = None
            for i in range(2):
                log = rehearsal.RehearsalLog(30)
                cue = dict(show.new_cue(), source="private.mp4", notes="private note")
                log.event("request", cue, 0, "go")
                ext._rehearsal = SimpleNamespace(directory=Path(root), freeze=log.freeze, report=log.report)
                path = runtime.save(component)
                self.assertEqual(path.parent, Path(root).resolve()/".imagefx"/"rehearsals")
                encoded = path.read_text(encoding="utf-8")
                self.assertEqual(json.loads(encoded)["cue_attempts"][0]["cue_number"], 1)
                self.assertNotIn("private.mp4", encoded)
                self.assertNotIn("private note", encoded)
                self.assertIsNone(ext._rehearsal)
            self.assertEqual(len(list(path.parent.glob("*.json"))), 2)

    def test_write_failure_keeps_the_frozen_report_for_retry(self):
        ext = SimpleNamespace(engine=SimpleNamespace(state="stopped"), _rehearsal=None)
        component = Mock()
        component.ext.ShowControlExt = ext
        component.fetch.return_value = None
        capture = Mock(directory=Path.cwd().resolve())
        ext._rehearsal = capture
        with patch.object(runtime, "atomic_write_json", side_effect=OSError("disk full")):
            runtime.on_pulse(component, "Rehearsalsave")
        self.assertIn("retained", component.par.Rehearsalstatus)
        self.assertIs(ext._rehearsal, capture)
        capture.freeze.assert_called_once_with("operator_stop")

    def test_sampling_error_does_not_pause_show_tick(self):
        ext = ShowControlExt.__new__(ShowControlExt)
        ext._rehearsal = Mock()
        ext._rehearsal.sample.side_effect = RuntimeError
        ext._rehearsal.failed.side_effect = RuntimeError
        ext.engine = Mock(selected=0, state="running", errors={})
        ext._ui_time = float("inf")
        ext._service_preloads = Mock()
        ext.UpdateCueRouting = Mock()
        ext.UpdateMapping = Mock()
        ext.Tick()
        ext.engine.tick.assert_called_once()
        self.assertEqual(ext.engine.state, "running")
        self.assertIsNone(ext._rehearsal)
