# genai-eval Phase 2 — the eval card and `eval-design` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn six of the SOP's eleven gates from questions a model can answer "yes" to, into checks a script either passes or fails — by giving an evaluation a machine-readable card and a validator that reads it.

**Architecture:** A new `genai-eval/scripts/card/` package: `loader.py` reads a card and validates its structure, `gates.py` holds one function per mechanical gate, and `check_eval_card.py` is a linter-style CLI that reports every violation at once with a JSON path and a gate number. Alongside it, `templates/` documents the card field by field, `examples/rag-grounding/` is a complete tier-2 card, and `skills/eval-design/SKILL.md` is the skill that produces one.

**Tech Stack:** Python 3.9+, standard library only. `unittest`. GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`](../specs/2026-09-05-genai-eval-plugin-design.md) — sections 3.1, 3.2, 4.2, 4.4, 6.

**Builds on:** Phase 1A ([`…-phase1a-evalstats.md`](2026-09-05-genai-eval-phase1a-evalstats.md)) and Phase 1B ([`…-phase1b-eval-qualify.md`](2026-09-05-genai-eval-phase1b-eval-qualify.md)), together delivering `evalstats/`, `calibration/`, `calibrate.py`, the `eval-qualify` skill, and 248 tests.

## Global Constraints

- **Standard library only.** No pip install step, ever. No numpy, scipy, pandas, or PyYAML — a card is JSON precisely because the stdlib has no YAML parser.
- **Python floor is 3.9.** CI runs a matrix over `["3.9", "3.x"]`.
- **`evalstats/` stays pure.** No file I/O and no printing inside it. This phase does not touch it.
- **The validator is a linter, not an assertion.** It reports *every* violation in one pass with a JSON path and a gate number, and never dies on the first. Exit non-zero when any error-level finding exists.
- **A hash mismatch on a sealed test split is always an error, never a warning.** It is the contamination tripwire; a warn-and-continue there defeats the gate entirely.
- **Degenerate input raises `ValueError` or returns `None`; it never returns a plausible-looking result.**
- **Every gate needs one deliberately broken card per failure mode**, asserting that gate fires *and that no other gate fires with it*. A test that only checks "some finding appeared" cannot tell a working gate from a noisy one.
- **Tests use stdlib `unittest`** and must run directly.

## Scope finding: card mode for `eval-qualify` belongs to no phase

The spec assumes something no phase builds. §3.1 says "`eval-qualify` appends a `qualification` block"; §3.2 marks Gates 6, 7, 10 and 11 "Computed" and written into the card; §4.3's renderer takes "a card, with or without its `qualification` block". But §10 puts bare mode in Phase 1, the card and `eval-design` in Phase 2, and the renderer in Phase 3. **Nothing writes the qualification block.**

This plan does not fix that — silently widening a phase is how phases stop shipping. The recommendation is a **Phase 2B** covering card mode for `eval-qualify`: reading a card, running the existing `calibration/` analysis against its item pool, appending the qualification block, and adding Gates 6, 7, 8, 10 and 11 to the validator. It has to land before Phase 3, because the renderer depends on the block existing.

Consequently **this phase's validator covers only the six design-time gates** — 1, 2, 3, 4, 5 and 9. `gates.py` is structured so the qualification-time gates slot in beside them without rework.

## File structure

```
genai-eval/
├── templates/
│   ├── eval-card.template.json      # NEW — fill-in-the-blanks card
│   └── eval-card.schema.md          # NEW — field-by-field reference
├── scripts/
│   ├── card/                        # NEW package
│   │   ├── __init__.py
│   │   ├── loader.py                # read a card, validate its structure
│   │   └── gates.py                 # one function per mechanical gate
│   ├── check_eval_card.py           # NEW — the CLI
│   └── tests/
│       ├── card_fixture.py          # NEW — builds a valid card on disk
│       ├── test_card_loader.py      # NEW
│       ├── test_gates.py            # NEW
│       └── test_check_eval_card.py  # NEW — CLI end to end
├── examples/rag-grounding/
│   ├── eval-card.json               # NEW — a complete tier-2 card
│   ├── items/pool.jsonl             # NEW
│   ├── items/test.jsonl             # NEW
│   └── README.md                    # NEW
└── skills/eval-design/
    └── SKILL.md                     # NEW
```

Modified: root `README.md`, `genai-eval/README.md`, `.claude-plugin/marketplace.json`, `genai-eval/.claude-plugin/plugin.json`, `.github/workflows/genai-eval-tests.yml`, and the spec's §3.3 tier table.

---

### Task 1: The card schema document and template

**Files:**
- Create: `genai-eval/templates/eval-card.schema.md`
- Create: `genai-eval/templates/eval-card.template.json`

**Interfaces:**
- Produces: the field contract every later task reads. Field names here are authoritative; `loader.py` and `gates.py` must match them exactly.

No code, no tests — this is the contract. It comes first because six later tasks encode it, and a field renamed after Task 5 would silently break Tasks 3-7.

- [ ] **Step 1: Write the schema reference**

Create `genai-eval/templates/eval-card.schema.md`. Document every field of the card shown in spec §3.1, in this order, with a table per top-level block giving **field / type / required / what it is for / which gate reads it**. Cover:

- `schema_version` (int, required, currently `1`), `id` (string), `title` (string), `tier` (int 1-3, required), `status` (one of `draft`, `designed`, `sealed`, `qualified`, `retired`), `created` (ISO 8601 date).
- `decision`: `question`, `owner`, `outcomes[]` each with `result` (one of `pass`, `fail`, `borderline`) and `action`. **Gate 1.**
- `domain`: `users`, `operating_conditions`, `harm_pathways[]` each with `id`, `rank`, `severity`, `description`. **Gate 2.**
- `constructs[]`: `id`, `definition`, `positive_evidence[]`, `negative_evidence[]`, `harm_pathways[]`. **Gates 2 and 3.**
- `claims[]`: `id`, `construct`, `statement`. **Gate 4.**
- `evidence_model[]`: `id`, `claim`, `observable`, `scoring_rule`, `rubric_ref`. **Gate 4.**
- `task_model[]`: `id`, `claim`, `task_family`, `conditions[]`. **Gate 4.**
- `items`: `source` (path to a JSONL pool, relative to the card), `sampling_frame`, `contamination_controls` (`canary`, `date_stamped`, `novel_items`), `splits` (`dev.path`, `test.path`, `test.sealed`, `test.sha256`, `test.sealed_at`). **Gates 4 and 5.**
- `grader`: `kind`, `model`, `mode`, `rubric_ref`, `gold_set`, `bias_probes[]`.
- `preregistration`: `sealed_at`, `content_hash`, `protocol` (`prompts_ref`, `seeds[]`, `temperature`, `elicitation_budget`), `baselines[]`, `threshold` (`metric`, `minimum_interesting_difference`, `decision_rule`). **Gate 9.**

State plainly at the top: **every item in the pool carries a `claim_id`**, and that is what makes Gate 4 checkable. State that paths inside the card resolve **relative to the card file's own directory**, so a card and its items move together.

Add a closing section, "Gates this file does not yet describe", naming the `qualification` block and Gates 6, 7, 8, 10 and 11 as Phase 2B work, so a reader does not think the card is complete as specified.

- [ ] **Step 2: Write the template**

Create `genai-eval/templates/eval-card.template.json` — a complete card with every field present and placeholder values that are obviously placeholders (`"FILL IN: ..."` strings, empty arrays where a list is expected). It must be valid JSON and structurally complete, so `check_eval_card.py` run against it reports gate failures about *content* rather than parse errors.

- [ ] **Step 3: Verify the template parses**

Run: `python3 -c "import json; d=json.load(open('genai-eval/templates/eval-card.template.json')); print(sorted(d))"`
Expected: prints the top-level keys, including `claims`, `constructs`, `decision`, `domain`, `evidence_model`, `grader`, `items`, `preregistration`, `schema_version`, `task_model`, `tier`.

- [ ] **Step 4: Commit**

```bash
git add genai-eval/templates/
git commit -m "docs(genai-eval): eval card schema reference and template"
```

---

### Task 2: The card loader and structural validation

**Files:**
- Create: `genai-eval/scripts/card/__init__.py`
- Create: `genai-eval/scripts/card/loader.py`
- Create: `genai-eval/scripts/tests/card_fixture.py`
- Create: `genai-eval/scripts/tests/test_card_loader.py`

**Interfaces:**
- Produces:
  - `loader.Finding` — a dataclass with fields `gate` (int or None), `level` (`"error"` or `"warning"`), `path` (str), `message` (str).
  - `loader.load_card(path) -> (dict, list[Finding])` — parses the card and returns it with structural findings (`gate=None`). Raises `ValueError` on unreadable or non-JSON input, and on a missing file.
  - `loader.resolve(card_path, relative) -> str` — resolves a path inside a card against the card's own directory.
  - `card_fixture.write_card(directory, mutate=None, items=None) -> str` — writes a valid card plus its item pool and test split into `directory`, applying `mutate(card_dict)` first if given, and returns the card's path.

Structural findings carry `gate=None`: a malformed card is not a failed gate, it is a card the gates cannot be run against.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_card_loader.py`:

```python
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
        """A card and its item pool travel together; resolving against the
        process's working directory would break the moment anyone runs the
        validator from somewhere else."""
        resolved = loader.resolve("/cards/x/eval-card.json", "items/pool.jsonl")
        self.assertEqual(
            os.path.normpath(resolved),
            os.path.normpath("/cards/x/items/pool.jsonl"),
        )

    def test_an_absolute_path_inside_a_card_is_left_alone(self):
        absolute = os.path.abspath(os.sep + "elsewhere" + os.sep + "pool.jsonl")
        self.assertEqual(loader.resolve("/cards/x/eval-card.json", absolute), absolute)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_card_loader.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'card'`

- [ ] **Step 3: Write the fixture helper**

Create `genai-eval/scripts/tests/card_fixture.py`:

```python
#!/usr/bin/env python3
"""Builds a valid eval card on disk, so each gate test can break exactly one thing.

Every gate test starts from this card and mutates one field. That is what makes
"this gate fires and no other gate fires" a meaningful assertion — if the base
card were already failing something, every test would pass for the wrong reason.
"""

import hashlib
import json
import os

POOL = [
    {"item_id": "i1", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i2", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i3", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i4", "claim_id": "cl2", "prompt": "..."},
    {"item_id": "i5", "claim_id": "cl2", "prompt": "..."},
    {"item_id": "i6", "claim_id": "cl2", "prompt": "..."},
]

TEST_SPLIT = [POOL[2], POOL[5]]


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_card():
    """A card that passes every gate this phase checks."""
    return {
        "schema_version": 1,
        "id": "fixture",
        "title": "Fixture card",
        "tier": 2,
        "status": "sealed",
        "created": "2026-09-06",
        "decision": {
            "question": "Ship the new prompt?",
            "owner": "eval lead",
            "outcomes": [
                {"result": "pass", "action": "roll out"},
                {"result": "fail", "action": "hold"},
                {"result": "borderline", "action": "escalate to tier 3"},
            ],
        },
        "domain": {
            "users": "support agents",
            "operating_conditions": "live traffic",
            "harm_pathways": [
                {"id": "hp1", "rank": 1, "severity": "high",
                 "description": "cites an unsupported source"},
            ],
        },
        "constructs": [
            {"id": "c_grounding",
             "definition": "answers are traceable to retrieved context",
             "positive_evidence": ["every factual sentence maps to a chunk"],
             "negative_evidence": ["asserts a figure absent from all chunks"],
             "harm_pathways": ["hp1"]},
        ],
        "claims": [
            {"id": "cl1", "construct": "c_grounding", "statement": "no unsupported facts"},
            {"id": "cl2", "construct": "c_grounding", "statement": "no invented citations"},
        ],
        "evidence_model": [
            {"id": "ev1", "claim": "cl1", "observable": "unsupported sentence count",
             "scoring_rule": "binary", "rubric_ref": "rubrics/grounding.md"},
            {"id": "ev2", "claim": "cl2", "observable": "invented citation count",
             "scoring_rule": "binary", "rubric_ref": "rubrics/grounding.md"},
        ],
        "task_model": [
            {"id": "tm1", "claim": "cl1", "task_family": "answer from 5 docs",
             "conditions": ["retrieval returns nothing relevant"]},
            {"id": "tm2", "claim": "cl2", "task_family": "answer from 5 docs",
             "conditions": ["retrieval returns a near-duplicate"]},
        ],
        "items": {
            "source": "items/pool.jsonl",
            "sampling_frame": "prod logs, stratified by intent",
            "contamination_controls": {
                "canary": "CANARY-fixture-9f3b",
                "date_stamped": True,
                "novel_items": 2,
            },
            "splits": {
                "dev": {"path": "items/dev.jsonl"},
                "test": {"path": "items/test.jsonl", "sealed": True,
                         "sha256": "", "sealed_at": "2026-09-06T10:00:00Z"},
            },
        },
        "grader": {
            "kind": "llm_judge",
            "model": "some-judge",
            "mode": "pairwise",
            "rubric_ref": "rubrics/grounding.md",
            "gold_set": "labels/gold.csv",
            "bias_probes": ["position", "length"],
        },
        "preregistration": {
            "sealed_at": "2026-09-06T10:00:00Z",
            "content_hash": "sha256:" + "0" * 64,
            "protocol": {"prompts_ref": "prompts/v4.md", "seeds": [0, 1, 2],
                         "temperature": 0.0, "elicitation_budget": "3 attempts"},
            "baselines": ["human", "prior_model_v3"],
            "threshold": {"metric": "grounding pass rate",
                          "minimum_interesting_difference": 0.03,
                          "decision_rule": "lower bound of 95% CI > 0.90"},
        },
    }


def write_card(directory, mutate=None, items=None, test_split=None):
    """Write a valid card and its pool into `directory`; return the card's path.

    `mutate` receives the card dict before it is written. `items` and
    `test_split` replace the default rows. The test split's sha256 is computed
    from what is actually written, so Gate 5 passes unless a test breaks it
    deliberately.
    """
    pool_path = os.path.join(directory, "items", "pool.jsonl")
    test_path = os.path.join(directory, "items", "test.jsonl")
    _write_jsonl(pool_path, POOL if items is None else items)
    _write_jsonl(test_path, TEST_SPLIT if test_split is None else test_split)

    card = base_card()
    card["items"]["splits"]["test"]["sha256"] = sha256_of(test_path)
    if mutate is not None:
        mutate(card)

    card_path = os.path.join(directory, "eval-card.json")
    with open(card_path, "w", encoding="utf-8") as handle:
        json.dump(card, handle, indent=2, sort_keys=True)
    return card_path
```

- [ ] **Step 4: Write the loader**

Create `genai-eval/scripts/card/__init__.py`:

