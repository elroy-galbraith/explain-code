---
name: eval-design
description: Design a GenAI evaluation before running it — name the decision it serves, define a falsifiable construct, operationalise it into claims, evidence and tasks, build a contamination-controlled item pool, and seal a preregistered threshold. Use when the user asks to "design an eval", "build an eval set", "how should I evaluate X", "what should I measure", "set up an LLM judge", "write a rubric", or is about to compare models or prompts with no protocol. Produces an eval-card.json that check_eval_card.py can hold to six gates. Not for interpreting results you already have — that is eval-qualify.
---

# Eval Design

This skill designs a GenAI evaluation before it produces a single score:
naming the decision it serves, defining a construct precise enough that it
could turn out to be wrong, breaking that construct into claims an item pool
can actually test, and preregistering the threshold that will judge the
result — all before any completion has been generated. It ends by handing
the card it built to a script and reporting back exactly what the script
says, because a gate this skill only asserted rather than proved would be
the rubber stamp the rest of this plugin exists to avoid: six of the eleven
SOP gates are answered by `check_eval_card.py`, not by a model's judgement,
and this skill never substitutes its own opinion for that check.

## When to use

- "Design an eval" / "build an eval set."
- "How should I evaluate X?" / "What should I measure?"
- "Set up an LLM judge" / "write a rubric."
- The user is about to compare models or prompts with no protocol in place —
  no fixed prompts, no seeds, no threshold decided in advance.
- Someone has said "we should evaluate this" and nothing yet names what
  would count as a bad result.

## When NOT to use

- **Interpreting results that already exist.** That is `eval-qualify` — it
  measures whether an instrument that already produces scores can be
  trusted. This skill runs before any score exists; once one does, hand off
  (see "Handoff to eval-qualify" below).
- **Auditing someone else's published benchmark with no access to its
  items.** Every step below reads or writes actual items, actual retrieved
  context, actual rubric text. A leaderboard number alone gives none of
  that, and a card built without it would be decoration, not a design.
- **Nobody in the conversation can name the decision the eval serves.** Say
  so plainly and stop, rather than continuing to build a card around a
  decision nobody owns. Gate 1 will fail on an empty `decision.owner` — and
  more importantly, an eval nobody owns gets optimised against while it is
  being built and then ignored once it ships, which wastes more effort than
  not building it at all.

## State your tier before doing anything else

Per the plugin's design, name the tier this design run serves and which
steps you will run and skip — before writing a single field, not after.
Guessing at a tier and backfilling the routing is the failure mode this step
exists to prevent.

| Tier | Trigger | Steps this skill runs |
|---|---|---|
| 1 — daily regression | Catch breakage | 1, 5, 6 |
| 2 — per release | Compare options | + 3, 4 |
| 3 — sign-off / external claim | Defend a claim | + 2 (all) |

A Tier 1 run reuses a construct and claim set a higher-tier run already
built: it re-states the decision (step 1), confirms or rebuilds the item
pool (step 5), and re-seals the protocol (step 6), but does not redo the
domain model or the construct definition from nothing. Tier 2 adds the
formal construct definition and the claim/evidence buildout (steps 3 and 4)
— comparing options needs claims an item pool can be traced to. Tier 3 adds
the full harm-pathway ranking (step 2, all of it), because a sign-off or an
external claim needs the strongest available justification for why this
measures the thing that matters rather than the thing that was easy to
build a rubric for.

**These are SOP process-step numbers, not gate numbers, and the two
sequences share numbers by coincidence, not by design.** Step 6 above is
design work this skill owns: freezing the grader's configuration alongside
the rest of the protocol, before any completion exists to score. Gate 6
("does judge-human agreement reach the human-human floor?") is a
measurement owned by `eval-qualify`, taken on every run at every tier once
real judge and human scores exist — it is not tier-gated the way the steps
above are, and finishing step 6 here does not satisfy it. See
`eval-qualify/SKILL.md`'s own tier table for where Gate 6 sits from that
side.

## Process

Each step below says which card fields it fills and which gate — of the six
`check_eval_card.py` checks — reads them.

### Step 1 — Name the decision, and the action for every outcome

Ask, or state from context: what decision does this eval exist to inform,
who is accountable for acting on the result, and what happens for a pass, a
fail, and a borderline result specifically? "Borderline" is not a hedge to
skip — an eval whose middle result has no stated action is the one most
likely to get run, read, and then quietly ignored. If nobody can name an
owner, or an action for every outcome, stop and say so plainly rather than
continuing to build a card around a decision nobody will act on.

