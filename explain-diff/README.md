# explain-diff

Explain a code change, diff, branch, or PR as a single self-contained HTML page.

## Design

- **Test-first gate.** A 2–3 question diagnostic runs before the content. Pass it
  and the deep walkthrough stays collapsed — you go straight to the quiz. Miss one
  and it expands automatically. Lets an experienced reviewer skip content honestly.
- **Brief by default, deep on demand.** Each section shows a short summary always;
  the full walkthrough sits behind a toggle. One artifact for the 60-second review
  and the hour-long onboarding read.
- **Shuffled answers.** Options carry a `correct` flag; `render.py` shuffles their
  positions with a deterministic per-question seed, so the answer isn't pinned to
  one slot.
- **Python-rendered.** The model emits a compact JSON spec; `render.py` owns the
  CSS/JS/scaffolding. Cheaper and more consistent than hand-writing HTML each run.

## Usage

The skill triggers when you ask Claude to explain a diff/PR/branch. Under the hood
it writes a JSON spec and runs:

```bash
python3 skills/explain-diff/scripts/render.py spec.json -o out.html
```

See `skills/explain-diff/SKILL.md` for the full spec schema and
`skills/explain-diff/scripts/sample_spec.json` for a worked example.

## Requirements

Python 3 standard library only. No packages to install.
