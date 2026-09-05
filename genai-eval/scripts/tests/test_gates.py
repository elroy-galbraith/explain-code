#!/usr/bin/env python3
"""Tests for card.gates. Run directly: python3 test_gates.py"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card import gates, loader
from card_fixture import base_card, write_card


def run_gate(check, mutate=None):
    """Apply `mutate` to a valid card, then run one gate over it."""
    card = base_card()
    if mutate is not None:
        mutate(card)
    return check(card)


class TestGate1Decision(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertEqual(run_gate(gates.gate_1_decision), [])

    def test_missing_owner_fires(self):
        findings = run_gate(gates.gate_1_decision, lambda c: c["decision"].pop("owner"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 1)
        self.assertEqual(findings[0].path, "decision.owner")

    def test_blank_owner_fires(self):
        """An empty string is not a named owner. Accepting it would let the
        gate be satisfied by typing a quote mark twice."""
        findings = run_gate(
            gates.gate_1_decision, lambda c: c["decision"].update(owner="   "))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "decision.owner")

    def test_a_missing_outcome_fires_naming_which(self):
        findings = run_gate(
            gates.gate_1_decision,
            lambda c: c["decision"].update(
                outcomes=[o for o in c["decision"]["outcomes"]
                          if o["result"] != "borderline"]),
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("borderline", findings[0].message)

    def test_an_outcome_with_no_action_fires(self):
        def mutate(card):
            card["decision"]["outcomes"][1]["action"] = ""

        findings = run_gate(gates.gate_1_decision, mutate)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "decision.outcomes[1].action")

    def test_two_problems_produce_two_findings(self):
        def mutate(card):
            card["decision"].pop("owner")
            card["decision"]["outcomes"][0]["action"] = ""

        self.assertEqual(len(run_gate(gates.gate_1_decision, mutate)), 2)


class TestGate3Falsifiable(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertEqual(run_gate(gates.gate_3_falsifiable), [])

    def test_empty_negative_evidence_fires(self):
        """A construct with nothing that would count against it is not
        falsifiable, so no result can disconfirm it."""
        findings = run_gate(
            gates.gate_3_falsifiable,
            lambda c: c["constructs"][0].update(negative_evidence=[]),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 3)
        self.assertEqual(findings[0].path, "constructs[0].negative_evidence")

    def test_missing_negative_evidence_fires(self):
        findings = run_gate(
            gates.gate_3_falsifiable,
            lambda c: c["constructs"][0].pop("negative_evidence"),
        )
        self.assertEqual(len(findings), 1)

    def test_blank_entries_do_not_count(self):
        findings = run_gate(
            gates.gate_3_falsifiable,
            lambda c: c["constructs"][0].update(negative_evidence=["", "  "]),
        )
        self.assertEqual(len(findings), 1)

    def test_each_bad_construct_fires_separately(self):
        def mutate(card):
            card["constructs"].append({
                "id": "c_two", "definition": "d",
                "positive_evidence": ["p"], "negative_evidence": [],
                "harm_pathways": ["hp1"],
            })
            card["constructs"][0]["negative_evidence"] = []

        findings = run_gate(gates.gate_3_falsifiable, mutate)
        self.assertEqual(len(findings), 2)


class TestGatesDoNotBleed(unittest.TestCase):
    def test_breaking_gate_1_leaves_gate_3_silent(self):
        """Each gate answers its own question. A card broken in one place
        should not produce a cascade that hides where the problem is."""
        card = base_card()
        card["decision"].pop("owner")
        self.assertEqual(len(gates.gate_1_decision(card)), 1)
        self.assertEqual(gates.gate_3_falsifiable(card), [])


if __name__ == "__main__":
    unittest.main()
