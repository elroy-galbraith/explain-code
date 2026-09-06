#!/usr/bin/env python3
"""check_eval_card.py — hold an eval card to the gates a script can check.

Six of the SOP's eleven gates are answerable from the card and its item pool:
a named decision-owner with an action per outcome (1), constructs tracing to
ranked harm pathways (2), a falsifiable construct (3), a claim-to-item trace
matrix (4), a sealed and hash-verified test split (5), and a preregistration
sealed before any result (9). This script answers them, so a model is never
asked to.

It behaves like a linter, not an assertion: every violation in one pass, each
with a JSON path and a gate number. A card gets fixed once, not once per run.

Usage
-----
    python3 check_eval_card.py eval-card.json
    python3 check_eval_card.py eval-card.json --format json
    python3 check_eval_card.py eval-card.json --warnings-as-errors

Exit codes
----------
    0  no error-level findings
    1  at least one error-level finding, or a structural problem
    2  the card could not be read at all — not the same answer as "it failed"
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card import gates, loader


def _tolerate_unencodable_output():
    """Degrade rather than die when the console cannot encode a character.

    The text in a card or a CSV belongs to whoever wrote it: an em dash in a
    construct name, an accent in an owner's name. On a legacy Windows console
    (cp850, cp437) a strict encoder raises UnicodeEncodeError partway through
    the report and the run ends in a traceback, leaving the user unable to tell
    whether their input or the tool is at fault.

    This sets only the *error handler*. The console's encoding is untouched, so
    everything it can already render still renders identically; only a genuinely
    unencodable character becomes a visible escape.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            # A StringIO under test, or a stream that does not support it.
            # Nothing here is worth failing a run over.
            pass


def main(argv=None):
    _tolerate_unencodable_output()
    parser = argparse.ArgumentParser(
        description="Check an eval card against the gates a script can answer, "
        "and report every violation in one pass."
    )
    parser.add_argument("card", help="Path to the eval card JSON.")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="Output format (default: text).")
    parser.add_argument(
        "--warnings-as-errors", action="store_true",
        help="Exit non-zero when only warnings were found.")
    args = parser.parse_args(argv)

    try:
        card, findings = loader.load_card(args.card)
    except ValueError as exc:
        print("check_eval_card: %s" % exc, file=sys.stderr)
        return 2

    findings = list(findings) + gates.run_all(card, args.card)
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]

    if args.format == "json":
        print(json.dumps({
            "card": args.card,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "findings": [
                {"gate": f.gate, "level": f.level, "path": f.path,
                 "message": f.message}
                for f in findings
            ],
        }, indent=2))
    else:
        if not findings:
            print("%s: no findings. Gates 1, 2, 3, 4, 5 and 9 pass."
                  % args.card)
        else:
            print("%s: %d error(s), %d warning(s)\n"
                  % (args.card, len(errors), len(warnings)))
            for finding in findings:
                print("  " + finding.render())
        # Both branches, not only the one carrying findings. A clean report is
        # the output most likely to be pasted into a review as evidence that
        # an eval is sound, so it is the last place that should omit the
        # sentence saying five gates were never examined.
        print("\nGates 6, 7, 8, 10 and 11 need a qualification block and "
              "are not checked here.")

    return 1 if errors or (warnings and args.warnings_as_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
