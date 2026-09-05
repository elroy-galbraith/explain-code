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


if __name__ == "__main__":
    unittest.main()
