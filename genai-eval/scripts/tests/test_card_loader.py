#!/usr/bin/env python3
"""Tests for card.loader. Run directly: python3 test_card_loader.py"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card import loader
from card_fixture import write_card


def _copy(entry):
    """A deep copy, so a mutation of the duplicate cannot touch the original."""
    return json.loads(json.dumps(entry))


class TestLoadValidCard(unittest.TestCase):
    def test_a_valid_card_loads_with_no_structural_findings(self):
        path = write_card(tempfile.mkdtemp())
        card, findings = loader.load_card(path)
        self.assertEqual(findings, [], [f.message for f in findings])
        self.assertEqual(card["schema_version"], 1)
        self.assertEqual(card["tier"], 2)


class TestStructuralFindings(unittest.TestCase):
    def _findings(self, mutate):
        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        _, findings = loader.load_card(path)
        return findings

    def test_missing_top_level_block_is_reported_with_its_path(self):
        findings = self._findings(lambda c: c.pop("claims"))
        self.assertEqual(len(findings), 1, [f.message for f in findings])
        self.assertEqual(findings[0].path, "claims")
        self.assertIsNone(findings[0].gate)
        self.assertEqual(findings[0].level, "error")

    def test_every_missing_block_is_reported_not_just_the_first(self):
        """The whole point of a linter: fix one card once, not iteratively."""
        def mutate(card):
            card.pop("claims")
            card.pop("grader")
            card.pop("preregistration")

        findings = self._findings(mutate)
        self.assertEqual(
            sorted(f.path for f in findings),
            ["claims", "grader", "preregistration"],
        )

    def test_unknown_schema_version_is_reported(self):
        findings = self._findings(lambda c: c.update(schema_version=99))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "schema_version")

    def test_tier_outside_one_to_three_is_reported(self):
        findings = self._findings(lambda c: c.update(tier=7))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "tier")

    def test_unknown_status_is_reported(self):
        findings = self._findings(lambda c: c.update(status="marinating"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "status")

    def test_a_non_object_block_is_reported(self):
        findings = self._findings(lambda c: c.update(decision="oops"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "decision")

    def test_a_non_object_entry_in_a_list_block_is_reported_with_its_index(self):
        """The index must address the card as written, so a reader can find
        the offending entry without counting past the valid ones."""
        findings = self._findings(
            lambda c: c.update(constructs=[c["constructs"][0], "typo"]))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "constructs[1]")
        self.assertIsNone(findings[0].gate)

    def test_an_empty_constructs_array_is_reported(self):
        """Gates 2 and 3 iterate constructs, so an empty array would pass them
        vacuously. Presence is not enough — the block has to have content."""
        findings = self._findings(lambda c: c.update(constructs=[]))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "constructs")
        self.assertEqual(findings[0].level, "error")

    def test_an_empty_claims_array_is_reported(self):
        """Gate 4's per-claim checks iterate claims, with the same consequence."""
        findings = self._findings(lambda c: c.update(claims=[]))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "claims")


