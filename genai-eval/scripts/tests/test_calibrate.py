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


def write_utf8_csv(text):
    """Like write_csv, but explicit about the encoding.

    write_csv relies on the platform's default text encoding, which is fine
    for the ASCII fixtures every other test uses. loader.py reads every CSV as
    utf-8, so a fixture that deliberately carries a non-ASCII character (an
    item id with an em dash) has to be written as utf-8 too, or it never
    reaches the loader intact regardless of what calibrate.py does with it.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline="", encoding="utf-8"
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


class TestTheLevelReachesTheReport(unittest.TestCase):
    """Whether the level was chosen or assumed has to survive the CLI.

    The argparse option defaults to None so the report can tell the two
    apart. The effective default must not move with it: a run with no flag
    still has to compute a nominal alpha, exactly as before.
    """

    ORDERED = "judge,human\n1,1\n2,3\n3,3\n4,4\n1,2\n4,3\n"

    def test_no_flag_still_computes_nominal_and_says_it_assumed_it(self):
        path = write_csv(self.ORDERED)
        code, out, _ = run([path, "--seed", "1", "--resamples", "200"])
        self.assertEqual(code, 0)
        self.assertIn("agreement at the nominal measurement level", out)
        self.assertIn("No measurement level was stated", out)

        stated = run([path, "--level", "nominal", "--seed", "1",
                      "--resamples", "200"])[1]
        self.assertNotIn("No measurement level was stated", stated)
        self.assertEqual(
            [line for line in out.splitlines()
             if line.startswith("Judge-human agreement")],
            [line for line in stated.splitlines()
             if line.startswith("Judge-human agreement")],
        )

    def test_a_stated_ordinal_level_is_named_and_uncaveated(self):
        code, out, _ = run(
            [write_csv(self.ORDERED), "--level", "ordinal", "--seed", "1",
             "--resamples", "200"]
        )
        self.assertEqual(code, 0)
        self.assertIn("agreement at the ordinal measurement level", out)
        self.assertNotIn("No measurement level was stated", out)

    def test_ordinal_and_nominal_do_not_produce_the_same_figure(self):
        """The caveat would be decorative if the level never moved anything.
        This fixture is ordered, so the two levels have to disagree."""
        path = write_csv(self.ORDERED)
        args = ["--seed", "1", "--resamples", "200"]
        nominal = run([path] + args)[1]
        ordinal = run([path, "--level", "ordinal"] + args)[1]

        def alpha(text):
            for line in text.splitlines():
                if line.startswith("Judge-human agreement"):
                    return line.split(":", 1)[1].split(",")[0].strip()
            raise AssertionError(text)

        self.assertNotEqual(alpha(nominal), alpha(ordinal))


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
    def test_the_rendered_report_contains_no_non_ascii_character(self):
        """The end-to-end counterpart to test_ascii_output.py, which can only
        see string literals in the source. This one renders a real report and
        checks the bytes, so it catches a character that arrives through a
        computed value: a rater name, an item id, a formatted number.

        It runs on a UTF-8 stream deliberately. The CLIs set
        errors="backslashreplace", so on a legacy codepage a stray character
        would print as an escape and the report would survive; that is the
        right behaviour there, and it is why checking survival proves nothing.
        Only a stream that can encode everything lets the character reach this
        assertion intact.
        """
        path = write_csv(ONE_RATER)
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        finished = subprocess.run(
            [sys.executable, CALIBRATE, path, "--seed", "1", "--resamples", "200"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(finished.returncode, 0,
                         finished.stderr.decode("utf-8", "replace"))
        offenders = sorted({byte for byte in finished.stdout if byte > 127})
        self.assertEqual(
            offenders, [],
            "the rendered report carried non-ASCII bytes: %r" % (offenders,))


class TestUnencodableConsole(unittest.TestCase):
    """An item id belongs to whoever exported the CSV, not to us, so it can
    contain anything. This must not crash on a console that cannot encode it."""

    EM_DASH_LABELS = (
        "item_id,human_a,human_b,judge\n"
        "i1,1,1,1\ni2,1,1,1\ni3,2,2,2\ni4,2,2,2\n"
        "grounding—v2,1,2,2\ni6,2,2,2\ni7,1,1,1\ni8,2,1,2\n"
    )

    def test_a_console_that_cannot_encode_an_item_id_does_not_crash_the_run(self):
        path = write_utf8_csv(self.EM_DASH_LABELS)
        environment = dict(os.environ, PYTHONIOENCODING="cp850")
        result = subprocess.run(
            [sys.executable, CALIBRATE, path, "--seed", "1", "--resamples", "200"],
            capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("UnicodeEncodeError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("Judge-human agreement", result.stdout)


class TestMid(unittest.TestCase):
    def test_mid_produces_a_sufficiency_statement(self):
        code, out, _ = run(
            [write_csv(ONE_RATER), "--mid", "0.05", "--seed", "1", "--resamples", "200"]
        )
        self.assertEqual(code, 0)
        self.assertIn("you would need", out)


if __name__ == "__main__":
    unittest.main()
