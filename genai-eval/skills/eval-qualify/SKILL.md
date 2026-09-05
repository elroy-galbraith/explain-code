---
name: eval-qualify
description: Qualify a GenAI evaluation instrument and report its results — measure judge–human agreement with confidence intervals against the human–human ceiling, run item analysis and a power calculation, and check the design gates. Use when the user asks "is my LLM judge reliable", "how good is my eval", "compute Krippendorff's alpha / Cohen's kappa", "is this result significant", "do I have enough items", "audit this benchmark", or hands over judge scores and human labels. Runs standalone on a two-column CSV — no eval card required. Not for designing an eval that does not exist yet.
---

# Eval Qualify

This skill measures whether an evaluation instrument can be trusted — the
phase most teams skip because it produces caveats instead of a chart. It runs
on a plain CSV of judge scores and human labels, no eval card required, and it
is deliberately more willing to tell you "this data cannot answer that" than
to hand you a clean-looking number that outruns what the sample supports.

## When to use

- "Is my LLM judge reliable?"
- "How good is my eval?"
- "Compute Krippendorff's alpha / Cohen's kappa for these ratings."
- "Is this result statistically significant?"
- "Do I have enough items to trust this comparison?"
- "Audit this benchmark."
- The user hands over a CSV (or two columns of data) with judge scores and
  human labels and wants to know what it shows.

## When NOT to use

- **Designing an eval that does not exist yet.** That is `eval-design`
  (Phase 2 of this plugin), which is not built yet — say so if the user asks
  for it. This skill qualifies an instrument that already produces scores; it
  does not choose a construct, write a rubric, or build an item pool.
- **Interpreting a benchmark someone else ran with no access to item-level
  data.** A published leaderboard number cannot be qualified from the outside.
  Every step below — the ceiling comparison, the power check, and above all
  the disagreement clustering — needs the raw per-item judge and human
  ratings, not a summary statistic.
- **Anything that needs correctness rather than agreement.** This skill
  measures whether the judge matches the humans, not whether either of them
  is right. A judge that agrees perfectly with a human rater who is
  systematically wrong will pass every check here and still produce wrong
  scores. Say this out loud whenever a result looks clean — agreement is not
  a synonym for quality.

## State your tier before doing anything else

Per the plugin's design, name the tier this run serves and which gates you
will check and skip — before running the tool, not after. Guessing at a
number and backfilling the tier is the failure mode this step exists to
prevent.

| Tier | Trigger | Gates in scope |
|---|---|---|
| 1 — daily regression | Catch breakage | 9, 10, 11 (light) |
| 2 — per release | Compare options | + 7 |
| 3 — sign-off / external claim | Defend a claim | + 8 (all) |

Gate 9 is "was the threshold set before this run", Gate 10 is "did the result
cross it", Gate 11 is "is the scale saturated or the item pool leaked" — all
three are cheap enough to check on every run, which is why Tier 1 always
includes them. Tier 2 adds Gate 7, the power calculation, because comparing
options needs to know the sample can actually detect a difference. Tier 3
adds Gate 8, criterion validity evidence, which is judgement rather than a
computation and is the reason a sign-off claim needs a human in the loop, not
just a script.

The tier table does not list Gate 6 — judge-human agreement reaching the
human-human ceiling — because it is not tier-gated: it is the core of what
`calibrate.py` computes on every run, at every tier. A Tier 1 regression check
still gets an agreement figure; the tier controls what else you check around
it, not whether you check agreement at all.

## Process

### Step 1 — Name the decision this judge serves

Ask, or state from context, what decision the judge's score is used for and
at which tier from the table above. If nobody in the conversation can name
the decision — "we ship if this number crosses X" or "we flag this for human
review if it drops below Y" — say so plainly and stop before running
anything. A calibration number with no decision attached to it is a vanity
metric: it will still be technically correct and it will still tell nobody
anything, because there is no consequence riding on it to make the number
matter.

### Step 2 — Run `calibrate.py`, and show the command

Run:

```bash
python3 genai-eval/scripts/calibrate.py LABELS.csv \
  --level ordinal --categories worst,bad,ok,good,best \
  --judge-model NAME --mid 0.10 --seed 7 -o report.md
```

Show the user the exact command you ran, not a paraphrase of it — the flags
are part of the record of what was measured. The columns needed are the
minimum contract: one judge score and one human label per row; everything
else (a second human rater, an item id, response length, a generator column)
is optional and unlocks more of the report. `--level` defaults to `nominal`;
set it to `ordinal` or `interval` whenever the scale has an order, since
nominal agreement penalizes a 4-vs-5 disagreement as heavily as a 1-vs-5 one.
`--categories` is required for a non-numeric ordinal or interval scale, must
be given low to high, and **must name every rating value that appears in the
data** — a rating the list omits raises an error rather than silently
sorting wrong. `--judge-model` turns on the self-preference probe.
`--mid` sets the minimum interesting difference for the power check; without
it, the report still tells you the smallest difference the sample size can
detect, just not whether that's enough for your purposes. `--seed` makes the
bootstrap confidence intervals reproducible — always set it and record it.
`-o` writes the report to a file instead of stdout.

If the user has no data of their own yet, or wants to see the shape of a
report before committing their own CSV, run the worked example first:

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/judge-calibration/labels.csv \
  --level ordinal --judge-model model-a --mid 0.10 --seed 7
