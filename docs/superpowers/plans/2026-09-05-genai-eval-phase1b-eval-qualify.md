# genai-eval Phase 1B — the `eval-qualify` skill surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 1A statistics package into something a person can actually run — a CSV of judge scores and human labels goes in, a calibration report with confidence intervals and an honest limits section comes out — and ship it as the `eval-qualify` skill.

**Architecture:** A new `genai-eval/scripts/calibration/` package holding the three things `evalstats/` is forbidden to do: `loader.py` reads a CSV and reports which columns it found and what their absence disables; `analysis.py` decides which statistics the available columns support and runs them; `report.py` renders the result as markdown. A thin `calibrate.py` CLI wires them together. The `eval-qualify` SKILL.md drives the whole thing and supplies the judgement the scripts deliberately do not — naming error clusters, deciding whether a judge is fit for its decision.

**Tech Stack:** Python 3.9+, standard library only. `unittest`. GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`](../specs/2026-09-05-genai-eval-plugin-design.md) — sections 3.4 (bare mode), 4.3, 4.4, 4.5, 6, 9.

**Builds on:** [`2026-09-05-genai-eval-phase1a-evalstats.md`](2026-09-05-genai-eval-phase1a-evalstats.md), merged as PR #12. That phase delivered `evalstats/` with 140 tests.

## Global Constraints

- **Standard library only.** No pip install step, ever. No numpy, scipy, pandas, or PyYAML.
- **Python floor is 3.9.** CI runs a matrix over `["3.9", "3.x"]`.
- **`evalstats/` stays pure.** No file I/O and no printing inside it — that rule is why `calibration/` exists. All reading, writing and formatting lives in the new package.
- **Every function returning a number needs a known-answer test**, with the producing arithmetic in the test docstring. Functions returning structures need an exact-structure test, not a "did it run" smoke test.
- **Degenerate input raises `ValueError` or returns `None`; it never returns a plausible-looking number.**
- **The report must state what it cannot support.** A single human rater means no agreement ceiling exists; the report says so in its own section rather than omitting the comparison silently. This is the spec's central behavioural requirement for bare mode and the reason the phase exists.
- **Scripts count and cluster; the skill interprets.** `analysis.py` produces disagreement clusters as counts; naming what each cluster means is SKILL.md's job. Do not put category naming in Python.

## Scope note

Phase 1A's final review deferred fifteen findings. Two are folded in here because this phase's deliverables need them — Task 1 (explicit ordinal ordering, which the loader needs for word-labelled rubrics) and Task 8 Step 5 (the undefined-value contract table the report renderer reads). The remaining eleven — a shared rectangular-validation helper, the corrected rest-score point-biserial inside `flag_items`, a Jacobi non-convergence signal, `discordant_counts` truthiness, mixed-type nominal alpha, percentile-interval deduplication, and assorted cosmetics — are independent quality work with no dependency on this phase and belong in a separate hardening plan.

## File structure

```
genai-eval/
├── README.md                          # NEW — plugin README, house pattern
├── scripts/
│   ├── evalstats/
│   │   ├── __init__.py                # MODIFY — undefined-value contract table
│   │   └── agreement.py               # MODIFY — categories= parameter
│   ├── calibration/                   # NEW package — everything evalstats may not do
│   │   ├── __init__.py
│   │   ├── loader.py                  # CSV -> CalibrationData, column detection
│   │   ├── analysis.py                # CalibrationData -> results, no-ceiling guard
│   │   └── report.py                  # results -> markdown
│   ├── calibrate.py                   # NEW — the CLI
│   └── tests/
│       ├── test_loader.py             # NEW
│       ├── test_analysis.py           # NEW
│       ├── test_report.py             # NEW
│       └── test_calibrate.py          # NEW — CLI end to end
├── examples/judge-calibration/
│   ├── labels.csv                     # NEW
│   └── README.md                      # NEW
└── skills/eval-qualify/
    └── SKILL.md                       # NEW
.claude-plugin/marketplace.json        # MODIFY — register genai-eval
README.md                              # MODIFY — root README, three places
```

---

### Task 1: Explicit ordinal category ordering

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Consumes: `agreement._coincidence(units)`, `agreement.krippendorff_alpha(units, level)`, `agreement.weighted_kappa(a, b, weights)` from Phase 1A.
- Produces: `agreement.krippendorff_alpha(units, level="nominal", categories=None)` and `agreement.weighted_kappa(a, b, weights="linear", categories=None)`. When `categories` is a sequence, it is the authoritative scale order and any observed rating outside it raises `ValueError`. When `None`, behaviour is exactly as before. `agreement._coincidence(units, categories=None)` gains the same parameter.

Phase 1A's review found that ordinal scales take their order from `sorted(values)`, so `low`/`medium`/`high` sorts alphabetically to `high, low, medium` and produces a confident wrong number. Docstring caveats were added; this is the durable fix, and the CSV loader in Task 2 needs it because word-labelled rubrics are the common real case.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`:

```python
class TestExplicitCategories(unittest.TestCase):
    """Word-labelled ordinal scales must give the same answer as their numeric
    encoding once the order is stated."""

    NUMERIC = [[1, 1], [2, 2], [1, 2], [3, 3]]
    WORDS = [["low", "low"], ["medium", "medium"], ["low", "medium"], ["high", "high"]]
    ORDER = ["low", "medium", "high"]

    def test_ordinal_words_match_their_numeric_encoding(self):
        """The numeric fixture is pinned at 0.79 by TestKrippendorffLevels. The
        word fixture is the same data with labels substituted, so stating the
        order must reproduce that number exactly."""
        got = agreement.krippendorff_alpha(
            self.WORDS, level="ordinal", categories=self.ORDER
        )
        self.assertAlmostEqual(got, 0.79, places=10)

    def test_without_categories_words_give_a_different_wrong_answer(self):
        """Documents the trap: sorted() puts 'high' first, so the scale is
        scrambled and the number is confidently wrong rather than an error."""
        scrambled = agreement.krippendorff_alpha(self.WORDS, level="ordinal")
        self.assertNotAlmostEqual(scrambled, 0.79, places=6)

    def test_interval_words_are_rejected(self):
        """Stating an order does not make labels numeric."""
        with self.assertRaises(TypeError):
            agreement.krippendorff_alpha(
                self.WORDS, level="interval", categories=self.ORDER
            )

    def test_rating_outside_the_stated_categories_raises(self):
        units = [["low", "medium"], ["low", "unheard-of"]]
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha(
                units, level="ordinal", categories=self.ORDER
            )

    def test_categories_none_preserves_existing_behaviour(self):
        """Regression guard for every caller that does not pass categories."""
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(self.NUMERIC, level="ordinal"),
            agreement.krippendorff_alpha(
                self.NUMERIC, level="ordinal", categories=None
            ),
            places=12,
        )

    def test_weighted_kappa_honours_stated_order(self):
        """Same data twice: once labelled, once as 1/2/3. Weighted kappa must
        not care which, given the order."""
        a_words = ["low", "medium", "high", "low", "high"]
        b_words = ["low", "high", "high", "medium", "high"]
        a_nums = [1, 2, 3, 1, 3]
        b_nums = [1, 3, 3, 2, 3]
        self.assertAlmostEqual(
            agreement.weighted_kappa(a_words, b_words, categories=self.ORDER),
            agreement.weighted_kappa(a_nums, b_nums),
            places=12,
        )

    def test_weighted_kappa_rejects_unknown_rating(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa(
                ["low", "surprise"], ["low", "low"], categories=self.ORDER
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestExplicitCategories`
Expected: FAIL — `TypeError: krippendorff_alpha() got an unexpected keyword argument 'categories'`

- [ ] **Step 3: Write the implementation**

In `genai-eval/scripts/evalstats/agreement.py`, change `_coincidence`'s signature and its value-list construction:

```python
def _coincidence(units, categories=None):
```

Replace the line that reads `values = sorted({v for unit in pairable for v in unit})` with:

```python
    observed = {v for unit in pairable for v in unit}
    if categories is None:
        values = sorted(observed)
    else:
        values = list(categories)
        unknown = observed - set(values)
        if unknown:
            raise ValueError(
                "ratings not present in the supplied categories: %s"
                % ", ".join(sorted(str(v) for v in unknown))
            )
```

Change `krippendorff_alpha`'s signature to `def krippendorff_alpha(units, level="nominal", categories=None):` and its call to `matrix, values, marginals, total = _coincidence(units, categories)`.

Add to its docstring, replacing the CAVEAT paragraph added in Phase 1A's fix wave:

```
    CAVEAT: ordinal and interval levels need a scale order. By default that
    order comes from sorting the rating values, which is right for 1/2/3 and
    wrong for word labels — sorted(["low", "medium", "high"]) is
    ["high", "low", "medium"], and the resulting alpha is confidently wrong
    rather than an error. Pass `categories` to state the order explicitly:
    krippendorff_alpha(units, level="ordinal", categories=["low", "medium", "high"]).
    Any rating not in that list raises.
```

Change `weighted_kappa`'s signature to `def weighted_kappa(a, b, weights="linear", categories=None):` and replace its `categories = sorted(set(a) | set(b))` line with:

```python
    observed = set(a) | set(b)
    if categories is None:
        scale = sorted(observed)
    else:
        scale = list(categories)
        unknown = observed - set(scale)
        if unknown:
            raise ValueError(
                "ratings not present in the supplied categories: %s"
                % ", ".join(sorted(str(v) for v in unknown))
            )
```

