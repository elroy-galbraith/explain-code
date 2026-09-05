# genai-eval Phase 1A — the `evalstats` toolkit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the stdlib-only statistics package that gives the SOP's Gates 6, 7, 10 and 11 real teeth — inter-rater agreement, judge bias probes, classical item analysis, and power calculation — with every statistic pinned by a known-answer test.

**Architecture:** A small Python package at `genai-eval/scripts/evalstats/`, split by responsibility: `agreement.py` (kappa family, Krippendorff's alpha, bootstrap CIs), `items.py` (difficulty, discrimination, reliability, dimensionality), `power.py` (MDE, required-n, McNemar), `bias.py` (judge bias probes). No I/O, no CLI, no formatting — this package computes numbers and raises on degenerate input. The CSV loader, report renderer and skill body are Phase 1B.

**Tech Stack:** Python 3.8+, standard library only. `unittest` for tests. GitHub Actions for CI.

**Spec:** [`docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`](../specs/2026-09-05-genai-eval-plugin-design.md) — sections 4.1, 6, 7.

## Global Constraints

- **Standard library only.** No pip install step, ever. No numpy, scipy, pandas, or PyYAML. This is the rule every plugin in this repo follows and it is what lets CI run with no install step.
- **Python floor is 3.8.** `math.comb` and `statistics.NormalDist` both require it. CI pins `python-version: "3.x"`, matching `ste-tests.yml`.
- **Every statistic needs a known-answer test.** A property test alone is not sufficient for any function that returns a number. Where this plan gives an expected value, the arithmetic that produces it is shown in the test docstring so a reviewer can check it without trusting the plan.
- **Degenerate input raises `ValueError` or returns `None`; it never returns a plausible-looking number.** Which of the two is specified per function. Silent wrong answers are the failure mode this whole plugin exists to prevent.
- **No file I/O and no printing anywhere in `evalstats/`.** Callers own both.
- **Deliberate deviation from the spec, §8:** the spec shows a single `scripts/evalstats.py`. It is split into a package here because one file covering agreement, bias, items and power would run past 800 lines. Update the spec's §8 layout in the final task.
- **Deliberate deviation from the spec, §7:** the spec says the suites match `test_check_ste.py`, which uses a homegrown `check(name, condition)` harness. These suites use stdlib `unittest` instead, because a numerics suite needs `assertAlmostEqual` and precise failure output. They still run directly (`python3 test_agreement.py`) as the house convention requires.

---

### Task 1: Plugin skeleton, CI, and Cohen's kappa

**Files:**
- Create: `genai-eval/.claude-plugin/plugin.json`
- Create: `genai-eval/scripts/evalstats/__init__.py`
- Create: `genai-eval/scripts/evalstats/agreement.py`
- Create: `genai-eval/scripts/tests/test_agreement.py`
- Create: `.github/workflows/genai-eval-tests.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `agreement.cohens_kappa(a: Sequence, b: Sequence) -> float`. Raises `ValueError` on length mismatch, empty input, or `p_e == 1.0`.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_agreement.py`:

```python
#!/usr/bin/env python3
"""Known-answer tests for evalstats.agreement. Run directly: python3 test_agreement.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import agreement


def _from_matrix(counts):
    """Expand a {(rater_a_value, rater_b_value): n} dict into two parallel lists."""
    a, b = [], []
    for (x, y), n in counts.items():
        a.extend([x] * n)
        b.extend([y] * n)
    return a, b


class TestCohensKappa(unittest.TestCase):
    def test_known_answer_2x2(self):
        """2x2 table: 20/5/10/65.

        p_o = (20 + 65) / 100 = 0.85
        marginals: A=(25, 75), B=(30, 70)
        p_e = (25*30 + 75*70) / 100^2 = 6000 / 10000 = 0.60
        kappa = (0.85 - 0.60) / (1 - 0.60) = 0.25 / 0.40 = 0.625
        """
        a, b = _from_matrix({(1, 1): 20, (1, 0): 5, (0, 1): 10, (0, 0): 65})
        self.assertAlmostEqual(agreement.cohens_kappa(a, b), 0.625, places=10)

    def test_perfect_agreement_is_one(self):
        a = [1, 2, 3, 1, 2, 3]
        self.assertAlmostEqual(agreement.cohens_kappa(a, a), 1.0, places=10)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([1, 2, 3], [1, 2])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([], [])

    def test_single_category_raises(self):
        """Both raters used one category, so p_e == 1.0 and kappa is undefined."""
        with self.assertRaises(ValueError):
            agreement.cohens_kappa([1, 1, 1], [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'evalstats'`

- [ ] **Step 3: Write the package scaffold and the implementation**

Create `genai-eval/scripts/evalstats/__init__.py`:

```python
"""evalstats — stdlib-only measurement statistics for GenAI evaluation.

No I/O, no printing, no formatting. Every function computes a number or raises.
"""

__all__ = ["agreement", "bias", "items", "power"]
```

Create `genai-eval/scripts/evalstats/agreement.py`:

```python
"""Inter-rater agreement statistics.

Every function here answers one question: how much of the observed agreement
between raters is more than you would get by chance? A judge that agrees with a
human 90% of the time on a task where 88% of items get the same label is not a
good judge, and only a chance-corrected statistic shows that.
"""


def cohens_kappa(a, b):
    """Cohen's kappa for two raters on nominal categories.

    `a` and `b` are parallel sequences of labels, one entry per item. Labels may
    be any hashable, comparable-by-str value.

    Raises ValueError on length mismatch, empty input, or when expected
    agreement is exactly 1.0 (both raters used a single category, so kappa is
    undefined rather than zero).
    """
    if len(a) != len(b):
        raise ValueError("rater sequences must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("no ratings supplied")

    categories = sorted(set(a) | set(b), key=str)
    index = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    observed = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1

    p_o = sum(observed[i][i] for i in range(k)) / n
    rows = [sum(observed[i]) for i in range(k)]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    p_e = sum(rows[i] * cols[i] for i in range(k)) / (n * n)

    if p_e == 1.0:
        raise ValueError(
            "expected agreement is 1.0 (only one category in use); kappa is undefined"
        )
    return (p_o - p_e) / (1.0 - p_e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 5 tests ... OK`

- [ ] **Step 5: Add the plugin manifest and CI workflow**

Create `genai-eval/.claude-plugin/plugin.json`:

```json
{
  "name": "genai-eval",
  "version": "0.1.0",
  "description": "Design and qualify GenAI evaluations as measurement instruments. Ships eval-design (construct, claims, item pool, grader calibration) and eval-qualify (judge-human agreement with confidence intervals, item analysis, power, validity argument), coupled by a machine-readable eval card and a stdlib-only statistics toolkit.",
  "author": {
    "name": "Elroy Galbraith"
  },
  "license": "MIT",
  "keywords": [
    "evaluation",
    "llm-as-judge",
    "measurement",
    "psychometrics",
    "inter-rater-agreement",
    "validity",
    "benchmark",
    "ai-safety"
  ]
}
```

Create `.github/workflows/genai-eval-tests.yml`:

```yaml
name: genai-eval toolkit tests

# Runs the evalstats test suites. What these guard that isn't obvious:
#
#   1. Every statistic here is pinned by a known-answer test with the arithmetic
#      shown in the test docstring. A refactor that silently changes a chance
#      correction or a variance divisor produces a plausible number, not an
#      error, and only the pinned values catch it.
#   2. The degenerate-input cases (one human rater, zero variance, single
#      category) must raise or return None rather than return a number. A
#      confident-looking statistic computed from nothing is the failure mode
#      this plugin exists to prevent.
#
# Pure Python 3 standard library — no install step needed.

on:
  push:
    branches: [main]
    paths:
      - "genai-eval/**"
      - ".github/workflows/genai-eval-tests.yml"
  pull_request:
    paths:
      - "genai-eval/**"
      - ".github/workflows/genai-eval-tests.yml"

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Run the evalstats test suites
        run: |
          python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py" -v
```

- [ ] **Step 6: Verify the CI command works locally, then commit**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py" -v`
Expected: PASS — `Ran 5 tests ... OK`

```bash
git add genai-eval/.claude-plugin/plugin.json genai-eval/scripts/evalstats/__init__.py genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py .github/workflows/genai-eval-tests.yml
git commit -m "feat(genai-eval): plugin skeleton, CI, and Cohen's kappa"
```

---

### Task 2: Weighted kappa for ordinal rubrics

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Consumes: nothing from Task 1's code, but shares its module.
- Produces: `agreement.weighted_kappa(a, b, weights="linear") -> float`. `weights` is `"linear"` or `"quadratic"`. Categories are ordered by their natural sort order, so they must be mutually comparable (all ints, or all floats, or all strings). Raises `ValueError` on fewer than two distinct categories.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`, before the `__main__` block:

```python
# Ordinal 3x3 confusion matrix used by the weighted-kappa tests.
#   rater A rows, rater B columns, N = 20
#         B=1  B=2  B=3
#   A=1     4    2    0
#   A=2     1    5    1
#   A=3     0    2    5
_ORDINAL_3X3 = {
    (1, 1): 4, (1, 2): 2, (1, 3): 0,
    (2, 1): 1, (2, 2): 5, (2, 3): 1,
    (3, 1): 0, (3, 2): 2, (3, 3): 5,
}


class TestWeightedKappa(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _from_matrix(_ORDINAL_3X3)

    def test_unweighted_known_answer(self):
        """p_o = 14/20 = 0.70; row marginals (6, 7, 7), col marginals (5, 9, 6)
        p_e = (6*5 + 7*9 + 7*6) / 400 = 135 / 400 = 0.3375
        kappa = (0.70 - 0.3375) / (1 - 0.3375) = 0.3625 / 0.6625 = 29/53
        """
        self.assertAlmostEqual(agreement.cohens_kappa(self.a, self.b), 29 / 53, places=10)

    def test_linear_known_answer(self):
        """Agreement weights w = 1 - |i-j|/(k-1), k = 3, so w = 1, 0.5, 0.

        weighted p_o = [1*(4+5+5) + 0.5*(2+1+1+2)] / 20 = 17/20 = 0.85
        weighted p_e = [1*(30+63+42) + 0.5*(54+35+42+63)] / 400
                     = (135 + 97) / 400 = 232/400 = 0.58
        kappa_w = (0.85 - 0.58) / (1 - 0.58) = 0.27 / 0.42 = 9/14
        """
        got = agreement.weighted_kappa(self.a, self.b, weights="linear")
        self.assertAlmostEqual(got, 9 / 14, places=10)

    def test_quadratic_known_answer(self):
        """Agreement weights w = 1 - (|i-j|/(k-1))^2, so w = 1, 0.75, 0.

        weighted p_o = [1*14 + 0.75*6] / 20 = 18.5/20 = 0.925
        weighted p_e = [1*135 + 0.75*194] / 400 = 280.5/400 = 0.70125
        kappa_q = (0.925 - 0.70125) / (1 - 0.70125) = 0.22375 / 0.29875 = 179/239
        """
        got = agreement.weighted_kappa(self.a, self.b, weights="quadratic")
        self.assertAlmostEqual(got, 179 / 239, places=10)

    def test_weighting_orders_as_expected(self):
        """Partial credit for near-misses can only raise the statistic, and
        quadratic forgives a one-step disagreement more than linear does."""
        plain = agreement.cohens_kappa(self.a, self.b)
        linear = agreement.weighted_kappa(self.a, self.b, weights="linear")
        quad = agreement.weighted_kappa(self.a, self.b, weights="quadratic")
        self.assertLess(plain, linear)
        self.assertLess(linear, quad)

    def test_unknown_weighting_raises(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa(self.a, self.b, weights="cubic")

    def test_single_category_raises(self):
        with self.assertRaises(ValueError):
            agreement.weighted_kappa([1, 1], [1, 1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestWeightedKappa`
Expected: FAIL — `AttributeError: module 'evalstats.agreement' has no attribute 'weighted_kappa'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/agreement.py`:

```python
def weighted_kappa(a, b, weights="linear"):
    """Weighted kappa for two raters on an ordinal scale.

    Most rubrics are ordinal (1-5, or fail/weak/adequate/strong), and unweighted
    kappa treats a 4-vs-5 disagreement as harshly as a 1-vs-5. Weighted kappa
    gives partial credit for near-misses.

    Categories are ordered by natural sort, so all labels must be mutually
    comparable. `weights` is "linear" (credit falls off with distance) or
    "quadratic" (credit falls off with squared distance, so near-misses are
    forgiven more and far-misses punished about the same).

    Raises ValueError on length mismatch, empty input, fewer than two distinct
    categories, or an unknown weighting.
    """
    if weights not in ("linear", "quadratic"):
        raise ValueError("weights must be 'linear' or 'quadratic'")
    if len(a) != len(b):
        raise ValueError("rater sequences must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("no ratings supplied")

    categories = sorted(set(a) | set(b))
    k = len(categories)
    if k < 2:
        raise ValueError(
            "weighted kappa needs at least two distinct categories; only one in use"
        )
    index = {c: i for i, c in enumerate(categories)}

    def weight(i, j):
        d = abs(i - j) / (k - 1)
        return 1.0 - d if weights == "linear" else 1.0 - d * d

    observed = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1

    rows = [sum(observed[i]) for i in range(k)]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    p_o = sum(
        weight(i, j) * observed[i][j] for i in range(k) for j in range(k)
    ) / n
    p_e = sum(
        weight(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k)
    ) / (n * n)

    if p_e == 1.0:
        raise ValueError("expected agreement is 1.0; weighted kappa is undefined")
    return (p_o - p_e) / (1.0 - p_e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): weighted kappa for ordinal rubrics"
```

---

### Task 3: Fleiss' kappa for three or more raters

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Produces: `agreement.fleiss_kappa(counts: Sequence[Sequence[int]]) -> float`. `counts` is one row per item, holding the number of raters who chose each category. Every row must sum to the same total. Raises `ValueError` on ragged rows, fewer than two raters, or `P_e == 1.0`.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`:

```python
class TestFleissKappa(unittest.TestCase):
    def test_known_answer(self):
        """3 raters, 4 items, 2 categories.

        P_i = (sum(n_ij^2) - n) / (n(n-1)), n = 3:
          [3,0] -> (9 - 3)/6 = 1
          [2,1] -> (5 - 3)/6 = 1/3
          [0,3] -> (9 - 3)/6 = 1
          [1,2] -> (5 - 3)/6 = 1/3
        P_bar = (1 + 1/3 + 1 + 1/3)/4 = 2/3
        p_j = (6/12, 6/12) = (0.5, 0.5); P_e = 0.25 + 0.25 = 0.5
        kappa = (2/3 - 1/2) / (1 - 1/2) = (1/6)/(1/2) = 1/3
        """
        counts = [[3, 0], [2, 1], [0, 3], [1, 2]]
        self.assertAlmostEqual(agreement.fleiss_kappa(counts), 1 / 3, places=10)

    def test_perfect_agreement_is_one(self):
        counts = [[3, 0], [0, 3], [3, 0]]
        self.assertAlmostEqual(agreement.fleiss_kappa(counts), 1.0, places=10)

    def test_ragged_rows_raise(self):
        with self.assertRaises(ValueError):
            agreement.fleiss_kappa([[3, 0], [2, 0]])

    def test_single_rater_raises(self):
        with self.assertRaises(ValueError):
            agreement.fleiss_kappa([[1, 0], [0, 1]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestFleissKappa`
Expected: FAIL — `AttributeError: module 'evalstats.agreement' has no attribute 'fleiss_kappa'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/agreement.py`:

```python
def fleiss_kappa(counts):
    """Fleiss' kappa for a fixed number of raters per item.

    `counts` is one row per item giving how many raters chose each category, so
    `[[3, 0], [2, 1]]` means three raters picked category 0 for item 1, and two
    picked category 0 with one picking category 1 for item 2.

    Unlike Cohen's kappa this does not require the same raters on every item,
    only the same *number* of raters. Use krippendorff_alpha when even that does
    not hold.

    Raises ValueError on ragged rows, fewer than two raters, no items, or when
    expected agreement is exactly 1.0.
    """
    if not counts:
        raise ValueError("no items supplied")
    n_raters = sum(counts[0])
    if n_raters < 2:
        raise ValueError("Fleiss' kappa needs at least two raters per item")
    if any(sum(row) != n_raters for row in counts):
        raise ValueError(
            "every item must have the same number of ratings; use "
            "krippendorff_alpha for ragged or missing data"
        )

    n_items = len(counts)
    n_categories = len(counts[0])

    agreements = [
        (sum(c * c for c in row) - n_raters) / (n_raters * (n_raters - 1))
        for row in counts
    ]
    p_bar = sum(agreements) / n_items

    proportions = [
        sum(row[j] for row in counts) / (n_items * n_raters)
        for j in range(n_categories)
    ]
    p_e = sum(p * p for p in proportions)

    if p_e == 1.0:
        raise ValueError("expected agreement is 1.0; kappa is undefined")
    return (p_bar - p_e) / (1.0 - p_e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 15 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): Fleiss' kappa for three or more raters"
```

---

### Task 4: Krippendorff's alpha — the coincidence matrix and nominal metric

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Produces:
  - `agreement.krippendorff_alpha(units, level="nominal") -> float`. `units` is one list per item holding that item's ratings, with `None` for a missing rating. Items with fewer than two present ratings are dropped, since they carry no pairable information. Raises `ValueError` if no unit survives.
  - `agreement._coincidence(units)` — internal, returns `(matrix, values, marginals, total)`. Later tasks reuse it for the ordinal and interval metrics.

Krippendorff's alpha is the flagship statistic of this package: it takes any number of raters, tolerates missing data natively, and switches measurement level without changing the estimator.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`:

```python
class TestKrippendorffNominal(unittest.TestCase):
    def test_known_answer_complete_data(self):
        """Four units, two raters, no missing data.

        units = [[a,a], [a,b], [b,b], [b,b]]
        Each unit has m = 2 ratings, so each ordered pair carries weight
        1/(m-1) = 1. The coincidence matrix is o_aa = 2, o_ab = 1, o_ba = 1,
        o_bb = 4, total n = 8, marginals n_a = 3, n_b = 5.
        D_o = (o_ab + o_ba)/n = 2/8 = 0.25
        D_e = (n_a*n_b + n_b*n_a)/(n(n-1)) = 30/56
        alpha = 1 - 0.25/(30/56) = 1 - 7/15 = 8/15
        """
        units = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(units), 8 / 15, places=10
        )

    def test_known_answer_with_missing_data(self):
        """Three raters, four units, two ratings missing.

        units = [[a,a,a], [a,b,b], [b,b,None], [None,b,b]]
        The first two units have m = 3, so each of their 6 ordered pairs carries
        weight 1/2; the last two have m = 2 and carry weight 1.
        Coincidence: o_aa = 3, o_ab = 1, o_ba = 1, o_bb = 5, n = 10,
        marginals n_a = 4, n_b = 6.
        D_o = 2/10 = 0.2
        D_e = (24 + 24)/(10*9) = 48/90
        alpha = 1 - 0.2/(48/90) = 1 - 0.375 = 0.625
        """
        units = [
            ["a", "a", "a"],
            ["a", "b", "b"],
            ["b", "b", None],
            [None, "b", "b"],
        ]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(units), 0.625, places=10
        )

    def test_perfect_agreement_is_one(self):
        units = [["a", "a"], ["b", "b"], ["c", "c"], ["a", "a"]]
        self.assertAlmostEqual(agreement.krippendorff_alpha(units), 1.0, places=10)

    def test_systematic_disagreement_is_negative(self):
        """Two raters who always disagree do worse than chance."""
        units = [["a", "b"], ["b", "a"], ["a", "b"], ["b", "a"]]
        self.assertLess(agreement.krippendorff_alpha(units), 0.0)

    def test_units_with_one_rating_are_dropped(self):
        """A unit rated once carries no pairable information, so adding one
        must not change the result."""
        base = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        padded = base + [["a", None]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(base),
            agreement.krippendorff_alpha(padded),
            places=10,
        )

    def test_no_pairable_units_raises(self):
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha([["a", None], ["b", None]])

    def test_unknown_level_raises(self):
        with self.assertRaises(ValueError):
            agreement.krippendorff_alpha([["a", "a"], ["a", "b"]], level="ratio")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestKrippendorffNominal`
Expected: FAIL — `AttributeError: module 'evalstats.agreement' has no attribute 'krippendorff_alpha'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/agreement.py`:

```python
def _coincidence(units):
    """Build Krippendorff's coincidence matrix from per-unit rating lists.

    Returns (matrix, values, marginals, total). Each unit contributes every
    ordered pair of its present ratings, weighted 1/(m-1) where m is how many
    ratings that unit actually has. That weighting is what lets units with
    different numbers of raters sit in the same matrix.
    """
    present = [[v for v in unit if v is not None] for unit in units]
    pairable = [unit for unit in present if len(unit) >= 2]
    if not pairable:
        raise ValueError(
            "no unit has two or more ratings; alpha needs at least one pairable unit"
        )

    values = sorted({v for unit in pairable for v in unit})
    index = {v: i for i, v in enumerate(values)}
    k = len(values)

    matrix = [[0.0] * k for _ in range(k)]
    for unit in pairable:
        m = len(unit)
        weight = 1.0 / (m - 1)
        for i, x in enumerate(unit):
            for j, y in enumerate(unit):
                if i != j:
                    matrix[index[x]][index[y]] += weight

    marginals = [sum(row) for row in matrix]
    total = sum(marginals)
    return matrix, values, marginals, total


def _nominal_metric(values, marginals):
    """Squared difference for unordered categories: 0 if equal, 1 if not."""

    def delta(i, j):
        return 0.0 if i == j else 1.0

    return delta


_METRICS = {"nominal": _nominal_metric}


def krippendorff_alpha(units, level="nominal"):
    """Krippendorff's alpha — chance-corrected agreement for any number of raters.

    `units` is one list per item holding that item's ratings, using None for a
    rating that is absent. Units with fewer than two present ratings are dropped
    because they carry no pairable information.

    `level` selects the difference function: "nominal" for unordered categories.
    Later tasks add "ordinal" and "interval".

    Returns 1.0 when expected disagreement is zero, which happens when every
    rating in the data is identical — agreement is perfect and the chance
    correction has nothing to correct.

    Raises ValueError when no unit is pairable or the level is unknown.
    """
    if level not in _METRICS:
        raise ValueError(
            "level must be one of %s" % ", ".join(sorted(_METRICS))
        )

    matrix, values, marginals, total = _coincidence(units)
    delta = _METRICS[level](values, marginals)
    k = len(values)

    observed = sum(
        matrix[i][j] * delta(i, j) for i in range(k) for j in range(k)
    ) / total
    expected = sum(
        marginals[i] * marginals[j] * delta(i, j)
        for i in range(k)
        for j in range(k)
    ) / (total * (total - 1))

    if expected == 0.0:
        return 1.0
    return 1.0 - observed / expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 22 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): Krippendorff's alpha with the nominal metric"
```

---

### Task 5: Krippendorff's ordinal and interval metrics

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Consumes: `agreement._coincidence`, `agreement._METRICS` from Task 4.
- Produces: `agreement.krippendorff_alpha(units, level=...)` now accepts `"ordinal"` and `"interval"`. `"interval"` requires numeric values and raises `TypeError` otherwise.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`:

```python
class TestKrippendorffLevels(unittest.TestCase):
    """One fixture, three known answers.

    units = [[1,1], [2,2], [1,2], [3,3]]
    Coincidence: o_11 = 2, o_22 = 2, o_12 = 1, o_21 = 1, o_33 = 2
    total n = 8, marginals n_1 = 3, n_2 = 3, n_3 = 2
    """

    UNITS = [[1, 1], [2, 2], [1, 2], [3, 3]]

    def test_nominal(self):
        """delta = 1 for every unequal pair.
        D_o = 2/8 = 0.25
        D_e = (9 + 9 + 6 + 6 + 6 + 6)/(8*7) = 42/56 = 0.75
        alpha = 1 - 0.25/0.75 = 2/3
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="nominal")
        self.assertAlmostEqual(got, 2 / 3, places=10)

    def test_interval(self):
        """delta(c,k) = (v_c - v_k)^2, so delta(1,2)=1, delta(1,3)=4, delta(2,3)=1.
        D_o = (1*1 + 1*1)/8 = 0.25
        D_e = [3*3*1*2 + 3*2*4*2 + 3*2*1*2]/(8*7) = (18 + 48 + 12)/56 = 78/56
        alpha = 1 - 0.25*56/78 = 1 - 7/39 = 32/39
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="interval")
        self.assertAlmostEqual(got, 32 / 39, places=10)

    def test_ordinal(self):
        """delta(c,k) = (sum of marginals from c to k, minus half the endpoints)^2.
        delta(1,2) = (3 + 3 - 3)^2 = 9
        delta(1,3) = (3 + 3 + 2 - 2.5)^2 = 5.5^2 = 30.25
        delta(2,3) = (3 + 2 - 2.5)^2 = 2.5^2 = 6.25
        D_o = (9 + 9)/8 = 2.25
        D_e = [3*3*9*2 + 3*2*30.25*2 + 3*2*6.25*2]/56 = (162 + 363 + 75)/56 = 600/56
        alpha = 1 - 2.25*56/600 = 1 - 0.21 = 0.79
        """
        got = agreement.krippendorff_alpha(self.UNITS, level="ordinal")
        self.assertAlmostEqual(got, 0.79, places=10)

    def test_interval_punishes_distant_disagreement_more(self):
        """A one-step disagreement should score higher than a three-step one."""
        near = [[1, 1], [2, 2], [1, 2], [4, 4]]
        far = [[1, 1], [2, 2], [1, 4], [4, 4]]
        self.assertGreater(
            agreement.krippendorff_alpha(near, level="interval"),
            agreement.krippendorff_alpha(far, level="interval"),
        )

    def test_nominal_ignores_distance(self):
        """The same two datasets are indistinguishable to the nominal metric,
        which is exactly why an ordinal rubric must not use it."""
        near = [[1, 1], [2, 2], [1, 2], [4, 4]]
        far = [[1, 1], [2, 2], [1, 4], [4, 4]]
        self.assertAlmostEqual(
            agreement.krippendorff_alpha(near, level="nominal"),
            agreement.krippendorff_alpha(far, level="nominal"),
            places=10,
        )

    def test_interval_on_non_numeric_raises(self):
        with self.assertRaises(TypeError):
            agreement.krippendorff_alpha([["a", "a"], ["a", "b"]], level="interval")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestKrippendorffLevels`
Expected: FAIL — `ValueError: level must be one of nominal` on the interval and ordinal cases

- [ ] **Step 3: Write the implementation**

In `genai-eval/scripts/evalstats/agreement.py`, add the two metric factories immediately after `_nominal_metric`, then replace the `_METRICS` line:

```python
def _interval_metric(values, marginals):
    """Squared numeric distance. Requires values to be numbers."""
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(
                "the interval metric needs numeric ratings; got %r" % (v,)
            )

    def delta(i, j):
        d = values[i] - values[j]
        return float(d * d)

    return delta


def _ordinal_metric(values, marginals):
    """Krippendorff's ordinal metric.

    The distance between two ranks depends on how many observations sit between
    them: the squared sum of the marginals spanning the interval, less half of
    each endpoint. Two adjacent categories are far apart if the scale is
    crowded there and close together if it is sparse, which is the behaviour an
    ordinal rubric actually has.
    """
    cumulative = []
    running = 0.0
    for m in marginals:
        running += m
        cumulative.append(running)

    def delta(i, j):
        if i == j:
            return 0.0
        lo, hi = (i, j) if i < j else (j, i)
        span = cumulative[hi] - (cumulative[lo] - marginals[lo])
        adjusted = span - (marginals[lo] + marginals[hi]) / 2.0
        return adjusted * adjusted

    return delta


_METRICS = {
    "nominal": _nominal_metric,
    "ordinal": _ordinal_metric,
    "interval": _interval_metric,
}
```

Delete the old single-entry `_METRICS = {"nominal": _nominal_metric}` line so only the three-entry version remains.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 28 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): Krippendorff ordinal and interval metrics"
```

---

### Task 6: Bootstrap confidence intervals, resampled by item

**Files:**
- Modify: `genai-eval/scripts/evalstats/agreement.py`
- Modify: `genai-eval/scripts/tests/test_agreement.py`

**Interfaces:**
- Produces: `agreement.bootstrap_ci(units, statistic, n_resamples=2000, confidence=0.95, seed=None) -> (float, float)`. `statistic` is a callable taking a list of units and returning a float. Resamples **whole units**, never individual ratings. Raises `ValueError` on fewer than two units or when more than half the resamples are degenerate.

A point estimate with no interval is the thing the SOP's Step 10 forbids, and this is the function that supplies the interval. Resampling by unit rather than by rating is the part that is easy to get wrong: ratings cluster inside an item, and resampling them independently produces intervals that are far too narrow.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_agreement.py`:

```python
import random


class TestBootstrapCI(unittest.TestCase):
    def _units(self, n_agree, n_disagree):
        return [["a", "a"]] * n_agree + [["a", "b"]] * n_disagree

    def test_is_deterministic_for_a_fixed_seed(self):
        units = self._units(30, 10)
        first = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=200, seed=7
        )
        second = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=200, seed=7
        )
        self.assertEqual(first, second)

    def test_interval_brackets_the_point_estimate(self):
        units = self._units(30, 10)
        point = agreement.krippendorff_alpha(units)
        low, high = agreement.bootstrap_ci(
            units, agreement.krippendorff_alpha, n_resamples=500, seed=11
        )
        self.assertLessEqual(low, point)
        self.assertLessEqual(point, high)

    def test_more_units_give_a_narrower_interval(self):
        """The whole point of reporting n alongside an interval."""
        small = agreement.bootstrap_ci(
            self._units(15, 5), agreement.krippendorff_alpha,
            n_resamples=400, seed=3,
        )
        large = agreement.bootstrap_ci(
            self._units(300, 100), agreement.krippendorff_alpha,
            n_resamples=400, seed=3,
        )
        self.assertLess(large[1] - large[0], small[1] - small[0])

    def test_too_few_units_raises(self):
        with self.assertRaises(ValueError):
            agreement.bootstrap_ci([["a", "a"]], agreement.krippendorff_alpha)

    def test_mostly_degenerate_resamples_raise(self):
        """A statistic that almost always fails must not silently yield an
        interval computed from the handful of resamples that happened to work."""

        def almost_always_fails(units):
            raise ValueError("degenerate")

        with self.assertRaises(ValueError):
            agreement.bootstrap_ci(
                self._units(10, 10), almost_always_fails, n_resamples=50, seed=1
            )

    def test_nominal_coverage_is_close_to_the_stated_level(self):
        """Simulation check: a nominal 95% interval should cover the truth about
        95% of the time. Loose bounds, since this is 150 simulations."""
        rng = random.Random(20260905)
        truth_units = self._units(300, 100)
        truth = agreement.krippendorff_alpha(truth_units)

        covered = 0
        trials = 150
        for _ in range(trials):
            sample = [truth_units[rng.randrange(len(truth_units))] for _ in range(60)]
            try:
                low, high = agreement.bootstrap_ci(
                    sample, agreement.krippendorff_alpha,
                    n_resamples=300, seed=rng.randrange(10 ** 6),
                )
            except ValueError:
                continue
            if low <= truth <= high:
                covered += 1
        self.assertGreater(covered / trials, 0.85)
        self.assertLessEqual(covered / trials, 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_agreement.py -k TestBootstrapCI`
Expected: FAIL — `AttributeError: module 'evalstats.agreement' has no attribute 'bootstrap_ci'`

- [ ] **Step 3: Write the implementation**

Add `import random` to the top of `genai-eval/scripts/evalstats/agreement.py`, then append:

```python
def bootstrap_ci(units, statistic, n_resamples=2000, confidence=0.95, seed=None):
    """Percentile bootstrap confidence interval for a unit-level statistic.

    `units` is the same per-item structure the agreement functions take, and
    `statistic` is any callable mapping a list of units to a float.

    Resampling is by *unit*, not by individual rating. Ratings cluster within an
    item — two raters looking at the same hard item disagree together — so
    resampling ratings independently breaks that dependence and produces
    intervals that are far too narrow.

    Resamples on which `statistic` raises ValueError are skipped, since a
    resample can legitimately contain a single category. If more than half of
    them fail, that is not a skippable edge case and this raises rather than
    returning an interval computed from the survivors.
    """
    n = len(units)
    if n < 2:
        raise ValueError("bootstrap needs at least two units")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    rng = random.Random(seed)
    estimates = []
    for _ in range(n_resamples):
        sample = [units[rng.randrange(n)] for _ in range(n)]
        try:
            estimates.append(statistic(sample))
        except ValueError:
            continue

    if len(estimates) < n_resamples / 2:
        raise ValueError(
            "%d of %d resamples were degenerate; the sample is too small or too "
            "homogeneous for a bootstrap interval" % (n_resamples - len(estimates), n_resamples)
        )

    estimates.sort()
    tail = (1.0 - confidence) / 2.0
    low_index = int(tail * len(estimates))
    high_index = min(len(estimates) - 1, int((1.0 - tail) * len(estimates)))
    return estimates[low_index], estimates[high_index]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_agreement.py`
Expected: PASS — `Ran 34 tests ... OK`. The coverage simulation takes roughly 5–20 seconds; everything else is instant.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/agreement.py genai-eval/scripts/tests/test_agreement.py
git commit -m "feat(genai-eval): bootstrap confidence intervals resampled by item"
```

---

### Task 7: Item difficulty, discrimination, and flagging

**Files:**
- Create: `genai-eval/scripts/evalstats/items.py`
- Create: `genai-eval/scripts/tests/test_items.py`

**Interfaces:**
- Produces:
  - `items.item_difficulty(responses: Sequence[int]) -> float` — proportion passing.
  - `items.point_biserial(responses: Sequence[int], totals: Sequence[float]) -> Optional[float]` — returns `None` when every response is identical or total-score variance is zero.
  - `items.flag_items(matrix: Sequence[Sequence[int]]) -> List[dict]` — one dict per item: `{"index", "difficulty", "discrimination", "flags"}` where `flags` is a list drawn from `"mis-keyed"`, `"non-discriminating"`, `"ceiling"`, `"floor"`, `"undefined"`.

The single highest-value thing item analysis finds is a **mis-keyed item** — one where the better candidates do *worse*. That shows up as a negative point-biserial and nothing else catches it.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_items.py`:

```python
#!/usr/bin/env python3
"""Known-answer tests for evalstats.items. Run directly: python3 test_items.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import items

# A perfectly Guttman-scaled response matrix: 5 examinees, 4 items.
#         I1 I2 I3 I4   total
#   E1     1  1  1  1     4
#   E2     1  1  1  0     3
#   E3     1  1  0  0     2
#   E4     1  0  0  0     1
#   E5     0  0  0  0     0
GUTTMAN = [
    [1, 1, 1, 1],
    [1, 1, 1, 0],
    [1, 1, 0, 0],
    [1, 0, 0, 0],
    [0, 0, 0, 0],
]


def _column(matrix, j):
    return [row[j] for row in matrix]


def _totals(matrix):
    return [sum(row) for row in matrix]


class TestDifficulty(unittest.TestCase):
    def test_known_answers(self):
        """Column pass rates are 4/5, 3/5, 2/5, 1/5."""
        expected = [0.8, 0.6, 0.4, 0.2]
        for j, want in enumerate(expected):
            self.assertAlmostEqual(
                items.item_difficulty(_column(GUTTMAN, j)), want, places=10
            )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            items.item_difficulty([])


class TestPointBiserial(unittest.TestCase):
    def test_known_answer_item_two(self):
        """Item 2 (index 1). Totals are [4,3,2,1,0], mean 2, population sd sqrt(2).
        Passers scored [4,3,2] -> mean 3; failers scored [1,0] -> mean 0.5.
        p = 0.6, q = 0.4.
        r_pb = (3 - 0.5)/sqrt(2) * sqrt(0.24) = 2.5 * sqrt(0.12) = sqrt(3)/2
        """
        import math

        got = items.point_biserial(_column(GUTTMAN, 1), _totals(GUTTMAN))
        self.assertAlmostEqual(got, math.sqrt(3) / 2, places=10)

    def test_known_answer_item_one(self):
        """Item 1 (index 0). Passers [4,3,2,1] -> mean 2.5; failers [0] -> mean 0.
        p = 0.8, q = 0.2.
        r_pb = 2.5/sqrt(2) * sqrt(0.16) = sqrt(2)/2
        """
        import math

        got = items.point_biserial(_column(GUTTMAN, 0), _totals(GUTTMAN))
        self.assertAlmostEqual(got, math.sqrt(2) / 2, places=10)

    def test_mis_keyed_item_is_negative(self):
        """An item the strongest candidates fail must produce a negative value.
        This is the case item analysis exists to find."""
        reversed_column = [0, 0, 0, 1, 1]
        got = items.point_biserial(reversed_column, _totals(GUTTMAN))
        self.assertLess(got, 0.0)

    def test_all_pass_returns_none(self):
        self.assertIsNone(items.point_biserial([1, 1, 1, 1, 1], _totals(GUTTMAN)))

    def test_zero_total_variance_returns_none(self):
        self.assertIsNone(items.point_biserial([1, 0, 1, 0, 1], [2, 2, 2, 2, 2]))


class TestFlagItems(unittest.TestCase):
    def test_guttman_items_are_all_clean(self):
        report = items.flag_items(GUTTMAN)
        self.assertEqual(len(report), 4)
        for row in report:
            self.assertEqual(row["flags"], [])

    def test_flags_a_mis_keyed_item(self):
        matrix = [row[:] for row in GUTTMAN]
        for i, row in enumerate(matrix):
            row.append(1 if i >= 3 else 0)  # strongest candidates fail it
        report = items.flag_items(matrix)
        self.assertIn("mis-keyed", report[4]["flags"])

    def test_flags_ceiling_and_floor_items(self):
        matrix = [row + [1, 0] for row in GUTTMAN]
        report = items.flag_items(matrix)
        self.assertIn("ceiling", report[4]["flags"])
        self.assertIn("floor", report[5]["flags"])

    def test_ragged_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.flag_items([[1, 0], [1]])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_items.py`
Expected: FAIL — `ImportError: cannot import name 'items' from 'evalstats'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/evalstats/items.py`:

```python
"""Classical test theory for eval item pools.

An eval is a test, and a test made of items nobody gets wrong measures nothing.
These functions answer the two questions Step 7 of the SOP asks: how hard is
each item, and does it separate stronger systems from weaker ones?

All functions take binary responses (1 = passed the item, 0 = failed).
"""

import math
import statistics

# An item whose point-biserial sits below this separates nothing useful.
DISCRIMINATION_FLOOR = 0.2
# Items passed or failed by nearly everyone carry almost no information.
CEILING = 0.95
FLOOR = 0.05


def item_difficulty(responses):
    """Proportion of respondents who passed this item.

    Confusingly, higher means *easier* — this is the classical p-value, and the
    convention is worth keeping because every psychometrics reference uses it.
    """
    if not responses:
        raise ValueError("no responses supplied")
    return sum(responses) / len(responses)


def point_biserial(responses, totals):
    """Point-biserial correlation between one item and total score.

    This is item discrimination: how well passing this item predicts doing well
    overall. Near zero means the item separates nobody. Negative means the item
    is mis-keyed or measures something the rest of the test does not — the
    highest-value finding in the whole procedure.

    Returns None rather than a number when the correlation is undefined: every
    response identical, or no variance in total scores.
    """
    if len(responses) != len(totals):
        raise ValueError("responses and totals must be the same length")
    if not responses:
        raise ValueError("no responses supplied")

    passed = [t for r, t in zip(responses, totals) if r == 1]
    failed = [t for r, t in zip(responses, totals) if r == 0]
    if not passed or not failed:
        return None

    spread = statistics.pstdev(totals)
    if spread == 0:
        return None

    p = len(passed) / len(responses)
    mean_gap = statistics.mean(passed) - statistics.mean(failed)
    return (mean_gap / spread) * math.sqrt(p * (1.0 - p))


def flag_items(matrix):
    """Difficulty, discrimination and flags for every item in a response matrix.

    `matrix` is one row per respondent, one column per item, entries 0 or 1.
    Returns one dict per item with keys index, difficulty, discrimination and
    flags. An empty flag list means the item is doing its job.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    width = len(matrix[0])
    if width == 0:
        raise ValueError("no items supplied")
    if any(len(row) != width for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    totals = [sum(row) for row in matrix]
    report = []
    for j in range(width):
        column = [row[j] for row in matrix]
        difficulty = item_difficulty(column)
        discrimination = point_biserial(column, totals)

        flags = []
        if difficulty >= CEILING:
            flags.append("ceiling")
        if difficulty <= FLOOR:
            flags.append("floor")
        if discrimination is None:
            flags.append("undefined")
        elif discrimination < 0:
            flags.append("mis-keyed")
        elif discrimination < DISCRIMINATION_FLOOR:
            flags.append("non-discriminating")

        report.append(
            {
                "index": j,
                "difficulty": difficulty,
                "discrimination": discrimination,
                "flags": flags,
            }
        )
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_items.py`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/items.py genai-eval/scripts/tests/test_items.py
git commit -m "feat(genai-eval): item difficulty, discrimination, and flagging"
```

---

### Task 8: KR-20 reliability

**Files:**
- Modify: `genai-eval/scripts/evalstats/items.py`
- Modify: `genai-eval/scripts/tests/test_items.py`

**Interfaces:**
- Produces: `items.kr20(matrix: Sequence[Sequence[int]]) -> Optional[float]`. Returns `None` when total-score variance is zero. Raises `ValueError` on fewer than two items or a ragged matrix. **Uses population variance (divisor N)**, which is the classical form — sample variance gives a different number and the tests pin the classical one.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_items.py`:

```python
class TestKR20(unittest.TestCase):
    def test_known_answer(self):
        """4 items, 5 examinees, Guttman matrix.

        Item p values: 0.8, 0.6, 0.4, 0.2
        sum of p*q = 0.16 + 0.24 + 0.24 + 0.16 = 0.80
        totals [4,3,2,1,0], mean 2, population variance 10/5 = 2.0
        KR-20 = (4/3) * (1 - 0.80/2.0) = (4/3) * 0.6 = 0.8
        """
        self.assertAlmostEqual(items.kr20(GUTTMAN), 0.8, places=10)

    def test_zero_variance_returns_none(self):
        self.assertIsNone(items.kr20([[1, 1], [1, 1], [1, 1]]))

    def test_single_item_raises(self):
        with self.assertRaises(ValueError):
            items.kr20([[1], [0], [1]])

    def test_ragged_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.kr20([[1, 0], [1]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_items.py -k TestKR20`
Expected: FAIL — `AttributeError: module 'evalstats.items' has no attribute 'kr20'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/items.py`:

```python
def kr20(matrix):
    """Kuder-Richardson 20 — internal-consistency reliability for binary items.

    Answers "if I built a second eval from the same item pool, how much would
    the scores agree?". Low reliability caps every comparison you can make: an
    instrument that disagrees with itself cannot detect a difference between two
    models.

    Uses the *population* variance of total scores (divisor N), which is the
    classical KR-20 form. Sample variance produces a slightly higher number, and
    mixing the two silently across a codebase is a real source of irreproducible
    reliability figures.

    Returns None when total-score variance is zero, since reliability is
    undefined rather than zero when nobody differs.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    n_items = len(matrix[0])
    if n_items < 2:
        raise ValueError("KR-20 needs at least two items")
    if any(len(row) != n_items for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    totals = [sum(row) for row in matrix]
    total_variance = statistics.pvariance(totals)
    if total_variance == 0:
        return None

    item_variance_sum = 0.0
    for j in range(n_items):
        column = [row[j] for row in matrix]
        p = sum(column) / len(column)
        item_variance_sum += p * (1.0 - p)

    return (n_items / (n_items - 1)) * (1.0 - item_variance_sum / total_variance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_items.py`
Expected: PASS — `Ran 15 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/items.py genai-eval/scripts/tests/test_items.py
git commit -m "feat(genai-eval): KR-20 internal-consistency reliability"
```

---

### Task 9: Jacobi eigenvalues and a dimensionality summary

**Files:**
- Modify: `genai-eval/scripts/evalstats/items.py`
- Modify: `genai-eval/scripts/tests/test_items.py`

**Interfaces:**
- Produces:
  - `items.eigenvalues_symmetric(matrix, max_sweeps=100, tol=1e-12) -> List[float]` — descending. Raises `ValueError` on a non-square or asymmetric matrix.
  - `items.correlation_matrix(matrix) -> List[List[float]]` — item-by-item Pearson correlations. Items with zero variance get a correlation of 0.0 against everything, including a 1.0 self-correlation, so the matrix stays well-formed.
  - `items.dimensionality(matrix) -> dict` with keys `eigenvalues`, `first_ratio` (share of total variance on the first component), `n_above_one` (Kaiser count).

This is as far as this package goes toward Gate 8's internal-structure evidence. Real factor analysis needs numpy; the spec records that boundary and `references/item-analysis.md` will state it plainly for readers in Phase 3.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_items.py`:

```python
class TestEigenvalues(unittest.TestCase):
    def test_two_by_two_known_answer(self):
        """A 2x2 correlation matrix [[1, r], [r, 1]] has eigenvalues 1+r and 1-r.
        With r = 0.6 that is 1.6 and 0.4."""
        got = items.eigenvalues_symmetric([[1.0, 0.6], [0.6, 1.0]])
        self.assertAlmostEqual(got[0], 1.6, places=9)
        self.assertAlmostEqual(got[1], 0.4, places=9)

    def test_equicorrelated_three_by_three_known_answer(self):
        """An equicorrelated 3x3 with r = 0.5 has eigenvalues 1+2r = 2.0 and
        1-r = 0.5 twice."""
        m = [[1.0, 0.5, 0.5], [0.5, 1.0, 0.5], [0.5, 0.5, 1.0]]
        got = items.eigenvalues_symmetric(m)
        self.assertAlmostEqual(got[0], 2.0, places=9)
        self.assertAlmostEqual(got[1], 0.5, places=9)
        self.assertAlmostEqual(got[2], 0.5, places=9)

    def test_identity_has_unit_eigenvalues(self):
        got = items.eigenvalues_symmetric([[1.0, 0.0], [0.0, 1.0]])
        self.assertAlmostEqual(got[0], 1.0, places=9)
        self.assertAlmostEqual(got[1], 1.0, places=9)

    def test_trace_is_preserved(self):
        """Eigenvalues of a symmetric matrix sum to its trace."""
        m = [[1.0, 0.3, -0.2], [0.3, 1.0, 0.4], [-0.2, 0.4, 1.0]]
        self.assertAlmostEqual(sum(items.eigenvalues_symmetric(m)), 3.0, places=9)

    def test_asymmetric_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.eigenvalues_symmetric([[1.0, 0.5], [0.2, 1.0]])

    def test_non_square_matrix_raises(self):
        with self.assertRaises(ValueError):
            items.eigenvalues_symmetric([[1.0, 0.5]])


class TestDimensionality(unittest.TestCase):
    def test_returns_one_eigenvalue_per_item(self):
        result = items.dimensionality(GUTTMAN)
        self.assertEqual(len(result["eigenvalues"]), 4)

    def test_eigenvalues_sum_to_item_count(self):
        """A correlation matrix has 1.0 down its diagonal, so its trace equals
        its size, and eigenvalues sum to the trace. Four items always total 4."""
        result = items.dimensionality(GUTTMAN)
        self.assertAlmostEqual(sum(result["eigenvalues"]), 4.0, places=9)

    def test_eigenvalues_are_descending(self):
        values = items.dimensionality(GUTTMAN)["eigenvalues"]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_summary_fields_agree_with_the_eigenvalues(self):
        result = items.dimensionality(GUTTMAN)
        values = result["eigenvalues"]
        self.assertAlmostEqual(
            result["first_ratio"], values[0] / sum(values), places=12
        )
        self.assertEqual(
            result["n_above_one"], sum(1 for v in values if v > 1.0)
        )

    def test_duplicated_item_produces_a_zero_eigenvalue(self):
        """Two identical items carry one item's worth of information, so the
        correlation matrix is rank-deficient and its smallest eigenvalue is 0.
        This is the signature of a redundant item in the pool."""
        duplicated = [row + [row[0]] for row in GUTTMAN]
        values = items.dimensionality(duplicated)["eigenvalues"]
        self.assertEqual(len(values), 5)
        self.assertAlmostEqual(values[-1], 0.0, places=8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_items.py -k Eigen`
Expected: FAIL — `AttributeError: module 'evalstats.items' has no attribute 'eigenvalues_symmetric'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/items.py`:

```python
def eigenvalues_symmetric(matrix, max_sweeps=100, tol=1e-12):
    """Eigenvalues of a real symmetric matrix, descending, via Jacobi rotation.

    Jacobi is slow for large matrices and perfectly adequate here: item pools
    have tens of items, not thousands, and it needs nothing but the standard
    library.
    """
    n = len(matrix)
    if n == 0:
        raise ValueError("empty matrix")
    if any(len(row) != n for row in matrix):
        raise ValueError("matrix must be square")
    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j] - matrix[j][i]) > 1e-9:
                raise ValueError("matrix must be symmetric")

    a = [list(map(float, row)) for row in matrix]

    for _ in range(max_sweeps):
        off_diagonal = math.sqrt(
            sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        )
        if off_diagonal < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < tol:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                sign = 1.0 if theta >= 0 else -1.0
                t = sign / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk

    return sorted((a[i][i] for i in range(n)), reverse=True)


def correlation_matrix(matrix):
    """Item-by-item Pearson correlation matrix from a response matrix.

    An item with zero variance correlates with nothing, so its row and column
    are zero apart from a 1.0 on the diagonal. That keeps the matrix square and
    symmetric instead of propagating a division by zero.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    n_items = len(matrix[0])
    if any(len(row) != n_items for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    columns = [[row[j] for row in matrix] for j in range(n_items)]
    means = [statistics.mean(c) for c in columns]
    spreads = [statistics.pstdev(c) for c in columns]

    result = [[0.0] * n_items for _ in range(n_items)]
    for i in range(n_items):
        result[i][i] = 1.0
        for j in range(i + 1, n_items):
            if spreads[i] == 0 or spreads[j] == 0:
                continue
            covariance = sum(
                (x - means[i]) * (y - means[j])
                for x, y in zip(columns[i], columns[j])
            ) / len(matrix)
            r = covariance / (spreads[i] * spreads[j])
            result[i][j] = result[j][i] = r
    return result


def dimensionality(matrix):
    """Eigenvalue summary of a response matrix's item correlation structure.

    Gate 8's internal-structure category asks whether the items behave like
    measurements of one thing. A first component carrying most of the variance
    with everything else below 1.0 is consistent with that; several components
    above 1.0 says the eval is measuring more than one construct and the single
    headline score is hiding it.

    This is a scree summary, not factor analysis. Real factor analysis needs
    numpy and is out of scope for this package.
    """
    correlations = correlation_matrix(matrix)
    values = eigenvalues_symmetric(correlations)
    total = sum(values)
    return {
        "eigenvalues": values,
        "first_ratio": (values[0] / total) if total > 0 else None,
        "n_above_one": sum(1 for v in values if v > 1.0),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_items.py`
Expected: PASS — `Ran 26 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/items.py genai-eval/scripts/tests/test_items.py
git commit -m "feat(genai-eval): Jacobi eigenvalues and dimensionality summary"
```

---

### Task 10: Power — required n and minimum detectable effect

**Files:**
- Create: `genai-eval/scripts/evalstats/power.py`
- Create: `genai-eval/scripts/tests/test_power.py`

**Interfaces:**
- Produces:
  - `power.n_required_two_proportion(p1, p2, alpha=0.05, power=0.80) -> float` — per group, unrounded. Raises `ValueError` if either proportion is outside `(0, 1)` or the two are equal.
  - `power.mde_two_proportion(n, baseline, alpha=0.05, power=0.80, direction="up") -> Optional[float]` — the nearest detectable proportion given `n` per group, found by bisection. Returns `None` when no detectable value exists in range.

This is Gate 7. Most A-vs-B model calls in practice are made on sample sizes that cannot support them, and this function is what turns that from an opinion into a number.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_power.py`:

```python
#!/usr/bin/env python3
"""Known-answer tests for evalstats.power. Run directly: python3 test_power.py"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import power


class TestRequiredN(unittest.TestCase):
    def test_known_answer(self):
        """Detecting 0.80 vs 0.85 at alpha=0.05, power=0.80.

        z(0.975) = 1.9599639845, z(0.80) = 0.8416212336
        (z_a + z_b)^2 = 2.8015852181^2 = 7.8488797
        p1*q1 + p2*q2 = 0.16 + 0.1275 = 0.2875
        (p1 - p2)^2 = 0.0025
        n = 7.8488797 * 0.2875 / 0.0025 = 902.62 per group
        """
        got = power.n_required_two_proportion(0.80, 0.85)
        self.assertAlmostEqual(got, 902.62, places=2)

    def test_bigger_effects_need_fewer_items(self):
        small = power.n_required_two_proportion(0.80, 0.85)
        large = power.n_required_two_proportion(0.80, 0.95)
        self.assertLess(large, small)

    def test_more_power_needs_more_items(self):
        at_80 = power.n_required_two_proportion(0.80, 0.85, power=0.80)
        at_95 = power.n_required_two_proportion(0.80, 0.85, power=0.95)
        self.assertGreater(at_95, at_80)

    def test_symmetric_in_its_arguments(self):
        self.assertAlmostEqual(
            power.n_required_two_proportion(0.80, 0.85),
            power.n_required_two_proportion(0.85, 0.80),
            places=9,
        )

    def test_no_effect_raises(self):
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.80, 0.80)

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.0, 0.85)
        with self.assertRaises(ValueError):
            power.n_required_two_proportion(0.80, 1.0)


class TestMDE(unittest.TestCase):
    def test_round_trips_against_required_n(self):
        """With the n that detects 0.80 vs 0.85, the MDE should land back on
        about 0.85. This checks the two functions against each other rather
        than against a remembered constant."""
        n = power.n_required_two_proportion(0.80, 0.85)
        got = power.mde_two_proportion(math.ceil(n), 0.80)
        self.assertAlmostEqual(got, 0.85, places=3)

    def test_more_items_detect_smaller_effects(self):
        few = power.mde_two_proportion(200, 0.80)
        many = power.mde_two_proportion(2000, 0.80)
        self.assertLess(many - 0.80, few - 0.80)

    def test_downward_direction(self):
        got = power.mde_two_proportion(903, 0.85, direction="down")
        self.assertAlmostEqual(got, 0.80, places=2)

    def test_tiny_sample_returns_none(self):
        """No proportion below 1.0 is detectable against 0.80 with 3 items."""
        self.assertIsNone(power.mde_two_proportion(3, 0.80))

    def test_bad_direction_raises(self):
        with self.assertRaises(ValueError):
            power.mde_two_proportion(903, 0.80, direction="sideways")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_power.py`
Expected: FAIL — `ImportError: cannot import name 'power' from 'evalstats'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/evalstats/power.py`:

```python
"""Statistical power for eval comparisons.

Gate 7 of the SOP asks whether the instrument can detect the smallest difference
you would act on. Most model-versus-model calls are made on item counts far too
small to support them, and the comparison then reports noise with a confident
face. These functions turn "is this enough items?" into a number.
"""

from statistics import NormalDist

_NORMAL = NormalDist()


def n_required_two_proportion(p1, p2, alpha=0.05, power=0.80):
    """Items per group needed to detect p1 versus p2, two-sided.

    Returns an unrounded float; the caller decides whether to ceil it. Uses the
    standard normal approximation with unpooled variance:

        n = (z_{1-alpha/2} + z_{power})^2 * (p1*q1 + p2*q2) / (p1 - p2)^2

    The approximation is unreliable when n*p is very small, which in practice
    means proportions within a whisker of 0 or 1.
    """
    for name, value in (("p1", p1), ("p2", p2)):
        if not 0.0 < value < 1.0:
            raise ValueError("%s must be strictly between 0 and 1" % name)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be strictly between 0 and 1")
    if p1 == p2:
        raise ValueError("p1 and p2 are equal; there is no effect to detect")

    z_alpha = _NORMAL.inv_cdf(1.0 - alpha / 2.0)
    z_power = _NORMAL.inv_cdf(power)
    variance = p1 * (1.0 - p1) + p2 * (1.0 - p2)
    return ((z_alpha + z_power) ** 2) * variance / ((p1 - p2) ** 2)


def mde_two_proportion(n, baseline, alpha=0.05, power=0.80, direction="up",
                       tolerance=1e-7):
    """Smallest detectable proportion against `baseline` with `n` items per group.

    Solved by bisection rather than in closed form, because the required-n
    formula has the unknown proportion inside its own variance term.

    `direction` is "up" to search above the baseline or "down" to search below.
    Returns None when nothing in range is detectable at this sample size — which
    is the honest answer for a small eval, and much more useful than a number.
    """
    if direction not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")
    if not 0.0 < baseline < 1.0:
        raise ValueError("baseline must be strictly between 0 and 1")
    if n < 1:
        raise ValueError("n must be at least 1")

    edge = 1.0 - tolerance if direction == "up" else tolerance
    if n_required_two_proportion(baseline, edge, alpha, power) > n:
        return None

    near, far = baseline, edge
    for _ in range(200):
        middle = (near + far) / 2.0
        if abs(middle - baseline) < tolerance:
            break
        if n_required_two_proportion(baseline, middle, alpha, power) > n:
            near = middle  # not detectable, move away from the baseline
        else:
            far = middle  # detectable, try closer to the baseline
    return far
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_power.py`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/power.py genai-eval/scripts/tests/test_power.py
git commit -m "feat(genai-eval): required-n and minimum detectable effect"
```

---

### Task 11: McNemar's exact test for paired comparisons

**Files:**
- Modify: `genai-eval/scripts/evalstats/power.py`
- Modify: `genai-eval/scripts/tests/test_power.py`

**Interfaces:**
- Produces:
  - `power.mcnemar_exact(b: int, c: int) -> float` — two-sided exact p-value from the discordant counts. `b` is items the first system passed and the second failed; `c` is the reverse. Raises `ValueError` on negatives.
  - `power.discordant_counts(a_results, b_results) -> (int, int)` — turns two parallel binary result lists into `(b, c)`.

When two models run on the *same* items, an unpaired test throws away the pairing and loses power. McNemar uses only the items where the two disagree, which is the information that actually distinguishes them.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_power.py`:

```python
class TestMcNemar(unittest.TestCase):
    def test_known_answer(self):
        """b=3, c=12, so n=15 discordant pairs.
        One tail = [C(15,0)+C(15,1)+C(15,2)+C(15,3)] / 2^15
                 = (1 + 15 + 105 + 455) / 32768 = 576/32768
        Two-sided p = 2 * 576/32768 = 9/256 = 0.03515625
        """
        self.assertAlmostEqual(power.mcnemar_exact(3, 12), 9 / 256, places=12)

    def test_symmetric_in_its_arguments(self):
        self.assertAlmostEqual(
            power.mcnemar_exact(3, 12), power.mcnemar_exact(12, 3), places=12
        )

    def test_balanced_discordance_is_not_significant(self):
        """b == c is the null exactly; the two-sided p caps at 1.0."""
        self.assertEqual(power.mcnemar_exact(5, 5), 1.0)

    def test_no_discordant_pairs_returns_one(self):
        """Two systems that never differ give no evidence of a difference."""
        self.assertEqual(power.mcnemar_exact(0, 0), 1.0)

    def test_lopsided_discordance_is_significant(self):
        self.assertLess(power.mcnemar_exact(0, 12), 0.001)

    def test_negative_counts_raise(self):
        with self.assertRaises(ValueError):
            power.mcnemar_exact(-1, 5)


class TestDiscordantCounts(unittest.TestCase):
    def test_counts_each_direction(self):
        a = [1, 1, 0, 0, 1]
        b = [1, 0, 1, 0, 0]
        # a passed / b failed at indices 1 and 4 -> 2
        # b passed / a failed at index 2 -> 1
        self.assertEqual(power.discordant_counts(a, b), (2, 1))

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            power.discordant_counts([1, 0], [1])

    def test_feeds_mcnemar(self):
        a = [1] * 12 + [0] * 3 + [1] * 20
        b = [0] * 12 + [1] * 3 + [1] * 20
        counts = power.discordant_counts(a, b)
        self.assertEqual(counts, (12, 3))
        self.assertAlmostEqual(power.mcnemar_exact(*counts), 9 / 256, places=12)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_power.py -k McNemar`
Expected: FAIL — `AttributeError: module 'evalstats.power' has no attribute 'mcnemar_exact'`

- [ ] **Step 3: Write the implementation**

Add `import math` to the top of `genai-eval/scripts/evalstats/power.py`, then append:

```python
def discordant_counts(a_results, b_results):
    """Discordant pair counts for two systems run on the same items.

    Returns (b, c): b is the number of items the first system passed and the
    second failed, c the reverse. Items where both agree carry no information
    about which system is better and are discarded.
    """
    if len(a_results) != len(b_results):
        raise ValueError("result sequences must be the same length")
    b = sum(1 for x, y in zip(a_results, b_results) if x and not y)
    c = sum(1 for x, y in zip(a_results, b_results) if y and not x)
    return b, c


def mcnemar_exact(b, c):
    """Two-sided exact McNemar test on discordant counts.

    Under the null, each discordant item is a fair coin flip, so the p-value is
    an exact binomial tail rather than a chi-square approximation. Use the exact
    form always: the approximation is unreliable at exactly the small discordant
    counts eval comparisons usually produce.

    Returns 1.0 when there are no discordant pairs — two systems that never
    differ provide no evidence that they differ.
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts cannot be negative")
    n = b + c
    if n == 0:
        return 1.0
    smaller = min(b, c)
    tail = sum(math.comb(n, i) for i in range(smaller + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_power.py`
Expected: PASS — `Ran 20 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/power.py genai-eval/scripts/tests/test_power.py
git commit -m "feat(genai-eval): McNemar exact test for paired comparisons"
```

---

### Task 12: Rank correlation and the length-bias probe

**Files:**
- Create: `genai-eval/scripts/evalstats/bias.py`
- Create: `genai-eval/scripts/tests/test_bias.py`

**Interfaces:**
- Produces:
  - `bias.rank_correlation(xs, ys) -> Optional[float]` — Spearman's rho with average ranks for ties. Returns `None` when either sequence has no variance. Raises `ValueError` on length mismatch or fewer than two points.
  - `bias.length_bias(judge_scores, human_scores, lengths) -> dict` with keys `judge_rho`, `human_rho`, `gap`.

The subtlety this encodes: a judge correlating with response length is **not by itself bias**, because longer answers are often genuinely better. The bias is the *gap* between how much the judge rewards length and how much humans do.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_bias.py`:

```python
#!/usr/bin/env python3
"""Known-answer tests for evalstats.bias. Run directly: python3 test_bias.py"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import bias


class TestRankCorrelation(unittest.TestCase):
    def test_known_answer_no_ties(self):
        """xs = [1,2,3,4,5], ys = [2,1,4,3,5]; rank differences are
        [-1, 1, -1, 1, 0], so sum(d^2) = 4.
        rho = 1 - 6*4/(5*(25-1)) = 1 - 24/120 = 0.8
        """
        got = bias.rank_correlation([1, 2, 3, 4, 5], [2, 1, 4, 3, 5])
        self.assertAlmostEqual(got, 0.8, places=10)

    def test_known_answer_with_ties(self):
        """xs = [1,2,2,3] gets average ranks [1, 2.5, 2.5, 4] against
        ys ranks [1,2,3,4]. Pearson on those ranks is 4.5/sqrt(4.5*5)
        = 4.5/sqrt(22.5) = sqrt(0.9)
        """
        got = bias.rank_correlation([1, 2, 2, 3], [1, 2, 3, 4])
        self.assertAlmostEqual(got, math.sqrt(0.9), places=10)

    def test_monotonic_is_one(self):
        self.assertAlmostEqual(
            bias.rank_correlation([1, 2, 3, 4], [10, 20, 30, 40]), 1.0, places=10
        )

    def test_reversed_is_minus_one(self):
        self.assertAlmostEqual(
            bias.rank_correlation([1, 2, 3, 4], [40, 30, 20, 10]), -1.0, places=10
        )

    def test_constant_input_returns_none(self):
        self.assertIsNone(bias.rank_correlation([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.rank_correlation([1, 2], [1])

    def test_single_point_raises(self):
        with self.assertRaises(ValueError):
            bias.rank_correlation([1], [1])


class TestLengthBias(unittest.TestCase):
    def test_constant_human_scores_leave_the_gap_undefined(self):
        """Humans who gave every response the same score provide no baseline to
        compare the judge against, so the gap is None rather than equal to
        judge_rho. Reporting the judge's raw length correlation as 'bias' here
        would be exactly the mistake this function exists to avoid."""
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]      # tracks length exactly
        human = [3, 3, 3, 3, 3]      # no variance, so no baseline
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["judge_rho"], 1.0, places=10)
        self.assertIsNone(result["human_rho"])
        self.assertIsNone(result["gap"])

    def test_shared_length_preference_is_not_flagged_as_bias(self):
        """Both judge and humans prefer the longer answers, so the gap is zero.
        Length correlation alone is not bias."""
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]
        human = [1, 2, 3, 4, 5]
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["gap"], 0.0, places=10)

    def test_gap_is_judge_minus_human(self):
        lengths = [10, 20, 30, 40, 50]
        judge = [1, 2, 3, 4, 5]
        human = [5, 4, 3, 2, 1]
        result = bias.length_bias(judge, human, lengths)
        self.assertAlmostEqual(result["judge_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["human_rho"], -1.0, places=10)
        self.assertAlmostEqual(result["gap"], 2.0, places=10)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.length_bias([1, 2], [1, 2], [1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_bias.py`
Expected: FAIL — `ImportError: cannot import name 'bias' from 'evalstats'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/evalstats/bias.py`:

```python
"""Judge bias probes.

An LLM judge is an instrument, and instruments have systematic errors. These
probes measure the four that show up most: preferring whichever answer came
first, rewarding length, favouring its own model's outputs, and giving different
answers when the rubric is reworded.

None of these is a pass/fail test. They produce numbers you report alongside the
agreement statistic so a reader can see what the judge is actually responding to.
"""

import statistics


def _average_ranks(values):
    """Ranks with ties averaged, which is what Spearman requires."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_correlation(xs, ys):
    """Spearman's rank correlation, with average ranks for ties.

    Rank-based rather than Pearson because judge scores are ordinal: the gap
    between a 4 and a 5 is not necessarily the gap between a 1 and a 2.

    Returns None when either sequence is constant, since correlation is
    undefined rather than zero when nothing varies.
    """
    if len(xs) != len(ys):
        raise ValueError("sequences must be the same length")
    if len(xs) < 2:
        raise ValueError("rank correlation needs at least two points")

    rx = _average_ranks(list(xs))
    ry = _average_ranks(list(ys))
    sx = statistics.pstdev(rx)
    sy = statistics.pstdev(ry)
    if sx == 0 or sy == 0:
        return None

    mx = statistics.mean(rx)
    my = statistics.mean(ry)
    covariance = sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / len(rx)
    return covariance / (sx * sy)


def length_bias(judge_scores, human_scores, lengths):
    """How much more than humans does the judge reward long responses?

    Returns judge_rho, human_rho and their gap. The gap is the finding, not
    judge_rho on its own: longer answers really are better sometimes, and a
    judge that tracks length exactly as much as humans do is not biased, it is
    agreeing. Either rho, and therefore the gap, is None when that side has no
    variance to correlate.
    """
    if not (len(judge_scores) == len(human_scores) == len(lengths)):
        raise ValueError("judge scores, human scores and lengths must align")

    judge_rho = rank_correlation(judge_scores, lengths)
    human_rho = rank_correlation(human_scores, lengths)
    gap = None if judge_rho is None or human_rho is None else judge_rho - human_rho
    return {"judge_rho": judge_rho, "human_rho": human_rho, "gap": gap}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_bias.py`
Expected: PASS — `Ran 11 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/bias.py genai-eval/scripts/tests/test_bias.py
git commit -m "feat(genai-eval): rank correlation and length-bias probe"
```

---

### Task 13: Position, self-preference and prompt-sensitivity probes

**Files:**
- Modify: `genai-eval/scripts/evalstats/bias.py`
- Modify: `genai-eval/scripts/tests/test_bias.py`
- Modify: `docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`

**Interfaces:**
- Produces:
  - `bias.position_bias(pairs) -> dict` with keys `first_pick_rate`, `consistency`, `n`. `pairs` is a list of `(choice_ab, choice_ba)` where each entry names the *content* chosen ("A" or "B") when A was shown first, and when B was shown first.
  - `bias.self_preference(scores, generators, judge_model) -> dict` with keys `own_mean`, `other_mean`, `delta`, `n_own`, `n_other`. Returns `None` for `delta` when either group is empty.
  - `bias.prompt_sensitivity(variant_scores) -> dict` with keys `mean_pairwise_rho`, `mean_spread`, `n_variants`. `variant_scores` is one score list per rubric wording, all over the same items in the same order.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_bias.py`:

```python
class TestPositionBias(unittest.TestCase):
    def test_consistent_judge_has_no_position_effect(self):
        """The judge picks the same content whichever order it saw, so it picks
        the first-shown option exactly half the time."""
        pairs = [("A", "A"), ("B", "B"), ("A", "A"), ("B", "B")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 0.5, places=10)
        self.assertAlmostEqual(result["consistency"], 1.0, places=10)
        self.assertEqual(result["n"], 4)

    def test_judge_that_always_picks_first_is_fully_biased(self):
        """Picks A when A is first, B when B is first: never the same content."""
        pairs = [("A", "B"), ("A", "B"), ("A", "B")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 1.0, places=10)
        self.assertAlmostEqual(result["consistency"], 0.0, places=10)

    def test_judge_that_always_picks_second(self):
        pairs = [("B", "A"), ("B", "A")]
        result = bias.position_bias(pairs)
        self.assertAlmostEqual(result["first_pick_rate"], 0.0, places=10)
        self.assertAlmostEqual(result["consistency"], 0.0, places=10)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            bias.position_bias([])

    def test_unknown_choice_raises(self):
        with self.assertRaises(ValueError):
            bias.position_bias([("A", "C")])


class TestSelfPreference(unittest.TestCase):
    def test_judge_scoring_its_own_output_higher(self):
        scores = [5, 5, 3, 3]
        generators = ["gpt-x", "gpt-x", "other", "other"]
        result = bias.self_preference(scores, generators, "gpt-x")
        self.assertAlmostEqual(result["own_mean"], 5.0, places=10)
        self.assertAlmostEqual(result["other_mean"], 3.0, places=10)
        self.assertAlmostEqual(result["delta"], 2.0, places=10)
        self.assertEqual(result["n_own"], 2)
        self.assertEqual(result["n_other"], 2)

    def test_no_own_outputs_gives_no_delta(self):
        result = bias.self_preference([3, 4], ["other", "other"], "gpt-x")
        self.assertIsNone(result["delta"])
        self.assertEqual(result["n_own"], 0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            bias.self_preference([1, 2], ["a"], "a")


class TestPromptSensitivity(unittest.TestCase):
    def test_identical_variants_are_perfectly_stable(self):
        variants = [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["mean_spread"], 0.0, places=10)
        self.assertEqual(result["n_variants"], 3)

    def test_reworded_rubric_that_flips_the_ranking(self):
        variants = [[1, 2, 3, 4], [4, 3, 2, 1]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], -1.0, places=10)

    def test_shifted_variant_keeps_ranking_but_moves_the_mean(self):
        variants = [[1, 2, 3, 4], [2, 3, 4, 5]]
        result = bias.prompt_sensitivity(variants)
        self.assertAlmostEqual(result["mean_pairwise_rho"], 1.0, places=10)
        self.assertAlmostEqual(result["mean_spread"], 1.0, places=10)

    def test_single_variant_raises(self):
        with self.assertRaises(ValueError):
            bias.prompt_sensitivity([[1, 2, 3]])

    def test_ragged_variants_raise(self):
        with self.assertRaises(ValueError):
            bias.prompt_sensitivity([[1, 2, 3], [1, 2]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_bias.py -k TestPositionBias`
Expected: FAIL — `AttributeError: module 'evalstats.bias' has no attribute 'position_bias'`

- [ ] **Step 3: Write the implementation**

Append to `genai-eval/scripts/evalstats/bias.py`:

```python
def position_bias(pairs):
    """Does the judge prefer whichever response it saw first?

    `pairs` holds one entry per item: (choice when A was shown first, choice
    when B was shown first). Each choice names the *content* picked, "A" or "B",
    not the slot it sat in.

    A judge with no position effect picks the same content both times, giving
    consistency 1.0 and a first_pick_rate of 0.5. A judge driven entirely by
    position picks whatever came first, giving consistency 0.0 and a
    first_pick_rate of 1.0 (or 0.0 if it always picks the second).

    Report both numbers: first_pick_rate says which direction the judge leans,
    consistency says how much of its output the lean is eating.
    """
    if not pairs:
        raise ValueError("no order-swapped pairs supplied")

    first_picks = 0
    consistent = 0
    for choice_ab, choice_ba in pairs:
        if choice_ab not in ("A", "B") or choice_ba not in ("A", "B"):
            raise ValueError("each choice must be 'A' or 'B'")
        if choice_ab == "A":
            first_picks += 1  # A was shown first and A won
        if choice_ba == "B":
            first_picks += 1  # B was shown first and B won
        if choice_ab == choice_ba:
            consistent += 1

    n = len(pairs)
    return {
        "first_pick_rate": first_picks / (2 * n),
        "consistency": consistent / n,
        "n": n,
    }


def self_preference(scores, generators, judge_model):
    """Does the judge score its own model's outputs higher than everyone else's?

    `generators` names the model that produced each response, aligned with
    `scores`. `delta` is own_mean minus other_mean, and is None when either
    group is empty — with nothing to compare against there is no finding.

    A positive delta is not proof of favouritism on its own; the judge's own
    model may genuinely be better on this task. Read it next to the human scores
    for the same responses.
    """
    if len(scores) != len(generators):
        raise ValueError("scores and generators must be the same length")

    own = [s for s, g in zip(scores, generators) if g == judge_model]
    other = [s for s, g in zip(scores, generators) if g != judge_model]

    own_mean = statistics.mean(own) if own else None
    other_mean = statistics.mean(other) if other else None
    delta = None if own_mean is None or other_mean is None else own_mean - other_mean
    return {
        "own_mean": own_mean,
        "other_mean": other_mean,
        "delta": delta,
        "n_own": len(own),
        "n_other": len(other),
    }


def prompt_sensitivity(variant_scores):
    """How much does rewording the rubric change the judge's output?

    `variant_scores` is one score list per rubric wording, all covering the same
    items in the same order.

    Two numbers, because they fail differently. mean_pairwise_rho near 1.0 means
    the *ranking* survives rewording. mean_spread is the largest gap between any
    two variants' mean scores, which catches a rubric that preserves the ranking
    while shifting every score up — harmless for a comparison, fatal for an
    absolute threshold.
    """
    if len(variant_scores) < 2:
        raise ValueError("prompt sensitivity needs at least two rubric variants")
    width = len(variant_scores[0])
    if any(len(v) != width for v in variant_scores):
        raise ValueError("every variant must score the same items")

    correlations = []
    for i in range(len(variant_scores)):
        for j in range(i + 1, len(variant_scores)):
            rho = rank_correlation(variant_scores[i], variant_scores[j])
            if rho is not None:
                correlations.append(rho)

    means = [statistics.mean(v) for v in variant_scores]
    return {
        "mean_pairwise_rho": statistics.mean(correlations) if correlations else None,
        "mean_spread": max(means) - min(means),
        "n_variants": len(variant_scores),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"`
Expected: PASS — all four suites green, roughly 100 tests total.

- [ ] **Step 5: Update the spec's file layout to match what was built**

In `docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md`, section 8, replace the three `scripts/` lines:

```
├── scripts/
│   ├── evalstats.py
│   ├── check_eval_card.py
```

with:

```
├── scripts/
│   ├── evalstats/                  # package: agreement, bias, items, power, saturation
│   ├── check_eval_card.py
```

And in section 4.1, change the heading `### 4.1 \`scripts/evalstats.py\`` to `### 4.1 \`scripts/evalstats/\``, adding a sentence after the first line: "Split into five modules by responsibility — `agreement.py`, `bias.py`, `items.py`, `power.py`, `saturation.py` — because one file covering all of them would run past 800 lines."

The spec describes the finished package, so write all five module names now even though `saturation.py` arrives in Task 15.

- [ ] **Step 6: Commit**

```bash
git add genai-eval/scripts/evalstats/bias.py genai-eval/scripts/tests/test_bias.py docs/superpowers/specs/2026-09-05-genai-eval-plugin-design.md
git commit -m "feat(genai-eval): position, self-preference and prompt-sensitivity probes"
```

---

### Task 14: Paired bootstrap for ordinal score differences

**Files:**
- Modify: `genai-eval/scripts/evalstats/power.py`
- Modify: `genai-eval/scripts/tests/test_power.py`

**Interfaces:**
- Produces: `power.paired_bootstrap_diff(a_scores, b_scores, n_resamples=2000, confidence=0.95, seed=None) -> dict` with keys `mean_diff`, `ci` (a `(low, high)` tuple), and `n`. Raises `ValueError` on length mismatch or fewer than two items.

McNemar handles paired *binary* results. Rubric scores are usually ordinal, and for those the paired comparison is a bootstrap over item indices — resampling the pairs together, never the two systems independently, because the whole value of running both systems on the same items is the pairing.

- [ ] **Step 1: Write the failing test**

Append to `genai-eval/scripts/tests/test_power.py`:

```python
class TestPairedBootstrapDiff(unittest.TestCase):
    def test_is_deterministic_for_a_fixed_seed(self):
        a = [5, 4, 3, 5, 4, 3, 5, 4]
        b = [2, 1, 2, 1, 2, 1, 2, 1]
        first = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        second = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        self.assertEqual(first, second)

    def test_mean_diff_is_the_observed_difference(self):
        a = [5, 4, 3, 5, 4, 3]     # mean 4.0
        b = [2, 1, 2, 1, 2, 1]     # mean 1.5
        result = power.paired_bootstrap_diff(a, b, n_resamples=200, seed=5)
        self.assertAlmostEqual(result["mean_diff"], 2.5, places=10)
        self.assertEqual(result["n"], 6)

    def test_interval_brackets_the_mean_difference(self):
        a = [5, 4, 3, 5, 4, 3, 2, 4]
        b = [2, 1, 2, 1, 2, 1, 3, 2]
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=9)
        low, high = result["ci"]
        self.assertLessEqual(low, result["mean_diff"])
        self.assertLessEqual(result["mean_diff"], high)

    def test_clear_difference_excludes_zero(self):
        a = [5] * 20 + [4] * 20
        b = [1] * 20 + [2] * 20
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=13)
        self.assertGreater(result["ci"][0], 0.0)

    def test_no_difference_includes_zero(self):
        a = [3, 4, 2, 5, 3, 4, 2, 5, 3, 4]
        b = [4, 3, 5, 2, 4, 3, 5, 2, 4, 3]
        result = power.paired_bootstrap_diff(a, b, n_resamples=500, seed=13)
        low, high = result["ci"]
        self.assertLessEqual(low, 0.0)
        self.assertGreaterEqual(high, 0.0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            power.paired_bootstrap_diff([1, 2, 3], [1, 2])

    def test_single_item_raises(self):
        with self.assertRaises(ValueError):
            power.paired_bootstrap_diff([1], [2])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_power.py -k TestPairedBootstrapDiff`
Expected: FAIL — `AttributeError: module 'evalstats.power' has no attribute 'paired_bootstrap_diff'`

- [ ] **Step 3: Write the implementation**

Add `import random` and `import statistics` to the top of `genai-eval/scripts/evalstats/power.py`, then append:

```python
def paired_bootstrap_diff(a_scores, b_scores, n_resamples=2000, confidence=0.95,
                          seed=None):
    """Bootstrap interval for the mean score difference between two systems.

    Use this where McNemar does not fit: ordinal rubric scores rather than
    binary pass/fail, on the same items for both systems.

    Resampling draws item *indices* and takes both systems' scores for each
    drawn item, so the pairing survives. Resampling the two systems
    independently would discard exactly the information that makes a paired
    design worth running.

    Returns mean_diff (mean of a minus mean of b), ci, and n. An interval that
    excludes zero is the paired equivalent of a significant difference.
    """
    if len(a_scores) != len(b_scores):
        raise ValueError("score sequences must be the same length")
    n = len(a_scores)
    if n < 2:
        raise ValueError("paired bootstrap needs at least two items")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    differences = [a - b for a, b in zip(a_scores, b_scores)]
    observed = statistics.mean(differences)

    rng = random.Random(seed)
    estimates = []
    for _ in range(n_resamples):
        sample = [differences[rng.randrange(n)] for _ in range(n)]
        estimates.append(statistics.mean(sample))

    estimates.sort()
    tail = (1.0 - confidence) / 2.0
    low = estimates[int(tail * len(estimates))]
    high = estimates[min(len(estimates) - 1, int((1.0 - tail) * len(estimates)))]
    return {"mean_diff": observed, "ci": (low, high), "n": n}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 genai-eval/scripts/tests/test_power.py`
Expected: PASS — `Ran 27 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/power.py genai-eval/scripts/tests/test_power.py
git commit -m "feat(genai-eval): paired bootstrap for ordinal score differences"
```

---

### Task 15: Saturation and contamination signals

**Files:**
- Create: `genai-eval/scripts/evalstats/saturation.py`
- Create: `genai-eval/scripts/tests/test_saturation.py`
- Modify: `genai-eval/scripts/evalstats/__init__.py`

**Interfaces:**
- Produces:
  - `saturation.ceiling_proportion(scores, max_score) -> float` — share of scores at or above the maximum. Raises `ValueError` on empty input.
  - `saturation.canary_hit_rate(outputs, canary) -> float` — share of outputs containing the canary string. Raises `ValueError` on empty input or an empty canary.
  - `saturation.saturation_report(scores, max_score, ceiling_threshold=0.90) -> dict` with keys `ceiling_proportion`, `n`, `saturated`.

This is Gate 11, and it is the gate people ignore. A saturated benchmark is worse than no benchmark, because it keeps getting cited after it has stopped discriminating between anything.

- [ ] **Step 1: Write the failing test**

Create `genai-eval/scripts/tests/test_saturation.py`:

```python
#!/usr/bin/env python3
"""Known-answer tests for evalstats.saturation. Run: python3 test_saturation.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import saturation


class TestCeilingProportion(unittest.TestCase):
    def test_known_answer(self):
        """Two of four scores sit at the maximum, so the proportion is 0.5."""
        self.assertAlmostEqual(
            saturation.ceiling_proportion([5, 5, 4, 3], max_score=5), 0.5, places=10
        )

    def test_all_at_ceiling(self):
        self.assertAlmostEqual(
            saturation.ceiling_proportion([1, 1, 1], max_score=1), 1.0, places=10
        )

    def test_none_at_ceiling(self):
        self.assertAlmostEqual(
            saturation.ceiling_proportion([1, 2, 3], max_score=5), 0.0, places=10
        )

    def test_scores_above_the_maximum_still_count(self):
        """A grader that can exceed its own stated maximum is a bug, but the
        item is still at ceiling and must not be silently dropped."""
        self.assertAlmostEqual(
            saturation.ceiling_proportion([6, 5, 1, 1], max_score=5), 0.5, places=10
        )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            saturation.ceiling_proportion([], max_score=5)


class TestCanaryHitRate(unittest.TestCase):
    def test_known_answer(self):
        outputs = [
            "the answer is 42",
            "CANARY-9f3b leaked into this one",
            "nothing here",
        ]
        self.assertAlmostEqual(
            saturation.canary_hit_rate(outputs, "CANARY-9f3b"), 1 / 3, places=10
        )

    def test_no_hits(self):
        self.assertAlmostEqual(
            saturation.canary_hit_rate(["a", "b"], "CANARY-9f3b"), 0.0, places=10
        )

    def test_every_output_hits(self):
        self.assertAlmostEqual(
            saturation.canary_hit_rate(["x CANARY y", "CANARY"], "CANARY"),
            1.0,
            places=10,
        )

    def test_empty_outputs_raise(self):
        with self.assertRaises(ValueError):
            saturation.canary_hit_rate([], "CANARY")

    def test_empty_canary_raises(self):
        """An empty needle matches every string, which would report total
        contamination on clean data."""
        with self.assertRaises(ValueError):
            saturation.canary_hit_rate(["a"], "")


class TestSaturationReport(unittest.TestCase):
    def test_healthy_pool_is_not_saturated(self):
        report = saturation.saturation_report([5, 5, 4, 3], max_score=5)
        self.assertAlmostEqual(report["ceiling_proportion"], 0.5, places=10)
        self.assertEqual(report["n"], 4)
        self.assertFalse(report["saturated"])

    def test_pool_at_the_threshold_is_saturated(self):
        scores = [5] * 19 + [4]  # 0.95 at ceiling
        report = saturation.saturation_report(scores, max_score=5)
        self.assertAlmostEqual(report["ceiling_proportion"], 0.95, places=10)
        self.assertTrue(report["saturated"])

    def test_threshold_is_configurable(self):
        scores = [5] * 8 + [4] * 2  # 0.8 at ceiling
        self.assertFalse(saturation.saturation_report(scores, 5)["saturated"])
        self.assertTrue(
            saturation.saturation_report(scores, 5, ceiling_threshold=0.75)["saturated"]
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 genai-eval/scripts/tests/test_saturation.py`
Expected: FAIL — `ImportError: cannot import name 'saturation' from 'evalstats'`

- [ ] **Step 3: Write the implementation**

Create `genai-eval/scripts/evalstats/saturation.py`:

```python
"""Saturation and contamination signals for an item pool.

Gate 11 asks whether the benchmark still measures anything. Two things end its
useful life: every system reaching the ceiling, so the score stops separating
them, and the items leaking into training data, so the score measures recall.

A retired benchmark keeps getting cited. That is why this gate exists and why
its answer belongs in the report rather than in someone's memory.
"""


def ceiling_proportion(scores, max_score):
    """Share of scores sitting at or above the maximum.

    Scores above the stated maximum are counted rather than ignored: a grader
    that exceeds its own scale is a bug worth surfacing, and the item is at
    ceiling either way.
    """
    if not scores:
        raise ValueError("no scores supplied")
    return sum(1 for s in scores if s >= max_score) / len(scores)


def canary_hit_rate(outputs, canary):
    """Share of model outputs containing the canary string.

    A canary is a unique string planted in the item pool. If it comes back out
    of a model, the pool is in that model's training data and every number
    derived from it measures memorisation.

    Any non-zero rate is a finding. This is not a threshold to tune.
    """
    if not outputs:
        raise ValueError("no outputs supplied")
    if not canary:
        raise ValueError(
            "canary string is empty; an empty needle matches every output"
        )
    return sum(1 for text in outputs if canary in text) / len(outputs)


def saturation_report(scores, max_score, ceiling_threshold=0.90):
    """Ceiling summary with a saturation verdict.

    `saturated` is True once the ceiling proportion reaches the threshold. At
    that point the eval can no longer distinguish a good system from a very good
    one, and Gate 11 says retire it and refresh the pool.
    """
    proportion = ceiling_proportion(scores, max_score)
    return {
        "ceiling_proportion": proportion,
        "n": len(scores),
        "saturated": proportion >= ceiling_threshold,
    }
```

Then update `genai-eval/scripts/evalstats/__init__.py` so its `__all__` reads:

```python
__all__ = ["agreement", "bias", "items", "power", "saturation"]
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"`
Expected: PASS — five suites, roughly 125 tests, all green.

- [ ] **Step 5: Commit**

```bash
git add genai-eval/scripts/evalstats/saturation.py genai-eval/scripts/evalstats/__init__.py genai-eval/scripts/tests/test_saturation.py
git commit -m "feat(genai-eval): saturation and contamination signals"
```

---

## Done when

- `python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"` is green.
- `.github/workflows/genai-eval-tests.yml` passes on a pull request.
- `genai-eval/scripts/evalstats/` imports with no third-party package installed.
- Every public function has a known-answer test whose arithmetic is written in its docstring.

Phase 1B then builds the skill surface on top of this: the CSV loader with its column detection and no-ceiling guard, the calibration report renderer, the `calibrate.py` CLI, the `examples/judge-calibration/` worked example, and the `eval-qualify` SKILL.md.
