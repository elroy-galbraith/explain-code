# genai-eval

Design and qualify a GenAI evaluation as a measurement instrument, before
trusting its numbers. This plugin ships two skills. `eval-design` designs an
evaluation before it produces a single score — naming the decision it
serves, defining a falsifiable construct, and sealing the result into a
machine-checkable `eval-card.json`. `eval-qualify` is a stdlib-only CLI that
tells you whether an LLM judge agrees with humans well enough to automate a
decision — and, just as often, tells you that your data cannot answer that
yet.

**The two skills are not wired together.** `eval-qualify` has no card mode:
it cannot read an `eval-card.json`, and there is no `qualification` block for
it to write back. See "What this plugin does not do yet" below.

## What `eval-design` does

It walks a six-step process — name the decision and an action for every
outcome, model the domain and rank harm pathways, define a falsifiable
construct, operationalise it into claims/evidence/tasks, build a
contamination-controlled item pool with a sealed test split, and
preregister the protocol and threshold — and writes the result into an
`eval-card.json`. Full field-by-field process in
[`skills/eval-design/SKILL.md`](skills/eval-design/SKILL.md); the card's
shape is documented in
[`templates/eval-card.schema.md`](templates/eval-card.schema.md).

The card is checked by `scripts/check_eval_card.py`, a stdlib-only validator
that answers six of the SOP's eleven gates mechanically, because **a gate
that cannot be checked mechanically will be rubber-stamped** — asking a
model "does this construct trace to a ranked harm pathway?" gets you an
opinion, not a check:

| Gate | Question | What the script checks |
|---|---|---|
| 1 | Named owner + action per outcome | `decision.owner` non-empty; pass/fail/borderline all present |
| 2 | Measures trace to ranked pathways | every construct references an `hp*` that has a `rank` |
| 3 | Falsifiable construct | `negative_evidence` non-empty |
| 4 | Every item maps to a claim, every claim has 3+ items | orphan and thin-claim scan across pool and card |
| 5 | Test split sealed and uncontaminated | recorded sha256 re-verified against the file; canary present |
| 9 | Threshold set before the run | prereg `content_hash` recomputed over the named protocol file and re-verified; `sealed_at` parseable and predating every result timestamp |

Run it against the worked example:

```bash
python3 genai-eval/scripts/check_eval_card.py \
  genai-eval/examples/rag-grounding/eval-card.json
```

Real output:

```
genai-eval/examples/rag-grounding/eval-card.json: 0 error(s), 1 warning(s)

  WARNING [Gate 2] domain.harm_pathways[2]: pathway 'hp3' is ranked but no construct measures it

Gates 6, 7, 8, 10 and 11 need a qualification block and are not checked here.
```

Exit code `0`. The warning is deliberate, not a bug in the example — see
[`examples/rag-grounding/README.md`](examples/rag-grounding/README.md) for
why that harm pathway is ranked but intentionally not measured by this card.
`--format json` gives machine-readable findings, each with a gate number and
a JSON path; `--warnings-as-errors` treats a warning as a failure for CI that
wants zero of either.

## What `eval-qualify` does

It runs on a plain CSV of judge scores and human labels. No eval card, no
setup, no dependencies beyond the Python standard library:

- **Chance-corrected agreement** (Krippendorff's alpha) with bootstrap
  confidence intervals, compared against the **human-human ceiling** — a
  judge's agreement figure means nothing on its own. It has to be measured
  against how well two humans agree with each other on the same items.
- **A power check** against a stated minimum interesting difference, so a
  precise-looking gap doesn't get treated as real when the sample is too
  small to have detected it either way.
- **Judge bias probes**: does the judge reward length more than the human
  raters do, and does it score its own model's outputs higher than everyone
  else's. A probe the available columns cannot support is named in the
  report, never silently skipped — a skipped probe reads as a probe that
  found nothing.
- **Disagreement clusters** — counted by the script, grouped by which
  human/judge score pair they fall into. The script does not name the
  pattern behind a cluster; that takes reading the actual items, which is a
  human's job, not the tool's.

## Run eval-qualify

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/judge-calibration/labels.csv \
  --level ordinal --judge-model model-a --mid 0.10 --seed 7
```

This is the worked example: a judge that looks fine in aggregate — 0.880
agreement against a 0.921 human-human ceiling, both at n = 24 — but rewards
response length nearly twice as hard as the human raters do (rho 0.584
against 0.304). Full walkthrough, including which six items drive that
finding, in
[`examples/judge-calibration/README.md`](examples/judge-calibration/README.md).
`-o report.md` writes the report to a file instead of stdout.

## The statistics toolkit

The report is built on `scripts/evalstats/`, a small stdlib-only package:
Krippendorff's alpha and Cohen's kappa (`agreement.py`), classical item
analysis and KR-20 (`items.py`), bootstrap confidence intervals and sample
size for a target power (`power.py`), the bias probes (`bias.py`), and scale
saturation checks (`saturation.py`). Nothing in `evalstats/` opens a file or
prints — it is a pure computation layer, imported by `scripts/calibration/`
(which does the CSV loading and report rendering) and by `calibrate.py`
itself.

The report uses part of that toolkit, not all of it: Krippendorff's alpha
with a bootstrap interval, the length and self-preference probes, and the
two-proportion power functions. Item analysis, the three kappas, scale
saturation, position bias and prompt sensitivity are tested and available to
import, but nothing in `calibrate.py` calls them yet. Wiring them into the
report is later work, not a claim about what today's report contains.

## The honesty rules

The report is deliberately more willing to say "this data cannot answer
that" than to produce a number that outruns what the sample supports:

- **No ceiling without two raters.** With only one human rater column, there
  is nothing to compare the judge's agreement against. The report says so in
  its opening section, before any agreement figure — "Gate 6 is unanswered,"
  not a number that reads as if it had passed one.
- **No figure without its n.** Every agreement figure, correlation and bias
  delta is printed with the number of items it was computed from — pairable
  units for an alpha, rows complete in all three columns for the length
  correlation, rows carrying both a judge score and a human label for the
  power baseline — never the file's row count, so a tight-looking interval
  from 8 items can't be mistaken for one from 800.
- **Undefined is reported as undefined**, never silently coerced to zero or
  omitted. A statistic that cannot be computed from degenerate input (zero
  variance, a single category, one rater) renders as a dash, not a number
  that happens to be zero.
- **Agreement is not correctness.** High agreement between the judge and
  humans shows the judge reproduces their judgments consistently — not that
  either is right. A judge agreeing with humans who are mistaken is still
  wrong.
- **A gate that cannot be checked mechanically will be rubber-stamped.**
  That is why six of the eleven SOP gates are checked by a script
  (`check_eval_card.py`, see above) rather than asked of a model, and why
  the remaining five are named below instead of being quietly assumed.

## What this plugin does not do yet

`eval-qualify` qualifies an evaluation that already produces scores; it does
not design one, and `eval-design` designs an evaluation but cannot measure
whether one performs. Between them, five of the eleven SOP gates are not
computed by anything that ships:

- **Gates 6, 7, 8, 10 and 11 need a `qualification` block that does not
  exist.** `check_eval_card.py` checks Gates 1, 2, 3, 4, 5 and 9 only — it
  has no code path for the other five. `eval-qualify` computes agreement,
  power and bias figures that speak to some of those gates, but it has no
  card mode: it cannot open an `eval-card.json`, read the `grader` block
  `eval-design` writes, or append a `qualification` block back onto the
  card. The bridge today is manual — export judge scores and human labels
  into the CSV `eval-qualify` expects and hand it that file directly (see
  [`examples/rag-grounding/README.md`](examples/rag-grounding/README.md)
  for a worked handoff) — and nothing produced that way is recorded in the
  card itself.
- If you're starting from nothing, run `eval-design` first; it has a
  process for exactly that. If you already have judge scores and human
  labels and no card, `eval-qualify` has something to run today; it just
  won't write its answer back into one.

## Tests

```bash
python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"
```

Standard library only, no install step, Python 3.9+.