**Fields:** `decision.question`, `decision.owner`, `decision.outcomes[]`
(one entry each for `pass`, `fail`, `borderline`, each with a non-blank
`action`). **Gate:** 1 — named owner, and every outcome mapped to an action.

### Step 2 — Model the domain and rank the harm pathways

Describe who is exposed to the system (`domain.users`) and the conditions it
runs under (`domain.operating_conditions`), then list the concrete ways it
can cause harm and rank them. The ranking is the actual work here, not a
formality on top of the list: an unranked catalog of harm pathways justifies
measuring any of them, including the one that is easiest to build a rubric
for rather than the one that matters most. Give each pathway a severity and
a description concrete enough that a stranger could tell whether a
transcript is an instance of it.

**Fields:** `domain.users`, `domain.operating_conditions`,
`domain.harm_pathways[]` (`id`, `rank`, `severity`, `description`).
**Gate:** 2 — every construct in Step 3 must trace to one of these ranked
pathways; a pathway with no `rank` cannot be traced to.

### Step 3 — Define the construct, and say what would count against it

Write a definition precise enough that two people reading the same
transcript would classify it the same way — vague definitions are where
most judge/human disagreement later turns out to live. Then do the harder
half: write down what evidence would count *against* the construct, not
just for it. A construct with nothing that could disconfirm it is not
falsifiable, and an unfalsifiable construct reads as measuring something no
matter what the transcripts show, because no observation could have gone
the other way. Link the construct back to at least one ranked harm pathway
from Step 2.

**Fields:** `constructs[].id`, `definition`, `positive_evidence[]`,
`negative_evidence[]` (at least one, non-blank), `harm_pathways[]`
(references `domain.harm_pathways[].id`). **Gate:** 3 — `negative_evidence`
non-empty. Gate 2 also reads `harm_pathways[]` here.

### Step 4 — Operationalise into claims, evidence and tasks

Break the construct into specific, checkable claims, then for each claim
write what gets observed (`evidence_model`) and what family of tasks
exercises it (`task_model`). This is also where the trace matrix gets
built: every claim needs at least three items in the pool, or its score
cannot be read at the claim level separately from the eval as a whole — a
claim with two items is a claim you cannot actually report on. Write each
scoring rule concretely enough that it can point at a rubric file, since
that rubric is what a human or a judge will apply later.

**Fields:** `claims[].id/construct/statement`,
`evidence_model[].id/claim/observable/scoring_rule/rubric_ref`,
`task_model[].id/claim/task_family/conditions[]`. **Gate:** 4 — every claim
needs at least one `evidence_model` entry and, once the pool exists, at
least three items whose `claim_id` names it.

### Step 5 — Build the item pool

State the sampling frame — where the items came from and how they were
selected — then build in the contamination controls before anything is
sealed: a canary string embedded in the pool, date-stamping so future
leakage can be bounded in time, a count of genuinely novel items, and a
sealed test split whose hash goes in the card. Every row in the pool JSONL
needs both an `item_id` and a `claim_id`; the `claim_id` is what makes Gate
4's item-to-claim trace a script's job instead of a reviewer's.

One warning, because the worked `rag-grounding` example hit it for real: **a
sealed split has to reach every machine byte-identical, or the hash lies
about what changed.** On a checkout with `core.autocrlf=true` — the default
on Windows — git rewrites the split's LF line endings to CRLF on the way out
of the repository. The file's bytes change, the recorded `sha256` no longer
matches, and Gate 5 fires — not because anyone touched the split, but
because git did, silently, during checkout. The worked example carries a
scoped `.gitattributes` for exactly this reason:

```
* text=auto eol=lf
```

Add the same file, scoped to the directory holding the sealed split (and to
any hashed protocol file from Step 6), and say why in a comment: a validator
that cries tampering when nothing was tampered with teaches people to
ignore it the next time it fires for a real reason. Confirm it took effect
with:

```bash
git check-attr eol -- path/to/sealed/split.jsonl
```

Expected output: `path/to/sealed/split.jsonl: eol: lf`.

