---
name: explain-code
description: Use when the user asks for an explanation of code — a change, diff, branch, or PR, but also a whole feature, a module, a subsystem, or an unfamiliar codebase. Triggers on phrases like "explain this PR", "explain how this feature works", "walk a new hire through this module", "help me understand this codebase". Produces a single self-contained HTML page with an adaptive "test-first" gate, brief-by-default sections that expand on demand, and a shuffled comprehension quiz. Fast for PR review, deep enough for onboarding.
---

# explain-code

Explain a piece of code as one self-contained HTML file. "A piece of code" can be a
single change (diff/branch/PR) or something larger — a whole feature, a module, a
subsystem, or an unfamiliar codebase you're onboarding someone onto. The reader
opens it in a browser — no server, no account, nothing to install. If they want to
keep it they save the `.html`, print it to PDF, or drop it into a wiki/Notion page
later.

You do **not** hand-write the HTML. You gather the substance, emit a compact
**JSON spec**, and run `scripts/render.py`, which owns all the CSS, quiz
JavaScript, answer-shuffling, and page scaffolding. This keeps output consistent
and saves your tokens for the parts that actually change from one explanation to
the next.

## When to use this skill

What the change **touches** is the strongest signal — stronger than how big it
is. Use this skill when:

- The change touches a **critical path**: auth, payments/billing,
  permissions/access control, data migrations, or pricing/business rules —
  regardless of how small the diff looks. A one-line permission check is
  exactly the kind of change worth explaining.
- The change is **large and structural, spanning multiple modules**. Treat size
  as a secondary signal only — never trigger on size alone, and don't count
  lines from lockfiles or generated code, which are noise.
- Someone **explicitly asks** for a walkthrough: onboarding a new hire,
  explaining a subsystem, preparing sign-off on a feature.

Skip it — generating here is a speedbump, not a value-add — for mechanical
diffs: formatting-only changes, renames, lockfile/dependency bumps, generated
code, comment-only changes, test-fixture-only changes, and otherwise-trivial
changes to non-critical paths.

Two things make this loose framing safe rather than sloppy:

- **The test-first gate is the safety valve.** Even when you do generate, an
  expert reviewer clears the gate in about 30 seconds and never opens the deep
  content. A false trigger costs 30 seconds; a missed trigger risks someone
  shipping critical code they didn't understand. That asymmetry is why you
  should err toward generating on critical paths rather than holding back.
- **Audience is a depth knob, not a trigger gate.** Whether the reader is a
  junior engineer, a senior engineer, or a non-technical stakeholder changes
  how much they lean on `body` versus `summary` — it does not change whether
  you generate. Don't restrict who gets an explanation by seniority; let the
  gate self-select instead.

This skill defines *what* to explain. *When* to trigger it automatically — the
hard thresholds an LLM shouldn't be asked to compute, like line counts and path
globs — is a separate policy decision; see `explain-code/policy/` for the CI
policy that encodes it.

## Design goals (why the format is shaped this way)

1. **Fast by default, deep on demand.** A PR reviewer should get the gist in
   under a minute; a new hire should be able to go as deep as they want. So every
   section leads with a 2-3 sentence summary that is always visible, and the full
   walkthrough lives behind a toggle. Don't cut the depth — hide it.
2. **Test-first, like TDD.** Red → green → refactor becomes *pre-check → read →
   confirm*. A short diagnostic **gate** runs first. If the reader already knows
   the material, they pass and skip straight to the quiz; the deep content stays
   collapsed. If they miss anything, the walkthrough expands automatically. This
   is what lets an experienced reviewer skip the content honestly rather than
   guessing they don't need it.
3. **No answer-position bias.** You just mark which option is `correct`;
   `render.py` shuffles positions deterministically so the answer isn't always in
   the same slot. Never try to randomize positions yourself.

## Workflow

1. **Understand the code first.** Read whatever you're explaining — the diff / PR /
   branch, or the feature / module / subsystem / codebase — plus enough surrounding
   code to get the real substance, before writing anything. Do not read
   `render.py` for content guidance — it is pure plumbing.
