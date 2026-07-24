---
name: improvement-plan
description: Draft a layered, plain-English improvement plan for non-technical or mixed audiences (product, C-suite, leadership, finance, customer success, non-native English readers). Use when the user asks to "draft a plan", "write an improvement plan", "create a roadmap for leadership", "communicate this work to product / C-suite / stakeholders", or "translate this technical finding into a plan". Output is a Notion-ready or markdown document that orders interventions cheapest-first, sets honest expectations, and ends with explicit stakeholder asks.
---

# Improvement Plan Writer

A skill for writing plan documents that travel well across audiences. Optimised for situations where the writer (engineering / data) needs to brief readers who don't share their context — product, executives, business teams, non-native English speakers — on how to fix a measurable problem.

## When to use

Trigger on requests like:

- "Draft a plan to improve [metric] for [audience]"
- "Write up the improvement plan for the team"
- "Communicate this work to product / C-suite / leadership"
- "Create a roadmap document"
- "Translate this technical investigation into a stakeholder doc"
- "Help me explain this to non-engineers"

## When NOT to use

- Pure technical specs / RFCs / engineering ADRs — too "explainy" for that audience, will read as patronising.
- One-off Slack messages — overkill.
- Customer-facing copy — different tone, different consent model.
- Conference talks / pitches — needs storytelling structure this skill doesn't provide.

## Process

### Step 1 — Establish the audience before writing a single sentence

Confirm with the user (or infer from explicit context):

- **Who reads this?** Engineering, product, leadership, customers, finance, mixed?
- **Are non-native English speakers present?** If yes: avoid idioms, phrasal verbs, long sentences.
- **What decision are they being asked to make?** Approve funding / prioritise / understand / external comms / something else?
- **What context do they already have?** Anchor to existing docs rather than re-explaining.

If the audience is purely technical engineers, stop and recommend a different format (RFC, design doc).

### Step 2 — Anchor to source documents, don't duplicate them

This document is a *plan*, not the substrate. Link to the measurement / investigation / spec that motivates it. The plan summarises the problem in 2 paragraphs, then moves to the proposed action. If the source doc doesn't exist, recommend creating it first.

### Step 3 — Use the fixed macro structure

The section order is fixed. Sections may be omitted if not relevant, but their order should not be rearranged.

1. **Purpose & background callout** (top) — 2 sentences, plus link to source doc.
2. **Summary** — 2 short paragraphs. State the problem and the proposed approach. Include "the key number" as a `>` callout.
3. **The Situation Today** — three sub-sections: What's working / What's not working / The bottom line.
4. **The Plan in One Picture** — single overview table with columns: Stage / What / Effort / Expected impact.
5. **Stages 1 through N** — each with a "Why these come first" framing and 2–4 concrete changes.
6. **Important Caveats** — sample size, statistical reliability, dependencies. Don't bury this.
7. **Recommended Timeline** — week-by-week table.
8. **What Success Looks Like** — measurable milestones at today / interim / target dates.
9. **What We Need from Stakeholders** — explicit asks (engineering hours, partner team time, leadership cadence).
10. **Questions for Decision-Makers** — 3–5 specific questions the doc is asking the reader to answer.
11. **Related Documents** — links.

### Step 4 — Layer by effort, cheapest first

The single most important structural rule. A typical layering:

- **Stage 1: Quick Wins** — text edits, instruction changes, config tweaks. 1–2 weeks. Low risk.
- **Stage 2: Best Practices** — architectural cleanups, new abstractions. 2–4 weeks. Medium risk.
- **Stage 3: Experimental Upgrades** — model swaps, ensemble methods, A/B harness. 4–6 weeks. Higher uncertainty.
- **Stage 4: Long-term Bets** — major changes that need prerequisite data, budget, or sample size. Later. Highest potential.

For each stage, state the gating condition before the next one begins. Stage 3 should not start until Stage 2 is measured. Make the gates explicit.

### Step 5 — Use the consistent micro-structure inside each stage

For every individual change within a stage:

- **Today:** what is currently happening (1 sentence).
- **Change:** what we will do (1 sentence).
- **Why it helps:** the mechanism — why this is expected to move the metric (1–2 sentences).

This three-line pattern is scannable and gives readers a complete mental model of each change without a wall of prose.

### Step 6 — Apply the language rules

**Favour:**

- Short sentences (≤ 20 words is a good target).
- Common words: "change" not "modify", "show" not "demonstrate", "use" not "leverage".
- Concrete numbers with counts in parentheses: "9.5% (2 of 21)", not bare "9.5%".
- Plain technical names: "AI" not "LLM"; "instructions" not "prompt"; "borderline cases" not "low-confidence samples"; "missed approvals" not "false negatives".

