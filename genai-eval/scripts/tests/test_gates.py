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


class TestGate2HarmPathways(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertEqual(run_gate(gates.gate_2_harm_pathways), [])

    def test_a_construct_with_no_pathway_fires(self):
        """Dropping the only reference also orphans hp1, so the warning is part
        of the correct answer here — pin both rather than only the error."""
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["constructs"][0].update(harm_pathways=[]),
        )
        self.assertEqual([(f.level, f.path) for f in findings], [
            ("error", "constructs[0].harm_pathways"),
            ("warning", "domain.harm_pathways[0]"),
        ])
        self.assertEqual(findings[0].gate, 2)

    def test_a_dangling_pathway_reference_fires_naming_the_id(self):
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["constructs"][0].update(harm_pathways=["hp_nope"]),
        )
        self.assertEqual([(f.level, f.path) for f in findings], [
            ("error", "constructs[0].harm_pathways"),
            ("warning", "domain.harm_pathways[0]"),
        ])
        self.assertIn("hp_nope", findings[0].message)

    def test_an_unranked_pathway_fires(self):
        """An unranked pathway justifies measuring anything. The ranking is the
        part that makes the trace mean something."""
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["domain"]["harm_pathways"][0].pop("rank"),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "domain.harm_pathways[0].rank")

    def test_a_non_integer_rank_fires(self):
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["domain"]["harm_pathways"][0].update(rank="high"),
        )
        self.assertEqual(len(findings), 1)

    def test_duplicate_ranks_fire(self):
        """Two pathways ranked 1 is not a ranking."""
        def mutate(card):
            card["domain"]["harm_pathways"].append(
                {"id": "hp2", "rank": 1, "severity": "low", "description": "d"})
            # Measure hp2, so the only finding left is the duplicate rank.
            card["constructs"][0]["harm_pathways"].append("hp2")

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "error")
        self.assertEqual(findings[0].path, "domain.harm_pathways[1].rank")

    def test_an_unreferenced_pathway_is_a_warning_not_an_error(self):
        """Listing a pathway you chose not to measure is honest. It is worth
        surfacing, but it is not a failure."""
        def mutate(card):
            card["domain"]["harm_pathways"].append(
                {"id": "hp2", "rank": 2, "severity": "low", "description": "d"})

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "warning")

    def test_a_wrong_shaped_domain_block_does_not_raise(self):
        """The loader reports the shape; this gate has to survive it anyway.
        With no readable pathways, every reference is unknown."""
        findings = run_gate(
            gates.gate_2_harm_pathways, lambda c: c.update(domain="healthcare"))
        self.assertEqual([(f.level, f.path) for f in findings],
                         [("error", "constructs[0].harm_pathways")])
        self.assertIn("hp1", findings[0].message)

    def test_a_malformed_construct_does_not_shift_the_index_of_a_real_one(self):
        """Skip the junk entry, but keep reporting against the card as written:
        the broken construct is the author's second, so it is [1]."""
        def mutate(card):
            card["constructs"].insert(0, "oops")
            card["constructs"][1]["harm_pathways"] = []

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual([(f.level, f.path) for f in findings], [
            ("error", "constructs[1].harm_pathways"),
            ("warning", "domain.harm_pathways[0]"),
        ])

    def test_a_boolean_rank_fires(self):
        """`True` is an `int` in Python, so `rank: true` sails past a bare
        isinstance check and ranks first."""
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["domain"]["harm_pathways"][0].update(rank=True))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "domain.harm_pathways[0].rank")


class TestGatesNeverRaise(unittest.TestCase):
    """The module's contract: a gate returns findings, it does not raise.

    The loader reports a malformed block, but it returns findings rather than
    raising, so a caller can still reach a gate with a card it has already
    complained about. A gate that crashed there would take down the whole
    report — and the CLI catches only ValueError, so an AttributeError would
    escape entirely.
    """

    def test_gate_1_survives_a_non_object_decision(self):
        findings = gates.gate_1_decision({"decision": "oops"})
        self.assertTrue(findings)
        self.assertTrue(all(f.gate == 1 for f in findings))

    def test_gate_1_survives_a_non_object_outcome_entry(self):
        card = base_card()
        card["decision"]["outcomes"].append("not-an-outcome")
        findings = gates.gate_1_decision(card)
        self.assertTrue(findings)

    def test_gate_3_survives_a_non_object_construct(self):
        findings = gates.gate_3_falsifiable({"constructs": ["typo"]})
        self.assertEqual(findings, [])

    def test_gate_3_still_reports_a_real_construct_beside_a_malformed_one(self):
        """Skipping what it cannot read must not mean skipping what it can."""
        card = base_card()
        card["constructs"][0]["negative_evidence"] = []
        card["constructs"].append("typo")
        findings = gates.gate_3_falsifiable(card)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "constructs[0].negative_evidence")


