"""Automatic cue requests wait for real track reservations, not for errors."""
import copy
import unittest
from unittest.mock import Mock

from tdimagefx import show
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class TrackBackend(ShowControlExt):
    """Use production prepare/_prepare with simulated TD operators and clock."""

    def __init__(self):
        self.model = show
        self._look_edit = None
        self.ownerComp = Mock()
        self.prepared, self.tracks, self.audio = {}, {}, {}
        self.starts, self.stops, self.prepare_calls = [], [], []
        self._deck = Mock(return_value=Mock())
        self.media_ready = True

    def _media_path(self, cue):
        if cue['source'] == 'missing':
            raise ValueError('Missing media: fixture')
        return ''

    def prepare(self, cue):
        self.prepare_calls.append(cue['id'])
        return super().prepare(cue)

    def ready(self, cue):
        return self.media_ready

    def start(self, cue, now):
        item = self.prepared.pop(cue['id'])
        self.starts.append((cue['id'], now))
        if cue['kind'] == 'visual':
            item.update(started=now, fading=cue['fade'] > 0)
            self.tracks[cue['track']] = item

    def tick(self, now):
        for item in self.tracks.values():
            item['fading'] = now - item['started'] < item['cue']['fade']

    def finish(self, cue):
        item = self.tracks.get(cue['track'])
        if item and item['cue']['id'] == cue['id']:
            item['fading'] = False

    def stop_cue(self, cue):
        self.stops.append(cue['id'])
        self.prepared.pop(cue['id'], None)
        item = self.tracks.get(cue['track'])
        if item and item['cue']['id'] == cue['id']:
            self.tracks.pop(cue['track'])

    def stop_all(self):
        self.prepared.clear()
        self.tracks.clear()

    def pause(self, value):
        pass


class ContinueTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.backend = TrackBackend()

    def engine(self, *changes):
        cues = [dict(dict(show.new_cue(), duration=0), **v) for v in changes]
        engine = show.CueEngine(cues, self.backend, lambda: self.now)
        self.backend.engine = engine
        return engine

    def step(self, engine, now):
        self.now = now
        engine.tick()

    def waiting(self, engine, index):
        cue_id = engine.cues[index]['id']
        self.assertIn(cue_id, engine.pending)
        self.assertIn(cue_id, engine._waiting_preparation)
        self.assertNotIn(cue_id, engine.errors)

    def test_continue_waits_then_starts_once_without_touching_live_deck(self):
        e = self.engine({'follow': 'continue', 'fade': 2}, {})
        document = copy.deepcopy(e.cues)
        e.go(0); e.tick()
        live = self.backend.tracks[1]
        self.step(e, .1)
        self.waiting(e, 1)
        self.assertIs(self.backend.tracks[1], live)
        self.assertEqual(self.backend.stops, [])
        self.assertEqual(self.backend._deck.call_count, 1)
        self.step(e, 2); self.step(e, 2.1); self.step(e, 3)
        self.assertEqual([v[0] for v in self.backend.starts], [c['id'] for c in e.cues])
        self.assertFalse(e.errors or e.pending or e._waiting_preparation)
        self.assertEqual(e.cues, document)

    def test_three_continue_cues_preserve_order(self):
        e = self.engine({'follow': 'continue'}, {'follow': 'continue'}, {})
        e.go(0)
        for i in range(50):
            self.step(e, i / 10)
        self.assertEqual([v[0] for v in self.backend.starts], [c['id'] for c in e.cues])
        self.assertFalse(e.errors or e._waiting_preparation)

    def test_other_track_does_not_wait_for_crossfade(self):
        e = self.engine({'follow': 'continue', 'fade': 60}, {'track': 2})
        e.go(0); e.tick(); self.step(e, .1)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e._waiting_preparation or e.errors)
        self.assertTrue(self.backend.tracks[1]['fading'])

    def test_long_fade_does_not_use_media_readiness_timeout(self):
        e = self.engine({'follow': 'continue', 'fade': 60}, {})
        e.go(0); e.tick(); self.step(e, .1); self.step(e, 40)
        self.waiting(e, 1)
        self.step(e, 60); self.step(e, 60.1)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e.errors)

    def test_media_timeout_starts_after_resource_is_available(self):
        e = self.engine({'follow': 'continue', 'fade': 60}, {})
        e.go(0); e.tick(); self.step(e, .1); self.step(e, 60)
        self.backend.media_ready = False
        self.step(e, 61); self.step(e, 90)
        self.assertIn(e.cues[1]['id'], e.pending)
        self.assertNotIn(e.cues[1]['id'], e._waiting_preparation)
        self.assertFalse(e.errors)
        self.step(e, 92)
        self.assertIn('30 seconds', e.errors[e.cues[1]['id']])
        self.assertIs(self.backend.tracks[1]['cue'], e.cues[0])

    def test_pause_holds_queue_and_resume_retries(self):
        e = self.engine({'follow': 'continue', 'fade': 2}, {})
        e.go(0); e.tick(); self.step(e, .1); e.pause()
        calls = len(self.backend.prepare_calls)
        self.step(e, 100)
        self.assertEqual(len(self.backend.prepare_calls), calls)
        self.assertEqual(e.elapsed, .1)
        self.waiting(e, 1)
        e.resume(); self.step(e, 103); self.step(e, 103.1)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e.errors)

    def test_stop_selected_cancels_waiting_request(self):
        e = self.engine({'follow': 'continue'}, {})
        e.go(0); e.tick(); self.step(e, .1); e.stop_cue(1)
        self.step(e, 10); self.step(e, 11)
        self.assertFalse(e.pending or e._waiting_preparation or e.errors)
        self.assertEqual(len(self.backend.starts), 1)

    def test_stop_all_clears_wait_and_allows_a_new_run(self):
        e = self.engine({'follow': 'continue'}, {})
        e.go(0); e.tick(); self.step(e, .1); e.stop()
        self.assertFalse(e.pending or e._waiting_preparation or e.triggered)
        e.go(0); e.tick(); self.step(e, 2); self.step(e, 2.1)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e.errors)

    def test_go_back_disarms_waiting_forward_request(self):
        e = self.engine({'follow': 'continue'}, {})
        e.go(0); e.tick(); self.step(e, .1)
        self.backend.tick(2)  # The live fade is complete; queue has not retried.
        e.go_back(); self.step(e, 2); self.step(e, 3); self.step(e, 4)
        self.assertNotIn(e.cues[1]['id'], e.pending)
        self.assertNotIn(e.cues[1]['id'], e.active)
        self.assertFalse(e._waiting_preparation or e.errors)

    def test_postwait_and_prewait_remain_relative_to_original_request(self):
        e = self.engine({'follow': 'continue', 'postwait': 2, 'fade': 10}, {'prewait': 3})
        e.go(0); e.tick(); self.step(e, 1)
        self.assertNotIn(e.cues[1]['id'], e.pending)
        self.step(e, 2); self.waiting(e, 1)
        self.assertEqual(e.pending[e.cues[1]['id']][1], 5)
        self.step(e, 10); self.step(e, 10.1)
        self.assertEqual(self.backend.starts[-1][1], 10.1)

    def test_busy_standby_is_not_overwritten(self):
        e = self.engine({'follow': 'continue', 'fade': 0}, {}, {})
        e.go(0); e.tick()
        self.backend.prepare(e.cues[2])
        reserved = self.backend.prepared[e.cues[2]['id']]
        self.step(e, .1); self.waiting(e, 1)
        self.assertIs(self.backend.prepared[e.cues[2]['id']], reserved)
        e.stop_cue(2); self.step(e, .2)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e.errors)

    def test_missing_media_is_error_not_wait(self):
        e = self.engine({'follow': 'continue'}, {'source': 'missing'})
        e.go(0); e.tick(); self.step(e, .1)
        self.assertEqual(e.errors[e.cues[1]['id']], 'Missing media: fixture')
        self.assertFalse(e._waiting_preparation)

    def test_missing_media_during_wait_is_reported_and_queue_removed(self):
        e = self.engine({'follow': 'continue'}, {})
        e.go(0); e.tick(); self.step(e, .1)
        self.backend._media_path = Mock(side_effect=ValueError('Media disappeared'))
        self.step(e, .2)
        self.assertEqual(e.errors[e.cues[1]['id']], 'Media disappeared')
        self.assertFalse(e.pending or e._waiting_preparation)

    def test_manual_go_still_reports_busy_without_queueing(self):
        e = self.engine({}, {})
        e.go(0); e.tick()
        with self.assertRaises(show.CuePreparationBusy):
            e.go(1)
        self.assertNotIn(e.cues[1]['id'], e.pending)
        self.assertFalse(e.errors or e._waiting_preparation)

    def test_auto_skips_disabled_row_and_nonvisual_can_run_during_fade(self):
        e = self.engine({'follow': 'continue'}, {'enabled': False}, {'kind': 'wait'})
        e.go(0); e.tick(); self.step(e, .1)
        self.assertIn(e.cues[2]['id'], e.active)
        self.assertFalse(e._waiting_preparation or e.errors)

    def test_timestamp_and_follow_share_safe_wait_path(self):
        for behavior in ('timestamp', 'follow'):
            with self.subTest(behavior=behavior):
                self.setUp()
                e = self.engine({'fade': 5}, {'at': .1 if behavior == 'timestamp' else None})
                e.go(0); e.tick()
                if behavior == 'follow':
                    e.follows.append((.1, 1, e.cues[0]['id']))
                self.step(e, .1); self.waiting(e, 1)
                self.step(e, 5); self.step(e, 5.1)
                self.assertIn(e.cues[1]['id'], e.active)
                self.assertFalse(e.errors)

    def test_follow_waits_for_duration_postwait_and_next_prewait(self):
        e = self.engine({'duration': 2, 'follow': 'follow', 'postwait': 1}, {'prewait': 3})
        e.go(0); e.tick(); self.step(e, 1.9)
        self.assertNotIn(e.cues[1]['id'], e.pending)
        self.step(e, 2)
        self.assertEqual(e.follows[0][:2], (3, 1))
        self.step(e, 2.9)
        self.assertNotIn(e.cues[1]['id'], e.pending)
        self.step(e, 3)
        self.assertEqual(e.pending[e.cues[1]['id']][1], 6)
        self.step(e, 5.9)
        self.assertNotIn(e.cues[1]['id'], e.active)
        self.step(e, 6)
        self.assertEqual(self.backend.starts[-1], (e.cues[1]['id'], 6))
        self.assertFalse(e.errors)

    def test_follow_duration_does_not_elapse_while_paused(self):
        e = self.engine({'duration': 2, 'follow': 'follow'}, {})
        e.go(0); e.tick(); self.step(e, 1); e.pause()
        self.step(e, 100)
        self.assertFalse(e.follows or e.pending)
        self.assertIn(e.cues[0]['id'], e.active)
        e.resume(); self.step(e, 101); self.step(e, 101.1)
        self.assertIn(e.cues[1]['id'], e.active)
        self.assertFalse(e.errors)

    def test_stopping_parent_before_completion_cancels_follow(self):
        e = self.engine({'duration': 2, 'follow': 'follow'}, {})
        e.go(0); e.tick(); self.step(e, 1); e.stop_cue(0)
        self.step(e, 10); self.step(e, 11)
        self.assertFalse(e.follows or e.pending or e.active or e.errors)
        self.assertEqual(len(self.backend.starts), 1)

    def test_real_follow_waits_for_another_cues_track_reservation(self):
        e = self.engine({'fade': 5}, {'kind': 'wait', 'track': 2, 'duration': 1, 'follow': 'follow'}, {})
        e.go(0); e.tick(); e.go(1); e.tick()
        self.step(e, 1); self.step(e, 1.1)
        self.waiting(e, 2)
        self.assertIs(self.backend.tracks[1]['cue'], e.cues[0])
        self.step(e, 5); self.step(e, 5.1)
        self.assertIn(e.cues[2]['id'], e.active)
        self.assertFalse(e.errors or e.pending or e._waiting_preparation)


if __name__ == '__main__':
    unittest.main()
