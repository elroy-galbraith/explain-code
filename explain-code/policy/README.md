# explain-code CI policy

**The one-sentence rule:** auto-generate on critical-path changes; one-click
opt-in otherwise; skip mechanical diffs.

This directory is the *WHEN* half of explain-code. The skill itself
(`skills/explain-code/SKILL.md`) is the *WHAT* half — it knows how to turn a
diff, feature, or codebase into a good explanation, but it deliberately has
no numeric thresholds baked into it. An LLM can't reliably decide "is 340
lines a lot?", and it doesn't know whether the reader is a reviewer who'll
clear the gate in 30 seconds or a new hire who needs the deep walkthrough.
Those are policy decisions, so they live here instead, in a file a script can
evaluate deterministically.

## Why this order of priority

1. **What the change touches is the strongest signal.** A one-line change to
   a permission check is worth explaining; a thousand-line reformat isn't.
   So `critical_paths` is checked first, and a single match forces
   generation *regardless of diff size*.
2. **Size is a weak, noisy proxy — demoted on purpose.** It only triggers
   generation together with `require_multi_module: true`, i.e. "large AND
   spans multiple modules." Size alone never triggers anything. Lines from
   `ignore_paths` (lockfiles, generated code, snapshots) are excluded before
   either number is computed, because those line counts are meaningless.
3. **Risk is asymmetric, so the policy leans toward generating.** A false
   trigger costs a reviewer about 30 seconds — the skill's test-first gate
   lets anyone who already understands the change ace it and skip straight
   to the quiz. A missed trigger risks someone shipping critical code they
   didn't understand. That asymmetry is why `critical_paths` matches
   override everything else, and why the size thresholds below are meant to
   be tuned conservatively (catch real structural changes, not just "a big
   diff").

Note what's *not* here: reader seniority. Audience (junior vs. senior,
technical vs. non-technical stakeholder) is handled inside the skill as a
depth knob — how much the explanation leans on the deep `body` vs. the
`summary` — not as a trigger condition. Gating generation on who's reading
would duplicate what the gate already does for free.

## The fields

```yaml
critical_paths:   # strongest signal — a match forces generation, any size
  - "auth/**"
  - ...

size:              # weak signal — only matters together
  added_lines_threshold: 300
  min_modules: 2
  require_multi_module: true

ignore_paths:      # mechanical diffs — never trigger, never count toward size
  - "**/*.lock"
  - ...
```

- **`critical_paths` forces generation; size-only never does.** If any
  non-ignored changed file matches a `critical_paths` glob, the policy
  returns `generate: true` immediately and doesn't even look at the size
  numbers. The reverse is never true — no amount of size/module spread
  substitutes for a critical-path match.
- **`ignore_paths` wins over `critical_paths`.** A file matching *both* (e.g.
  generated protobuf code checked into `auth/generated/`) is skipped, not
  flagged. Generated code was never hand-reasoned-about, so it's never worth
  explaining, even on a critical path.
- **`size.min_modules`** is what "spans multiple modules" concretely means —
  the changed (non-ignored) files must span at least this many distinct
  modules. A module is approximated from a file's leading path segments (see
  `MODULE_DEPTH` in `evaluate_policy.py` if your repo's layout needs a
  different depth than the default).

## Tuning it for your repo

- **`critical_paths`** ships with generic placeholders
  (`auth/**`, `billing/**`, `payments/**`, `migrations/**`,
  `permissions/**`, `pricing/**`). Replace or extend them with your repo's
  real layout, e.g.:
  ```yaml
  critical_paths:
    - "src/auth/**"
    - "services/payments/**"
    - "**/kyc/**"
    - "infra/iam/**"
    - "db/migrations/**"
  ```
  Glob syntax matches GitHub Actions' own `paths:` filters: `**` matches
  zero or more path segments, `*` matches within one segment. A pattern
  containing `/` is anchored to the repo root unless it starts with `**/`.
  A pattern with no `/` at all (like `package-lock.json`) matches that
  filename at any depth.
- **`size.added_lines_threshold`** and **`size.min_modules`** are starting
  points (300 lines, 2 modules). Raise them if the size trigger fires too
  often on diffs that turn out to be routine; lower them if genuinely risky
  multi-module changes are slipping through as "not large enough."
- **`ignore_paths`** covers the common cases (lockfiles, `**/generated/**`,
  `**/__snapshots__/**`, minified assets). Add your own generated-code or
  vendored-code directories as you find them.

## Testing it

`evaluate_policy.py` takes no GitHub API calls and does no network I/O, so
it's testable standalone with a hand-written `git diff --numstat` fixture:

```bash
printf '5\t0\tauth/session.py\n200\t10\tweb/dashboard/App.tsx\n' \
  | python3 evaluate_policy.py --pretty
```

The GitHub Actions workflow (`.github/workflows/explain-code-policy.yml`) is
a thin wrapper: it runs `git diff --numstat <base> <head>` on a pull request,
pipes it through this script, and — when the decision is `generate: true` —
posts (or updates) a PR comment with the reason. The workflow does not call
an LLM itself; it only evaluates and flags. Generating the actual walkthrough
is still the skill's job (ask Claude to explain the PR), by design — keeping
WHAT and WHEN apart is the point of this split.