**Fields:** `items.source`, `items.sampling_frame`,
`items.contamination_controls.canary/date_stamped/novel_items`,
`items.splits.dev.path`,
`items.splits.test.path/sealed/sha256/sealed_at`. **Gate:** 4 — `source` is
loaded off disk, the one check that touches a file rather than only the
card. **Gate:** 5 — `contamination_controls.canary` non-blank,
`splits.test.sealed` true, and `splits.test.sha256` matching the file's
recomputed hash.

### Step 6 — Preregister

Fix everything that could otherwise be tuned after seeing a result: the
exact prompts (`protocol.prompts_ref`), seeds, temperature, elicitation
budget, the baselines the result will be compared against, and the decision
threshold that answers Step 1's outcomes. This step also freezes the
`grader` block — which kind of grader, which model, which rubric, and which
gold set of human-labeled items it will eventually be checked against.
Designing the grader is this skill's job, done before any completion exists
to score; *calibrating* it — whether it actually agrees with humans at the
human-human ceiling — is a measurement that needs the grader's real outputs
against that gold set, which do not exist yet. That measurement is Gate 6,
and it belongs to `eval-qualify`, run after this skill is done.

Compute the content hash over the protocol file as written, not invented:

```bash
python3 -c "import hashlib,sys; print('sha256:' + hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  protocol.md
```

Then seal `preregistration.sealed_at` to the current timestamp. Everything
in this block must predate any result — that is what makes Gate 9 checkable
at all, rather than a claim the author makes about their own timing.

**Fields:** `preregistration.sealed_at`, `content_hash`,
`protocol.prompts_ref/seeds/temperature/elicitation_budget`, `baselines[]`,
`threshold.metric/minimum_interesting_difference/decision_rule`. **Gate:** 9
— `sealed_at` and `content_hash` both present, and, once results exist,
predating every result timestamp. The `grader` block
(`kind/model/mode/rubric_ref/gold_set/bias_probes`) is also written in this
step, but no gate in this phase reads it mechanically — it exists so
`eval-qualify` can run calibration against it later, which is Gate 6.

## Validate the card, and report what it says

Run the validator against the card this process just produced:

```bash
python3 genai-eval/scripts/check_eval_card.py CARD.json
```

Report the actual output, not a paraphrase of it, exit code included. It is
`0` when there are no error-level findings, `1` when there is at least one,
and `2` when the file could not be read as a card at all — a `2` means the
check never ran, which is a different failure than "it failed." Add
`--format json` for machine-readable findings, each with a gate number and a
JSON path. A warning does not fail the run; an error does.

This skill never asserts the card is good. It runs the tool and reads the
tool's own words back. The worked example
(`genai-eval/examples/rag-grounding/README.md`) is the model for this: its
card validates clean at `0 error(s), 1 warning(s)`, and the README documents
the real warning — a ranked harm pathway (`hp3`) that nothing in the card
measures — rather than quietly redesigning the card to make the warning
disappear or leaving it out of the writeup. Do the same: if the validator's
real output includes a warning, show it and say why it exists or what it
would take to close it. If it reports errors, fix the field it names and
re-run — it reports every violation in one pass, so fix what it lists
rather than the first one and re-running blind.

## Handoff to eval-qualify

A sealed, validated card is a well-formed design. It is not a qualified
one — Gates 6, 7, 8, 10 and 11 need real results, and nothing above computes
them. Once the eval has actually been run and scored, and a human has
labeled at least a subset of the same items, hand off to `eval-qualify`.

Say this plainly rather than implying a coupling that is not built:
**`eval-qualify` has no card mode.** It cannot open this eval card, read its
`grader` block, or append a `qualification` block back onto it — none of
that exists yet. What it runs today is bare mode, on a two-column CSV of
judge scores and human labels. The bridge between the two skills is manual:
export the judge's scores and the human labels into a CSV with the columns
bare mode expects (one judge score column, one or more human label columns,
optionally an `item_id` column), and hand that file to `eval-qualify`.

The `grader.gold_set` path this skill just pointed at is already shaped for
that handoff — in the worked example, `labels/gold.csv` carries `item_id`,
`judge_score`, `human_a` and `human_b`, which is exactly bare mode's
contract:

```bash
python3 genai-eval/scripts/calibrate.py \
  genai-eval/examples/rag-grounding/labels/gold.csv --level ordinal --seed 7
```

What `eval-qualify` produces from that file stays outside this card until a
future card mode is built: no gate above reads a `qualification` block, and
none of Gates 6, 7, 8, 10 or 11 exist yet as far as `check_eval_card.py` is
concerned.