2. **Write the JSON spec** (schema below). This is where all your effort goes.
3. **Render it.** `render.py` lives in this skill's own `scripts/` directory. Call
   it by its full path (this skill's directory is given to you when the skill
   loads) so it works regardless of the current working directory:
   ```bash
   python3 "<this-skill-dir>/scripts/render.py" spec.json -o <slug>.html
   ```
   `render.py` validates the spec and fails loudly if a question lacks exactly one
   correct option, so fix and re-run if it complains. It needs only the Python 3
   standard library — no packages to install.
4. **Deliver the `.html` file** to the user (in Cowork, use SendUserFile). Mention
   they can open it in any browser, and save or import it if they want to keep it.

## JSON spec schema

```json
{
  "title": "Human-readable title of what's being explained",
  "subtitle": "PR #482 · service-name   (or: 'Billing feature · payments-service')",
  "slug": "YYYY-MM-DD-short-name",
  "gate": [ /* 2-3 diagnostic questions */ ],
  "sections": [ /* the walkthrough */ ],
  "quiz": [ /* 5 questions — the post-test */ ]
}
```

### `gate` — the test-first check (2-3 questions)

The fast path. Ask the 2-3 questions that best separate "already understands this
code" from "needs the walkthrough." Target the load-bearing ideas, not trivia.
Same question shape as the quiz:

```json
{
  "prompt": "One clear question.",
  "options": [
    {"text": "The correct answer", "correct": true},
    {"text": "A plausible distractor", "correct": false},
    {"text": "Another distractor", "correct": false}
  ],
  "explanation": "One sentence on why the right answer is right (shown after grading)."
}
```

Rules: exactly one option has `correct: true`; give 2-4 options; distractors must
be plausible, not filler. Order doesn't matter — it gets shuffled.

### `sections` — brief by default, deep on demand

Aim for 3-4 sections (a little more is fine for a whole feature or codebase). Good
defaults, in order: **Background** (the existing system a newcomer needs),
**Intuition** (the core idea via a concrete example or diagram), **The code** (a
high-level, logically grouped walkthrough). Add or drop sections to fit what you're
explaining — a single diff may need three; a subsystem may warrant one per
component.

```json
{
  "id": "background",
  "heading": "Background",
  "summary": "2-3 sentences a hurried reviewer can read and move on. What changed and why it matters. ALWAYS VISIBLE.",
  "body": "<p>The deep, beginner-friendly walkthrough as raw HTML. Hidden behind a toggle; the reader expands it only if they want it.</p>"
}
```

The `summary` carries the brevity; the `body` carries the depth. Write both well —
the summary is not a teaser, it's a complete quick answer.

`body` is raw HTML, injected verbatim. Use it freely:
- Prose in `<p>`. Write in the clear, flowing style of Martin Kleppmann.
- Diagrams as **HTML/CSS**, not ASCII art — simple boxes, arrows, UI mockups, data
  flows with example data. (Inside a `<pre>` a small ASCII sketch is fine when it
  genuinely helps.)
- Code in `<pre>` (it wraps and scrolls automatically). Show representative
  snippets, not the whole diff or file.

### `quiz` — the confirmation (5 questions)

Five medium-difficulty questions that confirm the ideas stuck — this is the
"green" step after reading. Same question shape as `gate`. Positions are shuffled
at render time. Don't reuse the gate questions verbatim; probe the same core ideas
from a different angle.

## Notes

- Output is a single file with everything inlined — safe to email, attach, or
  archive.
- The gate drives disclosure: pass → deep content stays collapsed (reader can
  still expand any part); miss one → it opens automatically. If there is no
  `gate`, the walkthrough is shown expanded by default.
- Keep summaries genuinely short and the deep bodies genuinely thorough. The whole
  value of the format is that one artifact serves both the 60-second review and
  the hour-long onboarding read.
