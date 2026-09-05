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