Then rename the local uses: `k = len(scale)` and `index = {c: i for i, c in enumerate(scale)}`. Update its CAVEAT paragraph the same way, pointing at the `categories` parameter.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — the file's count rises by exactly 7. Note the existing total, add 7, and check you land on it; do not take the number from this plan, which was written before Phase 1A's fix wave settled the per-file split.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): explicit category order for ordinal scales"
```

---

### Task 2: The CSV loader and column detection

**Files:**
- Create: `genai-eval/scripts/calibration/__init__.py`
- Create: `genai-eval/scripts/calibration/loader.py`
- Create: `genai-eval/scripts/tests/test_loader.py`

**Interfaces:**
- Produces:
  - `loader.CalibrationData` — a dataclass with fields `item_ids` (list or None), `judge_column` (str), `judge_scores` (list), `human_columns` (dict of column name to list of values), `lengths` (list or None), `generators` (list or None), `numeric` (dict of column name to bool), `notes` (list of str), `n` (int).
  - `loader.load_labels(path, judge=None, humans=None, item_id=None, length=None, generator=None) -> CalibrationData`. Raises `ValueError` for a missing file column, no detectable judge column, no detectable human column, an empty file, or ragged rows.
  - `loader.detect_columns(fieldnames) -> dict` — the name heuristics, exposed so they can be tested without a file.

The minimum contract is two columns: one judge score and one human label. Every other column is optional and unlocks part of the analysis, so the loader's real job is to say what it found and what each absence disables. `notes` carries those statements and the report prints them verbatim.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_loader.py`:

```python
#!/usr/bin/env python3
"""Tests for calibration.loader. Run directly: python3 test_loader.py"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import loader

MINIMAL = "judge,human\n5,5\n4,3\n2,2\n"

FULL = (
    "item_id,human_a,human_b,judge,response_chars,generator\n"
    "i1,5,5,5,120,gpt-x\n"
    "i2,4,4,5,340,other\n"
    "i3,3,3,3,95,gpt-x\n"
    "i4,5,4,5,410,other\n"
)


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


class TestDetectColumns(unittest.TestCase):
    def test_detects_by_name_fragment(self):
        found = loader.detect_columns(
            ["item_id", "human_a", "human_b", "judge", "response_chars", "generator"]
        )
        self.assertEqual(found["judge"], "judge")
        self.assertEqual(found["humans"], ["human_a", "human_b"])
        self.assertEqual(found["item_id"], "item_id")
        self.assertEqual(found["length"], "response_chars")
        self.assertEqual(found["generator"], "generator")

    def test_recognises_common_synonyms(self):
        found = loader.detect_columns(["id", "gold_label", "llm_score", "n_tokens"])
        self.assertEqual(found["judge"], "llm_score")
        self.assertEqual(found["humans"], ["gold_label"])
        self.assertEqual(found["item_id"], "id")
        self.assertEqual(found["length"], "n_tokens")

    def test_reports_absence_rather_than_guessing(self):
        found = loader.detect_columns(["alpha", "beta"])
        self.assertIsNone(found["judge"])
        self.assertEqual(found["humans"], [])

    def test_a_column_is_claimed_once(self):
        """'human_judge' must not count as both. Judge wins, because the judge
        column is the one the analysis cannot proceed without."""
        found = loader.detect_columns(["human_judge", "gold"])
        self.assertEqual(found["judge"], "human_judge")
        self.assertEqual(found["humans"], ["gold"])


class TestLoadMinimal(unittest.TestCase):
    def test_two_columns_are_enough(self):
        data = loader.load_labels(write_csv(MINIMAL))
        self.assertEqual(data.judge_column, "judge")
        self.assertEqual(data.judge_scores, [5.0, 4.0, 2.0])
        self.assertEqual(list(data.human_columns), ["human"])
        self.assertEqual(data.human_columns["human"], [5.0, 3.0, 2.0])
        self.assertEqual(data.n, 3)
        self.assertIsNone(data.item_ids)

    def test_single_rater_is_noted_not_hidden(self):
        data = loader.load_labels(write_csv(MINIMAL))
        self.assertTrue(
            any("one human rater" in note for note in data.notes),
            data.notes,
        )

    def test_absent_optional_columns_are_each_noted(self):
        data = loader.load_labels(write_csv(MINIMAL))
        joined = " ".join(data.notes)
        self.assertIn("length", joined)
        self.assertIn("item id", joined)


class TestLoadFull(unittest.TestCase):
    def setUp(self):
        self.data = loader.load_labels(write_csv(FULL))

    def test_reads_every_optional_column(self):
        self.assertEqual(self.data.item_ids, ["i1", "i2", "i3", "i4"])
        self.assertEqual(list(self.data.human_columns), ["human_a", "human_b"])
        self.assertEqual(self.data.lengths, [120.0, 340.0, 95.0, 410.0])
        self.assertEqual(self.data.generators, ["gpt-x", "other", "gpt-x", "other"])

    def test_two_raters_means_no_ceiling_note(self):
        self.assertFalse(
            any("one human rater" in note for note in self.data.notes),
            self.data.notes,
        )

    def test_numeric_columns_are_marked(self):
        self.assertTrue(self.data.numeric["judge"])
        self.assertTrue(self.data.numeric["human_a"])


class TestCoercionAndMissing(unittest.TestCase):
    def test_word_labels_stay_strings(self):
        data = loader.load_labels(write_csv("judge,human\ngood,good\nfair,poor\n"))
        self.assertEqual(data.judge_scores, ["good", "fair"])
        self.assertFalse(data.numeric["judge"])

    def test_a_single_non_numeric_value_makes_the_whole_column_text(self):
        """Mixing floats and strings in one column would break every statistic
        downstream, so coercion is all-or-nothing per column."""
        data = loader.load_labels(write_csv("judge,human\n5,5\nn/a,4\n"))
        self.assertEqual(data.judge_scores, ["5", "n/a"])
        self.assertFalse(data.numeric["judge"])

    def test_blank_cells_become_none(self):
        data = loader.load_labels(
            write_csv("judge,human_a,human_b\n5,5,\n4,,4\n")
        )
        self.assertEqual(data.human_columns["human_a"], [5.0, None])
        self.assertEqual(data.human_columns["human_b"], [None, 4.0])

    def test_blanks_do_not_stop_numeric_coercion(self):
        data = loader.load_labels(write_csv("judge,human\n5,5\n,4\n"))
        self.assertTrue(data.numeric["judge"])


class TestOverridesAndErrors(unittest.TestCase):
    def test_explicit_columns_override_detection(self):
        data = loader.load_labels(
            write_csv("alpha,beta\n5,4\n3,3\n"), judge="alpha", humans=["beta"]
        )
        self.assertEqual(data.judge_column, "alpha")
        self.assertEqual(list(data.human_columns), ["beta"])

    def test_named_column_that_does_not_exist_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv(MINIMAL), judge="nope")

    def test_undetectable_judge_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("alpha,beta\n1,2\n"))

    def test_undetectable_human_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,notes\n5,hello\n"))

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,human\n"))

    def test_ragged_rows_raise(self):
        with self.assertRaises(ValueError):
            loader.load_labels(write_csv("judge,human\n5,5\n4\n"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_loader.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'calibration'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/calibration/__init__.py`. `analysis` and `report` do not exist yet — they arrive in Tasks 3 and 7 — so this file binds only `loader` for now, and Task 8 Step 4 widens it:

```python
"""calibration — everything evalstats is forbidden to do.

evalstats computes numbers and raises; it never touches a file or prints. This
package is where reading, deciding what to run, and formatting live:

    loader.py    a CSV becomes a CalibrationData, and says what it did not find
    analysis.py  available columns decide which statistics are defensible
    report.py    results become markdown a person reads
"""

from . import loader

__all__ = ["loader"]
```

Create `genai-eval/scripts/calibration/loader.py`:

```python
"""Read a labels CSV into the structure the analysis needs.

The minimum contract is two columns: one judge score and one human label per
row. Everything else is optional and unlocks part of the analysis, so this
module's real job is not parsing — it is saying plainly what it found and what
each absence costs. Those statements travel in `notes` and the report prints
them verbatim, because a reader who does not know the agreement ceiling was
unavailable will read the judge's score as if it had one.
"""

import csv
from dataclasses import dataclass, field
from typing import Optional

# Name fragments, checked case-insensitively against each column. Order matters
# within a role: the first fragment that matches wins.
JUDGE_HINTS = ("judge", "llm", "model_score", "auto", "ai_")
HUMAN_HINTS = ("human", "gold", "expert", "annotator", "rater", "label")
ITEM_HINTS = ("item_id", "item", "id", "example", "sample")
LENGTH_HINTS = ("length", "chars", "tokens", "len", "words")
GENERATOR_HINTS = ("generator", "system", "model_name", "produced_by")


@dataclass
class CalibrationData:
    """One labels file, parsed and described."""

    judge_column: str
    judge_scores: list
    human_columns: dict
    n: int
    numeric: dict = field(default_factory=dict)
    item_ids: Optional[list] = None
    lengths: Optional[list] = None
    generators: Optional[list] = None
    notes: list = field(default_factory=list)

    @property
    def human_rater_count(self):
        return len(self.human_columns)


def _matches(column, hints):
    lowered = column.lower()
    return any(hint in lowered for hint in hints)


def detect_columns(fieldnames):
    """Guess each column's role from its name.

    Returns a dict with keys judge, humans, item_id, length, generator. A role
    with no match is None (or an empty list for humans) rather than a guess —
    the caller reports the absence instead of proceeding on a hunch.

    Each column is claimed at most once. Judge is resolved first because it is
    the one column the analysis cannot proceed without, so a name like
    `human_judge` counts as the judge rather than as a rater.
    """
    remaining = list(fieldnames)

    judge = next((c for c in remaining if _matches(c, JUDGE_HINTS)), None)
    if judge is not None:
        remaining.remove(judge)

    humans = [c for c in remaining if _matches(c, HUMAN_HINTS)]
    for column in humans:
        remaining.remove(column)

    def claim(hints):
        found = next((c for c in remaining if _matches(c, hints)), None)
        if found is not None:
            remaining.remove(found)
        return found

    return {
        "judge": judge,
        "humans": humans,
        "item_id": claim(ITEM_HINTS),
        "length": claim(LENGTH_HINTS),
        "generator": claim(GENERATOR_HINTS),
    }


def _coerce(values):
    """Convert a column to floats, or leave it entirely as text.

    All-or-nothing per column: a column holding 4, 5 and "n/a" becomes text,
    because a list mixing floats and strings breaks every statistic downstream
    in a way that surfaces far from here. Blank cells become None and do not
    block coercion — Krippendorff's alpha handles missing ratings natively.
    """
    present = [v for v in values if v not in ("", None)]
    try:
        floats = [float(v) for v in present]
    except (TypeError, ValueError):
        return [None if v in ("", None) else v for v in values], False

    numbers = iter(floats)
    return [None if v in ("", None) else next(numbers) for v in values], True


def load_labels(path, judge=None, humans=None, item_id=None, length=None,
                generator=None):
    """Read `path` into a CalibrationData.

    Any of the column arguments overrides detection for that role. A named
    column that is not in the file raises rather than falling back to a guess.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not fieldnames:
        raise ValueError("%s has no header row" % path)
    if not rows:
        raise ValueError("%s has a header but no data rows" % path)
    for number, row in enumerate(rows, start=2):
        if any(value is None for value in row.values()) or None in row:
            raise ValueError(
                "%s line %d has a different number of fields than the header"
                % (path, number)
            )

    detected = detect_columns(fieldnames)

    def resolve(explicit, role, fallback):
        if explicit is None:
            return fallback
        names = explicit if isinstance(explicit, list) else [explicit]
        missing = [n for n in names if n not in fieldnames]
        if missing:
            raise ValueError(
                "column(s) named for %s not in %s: %s"
                % (role, path, ", ".join(missing))
            )
        return explicit

    judge_column = resolve(judge, "the judge", detected["judge"])
    human_names = resolve(humans, "human raters", detected["humans"])
    item_column = resolve(item_id, "item ids", detected["item_id"])
    length_column = resolve(length, "response length", detected["length"])
    generator_column = resolve(generator, "the generator", detected["generator"])

    if judge_column is None:
        raise ValueError(
            "no judge column found in %s (looked for a name containing %s); "
            "name one explicitly" % (path, ", ".join(JUDGE_HINTS))
        )
    if not human_names:
        raise ValueError(
            "no human label column found in %s (looked for a name containing "
            "%s); name one explicitly" % (path, ", ".join(HUMAN_HINTS))
        )

    def column(name):
        return [row[name] for row in rows]

    numeric = {}
    judge_scores, numeric[judge_column] = _coerce(column(judge_column))

    human_columns = {}
    for name in human_names:
        human_columns[name], numeric[name] = _coerce(column(name))

    lengths = None
    if length_column is not None:
        lengths, numeric[length_column] = _coerce(column(length_column))

    notes = []
    if len(human_names) < 2:
        notes.append(
            "Only one human rater column was found, so there is no "
            "human-human agreement ceiling. Judge-human agreement cannot be "
            "compared against anything, and Gate 6 cannot be answered."
        )
    if item_column is None:
        notes.append(
            "No item id column, so bootstrap resampling cannot be clustered "
            "by item and disagreements cannot be listed by id."
        )
    if length_column is None:
        notes.append("No response length column, so the length-bias probe is unavailable.")
    if generator_column is None:
        notes.append(
            "No generator column, so the self-preference probe is unavailable."
        )

    return CalibrationData(
        judge_column=judge_column,
        judge_scores=judge_scores,
        human_columns=human_columns,
        n=len(rows),
        numeric=numeric,
        item_ids=column(item_column) if item_column else None,
        lengths=lengths,
        generators=column(generator_column) if generator_column else None,
        notes=notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_loader.py`
Expected: PASS — `Ran 20 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/calibration/__init__.py genai-eval/scripts/calibration/loader.py genai-eval/scripts/tests/test_loader.py
git commit -m "feat(genai-eval): labels CSV loader with column detection"
```

---

### Task 3: Agreement analysis and the no-ceiling guard

**Files:**
- Create: `genai-eval/scripts/calibration/analysis.py`
- Create: `genai-eval/scripts/tests/test_analysis.py`

**Interfaces:**
- Consumes: `loader.CalibrationData`; `evalstats.agreement.krippendorff_alpha`, `bootstrap_ci`.
- Produces: `analysis.agreement_section(data, level="nominal", categories=None, seed=None, n_resamples=2000) -> dict` with keys `judge_human` (dict with `alpha`, `ci`, `n`), `human_human` (dict or None), `ceiling_available` (bool), `verdict` (one of `"at_or_above_ceiling"`, `"below_ceiling"`, `"no_ceiling"`), and `notes` (list of str).

This is the spec's central requirement. With one human rater there is no ceiling, so `human_human` is `None`, `verdict` is `"no_ceiling"`, and a note says the comparison is unavailable. The function never invents a ceiling and never compares the judge against nothing.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_analysis.py`:

```python
#!/usr/bin/env python3
"""Tests for calibration.analysis. Run directly: python3 test_analysis.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import analysis
from calibration.loader import CalibrationData


def make_data(judge, humans, **kwargs):
    return CalibrationData(
        judge_column="judge",
        judge_scores=list(judge),
        human_columns={name: list(vals) for name, vals in humans.items()},
        n=len(judge),
        numeric={"judge": True},
        **kwargs
    )


class TestNoCeilingGuard(unittest.TestCase):
    def test_one_rater_yields_no_ceiling(self):
        """The whole point of bare mode: with nothing to compare against, the
        analysis says so rather than reporting judge-human agreement as if it
        had passed a bar."""
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNone(result["human_human"])
        self.assertFalse(result["ceiling_available"])
        self.assertEqual(result["verdict"], "no_ceiling")
        self.assertTrue(
            any("no human-human ceiling" in n.lower() for n in result["notes"]),
            result["notes"],
        )

    def test_judge_human_is_still_reported_without_a_ceiling(self):
        """The number is computable and worth having — it just cannot be
        graded."""
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNotNone(result["judge_human"]["alpha"])
        self.assertEqual(result["judge_human"]["n"], 6)


class TestWithCeiling(unittest.TestCase):
    HUMANS = {
        "human_a": [1, 1, 2, 2, 1, 2, 1, 2],
        "human_b": [1, 1, 2, 2, 2, 2, 1, 1],
    }

    def test_two_raters_give_a_ceiling(self):
        data = make_data([1, 1, 2, 2, 1, 2, 1, 2], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNotNone(result["human_human"])
        self.assertTrue(result["ceiling_available"])
        self.assertIn(result["verdict"], ("at_or_above_ceiling", "below_ceiling"))

    def test_judge_agreeing_with_rater_a_exactly_reaches_the_ceiling(self):
        """Judge copies human_a. Its agreement with the pooled humans is then
        at least as good as the humans manage with each other."""
        data = make_data(self.HUMANS["human_a"], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertEqual(result["verdict"], "at_or_above_ceiling")

    def test_a_random_judge_falls_below_the_ceiling(self):
        data = make_data([2, 1, 1, 2, 2, 1, 2, 1], self.HUMANS)
        result = analysis.agreement_section(data, seed=1)
        self.assertEqual(result["verdict"], "below_ceiling")

    def test_intervals_are_present_and_bracket_their_estimates(self):
        data = make_data(self.HUMANS["human_a"], self.HUMANS)
        result = analysis.agreement_section(data, seed=1, n_resamples=400)
        for block in (result["judge_human"], result["human_human"]):
            low, high = block["ci"]
            self.assertLessEqual(low, block["alpha"])
            self.assertLessEqual(block["alpha"], high)


class TestKnownAnswer(unittest.TestCase):
    def test_judge_human_alpha_matches_a_hand_derived_value(self):
        """Four units, judge and one human. Pairs are (a,a), (a,b), (b,b),
        (b,b), which is the fixture pinned at 8/15 by the agreement suite's
        own known-answer test."""
        data = make_data(["a", "a", "b", "b"], {"human": ["a", "b", "b", "b"]})
        result = analysis.agreement_section(data, seed=1, n_resamples=200)
        self.assertAlmostEqual(result["judge_human"]["alpha"], 8 / 15, places=10)


class TestDegenerate(unittest.TestCase):
    def test_all_identical_ratings_report_undefined_rather_than_one(self):
        """alpha is undefined when nothing varies. The section must carry that
        through as None with an explanation, not as perfect agreement."""
        data = make_data([1, 1, 1, 1], {"human": [1, 1, 1, 1]})
        result = analysis.agreement_section(data, seed=1)
        self.assertIsNone(result["judge_human"]["alpha"])
        self.assertTrue(
            any("undefined" in n.lower() for n in result["notes"]), result["notes"]
        )

    def test_too_few_items_for_an_interval_is_reported_not_faked(self):
        """One item: alpha is computable (the single unit's two ratings
        disagree, giving 0.0), but bootstrap_ci needs at least two units. The
        point estimate survives and the interval is honestly absent, rather
        than a zero-width interval implying certainty."""
        data = make_data([1], {"human": [2]})
        result = analysis.agreement_section(data, seed=1, n_resamples=100)
        self.assertAlmostEqual(result["judge_human"]["alpha"], 0.0, places=10)
        self.assertIsNone(result["judge_human"]["ci"])
        self.assertTrue(
            any("confidence interval" in n.lower() for n in result["notes"]),
            result["notes"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_analysis.py`
