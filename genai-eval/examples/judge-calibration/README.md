# Worked example: judge calibration

This is the example to run first. It shows `calibrate.py` scoring a judge that
looks fine on the surface and has a real, measurable flaw underneath: it
systematically over-scores long responses.

## The data

`labels.csv` has 24 items on a 1-4 groundedness rubric: two human raters
(`human_a`, `human_b`), one LLM judge (`judge`), a response length column
(`response_chars`), and a generator column (`generator`, one of `model-a` /
`model-b`) so the judge's own outputs can be told apart from everyone else's.

## Run it

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/judge-calibration/labels.csv \
  --level ordinal --judge-model model-a --mid 0.10 --seed 7
```

The `--seed 7` makes the bootstrap confidence intervals below reproducible.
Running this exact command should reproduce every figure in this README.

## What it found

**Agreement.** Judge-human agreement (Krippendorff's alpha, ordinal): **0.880**,
95% CI **[0.715, 0.960]**, n = 24. Human-human agreement, the ceiling the judge
is measured against: **0.921**, 95% CI **[0.794, 0.985]**, n = 24. The judge
falls below the ceiling — humans agree with each other more than the judge
agrees with them, so automating this rubric costs measurable accuracy.

**Statistical power.** The observed exact-agreement rate (judge equals human
on the raw label) is 0.750 over 24 items. With n = 24, the smallest
agreement-rate difference this sample could reliably detect is 0.999 — in
practical terms, none. Detecting a difference of 0.10 (the `--mid` given
above) in that agreement rate would need 248 items; this sample has 24, which
the tool correctly reports as not enough. This is a separate statistic from
the alpha figures above, but it makes the same point from another angle: 24
items is a small sample, and this report says so rather than dressing up a
precise-looking interval.

**Length bias, n = 24.** Judge score vs. response length: rho = 0.584. Human
score vs. response length: rho = 0.304. Gap = **0.280**. The judge rewards
length noticeably more than the humans do.

**Largest disagreement cluster, n = 24 (6 items disagree, 18 agree).**
Human = 3, judge = 4: 3 items (50% of all disagreements) — `i02`, `i13`, `i24`.

## The pattern behind that cluster

The report doesn't name causes for you, so here is what reading the six
disagreeing items by hand shows: they are `i02`, `i13`, `i24` (human 3 / judge
4), `i07`, `i19` (human 2 / judge 3), and `i10` (human 1 / judge 2). Every one
of these six is a judge-scores-higher disagreement — there are zero cases of
the judge scoring lower than a human. And by response length, these six items
(460-540 characters) are exactly the six longest responses in the entire
24-item set; the next-longest item is 310 characters. The judge's extra
credit and the response length line up exactly.

## What this tells you

This judge is usable but not free: it agrees with humans well relative to how
much humans agree with each other (0.880 against a 0.921 ceiling, both on
n = 24), but every disagreement it has with the human rater — 100% of them,
all six — is the same failure in the same direction: it gives a higher score
to the six longest responses in the sample, none of which a human rated that
generously. A sample of 24 items is small — both the width of the alpha
confidence intervals above and the statistical-power figures say so directly —
so you should not lean on the exact size of the alpha gap or the rho gap. But
the direction of the disagreement is not subtle: it is one-directional, all
six cases, and it lines up with a variable that has nothing to do with the
rubric.

The practical consequence is about the corpus you'd actually run this judge
on. If you use it to score a set of responses whose length distribution looks
like this sample, its aggregate score will run a little high, fairly evenly.
But if you use it on a corpus where length varies more by system — for
example, comparing a verbose model against a terse one — this judge will
systematically favor the verbose model for reasons the rubric was never meant
to reward. Re-calibrate, or at minimum re-check this bias probe, before using
this judge's scores to rank generators that differ in how long their
responses run.

(The report also computes a self-preference probe here, since `--judge-model
model-a` was passed: the judge scores model-a's own outputs at 3.769 (n = 13)
against 2.000 for everyone else's (n = 11), delta 1.769. We aren't reading
that as favoritism in this example — model-a's outputs also score higher with
the human raters in this sample, and model-a's responses are also the longer
ones on average, so the self-preference number is confounded with both
genuine quality and the length bias above. A dataset built to isolate
self-preference would need matched-quality, matched-length items from each
generator, which this one is not.)

## What this report cannot tell you

The tool says this plainly, and it's worth repeating here rather than letting
the numbers above stand alone: this report measures *agreement*, not
*correctness* — a judge that agrees with a mistaken human is still wrong. And
at n = 24, none of the confidence intervals above should be read as more
precise than they are.
