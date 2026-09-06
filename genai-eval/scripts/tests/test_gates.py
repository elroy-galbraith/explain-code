#!/usr/bin/env python3
"""Tests for card.gates. Run directly: python3 test_gates.py"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card import gates, loader
from card_fixture import base_card, sha256_of, write_card


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

    def test_a_non_string_pathway_id_is_not_matchable(self):
        """The schema requires these ids to be strings, and the id lookup
        filters to strings for that reason -- so a pathway written {"id": 5}
        is not a pathway any construct can trace to, and the construct
        referencing it reports an unknown pathway rather than resolving.

        Pinned because nothing else does: the filter is one isinstance call,
        and a future edit that dropped it would restore the silent match with
        no test to notice.
        """
        def mutate(card):
            card["domain"]["harm_pathways"][0]["id"] = 5
            card["constructs"][0]["harm_pathways"] = [5]

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual([(f.level, f.path) for f in findings], [
            ("error", "constructs[0].harm_pathways"),
            ("warning", "domain.harm_pathways[0]"),
        ])
        self.assertIn("unknown pathway 5", findings[0].message)

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
        self.assertIn("has 2 distinct items", thin[0].message)

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
        self.assertTrue(any("cl2" in m and "2 distinct items" in m for m in messages),
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

    def test_a_pool_padded_with_copies_of_one_item_fires(self):
        """Six rows, one item. Three copies of an item carry no more
        claim-level information than one copy, so counting rows leaves the
        floor satisfiable by copy-paste -- which is exactly how a pool gets
        padded under deadline pressure."""
        items = ([{"item_id": "same", "claim_id": "cl1"}] * 3
                 + [{"item_id": "same", "claim_id": "cl2"}] * 3)
        findings = self._run(items=items)
        thin = [f for f in findings if f.path.startswith("claims[")]
        self.assertEqual([f.path for f in thin], ["claims[0]", "claims[1]"])
        for finding in thin:
            self.assertIn("has 1 distinct items", finding.message)

    def test_a_single_duplicated_item_id_fires_naming_the_id(self):
        """And the duplicate does not count toward its claim: cl2 has three
        rows but two distinct items, so the floor finding fires too."""
        items = [{"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i2", "claim_id": "cl1"},
                 {"item_id": "i3", "claim_id": "cl1"},
                 {"item_id": "i4", "claim_id": "cl2"},
                 {"item_id": "i5", "claim_id": "cl2"},
                 {"item_id": "i4", "claim_id": "cl2"}]
        findings = self._run(items=items)
        self.assertEqual([f.path for f in findings],
                         ["items.source", "claims[1]"])
        self.assertIn("'i4'", findings[0].message)
        self.assertIn("line 6", findings[0].message)
        self.assertIn("line 4", findings[0].message)
        self.assertIn("has 2 distinct items", findings[1].message)

    def test_an_item_with_no_item_id_is_reported_with_its_line(self):
        """It is the one finding: both claims still reach three distinct
        items, so nothing else fires and this cannot pass for the wrong
        reason. The line number is the only handle a row with no id has."""
        items = [{"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i2", "claim_id": "cl1"},
                 {"item_id": "i3", "claim_id": "cl1"},
                 {"claim_id": "cl2"},
                 {"item_id": "i4", "claim_id": "cl2"},
                 {"item_id": "i5", "claim_id": "cl2"},
                 {"item_id": "i6", "claim_id": "cl2"}]
        findings = self._run(items=items)
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path, "items.source")
        self.assertIn("line 4", findings[0].message)
        self.assertIn("no item_id", findings[0].message)

    def test_a_non_string_item_id_cannot_be_counted_as_distinct(self):
        """An id that is not a string is not a usable identifier, so the row
        is reported and left out of the count rather than counted anyway."""
        items = [{"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i2", "claim_id": "cl1"},
                 {"item_id": 5, "claim_id": "cl1"},
                 {"item_id": "i4", "claim_id": "cl2"},
                 {"item_id": "i5", "claim_id": "cl2"},
                 {"item_id": "i6", "claim_id": "cl2"}]
        findings = self._run(items=items)
        self.assertEqual([f.path for f in findings],
                         ["items.source", "claims[0]"])
        self.assertIn("line 3", findings[0].message)
        self.assertIn("has 2 distinct items", findings[1].message)

    def test_a_duplicate_is_reported_even_when_its_claim_is_unknown(self):
        """Two rows sharing an id are ambiguous however they are counted, so
        the check does not hide behind the claim lookup."""
        items = [{"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i2", "claim_id": "cl1"},
                 {"item_id": "i3", "claim_id": "cl1"},
                 {"item_id": "i4", "claim_id": "cl2"},
                 {"item_id": "i5", "claim_id": "cl2"},
                 {"item_id": "i6", "claim_id": "cl2"},
                 {"item_id": "i6", "claim_id": "ghost"}]
        findings = self._run(items=items)
        self.assertEqual([f.path for f in findings],
                         ["items.source", "items.source"])
        self.assertIn("is repeated on", findings[0].message)
        self.assertIn("ghost", findings[1].message)

    def test_one_id_repeated_a_hundred_times_is_one_finding(self):
        """A linter reports a violation once. One id pasted a hundred times is
        one violation, not a hundred and one, and the wall of near-identical
        lines buries the findings a reader came for -- here, the two thin
        claims that are the real problem with this pool."""
        items = [{"item_id": "x", "claim_id": "cl1"}] * 50
        items += [{"item_id": "x", "claim_id": "cl2"}] * 50
        findings = self._run(items=items)

        duplicates = [f for f in findings if f.path == "items.source"]
        self.assertEqual(len(duplicates), 1, [f.message for f in duplicates])
        self.assertEqual(duplicates[0].level, "error")
        self.assertEqual(duplicates[0].gate, 4)
        self.assertIn("'x'", duplicates[0].message)
        self.assertIn("first appears on line 1", duplicates[0].message)
        self.assertIn("99 further rows", duplicates[0].message)

        # The findings the reader actually needs are still there, and still
        # readable beside a single duplicate line.
        self.assertEqual([f.path for f in findings if f.path != "items.source"],
                         ["claims[0]", "claims[1]"])

    def test_two_duplicated_ids_produce_two_findings(self):
        """Collapsing is per id, not per pool: two distinct ids repeated are
        two separate things to fix."""
        items = [{"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i2", "claim_id": "cl1"},
                 {"item_id": "i3", "claim_id": "cl1"},
                 {"item_id": "i1", "claim_id": "cl1"},
                 {"item_id": "i4", "claim_id": "cl2"},
                 {"item_id": "i5", "claim_id": "cl2"},
                 {"item_id": "i6", "claim_id": "cl2"},
                 {"item_id": "i4", "claim_id": "cl2"}]
        duplicates = [f for f in self._run(items=items)
                      if f.path == "items.source"]
        self.assertEqual(len(duplicates), 2, [f.message for f in duplicates])
        self.assertIn("'i1'", duplicates[0].message)
        self.assertIn("'i4'", duplicates[1].message)

    def test_the_repeated_lines_are_named_but_the_list_is_bounded(self):
        """The line numbers are the handle for fixing the pool, so a few are
        named; the tail is counted so one finding stays one line."""
        items = [{"item_id": "dup", "claim_id": "cl1"}] * 9
        items += [{"item_id": "i%d" % n, "claim_id": "cl2"} for n in range(3)]
        message = [f for f in self._run(items=items)
                   if f.path == "items.source"][0].message
        self.assertIn("lines 2, 3, 4, 5, 6 and 3 more", message)


class TestGate5SealedSplit(unittest.TestCase):
    def _run(self, mutate=None, tamper=None):
        directory = tempfile.mkdtemp()
        path = write_card(directory, mutate=mutate)
        if tamper is not None:
            tamper(os.path.join(directory, "items", "test.jsonl"))
        card, _ = loader.load_card(path)
        return gates.gate_5_sealed_split(card, path)

    def test_a_valid_card_passes(self):
        self.assertEqual(self._run(), [])

    def test_a_changed_split_fires_as_an_error_never_a_warning(self):
        """The contamination tripwire. If this ever warns instead of failing,
        the gate is decorative — a changed split is exactly the thing sealing
        was supposed to make impossible."""
        def tamper(path):
            with open(path, "a", encoding="utf-8") as handle:
                handle.write('{"item_id": "sneaky", "claim_id": "cl1"}\n')

        findings = self._run(tamper=tamper)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 5)
        self.assertEqual(findings[0].level, "error")
        self.assertIn("sha256", findings[0].path)

    def test_sealed_false_fires(self):
        findings = self._run(
            lambda c: c["items"]["splits"]["test"].update(sealed=False))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "items.splits.test.sealed")

    def test_a_missing_hash_fires(self):
        findings = self._run(
            lambda c: c["items"]["splits"]["test"].pop("sha256"))
        self.assertEqual(len(findings), 1)

    def test_a_missing_sealed_at_fires(self):
        findings = self._run(
            lambda c: c["items"]["splits"]["test"].pop("sealed_at"))
        self.assertEqual(len(findings), 1)
        self.assertIn("sealed_at", findings[0].path)

    def test_a_missing_canary_fires(self):
        findings = self._run(
            lambda c: c["items"]["contamination_controls"].update(canary=""))
        self.assertEqual(len(findings), 1)
        self.assertIn("canary", findings[0].path)

    def test_a_missing_split_file_is_reported_not_raised(self):
        findings = self._run(
            lambda c: c["items"]["splits"]["test"].update(path="items/gone.jsonl"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "error")

    def test_a_recorded_hash_with_no_split_path_fires(self):
        """The `elif` branch: the card records a hash but names no file to
        check it against. Nothing else in this class reaches it, and untested,
        a swapped if/elif would pass the whole suite."""
        findings = self._run(lambda c: c["items"]["splits"]["test"].pop("path"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "items.splits.test.path")
        self.assertIn("no test split file is named", findings[0].message)

    def test_a_wrong_shaped_items_block_does_not_raise(self):
        """The loader reports the shape; this gate has to survive it anyway.
        With nothing readable, all four checks fire and none of them crash."""
        findings = self._run(lambda c: c.update(items="items/pool.jsonl"))
        self.assertEqual([f.path for f in findings], [
            "items.contamination_controls.canary",
            "items.splits.test.sealed",
            "items.splits.test.sealed_at",
            "items.splits.test.sha256",
        ])

    def test_the_hash_is_computed_over_bytes_not_parsed_json(self):
        """Reformatting the split — same items, different whitespace — must
        still trip the seal. A hash over parsed content would let someone
        rewrite the file and keep the gate green."""
        def tamper(path):
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content.replace('", "', '",  "'))

        findings = self._run(tamper=tamper)
        self.assertEqual(len(findings), 1)
        self.assertIn("sha256", findings[0].path)

    def test_an_empty_sealed_split_fires_even_though_its_hash_matches(self):
        """The hash of an empty file is a perfectly valid sha256, so a card
        can seal nothing and satisfy every other check in this gate. A split
        with no items seals nothing."""
        directory = tempfile.mkdtemp()
        path = write_card(directory, test_split=[])
        card, _ = loader.load_card(path)
        findings = gates.gate_5_sealed_split(card, path)
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path, "items.splits.test.path")
        self.assertEqual(findings[0].level, "error")
        self.assertEqual(findings[0].gate, 5)
        self.assertIn("empty", findings[0].message)

    def test_a_split_of_nothing_but_blank_lines_is_empty_too(self):
        """A file of newlines is not zero bytes, so a size check would pass
        it. It still seals no items. The card's hash is recomputed here so
        that the seal itself matches and this is the only finding left."""
        directory = tempfile.mkdtemp()
        path = write_card(directory)
        split_path = os.path.join(directory, "items", "test.jsonl")
        with open(split_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n\n   \n")
        card, _ = loader.load_card(path)
        card["items"]["splits"]["test"]["sha256"] = sha256_of(split_path)
        findings = gates.gate_5_sealed_split(card, path)
        self.assertEqual([f.path for f in findings],
                         ["items.splits.test.path"])

    def test_a_changed_split_is_reported_as_a_change_not_as_emptiness(self):
        """The two findings must not both fire on one file, and the seal
        break is the one that matters -- emptiness is only interesting once
        the file is known to be the sealed one."""
        def tamper(path):
            open(path, "w", encoding="utf-8").close()

        findings = self._run(tamper=tamper)
        self.assertEqual([f.path for f in findings],
                         ["items.splits.test.sha256"])


class TestGate9Preregistration(unittest.TestCase):
    def _run(self, mutate=None, protocol=None, tamper=None):
        """Gate 9 recomputes the protocol hash, so it needs a card on disk."""
        directory = tempfile.mkdtemp()
        path = write_card(directory, mutate=mutate, protocol=protocol)
        if tamper is not None:
            tamper(os.path.join(directory, "prompts", "v4.md"))
        card, _ = loader.load_card(path)
        return gates.gate_9_preregistration(card, path)

    def test_a_valid_card_passes(self):
        self.assertEqual(self._run(), [])

    def test_a_missing_content_hash_fires(self):
        findings = self._run(lambda c: c["preregistration"].pop("content_hash"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 9)
        self.assertEqual(findings[0].path, "preregistration.content_hash")

    def test_a_missing_sealed_at_fires(self):
        findings = self._run(lambda c: c["preregistration"].pop("sealed_at"))
        self.assertEqual(len(findings), 1)

    def test_an_unparseable_timestamp_fires(self):
        findings = self._run(
            lambda c: c["preregistration"].update(sealed_at="last Tuesday"))
        self.assertEqual(len(findings), 1)
        self.assertIn("sealed_at", findings[0].path)

    def test_a_missing_threshold_fires(self):
        """A preregistration with no decision rule preregisters nothing."""
        findings = self._run(lambda c: c["preregistration"].pop("threshold"))
        self.assertEqual(len(findings), 1)

    def test_an_empty_threshold_fires(self):
        """Gate 9 asks only that a threshold was fixed before the run. Whether
        the decision rule inside it is coherent is Gate 10's question, and the
        schema tags `decision_rule` to Gate 10 — so `{}` is the failure this
        gate names, not a missing decision_rule."""
        findings = self._run(lambda c: c["preregistration"].update(threshold={}))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "preregistration.threshold")

    def test_a_naive_result_timestamp_is_compared_not_crashed_on(self):
        """The seal carries a Z and this result does not. Python refuses to
        compare an aware datetime with a naive one, so the unguarded version of
        this gate raises TypeError on a perfectly ordinary card."""
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "2026-09-05T09:00:00"}}

        findings = self._run(mutate)
        self.assertEqual(len(findings), 1)
        self.assertIn("predates", findings[0].message)

    def test_a_wrong_shaped_preregistration_block_does_not_raise(self):
        """The loader reports the shape; this gate has to survive it anyway."""
        findings = self._run(lambda c: c.update(preregistration="sealed"))
        self.assertEqual([f.path for f in findings], [
            "preregistration.content_hash",
            "preregistration.sealed_at",
            "preregistration.threshold",
        ])

    def test_a_result_timestamped_before_the_seal_fires(self):
        """The goalposts moved. A result that predates the threshold it is
        judged against means the threshold was chosen knowing the answer."""
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "2026-09-05T09:00:00Z"}}

        findings = self._run(mutate)
        self.assertEqual(len(findings), 1)
        self.assertIn("predates", findings[0].message)

    def test_a_result_after_the_seal_passes(self):
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "2026-09-07T09:00:00Z"}}

        self.assertEqual(self._run(mutate), [])

    def test_results_recorded_as_a_list_are_walked(self):
        """A qualification block naturally holds a list of runs. Nothing else
        exercises the list branch of the walk, so removing that recursion would
        pass the whole suite."""
        def mutate(card):
            card["qualification"] = {"runs": [
                {"label": "a", "run_at": "2026-09-07T09:00:00Z"},
                {"label": "b", "run_at": "2026-09-05T09:00:00Z"},
            ]}

        findings = self._run(mutate)
        self.assertEqual([f.path for f in findings],
                         ["qualification.runs[1].run_at"])

    def test_a_rewritten_protocol_fires_naming_both_hashes(self):
        """The schema says content_hash exists so the protocol "cannot be
        edited after the fact without detection". Requiring the string to be
        present and never recomputing it makes that promise unfalsifiable --
        the exact shape of failure this plugin exists to name."""
        directory = tempfile.mkdtemp()
        path = write_card(directory)
        protocol_path = os.path.join(directory, "prompts", "v4.md")
        recorded = sha256_of(protocol_path)
        with open(protocol_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("temperature 2.0, best-of-50, prompts rewritten "
                         "after seeing the results\n")
        actual = sha256_of(protocol_path)
        self.assertNotEqual(recorded, actual)

        card, _ = loader.load_card(path)
        findings = gates.gate_9_preregistration(card, path)
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path, "preregistration.content_hash")
        self.assertEqual(findings[0].level, "error")
        self.assertEqual(findings[0].gate, 9)
        self.assertIn(recorded[:12], findings[0].message)
        self.assertIn(actual[:12], findings[0].message)

    def test_a_hash_over_a_protocol_the_card_does_not_name_fires(self):
        """A hash with nothing to check it against proves nothing."""
        findings = self._run(
            lambda c: c["preregistration"]["protocol"].pop("prompts_ref"))
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path,
                         "preregistration.protocol.prompts_ref")
        self.assertEqual(findings[0].gate, 9)

    def test_an_unreadable_protocol_is_reported_not_raised(self):
        """A card pointing at a file that is not there is a common state for
        a card in progress, and the gate's contract is that it reports."""
        findings = self._run(
            lambda c: c["preregistration"]["protocol"].update(
                prompts_ref="prompts/gone.md"))
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path,
                         "preregistration.protocol.prompts_ref")
        self.assertIn("cannot read", findings[0].message)

    def test_the_sha256_label_on_a_recorded_hash_is_optional(self):
        """The example card writes `sha256:<hex>` for this hash and bare hex
        for the split hash. Both name the same digest, and a gate that failed
        over the label would be failing over punctuation."""
        def bare(card):
            prereg = card["preregistration"]
            prereg["content_hash"] = prereg["content_hash"].split(":", 1)[1]

        def shouting(card):
            prereg = card["preregistration"]
            prereg["content_hash"] = prereg["content_hash"].upper()

        self.assertEqual(self._run(bare), [])
        self.assertEqual(self._run(shouting), [])

    def test_an_unparseable_result_timestamp_fires_at_its_own_path(self):
        """Silently dropping it means Gate 9's ordering check simply does not
        happen for that result and nothing says so."""
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "last Tuesday"}}

        findings = self._run(mutate)
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path, "qualification.results.computed_at")
        self.assertEqual(findings[0].gate, 9)
        self.assertIn("last Tuesday", findings[0].message)

    def test_a_qualification_block_with_no_result_timestamp_is_silent(self):
        """Absence is not a claim. Only a value that was written and cannot
        be read is a finding."""
        def mutate(card):
            card["qualification"] = {"results": {"pass_rate": 0.92}}

        self.assertEqual(self._run(mutate), [])

    def test_an_explicitly_null_result_timestamp_is_silent(self):
        """`null` is how a scaffolded card says "not computed yet". It claims
        no time, so there is nothing for the gate to fail to read."""
        def mutate(card):
            card["qualification"] = {"results": {"computed_at": None}}

        self.assertEqual(self._run(mutate), [])

    def test_an_unreadable_result_time_fires_without_a_readable_seal(self):
        """The result timestamp is a defect in its own right, so reporting it
        must not be nested inside the branch that needs a readable seal."""
        def mutate(card):
            card["preregistration"]["sealed_at"] = "last Tuesday"
            card["qualification"] = {"results": {"computed_at": "soon"}}

        findings = self._run(mutate)
        self.assertEqual(
            sorted(f.path for f in findings),
            ["preregistration.sealed_at", "qualification.results.computed_at"])


