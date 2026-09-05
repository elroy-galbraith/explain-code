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


if __name__ == "__main__":
    unittest.main()