```python
"""card — the eval card, and the gates a script can actually check.

The design commitment this package exists to serve: a gate that cannot be
checked mechanically will be rubber-stamped. Six of the SOP's eleven gates are
answerable from the card and its item pool, so they are answered here rather
than asked of a model.

    loader.py   read a card, resolve its paths, validate its structure
    gates.py    one function per mechanical gate
"""

from . import gates, loader

__all__ = ["gates", "loader"]
```

Note: `gates` does not exist until Task 3. For **this task only**, write the import line as `from . import loader` and `__all__ = ["loader"]`; Task 3 widens it.

Create `genai-eval/scripts/card/loader.py`:

```python
"""Read an eval card and check that it is structurally a card at all.

A finding from this module carries `gate=None`. A malformed card has not failed
a gate — it is a card the gates cannot be run against, and saying "Gate 4
failed" about a file missing its `claims` block would send someone looking in
the wrong place.
"""

import json
import os
from dataclasses import dataclass

SCHEMA_VERSIONS = (1,)
TIERS = (1, 2, 3)
STATUSES = ("draft", "designed", "sealed", "qualified", "retired")

REQUIRED_BLOCKS = (
    "schema_version", "tier", "decision", "domain", "constructs", "claims",
    "evidence_model", "task_model", "items", "grader", "preregistration",
)


@dataclass
class Finding:
    """One problem with one card. `gate` is None for structural problems."""

    level: str
    path: str
    message: str
    gate: int = None

    def render(self):
        label = "structure" if self.gate is None else "Gate %d" % self.gate
        return "%s [%s] %s: %s" % (self.level.upper(), label, self.path, self.message)


def resolve(card_path, relative):
    """Resolve a path found inside a card, against the card's own directory.

    Cards and their item pools travel together. Resolving against the process's
    working directory would break the moment anyone validated a card from
    anywhere but its own folder.
    """
    if os.path.isabs(relative):
        return relative
    return os.path.join(os.path.dirname(os.path.abspath(card_path)), relative)


def load_card(path):
    """Parse a card and check its shape. Returns (card, findings)."""
    if not os.path.isfile(path):
        raise ValueError("no such card: %s" % path)
    try:
        with open(path, encoding="utf-8") as handle:
            card = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("%s is not readable JSON: %s" % (path, exc))

    if not isinstance(card, dict):
        raise ValueError(
            "%s parsed as %s; an eval card must be a JSON object"
            % (path, type(card).__name__)
        )

    findings = []
    for block in REQUIRED_BLOCKS:
        if block not in card:
            findings.append(Finding("error", block, "required block is missing"))

    version = card.get("schema_version")
    if version is not None and version not in SCHEMA_VERSIONS:
        findings.append(Finding(
            "error", "schema_version",
            "unknown schema version %r; this validator understands %s"
            % (version, ", ".join(str(v) for v in SCHEMA_VERSIONS)),
        ))

    tier = card.get("tier")
    if tier is not None and tier not in TIERS:
        findings.append(Finding(
            "error", "tier", "tier must be 1, 2 or 3; got %r" % (tier,)))

    status = card.get("status")
    if status is not None and status not in STATUSES:
        findings.append(Finding(
            "error", "status",
            "unknown status %r; expected one of %s" % (status, ", ".join(STATUSES)),
        ))

    return card, findings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_card_loader.py`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add genai-eval/scripts/card/ genai-eval/scripts/tests/card_fixture.py genai-eval/scripts/tests/test_card_loader.py
git commit -m "feat(genai-eval): eval card loader and structural validation"
```

---

### Task 3: Gates 1 and 3 — a named decision, and a falsifiable construct

**Files:**
- Create: `genai-eval/scripts/card/gates.py`
- Create: `genai-eval/scripts/tests/test_gates.py`
- Modify: `genai-eval/scripts/card/__init__.py`

**Interfaces:**
- Consumes: `loader.Finding`, `card_fixture.write_card`.
- Produces:
  - `gates.gate_1_decision(card) -> list[Finding]`
  - `gates.gate_3_falsifiable(card) -> list[Finding]`
  - `gates.ALL` — a list of `(gate_number, callable)` pairs, growing as gates land. Callables taking only `card` are called with one argument; Tasks 5-7 add gates needing the card's path, so the registry entries are `(number, callable, needs_path)` triples.

Gate 1 asks whether a named person owns the decision and whether every outcome has an action. Gate 3 asks whether the construct is falsifiable — whether the card says what evidence would count *against* it. Both are pure dict checks; neither touches a file.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_gates.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: FAIL — `ImportError: cannot import name 'gates' from 'card'`

- [ ] **Step 3: Write the gates**

Create `genai-eval/scripts/card/gates.py`:

```python
"""One function per mechanical gate.

Each takes a card (some also its path) and returns a list of Findings — never
raises, never prints, never stops at the first problem. A gate that dies on the
first fault makes someone fix a card one error per run.

Gates 6, 7, 8, 10 and 11 need a qualification block that nothing writes yet;
they arrive with card mode. The registry at the bottom is the seam.
"""

from .loader import Finding

REQUIRED_OUTCOMES = ("pass", "fail", "borderline")


def _blank(value):
    return not isinstance(value, str) or not value.strip()


def _nonempty_strings(value):
    return isinstance(value, list) and any(
        isinstance(entry, str) and entry.strip() for entry in value
    )


def gate_1_decision(card):
    """Gate 1: is there a named decision-owner and an action for every outcome?

    Without both, the eval is a vanity metric: it will be optimised against and
    then ignored, because nobody was ever going to do anything different on any
    of its results.
    """
    findings = []
    decision = card.get("decision") or {}

    if _blank(decision.get("owner")):
        findings.append(Finding(
            "error", "decision.owner",
            "no named decision-owner; an eval nobody owns is a vanity metric",
            gate=1,
        ))

    outcomes = decision.get("outcomes") or []
    seen = {o.get("result") for o in outcomes if isinstance(o, dict)}
    for required in REQUIRED_OUTCOMES:
        if required not in seen:
            findings.append(Finding(
                "error", "decision.outcomes",
                "no action recorded for the %r outcome" % required,
                gate=1,
            ))

    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict) or _blank(outcome.get("action")):
            findings.append(Finding(
                "error", "decision.outcomes[%d].action" % index,
                "outcome %r has no action" % (
                    outcome.get("result") if isinstance(outcome, dict) else outcome,),
                gate=1,
            ))

    return findings


def gate_3_falsifiable(card):
    """Gate 3: can you state what output would count as evidence *against* the
    construct?

    If not, the construct is not falsifiable and no result can disconfirm it —
    which means every result confirms it, which means it measures nothing.
    """
    findings = []
    for index, construct in enumerate(card.get("constructs") or []):
        if not _nonempty_strings(construct.get("negative_evidence")):
            findings.append(Finding(
                "error", "constructs[%d].negative_evidence" % index,
                "construct %r states nothing that would count against it, so no "
                "result can disconfirm it" % construct.get("id"),
                gate=3,
            ))
    return findings