class TestRunAll(unittest.TestCase):
    def test_a_valid_card_produces_no_findings_from_any_gate(self):
        path = write_card(tempfile.mkdtemp())
        card, structural = loader.load_card(path)
        self.assertEqual(structural, [])
        self.assertEqual(gates.run_all(card, path), [])

    def test_findings_come_back_in_gate_order(self):
        def mutate(card):
            card["preregistration"].pop("content_hash")   # gate 9
            card["decision"].pop("owner")                 # gate 1
            card["constructs"][0]["negative_evidence"] = []  # gate 3

        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        card, _ = loader.load_card(path)
        found = gates.run_all(card, path)
        self.assertEqual([f.gate for f in found], [1, 3, 9])

    def test_every_registered_gate_runs_even_when_an_earlier_one_fails(self):
        """A linter fixes a card in one pass. Stopping at the first failed gate
        would make someone run it once per problem."""
        def mutate(card):
            card["decision"].pop("owner")
            card["items"]["splits"]["test"]["sealed"] = False

        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        card, _ = loader.load_card(path)
        found = gates.run_all(card, path)
        self.assertEqual(sorted({f.gate for f in found}), [1, 5])

    def test_run_all_sorts_by_gate_number_not_registry_order(self):
        """`ALL` happens to be ascending already, so nothing else here would
        notice if the sort were dropped or the registry reordered."""
        def mutate(card):
            card["preregistration"].pop("content_hash")   # gate 9
            card["decision"].pop("owner")                 # gate 1

        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        card, _ = loader.load_card(path)
        with mock.patch.object(gates, "ALL", list(reversed(gates.ALL))):
            found = gates.run_all(card, path)
        self.assertEqual([f.gate for f in found], [1, 9])


