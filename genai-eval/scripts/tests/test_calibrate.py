#!/usr/bin/env python3
"""End-to-end tests for calibrate.py. Run directly: python3 test_calibrate.py"""

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

_spec = importlib.util.spec_from_file_location(
    "calibrate", os.path.join(os.path.dirname(HERE), "calibrate.py")
)
calibrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calibrate)

TWO_RATER = (
    "item_id,human_a,human_b,judge\n"
    "i1,1,1,1\ni2,1,1,1\ni3,2,2,2\ni4,2,2,2\n"
    "i5,1,2,1\ni6,2,2,2\ni7,1,1,1\ni8,2,1,2\n"
)

ONE_RATER = "judge,human\n1,1\n1,1\n2,2\n2,1\n1,2\n2,2\n"

WORDS = (
    "judge,human\nlow,low\nmedium,medium\nlow,medium\nhigh,high\n"
    "high,high\nmedium,low\n"
)


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = calibrate.main(args)
    return code, out.getvalue(), err.getvalue()


class TestHappyPath(unittest.TestCase):
    def test_two_rater_file_reports_a_ceiling(self):
        code, out, _ = run([write_csv(TWO_RATER), "--seed", "1", "--resamples", "200"])
        self.assertEqual(code, 0)
        self.assertIn("Human-human agreement", out)
        self.assertIn("95% CI", out)

    def test_one_rater_file_says_so_and_still_succeeds(self):
        code, out, _ = run([write_csv(ONE_RATER), "--seed", "1", "--resamples", "200"])
        self.assertEqual(code, 0)
        self.assertIn("no human-human ceiling", out.lower())
        self.assertIn("Gate 6", out)

    def test_writes_to_a_file_when_asked(self):
        target = os.path.join(tempfile.mkdtemp(), "report.md")
        code, out, _ = run(
            [write_csv(ONE_RATER), "--seed", "1", "--resamples", "200", "-o", target]
        )
        self.assertEqual(code, 0)
        with open(target, encoding="utf-8") as handle:
            self.assertIn("Judge calibration report", handle.read())
        self.assertNotIn("## Agreement", out)


class TestOrdinalWords(unittest.TestCase):
    def test_categories_are_passed_through(self):
        code, out, _ = run(
            [
                write_csv(WORDS),
                "--level", "ordinal",
                "--categories", "low,medium,high",
                "--seed", "1",
                "--resamples", "200",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Judge-human agreement", out)

    def test_ordinal_words_without_categories_fails_loudly(self):
        """Rather than silently sorting them alphabetically and reporting a
        confident wrong number."""
        code, _, err = run(
            [write_csv(WORDS), "--level", "ordinal", "--seed", "1"]
        )
        self.assertEqual(code, 1)
        self.assertIn("--categories", err)


class TestErrors(unittest.TestCase):
    def test_missing_file_exits_one(self):
        code, _, err = run(["/nonexistent/labels.csv"])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())

    def test_undetectable_judge_column_exits_one(self):
        code, _, err = run([write_csv("alpha,beta\n1,2\n")])
        self.assertEqual(code, 1)
        self.assertIn("judge", err.lower())

    def test_bad_categories_value_exits_one(self):
        code, _, err = run(
            [
                write_csv(WORDS),
                "--level", "ordinal",
                "--categories", "low,medium",
                "--seed", "1",
            ]
        )
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())

    def test_repeated_category_exits_one_and_names_the_repeat(self):
        """low,medium,high,low returns 0.417 where the correct order returns
        0.790, because the index keeps a duplicate's last position. A trailing
        paste-typo must not silently invert the scale."""
        code, _, err = run(
            [
                write_csv(WORDS),
                "--level", "ordinal",
                "--categories", "low,medium,high,low",
                "--seed", "1",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("low", err)

    def test_complete_categories_are_accepted(self):
        """The guard must reject only genuinely uncovered ratings — naming the
        full scale has to still work, or the check would block correct use."""
        code, out, err = run(
            [
                write_csv(WORDS),
                "--level", "ordinal",
                "--categories", "low,medium,high",
                "--seed", "1",
                "--resamples", "200",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Judge-human agreement", out)


class TestMid(unittest.TestCase):
    def test_mid_produces_a_sufficiency_statement(self):
        code, out, _ = run(
            [write_csv(ONE_RATER), "--mid", "0.05", "--seed", "1", "--resamples", "200"]
        )
        self.assertEqual(code, 0)
        self.assertIn("you would need", out)


if __name__ == "__main__":
    unittest.main()