# (gate number, callable, needs_card_path). Gates 4, 5 and 9 join in later tasks.
ALL = [
    (1, gate_1_decision, False),
    (3, gate_3_falsifiable, False),
]
```

Then widen `genai-eval/scripts/card/__init__.py` to `from . import gates, loader` and `__all__ = ["gates", "loader"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: PASS — `Ran 12 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/card/ genai-eval/scripts/tests/test_gates.py
git commit -m "feat(genai-eval): Gates 1 and 3 — named decision, falsifiable construct"
```

---

### Task 4: Gate 2 — every measure traces to a ranked harm pathway

**Files:**
- Modify: `genai-eval/scripts/card/gates.py`
- Modify: `genai-eval/scripts/tests/test_gates.py`

**Interfaces:**
- Produces: `gates.gate_2_harm_pathways(card) -> list[Finding]`, and its entry in `gates.ALL`.

Gate 2 asks whether each construct traces to a ranked route to harm. Without it you measure what is easy rather than what matters — and the ranking is the part that does the work, because an unranked list of pathways justifies measuring any of them.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_gates.py`, before the `TestGatesDoNotBleed` class:

```python
class TestGate2HarmPathways(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertEqual(run_gate(gates.gate_2_harm_pathways), [])

    def test_a_construct_with_no_pathway_fires(self):
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["constructs"][0].update(harm_pathways=[]),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 2)
        self.assertEqual(findings[0].path, "constructs[0].harm_pathways")

    def test_a_dangling_pathway_reference_fires_naming_the_id(self):
        findings = run_gate(
            gates.gate_2_harm_pathways,
            lambda c: c["constructs"][0].update(harm_pathways=["hp_nope"]),
        )
        self.assertEqual(len(findings), 1)
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

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual(len(findings), 1)
        self.assertIn("rank", findings[0].path)

    def test_an_unreferenced_pathway_is_a_warning_not_an_error(self):
        """Listing a pathway you chose not to measure is honest. It is worth
        surfacing, but it is not a failure."""
        def mutate(card):
            card["domain"]["harm_pathways"].append(
                {"id": "hp2", "rank": 2, "severity": "low", "description": "d"})

        findings = run_gate(gates.gate_2_harm_pathways, mutate)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "warning")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_gates.py -k TestGate2HarmPathways`
Expected: FAIL — `AttributeError: module 'card.gates' has no attribute 'gate_2_harm_pathways'`

- [ ] **Step 3: Write the gate**

Append to `genai-eval/scripts/card/gates.py`, before the `ALL` registry:

```python
def gate_2_harm_pathways(card):
    """Gate 2: is each measure traceable to a ranked harm pathway?

    Without the trace you measure what is easy rather than what matters. The
    *ranking* is what makes the trace mean something — an unranked list
    justifies measuring any pathway on it equally.
    """
    findings = []
    pathways = (card.get("domain") or {}).get("harm_pathways") or []
    by_id = {p.get("id"): p for p in pathways if isinstance(p, dict)}

    ranks = []
    for index, pathway in enumerate(pathways):
        rank = pathway.get("rank") if isinstance(pathway, dict) else None
        if not isinstance(rank, int) or isinstance(rank, bool):
            findings.append(Finding(
                "error", "domain.harm_pathways[%d].rank" % index,
                "pathway %r has no integer rank, so nothing distinguishes it "
                "from any other" % (pathway.get("id") if isinstance(pathway, dict) else pathway,),
                gate=2,
            ))
        else:
            ranks.append((rank, index))

    seen_ranks = {}
    for rank, index in ranks:
        if rank in seen_ranks:
            findings.append(Finding(
                "error", "domain.harm_pathways[%d].rank" % index,
                "rank %d is already used by pathway %d; duplicate ranks are not "
                "a ranking" % (rank, seen_ranks[rank]),
                gate=2,
            ))
        else:
            seen_ranks[rank] = index

    referenced = set()
    for index, construct in enumerate(card.get("constructs") or []):
        listed = construct.get("harm_pathways") or []
        if not listed:
            findings.append(Finding(
                "error", "constructs[%d].harm_pathways" % index,
                "construct %r traces to no harm pathway" % construct.get("id"),
                gate=2,
            ))
        for reference in listed:
            referenced.add(reference)
            if reference not in by_id:
                findings.append(Finding(
                    "error", "constructs[%d].harm_pathways" % index,
                    "construct %r references unknown pathway %r"
                    % (construct.get("id"), reference),
                    gate=2,
                ))

    for index, pathway in enumerate(pathways):
        identifier = pathway.get("id") if isinstance(pathway, dict) else None
        if identifier is not None and identifier not in referenced:
            findings.append(Finding(
                "warning", "domain.harm_pathways[%d]" % index,
                "pathway %r is ranked but no construct measures it" % identifier,
                gate=2,
            ))

    return findings
```

Add `(2, gate_2_harm_pathways, False),` to `ALL`, keeping numeric order.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: PASS — `Ran 19 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/card/gates.py genai-eval/scripts/tests/test_gates.py
git commit -m "feat(genai-eval): Gate 2 — measures trace to ranked harm pathways"
```

---

### Task 5: Gate 4 — the trace matrix

**Files:**
- Modify: `genai-eval/scripts/card/gates.py`
- Modify: `genai-eval/scripts/tests/test_gates.py`

**Interfaces:**
- Produces: `gates.gate_4_trace_matrix(card, card_path) -> list[Finding]`, registered in `gates.ALL` with `needs_path=True`.

This is the gate the whole card format exists for. Every item must map to a claim, every claim must have at least three items, and every claim must map to a construct. It is the one check that reads the item pool off disk.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_gates.py`, before `TestGatesDoNotBleed`:

```python
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
        there, and say so — that is a common state for a card in progress."""
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_gates.py -k TestGate4TraceMatrix`
Expected: FAIL — `AttributeError: module 'card.gates' has no attribute 'gate_4_trace_matrix'`

- [ ] **Step 3: Write the gate**

Add `import json` and `from .loader import Finding, resolve` at the top of `gates.py` (replacing the existing `from .loader import Finding`), then append before `ALL`:

```python
MINIMUM_ITEMS_PER_CLAIM = 3


def _read_pool(path):
    """Read a JSONL item pool. Returns (rows, findings)."""
    rows, findings = [], []
    try:
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    findings.append(Finding(
                        "error", "items.source",
                        "line %d of the item pool is not JSON: %s" % (number, exc),
                        gate=4,
                    ))
    except OSError as exc:
        findings.append(Finding(
            "error", "items.source",
            "cannot read the item pool: %s" % exc, gate=4))
    return rows, findings


def gate_4_trace_matrix(card, card_path):
    """Gate 4: does every item trace to a claim, and every claim to 3+ items?

    This is what makes a score readable at the claim level. Without it the
    number says the system did well overall and cannot say what it did well at,
    which is the difference between a result and a leaderboard entry.
    """
    findings = []
    construct_ids = {c.get("id") for c in card.get("constructs") or []}
    claims = card.get("claims") or []
    claim_ids = {c.get("id") for c in claims}

    for index, claim in enumerate(claims):
        if claim.get("construct") not in construct_ids:
            findings.append(Finding(
                "error", "claims[%d].construct" % index,
                "claim %r references unknown construct %r"
                % (claim.get("id"), claim.get("construct")),
                gate=4,
            ))

    for block in ("evidence_model", "task_model"):
        for index, entry in enumerate(card.get(block) or []):
            if entry.get("claim") not in claim_ids:
                findings.append(Finding(
                    "error", "%s[%d].claim" % (block, index),
                    "%s entry %r references unknown claim %r"
                    % (block, entry.get("id"), entry.get("claim")),
                    gate=4,
                ))

    evidenced = {e.get("claim") for e in card.get("evidence_model") or []}
    tasked = {t.get("claim") for t in card.get("task_model") or []}
    for index, claim in enumerate(claims):
        identifier = claim.get("id")
        if identifier not in evidenced:
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has no evidence model entry, so nothing says what "
                "would be observed to support it" % identifier,
                gate=4,
            ))
        if identifier not in tasked:
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has no task model entry, so nothing elicits it"
                % identifier,
                gate=4,
            ))

    source = (card.get("items") or {}).get("source")
    if not source:
        findings.append(Finding(
            "error", "items.source", "no item pool is named", gate=4))
        return findings

    rows, read_findings = _read_pool(resolve(card_path, source))
    findings.extend(read_findings)

    counts = {}
    for index, row in enumerate(rows):
        claim_id = row.get("claim_id") if isinstance(row, dict) else None
        if claim_id is None:
            findings.append(Finding(
                "error", "items.source",
                "item %r has no claim_id, so it traces to nothing"
                % (row.get("item_id") if isinstance(row, dict) else index),
                gate=4,
            ))
            continue
        if claim_id not in claim_ids:
            findings.append(Finding(
                "error", "items.source",
                "item %r references unknown claim %r"
                % (row.get("item_id"), claim_id),
                gate=4,
            ))
            continue
        counts[claim_id] = counts.get(claim_id, 0) + 1

    for index, claim in enumerate(claims):
        identifier = claim.get("id")
        count = counts.get(identifier, 0)
        if count < MINIMUM_ITEMS_PER_CLAIM:
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has %d items; %d are needed before a score can be "
                "read at the claim level"
                % (identifier, count, MINIMUM_ITEMS_PER_CLAIM),
                gate=4,
            ))

    return findings
```

