#!/usr/bin/env python3
"""Tests for calibration.loader. Run directly: python3 test_loader.py"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import loader

MINIMAL = "judge,human\n5,5\n4,3\n2,2\n"

FULL = (
    "item_id,human_a,human_b,judge,response_chars,generator\n"
    "i1,5,5,5,120,gpt-x\n"
    "i2,4,4,5,340,other\n"
    "i3,3,3,3,95,gpt-x\n"
    "i4,5,4,5,410,other\n"
)


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


class TestDetectColumns(unittest.TestCase):
    def test_detects_by_name_fragment(self):
        found = loader.detect_columns(
            ["item_id", "human_a", "human_b", "judge", "response_chars", "generator"]
        )
        self.assertEqual(found["judge"], "judge")
        self.assertEqual(found["humans"], ["human_a", "human_b"])
        self.assertEqual(found["item_id"], "item_id")
        self.assertEqual(found["length"], "response_chars")
        self.assertEqual(found["generator"], "generator")

    def test_recognises_common_synonyms(self):
        found = loader.detect_columns(["id", "gold_label", "llm_score", "n_tokens"])
        self.assertEqual(found["judge"], "llm_score")
        self.assertEqual(found["humans"], ["gold_label"])
        self.assertEqual(found["item_id"], "id")
        self.assertEqual(found["length"], "n_tokens")

    def test_reports_absence_rather_than_guessing(self):
        found = loader.detect_columns(["alpha", "beta"])
        self.assertIsNone(found["judge"])
        self.assertEqual(found["humans"], [])

    def test_a_column_is_claimed_once(self):
        """'human_judge' must not count as both. Judge wins, because the judge
        column is the one the analysis cannot proceed without."""
        found = loader.detect_columns(["human_judge", "gold"])
        self.assertEqual(found["judge"], "human_judge")
        self.assertEqual(found["humans"], ["gold"])


class TestLoadMinimal(unittest.TestCase):
    def test_two_columns_are_enough(self):
        data = loader.load_labels(write_csv(MINIMAL))
        self.assertEqual(data.judge_column, "judge")
        self.assertEqual(data.judge_scores, [5.0, 4.0, 2.0])
        self.assertEqual(list(data.human_columns), ["human"])
        self.assertEqual(data.human_columns["human"], [5.0, 3.0, 2.0])
        self.assertEqual(data.n, 3)
        self.assertIsNone(data.item_ids)

    def test_single_rater_is_noted_not_hidden(self):
        data = loader.load_labels(write_csv(MINIMAL))
        self.assertTrue(
            any("one human rater" in note for note in data.notes),
            data.notes,
        )

    def test_absent_optional_columns_are_each_noted(self):
        data = loader.load_labels(write_csv(MINIMAL))
        joined = " ".join(data.notes)
        self.assertIn("length", joined)
        self.assertIn("item id", joined)


class TestLoadFull(unittest.TestCase):
    def setUp(self):
        self.data = loader.load_labels(write_csv(FULL))

    def test_reads_every_optional_column(self):
        self.assertEqual(self.data.item_ids, ["i1", "i2", "i3", "i4"])
        self.assertEqual(list(self.data.human_columns), ["human_a", "human_b"])
        self.assertEqual(self.data.lengths, [120.0, 340.0, 95.0, 410.0])
        self.assertEqual(self.data.generators, ["gpt-x", "other", "gpt-x", "other"])

    def test_two_raters_means_no_ceiling_note(self):
        self.assertFalse(
            any("one human rater" in note for note in self.data.notes),
            self.data.notes,
        )

    def test_numeric_columns_are_marked(self):
        self.assertTrue(self.data.numeric["judge"])
        self.assertTrue(self.data.numeric["human_a"])

    def test_detected_columns_are_named_so_a_wrong_guess_is_visible(self):
        """The heuristics are guesses about someone else's file. A guess that
        fills a role wrongly is otherwise invisible — notes only ever reported
        absences, never mis-matches, so a mis-detected length column would feed
        the bias probe with no signal that anything was assumed."""
        matched = [n for n in self.data.notes if "matched by name" in n]
        self.assertEqual(len(matched), 1, self.data.notes)
        for column in ("item_id", "judge", "response_chars", "generator"):
            self.assertIn(column, matched[0])


class TestCoercionAndMissing(unittest.TestCase):
    def test_word_labels_stay_strings(self):
        data = loader.load_labels(write_csv("judge,human\ngood,good\nfair,poor\n"))
        self.assertEqual(data.judge_scores, ["good", "fair"])
        self.assertFalse(data.numeric["judge"])

    def test_a_single_non_numeric_value_makes_the_whole_column_text(self):
        """Mixing floats and strings in one column would break every statistic
        downstream, so coercion is all-or-nothing per column."""
        data = loader.load_labels(write_csv("judge,human\n5,5\nn/a,4\n"))
        self.assertEqual(data.judge_scores, ["5", "n/a"])
        self.assertFalse(data.numeric["judge"])

    def test_blank_cells_become_none(self):
        data = loader.load_labels(
            write_csv("judge,human_a,human_b\n5,5,\n4,,4\n")
        )
        self.assertEqual(data.human_columns["human_a"], [5.0, None])
        self.assertEqual(data.human_columns["human_b"], [None, 4.0])

    def test_blanks_do_not_stop_numeric_coercion(self):
        data = loader.load_labels(write_csv("judge,human\n5,5\n,4\n"))
        self.assertTrue(data.numeric["judge"])


class TestOverridesAndErrors(unittest.TestCase):
    def test_explicit_columns_override_detection(self):
        data = loader.load_labels(
            write_csv("alpha,beta\n5,4\n3,3\n"), judge="alpha", humans=["beta"]
        )
        self.assertEqual(data.judge_column, "alpha")
        self.assertEqual(list(data.human_columns), ["beta"])

    def test_named_column_that_does_not_exist_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv(MINIMAL), judge="nope")

    def test_undetectable_judge_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("alpha,beta\n1,2\n"))

    def test_undetectable_human_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,notes\n5,hello\n"))

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,human\n"))

    def test_ragged_rows_raise(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,human\n5,5\n4\n"))

    def test_explicitly_named_columns_are_not_reported_as_guesses(self):
        data = loader.load_labels(
            write_csv("alpha,beta\n5,4\n3,3\n"), judge="alpha", humans=["beta"]
        )
        self.assertFalse(
            [n for n in data.notes if "matched by name" in n], data.notes
        )

    def test_long_rows_raise(self):
        """csv.DictReader stows extra fields under a None key, which is the
        other ragged shape — the short-row case leaves None values instead."""
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,human\n5,5\n4,5,6\n"))


if __name__ == "__main__":
    unittest.main()
