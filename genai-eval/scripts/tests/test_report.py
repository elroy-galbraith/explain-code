#!/usr/bin/env python3
"""Tests for calibration.report. Run directly: python3 test_report.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re

from calibration import analysis, report
from calibration.loader import CalibrationData
from evalstats import power


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


class TestFiguresCarryTheirN(unittest.TestCase):
    """Every figure, not only the ones inside a confidence interval.

    The earlier version of this test only inspected lines containing "95% CI",
    which is why it could see neither of the two failures the README's second
    honesty rule promised against: the rho and delta lines carried no n at all,
    and the n the interval lines did carry was the file's row count rather than
    the units the statistic used.
    """

    FIGURE = re.compile(r"\d+\.\d{3}")

    def test_every_line_with_a_figure_names_its_sample_size(self):
        data = make_data(
            [1, 2, 3, 4, 1, 2, 3, 4],
            {
                "human_a": [1, 2, 3, 3, 1, 2, 4, 4],
                "human_b": [1, 2, 3, 4, 2, 2, 3, 4],
            },
            lengths=[10, 20, 30, 40, 15, 25, 35, 45],
            generators=["gpt-x"] * 4 + ["other"] * 4,
            item_ids=["i%d" % i for i in range(8)],
        )
        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=200),
            analysis.bias_section(data, judge_model="gpt-x"),
            analysis.disagreement_clusters(data),
            analysis.power_section(data, mid=0.10),
        )

        checked = 0
        for line in text.splitlines():
            if line.startswith("|"):
                continue  # the cluster table carries counts, not estimates
            if self.FIGURE.search(line):
                self.assertIn("n = ", line, line)
                checked += 1
        self.assertGreater(checked, 4, text)

    def test_the_n_is_the_units_the_statistic_used(self):
        """Seven of ten judge cells blank. alpha drops every unit with fewer
        than two ratings, so the figure comes from three units, and printing
        n = 10 beside it invites exactly the misreading the rule forbids."""
        data = make_data(
            [1, None, None, None, None, None, None, None, 3, 2],
            {"human": [1, 2, 3, 1, 2, 3, 1, 2, 3, 1]},
        )
        text = render_for(data)
        self.assertIn("n = 3", text)
        self.assertNotIn("n = 10", text)


class TestPowerLine(unittest.TestCase):
    def test_the_mde_prints_as_a_difference_not_as_a_proportion(self):
        """Known answer: at n = 24 against a 0.750 baseline the smallest
        detectable proportion is 0.9986, so the smallest detectable difference
        is 0.249. The report printed 0.999 under a "difference" label, which is
        arithmetically impossible on a 0.750 baseline."""
        mde = power.mde_two_proportion(24, 0.750)
        self.assertAlmostEqual(mde, 0.998569176042279, places=12)

        data = make_data([1, 2], {"human": [1, 2]})
        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=100),
            analysis.bias_section(data),
            analysis.disagreement_clusters(data),
            {
                "n": 24,
                "rows": 24,
                "baseline": 0.750,
                "mde": mde,
                "mid": None,
                "n_required": None,
                "sufficient": None,
            },
        )
        self.assertIn("can detect: 0.249", text)
        self.assertNotIn("can detect: 0.999", text)

    def test_the_requirement_is_labelled_per_group(self):
        data = make_data([1, 2, 3, 9], {"human": [1, 2, 3, 4]})
        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=200),
            analysis.bias_section(data),
            analysis.disagreement_clusters(data),
            analysis.power_section(data, mid=0.05),
        )
        self.assertIn("items per group", text)


class TestVerdictMatchesTheCeilingsState(unittest.TestCase):
    """"no_ceiling" is three states, and the sentence has to say which one.

    The report used to print a ceiling figure and then say, on the next line,
    that there was no ceiling to compare against.
    """

    def render(self, data):
        return render_for(data)

    def test_one_rater_says_one_rater(self):
        data = make_data([1, 2, 1, 2], {"human": [1, 1, 2, 2]})
        text = self.render(data)
        self.assertIn("one human rater column", text)

    def test_an_undefined_ceiling_is_not_reported_as_a_missing_rater(self):
        data = make_data(
            [1, 2, 1, 2],
            {"human_a": [1, 1, 1, 1], "human_b": [1, 1, 1, 1]},
        )
        text = self.render(data)
        self.assertIn("ceiling is itself undefined", text)
        self.assertNotIn("one human rater column", text)

    def test_a_defined_ceiling_with_an_undefined_judge_says_so(self):
        data = make_data(
            [1, 1, 1, 1],
            {"human_a": [1, 1, 1, 1], "human_b": [1, 2, 1, 2]},
        )
        text = self.render(data)
        self.assertIn("Human-human agreement", text)
        self.assertIn("judge's own agreement figure is not", text)
        self.assertNotIn("no ceiling to compare", text)


class TestSingleRaterDisclosure(unittest.TestCase):
    def test_two_raters_disclose_which_sections_use_only_the_first(self):
        """Length bias, the clusters and the power baseline all read rater A
        alone, while the header says the report ran against two columns."""
        data = make_data(
            [1, 2, 3, 4],
            {"human_a": [1, 2, 3, 3], "human_b": [1, 2, 3, 4]},
            lengths=[10, 20, 30, 40],
        )
        text = render_for(data)
        self.assertIn("first human rater column", text)
        self.assertIn("`human_a`", text)

    def test_a_single_rater_file_does_not_carry_the_disclosure(self):
        data = make_data([1, 2, 3, 4], {"human": [1, 2, 3, 3]})
        self.assertNotIn("first human rater column", render_for(data))


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
