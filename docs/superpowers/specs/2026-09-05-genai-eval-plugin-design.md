# genai-eval — design

*Design doc. Written 2026-09-05. Source: an internal SOP, "GenAI evaluation and
validation system design", which merges Evidence-Centered Design (ECD/ECBD),
measurement modelling, and risk-based governance into eleven steps across four
phases, each with a yes/no gate.*

## 1. Summary

A new plugin, `genai-eval`, holding two composed skills:

- **`eval-design`** — SOP steps 1–6 (Frame, Design). Turns "we should evaluate
  this" into a construct, a claim/evidence/task operationalisation, a
  contamination-controlled item pool, a calibrated grader, and a sealed
  preregistration.
- **`eval-qualify`** — SOP steps 7–11 (Qualify, Operate). Measures whether the
  instrument itself is trustworthy, then reports and monitors it.

They are coupled by one machine-readable artifact, the **eval card**
(`eval-card.json`), and share a stdlib-only statistics toolkit.

The design's organising commitment: **a gate that cannot be checked
mechanically will be rubber-stamped.** Nine of the eleven gates are therefore
bound to either a validator or a computation. Only Gate 8 remains judgement,
and the tooling labels that honestly rather than hiding it.

## 2. Why this shape

The source SOP is roughly 60% reference essay — a survey of the field, seven
live debates, and a source list — and 40% procedure. Transcribing it into a
SKILL.md would load thousands of words of orientation on every trigger while
telling the model very little about what to *do*. This design splits the two:
SKILL.md holds the procedure, `references/` holds the essay.

The SOP's gates are its best feature and its biggest implementation risk. Each
is a yes/no question with a stated consequence, which maps cleanly onto an
agent checklist — but an LLM asked "does every item trace to a claim?" will
answer "yes" without looking. Binding gates to artifacts is what makes the
difference between a checklist and a check.

### Decisions taken during design