Expected: FAIL — `ImportError: cannot import name 'analysis' from 'calibration'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/calibration/analysis.py`:

```python
"""Decide which statistics the available columns actually support, then run them.

The rule this module exists to enforce: a judge's agreement number means
nothing on its own. It has to be read against how well humans agree with each
other, because that ceiling is the best any instrument could do on this task.
With one human rater there is no ceiling, so this module reports the judge's
number and states plainly that it cannot be graded — rather than letting a
reader assume it passed a bar that was never measured.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import agreement


def _alpha_with_ci(units, level, categories, seed, n_resamples):
    """Point estimate plus interval, with both failures reported honestly."""

    def statistic(sample):
        return agreement.krippendorff_alpha(sample, level=level, categories=categories)

    try:
        point = statistic(units)
    except ValueError as exc:
        return {"alpha": None, "ci": None, "n": len(units), "why": str(exc)}

    try:
        interval = agreement.bootstrap_ci(
            units, statistic, n_resamples=n_resamples, seed=seed
        )
    except ValueError as exc:
        return {"alpha": point, "ci": None, "n": len(units), "why": str(exc)}

    return {"alpha": point, "ci": interval, "n": len(units), "why": None}


def agreement_section(data, level="nominal", categories=None, seed=None,
                      n_resamples=2000):
    """Judge-human agreement, the human-human ceiling, and the verdict between.

    `data` is a loader.CalibrationData. `level` and `categories` are passed
    through to Krippendorff's alpha — pass `categories` whenever the ratings
    are word labels on an ordinal scale, or the scale order will come from
    sorting them alphabetically.

    verdict is "no_ceiling" when fewer than two human raters exist,
    "at_or_above_ceiling" when the judge's point estimate reaches the humans',
    and "below_ceiling" otherwise.
    """
    human_names = list(data.human_columns)
    notes = []

    pooled_human = []
    for row in range(data.n):
        ratings = [data.human_columns[name][row] for name in human_names]
        present = [r for r in ratings if r is not None]
        pooled_human.append(present[0] if present else None)

    judge_units = [
        [data.judge_scores[row], pooled_human[row]] for row in range(data.n)
    ]
    judge_human = _alpha_with_ci(
        judge_units, level, categories, seed, n_resamples
    )
    if judge_human["alpha"] is None:
        notes.append(
            "Judge-human agreement is undefined: %s" % judge_human["why"]
        )
    elif judge_human["ci"] is None:
        notes.append(
            "No confidence interval for judge-human agreement: %s"
            % judge_human["why"]
        )

    if len(human_names) < 2:
        notes.append(
            "There is no human-human ceiling, because only one human rater "
            "column was supplied. The judge's agreement figure below cannot be "
            "compared against anything, so Gate 6 stays unanswered. Add a "
            "second independent rater on at least a subset of items."
        )
        return {
            "judge_human": judge_human,
            "human_human": None,
            "ceiling_available": False,
            "verdict": "no_ceiling",
            "notes": notes,
        }

    human_units = [
        [data.human_columns[name][row] for name in human_names]
        for row in range(data.n)
    ]
    human_human = _alpha_with_ci(
        human_units, level, categories, seed, n_resamples
    )
    if human_human["alpha"] is None:
        notes.append("The ceiling is undefined: %s" % human_human["why"])
        verdict = "no_ceiling"
    elif judge_human["alpha"] is None:
        verdict = "no_ceiling"
    elif judge_human["alpha"] >= human_human["alpha"]:
        verdict = "at_or_above_ceiling"
    else:
        verdict = "below_ceiling"

    return {
        "judge_human": judge_human,
        "human_human": human_human,
        "ceiling_available": human_human["alpha"] is not None,
        "verdict": verdict,
        "notes": notes,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_analysis.py`
Expected: PASS — `Ran 9 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/calibration/analysis.py genai-eval/scripts/tests/test_analysis.py
git commit -m "feat(genai-eval): agreement analysis with the no-ceiling guard"
```

---

### Task 4: Bias probes conditional on available columns

**Files:**
- Modify: `genai-eval/scripts/calibration/analysis.py`
- Modify: `genai-eval/scripts/tests/test_analysis.py`

**Interfaces:**
- Consumes: `evalstats.bias.length_bias`, `evalstats.bias.self_preference`.
- Produces: `analysis.bias_section(data, judge_model=None) -> dict` with keys `length` (dict or None), `self_preference` (dict or None), `unavailable` (list of str naming each probe that could not run and why).

