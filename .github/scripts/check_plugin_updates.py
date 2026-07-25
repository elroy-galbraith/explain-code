#!/usr/bin/env python3
"""
check_plugin_updates.py -- find newer upstream tags for third-party plugins in a
Claude Code marketplace manifest, and optionally bump a plugin's pinned `ref`.

A "third-party plugin" here is a marketplace entry whose `source` is a GitHub
object pinned to a stable semver tag, e.g.:

    { "source": "github", "repo": "blader/humanizer", "ref": "v2.9.1" }

Entries with a local path source ("./foo"), or a github source pinned to a
branch (e.g. "main") or a commit SHA, are deliberately left alone: a branch
already tracks latest, and a SHA is a manual pin. Only stable semver-tag pins
(vX.Y.Z or X.Y.Z) are managed.

Usage:
    # human-readable report of available updates
    python3 check_plugin_updates.py --marketplace .claude-plugin/marketplace.json

    # machine-readable list for CI
    python3 check_plugin_updates.py --marketplace <path> --json

    # bump one plugin's pinned ref in place
    python3 check_plugin_updates.py --marketplace <path> --apply humanizer --ref v2.9.2

No third-party dependencies; tag discovery uses `git ls-remote`, so no API token
is needed for public upstreams.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_semver(tag):
    """Return (major, minor, patch) for a stable semver tag, else None."""
    m = SEMVER.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def list_upstream_tags(repo):
    """Return tag names for a github repo via `git ls-remote --tags`."""
    url = f"https://github.com/{repo}.git"
    out = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    tags = set()
    for line in out.splitlines():
        # lines look like "<sha>\trefs/tags/<name>" or ".../<name>^{}"
        _, _, ref = line.partition("\trefs/tags/")
        if ref:
            tags.add(ref[:-3] if ref.endswith("^{}") else ref)
    return sorted(tags)


def latest_stable_tag(repo):
    """Highest stable semver tag for a repo, or None if it has none."""
    best, best_key = None, None
    for tag in list_upstream_tags(repo):
        key = parse_semver(tag)
        if key is not None and (best_key is None or key > best_key):
            best, best_key = tag, key
    return best


def managed_plugins(manifest):
    """Yield plugin entries pinned to a stable-semver-tag github source."""
    for p in manifest.get("plugins", []):
        src = p.get("source")
        if not isinstance(src, dict) or src.get("source") != "github":
            continue
        if src.get("repo") and parse_semver(src.get("ref")) is not None:
            yield p


def find_updates(manifest):
    """List available updates: {name, repo, current_ref, latest_ref}."""
    updates = []
    for p in managed_plugins(manifest):
        repo, ref = p["source"]["repo"], p["source"]["ref"]
        try:
            latest = latest_stable_tag(repo)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as ex:
            print(f"warning: could not fetch tags for {repo}: {ex}", file=sys.stderr)
            continue
        if latest and parse_semver(latest) > parse_semver(ref):
            updates.append({
                "name": p.get("name", repo),
                "repo": repo,
                "current_ref": ref,
                "latest_ref": latest,
            })
    return updates


def apply_bump(raw, manifest, name, new_ref):
    """Return marketplace text with `name`'s pinned ref set to `new_ref`,
    preserving formatting when the old ref value is unambiguous."""
    target = next((p for p in managed_plugins(manifest) if p.get("name") == name), None)
    if target is None:
        sys.exit(f"no github-tag-pinned plugin named {name!r}")
    if parse_semver(new_ref) is None:
        sys.exit(f"--ref {new_ref!r} is not a stable semver tag")

    old_ref = target["source"]["ref"]
    needle = f'"ref": "{old_ref}"'
    if raw.count(needle) == 1:  # minimal, format-preserving edit
        return raw.replace(needle, f'"ref": "{new_ref}"')
    target["source"]["ref"] = new_ref  # fallback: re-serialize
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check/bump third-party plugin pins.")
    ap.add_argument("--marketplace", required=True, help="path to marketplace.json")
    ap.add_argument("--json", action="store_true", help="emit updates as JSON")
    ap.add_argument("--apply", metavar="NAME", help="bump this plugin's ref in place")
    ap.add_argument("--ref", help="the new semver tag to pin (with --apply)")
    args = ap.parse_args(argv)

    raw = open(args.marketplace, encoding="utf-8").read()
    manifest = json.loads(raw)

    if args.apply:
        if not args.ref:
            sys.exit("--apply requires --ref")
        new_text = apply_bump(raw, manifest, args.apply, args.ref)
        json.loads(new_text)  # sanity: must remain valid JSON
        with open(args.marketplace, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        print(f"pinned {args.apply} -> {args.ref}")
        return

    updates = find_updates(manifest)
    if args.json:
        print(json.dumps(updates))
        return
    if not updates:
        print("All third-party plugins are on their latest upstream tag.")
        return
    print("Available plugin updates:")
    for u in updates:
        print(f"  {u['name']}: {u['current_ref']} -> {u['latest_ref']}  ({u['repo']})")


if __name__ == "__main__":
    main()
