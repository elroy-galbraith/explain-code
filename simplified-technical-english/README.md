# simplified-technical-english

Rewrite technical prose into **Simplified Technical English** (ASD-STE100) so it
survives the reader it will actually meet: someone tired, rushed, or reading in
their second language.

This is a constraint applied *to* prose, not a way of producing a document. You
run it over text that already exists — a runbook, a design doc, a release note, a
PR description, or the output of another skill in this marketplace.

## Two profiles, because the standard was not written for software

ASD-STE100 comes from aerospace maintenance manuals and assumes procedural prose
("Remove the bolt. Install the new bolt."). Most software writing is descriptive,
and it is full of terms that no approved-word list contains. Forcing full
conformance onto it produces documents that are compliant and worse.

- **`lite` (the default)** keeps the rules that carry the readability gain and
  drops the ones that fight technical writing. Domain terms stay as Technical
  Names. Descriptive sentences get 25 words, instructions get 20.
- **`strict`** is the conformance exercise: 20 words everywhere, active voice
  only, no `-ing` verbs, approved dictionary. Use it when a contract or a
  regulated deliverable asks for it.

## What it actually enforces

The five rules that do most of the work:

1. **One word, one meaning.** Pick a term and never vary it. "The request… the
   call… the invocation…" is good English-essay style and a comprehension bug here.
2. **Break noun clusters.** `user session token refresh handler` →
   `the handler that refreshes session tokens`. Software prose generates these
   constantly.
3. **One idea per sentence**, under the word cap.
4. **Active voice, actor named.** "The token is validated" hides the thing a
   debugger needs to know.
5. **No idioms or phrasal verbs** where a simple verb exists — "spin up" →
   "start", "under the hood" → "internally".

Full list, grouped by the specification's own chapters and tagged by profile:
[`references/rules.md`](skills/simplified-technical-english/references/rules.md).

## What it never touches

Code, identifiers, file paths, commands, and log output — inside backticks,
fenced blocks, or `<pre>`/`<code>`, every character is left alone. A variable
named `isRunningBackfill` is not a gerund violation. Technical Names, quotations,
and mandated legal or safety wording are also preserved. If a rule would make a
technical claim vaguer, the rule loses and the skill says which one it broke.

## The checker

```bash
python3 skills/simplified-technical-english/scripts/check_ste.py draft.md
python3 skills/simplified-technical-english/scripts/check_ste.py draft.md --profile strict
cat draft.md | python3 skills/simplified-technical-english/scripts/check_ste.py -
```

It flags sentence-length overruns, passive constructions, participle chains, noun
clusters, banned phrasal verbs and idioms, trailing conditions, over-long
paragraphs, and terminology drift. Errors exit non-zero; warnings are advisory.
`--format json` for machine-readable output. Python 3 standard library only.

The word lists live in
[`references/engineering-vocabulary.md`](skills/simplified-technical-english/references/engineering-vocabulary.md)
and the checker parses that file directly, so the documentation a human reads and
the list the tool enforces cannot drift apart. Add a row to the table and the
checker picks it up.

A clean run is a floor, not a pass. The checker counts things; it cannot tell you
whether the rewrite kept the meaning.

## Ordering with the other plugins

**Run `humanizer` first, then this.** The two pull in opposite directions:
humanizer removes AI tells to produce natural human voice, and STE imposes a
deliberately uniform, repetitive register that humanizer reads as machine-written.
Run in the wrong order, humanizer reintroduces synonym variation and breaks the
most valuable rule in the set.

`explain-code` applies it to the always-visible section summaries and the
gate/quiz prompts, leaving the deep walkthrough bodies as flowing prose.
`improvement-plan` offers it as an alternative final pass to humanizer for
audiences with non-native English readers.

## On the source specification

ASD holds the copyright to ASD-STE100. The specification is free to download from
[asd-ste100.org](https://www.asd-ste100.org/) but **may not be redistributed**, so
the approved-word dictionary is not bundled here. `references/rules.md` paraphrases
the rule categories in this skill's own words with software examples, and
`references/engineering-vocabulary.md` is an original substitution table written
for this marketplace. Dictionary-exact conformance work needs the user's own copy
of the specification, and the skill says so rather than guessing.

Issue 9 (January 2025) is 53 writing rules and roughly 900 approved words,
maintained by the Simplified Technical English Maintenance Group at ASD, Brussels.
