#!/usr/bin/env python3
"""Known-answer tests for evalstats.agreement. Run directly: python3 test_agreement.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import agreement


def _from_matrix(counts):
    """Expand a {(rater_a_value, rater_b_value): n} dict into two parallel lists."""
    a, b = [], []
    for (x, y), n in counts.items():
        a.extend([x] * n)
        b.extend([y] * n)
    return a, b


class TestCohensKappa(unittest.TestCase):
    def test_known_answer_2x2(self):
        """2x2 table: 20/5/10/65.

        p_o = (20 + 65) / 100 = 0.85
        marginals: A=(25, 75), B=(30, 70)
        p_e = (25*30 + 75*70) / 100^2 = 6000 / 10000 = 0.60
        kappa = (0.85 - 0.60) / (1 - 0.60) = 0.25 / 0.40 = 0.625
        """
        a, b = _from_matrix({(1, 1): 20, (1, 0): 5, (0, 1): 10, (0, 0): 65})
        self.assertAlmostEqual(agreement.cohens_kappa(a, b), 0.625, places=10)

    def test_perfect_agreement_is_one(self):
        a = [1, 2, 3, 1, 2, 3]
        self.assertAlmostEqual(agreement.cohens_kappa(a, a), 1.0, places=10)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([1, 2, 3], [1, 2])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([], [])

    def test_single_category_raises(self):
        """Both raters used one category, so p_e == 1.0 and kappa is undefined."""
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([1, 1, 1], [1, 1, 1])


# Ordinal 3x3 confusion matrix used by the weighted-kappa tests.
#   rater A rows, rater B columns, N = 20
#         B=1  B=2  B=3
#   A=1     4    2    0
#   A=2     1    5    1
#   A=3     0    2    5
_ORDINAL_3X3 = {
    (1, 1): 4, (1, 2): 2, (1, 3): 0,
    (2, 1): 1, (2, 2): 5, (2, 3): 1,
    (3, 1): 0, (3, 2): 2, (3, 3): 5,
}


class TestWeightedKappa(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _from_matrix(_ORDINAL_3X3)

    def test_unweighted_known_answer(self):
        """p_o = 14/20 = 0.70; row marginals (6, 7, 7), col marginals (5, 9, 6)
        p_e = (6*5 + 7*9 + 7*6) / 400 = 135 / 400 = 0.3375
        kappa = (0.70 - 0.3375) / (1 - 0.3375) = 0.3625 / 0.6625 = 29/53
        """
        self.assertAlmostEqual(agreement.cohens_kappa(self.a, self.b), 29 / 53, places=10)

    def test_linear_known_answer(self):
        """Agreement weights w = 1 - |i-j|/(k-1), k = 3, so w = 1, 0.5, 0.

        weighted p_o = [1*(4+5+5) + 0.5*(2+1+1+2)] / 20 = 17/20 = 0.85
        weighted p_e = [1*(30+63+42) + 0.5*(54+35+42+63)] / 400
                     = (135 + 97) / 400 = 232/400 = 0.58
        kappa_w = (0.85 - 0.58) / (1 - 0.58) = 0.27 / 0.42 = 9/14
        """
        got = agreement.weighted_kappa(self.a, self.b, weights="linear")
        self.assertAlmostEqual(got, 9 / 14, places=10)

    def test_quadratic_known_answer(self):
        """Agreement weights w = 1 - (|i-j|/(k-1))^2, so w = 1, 0.75, 0.

        weighted p_o = [1*14 + 0.75*6] / 20 = 18.5/20 = 0.925
        weighted p_e = [1*135 + 0.75*194] / 400 = 280.5/400 = 0.70125
        kappa_q = (0.925 - 0.70125) / (1 - 0.70125) = 0.22375 / 0.29875 = 179/239
        """
        got = agreement.weighted_kappa(self.a, self.b, weights="quadratic")
        self.assertAlmostEqual(got, 179 / 239, places=10)

    def test_weighting_orders_as_expected(self):
        """Partial credit for near-misses can only raise the statistic, and
        quadratic forgives a one-step disagreement more than linear does."""
        plain = agreement.cohens_kappa(self.a, self.b)
        linear = agreement.weighted_kappa(self.a, self.b, weights="linear")
        quad = agreement.weighted_kappa(self.a, self.b, weights="quadratic")
        self.assertLess(plain, linear)
        self.assertLess(linear, quad)

    def test_unknown_weighting_raises(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa(self.a, self.b, weights="cubic")

    def test_single_category_raises(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa([1, 1], [1, 1])


class TestFleissKappa(unittest.TestCase):
    def test_known_answer(self):
        """3 raters, 4 items, 2 categories.

        P_i = (sum(n_ij^2) - n) / (n(n-1)), n = 3:
          [3,0] -> (9 - 3)/6 = 1
          [2,1] -> (5 - 3)/6 = 1/3
          [0,3] -> (9 - 3)/6 = 1
          [1,2] -> (5 - 3)/6 = 1/3
        P_bar = (1 + 1/3 + 1 + 1/3)/4 = 2/3
        p_j = (6/12, 6/12) = (0.5, 0.5); P_e = 0.25 + 0.25 = 0.5
        kappa = (2/3 - 1/2) / (1 - 1/2) = (1/6)/(1/2) = 1/3
        """
        counts = [[3, 0], [2, 1], [0, 3], [1, 2]]
        self.assertAlmostEqual(agreement.fleiss_kappa(counts), 1 / 3, places=10)

    def test_perfect_agreement_is_one(self):
        counts = [[3, 0], [0, 3], [3, 0]]
        self.assertAlmostEqual(agreement.fleiss_kappa(counts), 1.0, places=10)

    def test_ragged_rows_raise(self):
        with self.assertRaises(ValueError):
            agreement.fleiss_kappa([[3, 0], [2, 0]])

    def test_ragged_rows_with_matching_sums_still_raise(self):
        """[[3, 0], [0, 1, 2]] has equal row sums (3 and 3), so the sum check
        alone lets it through — n_categories then comes from len(counts[0])
        == 2, and the third column of row two is invisible to the proportions
        loop, silently producing a wrong-but-plausible kappa instead of
        raising. A row-length check is needed alongside the sum check."""
        with self.assertRaises(ValueError):
            agreement.fleiss_kappa([[3, 0], [0, 1, 2]])

    def test_single_rater_raises(self):
        with self.assertRaises(ValueError):
            agreement.fleiss_kappa([[1, 0], [0, 1]])


class TestKrippendorffNominal(unittest.TestCase):
    def test_known_answer_complete_data(self):
        """Four units, two raters, no missing data.

        units = [[a,a], [a,b], [b,b], [b,b]]
        Each unit has m = 2 ratings, so each ordered pair carries weight
        1/(m-1) = 1. The coincidence matrix is o_aa = 2, o_ab = 1, o_ba = 1,
        o_bb = 4, total n = 8, marginals n_a = 3, n_b = 5.
        D_o = (o_ab + o_ba)/n = 2/8 = 0.25
        D_e = (n_a*n_b + n_b*n_a)/(n(n-1)) = 30/56
        alpha = 1 - 0.25/(30/56) = 1 - 7/15 = 8/15
        """
        units = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(units), 8 / 15, places=10
        )

    def test_known_answer_with_missing_data(self):
        """Three raters, four units, two ratings missing.

        units = [[a,a,a], [a,b,b], [b,b,None], [None,b,b]]
        The first two units have m = 3, so each of their 6 ordered pairs carries
        weight 1/2; the last two have m = 2 and carry weight 1.
        Coincidence: o_aa = 3, o_ab = 1, o_ba = 1, o_bb = 5, n = 10,
        marginals n_a = 4, n_b = 6.
        D_o = 2/10 = 0.2
        D_e = (24 + 24)/(10*9) = 48/90
        alpha = 1 - 0.2/(48/90) = 1 - 0.375 = 0.625
        """
        units = [
            ["a", "a", "a"],
            ["a", "b", "b"],
            ["b", "b", None],
            [None, "b", "b"],
        ]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(units), 0.625, places=10
        )

    def test_perfect_agreement_is_one(self):
        units = [["a", "a"], ["b", "b"], ["c", "c"], ["a", "a"]]
        self.assertAlmostEqual(agreement.krippendorff_alpha(units), 1.0, places=10)

    def test_single_category_raises(self):
        """One distinct rating across all pairable units means expected
        disagreement is zero, so alpha is undefined rather than 1.0 — there is
        no chance agreement to correct for. Returning a number here let
        bootstrap_ci count information-free resamples as perfect agreement."""
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha([["a", "a"], ["a", "a"]])

    def test_systematic_disagreement_is_negative(self):
        """Two raters who always disagree do worse than chance."""
        units = [["a", "b"], ["b", "a"], ["a", "b"], ["b", "a"]]
        self.assertLess(agreement.krippendorff_alpha(units), 0.0)

    def test_units_with_one_rating_are_dropped(self):
        """A unit rated once carries no pairable information, so adding one
        must not change the result."""
        base = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        padded = base + [["a", None]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(base),
            agreement.krippendorff_alpha(padded),
            places=10,
        )

    def test_no_pairable_units_raises(self):
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha([["a", None], ["b", None]])

    def test_unknown_level_raises(self):
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha([["a", "a"], ["a", "b"]], level="ratio")


class TestKrippendorffLevels(unittest.TestCase):
    """One fixture, three known answers.

    units = [[1,1], [2,2], [1,2], [3,3]]
    Coincidence: o_11 = 2, o_22 = 2, o_12 = 1, o_21 = 1, o_33 = 2
    total n = 8, marginals n_1 = 3, n_2 = 3, n_3 = 2
    """

    UNITS = [[1, 1], [2, 2], [1, 2], [3, 3]]

    def test_nominal(self):
        """delta = 1 for every unequal pair.
        D_o = 2/8 = 0.25
        D_e = (9 + 9 + 6 + 6 + 6 + 6)/(8*7) = 42/56 = 0.75
        alpha = 1 - 0.25/0.75 = 2/3
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="nominal")
        self.assertAlmostEqual(got, 2 / 3, places=10)

    def test_interval(self):
        """delta(c,k) = (v_c - v_k)^2, so delta(1,2)=1, delta(1,3)=4, delta(2,3)=1.
        D_o = (1*1 + 1*1)/8 = 0.25
        D_e = [3*3*1*2 + 3*2*4*2 + 3*2*1*2]/(8*7) = (18 + 48 + 12)/56 = 78/56
        alpha = 1 - 0.25*56/78 = 1 - 7/39 = 32/39
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="interval")
        self.assertAlmostEqual(got, 32 / 39, places=10)

    def test_ordinal(self):
        """delta(c,k) = (sum of marginals from c to k, minus half the endpoints)^2.
        delta(1,2) = (3 + 3 - 3)^2 = 9
        delta(1,3) = (3 + 3 + 2 - 2.5)^2 = 5.5^2 = 30.25
        delta(2,3) = (3 + 2 - 2.5)^2 = 2.5^2 = 6.25
        D_o = (9 + 9)/8 = 2.25
        D_e = [3*3*9*2 + 3*2*30.25*2 + 3*2*6.25*2]/56 = (162 + 363 + 75)/56 = 600/56
        alpha = 1 - 2.25*56/600 = 1 - 0.21 = 0.79
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="ordinal")
        self.assertAlmostEqual(got, 0.79, places=10)

    def test_interval_punishes_distant_disagreement_more(self):
        """A one-step disagreement should score higher than a three-step one."""
        near = [[1, 1], [2, 2], [1, 2], [4, 4]]
        far = [[1, 1], [2, 2], [1, 4], [4, 4]]
        self.assertGreater(
            agreement.krippendorff_alpha(near, level="interval"),
            agreement.krippendorff_alpha(far, level="interval"),
        )

    def test_nominal_ignores_distance(self):
        """The same two datasets are indistinguishable to the nominal metric,
        which is exactly why an ordinal rubric must not use it."""
        near = [[1, 1], [2, 2], [1, 2], [4, 4]]
        far = [[1, 1], [2, 2], [1, 4], [4, 4]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(near, level="nominal"),
            agreement.krippendorff_alpha(far, level="nominal"),
            places=10,
        )

    def test_interval_on_non_numeric_raises(self):
        with self.assertRaises(TypeError):
            agreement.krippendorff_alpha([["a", "a"], ["a", "b"]], level="interval")