MALFORMED_SHAPES = {
    # The seven shapes that crashed the CLI with a traceback on exit 1 --
    # indistinguishable in CI from a legitimate gate failure, and with the
    # loader's own correct finding computed and then never printed.
    "constructs is a number": lambda c: c.update(constructs=5),
    "claims is a number": lambda c: c.update(claims=5),
    "evidence_model is a number": lambda c: c.update(evidence_model=5),
    "task_model is a number": lambda c: c.update(task_model=5),
    "a construct id is a list": lambda c: c["constructs"][0].update(id=["x"]),
    "an outcome result is a list":
        lambda c: c["decision"]["outcomes"][0].update(result=["x"]),
    "items.source is a number": lambda c: c["items"].update(source=5),
    # Neighbours of those three causes, so the contract is tested as total
    # rather than as a list of the shapes someone happened to probe.
    "decision is a number": lambda c: c.update(decision=5),
    "outcomes is a number": lambda c: c["decision"].update(outcomes=5),
    "outcomes is a string": lambda c: c["decision"].update(outcomes="pass"),
    "domain is a number": lambda c: c.update(domain=5),
    "harm_pathways is a number":
        lambda c: c["domain"].update(harm_pathways=5),
    "a pathway id is a list":
        lambda c: c["domain"]["harm_pathways"][0].update(id=["x"]),
    "a construct's pathway list holds a list":
        lambda c: c["constructs"][0].update(harm_pathways=[["x"]]),
    "a construct's pathway list is a number":
        lambda c: c["constructs"][0].update(harm_pathways=5),
    "a claim's construct is a list":
        lambda c: c["claims"][0].update(construct=["x"]),
    "a claim id is a list": lambda c: c["claims"][0].update(id=["x"]),
    "a claim id is an object": lambda c: c["claims"][0].update(id={"a": 1}),
    "an evidence entry's claim is a list":
        lambda c: c["evidence_model"][0].update(claim=["x"]),
    "a task entry's claim is a list":
        lambda c: c["task_model"][0].update(claim=["x"]),
    "items is a number": lambda c: c.update(items=5),
    "splits is a number": lambda c: c.update(items={"splits": 5}),
    "the test split is a number":
        lambda c: c["items"]["splits"].update(test=5),
    "the split path is a number":
        lambda c: c["items"]["splits"]["test"].update(path=5),
    "the split hash is a number":
        lambda c: c["items"]["splits"]["test"].update(sha256=5),
    "the split path names a directory":
        lambda c: c["items"]["splits"]["test"].update(path="items"),
    "grader is a number": lambda c: c.update(grader=5),
    "preregistration is a number": lambda c: c.update(preregistration=5),
    "the protocol block is a number":
        lambda c: c["preregistration"].update(protocol=5),
    "prompts_ref is a number":
        lambda c: c["preregistration"]["protocol"].update(prompts_ref=5),
    "prompts_ref names a directory":
        lambda c: c["preregistration"]["protocol"].update(prompts_ref="items"),
    "content_hash is a number":
        lambda c: c["preregistration"].update(content_hash=5),
    "content_hash is a list":
        lambda c: c["preregistration"].update(content_hash=["x"]),
    "sealed_at is a number": lambda c: c["preregistration"].update(sealed_at=5),
    "threshold is a number": lambda c: c["preregistration"].update(threshold=5),
    "qualification is a number": lambda c: c.update(qualification=5),
    "qualification is a list":
        lambda c: c.update(qualification=[{"run_at": "nope"}]),
    "a result timestamp is a number":
        lambda c: c.update(qualification={"r": {"computed_at": 5}}),
    "a result timestamp is an object":
        lambda c: c.update(qualification={"r": {"computed_at": {}}}),
    "schema_version is a list": lambda c: c.update(schema_version=["x"]),
    "tier is a list": lambda c: c.update(tier=["x"]),
    "status is a list": lambda c: c.update(status=["x"]),
    "constructs holds a number": lambda c: c.update(constructs=[5]),
    "claims holds a number": lambda c: c.update(claims=[5]),
    "harm_pathways holds a number":
        lambda c: c["domain"].update(harm_pathways=[5]),
    "the card is empty": lambda c: [c.pop(key) for key in list(c)],
}


