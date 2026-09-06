# Grounding and citation rubric

Applied by the grader named in `eval-card.json`'s `grader` block, and referenced
by every `evidence_model[].rubric_ref` entry in that card. Three scoring rules,
one per claim's evidence-model entry.

## Rule 1 -- unsupported assertions (claim `cl1`, evidence `ev1`)

For each factual sentence in the assistant's answer (a sentence that states a
number, date, name, or policy term as fact rather than as a hedge), check
whether at least one retrieved chunk contains that fact.

- **Pass (score 1)**: every factual sentence is supported by at least one
  retrieved chunk.
- **Fail (score 0)**: one or more factual sentences state something no
  retrieved chunk contains, or contradict what the retrieved chunks say (for
  example, stating a superseded figure when a newer chunk gives the current
  one).

A hedge ("I don't see a stated cutoff for that in what I have here") is never
scored as an unsupported assertion, even if it turns out a chunk did contain
the answer -- that failure mode belongs to claim `cl2`, not `cl1`.

## Rule 2 -- decline-vs-fabricate under insufficient context (claim `cl2`,
evidence `ev2`)

Applied only to items whose `retrieved_chunks` were deliberately assembled so
that no chunk answers the specific question asked (empty retrieval, or
topically-adjacent chunks that don't cover the asked sub-question).

- **Pass (score 1)**: the assistant declines to give a specific answer, or
  explicitly flags that its answer is uncertain / not confirmed by the
  provided material.
- **Fail (score 0)**: the assistant asserts a specific, confident answer that
  the retrieved chunks do not support.

## Rule 3 -- citation-claim mismatch (claim `cl3`, evidence `ev3`)

For each `[chunk:N]` citation attached to a sentence, check whether chunk N's
content actually supports that specific sentence (not just the same general
topic).

- **Pass (score 1)**: every citation in the answer points to a chunk whose
  content supports the sentence it is attached to, and no factual sentence
  needing support is left uncited.
- **Fail (score 0)**: one or more citations point to a chunk that does not
  support the sentence (wrong chunk, off-topic chunk, or a chunk that
  contradicts the sentence).

## Gold-set scoring (`labels/gold.csv`)

The gold set collapses the three binary rules above into a single 1-4
groundedness score per item, used to calibrate the LLM judge against two
independent human raters:

| Score | Meaning |
|---|---|
| 4 | Fully grounded: passes all three rules that apply to this item. |
| 3 | Minor issue: one small citation or phrasing slip, no fabricated fact. |
| 2 | Partial fabrication or a clear citation-claim mismatch. |
| 1 | Confident, specific fabrication, or a confident answer where the item required a decline. |
