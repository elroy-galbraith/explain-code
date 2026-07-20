#!/usr/bin/env python3
"""
evaluate_policy.py — decide WHEN explain-code should auto-generate a
walkthrough for a PR, per explain-code-policy.yml.

This is deliberately a small, standalone script with no GitHub API calls, so
it's testable on its own: feed it a `git diff --numstat` style diff and a
policy file, and it prints a JSON decision. The GitHub Actions workflow in
.github/workflows/ is a thin wrapper — it produces the numstat input (via
`git diff --numstat base head`) and acts on this script's JSON output.

Priority order (see policy/README.md for the full rationale):
  1. Any non-ignored changed file matching `critical_paths` -> generate,
     regardless of size. This is checked first and short-circuits everything
     else.
  2. Otherwise, size only matters together with module count: added lines
     (excluding ignore_paths) >= added_lines_threshold AND the changed files
     span >= min_modules distinct modules (when require_multi_module: true).
  3. Otherwise -> don't auto-generate. (One-click opt-in still exists outside
     this script, e.g. asking Claude directly.)

Usage
-----
    git diff --numstat origin/main...HEAD | python3 evaluate_policy.py
    python3 evaluate_policy.py --policy explain-code-policy.yml --diff pr.numstat --pretty
"""

import argparse
import functools
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(
        "evaluate_policy.py: PyYAML is required to read the policy file "
        "(`pip install pyyaml`)."
    )


# How many leading path segments (directories, not the filename) count as
# one "module" when checking require_multi_module. 2 handles both flat repos
# (auth/token.py -> "auth") and the common src/<module>/... or
# packages/<module>/... layout (src/billing/x.py -> "src/billing", distinct
# from src/auth/y.py -> "src/auth"). Adjust here if your repo's layout needs
# a different depth; it isn't exposed in the YAML to keep that file legible.
MODULE_DEPTH = 2


# --------------------------------------------------------------------------- #
# Glob matching (gitignore / GitHub Actions `paths:` style)
# --------------------------------------------------------------------------- #

@functools.lru_cache(maxsize=None)
def _glob_to_regex(pattern):
    """Compile one policy glob to a full-path regex.

    `**` matches zero or more whole path segments; `*` matches within a
    single segment; `?` matches one character within a segment. A pattern
    containing no "/" matches that name at any depth (like .gitignore);
    otherwise the pattern is anchored to the repo root unless it starts with
    "**/" — the same convention GitHub Actions uses for `paths:` filters.
    """
    if "/" not in pattern:
        pattern = f"**/{pattern}"

    out = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if pattern[i:i + 2] == "**":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _matches_any(path, patterns):
    """Return the subset of `patterns` that match `path`."""
    return [p for p in patterns if _glob_to_regex(p).match(path)]


# --------------------------------------------------------------------------- #
# `git diff --numstat` parsing
# --------------------------------------------------------------------------- #

_BRACE_RENAME_RE = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")


def _resolve_numstat_path(raw):
    """Resolve git's rename notation in --numstat's path column.

    git emits either `old/path => new/path` (whole-path rename) or
    `common{old => new}suffix` (rename confined to one segment). Either way
    we only care about the resulting (new) path.
    """
    m = _BRACE_RENAME_RE.match(raw)
    if m:
        prefix, _old, new, suffix = m.groups()
        return f"{prefix}{new}{suffix}"
    if " => " in raw:
        return raw.split(" => ", 1)[1].strip()
    return raw


def parse_numstat(text):
    """Parse `git diff --numstat` output into a list of (added_lines, path).

    Binary files report `-` for both counts in numstat; treated as 0 added
    lines here since line counts are meaningless for binaries anyway (and
    binaries are unlikely to be hand-reasoned-about source changes).
    """
    files = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, _deleted, raw_path = parts
        path = _resolve_numstat_path(raw_path.strip())
        added_n = int(added) if added.strip().isdigit() else 0
        files.append((added_n, path))
    return files


