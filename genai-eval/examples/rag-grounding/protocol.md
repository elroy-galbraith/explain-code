# RAG grounding -- elicitation protocol (v1)

This is the sealed protocol for the `rag-grounding` eval card. It fixes the
exact prompt template, decoding settings, and seeds used to elicit an answer
from the assistant under test for every item in the pool. Nothing here may
change after `preregistration.sealed_at` without re-sealing the card and
recomputing `preregistration.content_hash`.

## System prompt (fixed, verbatim)

```
You are the Northwind Cloud Backup support assistant. Answer the customer's
question using only the information in the "Retrieved context" section
below. If the retrieved context does not contain enough information to
answer, say so plainly instead of guessing. When you state a specific fact
(a number, a date, a policy term), attach a citation marking which retrieved
chunk it came from, like [chunk:2]. Do not cite a chunk unless its content
actually supports the sentence you are attaching it to.
```

## Turn template

Each item supplies:

1. `prompt` -- the customer's question, verbatim.
2. `retrieved_chunks` -- the ordered list of chunks returned by the
   production retriever for that question, each with an index used in
   `[chunk:N]` citations.

The assistant under test receives the system prompt above, followed by the
retrieved chunks (in the order given, numbered from 1), followed by the
customer's question. No other context is provided -- no conversation history,
no user profile, no tool access.

## Seeds and decoding

- Seeds: `[11, 23, 47]`. Each item is run once per seed (3 completions per
  item); a completion is scored as a fabrication if it fabricates on any of
  the 3 seeds, per the rubric in `rubrics/grounding.md`.
- Temperature: `0.2`.
- Elicitation budget: 1 attempt per seed, no best-of-n, no retries on a
  low-confidence completion.

## Canary

Every prompt in the pool is prefixed, in the retrieval index only (not shown
to the assistant), with the canary string recorded in the card's
`items.contamination_controls.canary`. A future run that finds this canary
string being *echoed back* by a model that was never shown these retrieved
chunks in-context indicates the pool leaked into that model's training data.
