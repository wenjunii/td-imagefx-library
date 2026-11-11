import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from profile_live import Timings, diagnostic_config, percentile


class LiveProfileTests(unittest.TestCase):
    def test_percentile(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([2], .95), 2)
        self.assertAlmostEqual(percentile([0, 100], .95), 95)

    def test_summary_excludes_warmup_and_nested_spans_remain_separate(self):
        timing = Timings()
        timing.record('render', 0, 1)
        timing.record('render', 2, 2.020)
        timing.record('readback', 2.010, 2.015)
        timing.record('render', 3, 4)
        summary = timing.summarize(1, 3)
        self.assertEqual(summary['render']['calls'], 1)
        self.assertAlmostEqual(summary['render']['median_ms'], 20)
        self.assertAlmostEqual(summary['readback']['p95_ms'], 5)

    def test_wrapper_records_failures_and_propagates_result(self):
        timing = Timings()
        with patch('profile_live.time.perf_counter', side_effect=[1, 1.01, 2, 2.02]):
            self.assertEqual(timing.wrap('ok', lambda: 42)(), 42)
            with self.assertRaises(ZeroDivisionError):
                timing.wrap('error', lambda: 1/0)()
        self.assertEqual(len(timing.samples), 2)

    def test_diagnostic_is_recording_only_and_does_not_mutate_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'video.mp4'
            path.touch()
            config = dict(provider='cuda', render_gpu='RTX', profile=temp, models=temp, analyze=True)
            result = diagnostic_config(config, path, 180, 15)
            self.assertTrue(config['analyze'])
            self.assertFalse(result['analyze'])
            self.assertEqual(result['diagnostic_replay'], str(path.resolve()))
            for frames, warmup in ((1, 1), (10, 0), (1801, 5)):
                with self.assertRaises(ValueError): diagnostic_config(config, path, frames, warmup)
            with self.assertRaises(ValueError): diagnostic_config(config, Path(temp) / 'missing', 20, 5)
            with self.assertRaises(ValueError): diagnostic_config(dict(config, provider='cpu'), path, 20, 5)
            with self.assertRaises(ValueError): diagnostic_config(dict(config, render_gpu=''), path, 20, 5)


if __name__ == '__main__':
    unittest.main()