Add `(4, gate_4_trace_matrix, True),` to `ALL`, in numeric order.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: PASS — `Ran 28 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/card/gates.py genai-eval/scripts/tests/test_gates.py
git commit -m "feat(genai-eval): Gate 4 — the claim-to-item trace matrix"
```

---

### Task 6: Gate 5 — the sealed, uncontaminated test split

**Files:**
- Modify: `genai-eval/scripts/card/gates.py`
- Modify: `genai-eval/scripts/tests/test_gates.py`

**Interfaces:**
- Produces: `gates.gate_5_sealed_split(card, card_path) -> list[Finding]`, registered with `needs_path=True`.

The contamination tripwire. A recorded hash that no longer matches its file means the sealed split changed after sealing, and the whole point of sealing was that it would not.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_gates.py`, before `TestGatesDoNotBleed`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_gates.py -k TestGate5SealedSplit`
Expected: FAIL — `AttributeError: module 'card.gates' has no attribute 'gate_5_sealed_split'`

- [ ] **Step 3: Write the gate**

Add `import hashlib` to `gates.py`'s imports, then append before `ALL`:

```python
def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gate_5_sealed_split(card, card_path):
    """Gate 5: is the test split sealed, and is it still the file that was sealed?

    The hash is taken over raw bytes, not parsed JSON, so reformatting the file
    trips it too. That is deliberate: "same items, different whitespace" is
    indistinguishable from "someone edited the split" without reading the diff,
    and the gate exists precisely to make that visible.

    A mismatch is always an error. A warning here would make the gate
    decorative.
    """
    findings = []
    items = card.get("items") or {}

    canary = (items.get("contamination_controls") or {}).get("canary")
    if _blank(canary):
        findings.append(Finding(
            "error", "items.contamination_controls.canary",
            "no canary string; without one, leakage into a model's training "
            "data cannot be detected later",
            gate=5,
        ))

    split = (items.get("splits") or {}).get("test") or {}

    if split.get("sealed") is not True:
        findings.append(Finding(
            "error", "items.splits.test.sealed",
            "the test split is not marked sealed", gate=5))

    if _blank(split.get("sealed_at")):
        findings.append(Finding(
            "error", "items.splits.test.sealed_at",
            "no seal timestamp, so nothing records when the split was fixed",
            gate=5,
        ))

    recorded = split.get("sha256")
    path = split.get("path")
    if _blank(recorded):
        findings.append(Finding(
            "error", "items.splits.test.sha256",
            "no recorded hash, so the split cannot be shown to be unchanged",
            gate=5,
        ))
    elif _blank(path):
        findings.append(Finding(
            "error", "items.splits.test.path",
            "no test split file is named", gate=5))
    else:
        try:
            actual = _sha256_of(resolve(card_path, path))
        except OSError as exc:
            findings.append(Finding(
                "error", "items.splits.test.path",
                "cannot read the test split: %s" % exc, gate=5))
        else:
            if actual != recorded:
                findings.append(Finding(
                    "error", "items.splits.test.sha256",
                    "the test split has changed since it was sealed (recorded "
                    "%s..., found %s...); every number computed from it "
                    "measures something other than what was sealed"
                    % (recorded[:12], actual[:12]),
                    gate=5,
                ))

    return findings
```

Add `(5, gate_5_sealed_split, True),` to `ALL`, in numeric order.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: PASS — `Ran 36 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/card/gates.py genai-eval/scripts/tests/test_gates.py
git commit -m "feat(genai-eval): Gate 5 — the sealed test split tripwire"
```

---

### Task 7: Gate 9 — the threshold was set before the run

**Files:**
- Modify: `genai-eval/scripts/card/gates.py`
- Modify: `genai-eval/scripts/tests/test_gates.py`

**Interfaces:**
- Produces: `gates.gate_9_preregistration(card) -> list[Finding]`, registered with `needs_path=False`.
- Also produces: `gates.run_all(card, card_path) -> list[Finding]` — runs every registered gate, in numeric order, and returns the concatenated findings.

Gate 9 asks whether the decision threshold was fixed before anyone saw a result. It is the gate that stops the goalposts moving, and the only reason it is checkable at all is that the card records a hash and a timestamp.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_gates.py`, before `TestGatesDoNotBleed`:

```python
class TestGate9Preregistration(unittest.TestCase):
    def test_a_valid_card_passes(self):
        self.assertEqual(run_gate(gates.gate_9_preregistration), [])

    def test_a_missing_content_hash_fires(self):
        findings = run_gate(
            gates.gate_9_preregistration,
            lambda c: c["preregistration"].pop("content_hash"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].gate, 9)
        self.assertEqual(findings[0].path, "preregistration.content_hash")

    def test_a_missing_sealed_at_fires(self):
        findings = run_gate(
            gates.gate_9_preregistration,
            lambda c: c["preregistration"].pop("sealed_at"))
        self.assertEqual(len(findings), 1)

    def test_an_unparseable_timestamp_fires(self):
        findings = run_gate(
            gates.gate_9_preregistration,
            lambda c: c["preregistration"].update(sealed_at="last Tuesday"))
        self.assertEqual(len(findings), 1)
        self.assertIn("sealed_at", findings[0].path)

    def test_a_missing_threshold_fires(self):
        """A preregistration with no decision rule preregisters nothing."""
        findings = run_gate(
            gates.gate_9_preregistration,
            lambda c: c["preregistration"].pop("threshold"))
        self.assertEqual(len(findings), 1)

    def test_a_threshold_without_a_decision_rule_fires(self):
        findings = run_gate(
            gates.gate_9_preregistration,
            lambda c: c["preregistration"]["threshold"].update(decision_rule=""))
        self.assertEqual(len(findings), 1)

    def test_a_result_timestamped_before_the_seal_fires(self):
        """The goalposts moved. A result that predates the threshold it is
        judged against means the threshold was chosen knowing the answer."""
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "2026-09-05T09:00:00Z"}}

        findings = run_gate(gates.gate_9_preregistration, mutate)
        self.assertEqual(len(findings), 1)
        self.assertIn("predates", findings[0].message)

    def test_a_result_after_the_seal_passes(self):
        def mutate(card):
            card["qualification"] = {
                "results": {"computed_at": "2026-09-07T09:00:00Z"}}

        self.assertEqual(run_gate(gates.gate_9_preregistration, mutate), [])


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_gates.py -k TestGate9Preregistration`
Expected: FAIL — `AttributeError: module 'card.gates' has no attribute 'gate_9_preregistration'`

- [ ] **Step 3: Write the gate and the runner**

Add `import datetime` to `gates.py`'s imports, then append before `ALL`:

```python
def _parse_timestamp(value):
    """Parse an ISO 8601 timestamp, tolerating a trailing Z. None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _result_timestamps(card):
    """Every timestamp under `qualification` that looks like a result time."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("computed_at", "run_at", "measured_at"):
                    parsed = _parse_timestamp(value)
                    if parsed is not None:
                        found.append((path + "." + key, parsed))
                else:
                    walk(value, path + "." + key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, "%s[%d]" % (path, index))

    walk(card.get("qualification") or {}, "qualification")
    return found


