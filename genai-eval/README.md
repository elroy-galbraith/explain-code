# genai-eval

Qualify a GenAI evaluation as a measurement instrument, before trusting its
numbers. This plugin ships `eval-qualify`: a skill and a stdlib-only CLI that
tell you whether an LLM judge agrees with humans well enough to automate a
decision — and, just as often, tell you that your data cannot answer that yet.

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
- **Judge bias probes**: does the judge reward length, position, or its own
  model's outputs more than the human raters do; is it sensitive to prompt
  rewording that shouldn't change the verdict.
- **Disagreement clusters** — counted by the script, grouped by which
  human/judge score pair they fall into. The script does not name the
  pattern behind a cluster; that takes reading the actual items, which is a
  human's job, not the tool's.

## Run it

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

## The honesty rules

The report is deliberately more willing to say "this data cannot answer
that" than to produce a number that outruns what the sample supports:

- **No ceiling without two raters.** With only one human rater column, there
  is nothing to compare the judge's agreement against. The report says so in
  its opening section, before any agreement figure — "Gate 6 is unanswered,"
  not a number that reads as if it had passed one.
- **No interval without its n.** Every confidence interval and correlation
  in the report is printed with the item count it was computed from, so a
  tight-looking interval from 8 items can't be mistaken for one from 800.
- **Undefined is reported as undefined**, never silently coerced to zero or
  omitted. A statistic that cannot be computed from degenerate input (zero
  variance, a single category, one rater) renders as a dash, not a number
  that happens to be zero.
- **Agreement is not correctness.** High agreement between the judge and
  humans shows the judge reproduces their judgments consistently — not that
  either is right. A judge agreeing with humans who are mistaken is still
  wrong. The number means your judge is predictable like the humans; it says
  nothing about whether all of you are accurate.

## What this plugin does not do yet

`eval-qualify` qualifies an evaluation that already produces scores. It does
not design one. Choosing a construct, writing a rubric, building an item
pool, and sealing a test split is `eval-design` — Phase 2 of this plugin,
not built yet. If you're starting from nothing, this skill has nothing to
run until you have judge scores and human labels to feed it.

## Tests

```bash
python3 -m unittest discover -s genai-eval/scripts/tests -p "test_*.py"
```

Standard library only, no install step, Python 3.9+.
