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


class TestPositionBias(unittest.TestCase):
    def test_consistent_judge_has_no_position_effect(self):
        """The judge picks the same content whichever order it saw, so it picks
        the first-shown option exactly half the time."""
        pairs = [("A", "A"), ("B", "B"), ("A", "A"), ("B", "B")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 0.5, places=10)
        self.assertAlmostEqual(result["consistency"], 1.0, places=10)
        self.assertEqual(result["n"], 4)

    def test_judge_that_always_picks_first_is_fully_biased(self):
        """Picks A when A is first, B when B is first: never the same content."""
        pairs = [("A", "B"), ("A", "B"), ("A", "B")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 1.0, places=10)
        self.assertAlmostEqual(result["consistency"], 0.0, places=10)

    def test_judge_that_always_picks_second(self):
        pairs = [("B", "A"), ("B", "A")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 0.0, places=10)
        self.assertAlmostEqual(result["consistency"], 0.0, places=10)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            bias.position_bias([])

    def test_unknown_choice_raises(self):
        with self.assertRaises(ValueError):
            bias.position_bias([("A", "C")])


class TestSelfPreference(unittest.TestCase):
    def test_judge_scoring_its_own_output_higher(self):
        scores = [5, 5, 3, 3]
        generators = ["gpt-x", "gpt-x", "other", "other"]
        result = bias.self_preference(scores, generators, "gpt-x")
        self.assertAlmostEqual(result["own_mean"], 5.0, places=10)
        self.assertAlmostEqual(result["other_mean"], 3.0, places=10)
        self.assertAlmostEqual(result["delta"], 2.0, places=10)
        self.assertEqual(result["n_own"], 2)
        self.assertEqual(result["n_other"], 2)

    def test_no_own_outputs_gives_no_delta(self):
        result = bias.self_preference([3, 4], ["other", "other"], "gpt-x")
        self.assertIsNone(result["delta"])
        self.assertEqual(result["n_own"], 0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.self_preference([1, 2], ["a"], "a")


class TestPromptSensitivity(unittest.TestCase):
    def test_identical_variants_are_perfectly_stable(self):
        variants = [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["mean_spread"], 0.0, places=10)
        self.assertEqual(result["n_variants"], 3)

    def test_reworded_rubric_that_flips_the_ranking(self):
        variants = [[1, 2, 3, 4], [4, 3, 2, 1]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], -1.0, places=10)

    def test_shifted_variant_keeps_ranking_but_moves_the_mean(self):
        variants = [[1, 2, 3, 4], [2, 3, 4, 5]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["mean_spread"], 1.0, places=10)

    def test_single_variant_raises(self):
        with self.assertRaises(ValueError):
            bias.prompt_sensitivity([[1, 2, 3]])

    def test_ragged_variants_raise(self):
        with self.assertRaises(ValueError):
            bias.prompt_sensitivity([[1, 2, 3], [1, 2]])


if __name__ == "__main__":
    unittest.main()
