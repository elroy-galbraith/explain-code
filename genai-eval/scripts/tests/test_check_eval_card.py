#!/usr/bin/env python3
"""End-to-end tests for check_eval_card.py. Run: python3 test_check_eval_card.py"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

_spec = importlib.util.spec_from_file_location(
    "check_eval_card", os.path.join(os.path.dirname(HERE), "check_eval_card.py")
)
check_eval_card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_eval_card)

from card_fixture import write_card


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = check_eval_card.main(args)
    return code, out.getvalue(), err.getvalue()


class TestValidCard(unittest.TestCase):
    def test_a_valid_card_exits_zero(self):
        code, out, err = run([write_card(tempfile.mkdtemp())])
        self.assertEqual(code, 0, err)
        self.assertIn("no findings", out.lower())

    def test_a_clean_report_still_names_the_gates_it_did_not_check(self):
        """The clean output is the one most likely to be pasted into a review
        as evidence that an eval is sound, so it is the one that must not
        omit the sentence saying five gates were never examined."""
        _, clean, _ = run([write_card(tempfile.mkdtemp())])
        caveat = "Gates 6, 7, 8, 10 and 11 need a qualification block"
        self.assertIn(caveat, clean)

        with_findings = run([write_card(
            tempfile.mkdtemp(),
            mutate=lambda c: c["decision"].pop("owner"))])[1]
        self.assertIn(caveat, with_findings)

    def test_the_caveat_is_absent_from_machine_readable_output(self):
        """It is prose for a reader. The json branch carries the gate numbers
        in its findings, and a stray sentence there would not parse."""
        _, out, _ = run([write_card(tempfile.mkdtemp()), "--format", "json"])
        self.assertNotIn("need a qualification block", out)
        json.loads(out)


class TestFailingCard(unittest.TestCase):
    def test_a_gate_failure_exits_one_and_names_the_gate(self):
        path = write_card(
            tempfile.mkdtemp(), mutate=lambda c: c["decision"].pop("owner"))
        code, out, _ = run([path])
        self.assertEqual(code, 1)
        self.assertIn("Gate 1", out)
        self.assertIn("decision.owner", out)

    def test_every_failure_is_reported_in_one_run(self):
        """The point of a linter: fix a card once, not once per problem."""
        def mutate(card):
            card["decision"].pop("owner")
            card["constructs"][0]["negative_evidence"] = []
            card["items"]["splits"]["test"]["sealed"] = False

        code, out, _ = run([write_card(tempfile.mkdtemp(), mutate=mutate)])
        self.assertEqual(code, 1)
        for gate in ("Gate 1", "Gate 3", "Gate 5"):
            self.assertIn(gate, out)


class TestWarnings(unittest.TestCase):
    def _warning_card(self):
        def mutate(card):
            card["domain"]["harm_pathways"].append(
                {"id": "hp2", "rank": 2, "severity": "low", "description": "d"})
        return write_card(tempfile.mkdtemp(), mutate=mutate)

    def test_a_warning_alone_still_exits_zero(self):
        code, out, _ = run([self._warning_card()])
        self.assertEqual(code, 0)
        self.assertIn("WARNING", out)

    def test_warnings_as_errors_flips_the_exit_code(self):
        code, _, _ = run([self._warning_card(), "--warnings-as-errors"])
        self.assertEqual(code, 1)


class TestJsonFormat(unittest.TestCase):
    def test_json_output_is_machine_readable(self):
        path = write_card(
            tempfile.mkdtemp(), mutate=lambda c: c["decision"].pop("owner"))
        code, out, _ = run([path, "--format", "json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["findings"][0]["gate"], 1)
        self.assertEqual(payload["findings"][0]["path"], "decision.owner")
        self.assertEqual(payload["error_count"], 1)

    def test_a_valid_card_produces_an_empty_findings_list(self):
        code, out, _ = run([write_card(tempfile.mkdtemp()), "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["findings"], [])


class TestUnreadableCard(unittest.TestCase):
    def test_a_missing_file_exits_two(self):
        """Distinct from exit 1: "this is not a card" and "this card fails its
        gates" are different answers, and a pipeline needs to tell them apart."""
        code, _, err = run([os.path.join(tempfile.mkdtemp(), "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("nope.json", err)
        self.assertIn("no such card", err)

    def test_malformed_json_exits_two(self):
        path = os.path.join(tempfile.mkdtemp(), "eval-card.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        code, _, err = run([path])
        self.assertEqual(code, 2)
        self.assertIn("eval-card.json", err)
        self.assertIn("json", err.lower())

    def test_a_structurally_broken_card_exits_one_not_two(self):
        """It parsed. It is a card with a missing block, which is a finding,
        not an unreadable file."""
        path = write_card(tempfile.mkdtemp(), mutate=lambda c: c.pop("claims"))
        code, out, _ = run([path])
        self.assertEqual(code, 1)
        self.assertIn("structure", out.lower())


class TestUnencodableConsole(unittest.TestCase):
    """The card's text belongs to its author, not to us, so it can contain
    anything. On a legacy Windows console a strict encoder turns that into a
    traceback halfway through the report."""

    def _card_with_an_em_dash(self):
        directory = tempfile.mkdtemp()
        path = write_card(
            directory,
            mutate=lambda c: c["constructs"][0].update(negative_evidence=[]))
        with open(path, encoding="utf-8") as handle:
            card = json.load(handle)
        card["constructs"][0]["id"] = "grounding — v2"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(card, handle, ensure_ascii=False)
        return path

    def test_a_console_that_cannot_encode_the_card_does_not_crash_the_run(self):
        script = os.path.join(os.path.dirname(HERE), "check_eval_card.py")
        environment = dict(os.environ, PYTHONIOENCODING="cp850")
        result = subprocess.run(
            [sys.executable, script, self._card_with_an_em_dash()],
            capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("UnicodeEncodeError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        # The gate finding still has to arrive, in whatever form the console
        # can show. This is the point: degraded, not lost.
        self.assertIn("Gate 3", result.stdout)
        self.assertIn("grounding", result.stdout)

    def test_the_same_card_on_a_utf8_console_keeps_the_character_intact(self):
        """Degrading on cp850 must not mean degrading everywhere. A console
        that can render the em dash still gets the em dash."""
        script = os.path.join(os.path.dirname(HERE), "check_eval_card.py")
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, script, self._card_with_an_em_dash()],
            capture_output=True, text=True, encoding="utf-8", env=environment)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("grounding — v2", result.stdout)


if __name__ == "__main__":
    unittest.main()
