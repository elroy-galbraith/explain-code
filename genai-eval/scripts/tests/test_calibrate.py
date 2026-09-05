#!/usr/bin/env python3
"""End-to-end tests for calibrate.py. Run directly: python3 test_calibrate.py"""

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

CALIBRATE = os.path.join(os.path.dirname(HERE), "calibrate.py")

_spec = importlib.util.spec_from_file_location("calibrate", CALIBRATE)
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

NUMERIC_WITH_LENGTH = (
    "item_id,human,judge,response_chars\n"
    "i1,1,1,100\ni2,2,3,300\ni3,3,3,500\n"
    "i4,1,2,200\ni5,2,2,250\ni6,3,3,520\n"
)

BLANK_JUDGE_CELL = NUMERIC_WITH_LENGTH.replace("i3,3,3,500", "i3,3,,500")
BLANK_HUMAN_CELL = NUMERIC_WITH_LENGTH.replace("i3,3,3,500", "i3,,3,500")
BLANK_LENGTH_COLUMN = (
    "item_id,human,judge,response_chars\n"
    "i1,1,1,\ni2,2,3,\ni3,3,3,\ni4,1,2,\ni5,2,2,\ni6,3,3,\n"
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


class TestBlankCells(unittest.TestCase):
    """A blank cell is missing data everywhere else in this pipeline.

    The loader deliberately produces None for one, disagreement_clusters skips
    those rows and the agreement statistic pools around them. The length probe
    used to hand them to a sort, which raised and left the user with an exit
    code, no report, and a message naming neither the column nor the flag.
    """

    def report_for(self, csv_text):
        code, out, err = run(
            [write_csv(csv_text), "--seed", "1", "--resamples", "200"]
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Judge-human agreement", out)
        return out

    def test_a_blank_judge_cell_still_produces_a_report(self):
        out = self.report_for(BLANK_JUDGE_CELL)
        self.assertIn("Length: judge rho", out)

    def test_a_blank_human_cell_still_produces_a_report(self):
        out = self.report_for(BLANK_HUMAN_CELL)
        self.assertIn("Length: judge rho", out)

    def test_a_wholly_blank_length_column_is_named_not_fatal(self):
        """An empty column coerces to numeric vacuously, so nothing upstream
        rejects it."""
        out = self.report_for(BLANK_LENGTH_COLUMN)
        self.assertIn("Not measured", out)
        self.assertIn("Length bias", out)


class TestOneSectionFailingKeepsTheRest(unittest.TestCase):
    """Report what you can, name what you cannot - including of itself."""

    def test_a_failing_probe_does_not_erase_the_other_sections(self):
        with mock.patch.object(
            calibrate.analysis, "bias_section", side_effect=RuntimeError("boom")
        ):
            code, out, err = run(
                [write_csv(TWO_RATER), "--seed", "1", "--resamples", "200"]
            )
        self.assertEqual(code, 0, err)
        self.assertIn("Judge-human agreement", out)
        self.assertIn("Human-human agreement", out)
        self.assertIn("Disagreement clusters", out)
        self.assertIn("judge bias section could not be computed", out)
        self.assertIn("boom", out)

    def test_a_failing_cluster_count_is_not_reported_as_agreement(self):
        """An empty cluster list means the judge and the human never
        disagreed. A section that could not run must not borrow that
        sentence."""
        with mock.patch.object(
            calibrate.analysis,
            "disagreement_clusters",
            side_effect=RuntimeError("boom"),
        ):
            code, out, err = run(
                [write_csv(TWO_RATER), "--seed", "1", "--resamples", "200"]
            )
        self.assertEqual(code, 0, err)
        self.assertNotIn("never disagreed", out)
        self.assertIn("disagreement clusters section could not be computed", out)

    def test_a_user_error_still_exits_one_before_any_section_runs(self):
        code, out, err = run(["/nonexistent/labels.csv"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("calibrate:", err)


class TestNumericCategories(unittest.TestCase):
    def test_numbers_are_accepted_for_a_numeric_rubric(self):
        """The most common scale shape there is. The loader coerces the column
        to floats, so a scale stated as text covers none of its ratings."""
        code, out, err = run(
            [
                write_csv(NUMERIC_WITH_LENGTH),
                "--level", "ordinal",
                "--categories", "1,2,3",
                "--seed", "1",
                "--resamples", "200",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Judge-human agreement", out)

    def test_a_non_numeric_entry_against_a_numeric_column_is_named(self):
        code, _, err = run(
            [
                write_csv(NUMERIC_WITH_LENGTH),
                "--level", "ordinal",
                "--categories", "1,2,three",
                "--seed", "1",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("three", err)


class TestConsoleEncoding(unittest.TestCase):
    def test_a_legacy_codepage_degrades_a_character_not_the_report(self):
        """The report carries an em dash, which cp437 cannot encode. Printing
        it used to raise UnicodeEncodeError and lose the whole report; the
        error handler alone turns that into a "?"."""
        path = write_csv(ONE_RATER)
        environment = dict(os.environ, PYTHONIOENCODING="cp437")
        finished = subprocess.run(
            [sys.executable, CALIBRATE, path, "--seed", "1", "--resamples", "200"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr.decode("utf-8", "replace"))
        self.assertIn(
            "Judge-human agreement", finished.stdout.decode("cp437", "replace")
        )


class TestMid(unittest.TestCase):
    def test_mid_produces_a_sufficiency_statement(self):
        code, out, _ = run(
            [write_csv(ONE_RATER), "--mid", "0.05", "--seed", "1", "--resamples", "200"]
        )
        self.assertEqual(code, 0)
        self.assertIn("you would need", out)


if __name__ == "__main__":
    unittest.main()
