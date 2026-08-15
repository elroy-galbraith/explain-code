---
name: simplified-technical-english
description: Rewrite technical prose into Simplified Technical English (ASD-STE100) so it reads clearly for non-native English speakers, translators, and readers skimming under time pressure. Use when the user asks for "Simplified Technical English", "STE", "ASD-STE100", "controlled language", "plain technical English", "make this readable for non-native speakers", "simplify this documentation", or asks to check prose against STE rules. Also invoked as a final language pass by other skills (explain-code, improvement-plan). Applies to prose only — never to code, identifiers, or command output.
---

# Simplified Technical English (ASD-STE100)

Rewrite technical prose so a reader who is tired, rushed, or reading in their
second language gets the meaning on the first pass. This is a **constraint applied
to prose**, not a way of producing a document — you run it over text that already
exists, whether you just wrote it or the user pasted it in.

The source standard is **ASD-STE100**, maintained by the Simplified Technical
English Maintenance Group at ASD (Brussels). Issue 9 (January 2025) is 53 writing
rules plus a dictionary of roughly 900 approved words. It was designed for
aerospace maintenance manuals, and that origin matters: it assumes procedural
prose ("Remove the bolt. Install the new bolt."). Most of what you will be asked
to rewrite is *descriptive* prose about software. The two profiles below exist to
handle that gap honestly.