class TestGatesSurviveAnyShape(unittest.TestCase):
    """The module's contract, tested as total rather than as a sample.

    The loader reports a malformed block and then *returns*, so every gate
    runs over cards it has already complained about. A gate that raises there
    takes the whole report down: the CLI catches only ValueError around
    `load_card`, so a TypeError from a gate escapes as a traceback on exit 1 --
    which in CI is indistinguishable from a legitimate gate failure, and which
    swallows the loader's own correct finding along with it.

    Driven through `run_all` because that is what the CLI calls, and so where
    a crash actually escapes.
    """

    def _run_all(self, mutate):
        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        card, structural = loader.load_card(path)
        return structural, gates.run_all(card, path)

    def test_no_malformed_shape_makes_any_gate_raise(self):
        """The assertion is that the call returns at all. Findings are the
        subject of the tests below; not crashing is the subject of this one."""
        for label, mutate in sorted(MALFORMED_SHAPES.items()):
            with self.subTest(shape=label):
                self._run_all(mutate)

    def test_a_non_list_constructs_block_reports_instead_of_crashing(self):
        structural, found = self._run_all(lambda c: c.update(constructs=5))
        self.assertEqual([f.path for f in structural], ["constructs"])
        self.assertEqual(
            [f.path for f in found if f.level == "error"],
            ["claims[0].construct", "claims[1].construct"])

    def test_a_non_list_claims_block_reports_instead_of_crashing(self):
        structural, found = self._run_all(lambda c: c.update(claims=5))
        self.assertEqual([f.path for f in structural], ["claims"])
        self.assertTrue(found)
        self.assertTrue(all(f.gate == 4 for f in found), found)

    def test_a_non_list_evidence_model_reports_instead_of_crashing(self):
        structural, found = self._run_all(lambda c: c.update(evidence_model=5))
        self.assertEqual([f.path for f in structural], ["evidence_model"])
        self.assertEqual([f.path for f in found], ["claims[0]", "claims[1]"])
        self.assertIn("no evidence model entry", found[0].message)

    def test_a_non_list_task_model_reports_instead_of_crashing(self):
        structural, found = self._run_all(lambda c: c.update(task_model=5))
        self.assertEqual([f.path for f in structural], ["task_model"])
        self.assertEqual([f.path for f in found], ["claims[0]", "claims[1]"])
        self.assertIn("no task model entry", found[0].message)

    def test_an_unhashable_construct_id_reports_instead_of_crashing(self):
        """A list where an id belongs used to raise `unhashable type` out of a
        set comprehension, before any finding was produced. An id that is not
        a string is not a usable identifier, so nothing references it."""
        _, found = self._run_all(lambda c: c["constructs"][0].update(id=["x"]))
        self.assertEqual([f.path for f in found],
                         ["claims[0].construct", "claims[1].construct"])

    def test_an_unhashable_outcome_result_reports_instead_of_crashing(self):
        _, found = self._run_all(
            lambda c: c["decision"]["outcomes"][0].update(result=["x"]))
        self.assertEqual([f.path for f in found], ["decision.outcomes"])
        self.assertIn("'pass'", found[0].message)

    def test_a_non_string_item_source_reports_instead_of_crashing(self):
        """`resolve()` wants a path and raises on anything else. Gate 5 has
        always guarded its own path with `_blank`; Gate 4 checked only
        falsiness, and the asymmetry was the tell."""
        _, found = self._run_all(lambda c: c["items"].update(source=5))
        self.assertEqual([f.path for f in found], ["items.source"])
        self.assertIn("no item pool is named", found[0].message)

    def test_a_pool_that_is_not_utf8_is_reported_not_raised(self):
        """UnicodeDecodeError is a ValueError, not an OSError, so it would
        otherwise escape both the gate and the CLI's own handler."""
        directory = tempfile.mkdtemp()
        path = write_card(directory)
        pool = os.path.join(directory, "items", "pool.jsonl")
        with open(pool, "wb") as handle:
            handle.write(b'{"item_id": "\xff\xfe", "claim_id": "cl1"}\n')
        card, _ = loader.load_card(path)
        findings = gates.gate_4_trace_matrix(card, path)
        self.assertEqual([f.path for f in findings], ["items.source"])
        self.assertIn("cannot read the item pool", findings[0].message)


class TestTheWorkedExample(unittest.TestCase):
    """The example card is meant to be a card that passes.

    It is the only card in the repo written by hand rather than by a fixture,
    so it is the only thing that catches a gate that passes the fixture and
    fails a real card.
    """

    PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "examples", "rag-grounding", "eval-card.json")

    def test_the_example_card_exists_where_this_test_looks_for_it(self):
        """Otherwise the test below would pass on a typo in the path."""
        self.assertTrue(os.path.isfile(self.PATH), self.PATH)

    def test_the_example_card_has_no_structural_findings(self):
        _, structural = loader.load_card(self.PATH)
        self.assertEqual([f.path for f in structural], [])

    def test_the_example_card_produces_one_warning_and_no_errors(self):
        card, _ = loader.load_card(self.PATH)
        found = gates.run_all(card, self.PATH)
        self.assertEqual([f.path for f in found if f.level == "error"], [])
        self.assertEqual([(f.gate, f.path) for f in found],
                         [(2, "domain.harm_pathways[2]")])


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
