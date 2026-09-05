#!/usr/bin/env python3
"""End-to-end tests for check_eval_card.py. Run: python3 test_check_eval_card.py"""

import importlib.util
import io
import json
import os
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


if __name__ == "__main__":
    unittest.main()