import random


class TestBootstrapCI(unittest.TestCase):
    def _units(self, n_agree, n_disagree):
        return [["a", "a"]] * n_agree + [["a", "b"]] * n_disagree

    def test_is_deterministic_for_a_fixed_seed(self):
        units = self._units(30, 10)
        first = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=200, seed=7
        )
        second = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=200, seed=7
        )
        self.assertEqual(first, second)

    def test_interval_brackets_the_point_estimate(self):
        units = self._units(30, 10)
        point = agreement.krippendorff_alpha(units)
        low, high = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=500, seed=11
        )
        self.assertLessEqual(low, point)
        self.assertLessEqual(point, high)

    def test_more_units_give_a_narrower_interval(self):
        """The whole point of reporting n alongside an interval."""
        small = agreement.bootstrap_ci(
            self._units(15, 5), agreement.krippendorff_alpha,
            n_resamples=400, seed=3,
        )
        large = agreement.bootstrap_ci(
            self._units(300, 100), agreement.krippendorff_alpha,
            n_resamples=400, seed=3,
        )
        self.assertLess(large[1] - large[0], small[1] - small[0])

    def test_too_few_units_raises(self):
        with self.assertRaises(ValueError):
            agreement.bootstrap_ci([["a", "a"]], agreement.krippendorff_alpha)

    def test_zero_resamples_raises(self):
        """n_resamples=0 previously fell through to a raw IndexError from
        indexing an empty estimates list; it must raise ValueError instead,
        naming the parameter."""
        with self.assertRaises(ValueError):
            agreement.bootstrap_ci(
                self._units(10, 10), agreement.krippendorff_alpha, n_resamples=0
            )

    def test_homogeneous_sample_does_not_pin_the_upper_bound_to_one(self):
        """Regression test for a composition bug between two correct-looking
        pieces. With 9 agreeing units and 1 disagreeing, roughly a third of
        resamples contain only one category. Those carry no information, so
        they must be skipped rather than scored 1.0 — otherwise the upper
        bound lands on exactly 1.0, which is the number a reader would use to
        argue a judge is good enough."""
        low, high = agreement.bootstrap_ci(
            self._units(9, 1),
            agreement.krippendorff_alpha,
            n_resamples=2000,
            seed=1,
        )
        self.assertLess(high, 1.0)

    def test_mostly_degenerate_resamples_raise(self):
        """A statistic that almost always fails must not silently yield an
        interval computed from the handful of resamples that happened to work."""

        def almost_always_fails(units):
            raise ValueError("degenerate")

        with self.assertRaises(ValueError):
            agreement.bootstrap_ci(
                self._units(10, 10), almost_always_fails, n_resamples=50, seed=1
            )

    def test_nominal_coverage_is_close_to_the_stated_level(self):
        """Simulation check: a nominal 95% interval should cover the truth about
        95% of the time. Loose bounds, since this is 150 simulations."""
        rng = random.Random(20260905)
        truth_units = self._units(300, 100)
        truth = agreement.krippendorff_alpha(truth_units)

        covered = 0
        trials = 150
        for _ in range(trials):
            sample = [truth_units[rng.randrange(len(truth_units))] for _ in range(60)]
            try:
                low, high = agreement.bootstrap_ci(
                    sample, agreement.krippendorff_alpha,
                    n_resamples=300, seed=rng.randrange(10 ** 6),
                )
            except ValueError:
                continue
            if low <= truth <= high:
                covered += 1
        self.assertGreater(covered / trials, 0.85)
        self.assertLessEqual(covered / trials, 1.0)

    def test_percentile_indices_pick_the_expected_estimates(self):
        """Known answer for the percentile arithmetic, including its float behaviour.

        A statistic returning a fresh consecutive integer per call makes the
        sorted estimate list 0.0 .. 99.0 for n_resamples=100.

        With confidence=0.90 the arithmetic is NOT the clean decimal 0.05:
        1.0 - 0.90 is 0.09999999999999998 in binary floating point, so
        tail = 0.04999999999999999 and tail * 100 = 4.999999999999999, which
        int() truncates to 4 rather than 5. The upper end is exact:
        1.0 - tail is 0.95, and 0.95 * 100 is 95.0, so high_index is 95.

        Truncation biases the interval outward at the low end, which is the
        conservative direction for a confidence interval.

        The pinned values (4.0 and 95.0) document current behaviour, not a
        desired invariant: they are an artefact of how int() truncation
        interacts with binary floating point at this particular confidence and
        n_resamples. A future change to round rather than truncate would
        legitimately change these numbers, and this test would need updating
        to match rather than being treated as a regression.
        """
        calls = []

        def counting_statistic(sample):
            calls.append(1)
            return float(len(calls) - 1)

        low, high = agreement.bootstrap_ci(
            self._units(1, 1),
            counting_statistic,
            n_resamples=100,
            confidence=0.90,
            seed=1,
        )
        self.assertEqual(low, 4.0)
        self.assertEqual(high, 95.0)

    def test_resamples_whole_units_not_individual_ratings(self):
        """The mechanism, pinned directly rather than through a symptom.

        Every element of every resample must be one of the original unit
        objects. A rating-level resampler would assemble new rating pairs that
        never appeared in the input, which is exactly what destroys the
        within-item dependence the docstring warns about.
        """
        units = [["a", "a"], ["b", "b"], ["a", "b"], ["b", "a"]]
        original_ids = {id(unit) for unit in units}
        seen = []

        def spy(sample):
            seen.append(sample)
            return 0.0

        agreement.bootstrap_ci(units, spy, n_resamples=20, seed=3)

        self.assertEqual(len(seen), 20)
        for sample in seen:
            self.assertEqual(len(sample), len(units))
            for unit in sample:
                self.assertIn(id(unit), original_ids)


