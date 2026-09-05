#!/usr/bin/env python3
"""Known-answer tests for evalstats.items. Run directly: python3 test_items.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import items

# A perfectly Guttman-scaled response matrix: 5 examinees, 4 items.
#         I1 I2 I3 I4   total
#   E1     1  1  1  1     4
#   E2     1  1  1  0     3
#   E3     1  1  0  0     2
#   E4     1  0  0  0     1
#   E5     0  0  0  0     0
GUTTMAN = [
    [1, 1, 1, 1],
    [1, 1, 1, 0],
    [1, 1, 0, 0],
    [1, 0, 0, 0],
    [0, 0, 0, 0],
]


def _column(matrix, j):
    return [row[j] for row in matrix]


def _totals(matrix):
    return [sum(row) for row in matrix]


class TestDifficulty(unittest.TestCase):
    def test_known_answers(self):
        """Column pass rates are 4/5, 3/5, 2/5, 1/5."""
        expected = [0.8, 0.6, 0.4, 0.2]
        for j, want in enumerate(expected):
            self.assertAlmostEqual(
                items.item_difficulty(_column(GUTTMAN, j)), want, places=10
            )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            items.item_difficulty([])


class TestPointBiserial(unittest.TestCase):
    def test_known_answer_item_two(self):
        """Item 2 (index 1). Totals are [4,3,2,1,0], mean 2, population sd sqrt(2).
        Passers scored [4,3,2] -> mean 3; failers scored [1,0] -> mean 0.5.
        p = 0.6, q = 0.4.
        r_pb = (3 - 0.5)/sqrt(2) * sqrt(0.24) = 2.5 * sqrt(0.12) = sqrt(3)/2
        """
        import math

        got = items.point_biserial(_column(GUTTMAN, 1), _totals(GUTTMAN))
        self.assertAlmostEqual(got, math.sqrt(3) / 2, places=10)

    def test_known_answer_item_one(self):
        """Item 1 (index 0). Passers [4,3,2,1] -> mean 2.5; failers [0] -> mean 0.
        p = 0.8, q = 0.2.
        r_pb = 2.5/sqrt(2) * sqrt(0.16) = sqrt(2)/2
        """
        import math

        got = items.point_biserial(_column(GUTTMAN, 0), _totals(GUTTMAN))
        self.assertAlmostEqual(got, math.sqrt(2) / 2, places=10)

    def test_mis_keyed_item_is_negative(self):
        """An item the strongest candidates fail must produce a negative value.
        This is the case item analysis exists to find."""
        reversed_column = [0, 0, 0, 1, 1]
        got = items.point_biserial(reversed_column, _totals(GUTTMAN))
        self.assertLess(got, 0.0)

    def test_all_pass_returns_none(self):
        self.assertIsNone(items.point_biserial([1, 1, 1, 1, 1], _totals(GUTTMAN)))

    def test_zero_total_variance_returns_none(self):
        self.assertIsNone(items.point_biserial([1, 0, 1, 0, 1], [2, 2, 2, 2, 2]))


class TestFlagItems(unittest.TestCase):
    def test_guttman_items_are_all_clean(self):
        report = items.flag_items(GUTTMAN)
        self.assertEqual(len(report), 4)
        for row in report:
            self.assertEqual(row["flags"], [])

    def test_flags_a_mis_keyed_item(self):
        matrix = [row[:] for row in GUTTMAN]
        for i, row in enumerate(matrix):
            row.append(1 if i >= 3 else 0)  # strongest candidates fail it
        report = items.flag_items(matrix)
        self.assertIn("mis-keyed", report[4]["flags"])

    def test_flags_ceiling_and_floor_items(self):
        matrix = [row + [1, 0] for row in GUTTMAN]
        report = items.flag_items(matrix)
        self.assertIn("ceiling", report[4]["flags"])
        self.assertIn("floor", report[5]["flags"])

    def test_ragged_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.flag_items([[1, 0], [1]])


class TestKR20(unittest.TestCase):
    def test_known_answer(self):
        """4 items, 5 examinees, Guttman matrix.

        Item p values: 0.8, 0.6, 0.4, 0.2
        sum of p*q = 0.16 + 0.24 + 0.24 + 0.16 = 0.80
        totals [4,3,2,1,0], mean 2, population variance 10/5 = 2.0
        KR-20 = (4/3) * (1 - 0.80/2.0) = (4/3) * 0.6 = 0.8
        """
        self.assertAlmostEqual(items.kr20(GUTTMAN), 0.8, places=10)

    def test_zero_variance_returns_none(self):
        self.assertIsNone(items.kr20([[1, 1], [1, 1], [1, 1]]))

    def test_single_item_raises(self):
        with self.assertRaises(ValueError):
            items.kr20([[1], [0], [1]])

    def test_ragged_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.kr20([[1, 0], [1]])


class TestEigenvalues(unittest.TestCase):
    def test_two_by_two_known_answer(self):
        """A 2x2 correlation matrix [[1, r], [r, 1]] has eigenvalues 1+r and 1-r.
        With r = 0.6 that is 1.6 and 0.4."""
        got = items.eigenvalues_symmetric([[1.0, 0.6], [0.6, 1.0]])
        self.assertAlmostEqual(got[0], 1.6, places=9)
        self.assertAlmostEqual(got[1], 0.4, places=9)

    def test_equicorrelated_three_by_three_known_answer(self):
        """An equicorrelated 3x3 with r = 0.5 has eigenvalues 1+2r = 2.0 and
        1-r = 0.5 twice."""
        m = [[1.0, 0.5, 0.5], [0.5, 1.0, 0.5], [0.5, 0.5, 1.0]]
        got = items.eigenvalues_symmetric(m)
        self.assertAlmostEqual(got[0], 2.0, places=9)
        self.assertAlmostEqual(got[1], 0.5, places=9)
        self.assertAlmostEqual(got[2], 0.5, places=9)

    def test_identity_has_unit_eigenvalues(self):
        got = items.eigenvalues_symmetric([[1.0, 0.0], [0.0, 1.0]])
        self.assertAlmostEqual(got[0], 1.0, places=9)
        self.assertAlmostEqual(got[1], 1.0, places=9)

    def test_trace_is_preserved(self):
        """Eigenvalues of a symmetric matrix sum to its trace."""
        m = [[1.0, 0.3, -0.2], [0.3, 1.0, 0.4], [-0.2, 0.4, 1.0]]
        self.assertAlmostEqual(sum(items.eigenvalues_symmetric(m)), 3.0, places=9)

    def test_asymmetric_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.eigenvalues_symmetric([[1.0, 0.5], [0.2, 1.0]])

    def test_non_square_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.eigenvalues_symmetric([[1.0, 0.5]])


class TestCorrelationMatrix(unittest.TestCase):
    def test_known_answer_two_items(self):
        """The first two Guttman columns: [1,1,1,1,0] and [1,1,1,0,0].

        p0 = 0.8, p1 = 0.6, and both items pass together on 3 of 5 respondents.
        cov  = 0.6 - 0.8 * 0.6 = 0.12
        sd0  = sqrt(0.8 * 0.2) = 0.4
        sd1  = sqrt(0.6 * 0.4) = sqrt(0.24)
        r    = 0.12 / (0.4 * sqrt(0.24)) = 3 / (2 * sqrt(6)) = sqrt(6) / 4
        """
        import math

        matrix = [[row[0], row[1]] for row in GUTTMAN]
        result = items.correlation_matrix(matrix)
        expected = math.sqrt(6) / 4

        self.assertAlmostEqual(result[0][0], 1.0, places=12)
        self.assertAlmostEqual(result[1][1], 1.0, places=12)
        self.assertAlmostEqual(result[0][1], expected, places=12)
        self.assertAlmostEqual(result[1][0], expected, places=12)

    def test_zero_variance_item_correlates_with_nothing(self):
        """An item everyone passes has no variance, so it correlates with
        nothing. Its row and column are zero apart from the 1.0 on the
        diagonal, which keeps the matrix square and symmetric for the
        eigenvalue solver instead of dividing by zero."""
        matrix = [[row[0], row[1], 1] for row in GUTTMAN]
        result = items.correlation_matrix(matrix)

        self.assertEqual(result[2], [0.0, 0.0, 1.0])
        self.assertEqual([row[2] for row in result], [0.0, 0.0, 1.0])

    def test_result_is_square_and_symmetric(self):
        """The eigenvalue solver rejects a non-symmetric matrix, so this is a
        precondition for dimensionality() working at all."""
        result = items.correlation_matrix(GUTTMAN)

        self.assertEqual(len(result), 4)
        for row in result:
            self.assertEqual(len(row), 4)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(result[i][j], result[j][i], places=12)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            items.correlation_matrix([])

    def test_ragged_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.correlation_matrix([[1, 0], [1]])


class TestDimensionality(unittest.TestCase):
    def test_returns_one_eigenvalue_per_item(self):
        result = items.dimensionality(GUTTMAN)
        self.assertEqual(len(result["eigenvalues"]), 4)

    def test_eigenvalues_sum_to_item_count(self):
        """A correlation matrix has 1.0 down its diagonal, so its trace equals
        its size, and eigenvalues sum to the trace. Four items always total 4."""
        result = items.dimensionality(GUTTMAN)
        self.assertAlmostEqual(sum(result["eigenvalues"]), 4.0, places=9)

    def test_eigenvalues_are_descending(self):
        values = items.dimensionality(GUTTMAN)["eigenvalues"]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_summary_fields_agree_with_the_eigenvalues(self):
        result = items.dimensionality(GUTTMAN)
        values = result["eigenvalues"]
        self.assertAlmostEqual(
            result["first_ratio"], values[0] / sum(values), places=12
        )
        self.assertEqual(
            result["n_above_one"], sum(1 for v in values if v > 1.0)
        )

    def test_duplicated_item_produces_a_zero_eigenvalue(self):
        """Two identical items carry one item's worth of information, so the
        correlation matrix is rank-deficient and its smallest eigenvalue is 0.
        This is the signature of a redundant item in the pool."""
        duplicated = [row + [row[0]] for row in GUTTMAN]
        values = items.dimensionality(duplicated)["eigenvalues"]
        self.assertEqual(len(values), 5)
        self.assertAlmostEqual(values[-1], 0.0, places=8)


if __name__ == "__main__":
    unittest.main()