def gate_9_preregistration(card):
    """Gate 9: was the decision threshold set before the run?

    This is the gate that stops the goalposts moving, and it is checkable only
    because the card records a hash and a timestamp before any result exists.
    Everyone believes they would not move a threshold after seeing the number.
    """
    findings = []
    prereg = card.get("preregistration") or {}

    if _blank(prereg.get("content_hash")):
        findings.append(Finding(
            "error", "preregistration.content_hash",
            "no content hash, so nothing shows the protocol is the one that "
            "was sealed",
            gate=9,
        ))

    sealed_at = _parse_timestamp(prereg.get("sealed_at"))
    if sealed_at is None:
        findings.append(Finding(
            "error", "preregistration.sealed_at",
            "no parseable ISO 8601 seal timestamp; without one, 'before the "
            "run' cannot be established",
            gate=9,
        ))

    threshold = prereg.get("threshold")
    if not isinstance(threshold, dict):
        findings.append(Finding(
            "error", "preregistration.threshold",
            "no threshold; a preregistration without a decision rule "
            "preregisters nothing",
            gate=9,
        ))
    elif _blank(threshold.get("decision_rule")):
        findings.append(Finding(
            "error", "preregistration.threshold.decision_rule",
            "no decision rule, so no result can be said to cross it", gate=9))

    if sealed_at is not None:
        for path, stamp in _result_timestamps(card):
            if stamp < sealed_at:
                findings.append(Finding(
                    "error", path,
                    "result timestamp %s predates the preregistration seal at "
                    "%s; the threshold was set knowing the answer"
                    % (stamp.isoformat(), sealed_at.isoformat()),
                    gate=9,
                ))

    return findings


def run_all(card, card_path):
    """Run every registered gate, in numeric order, and collect the findings."""
    findings = []
    for number, check, needs_path in sorted(ALL, key=lambda entry: entry[0]):
        findings.extend(check(card, card_path) if needs_path else check(card))
    return findings
```

Add `(9, gate_9_preregistration, False),` to `ALL`, in numeric order.

`run_all` may sit either side of `ALL` in the file — Python resolves a module-level name when the function *runs*, not when it is defined, so a `run_all` written above `ALL` still works. Put it at the end of the file for readability; do not reorganise the module on account of the reference.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_gates.py`
Expected: PASS — `Ran 47 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/card/gates.py genai-eval/scripts/tests/test_gates.py
git commit -m "feat(genai-eval): Gate 9 — the preregistration seal"
```

---

### Task 8: The `check_eval_card.py` CLI

**Files:**
- Create: `genai-eval/scripts/check_eval_card.py`
- Create: `genai-eval/scripts/tests/test_check_eval_card.py`

**Interfaces:**
- Produces: `check_eval_card.main(argv=None) -> int`. CLI: `python3 check_eval_card.py CARD.json [--format text|json] [--warnings-as-errors]`. Exit 0 when no error-level findings, 1 when any exist, 2 for an unreadable card.

Exit 2 for an unreadable card is deliberate and different from the calibration CLI's single convention: "this card fails gates" and "this is not a card" are different answers, and a CI job wiring the validator into a pipeline needs to tell them apart.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_check_eval_card.py`:

```python
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
        self.assertTrue(err.strip())

    def test_malformed_json_exits_two(self):
        path = os.path.join(tempfile.mkdtemp(), "eval-card.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        code, _, err = run([path])
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_a_structurally_broken_card_exits_one_not_two(self):
        """It parsed. It is a card with a missing block, which is a finding,
        not an unreadable file."""
        path = write_card(tempfile.mkdtemp(), mutate=lambda c: c.pop("claims"))
        code, out, _ = run([path])
        self.assertEqual(code, 1)
        self.assertIn("structure", out.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_check_eval_card.py`
Expected: FAIL — `FileNotFoundError` on `check_eval_card.py`

- [ ] **Step 3: Write the CLI**

Create `genai-eval/scripts/check_eval_card.py`:

```python
#!/usr/bin/env python3
"""check_eval_card.py — hold an eval card to the gates a script can check.

Six of the SOP's eleven gates are answerable from the card and its item pool:
a named decision-owner with an action per outcome (1), constructs tracing to
ranked harm pathways (2), a falsifiable construct (3), a claim-to-item trace
matrix (4), a sealed and hash-verified test split (5), and a preregistration
sealed before any result (9). This script answers them, so a model is never
asked to.

It behaves like a linter, not an assertion: every violation in one pass, each
with a JSON path and a gate number. A card gets fixed once, not once per run.

Usage
-----
    python3 check_eval_card.py eval-card.json
    python3 check_eval_card.py eval-card.json --format json
    python3 check_eval_card.py eval-card.json --warnings-as-errors

Exit codes
----------
    0  no error-level findings
    1  at least one error-level finding, or a structural problem
    2  the card could not be read at all — not the same answer as "it failed"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card import gates, loader


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check an eval card against the gates a script can answer, "
        "and report every violation in one pass."
    )
    parser.add_argument("card", help="Path to the eval card JSON.")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text).")
    parser.add_argument(
        "--warnings-as-errors", action="store_true",
        help="Exit non-zero when only warnings were found.")
    args = parser.parse_args(argv)

    try:
        card, findings = loader.load_card(args.card)
    except ValueError as exc:
        print("check_eval_card: %s" % exc, file=sys.stderr)
        return 2

    findings = list(findings) + gates.run_all(card, args.card)
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]

    if args.format == "json":
        print(json.dumps({
            "card": args.card,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "findings": [
                {"gate": f.gate, "level": f.level, "path": f.path,
                 "message": f.message}
                for f in findings
            ],
        }, indent=2))
    else:
        if not findings:
            print("%s: no findings. Gates 1, 2, 3, 4, 5 and 9 pass."
                  % args.card)
        else:
            print("%s: %d error(s), %d warning(s)\n"
                  % (args.card, len(errors), len(warnings)))
            for finding in findings:
                print("  " + finding.render())
            print("\nGates 6, 7, 8, 10 and 11 need a qualification block and "
                  "are not checked here.")

    return 1 if errors or (warnings and args.warnings_as_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"`
