#!/usr/bin/env python3
"""Known-answer tests for evalstats.bias. Run directly: python3 test_bias.py"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import bias


class TestRankCorrelation(unittest.TestCase):
    def test_known_answer_no_ties(self):
        """xs = [1,2,3,4,5], ys = [2,1,4,3,5]; rank differences are
        [-1, 1, -1, 1, 0], so sum(d^2) = 4.
        rho = 1 - 6*4/(5*(25-1)) = 1 - 24/120 = 0.8
        """
        got = bias.rank_correlation([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
        self.assertAlmostEqual(got, 0.8, places=10)

    def test_known_answer_with_ties(self):
        """xs = [1,2,2,3] gets average ranks [1, 2.5, 2.5, 4] against
        ys ranks [1,2,3,4]. Pearson on those ranks is 4.5/sqrt(4.5*5)
        = 4.5/sqrt(22.5) = sqrt(0.9)
        """
        got = bias.rank_correlation([1, 2, 2, 3], [1, 2, 3, 4])
        self.assertAlmostEqual(got, math.sqrt(0.9), places=10)

    def test_monotonic_is_one(self):
        self.assertAlmostEqual(
            bias.rank_correlation([1, 2, 3, 4], [10, 20, 30, 40]), 1.0, places=10
        )

    def test_reversed_is_minus_one(self):
        self.assertAlmostEqual(
            bias.rank_correlation([1, 2, 3, 4], [40, 30, 20, 10]), -1.0, places=10
        )

    def test_constant_input_returns_none(self):
        self.assertIsNone(bias.rank_correlation([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.rank_correlation([1, 2], [1])

    def test_single_point_raises(self):
        with self.assertRaises(ValueError):
            bias.rank_correlation([1], [1])


class TestLengthBias(unittest.TestCase):
    def test_constant_human_scores_leave_the_gap_undefined(self):
        """Humans who gave every response the same score provide no baseline to
        compare the judge against, so the gap is None rather than equal to
        judge_rho. Reporting the judge's raw length correlation as 'bias' here
        would be exactly the mistake this function exists to avoid."""
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]      # tracks length exactly
        human = [3, 3, 3, 3, 3]      # no variance, so no baseline
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["judge_rho"], 1.0, places=10)
        self.assertIsNone(result["human_rho"])
        self.assertIsNone(result["gap"])

    def test_shared_length_preference_is_not_flagged_as_bias(self):
        """Both judge and humans prefer the longer answers, so the gap is zero.
        Length correlation alone is not bias."""
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]
        human = [1, 2, 3, 4, 5]
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["gap"], 0.0, places=10)

    def test_gap_is_judge_minus_human(self):
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]
        human = [5, 4, 3, 2, 1]
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["judge_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["human_rho"], -1.0, places=10)
        self.assertAlmostEqual(result["gap"], 2.0, places=10)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.length_bias([1, 2], [1, 2], [1])


if __name__ == "__main__":
    unittest.main()
