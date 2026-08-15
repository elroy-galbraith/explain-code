# The rules, grouped — with software examples

This file paraphrases the *categories* of writing rule in ASD-STE100, in this
skill's own words, with examples drawn from software documentation. It is not a
reproduction of the specification and it is not a substitute for it. ASD holds
the copyright; the specification is free to download from
[asd-ste100.org](https://www.asd-ste100.org/) and the approved-word dictionary is
only available there.

Issue 9 (January 2025) organises 53 writing rules into nine chapters. The grouping
below follows those chapters so you can map back to the real thing.

Each rule is tagged:

- **[lite]** — applies in both profiles. These carry most of the readability gain.
- **[strict]** — applies only in the strict profile. Usually because enforcing it
  on descriptive software prose costs more clarity than it buys.

---

## 1. Words

**Use one approved word for each meaning. [lite]**
Pick a term and keep it. The reader must never have to decide whether a new word
means a new thing.

> ✗ The gateway validates the request. If the call is malformed, the invocation is rejected.
> ✓ The gateway validates the request. If the request is malformed, the gateway rejects it.

**Use each word in one part of speech only. [strict]**
English lets a word be noun and verb; STE does not. In software prose this rule
is expensive — *cache*, *hash*, *log*, *mock*, *commit*, and *deploy* are all
routinely both — so `lite` allows the dual use where the sentence is unambiguous.
When you do keep both, keep them visibly distinct: "write the entry to the log",
not "log the log".

**Keep Technical Names. [lite]**
A Technical Name is a noun with no plain-word equivalent that does not lose
precision: *mutex*, *idempotency*, *tokenizer*, *quorum*, *backpressure*, a
product name, a protocol name. Keep it, define it once at first use, then use it
unchanged. Do **not** downgrade a precise term to a vague one to satisfy a word
list.

**Keep approved Technical Verbs, but only for the manufacturing sense. [lite]**
Some verbs are permitted only in a specific technical meaning. In software prose
the practical form of this rule is: use the concrete verb the system actually
performs (*write*, *read*, *send*, *retry*, *delete*), not an abstract stand-in
(*handle*, *process*, *manage*, *leverage*).

**Do not use one word to stand for a longer phrase you have not defined. [lite]**
Expand an abbreviation at first use, then use the abbreviation consistently. Never
introduce a project-local shorthand without defining it.

**Prefer the short, common word. [lite]**
See `engineering-vocabulary.md` for the substitution table — *use* not *utilise*,
*start* not *initiate*, *show* not *demonstrate*, *change* not *modify*.

---

## 2. Noun phrases

**Do not put more than three nouns in a row. [lite]**
This is the highest-value rule for software writing, and it is broken constantly.

> ✗ user session token refresh handler configuration
> ✓ the configuration for the handler that refreshes session tokens

**Do not drop articles. [lite]**
Telegraphic style ("Set flag, restart worker") is harder to translate and easy to
misread. Write "Set the flag, then restart the worker."

**Hyphenate compound modifiers so the grouping is unambiguous. [lite]**
"a read only cache" versus "a read-only cache" — the hyphen carries meaning.

---

## 3. Verbs

**Use the active voice, and name the actor. [lite]**
Passive hides who acts, which is exactly the information a reader needs when
debugging.

> ✗ The token is validated before the request is forwarded.
> ✓ The gateway validates the token, then forwards the request.

Passive survives in `lite` only when the actor is genuinely unknown or irrelevant
("the row was deleted at some point before the backfill ran"). It is disallowed
in `strict`.

**Use the simple tenses. [lite]**
Present for how things behave, simple past for what happened, simple future for
what will change. Avoid stacked conditionals ("would have been being retried").

**Do not use `-ing` forms as verbs. [strict, partially lite]**
STE bans gerunds and participles because they blur what is acting on what.
Enforcing that fully makes software prose stilted, so `lite` flags only
**participle chains** — two or more `-ing` clauses in one sentence, where the
ambiguity actually bites:

> ✗ Running the migration while holding the lock, blocking writers, causes timeouts.
> ✓ The migration holds the lock. While the lock is held, writers block and time out.

An `-ing` word inside an identifier or a Technical Name (`RunningTotal`,
*rolling upgrade*) is never a violation.

**Write instructions as commands. [lite]**
"Set the retry limit to 3", not "The retry limit should be set to 3". In
instructions, *must* and *do not* are the only modal forms — *should*, *may*, and
*could* leave the reader guessing whether the step is optional.

---

## 4. Sentences

**Keep procedural sentences to 20 words and descriptive sentences to 25. [lite]**
`strict` applies 20 everywhere. Split on the conjunction; do not compress by
deleting articles or shortening words.

**One instruction per sentence. [lite]**
Two commands joined by "and" become two sentences. The reader is following along
with their hands busy.

**Put the condition before the instruction. [lite]**

> ✗ Restart the worker if the queue depth exceeds 10,000.
> ✓ If the queue depth is more than 10,000, restart the worker.

The reader should know whether the sentence applies to them before they read what
to do.

**Keep related words together. [lite]**
Do not separate the subject from its verb with a long qualifier.

---

## 5. Procedures

**Keep a procedural paragraph to six sentences. [lite]**

**Give each step its own number, and one action per step. [lite]**

**State the purpose before the steps, not after. [lite]**

---

## 6. Descriptive writing

**Keep a descriptive paragraph to one topic. [lite]**
Lead with the topic sentence. The reader who stops after one sentence should
still have the point.

**Vary paragraph length, but keep them short. [lite]**

**Do not leave out words to save space. [lite]**
Compression that removes *that*, *the*, or a relative pronoun makes a sentence
harder, not shorter, to read.

---

## 7. Safety instructions

**Put the warning before the step it applies to. [lite]**
A caution after the instruction arrives too late to prevent anything. In software
docs this covers destructive commands, irreversible migrations, and anything that
touches production data.

**Start a warning with the command, then the consequence. [lite]**

> ✓ Do not run this against production. The migration drops the table and cannot be reversed.

---

## 8. Punctuation and word counts

**Use punctuation to clarify, not to join more clauses. [lite]**
A semicolon that lets a 40-word sentence stay one sentence is a rule violation
wearing a disguise.

**Avoid the slash (`/`) as a stand-in for "and" or "or". [lite]**
"read/write access" is ambiguous: both, or either?

**Avoid parenthetical asides in instructions. [lite]**
They break the reading order. In descriptive prose a short parenthesis is fine.

---

## 9. Writing practices

**Define every abbreviation once, at first use. [lite]**

**Do not use idioms, slang, or metaphors. [lite]**
"low-hanging fruit", "move the needle", "out of the box", "under the hood" — all
opaque to a non-native reader and all common in engineering writing.

**Do not use humour or rhetorical questions in instructions. [lite]**

**Be consistent in formatting, capitalisation, and terminology across the whole
document. [lite]**

---

## When to break a rule

Keep the meaning. If the only way to satisfy a rule is to make a technical claim
vaguer, weaker, or wrong, break the rule and say which one you broke and why. A
document that conforms and misleads has failed at the thing conformance was for.