**Avoid:**

- Idioms — "move the needle", "low-hanging fruit", "boil the ocean", "when in doubt", "land us at".
- Phrasal verbs where simple verbs work — "implement" not "roll out", "remove" not "take out".
- Jargon — when unavoidable, define inline.
- Single-number predictions — use ranges to convey uncertainty: "15–25 percentage points", not "20 points".
- Mealy hedging — "could potentially maybe perhaps" reads as evasive. Be honest about uncertainty without being soggy.

**Final pass — run the `humanizer` skill over the draft.** Once the prose is written, run the **humanizer** skill (also in this marketplace) in its *embedded mode* over the plan text as a last language pass. It enforces many of the rules above automatically: it cuts em dashes, rule-of-three padding, "AI vocabulary", filler phrases, and excessive hedging — exactly the tells that make a plan read as machine-written to a non-technical or non-native audience.

Two constraints when you run it:

- **Tell-removal, not voice.** A stakeholder plan wants the neutral, plain register. Do not let humanizer's personality/voice behaviour add opinions or first person; embedded mode over plan prose already keeps it off.
- **Complement, don't replace.** Humanizer does not add the things this skill requires — counts in parentheses ("9.5% (2 of 21)"), inline-defined jargon, or forecast ranges. Keep those; humanizer only removes tells, it does not supply this structure.

If the humanizer skill is not installed, skip this pass and apply the rules above by hand.

### Step 7 — Be visibly honest about uncertainty

Always include a "Caveats" or "Important Caveat" section. Specifically:

- If the sample size is small, say so and quantify the noise threshold.
- If an estimate is a hunch, call it a rough estimate — don't pretend it's a forecast.
- If a stage gates on something external (data growth, vendor availability, another team), call that out.

Small honest caveats build trust. Hidden uncertainty destroys it when discovered later.

### Step 8 — Always add or update a revision-history block on every meaningful change

Every time the plan is created, revised, or restructured, prepend a `> 📝 Revision history` callout at the top of the document (or update the existing one). Format:

```
> 📝 **Revision history**
>
> - **<date> (<morning|afternoon|specific time if same-day>)** — <one-sentence summary of what changed and why it matters>
> - **<earlier date>** — <prior change>
```

Rules:

- Append new entries at the top of the list (newest first).
- One sentence per entry minimum, two if the *why* needs explaining.
- Same-day revisions get a time qualifier (`morning`, `afternoon`, or an explicit time) so the reader can disambiguate.
- The *why* matters as much as the *what* — "Restructured into two tracks because data starvation is the dominant failure mode" beats "Restructured into two tracks".
- Trivial fixes (typo, broken link) do not need an entry. Anything that changes the recommendation, numbers, structure, or ownership does.
- Preserve old entries verbatim — never edit historical entries. If a past claim turns out wrong, add a new entry correcting it.

This rule applies to **any meaningful update**, not just initial creation. Readers need to be able to tell what changed since they last read the doc, and trust that they're looking at the current view.

### Step 9 — Close with explicit asks

The "What We Need from Stakeholders" and "Questions for Decision-Makers" sections are not optional. They turn the doc from a description into a request. Without them, it's just a write-up.

Good asks have a name on them or a measurable size:

- "1 backend engineer, part-time, for 4–6 weeks"
- "Finance team time, approximately 1 hour per week"
- "Are we agreed that approval recall is the primary metric to improve?"
- "Is the 4–6 week timeline acceptable, or should we move faster (with higher risk)?"

## Formatting conventions

**Tables.** Use HTML-style tables (`<table header-row="true">...`) for any comparison with three or more dimensions. They render well in Notion and scan fast. Don't use tables for sequential narrative.

**Callouts.** Use `>` blockquote blocks for:
- Purpose statement at the top
- The single most important number ("The key number: ...")
- Risk callouts inline with the relevant section

Three or four callouts in a document is usually enough. More dilutes the signal.

**Headings.** H2 for major sections, H3 for sub-sections, H4 sparingly. Never go below H4.

**Numbers.** Always show count alongside percentage. Round percentages to one decimal max; drop decimals when they add nothing. Use ranges for forecasts.

## Evolution: maintain and improve this skill

This skill is a living document. After each use, update it.

### After every use, run this checklist

1. **Log what worked.** Did the structure land? Did the audience absorb it? Were sections skipped or particularly valued?
2. **Log what didn't.** Where did the reader get lost? Which sections felt redundant or confusing? Which numbers caused questions?
3. **Update the Evolution Log below** with a one-row entry per use.
4. **If a pattern is clear after 2–3 uses**, update the body of the skill itself (the steps, structure, or rules) — don't just keep adding rows to the log.
5. **Re-evaluate the trigger description** if the skill keeps firing on the wrong cases (or missing the right ones). Tighten or broaden the description in the frontmatter accordingly.