Expected: PASS — 10 new CLI tests. Note the package total before this task, add 10, and check you land on it. Do not trust an absolute figure written in this plan: Phase 1B's counts went stale twice when fix rounds added tests after the plan was written, and both times an implementer was right to flag the mismatch rather than assume it had done something wrong.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/check_eval_card.py genai-eval/scripts/tests/test_check_eval_card.py
git commit -m "feat(genai-eval): check_eval_card.py, a linter for the design gates"
```

---

### Task 9: The worked `rag-grounding` card

**Files:**
- Create: `genai-eval/examples/rag-grounding/eval-card.json`
- Create: `genai-eval/examples/rag-grounding/items/pool.jsonl`
- Create: `genai-eval/examples/rag-grounding/items/test.jsonl`
- Create: `genai-eval/examples/rag-grounding/README.md`

**Interfaces:**
- Consumes: `check_eval_card.py` from Task 8, and the schema from Task 1.
- Produces: a complete tier-2 card that passes every gate, and a README documenting the validator's real output.

The same rule as the judge-calibration example: **run the tool and document what it says, never what you expect it to say.** People copy the artifacts in examples.

- [ ] **Step 1: Write the card and its item pool**

Build a genuine tier-2 card for a retrieval-grounding eval: does a RAG assistant assert facts absent from its retrieved context? Give it two constructs (grounding, and citation accuracy), two ranked harm pathways, three or more claims, and an item pool of at least 12 items — at least three per claim, since Gate 4 requires it — with realistic prompts. Include a sealed test split of 4 items.

Compute the split's real sha256 and put it in the card:

```bash
python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  genai-eval/examples/rag-grounding/items/test.jsonl
```

- [ ] **Step 2: Run the validator and read what it says**

Run:

```bash
python3 genai-eval/scripts/check_eval_card.py genai-eval/examples/rag-grounding/eval-card.json
```

It must exit 0. If any gate fires, **fix the card, not the gate** — the example exists to show a card that passes, and a gate that lets a bad card through is worse than a card that needs another field.

- [ ] **Step 3: Write the README around the real output**

Create `genai-eval/examples/rag-grounding/README.md` containing: what the eval is for and what decision it serves; the validator command in a fenced `bash` block; the real output it produced; a short walk through the trace matrix showing how one item maps to a claim, that claim to a construct, and that construct to a ranked harm pathway; and a section on what the card does **not** yet carry — the qualification block, and therefore Gates 6, 7, 8, 10 and 11.

Then demonstrate the tripwire, because it is the most instructive thing in the card. Append a line to `items/test.jsonl`, re-run the validator, and paste the real Gate 5 failure it produces. Restore the file afterwards and confirm the validator exits 0 again.

- [ ] **Step 4: Verify the documented commands both behave as documented**

Run the passing command and confirm exit 0. Then re-run the tamper demonstration and confirm the Gate 5 message matches what the README shows, character for character.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/examples/rag-grounding/
git commit -m "docs(genai-eval): worked rag-grounding eval card"
```

---

### Task 10: The `eval-design` SKILL.md

**Files:**
- Create: `genai-eval/skills/eval-design/SKILL.md`
- Modify: `genai-eval/skills/eval-qualify/SKILL.md`
- Modify: `docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`

**Interfaces:**
- Consumes: the schema (Task 1), the validator (Task 8), the worked card (Task 9).
- Produces: the skill that walks someone from "we should evaluate this" to a card that passes the validator.

Follow the house structure every skill in this repo uses: YAML frontmatter with `name` and `description`, a short framing paragraph, "When to use", "When NOT to use", then numbered process steps. Read `genai-eval/skills/eval-qualify/SKILL.md` and `improvement-plan/skills/improvement-plan/SKILL.md` first and match their register.

- [ ] **Step 1: Write the frontmatter**

Use this verbatim — it decides whether the skill fires:

```markdown
---
name: eval-design
description: Design a GenAI evaluation before running it — name the decision it serves, define a falsifiable construct, operationalise it into claims, evidence and tasks, build a contamination-controlled item pool, and seal a preregistered threshold. Use when the user asks to "design an eval", "build an eval set", "how should I evaluate X", "what should I measure", "set up an LLM judge", "write a rubric", or is about to compare models or prompts with no protocol. Produces an eval-card.json that check_eval_card.py can hold to six gates. Not for interpreting results you already have — that is eval-qualify.
---
```

- [ ] **Step 2: Write "When to use" and "When NOT to use"**

NOT to use: interpreting results that already exist (that is `eval-qualify`); auditing someone else's published benchmark with no access to its items; and any case where the user cannot name a decision the eval serves — say so plainly rather than proceeding, because Gate 1 will fail and the eval would be optimised against and then ignored.

- [ ] **Step 3: Write the tier routing step**

Per spec §3.3, the skill states its tier before anything else and lists which SOP steps it runs and skips:

| Tier | Trigger | Steps this skill runs |
|---|---|---|
| 1 — daily regression | Catch breakage | 1, 5, 6 |
| 2 — per release | Compare options | + 3, 4 |
| 3 — sign-off / external claim | Defend a claim | + 2 (all) |

- [ ] **Step 4: Write the process steps**

Six numbered steps, each producing a specific part of the card:

1. **Name the decision** and the action for every outcome, including borderline. If nobody owns it, stop and say so.
2. **Model the domain and rank the harm pathways.** Ranking is the work; an unranked list justifies measuring anything.
3. **Define the construct, and say what would count against it.** Write the definition so two annotators would classify the same output the same way, and require the negative evidence before moving on — a construct with nothing that could disconfirm it measures nothing.
4. **Operationalise into claims, evidence and tasks**, then build the trace matrix. Every claim needs at least three items or its score cannot be read at the claim level.
5. **Build the item pool** with a stated sampling frame and contamination controls: a canary string, date-stamping, novel items, and a sealed test split whose hash goes in the card.
6. **Preregister**: fix prompts, seeds, temperature, elicitation budget, baselines and the decision threshold, then seal them with a timestamp and a content hash — before any result exists.

Each step must say which card fields it fills and which gate reads them.

- [ ] **Step 5: Write the validation and handoff sections**

The skill runs `check_eval_card.py` against the card it produced and reports the real output — it does not assert the card is good. Then: hand off to `eval-qualify` once results exist, noting that card mode is not built yet so `eval-qualify` currently runs in bare mode on a labels CSV.

- [ ] **Step 6: Fix the spec's Gate 6 ambiguity, and eval-qualify's cross-reference**

The spec's §3.3 tier table assigns SOP step 6 ("design and calibrate the grader") to `eval-design`, while Gate 6 ("does judge-human agreement reach the human-human floor?") is measured by `eval-qualify` — `eval-design` runs before any results exist and cannot take that measurement. Phase 1B added a clarifying note inside `eval-qualify/SKILL.md`; make it authoritative.

In the spec's §3.3, add a sentence directly beneath the tier table: **the numbered SOP steps and the numbered gates are different sequences that happen to share numbers.** Step 6 is design work owned by `eval-design`; Gate 6 is a measurement owned by `eval-qualify` and taken on every run at every tier. Then check `eval-qualify/SKILL.md`'s existing note agrees with that wording and does not contradict the new `eval-design` skill.

- [ ] **Step 7: Verify the skill file parses**

Run:

```bash
python3 -c "t=open('genai-eval/skills/eval-design/SKILL.md',encoding='utf-8').read(); assert t.startswith('---'); fm=t[3:t.index('---',3)]; assert 'name: eval-design' in fm; assert 'description:' in fm; print('frontmatter OK,', len(t.split()), 'words')"
```

Expected: `frontmatter OK, <n> words`. Compare `<n>` against the other skills in this repo — `eval-qualify` is about 2400 words, `improvement-plan` about 2500, `microworld` about 1050 — and stay inside that range.

- [ ] **Step 8: Commit**

```bash
git add genai-eval/skills/ docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md
git commit -m "feat(genai-eval): eval-design skill, and settle which skill owns Gate 6"
```

---

### Task 11: Document the second skill and guard it in CI

**Files:**
- Modify: `genai-eval/README.md`
- Modify: `README.md`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `genai-eval/.claude-plugin/plugin.json`
- Modify: `.github/workflows/genai-eval-tests.yml`