class TestExplicitCategories(unittest.TestCase):
    """Word-labelled ordinal scales must give the same answer as their numeric
    encoding once the order is stated — and a demonstrably different one when
    it is not.

    The labels are chosen so that alphabetical order genuinely scrambles the
    scale: sorted(["bad", "fine", "excellent"]) is ["bad", "excellent", "fine"],
    which moves the disagreeing pair from adjacent to opposite ends.
    """

    NUMERIC = [[1, 1], [2, 2], [1, 2], [3, 3]]
    WORDS = [
        ["bad", "bad"],
        ["fine", "fine"],
        ["bad", "fine"],
        ["excellent", "excellent"],
    ]
    ORDER = ["bad", "fine", "excellent"]

    def test_ordinal_words_match_their_numeric_encoding(self):
        """The numeric fixture is pinned at 0.79 by TestKrippendorffLevels. The
        word fixture is the same data with labels substituted, so stating the
        order must reproduce that number exactly."""
        got = agreement.krippendorff_alpha(
            self.WORDS, level="ordinal", categories=self.ORDER
        )
        self.assertAlmostEqual(got, 0.79, places=10)

    def test_without_categories_the_scale_is_scrambled(self):
        """Known answer for the trap itself, not merely 'something different'.

        Sorted alphabetically the scale becomes bad(3) < excellent(2) < fine(3),
        so the disagreeing bad-fine pair now spans the whole range. Its ordinal
        delta rises from ((3+3)/2)^2 = 9 to (3+2+3 - (3+3)/2)^2 = 25, while the
        expected-disagreement term stays 600/56. That gives
        1 - (2*25/8) / (600/56) = 1 - 7/12 = 5/12.
        """
        got = agreement.krippendorff_alpha(self.WORDS, level="ordinal")
        self.assertAlmostEqual(got, 5 / 12, places=10)

    def test_interval_words_are_rejected(self):
        """Stating an order does not make labels numeric."""
        with self.assertRaises(TypeError):
            agreement.krippendorff_alpha(
                self.WORDS, level="interval", categories=self.ORDER
            )

    def test_rating_outside_the_stated_categories_raises(self):
        units = [["bad", "fine"], ["bad", "unheard-of"]]
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha(
                units, level="ordinal", categories=self.ORDER
            )

    def test_categories_none_preserves_existing_behaviour(self):
        """Regression guard for every caller that does not pass categories."""
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(self.NUMERIC, level="ordinal"),
            agreement.krippendorff_alpha(
                self.NUMERIC, level="ordinal", categories=None
            ),
            places=12,
        )

    def test_weighted_kappa_honours_stated_order(self):
        """Same data twice: once labelled, once as 1/2/3. Weighted kappa must
        not care which, given the order."""
        a_words = ["bad", "fine", "excellent", "bad", "excellent"]
        b_words = ["bad", "excellent", "excellent", "fine", "excellent"]
        a_nums = [1, 2, 3, 1, 3]
        b_nums = [1, 3, 3, 2, 3]
        self.assertAlmostEqual(
            agreement.weighted_kappa(a_words, b_words, categories=self.ORDER),
            agreement.weighted_kappa(a_nums, b_nums),
            places=12,
        )

    def test_weighted_kappa_rejects_unknown_rating(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa(
                ["bad", "surprise"], ["bad", "bad"], categories=self.ORDER
            )

    def test_a_repeated_category_is_rejected_by_name(self):
        """A trailing paste-typo. The index built from the list keeps only the
        last position, so ["bad", "fine", "excellent", "bad"] silently makes
        "bad" the top of the scale: the fixture pinned at 0.79 above comes back
        0.417 instead, with no warning."""
        with self.assertRaises(ValueError) as caught:
            agreement.krippendorff_alpha(
                self.WORDS, level="ordinal", categories=self.ORDER + ["bad"]
            )
        self.assertIn("bad", str(caught.exception))

    def test_weighted_kappa_rejects_a_repeated_category_too(self):
        """Both callers share one validator, so neither can drift from it."""
        with self.assertRaises(ValueError) as caught:
            agreement.weighted_kappa(
                ["bad", "fine"], ["bad", "bad"], categories=self.ORDER + ["fine"]
            )
        self.assertIn("fine", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