class TestDuplicateIds(unittest.TestCase):
    """The schema says "unique within the card" for five blocks of ids and
    nothing enforced it.

    This lives in the loader rather than in a gate because it is a structural
    property of the card and it spans five blocks answering to different
    gates -- and because the loader already owns "this card is malformed".
    Gate 2 checks duplicate *ranks*, so uniqueness was in scope for the design
    and the ids were simply missed.
    """

    def _duplicates(self, mutate):
        path = write_card(tempfile.mkdtemp(), mutate=mutate)
        _, findings = loader.load_card(path)
        return [f for f in findings if "already used" in f.message]

    def test_a_duplicate_id_is_reported_in_every_block_that_requires_one(self):
        """A duplicate claim id makes the trace matrix ambiguous: an item's
        `claim_id` no longer says which claim it supports."""
        expected = {
            "constructs": "constructs[1].id",
            "claims": "claims[2].id",
            "evidence_model": "evidence_model[2].id",
            "task_model": "task_model[2].id",
        }
        for block, path in sorted(expected.items()):
            with self.subTest(block=block):
                findings = self._duplicates(
                    lambda c, b=block: c[b].append(_copy(c[b][0])))
                self.assertEqual([f.path for f in findings], [path])
                self.assertIsNone(findings[0].gate)
                self.assertEqual(findings[0].level, "error")

    def test_a_duplicate_harm_pathway_id_is_reported(self):
        """`harm_pathways` carries the same rule but lives inside `domain`, so
        it is not one of LIST_OF_OBJECT_BLOCKS and is reached separately -- a
        check that skipped it would still pass the four tests above."""
        def mutate(card):
            pathways = card["domain"]["harm_pathways"]
            pathways.append(_copy(pathways[0]))

        findings = self._duplicates(mutate)
        self.assertEqual([f.path for f in findings],
                         ["domain.harm_pathways[1].id"])

    def test_the_finding_lands_on_the_second_occurrence_and_names_the_first(self):
        """The duplicate is the entry the author added, so that is the index
        to point at; the original is named in the message so both are findable
        without counting."""
        def mutate(card):
            card["claims"].append(_copy(card["claims"][0]))

        findings = self._duplicates(mutate)
        self.assertEqual(findings[0].path, "claims[2].id")
        self.assertIn("'cl1'", findings[0].message)
        self.assertIn("claims[0]", findings[0].message)

    def test_three_copies_of_one_id_report_the_second_and_the_third(self):
        """Reporting only the first repeat would leave a card needing two
        passes to fix, which is what this validator exists not to do."""
        def mutate(card):
            for _ in range(2):
                card["claims"].append(_copy(card["claims"][0]))

        findings = self._duplicates(mutate)
        self.assertEqual([f.path for f in findings],
                         ["claims[2].id", "claims[3].id"])

    def test_distinct_ids_in_every_block_report_nothing(self):
        """The valid fixture is the control: if it tripped this check, every
        test above would be passing for the wrong reason."""
        self.assertEqual(self._duplicates(None), [])

    def test_a_non_string_id_is_not_treated_as_a_duplicate_of_another(self):
        """Two entries whose ids are both `null` are not two uses of one id --
        they are two entries with no id, which is a different complaint and
        not this check's to make. An unhashable id must not raise either."""
        def mutate(card):
            card["claims"][0]["id"] = None
            card["claims"][1]["id"] = None
            card["constructs"].append(
                {"id": ["x"], "definition": "d", "negative_evidence": ["n"],
                 "harm_pathways": ["hp1"]})
            card["constructs"].append(
                {"id": ["x"], "definition": "d", "negative_evidence": ["n"],
                 "harm_pathways": ["hp1"]})

        self.assertEqual(self._duplicates(mutate), [])


class TestUnreadableInput(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            loader.load_card(os.path.join(tempfile.mkdtemp(), "nope.json"))

    def test_malformed_json_raises_naming_the_file(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "eval-card.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with self.assertRaises(ValueError) as caught:
            loader.load_card(path)
        self.assertIn(path, str(caught.exception))

    def test_a_json_array_is_rejected(self):
        """A card is an object. A list parses cleanly and would then fail with
        confusing key errors deep inside the gates."""
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "eval-card.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)
        with self.assertRaises(ValueError):
            loader.load_card(path)


class TestResolve(unittest.TestCase):
    def test_paths_resolve_against_the_cards_own_directory(self):
        """A card and its item pool travel together, so a relative path inside
        a card resolves against the card's own folder — not the working
        directory of whoever happened to run the validator.

        Asserted as a relationship to a real directory rather than as an
        equality against a hard-coded path literal, because a literal only
        agrees with itself on the platform it was written for.
        """
        directory = tempfile.mkdtemp()
        card_path = os.path.join(directory, "eval-card.json")

        resolved = loader.resolve(card_path, "items/pool.jsonl")
        resolved = os.path.normpath(resolved)

        self.assertEqual(os.path.dirname(os.path.dirname(resolved)), directory)
        self.assertTrue(
            resolved.endswith(os.path.join("items", "pool.jsonl")), resolved)

    def test_an_absolute_path_inside_a_card_is_left_alone(self):
        absolute = os.path.abspath(os.sep + "elsewhere" + os.sep + "pool.jsonl")
        self.assertEqual(loader.resolve("/cards/x/eval-card.json", absolute), absolute)


if __name__ == "__main__":
    unittest.main()
