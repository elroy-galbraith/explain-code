#!/usr/bin/env python3
"""Tests for calibration.analysis. Run directly: python3 test_analysis.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import analysis
from calibration.loader import CalibrationData


def make_data(judge, humans, **kwargs):
    return CalibrationData(
        judge_column="judge",
        judge_scores=list(judge),
        human_columns={name: list(vals) for name, vals in humans.items()},
        n=len(judge),
        numeric={"judge": True},
        **kwargs
    )


class TestNoCeilingGuard(unittest.TestCase):
    def test_one_rater_yields_no_ceiling(self):
        """The whole point of bare mode: with nothing to compare against, the
        analysis says so rather than reporting judge-human agreement as if it
        had passed a bar."""
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNone(result["human_human"])
        self.assertFalse(result["ceiling_available"])
        self.assertEqual(result["verdict"], "no_ceiling")
        self.assertTrue(
            any("no human-human ceiling" in n.lower() for n in result["notes"]),
            result["notes"],
        )

    def test_judge_human_is_still_reported_without_a_ceiling(self):
        """The number is computable and worth having — it just cannot be
        graded."""
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNotNone(result["judge_human"]["alpha"])
        self.assertEqual(result["judge_human"]["n"], 6)


class TestWithCeiling(unittest.TestCase):
    HUMANS = {
        "human_a": [1, 1, 2, 2, 1, 2, 1, 2],
        "human_b": [1, 1, 2, 2, 2, 2, 1, 1],
    }

    def test_two_raters_give_a_ceiling(self):
        data = make_data([1, 1, 2, 2, 1, 2, 1, 2], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNotNone(result["human_human"])
        self.assertTrue(result["ceiling_available"])
        self.assertIn(result["verdict"], ("at_or_above_ceiling", "below_ceiling"))

    def test_judge_agreeing_with_rater_a_exactly_reaches_the_ceiling(self):
        """Judge copies human_a. Its agreement with the pooled humans is then
        at least as good as the humans manage with each other."""
        data = make_data(self.HUMANS["human_a"], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertEqual(result["verdict"], "at_or_above_ceiling")

    def test_a_random_judge_falls_below_the_ceiling(self):
        data = make_data([2, 1, 1, 2, 2, 1, 2, 1], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertEqual(result["verdict"], "below_ceiling")

    def test_intervals_are_present_and_bracket_their_estimates(self):
        data = make_data(self.HUMANS["human_a"], self.HUMANS)
        result = analysis.agreement_section(data, seed=1, n_resamples=400)
        for block in (result["judge_human"], result["human_human"]):
            low, high = block["ci"]
            self.assertLessEqual(low, block["alpha"])
            self.assertLessEqual(block["alpha"], high)


class TestKnownAnswer(unittest.TestCase):
    def test_judge_human_alpha_matches_a_hand_derived_value(self):
        """Four units, judge and one human. Pairs are (a,a), (a,b), (b,b),
        (b,b), which is the fixture pinned at 8/15 by the agreement suite's
        own known-answer test."""
        data = make_data(["a", "a", "b", "b"], {"human": ["a", "b", "b", "b"]})
        result = analysis.agreement_section(data, seed=1, n_resamples=200)
        self.assertAlmostEqual(result["judge_human"]["alpha"], 8 / 15, places=10)


class TestDegenerate(unittest.TestCase):
    def test_all_identical_ratings_report_undefined_rather_than_one(self):
        """alpha is undefined when nothing varies. The section must carry that
        through as None with an explanation, not as perfect agreement."""
        data = make_data([1, 1, 1, 1], {"human": [1, 1, 1, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNone(result["judge_human"]["alpha"])
        self.assertTrue(
            any("undefined" in n.lower() for n in result["notes"]), result["notes"]
        )

    def test_too_few_items_for_an_interval_is_reported_not_faked(self):
        """One item: alpha is computable (the single unit's two ratings
        disagree, giving 0.0), but bootstrap_ci needs at least two units. The
        point estimate survives and the interval is honestly absent, rather
        than a zero-width interval implying certainty."""
        data = make_data([1], {"human": [2]})
        result = analysis.agreement_section(data, seed=1, n_resamples=100)
        self.assertAlmostEqual(result["judge_human"]["alpha"], 0.0, places=10)
        self.assertIsNone(result["judge_human"]["ci"])
        self.assertTrue(
            any("confidence interval" in n.lower() for n in result["notes"]),
            result["notes"],
        )


if __name__ == "__main__":
    unittest.main()
