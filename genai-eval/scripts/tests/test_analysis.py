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

    def test_undefined_ceiling_gives_no_verdict_even_with_two_raters(self):
        """Both raters gave every item the same score, so the ceiling itself is
        undefined. The judge's own alpha is computable, and the tempting bug is
        to report it as passing — there is nothing to pass against.

        Guards the first of two branches that a swapped elif would silently
        skip while still passing every other test in this file.
        """
        data = make_data(
            [1, 2, 1, 2],
            {"human_a": [1, 1, 1, 1], "human_b": [1, 1, 1, 1]},
        )
        result = analysis.agreement_section(data, seed=1, n_resamples=200)

        self.assertIsNotNone(result["judge_human"]["alpha"])
        self.assertIsNone(result["human_human"]["alpha"])
        self.assertFalse(result["ceiling_available"])
        self.assertEqual(result["verdict"], "no_ceiling")

    def test_undefined_judge_alpha_gives_no_verdict_even_with_a_ceiling(self):
        """The mirror case: the raters disagree enough for a real ceiling, but
        the judge matched the pooled human on every item, so its own alpha is
        undefined. A comparison against None must not happen.

        Guards the second of the two branches.
        """
        data = make_data(
            [1, 1, 1, 1],
            {"human_a": [1, 1, 1, 1], "human_b": [1, 2, 1, 2]},
        )
        result = analysis.agreement_section(data, seed=1, n_resamples=200)

        self.assertIsNone(result["judge_human"]["alpha"])
        self.assertIsNotNone(result["human_human"]["alpha"])
        self.assertEqual(result["verdict"], "no_ceiling")


class TestBiasSection(unittest.TestCase):
    def test_both_probes_unavailable_on_a_minimal_file(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        result = analysis.bias_section(data)
        self.assertIsNone(result["length"])
        self.assertIsNone(result["self_preference"])
        joined = " ".join(result["unavailable"]).lower()
        self.assertIn("length", joined)
        self.assertIn("generator", joined)

    def test_length_probe_runs_when_lengths_are_present(self):
        """Judge tracks length exactly, humans invert it, so the gap is the
        full 2.0 — the same known answer the bias suite pins."""
        data = make_data(
            [1, 2, 3, 4, 5],
            {"human": [5, 4, 3, 2, 1]},
            lengths=[10, 20, 30, 40, 50],
        )
        result = analysis.bias_section(data)
        self.assertAlmostEqual(result["length"]["judge_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["length"]["human_rho"], -1.0, places=10)
        self.assertAlmostEqual(result["length"]["gap"], 2.0, places=10)

    def test_self_preference_needs_a_judge_model_name(self):
        data = make_data(
            [5, 5, 3, 3],
            {"human": [4, 4, 4, 4]},
            generators=["gpt-x", "gpt-x", "other", "other"],
        )
        without = analysis.bias_section(data)
        self.assertIsNone(without["self_preference"])
        self.assertTrue(
            any("judge model" in u.lower() for u in without["unavailable"]),
            without["unavailable"],
        )

        with_name = analysis.bias_section(data, judge_model="gpt-x")
        self.assertAlmostEqual(with_name["self_preference"]["delta"], 2.0, places=10)

    def test_constant_human_scores_leave_the_length_gap_undefined(self):
        """A judge's raw length correlation is not bias — the gap against the
        humans is. With no human variance there is no gap to report."""
        data = make_data(
            [1, 2, 3, 4, 5],
            {"human": [3, 3, 3, 3, 3]},
            lengths=[10, 20, 30, 40, 50],
        )
        result = analysis.bias_section(data)
        self.assertIsNone(result["length"]["gap"])


class TestDisagreementClusters(unittest.TestCase):
    def test_known_counts_and_ordering(self):
        """Six items. The judge says 5 where the human said 3 three times, and
        3 where the human said 5 once; two items agree. So there are two
        clusters of sizes 3 and 1, shares 0.75 and 0.25, biggest first."""
        data = make_data(
            [5, 5, 5, 3, 4, 2],
            {"human": [3, 3, 3, 5, 4, 2]},
            item_ids=["i1", "i2", "i3", "i4", "i5", "i6"],
        )
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["human"], 3)
        self.assertEqual(clusters[0]["judge"], 5)
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[0]["item_ids"], ["i1", "i2", "i3"])
        self.assertAlmostEqual(clusters[0]["share"], 0.75, places=10)
        self.assertEqual(clusters[1]["count"], 1)
        self.assertAlmostEqual(clusters[1]["share"], 0.25, places=10)

    def test_perfect_agreement_gives_no_clusters(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        self.assertEqual(analysis.disagreement_clusters(data), [])

    def test_missing_item_ids_leave_the_list_empty_not_absent(self):
        data = make_data([5, 3], {"human": [3, 5]})
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(clusters[0]["item_ids"], [])

    def test_rows_with_a_missing_rating_are_skipped(self):
        """A blank cell is not a disagreement."""
        data = make_data([5, 5], {"human": [3, None]})
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["count"], 1)

    def test_limit_truncates_the_tail(self):
        data = make_data([5, 5, 4, 3], {"human": [1, 1, 1, 1]})
        self.assertEqual(len(analysis.disagreement_clusters(data, limit=1)), 1)


if __name__ == "__main__":
    unittest.main()
