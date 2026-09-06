# Worked example: `rag-grounding` eval card

This is the second worked example, after `judge-calibration`. Where that one
shows `calibrate.py` scoring a judge, this one shows the other half of the
pipeline: an `eval-card.json` that passes every mechanical gate
`check_eval_card.py` currently checks (Gates 1, 2, 3, 4, 5 and 9), plus every
file the card points at, so nothing it names dangles.

## What the eval is for

The decision this eval informs (`decision.question` in the card): should the
v3 RAG support assistant ship broadly, given how often it asserts facts its
retrieved context does not support? The owner (`decision.owner`) is the
Applied AI eval lead for the Support Widget team, and each of the three
possible results has a concrete action attached: pass ships to 100% of
traffic, fail holds the release and returns it to the retrieval/prompt team
with the failing item traces, borderline ships to a 10% canary and re-runs at
a larger n.

Two constructs operationalize this: **grounding** (`c_grounding` -- does the
assistant assert only what its retrieved context supports, and decline rather
than fabricate when the context is thin?) and **citation accuracy**
(`c_citation` -- when the assistant does cite a chunk, does that chunk
actually support the sentence it's attached to?). Both trace to a ranked harm
pathway in `domain.harm_pathways`, and three claims operationalize the two
constructs across an item pool of 12 realistic support-widget prompts about a
fictional product, "Northwind Cloud Backup."

## Running the validator

```bash
python3 genai-eval/scripts/check_eval_card.py genai-eval/examples/rag-grounding/eval-card.json
```

Real output:

```
genai-eval/examples/rag-grounding/eval-card.json: 0 error(s), 1 warning(s)

  WARNING [Gate 2] domain.harm_pathways[2]: pathway 'hp3' is ranked but no construct measures it

Gates 6, 7, 8, 10 and 11 need a qualification block and are not checked here.
```

Exit code: `0`. Zero errors, one warning, and the warning is deliberate --
see "The pathway we chose not to measure" below.

## The trace matrix, one item at a time

`items/pool.jsonl` item `i10` is the clearest single-item walk:

```json
{"claim_id": "cl3", "item_id": "i10",
 "prompt": "What's the current refund window, and has it changed recently?",
 "retrieved_chunks": [
   {"chunk_id": 1, "text": "[Superseded 2025-11-01] Refund window: 14 days from purchase."},
   {"chunk_id": 2, "text": "[Effective 2026-02-01] Refund window: 30 days from purchase, prorated for annual plans."}
 ]}
```

- **Item -> claim.** `i10.claim_id` is `cl3`. `cl3` (`claims[2]`) reads: "Every
  citation the assistant attaches to a claim points to a retrieved chunk
  whose content actually supports that specific claim." This item exists to
  probe exactly that: two chunks share a topic (the refund window) but only
  chunk 2 states the *current* figure, so an answer that cites chunk 1 for
  "the refund window is 30 days" would be a citation-claim mismatch even
  though chunk 1 is genuinely about refund windows.
- **Claim -> construct.** `cl3.construct` is `c_citation`: "every citation
  attached to a claim in the answer actually supports that specific claim."
- **Construct -> harm pathway.** `c_citation.harm_pathways` is `["hp2"]`.
  `domain.harm_pathways[1]` (`hp2`, rank 2, severity medium) reads: "The
  assistant attaches a citation to a claim that the cited chunk does not
  actually support ... so a reader who spot-checks 'is there a citation' is
  satisfied while the underlying claim is still unverified." That is exactly
  the failure mode `i10` is built to surface: a superseded chunk that looks
  on-topic enough to cite.
- **Claim -> evidence and task model.** `cl3` also has an `evidence_model`
  entry (`ev3`, scored against `rubrics/grounding.md`'s Rule 3) and a
  `task_model` entry (`tm3`, task family "multi-chunk answer requiring the
  assistant to attribute individual claims to individual sources"), which
  Gate 4 requires of every claim.

The other two claims trace the same way: `cl1` (`c_grounding` -> `hp1`,
unsupported assertions, e.g. item `i04` asking a max-file-size question
against a single supporting chunk) and `cl2` (`c_grounding` -> `hp1`,
decline-vs-fabricate under insufficient context, e.g. item `i07` asking
whether a sixth seat can be bought for the Family plan for an extra fee,
against the same chunk used elsewhere to state what the plan includes --
which says nothing at all about buying more).

## The pathway we chose not to measure

`domain.harm_pathways` lists three pathways, ranked 1-3, but the two
constructs in this card only trace to `hp1` and `hp2`. `hp3` -- a retrieved
chunk leaking internal-only text or another customer's PII into a visible
answer -- is real and ranked, but this card does not measure it; that's the
job of a separate PII-redaction eval that inspects retrieval output directly.
Gate 2 notices: "pathway is ranked but no construct measures it" is a
**warning**, not an error, so the card still validates clean. We're showing
this rather than quietly dropping `hp3` from the card, because a ranked,
acknowledged, unmeasured pathway is a materially different thing from a
pathway nobody ever thought about -- and the validator's own distinction
between warning and error is what makes that visible mechanically instead of
only in prose.

## Every file the card names, and why

Two conventions from `eval-card.schema.md` mean the card points at files
beyond its own JSON: every path is card-relative, and several fields outside
`items` name files no gate currently checks for existence. Here is every one,
with real, minimal content:

| Card field | File | What it holds |
|---|---|---|
| `items.source` | `items/pool.jsonl` | The 12-item pool, 4 items per claim, `item_id` + `claim_id` on every row (what makes Gate 4 checkable). |
| `items.splits.dev.path` | `items/dev.jsonl` | 3 freely-inspectable items, one per claim, for iterating on the rubric during design. |
| `items.splits.test.path` | `items/test.jsonl` | The 4-item sealed test split (Gate 5). |
| `evidence_model[].rubric_ref` (all three) | `rubrics/grounding.md` | The three scoring rules the evidence model claims exist: unsupported assertions, decline-vs-fabricate, citation-claim mismatch -- plus the 1-4 scale used in the gold set below. |
| `grader.rubric_ref` | `rubrics/grounding.md` | Same file; the LLM judge is scored against the same rubric the evidence model states. |
| `grader.gold_set` | `labels/gold.csv` | 12 rows, one per pool item: `item_id`, `judge_score`, and **two** independent human rater columns (`human_a`, `human_b`). |
| `preregistration.protocol.prompts_ref` | `protocol.md` | The fixed system prompt, turn template, seeds (`[11, 23, 47]`), temperature (`0.2`), and elicitation budget -- the exact protocol `preregistration.content_hash` is a hash of. |

Verified mechanically (this must print nothing but the confirmation line):

```bash
python3 - <<'EOF'
import json, os
base = "genai-eval/examples/rag-grounding"
card = json.load(open(os.path.join(base, "eval-card.json"), encoding="utf-8"))
refs = [card["items"]["source"], card["grader"]["rubric_ref"],
        card["grader"]["gold_set"],
        card["preregistration"]["protocol"]["prompts_ref"]]
refs += [s["path"] for s in card["items"]["splits"].values()]
refs += [e["rubric_ref"] for e in card["evidence_model"]]
for ref in refs:
    if not os.path.exists(os.path.join(base, ref)):
        print("dangling:", ref)
EOF
```

Real output: nothing (no line was printed).

`preregistration.content_hash` is `sha256:3ffe1b91b2ba7c04efe260ab19289eb12878daea7e2241de71879453b14122a6`,
computed over `protocol.md` as written, not invented:

```bash
python3 -c "import hashlib,sys; print('sha256:' + hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  genai-eval/examples/rag-grounding/protocol.md
```

## The gold set composes with `calibrate.py`

Because `labels/gold.csv` is a real 2-rater gold set rather than a
placeholder, it demonstrates the two skills (card validation and judge
calibration) composing on the same eval, not just sitting side by side:

```bash
python3 genai-eval/scripts/calibrate.py genai-eval/examples/rag-grounding/labels/gold.csv --seed 7
```

Real output:

```
# Judge calibration report

Judge column `judge_score` against 2 human rater column(s), 12 items.

## What this report cannot tell you

- Columns matched by name rather than stated explicitly: judge_score -> judge score; human_a, human_b -> human rater; item_id -> item id. A wrong match here produces a confident number from the wrong data; name the column explicitly if any of these is not what you meant.
- No response length column, so the length-bias probe is unavailable.
- No generator column, so the self-preference probe is unavailable.
- Only the agreement figures use every human rater column. The length-bias probe, the disagreement clusters and the power baseline all read `human_a` alone, the first human rater column.
- This report measures agreement, not correctness. A judge that agrees with a mistaken human is still wrong.

## Agreement

Judge-human agreement (Krippendorff's alpha): 0.642, 95% CI [0.207, 1.000], n = 12

Human-human agreement, the ceiling: 0.771, 95% CI [0.392, 1.000], n = 12

The judge falls below the ceiling. Humans agree with each other more than the judge agrees with them, so automating this rubric costs measurable accuracy.

## Statistical power

Observed exact-agreement rate: 0.750, n = 12 rows carrying both a judge score and a human label.
This item count cannot detect any difference at conventional alpha and power. Any comparison drawn from it is noise.

## Judge bias

**Not measured:**

- Length bias: needs a response length column (characters, tokens or words).
- Self-preference: needs a generator column naming which model produced each response.

## Disagreement clusters

Biggest first. These are counts, not causes; name each pattern yourself by reading the items behind it.

| Human | Judge | Count | Share | Example items |
|---|---|---|---|---|
| 2.0 | 3.0 | 2 | 0.67 | i04, i12 |
| 3.0 | 4.0 | 1 | 0.33 | i10 |
```

**Headline figure:** judge-human agreement is 0.642 against a 0.771
human-human ceiling (both n = 12) -- the judge falls below the ceiling, and
at n = 12 (a deliberately small worked-example gold set, not a production
one) the confidence intervals are wide enough that this should be read as "a
ceiling exists and the judge is below it," not as a precise gap. Because
`gold.csv` carries two human columns, `calibrate.py` could compute that
ceiling at all -- a single-rater gold set would have produced the refusal
documented in `judge-calibration`'s sibling case ("no human-human agreement
ceiling ... Gate 6 cannot be answered") instead of this comparison.

## What this card does not yet carry

This card validates clean against Gates 1, 2, 3, 4, 5 and 9 -- the six gates
answerable from the card and its item pool alone. It has no `qualification`
block, and so it cannot yet answer:

- **Gate 6** (judge-human agreement against the human-human ceiling) -- the
  calibration run above is real, but nothing in the card records it as a
  qualification verdict; `eval-qualify` is what would append that.
- **Gate 7** (statistical power to detect the minimum interesting
  difference) -- `preregistration.threshold.minimum_interesting_difference`
  is set (`0.05`), but no power analysis against a real result sample has
  been run or recorded.
- **Gate 8** (criterion evidence on a real sample) -- not attempted here.
- **Gate 10** (does the result cross the preregistered threshold?) -- there
  is no result yet. `status` is `sealed`, not `qualified`.
- **Gate 11** (is the instrument saturated or leaked?) -- not attempted here.

This is a well-formed, falsifiable, traceable, sealed evaluation design. It
is not yet a qualified one.

## The tripwire: tampering with the sealed split

The whole point of Gate 5 is that the sealed test split cannot change
silently. To show it firing for real, we appended one line to
`items/test.jsonl` after it had already been sealed and hashed:

```bash
printf '{"claim_id": "cl1", "item_id": "i-leaked", "prompt": "tampered row appended after sealing", "retrieved_chunks": []}\n' \
  >> genai-eval/examples/rag-grounding/items/test.jsonl
python3 genai-eval/scripts/check_eval_card.py genai-eval/examples/rag-grounding/eval-card.json
```

Real output:

```
genai-eval/examples/rag-grounding/eval-card.json: 1 error(s), 1 warning(s)

  WARNING [Gate 2] domain.harm_pathways[2]: pathway 'hp3' is ranked but no construct measures it
  ERROR [Gate 5] items.splits.test.sha256: the test split has changed since it was sealed (recorded e68d01166ff1..., found 11c38a6c22f9...); every number computed from it measures something other than what was sealed

Gates 6, 7, 8, 10 and 11 need a qualification block and are not checked here.
```

Exit code: `1`. The hash is over the file's raw bytes, so this fires on a
single appended line -- no JSON parsing, no semantic diff, nothing that could
be fooled by reformatting the same items. We then restored `items/test.jsonl`
to the exact sealed content (the 4 lines above, byte-for-byte -- confirmed by
recomputing the hash, which matched `e68d01166ff1d37be56b74ae4d85474311f3935b361fb785b65ce8a737be40a4`
again) and re-ran the validator:

```
genai-eval/examples/rag-grounding/eval-card.json: 0 error(s), 1 warning(s)

  WARNING [Gate 2] domain.harm_pathways[2]: pathway 'hp3' is ranked but no construct measures it

Gates 6, 7, 8, 10 and 11 need a qualification block and are not checked here.
```

Exit code: `0` again. `git status` at the end of this exercise shows
`items/test.jsonl` unmodified from what was committed.
