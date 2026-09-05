#!/usr/bin/env python3
"""Known-answer tests for evalstats.power. Run directly: python3 test_power.py"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import power


class TestRequiredN(unittest.TestCase):
    def test_known_answer(self):
        """Detecting 0.80 vs 0.85 at alpha=0.05, power=0.80.

        z(0.975) = 1.9599639845, z(0.80) = 0.8416212336
        (z_a + z_b)^2 = 2.8015852181^2 = 7.8488797
        p1*q1 + p2*q2 = 0.16 + 0.1275 = 0.2875
        (p1 - p2)^2 = 0.0025
        n = 7.8488797 * 0.2875 / 0.0025 = 902.62 per group
        """
        got = power.n_required_two_proportion(0.80, 0.85)
        self.assertAlmostEqual(got, 902.62, places=2)

    def test_bigger_effects_need_fewer_items(self):
        small = power.n_required_two_proportion(0.80, 0.85)
        large = power.n_required_two_proportion(0.80, 0.95)
        self.assertLess(large, small)

    def test_more_power_needs_more_items(self):
        at_80 = power.n_required_two_proportion(0.80, 0.85, power=0.80)
        at_95 = power.n_required_two_proportion(0.80, 0.85, power=0.95)
        self.assertGreater(at_95, at_80)

    def test_symmetric_in_its_arguments(self):
        self.assertAlmostEqual(
            power.n_required_two_proportion(0.80, 0.85),
            power.n_required_two_proportion(0.85, 0.80),
            places=9,
        )

    def test_no_effect_raises(self):
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.80, 0.80)

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.0, 0.85)
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.80, 1.0)


class TestMDE(unittest.TestCase):
    def test_round_trips_against_required_n(self):
        """With the n that detects 0.80 vs 0.85, the MDE should land back on
        about 0.85. This checks the two functions against each other rather
        than against a remembered constant."""
        n = power.n_required_two_proportion(0.80, 0.85)
        got = power.mde_two_proportion(math.ceil(n), 0.80)
        self.assertAlmostEqual(got, 0.85, places=3)

    def test_more_items_detect_smaller_effects(self):
        few = power.mde_two_proportion(200, 0.80)
        many = power.mde_two_proportion(2000, 0.80)
        self.assertLess(many - 0.80, few - 0.80)

    def test_downward_direction(self):
        got = power.mde_two_proportion(903, 0.85, direction="down")
        self.assertAlmostEqual(got, 0.80, places=2)

    def test_tiny_sample_returns_none(self):
        """No proportion below 1.0 is detectable against 0.80 with 3 items."""
        self.assertIsNone(power.mde_two_proportion(3, 0.80))

    def test_bad_direction_raises(self):
        with self.assertRaises(ValueError):
            power.mde_two_proportion(903, 0.80, direction="sideways")


class TestMcNemar(unittest.TestCase):
    def test_known_answer(self):
        """b=3, c=12, so n=15 discordant pairs.
        One tail = [C(15,0)+C(15,1)+C(15,2)+C(15,3)] / 2^15
                 = (1 + 15 + 105 + 455) / 32768 = 576/32768
        Two-sided p = 2 * 576/32768 = 9/256 = 0.03515625
        """
        self.assertAlmostEqual(power.mcnemar_exact(3, 12), 9 / 256, places=12)

    def test_symmetric_in_its_arguments(self):
        self.assertAlmostEqual(
            power.mcnemar_exact(3, 12), power.mcnemar_exact(12, 3), places=12
        )

    def test_balanced_discordance_is_not_significant(self):
        """b == c is the null exactly; the two-sided p caps at 1.0."""
        self.assertEqual(power.mcnemar_exact(5, 5), 1.0)

    def test_no_discordant_pairs_returns_one(self):
        """Two systems that never differ give no evidence of a difference."""
        self.assertEqual(power.mcnemar_exact(0, 0), 1.0)

    def test_lopsided_discordance_is_significant(self):
        self.assertLess(power.mcnemar_exact(0, 12), 0.001)

    def test_negative_counts_raise(self):
        with self.assertRaises(ValueError):
            power.mcnemar_exact(-1, 5)


class TestDiscordantCounts(unittest.TestCase):
    def test_counts_each_direction(self):
        a = [1, 1, 0, 0, 1]
        b = [1, 0, 1, 0, 0]
        # a passed / b failed at indices 1 and 4 -> 2
        # b passed / a failed at index 2 -> 1
        self.assertEqual(power.discordant_counts(a, b), (2, 1))

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            power.discordant_counts([1, 0], [1])

    def test_feeds_mcnemar(self):
        a = [1] * 12 + [0] * 3 + [1] * 20
        b = [0] * 12 + [1] * 3 + [1] * 20
        counts = power.discordant_counts(a, b)
        self.assertEqual(counts, (12, 3))
        self.assertAlmostEqual(power.mcnemar_exact(*counts), 9 / 256, places=12)


class TestPairedBootstrapDiff(unittest.TestCase):
    def test_is_deterministic_for_a_fixed_seed(self):
        a = [5, 4, 3, 5, 4, 3, 5, 4]
        b = [2, 1, 2, 1, 2, 1, 2, 1]
        first = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        second = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        self.assertEqual(first, second)

    def test_mean_diff_is_the_observed_difference(self):
        a = [5, 4, 3, 5, 4, 3]     # mean 4.0
        b = [2, 1, 2, 1, 2, 1]     # mean 1.5
        result = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        self.assertAlmostEqual(result["mean_diff"], 2.5, places=10)
        self.assertEqual(result["n"], 6)

    def test_interval_brackets_the_mean_difference(self):
        a = [5, 4, 3, 5, 4, 3, 2, 4]
        b = [2, 1, 2, 1, 2, 1, 3, 2]
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=9)
        low, high = result["ci"]
        self.assertLessEqual(low, result["mean_diff"])
        self.assertLessEqual(result["mean_diff"], high)

    def test_clear_difference_excludes_zero(self):
        a = [5] * 20 + [4] * 20
        b = [1] * 20 + [2] * 20
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=13)
        self.assertGreater(result["ci"][0], 0.0)

    def test_no_difference_includes_zero(self):
        a = [3, 4, 2, 5, 3, 4, 2, 5, 3, 4]
        b = [4, 3, 5, 2, 4, 3, 5, 2, 4, 3]
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=13)
        low, high = result["ci"]
        self.assertLessEqual(low, 0.0)
        self.assertGreaterEqual(high, 0.0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            power.paired_bootstrap_diff([1, 2, 3], [1, 2])

    def test_single_item_raises(self):
        with self.assertRaises(ValueError):
            power.paired_bootstrap_diff([1], [2])

    def test_constant_difference_collapses_the_interval(self):
        """Known answer for the interval bounds, not just the point estimate.

        Every per-item difference here is exactly 3, so every resample's mean is
        also 3 and the sorted estimate list is entirely 3.0. Both percentile
        indices therefore select 3.0 and the interval collapses to (3.0, 3.0) —
        a hand-derivable known answer for the bounds themselves, which the
        bracketing and sign properties never pin.
        """
        a = [5, 4, 6, 5, 4, 6]
        b = [2, 1, 3, 2, 1, 3]
        result = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=17)
        low, high = result["ci"]
        self.assertAlmostEqual(result["mean_diff"], 3.0, places=12)
        self.assertAlmostEqual(low, 3.0, places=12)
        self.assertAlmostEqual(high, 3.0, places=12)


if __name__ == "__main__":
    unittest.main()
