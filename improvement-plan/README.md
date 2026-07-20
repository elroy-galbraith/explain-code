# improvement-plan

Draft a layered, plain-English improvement plan for non-technical or mixed
audiences — product, C-suite, leadership, FRA, customer success, non-native
English readers.

## Design

- **Cheapest-first layering.** Interventions are ordered into stages — Quick
  Wins, Best Practices, Experimental Upgrades, Long-term Bets — each gated on
  the previous stage being measured, so effort and risk climb gradually
  instead of all at once.
- **Fixed macro-structure.** Purpose, summary, situation today,
  plan-in-one-picture, staged detail, caveats, timeline, success criteria,
  stakeholder asks, decision questions, related documents — in that order,
  every time.
- **Plain language by rule.** Short sentences, common words, concrete counts
  alongside percentages, ranges instead of single-point forecasts, no idioms
  or unnecessary jargon.
- **Visibly honest about uncertainty.** Every plan carries a caveats section
  and a revision-history callout, so readers can tell what changed and trust
  that what they're looking at is current.
- **Closes with explicit asks.** Ends in named, sized requests to
  stakeholders and specific questions for decision-makers — turning the
  document from a write-up into a request.

## Usage

The skill triggers when you ask Claude to draft an improvement plan, write up
a roadmap for leadership, or translate a technical finding into a stakeholder
document. See `skills/improvement-plan/SKILL.md` for the full process, the
fixed section structure, the language rules, and a copyable section skeleton.

`SKILL.md` also includes an "Evolution" section: the skill is meant to be
updated with a log entry after each real use, so its structure keeps
improving instead of going stale.

## Requirements

None — this skill writes a markdown / Notion-ready document directly. There
are no scripts to run.