Two probes need columns the minimum contract does not require. Rather than skipping them silently, each absence is named in `unavailable` so the report can say which parts of the picture are missing.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_analysis.py`:

```python
class TestBiasSection(unittest.TestCase):
    def test_both_probes_unavailable_on_a_minimal_file(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        result = analysis.bias_section(data)
        self.assertIsNone(result["length"])
        self.assertIsNone(result["self_preference"])
        joined = " ".join(result["unavailable"]).lower()
        self.assertIn("length", joined)
        self.assertIn("generator", joined)

    def test_length_probe_runs_when_lengths_are_present(self):
        """Judge tracks length exactly, humans invert it, so the gap is the
        full 2.0 — the same known answer the bias suite pins."""
        data = make_data(
            [1, 2, 3, 4, 5],
            {"human": [5, 4, 3, 2, 1]},
            lengths=[10, 20, 30, 40, 50],
        )
        result = analysis.bias_section(data)
        self.assertAlmostEqual(result["length"]["judge_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["length"]["human_rho"], -1.0, places=10)
        self.assertAlmostEqual(result["length"]["gap"], 2.0, places=10)

    def test_self_preference_needs_a_judge_model_name(self):
        data = make_data(
            [5, 5, 3, 3],
            {"human": [4, 4, 4, 4]},
            generators=["gpt-x", "gpt-x", "other", "other"],
        )
        without = analysis.bias_section(data)
        self.assertIsNone(without["self_preference"])
        self.assertTrue(
            any("judge model" in u.lower() for u in without["unavailable"]),
            without["unavailable"],
        )

        with_name = analysis.bias_section(data, judge_model="gpt-x")
        self.assertAlmostEqual(with_name["self_preference"]["delta"], 2.0, places=10)

    def test_constant_human_scores_leave_the_length_gap_undefined(self):
        """A judge's raw length correlation is not bias — the gap against the
        humans is. With no human variance there is no gap to report."""
        data = make_data(
            [1, 2, 3, 4, 5],
            {"human": [3, 3, 3, 3, 3]},
            lengths=[10, 20, 30, 40, 50],
        )
        result = analysis.bias_section(data)
        self.assertIsNone(result["length"]["gap"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_analysis.py -k TestBiasSection`
Expected: FAIL — `AttributeError: module 'calibration.analysis' has no attribute 'bias_section'`

- [ ] **Step 3: Write the implementation**

Add `bias` to the evalstats import at the top of `analysis.py` so it reads `from evalstats import agreement, bias`, then append:

```python
def bias_section(data, judge_model=None):
    """Whichever judge bias probes the available columns support.

    Each probe that cannot run is named in `unavailable` together with what it
    would need. A silently skipped probe reads as a probe that found nothing.
    """
    unavailable = []

    length = None
    if data.lengths is None:
        unavailable.append(
            "Length bias: needs a response length column (characters, tokens "
            "or words)."
        )
    else:
        human_name = next(iter(data.human_columns))
        length = bias.length_bias(
            data.judge_scores, data.human_columns[human_name], data.lengths
        )

    preference = None
    if data.generators is None:
        unavailable.append(
            "Self-preference: needs a generator column naming which model "
            "produced each response."
        )
    elif judge_model is None:
        unavailable.append(
            "Self-preference: needs the judge model's name, to know which "
            "generator counts as its own. Pass --judge-model."
        )
    else:
        preference = bias.self_preference(
            data.judge_scores, data.generators, judge_model
        )

    return {
        "length": length,
        "self_preference": preference,
        "unavailable": unavailable,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_analysis.py`
Expected: PASS — `Ran 13 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/calibration/analysis.py genai-eval/scripts/tests/test_analysis.py
git commit -m "feat(genai-eval): bias probes gated on available columns"
```

---

### Task 5: Disagreement clustering

**Files:**
- Modify: `genai-eval/scripts/calibration/analysis.py`
- Modify: `genai-eval/scripts/tests/test_analysis.py`

**Interfaces:**
- Produces: `analysis.disagreement_clusters(data, limit=None) -> list[dict]`, each dict having `human`, `judge`, `count`, `item_ids` (list, empty when the file had no id column) and `share` (count divided by total disagreements). Sorted by `count` descending, then by `human` and `judge` as strings for a stable order.

This is the mechanical half of the error taxonomy. The script counts which (human label, judge label) pairs disagree and how often; naming what each cluster *means* is SKILL.md's job, because that needs a human's understanding of the rubric. Keeping the split here is what stops the taxonomy from being invented rather than observed.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_analysis.py`:

```python
class TestDisagreementClusters(unittest.TestCase):
    def test_known_counts_and_ordering(self):
        """Six items. The judge says 5 where the human said 3 three times, and
        3 where the human said 5 once; two items agree. So there are two
        clusters of sizes 3 and 1, shares 0.75 and 0.25, biggest first."""
        data = make_data(
            [5, 5, 5, 3, 4, 2],
            {"human": [3, 3, 3, 5, 4, 2]},
            item_ids=["i1", "i2", "i3", "i4", "i5", "i6"],
        )
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["human"], 3)
        self.assertEqual(clusters[0]["judge"], 5)
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[0]["item_ids"], ["i1", "i2", "i3"])
        self.assertAlmostEqual(clusters[0]["share"], 0.75, places=10)
        self.assertEqual(clusters[1]["count"], 1)
        self.assertAlmostEqual(clusters[1]["share"], 0.25, places=10)

    def test_perfect_agreement_gives_no_clusters(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        self.assertEqual(analysis.disagreement_clusters(data), [])

    def test_missing_item_ids_leave_the_list_empty_not_absent(self):
        data = make_data([5, 3], {"human": [3, 5]})
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(clusters[0]["item_ids"], [])

    def test_rows_with_a_missing_rating_are_skipped(self):
        """A blank cell is not a disagreement."""
        data = make_data([5, 5], {"human": [3, None]})
        clusters = analysis.disagreement_clusters(data)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["count"], 1)

    def test_limit_truncates_the_tail(self):
        data = make_data([5, 5, 4, 3], {"human": [1, 1, 1, 1]})
        self.assertEqual(len(analysis.disagreement_clusters(data, limit=1)), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_analysis.py -k TestDisagreementClusters`
Expected: FAIL — `AttributeError: module 'calibration.analysis' has no attribute 'disagreement_clusters'`

- [ ] **Step 3: Write the implementation**

Append to `analysis.py`:

```python
def disagreement_clusters(data, limit=None):
    """Count which (human label, judge label) pairs disagree, and how often.

    This is the observed half of a failure taxonomy. It does not name the
    categories — that needs someone who understands the rubric, and a name
    invented here would be a guess dressed as a finding. The skill reads these
    counts and supplies the names.

    Rows where either rating is missing are skipped: a blank cell is not a
    disagreement. Pairs are keyed on the first human rater column, which is the
    one a single-rater file has.
    """
    human_name = next(iter(data.human_columns))
    human = data.human_columns[human_name]
    judge = data.judge_scores

    buckets = {}
    for row in range(data.n):
        h, j = human[row], judge[row]
        if h is None or j is None or h == j:
            continue
        entry = buckets.setdefault((h, j), [])
        entry.append(data.item_ids[row] if data.item_ids else None)

    total = sum(len(ids) for ids in buckets.values())
    clusters = [
        {
            "human": h,
            "judge": j,
            "count": len(ids),
            "item_ids": [i for i in ids if i is not None],
            "share": len(ids) / total,
        }
        for (h, j), ids in buckets.items()
    ]
    clusters.sort(key=lambda c: (-c["count"], str(c["human"]), str(c["judge"])))
    return clusters[:limit] if limit else clusters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_analysis.py`
Expected: PASS — `Ran 18 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/calibration/analysis.py genai-eval/scripts/tests/test_analysis.py
git commit -m "feat(genai-eval): disagreement clustering for the error taxonomy"
```

---

### Task 6: Power check against a minimum detectable effect

**Files:**
- Modify: `genai-eval/scripts/calibration/analysis.py`
- Modify: `genai-eval/scripts/tests/test_analysis.py`

**Interfaces:**
- Consumes: `evalstats.power.n_required_two_proportion`, `evalstats.power.mde_two_proportion`.
- Produces: `analysis.power_section(data, mid=None, baseline=None) -> dict` with keys `n`, `baseline`, `mde` (smallest detectable proportion at this n, or None), `mid` (the minimum interesting difference the caller asked about, or None), `n_required` (items needed for `mid`, or None), `sufficient` (bool or None).

Gate 7. Most judge-calibration sets are far too small to support the comparison they are used for, and this turns that from an impression into a number a report can print.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_analysis.py`:

```python
class TestPowerSection(unittest.TestCase):
    def test_baseline_defaults_to_observed_exact_agreement(self):
        """Judge matches the human on 3 of 4 rows, so the baseline is 0.75."""
        data = make_data([1, 2, 3, 9], {"human": [1, 2, 3, 4]})
        result = analysis.power_section(data)
        self.assertAlmostEqual(result["baseline"], 0.75, places=10)
        self.assertEqual(result["n"], 4)

    def test_known_answer_for_required_n(self):
        """Detecting 0.80 vs 0.85 needs 903 items per group at the default
        alpha and power — the value the power suite pins at 902.62 before
        ceiling."""
        data = make_data([1] * 10, {"human": [1] * 10})
        result = analysis.power_section(data, mid=0.05, baseline=0.80)
        self.assertEqual(result["n_required"], 903)

    def test_a_small_set_is_reported_insufficient(self):
        data = make_data([1] * 20, {"human": [1] * 20})
        result = analysis.power_section(data, mid=0.05, baseline=0.80)
        self.assertFalse(result["sufficient"])

    def test_a_large_set_is_reported_sufficient(self):
        data = make_data([1] * 1000, {"human": [1] * 1000})
        result = analysis.power_section(data, mid=0.05, baseline=0.80)
        self.assertTrue(result["sufficient"])

    def test_no_mid_leaves_sufficiency_unanswered(self):
        """Without a stated minimum interesting difference there is no question
        to answer, and inventing one would be worse than saying so."""
        data = make_data([1] * 50, {"human": [1] * 50})
        result = analysis.power_section(data, baseline=0.80)
        self.assertIsNone(result["mid"])
        self.assertIsNone(result["sufficient"])

    def test_tiny_sample_detects_nothing(self):
        """Three items, observed agreement 2/3. No proportion below 1.0 is
        detectable against that baseline at n = 3, so mde is None — the honest
        answer, and far more useful than a number."""
        data = make_data([1, 1, 2], {"human": [1, 2, 2]})
        result = analysis.power_section(data)
        self.assertAlmostEqual(result["baseline"], 2 / 3, places=10)
        self.assertIsNone(result["mde"])

    def test_a_saturated_baseline_is_out_of_range_not_detectable(self):
        """Every row agreeing gives a baseline of 1.0, which the two-proportion
        formula cannot take. Report nothing rather than a number from a
        degenerate input."""
        data = make_data([1] * 3, {"human": [1] * 3})
        result = analysis.power_section(data)
        self.assertAlmostEqual(result["baseline"], 1.0, places=10)
        self.assertIsNone(result["mde"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_analysis.py -k TestPowerSection`
Expected: FAIL — `AttributeError: module 'calibration.analysis' has no attribute 'power_section'`

- [ ] **Step 3: Write the implementation**

Change the evalstats import in `analysis.py` to `from evalstats import agreement, bias, power`, add `import math` at the top, then append:

```python
def power_section(data, mid=None, baseline=None):
    """Can this many items detect the difference you would act on?

    `mid` is the minimum interesting difference in proportion terms — the
    smallest change in judge-human exact agreement that would change a
    decision. Without one there is no sufficiency question to answer, and
    guessing a value would produce a verdict nobody asked for.

    `baseline` defaults to the observed exact-agreement rate.
    """
    human_name = next(iter(data.human_columns))
    human = data.human_columns[human_name]

    if baseline is None:
        comparable = [
            (h, j)
            for h, j in zip(human, data.judge_scores)
            if h is not None and j is not None
        ]
        baseline = (
            sum(1 for h, j in comparable if h == j) / len(comparable)
            if comparable
            else None
        )

    result = {
        "n": data.n,
        "baseline": baseline,
        "mde": None,
        "mid": mid,
        "n_required": None,
        "sufficient": None,
    }
    if baseline is None or not 0.0 < baseline < 1.0:
        return result

    result["mde"] = power.mde_two_proportion(data.n, baseline)

    if mid is not None:
        target = min(baseline + mid, 1.0 - 1e-9)
        result["n_required"] = math.ceil(
            power.n_required_two_proportion(baseline, target)
        )
        result["sufficient"] = data.n >= result["n_required"]

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_analysis.py`
Expected: PASS — `Ran 25 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/calibration/analysis.py genai-eval/scripts/tests/test_analysis.py
git commit -m "feat(genai-eval): power check against a minimum interesting difference"
```

---

### Task 7: The markdown calibration report

**Files:**
- Create: `genai-eval/scripts/calibration/report.py`
- Create: `genai-eval/scripts/tests/test_report.py`
- Modify: `genai-eval/scripts/evalstats/__init__.py`

**Interfaces:**
- Consumes: the four section dicts from Tasks 3-6, plus `loader.CalibrationData`.
- Produces: `report.render(data, agreement_result, bias_result, clusters, power_result, title=None) -> str` — a complete markdown document.

The report's job is to be readable and honest in the same pass. Two rules it enforces structurally: an interval is never printed without its `n`, and the limits section comes before the numbers rather than in a footnote, because a reader who stops halfway must still have seen what the figures cannot support.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_report.py`:

```python
#!/usr/bin/env python3
"""Tests for calibration.report. Run directly: python3 test_report.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import analysis, report
from calibration.loader import CalibrationData


def make_data(judge, humans, **kwargs):
    return CalibrationData(
        judge_column="judge",
        judge_scores=list(judge),
        human_columns={name: list(vals) for name, vals in humans.items()},
        n=len(judge),
        numeric={"judge": True},
        **kwargs
    )


def render_for(data, **kwargs):
    return report.render(
        data,
        analysis.agreement_section(data, seed=1, n_resamples=200),
        analysis.bias_section(data, **kwargs),
        analysis.disagreement_clusters(data),
        analysis.power_section(data),
    )


class TestNoCeilingIsProminent(unittest.TestCase):
    def setUp(self):
        self.data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        self.text = render_for(self.data)

    def test_says_there_is_no_ceiling(self):
        self.assertIn("no human-human ceiling", self.text.lower())

    def test_limits_appear_before_the_agreement_numbers(self):
        """A reader who stops halfway must already have seen what the figures
        cannot support."""
        limits = self.text.lower().index("what this report cannot")
        numbers = self.text.lower().index("judge-human agreement")
        self.assertLess(limits, numbers)

    def test_gate_6_is_marked_unanswered(self):
        self.assertIn("Gate 6", self.text)
        self.assertIn("unanswered", self.text.lower())


class TestWithCeiling(unittest.TestCase):
    def test_reports_both_figures_and_the_verdict(self):
        humans = {
            "human_a": [1, 1, 2, 2, 1, 2, 1, 2],
            "human_b": [1, 1, 2, 2, 2, 2, 1, 1],
        }
        data = make_data(humans["human_a"], humans)
        text = render_for(data)
        self.assertIn("Judge-human agreement", text)
        self.assertIn("Human-human agreement", text)
        self.assertIn("reaches the ceiling", text.lower())


class TestIntervalsCarryTheirN(unittest.TestCase):
    def test_every_printed_interval_names_its_sample_size(self):
        data = make_data([1, 1, 2, 2, 1, 2], {"human": [1, 1, 2, 2, 2, 1]})
        text = render_for(data)
        for line in text.splitlines():
            if "95% CI" in line:
                self.assertIn("n = ", line, line)


class TestClustersAndProbes(unittest.TestCase):
    def test_disagreement_table_lists_the_biggest_cluster_first(self):
        data = make_data(
            [5, 5, 5, 3, 4, 2],
            {"human": [3, 3, 3, 5, 4, 2]},
            item_ids=["i1", "i2", "i3", "i4", "i5", "i6"],
        )
        text = render_for(data)
        self.assertIn("Disagreement clusters", text)
        first = text.index("| 3 | 5 |")
        second = text.index("| 5 | 3 |")
        self.assertLess(first, second)

    def test_unavailable_probes_are_named_not_omitted(self):
        data = make_data([1, 2, 3], {"human": [1, 2, 3]})
        text = render_for(data)
        self.assertIn("Not measured", text)
        self.assertIn("Length bias", text)

    def test_undefined_values_render_as_a_dash_not_a_zero(self):
        data = make_data([1, 1, 1, 1], {"human": [1, 1, 1, 1]})
        text = render_for(data)
        self.assertNotIn("0.000", text)
        self.assertIn("—", text)


class TestTitle(unittest.TestCase):
    def test_custom_title_is_used(self):
        data = make_data([1, 2], {"human": [1, 2]})
        text = report.render(
            data,
            analysis.agreement_section(data, seed=1, n_resamples=100),
            analysis.bias_section(data),
            analysis.disagreement_clusters(data),
            analysis.power_section(data),
            title="Retrieval judge v4",
        )
        self.assertTrue(text.startswith("# Retrieval judge v4"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_report.py`
Expected: FAIL — `ImportError: cannot import name 'report' from 'calibration'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/calibration/report.py`:

```python
"""Render a calibration result as markdown.

Two structural rules, both there to stop a reader drawing more from the
numbers than the numbers support:

  * The limits section comes before the figures. Someone who reads the top of
    this document and stops must already know what it cannot tell them.
  * No interval is printed without its sample size. An interval whose n is a
    footnote invites a reader to treat a 12-item result like a 1200-item one.
"""

VERDICT_TEXT = {
    "at_or_above_ceiling": (
        "The judge reaches the ceiling. Its agreement with humans is at least "
        "as good as humans manage with each other, which is the most any "
        "instrument can do on this task."
    ),
    "below_ceiling": (
        "The judge falls below the ceiling. Humans agree with each other more "
        "than the judge agrees with them, so automating this rubric costs "
        "measurable accuracy."
    ),
    "no_ceiling": (
        "No verdict is possible, because there is no ceiling to compare "
        "against."
    ),
}


def _number(value, places=3):
    return "—" if value is None else format(value, ".%df" % places)


def _interval(block):
    """An interval always travels with the n it was computed from."""
    if block is None or block["alpha"] is None:
        return "—"
    if block["ci"] is None:
        return "%s (no interval, n = %d)" % (_number(block["alpha"]), block["n"])
    low, high = block["ci"]
    return "%s, 95%% CI [%s, %s], n = %d" % (
        _number(block["alpha"]),
        _number(low),
        _number(high),
        block["n"],
    )


def render(data, agreement_result, bias_result, clusters, power_result,
           title=None):
    """Assemble the markdown calibration report."""
    lines = ["# %s" % (title or "Judge calibration report"), ""]

    lines += [
        "Judge column `%s` against %d human rater column(s), %d items."
        % (data.judge_column, data.human_rater_count, data.n),
        "",
        "## What this report cannot tell you",
        "",
    ]
    limits = list(data.notes) + list(agreement_result["notes"])
    if agreement_result["verdict"] == "no_ceiling":
        limits.append(
            "**Gate 6 is unanswered.** Whether the judge is good enough to "
            "automate cannot be decided from this data."
        )
    limits.append(
        "This report measures agreement, not correctness. A judge that agrees "
        "with a mistaken human is still wrong."
    )
    lines += ["- %s" % note for note in limits]
    lines.append("")

    lines += ["## Agreement", ""]
    lines.append(
        "Judge-human agreement (Krippendorff's alpha): %s"
        % _interval(agreement_result["judge_human"])
    )
    lines.append("")
    if agreement_result["human_human"] is not None:
        lines.append(
            "Human-human agreement, the ceiling: %s"
            % _interval(agreement_result["human_human"])
        )
        lines.append("")
    lines += [VERDICT_TEXT[agreement_result["verdict"]], ""]

    lines += ["## Statistical power", ""]
    if power_result["baseline"] is None:
        lines.append("Not computable: no comparable rows.")
    else:
        lines.append(
            "Observed exact-agreement rate: %s over %d items."
            % (_number(power_result["baseline"]), power_result["n"])
        )
        if power_result["mde"] is not None:
            lines.append(
                "Smallest difference this many items can detect: %s."
                % _number(power_result["mde"])
            )
        else:
            lines.append(
                "This item count cannot detect any difference at conventional "
                "alpha and power. Any comparison drawn from it is noise."
            )
        if power_result["mid"] is not None:
            lines.append(
                "To detect a difference of %s you would need %d items; you "
                "have %d, which is %s."
                % (
                    _number(power_result["mid"]),
                    power_result["n_required"],
                    power_result["n"],
                    "enough" if power_result["sufficient"] else "not enough",
                )
            )
    lines.append("")

    lines += ["## Judge bias", ""]
    if bias_result["length"] is not None:
        gap = bias_result["length"]["gap"]
        lines.append(
            "Length: judge rho %s against human rho %s, gap %s."
            % (
                _number(bias_result["length"]["judge_rho"]),
                _number(bias_result["length"]["human_rho"]),
                _number(gap),
            )
        )
        lines.append(
            "The gap is the finding, not the judge's own correlation — longer "
            "answers are sometimes genuinely better."
        )
        lines.append("")
    if bias_result["self_preference"] is not None:
        lines.append(
            "Self-preference: own outputs %s against others %s, delta %s."
            % (
                _number(bias_result["self_preference"]["own_mean"]),
                _number(bias_result["self_preference"]["other_mean"]),
                _number(bias_result["self_preference"]["delta"]),
            )
        )
        lines.append("")
    if bias_result["unavailable"]:
        lines += ["**Not measured:**", ""]
        lines += ["- %s" % item for item in bias_result["unavailable"]]
        lines.append("")

    lines += ["## Disagreement clusters", ""]
    if not clusters:
        lines.append("The judge and the human never disagreed.")
    else:
        lines += [
            "Biggest first. These are counts, not causes — name each pattern "
            "yourself by reading the items behind it.",
            "",
            "| Human | Judge | Count | Share | Example items |",
            "|---|---|---|---|---|",
        ]
        for cluster in clusters:
            examples = ", ".join(str(i) for i in cluster["item_ids"][:5]) or "—"
            lines.append(
                "| %s | %s | %d | %s | %s |"
                % (
                    cluster["human"],
                    cluster["judge"],
                    cluster["count"],
                    _number(cluster["share"], 2),
                    examples,
                )
            )
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_report.py`
Expected: PASS — `Ran 9 tests ... OK`

- [ ] **Step 5: Add the undefined-value contract table**

Phase 1A's review noted that a report renderer has to special-case eight different "undefined" signals with nowhere to look them up. Append to the docstring in `genai-eval/scripts/evalstats/__init__.py`, before the `from . import` line:

```
How this package signals "undefined"
------------------------------------
Raises ValueError   structurally invalid input: empty, length mismatch, ragged
                    rows, fewer than two categories, a rating outside the
                    stated categories, n_resamples below 1, a proportion
                    outside (0, 1), no pairable unit, or every rating
                    identical (krippendorff_alpha, cohens_kappa,
                    weighted_kappa, fleiss_kappa — chance-corrected agreement
                    is undefined when nothing varies).
Raises TypeError    interval-level ratings that are not numbers.
Returns None        mathematically undefined but structurally fine:
                    point_biserial and kr20 on zero variance,
                    rank_correlation on a constant sequence,
                    length_bias["gap"] when either side is constant,
                    self_preference["delta"] with an empty group,
                    mde_two_proportion when nothing is detectable at that n,
                    dimensionality["first_ratio"] on a zero total.

Nothing in this package returns a number it cannot justify. A caller that sees
None must say so in its output rather than substituting zero.
```

- [ ] **Step 6: Commit**

```bash
git add genai-eval/scripts/calibration/report.py genai-eval/scripts/tests/test_report.py genai-eval/scripts/evalstats/__init__.py
git commit -m "feat(genai-eval): markdown calibration report"
```

---

### Task 8: The `calibrate.py` CLI

**Files:**
- Create: `genai-eval/scripts/calibrate.py`
- Create: `genai-eval/scripts/tests/test_calibrate.py`
- Modify: `genai-eval/scripts/calibration/__init__.py`

**Interfaces:**
- Produces: `calibrate.main(argv=None) -> int`. CLI: `python3 calibrate.py LABELS.csv [--judge COL] [--human COL ...] [--item-id COL] [--length COL] [--generator COL] [--judge-model NAME] [--level nominal|ordinal|interval] [--categories a,b,c] [--mid FLOAT] [--seed INT] [--resamples INT] [--title TEXT] [-o OUT.md]`. Exit 0 on success, 1 on a usage or data error with the message on stderr.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_calibrate.py`:

```python
#!/usr/bin/env python3
"""End-to-end tests for calibrate.py. Run directly: python3 test_calibrate.py"""

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

_spec = importlib.util.spec_from_file_location(
    "calibrate", os.path.join(os.path.dirname(HERE), "calibrate.py")
)
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


class TestMid(unittest.TestCase):
    def test_mid_produces_a_sufficiency_statement(self):
        code, out, _ = run(
            [write_csv(ONE_RATER), "--mid", "0.05", "--seed", "1", "--resamples", "200"]
        )
        self.assertEqual(code, 0)
        self.assertIn("you would need", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_calibrate.py`
Expected: FAIL — `FileNotFoundError` on `calibrate.py`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/calibrate.py`:

```python
#!/usr/bin/env python3
"""calibrate.py — is this LLM judge trustworthy enough to automate?

Bare mode for the eval-qualify skill. Reads a CSV of judge scores and human
labels and writes a calibration report: chance-corrected agreement with
confidence intervals, the human-human ceiling when the data supports one, judge
bias probes, a power check, and an observed disagreement taxonomy.

Usage
-----
    python3 calibrate.py labels.csv
    python3 calibrate.py labels.csv --level ordinal --categories low,medium,high
    python3 calibrate.py labels.csv --mid 0.05 -o report.md

The only required columns are one judge score and one human label. Every other
column adds a section; each missing one is named in the report rather than
quietly skipped.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calibration import analysis, loader, report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure whether an LLM judge agrees with humans well "
        "enough to trust, and say plainly what the data cannot support."
    )
    parser.add_argument("labels", help="CSV of judge scores and human labels.")
    parser.add_argument("--judge", help="Judge score column (default: detected).")
    parser.add_argument(
        "--human", action="append", dest="humans",
        help="Human label column; repeat for multiple raters (default: detected).",
    )
    parser.add_argument("--item-id", help="Item id column (default: detected).")
    parser.add_argument("--length", help="Response length column (default: detected).")
    parser.add_argument("--generator", help="Generator column (default: detected).")
    parser.add_argument(
        "--judge-model", help="The judge's own model name, for the self-preference probe."
    )
    parser.add_argument(
        "--level", choices=("nominal", "ordinal", "interval"), default="nominal",
        help="Measurement level for Krippendorff's alpha (default: nominal).",
    )
    parser.add_argument(
        "--categories",
        help="Comma-separated scale order, low to high. Required for ordinal "
        "or interval levels with non-numeric labels.",
    )
    parser.add_argument(
        "--mid", type=float,
        help="Minimum interesting difference in agreement rate, for the power check.",
    )
    parser.add_argument("--seed", type=int, help="Seed for the bootstrap.")
    parser.add_argument(
        "--resamples", type=int, default=2000, help="Bootstrap resamples (default: 2000)."
    )
    parser.add_argument("--title", help="Report title.")
    parser.add_argument("-o", "--out", help="Write to this file instead of stdout.")
    args = parser.parse_args(argv)

    categories = args.categories.split(",") if args.categories else None

    try:
        data = loader.load_labels(
            args.labels,
            judge=args.judge,
            humans=args.humans,
            item_id=args.item_id,
            length=args.length,
            generator=args.generator,
        )

        if args.level != "nominal" and categories is None:
            if not data.numeric.get(data.judge_column, False):
                raise ValueError(
                    "--level %s with non-numeric ratings needs --categories to "
                    "state the scale order; sorting labels alphabetically would "
                    "produce a confident wrong answer" % args.level
                )

        text = report.render(
            data,
            analysis.agreement_section(
                data,
                level=args.level,
                categories=categories,
                seed=args.seed,
                n_resamples=args.resamples,
            ),
            analysis.bias_section(data, judge_model=args.judge_model),
            analysis.disagreement_clusters(data),
            analysis.power_section(data, mid=args.mid),
            title=args.title,
        )
    except (OSError, ValueError, TypeError) as exc:
        print("calibrate: %s" % exc, file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note on the raise above: do **not** reach for `parser.error` there. It exits with status 2 and bypasses the handler, while every other data problem in this tool exits 1. Raising `ValueError` keeps one exit convention for every failure a user can cause.

- [ ] **Step 4: Widen `calibration/__init__.py` now that all three modules exist**

Replace `genai-eval/scripts/calibration/__init__.py`'s import line and `__all__`:

```python
from . import analysis, loader, report

__all__ = ["analysis", "loader", "report"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"`
Expected: PASS — 9 new CLI tests. Package total should be 210: Phase 1A's 140, plus 7 (Task 1), 20 (Task 2), 25 (Tasks 3-6 in `test_analysis.py`), 9 (Task 7), 9 (Task 8).

- [ ] **Step 6: Commit**

```bash
git add genai-eval/scripts/calibrate.py genai-eval/scripts/calibration/__init__.py genai-eval/scripts/tests/test_calibrate.py
git commit -m "feat(genai-eval): calibrate.py CLI for bare-mode judge calibration"
```

---

### Task 9: The worked example

**Files:**
- Create: `genai-eval/examples/judge-calibration/labels.csv`
- Create: `genai-eval/examples/judge-calibration/README.md`

**Interfaces:**
- Consumes: `calibrate.py` from Task 8.
- Produces: a runnable example whose output demonstrates the ceiling comparison, a real bias gap, and a disagreement cluster.

The example must be honest: a judge that looks good on one axis and measurably worse on another is more instructive than a contrived pass.

- [ ] **Step 1: Write the example data**

Create `genai-eval/examples/judge-calibration/labels.csv`. Two human raters, one judge, 24 items on a 1-4 groundedness rubric, with a length column and a generator column. The judge systematically over-scores long responses:

```csv
item_id,human_a,human_b,judge,response_chars,generator
i01,4,4,4,180,model-a
i02,3,3,4,520,model-a
i03,2,2,2,140,model-b
i04,4,4,4,240,model-a
i05,1,1,1,90,model-b
i06,3,2,3,310,model-a
i07,2,2,3,480,model-b
i08,4,4,4,200,model-a
i09,3,3,3,220,model-b
i10,1,1,2,460,model-b
i11,4,3,4,260,model-a
i12,2,2,2,130,model-b
i13,3,3,4,540,model-a
i14,4,4,4,190,model-a
i15,2,3,2,170,model-b
i16,1,1,1,80,model-b
i17,3,3,3,230,model-a
i18,4,4,4,210,model-a
i19,2,2,3,500,model-b
i20,3,3,3,250,model-a
i21,1,2,1,110,model-b
i22,4,4,4,230,model-a
i23,2,2,2,160,model-b
i24,3,3,4,530,model-a
```

- [ ] **Step 2: Run the tool and capture the real output**

Run:

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/judge-calibration/labels.csv \
  --level ordinal --judge-model model-a --mid 0.10 --seed 7
```

Read the actual output. Do not write the README from expectation — the numbers in it must be the ones the tool produced.

- [ ] **Step 3: Write the README around the real numbers**

Create `genai-eval/examples/judge-calibration/README.md` containing: the command above in a fenced `bash` block; the real headline figures (judge-human alpha with CI, human-human alpha with CI, the verdict); the length-bias gap; the largest disagreement cluster; and a short "what this tells you" section reading the result the way the skill would — specifically that the judge over-scores long responses relative to the humans, and what that means for using it on a corpus whose length distribution differs from this sample.

State the sample size next to every figure.

- [ ] **Step 4: Verify the documented command runs clean**

Run the command from Step 2 again and confirm it exits 0 and the figures still match the README.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/examples/judge-calibration/
git commit -m "docs(genai-eval): worked judge-calibration example"
```

---

### Task 10: The `eval-qualify` SKILL.md

**Files:**
- Create: `genai-eval/skills/eval-qualify/SKILL.md`

**Interfaces:**
- Consumes: `calibrate.py` and the example from Tasks 8-9.
- Produces: the skill body that makes `eval-qualify` trigger and run.

Follow the house structure used by every other skill in this repo (see `simplified-technical-english/skills/simplified-technical-english/SKILL.md` and `improvement-plan/skills/improvement-plan/SKILL.md`): YAML frontmatter with `name` and `description`, then a short framing paragraph, a "When to use" list, a "When NOT to use" list, and numbered process steps.

- [ ] **Step 1: Write the frontmatter and framing**

The `description` decides whether the skill ever fires, so it is given here verbatim rather than described. Use exactly:

```markdown
---
name: eval-qualify
description: Qualify a GenAI evaluation instrument and report its results — measure judge–human agreement with confidence intervals against the human–human ceiling, run item analysis and a power calculation, and check the design gates. Use when the user asks "is my LLM judge reliable", "how good is my eval", "compute Krippendorff's alpha / Cohen's kappa", "is this result significant", "do I have enough items", "audit this benchmark", or hands over judge scores and human labels. Runs standalone on a two-column CSV — no eval card required. Not for designing an eval that does not exist yet.
---
```

Follow it with a short framing paragraph: this skill measures whether an instrument can be trusted, which is the phase most teams skip, and it is deliberately more willing to say "this data cannot answer that" than to produce a number.

- [ ] **Step 2: Write "When to use" and "When NOT to use"**

NOT to use: designing an eval that does not exist yet (that is `eval-design`, Phase 2); interpreting a benchmark someone else ran with no access to item-level data; and anything needing correctness rather than agreement — the skill measures whether the judge matches humans, not whether either is right.

- [ ] **Step 3: Write the tier routing step**

Per spec §3.3, the skill states its tier before doing anything else and lists which steps it will run and skip:

| Tier | Trigger | Runs |
|---|---|---|
| 1 — daily regression | Catch breakage | Steps 9, 10, 11 light |
| 2 — per release | Compare options | + step 7 |
| 3 — sign-off / external claim | Defend a claim | + step 8, all |

- [ ] **Step 4: Write the bare-mode process steps**

Six numbered steps, matching spec §3.4:

1. Establish what decision the judge serves and at which tier. If nobody can name the decision, say so — a calibration number with no decision attached is a vanity metric.
2. Run `calibrate.py`, showing the exact command.
3. Read the "What this report cannot tell you" section aloud to the user first, before any figure. This is the step most likely to be skipped and the one that matters most.
4. Interpret the ceiling comparison: what `at_or_above_ceiling`, `below_ceiling` and `no_ceiling` each mean for the decision from step 1.
5. Name the disagreement clusters. The script counts them; read the items behind the largest two or three and give each a name that describes the *failure*, not the score pair. Explicitly: do not invent a category the items do not support.
6. State the limits and the next cheapest action — usually a second human rater on a subset, since that is what unlocks Gate 6.
7. Offer to promote the result into a full eval card. Spec §3.4 requires this offer, and Phase 2 supplies the card schema, so until then the skill says what a card would add — a sealed test split, a claim-to-item trace matrix, and a preregistered threshold, which together turn Gates 1-5 and 9 from judgement into checks — and notes that `eval-design` is not built yet. Do not fabricate a card format.

- [ ] **Step 5: Write the handoff section**

Per spec §9: when the qualification result needs a leadership audience, hand off to the `improvement-plan` skill rather than growing a stakeholder-communication section here; when readers are non-native or the report will be translated, hand off to `simplified-technical-english`. Note that Phase 2's `eval-design` will add card mode, and that this skill works standalone until then.

- [ ] **Step 6: Verify the skill file parses and reads correctly**

Run:

```bash
python3 -c "import sys; t=open('genai-eval/skills/eval-qualify/SKILL.md',encoding='utf-8').read(); assert t.startswith('---'), 'no frontmatter'; end=t.index('---',3); fm=t[3:end]; assert 'name: eval-qualify' in fm, 'bad name'; assert 'description:' in fm, 'no description'; print('frontmatter OK,', len(t.split()), 'words')"
```

Expected: `frontmatter OK, <n> words`

- [ ] **Step 7: Commit**

```bash
git add genai-eval/skills/eval-qualify/SKILL.md
git commit -m "feat(genai-eval): eval-qualify skill, bare mode"
```

---

### Task 11: Register the plugin and document it

**Files:**
- Create: `genai-eval/README.md`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`
- Modify: `.github/workflows/genai-eval-tests.yml`

**Interfaces:**
- Consumes: everything from Tasks 1-10.
- Produces: an installable plugin listed in the marketplace.

Phase 1A deliberately left the plugin unregistered because a plugin with no skill has nothing to install. Task 10 changed that.

- [ ] **Step 1: Write the plugin README**

Create `genai-eval/README.md` following the pattern of `simplified-technical-english/README.md`: what the plugin is for, what `eval-qualify` does, the bare-mode command with a real example, what the statistics toolkit provides, the honesty rules (no ceiling without two raters, no interval without its n, undefined reported as undefined), and a note that `eval-design` and card mode arrive in Phase 2.

- [ ] **Step 2: Register in the marketplace**

Add to the `plugins` array in `.claude-plugin/marketplace.json`, after the `microworld` entry:

```json
    {
      "name": "genai-eval",
      "source": "./genai-eval",
      "description": "Qualify a GenAI evaluation as a measurement instrument: judge-human agreement with confidence intervals against the human-human ceiling, classical item analysis, power against a minimum detectable effect, judge bias probes, and an observed disagreement taxonomy. Runs standalone on a two-column CSV of judge scores and human labels; stdlib-only."
    }
```

- [ ] **Step 3: Verify the manifest still parses**

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); names=[p['name'] for p in d['plugins']]; assert 'genai-eval' in names, names; print('OK:', names)"`
Expected: `OK: ['explain-code', 'improvement-plan', 'humanizer', 'simplified-technical-english', 'microworld', 'genai-eval']`

- [ ] **Step 4: Update the root README in three places**

In `README.md`: add `genai-eval` to the opening plugin list; add a paragraph after the `microworld` paragraph describing it; add its tree to the "What's inside" block; and add a "Try the judge calibration directly" section after the STE checker section, matching that section's shape:

````markdown
## Try the judge calibration directly

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/judge-calibration/labels.csv \
  --level ordinal --judge-model model-a --mid 0.10 --seed 7
```

It prints a markdown calibration report: chance-corrected agreement with
confidence intervals, the human-human ceiling, judge bias probes, a power
check, and the observed disagreement clusters. `-o report.md` writes to a file.
Standard library only. Its test suites run the same way:

```bash
python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"
```
````

Also add the install line to the Install block: `/plugin install genai-eval@explain-code-marketplace`

- [ ] **Step 5: Widen the CI path filter**

`.github/workflows/genai-eval-tests.yml` already filters on `genai-eval/**`, which covers the new files. Add a step after the test run that exercises the CLI end to end on the worked example, mirroring how `ste-tests.yml` verifies its checker on a conforming sample:

```yaml
      - name: Verify the CLI runs clean on the worked example
        run: |
          set -euo pipefail
          python3 genai-eval/scripts/calibrate.py \
            genai-eval/examples/judge-calibration/labels.csv \
            --level ordinal --judge-model model-a --mid 0.10 --seed 7 > /dev/null
```

- [ ] **Step 6: Run everything**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"`
Expected: PASS — all suites green.

- [ ] **Step 7: Commit**

```bash
git add genai-eval/README.md .claude-plugin/marketplace.json README.md .github/workflows/genai-eval-tests.yml
git commit -m "feat(genai-eval): register the plugin and document it"
```

---

## Done when

- `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"` is green.
- `python3 genai-eval/scripts/calibrate.py genai-eval/examples/judge-calibration/labels.csv --level ordinal --judge-model model-a --mid 0.10 --seed 7` exits 0 and prints a report whose figures match the example README.
- A one-rater CSV produces a report that says Gate 6 is unanswered, before any agreement figure.
- `genai-eval` appears in `.claude-plugin/marketplace.json` and in the root README's three places.
- Nothing in `evalstats/` opens a file or prints.

## Deferred to a separate hardening plan

Eleven findings from Phase 1A's final review, none of which this phase depends on: a shared `_require_rectangular` helper replacing five validation sites in three flavours; the corrected rest-score point-biserial inside `flag_items`; a non-convergence signal on `eigenvalues_symmetric`; `discordant_counts` truthiness coercion; mixed-type nominal alpha raising `TypeError` where `cohens_kappa` succeeds; deduplicating the percentile-interval arithmetic between `agreement.py` and `power.py` (and deciding truncation vs rounding once, in one place); `kr20` reusing `item_difficulty`; and the cosmetic items.

Also still open, and needing sources rather than code: spec §7 asks for published worked examples — Krippendorff's canonical nominal dataset and a textbook Fleiss example, each asserted against its published constant. Every fixture in the package is hand-derived, which is self-consistent but validated by the same reasoning that produced the formulas.