```

That example (`genai-eval/examples/judge-calibration/README.md`) shows a
judge that looks fine in aggregate — 0.880 agreement against a 0.921
human-human ceiling, at n = 24 — but rewards response length nearly twice as
hard as the human raters do. It is worth running once just to see what a
report that catches a real, specific flaw looks like, before reading one
about the user's own judge.

`calibrate.py` needs nothing beyond the Python standard library. It runs
anywhere Python 3 runs.

### Step 3 — Read the limits back to the user before any figure

The report opens with a section called "What this report cannot tell you."
Read it back to the user — quote it, don't paraphrase it — **before** you
say a single number from the sections that follow. Do this every time, not
only when the result looks shaky.

This is the step most likely to get skipped, because it is the part of the
report with no number in it, and it is the step that matters most, because
it is what tells the reader whether the numbers that follow mean what they
are about to assume. If you catch yourself about to write "the alpha is
0.88" before you have said what this data cannot answer, stop and go back.
A reader who hears the figure first anchors on it; the caveats that arrive
afterward read as hedging rather than as the frame the number has to sit
inside. Order is not a formality here — it is the difference between a
qualification report and a number laundered through one.

When the report says a verdict is unavailable — most commonly "no ceiling"
because there is only one human rater — that sentence is not boilerplate.
Say it to the user in those terms: there is no floor to compare the judge
against, so nothing below can tell them whether the judge is good enough,
only whether it is internally consistent with the one rater it has.

### Step 4 — Interpret the ceiling verdict against the decision from Step 1

The report's Agreement section ends in one of three verdicts. Translate each
one into what it means for the decision named in Step 1, not just into what
it means abstractly:

- **`at_or_above_ceiling`** — the judge agrees with humans at least as well as
  humans agree with each other. This is the best any instrument can do on
  this task; automating the decision costs no measurable accuracy against a
  second human rater. It does not mean the judge is *correct* — see the
  "When NOT to use" section — only that it is not the weak link.
- **`below_ceiling`** — humans agree with each other more than the judge
  agrees with them. Automating this rubric with this judge costs real
  accuracy. Whether that cost is acceptable depends entirely on the tier and
  the decision: a small, well-characterized gap may be fine for a Tier 1
  regression trip-wire and disqualifying for a Tier 3 external claim.
- **`no_ceiling`** — there is only one human rater, so there is no ceiling to
  compare against. Gate 6 is unanswered, not failed: the data cannot say
  whether the judge is good enough, in either direction. The next action is
  almost always to get a second rater (see Step 6), not to treat the judge's
  agreement figure as if it had cleared a bar that was never there.

### Step 5 — Name the disagreement clusters by reading the items, not the scores

The report's Disagreement clusters section counts how many items fall into
each judge/human score pairing — for example, "human = 3, judge = 4: 3 items."
That count is not a finding. It is an index into the items you still have to
read.

To name a cluster, open the underlying items behind the largest two or three
clusters and read what the judge and the humans actually saw. Only after
reading them do you get to write a name for the failure — something like
"judge rewards length" or "judge misses missing citations," not "human-3
judge-4." Naming the score pair is not naming the cluster; it is quoting a
number back that the report already gave you.

Draw the line here plainly: a name invented without reading the items is a
guess dressed up as a finding. It will look identical to a real finding in
the report you hand back, and everyone downstream — the person deciding
whether to ship, the person deciding whether to fix the rubric — will treat
it as measured rather than guessed. If you have not read the items, say "the
report shows N items in this cluster; the pattern behind them hasn't been
examined yet" rather than inventing a label that sounds plausible.

### Step 6 — State the limits and the next cheapest action

Close with what this run does and does not establish, and what the single
cheapest next step is. That next step is almost always **a second human
rater scoring a subset of the same items** — it is the one thing that turns
a `no_ceiling` verdict into a real one and is what unlocks Gate 6. Recommend
it before recommending anything more expensive (a larger item pool, a new
rubric, IRT-grade item analysis): a second rater on items you already have
is nearly always cheaper than any alternative that produces the same
information.

### Step 7 — Offer to promote the result into a full eval card

Ask whether the user wants this qualification promoted into a full eval
card. Be explicit about what a card would add on top of what bare mode just
produced:

- **A sealed test split** — a hash-locked item set that cannot be quietly
  edited after the fact, which is what makes Gate 5 checkable rather than
  trust-based.
- **A claim-to-item trace matrix** — every item mapped to the claim it is
  meant to test, so Gate 4 (every item traces to a claim, every claim has
  enough items) is a scan instead of a guess.
- **A preregistered threshold** — a pass/fail line committed to before the
  result is seen, which is what makes Gate 9 mechanical instead of
  after-the-fact rationalization.

Together these turn Gates 1 through 5 and Gate 9 from judgement calls into
things a script can check. That is the whole point of the card: not more
paperwork, but fewer places where a reviewer has to take someone's word for
it.

Then say plainly that `eval-design` — the skill that would actually build
that card — is not built yet (it is Phase 2 of this plugin). Do not invent a
card file format, a field list, or a schema to fill the gap; there isn't one
yet, and guessing one here would just be a second version of the mistake
Step 5 warns against. This skill's job stops at qualifying an instrument, not
at inventing the artifact that would eventually hold the result.

## Handoff to other skills

This skill produces a measurement, not a document for a particular audience.
Rather than growing a stakeholder-communication section of its own:

- When the qualification result needs to reach a leadership or non-technical
  audience — a go/no-go recommendation, a plan for closing the gap — hand off
  to the **`improvement-plan`** skill instead of writing that framing here.
- When the readers are non-native English speakers, or the report will be
  translated, hand off to **`simplified-technical-english`** (`lite` profile)
  as a final language pass over whatever prose you write for them.

This skill works standalone, on nothing but a CSV, and will keep working that
way after Phase 2 ships. Once `eval-design` exists, it will add a card mode on
top of this same tool — appending a `qualification` block to a sealed eval
card instead of standing alone — but that is additive. Nothing above changes
because of it.