class TestGate4TraceMatrix(unittest.TestCase):
    def _run(self, mutate=None, items=None):
        path = write_card(tempfile.mkdtemp(), mutate=mutate, items=items)
        card, _ = loader.load_card(path)
        return gates.gate_4_trace_matrix(card, path)

    def test_a_valid_card_passes(self):
        self.assertEqual(self._run(), [])

    def test_an_item_whose_claim_does_not_exist_fires(self):
        items = [
            {"item_id": "i1", "claim_id": "cl1"},
            {"item_id": "i2", "claim_id": "cl1"},
            {"item_id": "i3", "claim_id": "cl1"},
            {"item_id": "i4", "claim_id": "cl2"},
            {"item_id": "i5", "claim_id": "cl2"},
            {"item_id": "i6", "claim_id": "ghost"},
        ]
        findings = self._run(items=items)
        orphans = [f for f in findings if "ghost" in f.message]
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0].gate, 4)

    def test_a_claim_with_fewer_than_three_items_fires(self):
        """Fewer than three items cannot support a claim-level reading of the
        score, which is the whole reason for tracing items to claims."""
        items = [
            {"item_id": "i1", "claim_id": "cl1"},
            {"item_id": "i2", "claim_id": "cl1"},
            {"item_id": "i3", "claim_id": "cl1"},
            {"item_id": "i4", "claim_id": "cl2"},
            {"item_id": "i5", "claim_id": "cl2"},
        ]
        findings = self._run(items=items)
        thin = [f for f in findings if "cl2" in f.message]
        self.assertEqual(len(thin), 1)
        self.assertIn("2", thin[0].message)

    def test_an_item_with_no_claim_id_fires(self):
        """Both claims keep three items, so the orphan is the *only* finding —
        otherwise a thin-claim finding would fire too and this test would pass
        without proving the orphan check works."""
        items = [{"item_id": "i%d" % n, "claim_id": "cl1"} for n in range(3)]
        items += [{"item_id": "i%d" % n, "claim_id": "cl2"} for n in range(3, 6)]
        items += [{"item_id": "i7"}]
        findings = self._run(items=items)
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertIn("no claim_id", findings[0].message)

    def test_a_claim_referencing_an_unknown_construct_fires(self):
        findings = self._run(lambda c: c["claims"][0].update(construct="c_ghost"))
        self.assertTrue(any("c_ghost" in f.message for f in findings), findings)

    def test_evidence_and_task_models_must_reference_real_claims(self):
        findings = self._run(lambda c: c["evidence_model"][0].update(claim="cl_ghost"))
        self.assertTrue(
            any("cl_ghost" in f.message and "evidence_model" in f.path
                for f in findings), findings)

    def test_a_claim_with_no_evidence_model_entry_fires(self):
        findings = self._run(lambda c: c["evidence_model"].pop(1))
        self.assertTrue(
            any("cl2" in f.message and "evidence" in f.message.lower()
                for f in findings), findings)

    def test_a_missing_item_pool_is_reported_not_raised(self):
        """The validator must survive a card pointing at a file that is not
        there, and say so — that is a common state for a card in progress.

        Exactly one finding: with no pool to read, every claim trivially has
        zero items, and reporting that too would bury the one fact the author
        can actually act on."""
        findings = self._run(lambda c: c["items"].update(source="items/gone.jsonl"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "items.source")
        self.assertEqual(findings[0].level, "error")

    def test_a_malformed_pool_line_is_reported_with_its_line_number(self):
        directory = tempfile.mkdtemp()
        path = write_card(directory)
        with open(os.path.join(directory, "items", "pool.jsonl"), "a",
                  encoding="utf-8") as handle:
            handle.write("{not json\n")
        card, _ = loader.load_card(path)
        findings = gates.gate_4_trace_matrix(card, path)
        self.assertTrue(any("line 7" in f.message for f in findings), findings)

    def test_a_malformed_line_does_not_stop_the_surviving_rows_counting(self):
        """A bad line is not an unreadable file. The rows that parsed still
        have to be counted, or one typo could hide a thin claim — so this pool
        is deliberately one short on cl2, and both findings must appear."""
        directory = tempfile.mkdtemp()
        items = [{"item_id": "i%d" % n, "claim_id": "cl1"} for n in range(3)]
        items += [{"item_id": "i4", "claim_id": "cl2"},
                  {"item_id": "i5", "claim_id": "cl2"}]
        path = write_card(directory, items=items)
        with open(os.path.join(directory, "items", "pool.jsonl"), "a",
                  encoding="utf-8") as handle:
            handle.write("{not json\n")
        card, _ = loader.load_card(path)
        messages = [f.message for f in gates.gate_4_trace_matrix(card, path)]
        self.assertEqual(len(messages), 2, messages)
        self.assertTrue(any("line 6" in m for m in messages), messages)
        self.assertTrue(any("cl2" in m and "2 items" in m for m in messages),
                        messages)

    def test_a_wrong_shaped_items_block_does_not_raise(self):
        """The loader reports the shape; this gate has to survive it anyway."""
        findings = self._run(lambda c: c.update(items="items/pool.jsonl"))
        self.assertEqual([(f.level, f.path) for f in findings],
                         [("error", "items.source")])

    def test_a_malformed_claim_does_not_shift_the_index_of_a_real_one(self):
        """Skip the junk entry, but keep reporting against the card as the
        author wrote it: the broken claim is their second, so it is [1]."""
        def mutate(card):
            card["claims"].insert(0, "oops")
            card["claims"][1]["construct"] = "c_ghost"

        findings = self._run(mutate)
        self.assertEqual([f.path for f in findings], ["claims[1].construct"])


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