**Interfaces:**
- Consumes: everything from Tasks 1-10.
- Produces: a plugin whose documentation describes two skills, and CI that fails if the card gates stop working.

Phase 1B's manifest deliberately said `eval-design` was "planned, not yet built". It is built now, so every description changes — and the same honesty rule applies: describe what ships, not what will.

- [ ] **Step 1: Update the plugin README**

In `genai-eval/README.md`, add an `eval-design` section covering what it produces, the six gates the validator checks, and the validator command against the worked card. Update the honesty rules with one more: **a gate that cannot be checked mechanically will be rubber-stamped, so six of them are checked by a script rather than asked of a model.** State plainly that Gates 6, 7, 8, 10 and 11 need a qualification block that is not built yet.

- [ ] **Step 2: Update the root README**

Add `eval-design` to the `genai-eval` paragraph, add the new files to the "What's inside" tree, and add a "Try the card validator directly" section matching the shape of the existing three:

````markdown
## Try the card validator directly

```bash
python3 genai-eval/scripts/check_eval_card.py \
  genai-eval/examples/rag-grounding/eval-card.json
```

It reports every gate violation in one pass, each with a JSON path and a gate
number. `--format json` for machine-readable output. Standard library only.
````

- [ ] **Step 3: Update both manifests**

In `.claude-plugin/marketplace.json` and `genai-eval/.claude-plugin/plugin.json`, rewrite the `description` to cover both skills. Remove the "eval-design and the machine-readable eval card are planned, not yet built" clause from the plugin manifest, and replace it with an accurate note about what remains: the qualification block and the gates that need it.

- [ ] **Step 4: Add a CI gate for the validator**

In `.github/workflows/genai-eval-tests.yml`, add two steps after the existing calibration smoke check. The first must pass; the second must fail, proving the tripwire actually trips:

```yaml
      - name: Verify the worked card passes every checkable gate
        run: |
          set -euo pipefail
          python3 genai-eval/scripts/check_eval_card.py \
            genai-eval/examples/rag-grounding/eval-card.json

      - name: Verify a tampered test split fails Gate 5
        run: |
          set -euo pipefail
          cp genai-eval/examples/rag-grounding/items/test.jsonl /tmp/test.jsonl.bak
          echo '{"item_id": "tamper", "claim_id": "cl1"}' \
            >> genai-eval/examples/rag-grounding/items/test.jsonl
          if python3 genai-eval/scripts/check_eval_card.py \
               genai-eval/examples/rag-grounding/eval-card.json > /tmp/out.txt; then
            echo "Gate 5 did not fire on a tampered split" >&2
            exit 1
          fi
          grep -q "Gate 5" /tmp/out.txt
          cp /tmp/test.jsonl.bak genai-eval/examples/rag-grounding/items/test.jsonl
```

A CI step that only proves the happy path would let the tripwire rot silently — which is the failure this whole phase exists to prevent, applied to itself.

- [ ] **Step 5: Verify everything**

Run:

```bash
python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"
python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print([p['name'] for p in d['plugins']])"
python3 genai-eval/scripts/check_eval_card.py genai-eval/examples/rag-grounding/eval-card.json
```

All three must succeed. Report the real test total.

- [ ] **Step 6: Commit**

```bash
git add genai-eval/README.md README.md .claude-plugin/marketplace.json genai-eval/.claude-plugin/plugin.json .github/workflows/genai-eval-tests.yml
git commit -m "docs(genai-eval): document eval-design and guard the gates in CI"
```

---

## Done when

- `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"` is green.
- `python3 genai-eval/scripts/check_eval_card.py genai-eval/examples/rag-grounding/eval-card.json` exits 0.
- Appending a line to that card's test split makes it exit 1 with a Gate 5 finding, and CI proves it.
- A card broken in several places reports every failure in one run, not the first.
- Both manifests and both READMEs describe two skills, and neither claims a qualification block exists.

## Deferred

**To Phase 2B (recommended before Phase 3):** card mode for `eval-qualify` — reading a card, running the existing `calibration/` analysis against its item pool, appending the `qualification` block, and adding Gates 6, 7, 8, 10 and 11 to the validator. Phase 3's renderer depends on the block existing.

**To the hardening plan:** the items listed at the end of the Phase 1A plan, plus those from Phase 1B — chiefly that `calibration.analysis._alpha_with_ci` still conflates "this data cannot support the statistic" with "you asked for something impossible", which the Phase 1B CLI guards against for today's only route but does not fix; and that `--categories` accepts a list with duplicate entries at the `evalstats` level, silently collapsing a scale slot.

**Inserted during execution, and completed on this branch:** two tasks the plan did not contain. **8b** made every string the tools print pure ASCII and added a checker that fails if another non-ASCII character appears in a shipped module, after it emerged that the Phase 1B ruling on this had checked cp1252 only: U+2014 also fails on cp850 and cp437, which are default console codepages on many Windows installs. **8c** stopped both CLIs crashing on a character the console cannot encode, by setting `errors="backslashreplace"` on stdout and stderr — the text inside a card belongs to whoever wrote it, and an em dash in a construct name was enough to end a validation run in a traceback. 8b closes the half we control; 8c closes the half we do not.

**To the hardening plan, found while writing Task 9:** nothing in the validator checks that the paths a card names actually resolve. A card can point `grader.rubric_ref`, `grader.gold_set` and `preregistration.protocol.prompts_ref` at files that do not exist and pass every gate. No SOP gate maps to this, which is why it is not a gate here, but Task 9's brief had to tell an author by hand to ship the files their example card names — and the fixture carried exactly that defect until Task 6 repaired it.

**To the hardening plan, found during 8c:** `calibration/loader.py` reads a labels CSV with `encoding="utf-8"` and nothing else. A CSV saved as cp1252, which is what Excel on a Western Windows machine produces by default, fails to load if it contains any accented character. It fails *gracefully*, exiting 1 with `calibrate: 'utf-8' codec can't decode byte 0xeb in position 32: invalid continuation byte`, so this is not a crash; it is a cryptic message for an extremely ordinary input. The fix worth having is either an `--encoding` flag or a message that names the remedy, and both are feature decisions rather than defect repairs, which is why this is recorded rather than done.

**The next thing to fix, and it is the plugin's own thesis again:** Gate 6's verdict is a bare point-estimate comparison. `calibration/analysis.py` sets `below_ceiling` when `judge_human["alpha"] < human_human["alpha"]` and nothing else, and the report then states flatly that "the judge falls below the ceiling ... so automating this rubric costs measurable accuracy". On the `rag-grounding` gold set at ordinal level that verdict rests on a gap of **0.029** between 0.865 and 0.894, with 95% intervals of [0.541, 1.000] and [0.611, 1.000] that overlap almost entirely. The spec says Gate 10 applies its decision rule to the interval rather than the point estimate; Gate 6's verdict does the opposite, in a tool whose stated purpose is to refuse rather than overclaim.

This is left for a decision rather than fixed here, because the fix is a methodological choice and not a repair. Comparing whether the two intervals overlap is the cheap option and is conservative to the point of being misleading — overlapping intervals do not imply the difference is not real. The correct instrument already exists in this package: `evalstats.agreement.paired_bootstrap_diff` resamples the *difference* by item, so the question becomes whether that difference's interval includes zero. Either way it needs a third verdict state meaning "this data cannot tell the judge and the humans apart", which is a new thing for the report to say and a new thing for `eval-qualify` to explain.

**Still needing sources, not code:** spec §7's published worked examples — Krippendorff's canonical dataset and a textbook Fleiss example asserted against their published constants. Every fixture in this package is hand-derived.