# --------------------------------------------------------------------------- #
# Policy evaluation
# --------------------------------------------------------------------------- #

def module_of(path, depth=MODULE_DEPTH):
    """Best-effort 'module' a changed file belongs to, for module counting."""
    dir_parts = Path(path).parts[:-1]
    if not dir_parts:
        return "."  # root-level file
    return "/".join(dir_parts[:depth])


def evaluate(policy, files):
    """Apply the policy to a list of (added_lines, path) tuples.

    Returns a JSON-serializable decision dict. Ignored files are excluded
    before *both* the critical-path check and the size/module count, so a
    file that happens to match both an ignore glob and a critical-path glob
    (e.g. generated code under auth/) is skipped, not flagged — generated
    code is never worth explaining, even on a critical path.
    """
    critical_paths = policy.get("critical_paths") or []
    ignore_paths = policy.get("ignore_paths") or []
    size = policy.get("size") or {}
    added_threshold = size.get("added_lines_threshold", float("inf"))
    min_modules = size.get("min_modules", 2)
    require_multi_module = size.get("require_multi_module", True)

    considered = []
    ignored = []
    matched_critical = {}

    for added, path in files:
        if _matches_any(path, ignore_paths):
            ignored.append(path)
            continue
        considered.append((added, path))
        hits = _matches_any(path, critical_paths)
        if hits:
            matched_critical[path] = hits

    added_total = sum(a for a, _ in considered)
    modules_touched = sorted({module_of(p) for _, p in considered})

    if matched_critical:
        touched = sorted(matched_critical)
        shown = ", ".join(touched[:5]) + ("…" if len(touched) > 5 else "")
        return {
            "generate": True,
            "trigger": "critical_path",
            "reason": f"{len(touched)} changed file(s) match a critical path: {shown}.",
            "matched_critical_paths": matched_critical,
            "added_lines_considered": added_total,
            "modules_touched": modules_touched,
            "ignored_files": ignored,
        }

    is_large = added_total >= added_threshold
    is_multi_module = len(modules_touched) >= min_modules
    size_trigger = is_large and (is_multi_module or not require_multi_module)

    if size_trigger:
        reason = (
            f"{added_total} added line(s) across {len(modules_touched)} module(s) "
            f"clears the size bar (>= {added_threshold} lines"
            + (f" and >= {min_modules} modules" if require_multi_module else "")
            + ")."
        )
    else:
        reason = (
            f"No critical path touched; {added_total} added line(s) across "
            f"{len(modules_touched)} module(s) doesn't clear the size bar "
            f"(needs >= {added_threshold} lines"
            + (f" AND >= {min_modules} modules" if require_multi_module else "")
            + "). One-click opt-in is still available on request."
        )

    return {
        "generate": bool(size_trigger),
        "trigger": "size_multi_module" if size_trigger else "none",
        "reason": reason,
        "matched_critical_paths": {},
        "added_lines_considered": added_total,
        "modules_touched": modules_touched,
        "ignored_files": ignored,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Evaluate a PR diff against an explain-code CI policy."
    )
    ap.add_argument(
        "--policy",
        default=str(Path(__file__).with_name("explain-code-policy.yml")),
        help="Path to the policy YAML file (default: explain-code-policy.yml next to this script).",
    )
    ap.add_argument(
        "--diff",
        help="Path to a `git diff --numstat` file. Reads stdin if omitted.",
    )
    ap.add_argument(
        "--pretty", action="store_true", help="Pretty-print the JSON decision."
    )
    args = ap.parse_args(argv)

    policy_text = Path(args.policy).read_text(encoding="utf-8")
    policy = yaml.safe_load(policy_text) or {}

    diff_text = (
        Path(args.diff).read_text(encoding="utf-8")
        if args.diff
        else sys.stdin.read()
    )
    files = parse_numstat(diff_text)

    decision = evaluate(policy, files)
    print(json.dumps(decision, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
