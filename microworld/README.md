# microworld

Build a "micro-world" — an interactive, scrubbable, self-contained HTML
simulation that teaches how a system in a repo actually works, grounded in
its real code and recorded numbers (in the spirit of Papert's mathland and
Geoffrey Litt's ephemeral debugger UIs).

## Design

- **Grounded in truth.** Real file paths, real hyperparameters, real recorded
  numbers. Where the simulation must invent (a hypothetical branch,
  interpolated values), it says so explicitly in the page's briefing.
- **One central tension.** A micro-world teaches one decision or mechanism,
  not a whole system. If the question is a fork, the fork is playable.
- **Scrubbable tape, not a video.** The entire run is precomputed as a
  deterministic sequence of steps; UI state is derived by folding the event
  list up to the current index (`snapshot(idx)`), so any step renders
  instantly and scrubbing backwards is free.
- **Stage + instruments.** Two synchronized views — what's happening now
  (diff against parent, verdicts, current actor) and what's happened so far
  (progression chart, state grids, scoreboard).
- **Verified before showing anyone.** A `node:vm` harness walks every step of
  every branch through the real render pipeline, and light/dark screenshots
  with the pre-installed Chromium catch what the harness can't (label
  collisions, overflow, contrast).
- **Self-improving.** `LEARNINGS.md` accumulates pitfalls and design moves
  across builds; each build reads it first and appends to it after delivery.

## Usage

The skill triggers when the user is trying to *understand* a mechanism
rather than change it — "help me understand X", "why does X do Y", "walk me
through how the pipeline works", "visualize/simulate how X behaves" — even
if they never say "simulation" or "micro-world". It also handles extending
or fixing an existing page under `docs/microworlds/`.

See `skills/microworld/SKILL.md` for the full method,
`skills/microworld/references/engine.md` for the page anatomy, data model,
and verification harness pattern, and `skills/microworld/scripts/` for
worked examples of the harness (`check.example.mjs`) and screenshot pass
(`shot.example.mjs`).

## Requirements

Node.js (for the verification harness) and the pre-installed Chromium via
`playwright-core` (for the screenshot pass). Pairs with the `artifact-design`
and `dataviz` skills, which it loads before building and charting.