| Decision | Choice | Rationale |
|---|---|---|
| Skill count | Two, composed | Designing an eval and qualifying one have different inputs, outputs, and trigger phrases; one skill covering both triggers inconsistently |
| Eval subjects in scope | Production LLM/RAG, agentic systems, model/prompt selection, safety sign-off | All four are in daily use, which makes tier routing mandatory rather than optional |
| Statistics scope | Agreement + classical item analysis + power | All implementable in pure stdlib; gives Gates 6, 7, 9, 10 real teeth. Full IRT rejected — needs numpy/scipy, breaks the repo's stdlib-only rule |
| Packaging | One plugin, two skills inside | The two skills share a toolkit and a handoff artifact; two plugins would duplicate the toolkit or need a dependency the marketplace cannot express |
| Handoff artifact | Machine-readable eval card, plus a bare mode that needs no card | The card makes gates enforceable; bare mode keeps the most common real request (judge vs. human labels) from requiring ceremony |
| Card format | JSON, with optional YAML read if PyYAML is present | The stdlib has no YAML parser. JSON is already the house pattern (`explain-code`'s `sample_spec.json`). Readability recovered via the renderer |

## 3. Architecture

### 3.1 The eval card

One file per eval, `eval-card.json`. `eval-design` writes it; `eval-qualify`
appends a `qualification` block. Abbreviated — the full field reference ships
as `templates/eval-card.schema.md`:

```json
{
  "schema_version": 1,
  "tier": 2,
  "status": "sealed",
  "decision": {
    "question": "Ship the new retrieval prompt to 100% of traffic?",
    "owner": "role or name",
    "outcomes": [
      {"result": "pass",       "action": "roll to 100%"},
      {"result": "fail",       "action": "hold, revert to v3"},
      {"result": "borderline", "action": "escalate to tier 3"}
    ]
  },
  "domain": {
    "harm_pathways": [
      {"id": "hp1", "rank": 1, "severity": "high",
       "description": "cites a source that does not support the claim"}
    ]
  },
  "constructs": [
    {"id": "c_grounding",
     "definition": "...",
     "positive_evidence": ["every factual sentence traceable to a retrieved chunk"],
     "negative_evidence": ["asserts a date or figure absent from all retrieved chunks"],
     "harm_pathways": ["hp1"]}
  ],
  "claims":         [{"id": "cl1", "construct": "c_grounding", "statement": "..."}],
  "evidence_model": [{"id": "ev1", "claim": "cl1", "observable": "...",
                      "scoring_rule": "...", "rubric_ref": "rubrics/grounding.md"}],
  "task_model":     [{"id": "tm1", "claim": "cl1", "task_family": "...",
                      "conditions": ["retrieval returns 0 relevant docs"]}],
  "items": {
    "source": "items/pool.jsonl",
    "sampling_frame": "prod logs 2026-06..08, stratified by intent",
    "contamination_controls": {"canary": "<uuid>", "date_stamped": true, "novel_items": 40},
    "splits": {
      "dev":  {"path": "items/dev.jsonl"},
      "test": {"path": "items/test.jsonl", "sealed": true,
               "sha256": "...", "sealed_at": "2026-09-05T10:00:00Z"}
    }
  },
  "grader": {
    "kind": "llm_judge",
    "mode": "pairwise",
    "gold_set": "labels/gold.csv",
    "bias_probes": ["position", "length", "verbosity", "self_preference", "prompt_sensitivity"]
  },
  "preregistration": {
    "sealed_at": "2026-09-05T10:00:00Z",
    "content_hash": "sha256:...",
    "protocol": {"seeds": [0, 1, 2], "temperature": 0.0,
                 "elicitation_budget": "3 attempts, best-of-n off"},
    "baselines": ["human", "prior_model_v3", "ablation_no_retrieval"],
    "threshold": {"minimum_interesting_difference": 0.03,
                  "decision_rule": "lower bound of 95% CI > 0.90"}
  }
}
```

Each item in the pool carries a `claim_id`, which is what makes Gate 4
checkable.

`eval-qualify` appends a `qualification` block holding judge calibration, item
analysis, validity evidence by AERA category, per-gate verdicts, results, and
monitoring state.

### 3.2 Gate binding

| Gate | Question | Enforcement | Mechanism |
|---|---|---|---|
| 1 | Named owner + action per outcome | Mechanical | `decision.owner` non-empty; pass/fail/borderline all present |
| 2 | Measures trace to ranked pathways | Mechanical | every construct references an `hp*` that has a `rank` |
| 3 | Falsifiable construct | Mechanical | `negative_evidence` non-empty (quality remains judgement) |
| 4 | Every item maps to a claim, every claim has 3+ items | Mechanical | orphan and thin-claim scan across pool and card |
| 5 | Test split sealed and uncontaminated | Mechanical | recorded sha256 re-verified against the file; canary present |
| 6 | Judge-human agreement reaches the human-human floor | Computed | Krippendorff alpha with bootstrap CIs, compared |
| 7 | Instrument detects the MDE | Computed | power calculation vs. actual item count |
| 8 | Criterion evidence on a real sample | Judgement | validator requires a non-empty block with an `n` and a held-out ref; otherwise emits the "proxy of unknown quality" label |
| 9 | Threshold set before the run | Mechanical | prereg `content_hash` and `sealed_at` predate every result timestamp |
| 10 | Result crosses the threshold | Computed | decision rule applied to the CI, not the point estimate |
| 11 | Saturated or leaked | Computed | ceiling proportion; canary hit rate |

### 3.3 Tier routing

Both skills state the tier before doing anything else, and list the steps they
will run and skip.

| Tier | Trigger | `eval-design` | `eval-qualify` |
|---|---|---|---|
| 1 — daily regression | Catch breakage | 1, 5, 6 | 9, 10, 11 (light) |
| 2 — per release | Compare options | + 3, 4 | + 7 |
| 3 — sign-off / external claim | Defend a claim | + 2 (all) | + 8 (all) |

**Deviation from the source SOP, taken deliberately.** The SOP's tier table
places step 9 in Tier 1 but omits step 10, even though Gate 10 is the actual
go/no-go and a regression test plainly has a decision. Here steps 10 and 11 are
always in scope, with tier controlling depth: at Tier 1, step 10 collapses to
"did the threshold hold"; at Tier 3 it is the full report with effect sizes,
item-level release, and a failure taxonomy.

### 3.4 Bare mode

`eval-qualify` runs with no card, on a single CSV. The **minimum contract is
two columns**: one judge score and one human label per row. Everything else is
optional and unlocks more of the run — an `item_id` column enables clustered
bootstrap resampling, additional human-rater columns enable the agreement
ceiling, and response length or presentation order enable the matching bias
probes. The skill reports which columns it found and which parts of the
analysis are therefore unavailable. Given the full set it:

1. Human-human agreement first, establishing the ceiling. **With only one human
   rater there is no ceiling**, and the skill says so explicitly rather than
   comparing the judge against nothing.
2. Judge-human agreement.
3. Bootstrap CIs on both, resampled by item.
4. Whatever bias probes the available columns support.
5. Disagreement clustering into a draft error taxonomy.
6. A short calibration report, plus an offer to promote the result into a full
   card.

That path covers SOP steps 3, 6, 7 and 10 in one run.

## 4. Components

### 4.1 `scripts/evalstats.py`

Standard library only.

**Agreement.** Cohen kappa; linear and quadratic weighted kappa (rubrics are
usually ordinal, and unweighted kappa penalises a 4-vs-5 disagreement as
heavily as 1-vs-5); Fleiss kappa; Krippendorff alpha with nominal, ordinal and
interval difference functions, tolerant of missing data and any number of
raters. `bootstrap_ci` resamples **by item, not by rating** — ratings cluster
within items, and resampling them independently produces intervals that are too
narrow.

**Bias probes.** Position bias from order-swapped pairwise presentations;
length bias as the gap between judge-length and human-length correlation (the
human correlation is not itself bias, since longer answers are sometimes
genuinely better); self-preference as the score delta on the judge's own
model's outputs; prompt sensitivity as variance across rubric paraphrases.

**Item analysis.** Difficulty (p-value), point-biserial discrimination, KR-20
and ordinal reliability, and automatic flagging of non-discriminating items
(r_pb below 0.2), floor and ceiling items, and mis-keyed items (negative r_pb).
Dimensionality via Jacobi eigenvalue decomposition of the correlation matrix,
giving the scree and first-eigenvalue ratio — enough for a unidimensionality
judgement under Gate 8's internal-structure category. Full IRT is out of scope.

**Power and comparison.** MDE and required-n for proportions using
`statistics.NormalDist().inv_cdf`; McNemar with an exact binomial tail for
paired model comparison on shared items; paired bootstrap for ordinal scores.

**Saturation.** Ceiling proportion and canary hit rate for Gate 11.

### 4.2 `scripts/check_eval_card.py`

A linter, not an assertion. Reports **every** violation in one pass with a JSON
path and a gate number rather than dying on the first. Exits non-zero on any
error-level gate failure. `--format json` for machine use. Mirrors the
structure of the existing `check_ste.py`.

### 4.3 `scripts/render_eval_card.py`

Renders a card, with or without its `qualification` block, into a readable
markdown Eval Card: decision, construct, claims, gate verdicts with evidence,
calibration and item statistics with confidence intervals, known limits. Where
Gate 8 is unmet, the rendered document carries the "proxy of unknown quality"
label in its header rather than in a footnote.

### 4.4 Skill bodies

**`eval-design/SKILL.md`** — triggers on "design an eval", "build an eval set",
"how should I evaluate X", "set up LLM-as-judge", "write a rubric", "what
should I measure", and on a user about to compare models or prompts with no
protocol. Explicitly not for interpreting results that already exist.

**`eval-qualify/SKILL.md`** — triggers on "is my judge reliable", "how good is
my eval", "compute Krippendorff alpha", "is this result significant", "do I
have enough items", "audit this benchmark", and on being handed judge scores
with human labels. States that it runs standalone on a two-column CSV.

Both follow the house structure used by the existing skills here: a "When to
use" list, a "When NOT to use" list, then numbered process steps.

### 4.5 Reference files

`eval-design/references/`: `ecd.md` (the three-model spine with a worked
example), `constructs.md` (writing falsifiable definitions), `item-pools.md`
(sampling frames, difficulty spread, contamination controls), `graders.md`
(rubric design, pairwise vs. absolute, known judge biases).

`eval-qualify/references/`: `validity.md` (the five AERA/APA categories and
what counts as evidence for each), `item-analysis.md`, `power.md`, and
`field-notes.md` (the source SOP's field survey and its seven live debates).

## 5. Data flow

```
eval-design  --writes-->  eval-card.json (status: draft -> designed -> sealed)
                              |
                    check_eval_card.py  (Gates 1-5, 9)
                              |
                          [ run the eval ]
                              |
eval-qualify --reads--->  eval-card.json + results/labels
             --runs---->  evalstats.py   (Gates 6, 7, 10, 11)
             --appends->  qualification block
                              |
                    render_eval_card.py --> Eval Card (markdown)
                              |
                    optional: improvement-plan / STE for stakeholder versions
```

Bare mode short-circuits this: `labels.csv -> evalstats.py -> calibration
report`, with no card at any point.

## 6. Error handling

- **One human rater.** No agreement ceiling exists. The toolkit refuses to
  report one and emits an explicit limitation instead of silently comparing the
  judge against nothing.
- **Degenerate variance** in point-biserial or correlation returns a flag, not
  a crash or a NaN that propagates.
- **Samples too small to bootstrap** warn loudly rather than returning a narrow,
  confident-looking interval.
- **Ragged or missing ratings** are handled natively by Krippendorff alpha; the
  kappa functions error with a clear message rather than imputing.
- **Card validation** always reports the full violation set, so a user fixes one
  card once rather than iterating through failures one at a time.
- **A card whose recorded `sha256` no longer matches its test split** fails Gate
  5 loudly. This is the contamination tripwire and must never warn-and-continue.

## 7. Testing

Known-answer tests, not smoke tests — the plugin's premise is measurement
rigour, and a weakly tested statistics toolkit would undercut it.

- **Published worked examples.** The canonical Krippendorff nominal example
  against its published alpha; a textbook Fleiss example; hand-computable 2x2
  kappa and small KR-20 matrices; McNemar against the exact binomial.
- **Properties.** alpha = 1 under perfect agreement; alpha near 0 under
  independent random rating; alpha below 0 under systematic disagreement;
  weighted kappa at least unweighted kappa on ordinal data.
- **Bootstrap.** Determinism under a fixed seed, and a simulation check that a
  nominal 95% interval covers the true value at approximately 95%.
- **Validator.** One deliberately broken card per gate, asserting that gate and
  only that gate fires.
- **Renderer.** Golden-file test, following `test_render.py` in `explain-code`.

Each suite runs directly under the stdlib `unittest` runner, matching
`test_check_ste.py`. CI: `.github/workflows/genai-eval-tests.yml`, mirroring
`ste-tests.yml`.

## 8. File layout

```
genai-eval/
├── .claude-plugin/plugin.json
├── README.md
├── scripts/
│   ├── evalstats.py
│   ├── check_eval_card.py
│   ├── render_eval_card.py
│   └── test_*.py
├── templates/
│   ├── eval-card.template.json
│   └── eval-card.schema.md
├── examples/
│   ├── judge-calibration/          # bare mode, end to end
│   │   ├── labels.csv
│   │   └── README.md
│   └── rag-grounding/              # a complete tier-2 card
│       ├── eval-card.json
│       └── items.jsonl
└── skills/
    ├── eval-design/
    │   ├── SKILL.md
    │   └── references/{ecd,constructs,item-pools,graders}.md
    └── eval-qualify/
        ├── SKILL.md
        └── references/{validity,item-analysis,power,field-notes}.md
```

The shared `scripts/` directory sits at plugin root because both skills use it.
No existing plugin in this repo references a path above its own skill
directory, so **the first implementation task is to confirm that resolution
works**. Fallback if it does not: give each skill its own `scripts/` directory
and accept one relative cross-reference from `eval-qualify` to the validator.

## 9. Repo integration

- `.claude-plugin/marketplace.json` — a new entry with `"source": "./genai-eval"`.
- `README.md` — three edits: the intro paragraph listing the plugins, the
  "What's inside" tree, and a "Try the eval toolkit directly" section matching
  the two that already exist for the `explain-code` renderer and the STE checker.
- `.github/workflows/genai-eval-tests.yml` — new, mirroring `ste-tests.yml`.

**Composition with existing plugins.** `eval-qualify` hands off to
`improvement-plan` when a qualification report needs a leadership audience, and
to `simplified-technical-english` when readers are non-native, rather than
growing its own stakeholder-communication section. This keeps the marketplace
coherent: the eval plugin measures, the existing plugins explain.

## 10. Phasing

1. **Phase 1** — plugin skeleton, `evalstats.py` with its known-answer tests,
   `eval-qualify` in bare mode, the `examples/judge-calibration/` worked
   example, and the `genai-eval-tests.yml` workflow. Independently useful and
   shippable alone.
2. **Phase 2** — `templates/eval-card.template.json` and
   `templates/eval-card.schema.md`, `check_eval_card.py` with its per-gate
   tests, `eval-design`, and the `examples/rag-grounding/` card.
3. **Phase 3** — `render_eval_card.py`, all eight reference files, citation
   verification, and the remaining repo integration (marketplace entry, README
   edits).

Phase 1 first because it is both the most differentiated half and the one that
stands alone if later phases slip.

**This spec is too large for one implementation plan.** Each phase gets its
own plan and its own implementation cycle. The first plan covers Phase 1 only.

## 11. Citation verification

The source SOP's bibliography mixes verifiable and unverifiable entries.
Recognised and safe to cite: ECBD (ACL 2024), Jacobs and Wallach (arXiv
1912.05511), Mislevy et al. (CSE Report 632), GDPval (arXiv 2510.04374), and the
NIST AI RMF to ISO/IEC 42001 crosswalk.

Postdating the assistant's knowledge cutoff and therefore **unverified**:
RuVerBench (arXiv 2606.29920), the item-level data release paper (arXiv
2604.03244), the GEM 2026 paper, the Stanford AIMS textbook, the NAE piece, the
UK AISI lessons post, the EU AI Watch piece, and the Agent Evaluation Science
Symposium listing.

Every citation must be resolved before `field-notes.md` ships. Anything that
does not resolve is dropped or explicitly marked unverified. A plugin whose
premise is measurement rigour cannot ship a bibliography taken on trust.

## 12. Out of scope

- **Item Response Theory and factor analysis.** The correct statistics for Steps
  7 and 8, but they need numpy/scipy and would break the stdlib-only rule every
  plugin here follows. `evalstats.py` provides classical test theory plus an
  eigenvalue scree, and `item-analysis.md` says plainly where that stops.
- **Running evals.** These skills design and qualify instruments; they do not
  execute model calls, host a harness, or manage sandboxes.
- **A hosted item-pool store.** Items live as JSONL in the user's own repo.
- **Automatic contamination detection** beyond canary strings and hash-sealed
  splits.
- **Stakeholder communication.** Delegated to `improvement-plan`.
