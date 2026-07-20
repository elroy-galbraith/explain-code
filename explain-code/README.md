# explain-code

Explain code — a change (diff/branch/PR), a whole feature, a module, or an
unfamiliar codebase — as a single self-contained HTML page.

## Design

- **Test-first gate.** A 2–3 question diagnostic runs before the content. Pass it
  and the deep walkthrough stays collapsed — you go straight to the quiz. Miss one
  and it expands automatically. Lets someone who already knows the code skip it
  honestly.
- **Brief by default, deep on demand.** Each section shows a short summary always;
  the full walkthrough sits behind a toggle. One artifact for the 60-second review
  and the hour-long onboarding read.
- **Shuffled answers.** Options carry a `correct` flag; `render.py` shuffles their
  positions with a deterministic per-question seed, so the answer isn't pinned to
  one slot.
- **Python-rendered.** The model emits a compact JSON spec; `render.py` owns the
  CSS/JS/scaffolding. Cheaper and more consistent than hand-writing HTML each run.

## Usage

The skill triggers when you ask Claude to explain code — a diff, PR, feature,
module, or codebase. Under the hood it writes a JSON spec and runs:

```bash
python3 skills/explain-code/scripts/render.py spec.json -o out.html
```

See `skills/explain-code/SKILL.md` for the full spec schema and
`skills/explain-code/scripts/sample_spec.json` for a worked example.
`SKILL.md` also has a "When to use this skill" section covering what should
and shouldn't trigger an explanation.

## Requirements

Python 3 standard library only. No packages to install.

## CI policy (when to auto-trigger)

The skill knows *what* to explain; it doesn't hardcode *when* to run
automatically. That's a separate policy layer in `policy/`:
`policy/explain-code-policy.yml` defines critical paths, size thresholds, and
ignore rules, `policy/evaluate_policy.py` evaluates a diff against it, and
`policy/README.md` explains the one-sentence rule behind it. See
`.github/workflows/explain-code-policy.yml` at the repo root for how it's
wired into pull requests.
