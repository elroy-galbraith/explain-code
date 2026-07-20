---
name: explain-diff
description: Use when the user asks for an explanation of a code change, diff, branch, or PR. Produces a single self-contained HTML page with an adaptive "test-first" gate, brief-by-default sections that expand on demand, and a shuffled comprehension quiz. Optimized for fast PR review while still supporting deep onboarding.
---

# explain-diff

Explain a code change as one self-contained HTML file. The reader opens it in a
browser — no server, no account, nothing to install. If they want to keep it for
onboarding they save the `.html`, print it to PDF, or drop it into a wiki/Notion
page later.

You do **not** hand-write the HTML. You gather the substance, emit a compact
**JSON spec**, and run `scripts/render.py`, which owns all the CSS, quiz
JavaScript, answer-shuffling, and page scaffolding. This keeps output consistent
and saves your tokens for the parts that actually change per diff.

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

1. **Understand the change first.** Read the diff / PR / branch and whatever
   surrounding code you need. Gather the real substance before writing anything.
   Do not read `render.py` for content guidance — it is pure plumbing.
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
  "title": "Human-readable title of the change",
  "subtitle": "PR #482 · service-name",
  "slug": "YYYY-MM-DD-short-name",
  "gate": [ /* 2-3 diagnostic questions */ ],
  "sections": [ /* the walkthrough */ ],
  "quiz": [ /* 5 questions — the post-test */ ]
}
```

### `gate` — the test-first check (2-3 questions)

The fast path. Ask the 2-3 questions that best separate "already understands this
change" from "needs the walkthrough." Target the load-bearing ideas, not trivia.
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

Aim for 3-4 sections. Good defaults, in order: **Background** (the existing system
a newcomer needs), **Intuition** (the core idea via a concrete example or
diagram), **The code** (a high-level, logically grouped walkthrough). Add or drop
sections to fit the change.

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
  snippets, not the whole diff.

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