This step is non-optional. A skill that doesn't learn from its own use stagnates and gets ignored.

### Evolution Log

| Date | Plan written for | What worked | What didn't | Skill changes made |
|---|---|---|---|---|
| 2026-05-25 | Metric-improvement plan for a product/C-suite audience | Layered stages with consistent today/change/why micro-structure; "Important Caveat: small sample" section; tables for plan overview and success metrics; closing "what we need" + "questions" sections. | (Pending stakeholder feedback after circulation.) | Initial skill creation. |
| 2026-05-25 (afternoon) | Same plan, restructured to two-track framing after a data-quality root-cause finding. | Two-track table at the top let readers see at a glance which work targets which problem. Same-day revision-history qualifier (`morning` / `afternoon`) was useful — readers can tell which version of the numbers they're seeing. Six toggle-collapsed stage blocks kept the page scannable despite doubling stage count. | The original "ordered cheapest-first" framing read fine but obscured that there were two underlying problems. Single-stack stages were not the right abstraction. | Added Step 8 (revision-history block on every meaningful change) as an explicit rule. The morning revision had a revision block by reflex; the afternoon revision continued it; codifying so it's not reflex-dependent. |
| 2026-05-27 | Model-baseline recap — brief C-suite update | Plain-language rules (short sentences, common words, counts) and the honest-caveat habit fit a non-technical, possibly non-native audience. A 3-part recap (what we were after / tried / found) + one key-point callout + short "what this means" was the right shape. | The full 11-section macro-structure did not fit a request for a brief recap — omitted stages, timeline, success table, and asks entirely. | None — logged as a data point for the open question on shorter-audience formats. |

### Open questions to resolve through use

- Does the macro-structure of 11 sections feel right, or should some be merged for shorter audiences?
- Are there audience profiles (board, customers, internal-only) that need a different template?
- Should there be a "before / after" comparison view as a default visual?
- When does the numbered-stage layered structure stop fitting (e.g. continuous-improvement contexts, or where there's only one possible intervention)?

## Quick reference — copyable section skeleton

```markdown
> 🎯 **Purpose:** [one sentence on what this doc is doing]. Audience: [list].
>
> 📊 **Background:** [link to source doc]

---

## Summary

[2 short paragraphs stating the problem and proposed approach.]

> ⚠️ **The key number:** [one sentence with the headline metric].

---

## The Situation Today

**Where it works well**
- [bullet]

**Where it falls short**
- [bullet]

**The bottom line**
[one paragraph]

---

## The Plan in One Picture

<table header-row="true">
<tr><td>Stage</td><td>What</td><td>Effort</td><td>Expected impact</td></tr>
<tr><td>**1. Quick Wins**</td><td>...</td><td>1–2 weeks</td><td>...</td></tr>
<tr><td>**2. Best Practices**</td><td>...</td><td>2–4 weeks</td><td>...</td></tr>
<tr><td>**3. Experimental Upgrades**</td><td>...</td><td>4–6 weeks</td><td>...</td></tr>
<tr><td>**4. Long-term Bets**</td><td>...</td><td>Later</td><td>...</td></tr>
</table>

---

## Stage 1: Quick Wins ([N]–[M] weeks, low risk)

[Why these come first — 1 paragraph.]

### Three concrete changes

**1. [Change name]**
- **Today:** [1 sentence]
- **Change:** [1 sentence]
- **Why it helps:** [1–2 sentences]

[Repeat for changes 2 and 3.]

### Expected outcome of Stage 1
[Quantitative range. Note risks to manage.]

---

[Repeat structure for Stages 2, 3, 4.]

---

## Important Caveat: [headline of the main uncertainty]

[1–2 paragraphs being honest about sample size, dependencies, or other risk to the plan landing.]

---

## Recommended Timeline

<table header-row="true">
<tr><td>Week</td><td>Action</td><td>Outcome</td></tr>
[rows]
</table>

---

## What Success Looks Like

<table header-row="true">
<tr><td>Measurement</td><td>Today</td><td>After 4 weeks</td><td>After 3 months</td></tr>
[rows]
</table>

---

## What We Need from Stakeholders

- **Engineering time:** [specific ask]
- **Partner team time:** [specific ask]
- **Leadership input:** [cadence and forum]

---

## Questions for Decision-Makers

1. [Specific question requiring a yes/no or choice.]
2. [Specific question.]
3. [Specific question.]

---

## Related Documents

- [Link to source doc]
- [Link to related docs]
```
