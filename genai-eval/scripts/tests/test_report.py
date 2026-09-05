#!/usr/bin/env python3
"""Tests for calibration.report. Run directly: python3 test_report.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import analysis, report
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


def render_for(data, **kwargs):
    return report.render(
        data,
        analysis.agreement_section(data, seed=1, n_resamples=200),
        analysis.bias_section(data, **kwargs),
        analysis.disagreement_clusters(data),
        analysis.power_section(data),
    )


class TestNoCeilingIsProminent(unittest.TestCase):
    def setUp(self):
        self.data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        self.text = render_for(self.data)

    def test_says_there_is_no_ceiling(self):
        self.assertIn("no human-human ceiling", self.text.lower())

    def test_limits_appear_before_the_agreement_numbers(self):
        """A reader who stops halfway must already have seen what the figures
        cannot support."""
        limits = self.text.lower().index("what this report cannot")
        numbers = self.text.lower().index("judge-human agreement")
        self.assertLess(limits, numbers)

    def test_gate_6_is_marked_unanswered(self):
        self.assertIn("Gate 6", self.text)
        self.assertIn("unanswered", self.text.lower())


class TestWithCeiling(unittest.TestCase):
    def test_reports_both_figures_and_the_verdict(self):
        humans = {
            "human_a": [1, 1, 2, 2, 1, 2, 1, 2],
            "human_b": [1, 1, 2, 2, 2, 2, 1, 1],
        }
        data = make_data(humans["human_a"], humans)
        text = render_for(data)
        self.assertIn("Judge-human agreement", text)
        self.assertIn("Human-human agreement", text)
        self.assertIn("reaches the ceiling", text.lower())


class TestIntervalsCarryTheirN(unittest.TestCase):
    def test_every_printed_interval_names_its_sample_size(self):
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        text = render_for(data)
        for line in text.splitlines():
            if "95% CI" in line:
                self.assertIn("n = ", line, line)


class TestClustersAndProbes(unittest.TestCase):
    def test_disagreement_table_lists_the_biggest_cluster_first(self):
        data = make_data(
            [5, 5, 5, 3, 4, 2],
            {"human": [3, 3, 3, 5, 4, 2]},
            item_ids=["i1", "i2", "i3", "i4", "i5", "i6"],
        )
        text = render_for(data)
        self.assertIn("Disagreement clusters", text)
        first = text.index("| 3 | 5 |")
        second = text.index("| 5 | 3 |")
        self.assertLess(first, second)

    def test_unavailable_probes_are_named_not_omitted(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        text = render_for(data)
        self.assertIn("Not measured", text)
        self.assertIn("Length bias", text)

    def test_undefined_values_render_as_a_dash_not_a_zero(self):
        data = make_data([1, 1, 1, 1], {"human": [1, 1, 1, 1]})
        text = render_for(data)
        self.assertNotIn("0.000", text)
        self.assertIn("—", text)


class TestTitle(unittest.TestCase):
    def test_custom_title_is_used(self):
        data = make_data([1, 2], {"human": [1, 2]})
        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=100),
            analysis.bias_section(data),
            analysis.disagreement_clusters(data),
            analysis.power_section(data),
            title="Retrieval judge v4",
        )
        self.assertTrue(text.startswith("# Retrieval judge v4"))


class TestPartiallyUndefinedBiasFigures(unittest.TestCase):
    """The probe ran, but its headline number came back undefined.

    This is a different state from a probe that could not run: the dict is
    present, so the report renders that probe's line rather than listing it
    under "Not measured". The undefined figure has to reach the reader as a
    dash — a fabricated 0.000 there would read as a real measurement of no
    bias, which is the opposite of what the data supports.
    """

    def test_length_gap_undefined_renders_as_a_dash(self):
        """Humans scored every response identically, so there is no human
        baseline to measure the judge's length preference against. judge_rho
        is computable; the gap is not."""
        data = make_data(
            [1, 2, 3],
            {"human": [3, 3, 3]},
            lengths=[10, 20, 30],
        )
        bias_result = analysis.bias_section(data)

        self.assertIsNotNone(bias_result["length"])
        self.assertIsNone(bias_result["length"]["gap"])

        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=200),
            bias_result,
            analysis.disagreement_clusters(data),
            analysis.power_section(data),
        )
        self.assertIn("gap —", text)
        self.assertNotIn("gap 0.000", text)

    def test_self_preference_delta_undefined_renders_as_a_dash(self):
        """The judge's own model produced none of these responses, so there is
        nothing to compare its scores against and delta is undefined."""
        data = make_data(
            [5, 3, 4],
            {"human": [4, 4, 4]},
            generators=["other", "other", "other"],
        )
        bias_result = analysis.bias_section(data, judge_model="gpt-x")

        self.assertIsNotNone(bias_result["self_preference"])
        self.assertIsNone(bias_result["self_preference"]["delta"])

        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=200),
            bias_result,
            analysis.disagreement_clusters(data),
            analysis.power_section(data),
        )
        self.assertIn("delta —", text)
        self.assertNotIn("delta 0.000", text)


if __name__ == "__main__":
    unittest.main()