> **On the source text.** ASD holds the copyright. The specification is free to
> download from [asd-ste100.org](https://www.asd-ste100.org/) but may not be
> redistributed, so the approved-word dictionary is **not** bundled here.
> `references/rules.md` paraphrases the rule *categories* in this skill's own
> words, and `references/engineering-vocabulary.md` is an original substitution
> table written for software prose. For dictionary-exact conformance work, the
> user needs their own copy of the specification — say so rather than guessing at
> approved words.

## Choose a profile first

**`lite` is the default.** Use `strict` only when the user names a conformance
requirement (a customer contract, a regulated deliverable, a translation memory)
or explicitly asks for full ASD-STE100.

| | `lite` (default) | `strict` |
|---|---|---|
| Sentence length | ≤ 25 words descriptive, ≤ 20 procedural | ≤ 20 words everywhere |
| Vocabulary | Plain-word substitutions; domain terms kept as Technical Names | Approved dictionary only; every exception justified |
| Voice | Active strongly preferred; passive allowed when the actor is genuinely unknown | Active only; imperative for every instruction |
| `-ing` forms | Participial *chains* flagged; gerunds allowed where natural | Rewritten unless part of a Technical Name |
| Needs the spec? | No | Yes — the user must supply the dictionary |

`lite` keeps the rules that carry almost all the readability benefit and drops
the ones that fight technical writing. `strict` is a conformance exercise and
will read stiffly; that is the intended trade, not a defect.

## The rules that matter most

Full breakdown in `references/rules.md`. These five do the heavy lifting, and
three of them are the ones engineers habitually break:

1. **One word, one meaning — and one word per meaning.** Pick a term for a thing
   and never vary it. Elegant variation ("the request… the call… the invocation…")
   is a style virtue in English essays and a comprehension bug here. The reader
   cannot tell whether you renamed the concept or introduced a new one.
2. **Break noun clusters.** More than three nouns in a row stops parsing:
   "user session token refresh handler" → "the handler that refreshes session
   tokens". Software prose generates these constantly.
3. **One idea per sentence, under the word cap.** Split on the conjunction rather
   than shortening words.
4. **Active voice, and name the actor.** "The token is validated" hides who
   validates it; "the gateway validates the token" is the same length and answers
   the question.
5. **No idioms or phrasal verbs where a simple verb exists.** "spin up" → "start",
   "fall back to" → "use instead", "roll out" → "release". These are the single
   biggest source of failure for non-native readers, and they survive spell-check.

## What this skill never touches

Rewriting these breaks the document instead of clarifying it:

- **Code, identifiers, file paths, commands, log output, error strings.** Inside
  `<code>`, `<pre>`, backticks, or fenced blocks, leave every character alone.
  A variable named `isRunningBackfill` is not a gerund violation.
- **Technical Names.** Domain terms with no plain equivalent — *mutex*, *idempotent*,
  *migration*, *tokenizer*, *quorum* — are kept. STE explicitly allows Technical
  Names; the discipline is to *define each one once, at first use*, then use it
  unchanged. Do not paraphrase a precise term into a vague one to satisfy a word
  list; that trades clarity for compliance.
- **Quotations, names, and cited text.** Rewriting a quote misrepresents its author.
- **Legal, licence, or safety text** with mandated wording.

If applying a rule would change the technical meaning, keep the meaning and note
the exception. Comprehension is the goal; the rules are the means.

## Process

1. **Establish scope and profile.** What text, and `lite` or `strict`? If the user
   has not said, assume `lite` and say so in one line rather than asking.
2. **Read the whole text before changing a sentence.** Terminology consistency
   (rule 1) can only be fixed with the whole document in view — you have to see
   both "call" and "invocation" to know one has to go.
3. **Build the term list.** Note every domain term you are keeping as a Technical
   Name and the one synonym you picked for each recurring concept. For anything
   over a few paragraphs, put this list in the reply so the user can overrule a
   choice.
4. **Rewrite, protecting the untouchable spans.** Split long sentences, break noun
   clusters, convert passive to active, substitute plain words
   (`references/engineering-vocabulary.md`).
5. **Check mechanically.** Run the checker over the result:
   ```bash
   python3 "<this-skill-dir>/scripts/check_ste.py" draft.md --profile lite
   ```
   It flags sentence-length overruns, passive constructions, participle chains,
   noun clusters, banned phrasal verbs and idioms, and terminology drift. It
   skips code spans automatically. Exit code is non-zero when errors remain;
   warnings are advisory. It reads markdown, HTML, or plain text and needs only
   the Python 3 standard library.
6. **Fix what the checker found, then re-run.** The checker is a heuristic, not a
   grader — it catches mechanical tells and cannot judge whether the meaning
   survived. Read the result once yourself before delivering.
7. **Report what changed.** Give the user the rewritten text, the term list, and
   any rule you deliberately broke with the reason. Do not report a silent
   rewrite of a technical claim.

## Working with the other skills in this marketplace

**Ordering with `humanizer`: STE goes last.** The two skills pull in opposite
directions and the order decides which one wins. Humanizer removes AI tells to
produce natural human voice; STE imposes a deliberately uniform, repetitive
register that humanizer reads as machine-written and will try to undo. So:
humanizer first (to strip padding, promotional language, and hedging), then STE
(to impose the constraints). Never run humanizer after STE — it will reintroduce
synonym variation, which breaks the most valuable rule in the set.

**With `explain-code`:** apply STE to the always-visible `summary` fields and the
`gate`/`quiz` prompts, not to section `body` HTML. The bodies are meant to be
flowing explanatory prose; the summaries and questions are read fast and are where
the constraint pays. Watch one interaction: `render.py` rejects a quiz whose
correct answer is the wordiest option, so when you shorten an option, shorten the
distractors to match rather than leaving the correct answer conspicuously terse.

**With `improvement-plan`:** that skill's Step 6 language rules are a subset of
STE-lite. Running this skill after it is a strengthening pass, not a conflict.
Keep the things STE does not supply: counts alongside percentages, forecast
ranges, and inline definitions.

## Reference files

- `references/rules.md` — the rule categories, grouped, in this skill's own words,
  with a software example for each and a note on which apply in `lite`.
- `references/engineering-vocabulary.md` — substitution table for software prose:
  wordy verbs, phrasal verbs, idioms, and the noun-cluster patterns that recur in
  engineering documentation.
- `scripts/check_ste.py` — the mechanical checker (`--help` for options).
