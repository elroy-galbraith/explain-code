# The eval card — field reference

An eval card (`eval-card.json`) is the machine-readable record of one
evaluation: the decision it informs, the construct and claims it
operationalizes, the item pool and sealed test split it draws on, the grader
that scores it, and the preregistered threshold it will be judged against.
`eval-design` writes the card; a validator (`check_eval_card.py`, Task 8)
checks it against six of the SOP's eleven gates. `eval-qualify` later appends
a `qualification` block — see "Gates this file does not yet describe" below.

The card is JSON, not YAML. The Python standard library has no YAML parser,
and this repo's tooling is stdlib-only throughout, so JSON is the format a
script can actually read without a dependency. (JSON is also already the
house pattern elsewhere in this repo, e.g. `explain-code`'s `sample_spec.json`.)

Two conventions apply across the whole file and are easy to miss because
they live in the item pool and the filesystem rather than in the card's own
keys:

- **Every item in the pool carries a `claim_id`.** The pool is a JSONL file
  referenced by `items.source`, not part of the card's JSON tree — but every
  row in it must carry `item_id` and `claim_id`. That single convention is
  what makes Gate 4 ("does every item trace to a claim?") checkable by a
  script at all. Without it, that question can only be answered by a human
  reading the pool.
- **Paths inside a card resolve relative to the card file's own directory,
  never the process's working directory.** `items.source`, `items.splits.*.path`,
  `evidence_model[].rubric_ref`, `grader.rubric_ref`, `grader.gold_set`, and
  `preregistration.protocol.prompts_ref` are all card-relative paths. A card
  and its item pool travel together as a unit; resolving against the
  current working directory would break validation the moment anyone ran it
  from somewhere other than the card's own folder.

Each table below covers one top-level block. The **Gate** column names the
SOP gate (per spec §3.2) that mechanically reads that field today. A dash
means no gate reads the field yet — either because the field is descriptive
context rather than something a gate checks, or because it feeds a gate that
is Phase 2B work (see the closing section).

## Card-level fields

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `schema_version` | int | Yes — must currently be `1` | Lets the validator refuse a card written against a future or unknown schema instead of misreading it | — (structural check, not a numbered gate) |
| `id` | string | No | A short, stable identifier for the eval, for cross-referencing outside the card | — |
| `title` | string | No | Human-readable name for the eval | — |
| `tier` | int, 1-3 | Yes | Which of the SOP's three tiers this eval runs at; controls which steps `eval-design`/`eval-qualify` run (spec §3.3) | — (structural check, not a numbered gate) |
| `status` | string, one of `draft`, `designed`, `sealed`, `qualified`, `retired` | No — but if present, must be one of the five values | Where the card is in its lifecycle | — (structural check, not a numbered gate) |
| `created` | string, ISO 8601 date | No | When the card was first written | — |

## `decision` — Gate 1

Gate 1 asks: is there a named, accountable owner, and does every possible
result lead to a stated action? An eval nobody owns, or whose "borderline"
result has no action attached, is a vanity metric — it will be computed and
then ignored.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `question` | string | Recommended | The actual decision this eval exists to inform | — |
| `owner` | string | Yes — non-blank | The named person or role accountable for acting on the result | 1 |
| `outcomes[]` | array of objects | Yes — one entry for each of `pass`, `fail`, `borderline` | Maps each possible result to what happens next | 1 |
| `outcomes[].result` | string, one of `pass`, `fail`, `borderline` | Yes — all three must appear across the array | Which result this entry describes | 1 |
| `outcomes[].action` | string | Yes — non-blank | What will actually happen when this result occurs | 1 |

## `domain` — Gate 2

Gate 2 asks: does every measure trace back to a ranked route to harm? An
unranked list of harm pathways justifies measuring any of them — the ranking
is the part that forces "measure what matters" rather than "measure what's
easy."

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `users` | string | Recommended | Who is exposed to the system being evaluated | — |
| `operating_conditions` | string | Recommended | The conditions the system runs under in practice | — |
| `harm_pathways[]` | array of objects | Yes — at least one, and every construct must reference one | The catalog of ranked ways this system can cause harm | 2 |
| `harm_pathways[].id` | string | Yes — unique within the card | Referenced from `constructs[].harm_pathways` | 2 |
| `harm_pathways[].rank` | int | Yes — no duplicates among referenced pathways | Orders pathways by importance; this is what makes tracing to "the pathway that matters" checkable | 2 |
| `harm_pathways[].severity` | string | Recommended | How bad this pathway is if it occurs | — |
| `harm_pathways[].description` | string | Recommended | What this pathway looks like in practice | — |

## `constructs[]` — Gates 2 and 3

Gate 3 asks: can you state what evidence would count *against* this
construct? If not, nothing can disconfirm it, which means every result
confirms it, which means it measures nothing. Gate 2 also reads this block:
each construct must trace to at least one ranked harm pathway from `domain`.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `id` | string | Yes — unique within the card | Referenced from `claims[].construct` | 2, 4 |
| `definition` | string | Yes | What the construct means | — |
| `positive_evidence[]` | array of strings | Recommended | What would count *for* the construct | — |
| `negative_evidence[]` | array of strings | Yes — at least one non-blank entry | What would count *against* the construct — this is what makes the construct falsifiable | 3 |
| `harm_pathways[]` | array of strings (harm pathway ids) | Yes — at least one, each must reference a ranked `domain.harm_pathways[].id` | Traces this construct to a ranked route to harm | 2 |

## `claims[]` — Gate 4

Gate 4 is the gate the card format exists for: every item in the pool must
map to a claim, and every claim must be backed by at least three items. A
claim with fewer than three items cannot support a claim-level reading of a
score.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `id` | string | Yes — unique within the card | Referenced from `evidence_model[].claim`, `task_model[].claim`, and each item pool row's `claim_id` | 4 |
| `construct` | string (a `constructs[].id`) | Yes — must reference an existing construct | Which construct this claim operationalizes | 4 |
| `statement` | string | Yes | The specific, checkable claim being made | — |

## `evidence_model[]` — Gate 4

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `id` | string | Yes — unique within the card | Identifies this observable/scoring pairing | — |
| `claim` | string (a `claims[].id`) | Yes — must reference an existing claim; every claim needs at least one `evidence_model` entry | Which claim this observable provides evidence for | 4 |
| `observable` | string | Yes | What is actually observed or measured | — |
| `scoring_rule` | string | Yes | How the observable becomes a score | — |
| `rubric_ref` | string (path, card-relative) | Recommended | Pointer to the rubric document used to apply the scoring rule | — |

## `task_model[]` — Gate 4

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `id` | string | Yes — unique within the card | Identifies this task-family entry | — |
| `claim` | string (a `claims[].id`) | Yes — must reference an existing claim | Which claim this task family is designed to exercise | 4 |
| `task_family` | string | Yes | The family of prompts/tasks that exercise the claim | — |
| `conditions[]` | array of strings | Recommended | Edge conditions this task family is meant to cover (e.g. "retrieval returns nothing relevant") | — |

## `items` — Gates 4 and 5

Gate 4 reads `source` to load the pool off disk — the one check that touches
a file rather than only the card. Gate 5 is the contamination tripwire: a
recorded `sha256` that no longer matches the sealed file means the split
changed after sealing, which the whole point of sealing was to prevent.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `source` | string (path, card-relative) | Yes | The item pool, a JSONL file where every row carries `item_id` and `claim_id` | 4 |
| `sampling_frame` | string | Recommended | Where and how the pool was sampled | — |
| `contamination_controls.canary` | string | Yes — non-blank | A canary string used to detect leakage into training or context | 5 |
| `contamination_controls.date_stamped` | bool | Recommended | Whether items are dated, so future contamination can be bounded in time | — |
| `contamination_controls.novel_items` | int | Recommended | Count of items not present in any prior release | — |
| `splits.dev.path` | string (path, card-relative) | Recommended | The development split, freely inspectable while designing | — |
| `splits.test.path` | string (path, card-relative) | Yes | The sealed test split | 5 |
| `splits.test.sealed` | bool | Yes — must be `true` | Whether the test split is currently sealed | 5 |
| `splits.test.sha256` | string | Yes — must match a hash recomputed over the file's raw bytes | The contamination tripwire itself | 5 |
| `splits.test.sealed_at` | string (ISO 8601 timestamp) | Yes | When the split was sealed | 5 |

## `grader`

No gate implemented in this phase reads this block mechanically. Its fields
exist so that `eval-qualify` (Phase 2B) can run judge calibration against
them — see Gate 6 below.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `kind` | string | Recommended | What kind of grader scores this eval (e.g. `llm_judge`, `rule_based`) | Gate 6 (not implemented this phase) |
| `model` | string | Recommended | Which model/version is doing the grading | Gate 6 (not implemented this phase) |
| `mode` | string | Recommended | Grading mode (e.g. `pairwise`, `pointwise`) | Gate 6 (not implemented this phase) |
| `rubric_ref` | string (path, card-relative) | Recommended | Pointer to the grading rubric | Gate 6 (not implemented this phase) |
| `gold_set` | string (path, card-relative) | Recommended | Held-out human-labeled set used for calibration | Gate 6 (not implemented this phase) |
| `bias_probes[]` | array of strings | Recommended | Which bias probes run (e.g. `position`, `length`, `self_preference`, `prompt_sensitivity`) | Gate 6 (not implemented this phase) |

## `preregistration` — Gate 9

Gate 9 asks whether the decision threshold was fixed before anyone saw a
result. It is checkable at all only because the card records both a content
hash and a sealing timestamp: once `eval-qualify` appends a `qualification`
block with its own result timestamps, Gate 9 also checks that every result
was computed *after* `sealed_at` — a result that predates the seal means the
threshold was chosen knowing the answer. For this to be verifiable,
`preregistration.threshold` must exist and be non-empty; a card that sets no
threshold cannot show that a threshold was fixed before the run.

| Field | Type | Required | What it's for | Gate |
|---|---|---|---|---|
| `sealed_at` | string (ISO 8601 timestamp) | Yes — must parse as a timestamp | When the threshold and protocol were fixed | 9 |
| `content_hash` | string | Yes | Hash of the sealed protocol content, so it cannot be edited after the fact without detection | 9 |
| `protocol.prompts_ref` | string (path, card-relative) | Recommended | Pointer to the exact prompts used | — |
| `protocol.seeds[]` | array of ints | Recommended | Random seeds used for reproducibility | — |
| `protocol.temperature` | number | Recommended | Sampling temperature used | — |
| `protocol.elicitation_budget` | string | Recommended | How many attempts are allowed, and whether best-of-n is used | — |
| `baselines[]` | array of strings | Recommended | What this eval's result will be compared against | — |
| `threshold.metric` | string | Recommended | The metric the decision rule is applied to | Gate 10 (not implemented this phase) |
| `threshold.minimum_interesting_difference` | number | Recommended | The smallest difference considered practically meaningful | Gate 7 (not implemented this phase) |
| `threshold.decision_rule` | string | Yes — non-blank | The actual go/no-go rule applied to the result | Gate 10 (not implemented this phase) |

## Gates this file does not yet describe

This document and the validator it backs cover Gates 1, 2, 3, 4, 5, and 9 —
the six gates answerable from the card and its item pool alone, without
running any statistics. The following are deliberately **not** covered here
because nothing in this phase builds them:

- **Gates 6, 7, 8, 10, and 11** — judge-human agreement against the
  human-human ceiling, statistical power to detect the minimum interesting
  difference, criterion evidence on a real sample, whether the result
  actually crosses the preregistered threshold, and whether the instrument
  is saturated or leaked. These are *computed* or *judgement* gates (spec
  §3.2), not mechanical ones — they need the statistics toolkit
  (`scripts/evalstats/`) run against real results, not just a well-formed
  card.
- **The `qualification` block.** `eval-qualify` appends this block to a
  sealed card, holding judge calibration, item analysis, validity evidence
  by AERA category, per-gate verdicts for Gates 6-8 and 10-11, results, and
  monitoring state. Its shape is Phase 2B work and is intentionally absent
  from `eval-card.template.json`.

A card that validates clean against this document's six gates is a
well-formed, falsifiable, traceable, sealed evaluation design. It is **not
yet a qualified one** — that determination is what Phase 2B's gates exist
to make.
