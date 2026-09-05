#!/usr/bin/env python3
"""Known-answer tests for evalstats.saturation. Run: python3 test_saturation.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import saturation


class TestCeilingProportion(unittest.TestCase):
    def test_known_answer(self):
        """Two of four scores sit at the maximum, so the proportion is 0.5."""
        self.assertAlmostEqual(
            saturation.ceiling_proportion([5, 5, 4, 3], max_score=5), 0.5, places=10
        )

    def test_all_at_ceiling(self):
        self.assertAlmostEqual(
            saturation.ceiling_proportion([1, 1, 1], max_score=1), 1.0, places=10
        )

    def test_none_at_ceiling(self):
        self.assertAlmostEqual(
            saturation.ceiling_proportion([1, 2, 3], max_score=5), 0.0, places=10
        )

    def test_scores_above_the_maximum_still_count(self):
        """A grader that can exceed its own stated maximum is a bug, but the
        item is still at ceiling and must not be silently dropped."""
        self.assertAlmostEqual(
            saturation.ceiling_proportion([6, 5, 1, 1], max_score=5), 0.5, places=10
        )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            saturation.ceiling_proportion([], max_score=5)


class TestCanaryHitRate(unittest.TestCase):
    def test_known_answer(self):
        outputs = [
            "the answer is 42",
            "CANARY-9f3b leaked into this one",
            "nothing here",
        ]
        self.assertAlmostEqual(
            saturation.canary_hit_rate(outputs, "CANARY-9f3b"), 1 / 3, places=10
        )

    def test_no_hits(self):
        self.assertAlmostEqual(
            saturation.canary_hit_rate(["a", "b"], "CANARY-9f3b"), 0.0, places=10
        )

    def test_every_output_hits(self):
        self.assertAlmostEqual(
            saturation.canary_hit_rate(["x CANARY y", "CANARY"], "CANARY"),
            1.0,
            places=10,
        )

    def test_empty_outputs_raise(self):
        with self.assertRaises(ValueError):
            saturation.canary_hit_rate([], "CANARY")

    def test_empty_canary_raises(self):
        """An empty needle matches every string, which would report total
        contamination on clean data."""
        with self.assertRaises(ValueError):
            saturation.canary_hit_rate(["a"], "")


class TestSaturationReport(unittest.TestCase):
    def test_healthy_pool_is_not_saturated(self):
        report = saturation.saturation_report([5, 5, 4, 3], max_score=5)
        self.assertAlmostEqual(report["ceiling_proportion"], 0.5, places=10)
        self.assertEqual(report["n"], 4)
        self.assertFalse(report["saturated"])

    def test_pool_at_the_threshold_is_saturated(self):
        scores = [5] * 19 + [4]  # 0.95 at ceiling
        report = saturation.saturation_report(scores, max_score=5)
        self.assertAlmostEqual(report["ceiling_proportion"], 0.95, places=10)
        self.assertTrue(report["saturated"])

    def test_threshold_is_configurable(self):
        scores = [5] * 8 + [4] * 2  # 0.8 at ceiling
        self.assertFalse(saturation.saturation_report(scores, 5)["saturated"])
        self.assertTrue(
            saturation.saturation_report(scores, 5, ceiling_threshold=0.75)["saturated"]
        )


if __name__ == "__main__":
    unittest.main()
