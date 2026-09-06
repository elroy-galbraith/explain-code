#!/usr/bin/env python3
"""calibrate.py — is this LLM judge trustworthy enough to automate?

Bare mode for the eval-qualify skill. Reads a CSV of judge scores and human
labels and writes a calibration report: chance-corrected agreement with
confidence intervals, the human-human ceiling when the data supports one, judge
bias probes, a power check, and an observed disagreement taxonomy.

Usage
-----
    python3 calibrate.py labels.csv
    python3 calibrate.py labels.csv --level ordinal --categories low,medium,high
    python3 calibrate.py labels.csv --mid 0.05 -o report.md

The only required columns are one judge score and one human label. Every other
column adds a section; each missing one is named in the report rather than
quietly skipped.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calibration import analysis, loader, report
from evalstats import agreement


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


def _run_section(name, compute, fallback, errors):
    """Run one section. A section that cannot run must not erase the rest.

    The whole thesis of this tool is "report what you can and name what you
    cannot", and aborting the entire report because one probe met an input it
    did not expect contradicts that at the worst possible moment - when
    something in the data is unusual. The reason is surfaced in the report's
    limits section, where a reader is already looking for what it could not
    do.

    Genuine user errors - a missing file, an undetectable column, an
    incomplete --categories - are raised before any section runs and still
    exit 1 with nothing printed.
    """
    try:
        return compute()
    except Exception as exc:  # deliberately broad: see the docstring above
        errors.append(
            "The %s section could not be computed: %s: %s"
            % (name, type(exc).__name__, exc)
        )
        return fallback


def main(argv=None):
    _tolerate_unencodable_output()

    parser = argparse.ArgumentParser(
        description="Measure whether an LLM judge agrees with humans well "
        "enough to trust, and say plainly what the data cannot support."
    )
    parser.add_argument("labels", help="CSV of judge scores and human labels.")
    parser.add_argument("--judge", help="Judge score column (default: detected).")
    parser.add_argument(
        "--human", action="append", dest="humans",
        help="Human label column; repeat for multiple raters (default: detected).",
    )
    parser.add_argument("--item-id", help="Item id column (default: detected).")
    parser.add_argument("--length", help="Response length column (default: detected).")
    parser.add_argument("--generator", help="Generator column (default: detected).")
    parser.add_argument(
        "--judge-model", help="The judge's own model name, for the self-preference probe."
    )
    parser.add_argument(
        "--level", choices=("nominal", "ordinal", "interval"), default="nominal",
        help="Measurement level for Krippendorff's alpha (default: nominal).",
    )
    parser.add_argument(
        "--categories",
        help="Comma-separated scale order, low to high. Required for ordinal "
        "or interval levels with non-numeric labels. It must name every "
        "rating value that appears in the judge and human columns, and name "
        "each one once: an omitted rating is rejected rather than ranked as a "
        "guess, and a repeated one would take its last position in the order.",
    )
    parser.add_argument(
        "--mid", type=float,
        help="Minimum interesting difference in agreement rate, for the power check.",
    )
    parser.add_argument("--seed", type=int, help="Seed for the bootstrap.")
    parser.add_argument(
        "--resamples", type=int, default=2000, help="Bootstrap resamples (default: 2000)."
    )
    parser.add_argument("--title", help="Report title.")
    parser.add_argument("-o", "--out", help="Write to this file instead of stdout.")
    args = parser.parse_args(argv)

    categories = args.categories.split(",") if args.categories else None

    try:
        data = loader.load_labels(
            args.labels,
            judge=args.judge,
            humans=args.humans,
            item_id=args.item_id,
            length=args.length,
            generator=args.generator,
        )

        if args.level != "nominal" and categories is None:
            if not data.numeric.get(data.judge_column, False):
                raise ValueError(
                    "--level %s with non-numeric ratings needs --categories to "
                    "state the scale order; sorting labels alphabetically would "
                    "produce a confident wrong answer" % args.level
                )

        if categories is not None and data.numeric.get(data.judge_column, False):
            # The loader coerces a numeric column to floats, so a scale stated
            # as text covers none of its ratings: "1" is not 1.0. Take each
            # entry through the same float() path that column took. Normalising
            # both sides with str() instead would only move the failure into
            # krippendorff_alpha, which indexes the ratings by the scale's own
            # values.
            numeric_categories = []
            for value in categories:
                try:
                    numeric_categories.append(float(value))
                except ValueError:
                    raise ValueError(
                        "--categories entry %r is not a number, but the judge "
                        "column %s holds numeric ratings; state the scale in "
                        "the same terms as the data"
                        % (value, data.judge_column)
                    )
            categories = numeric_categories

        if categories is not None:
            observed = set(data.judge_scores)
            for values in data.human_columns.values():
                observed.update(values)
            observed.discard(None)
            try:
                agreement.scale_order(categories, observed)
            except ValueError as exc:
                raise ValueError(
                    "--categories does not describe the ratings in %s: %s. "
                    "Either way the agreement figure comes back undefined or "
                    "quietly wrong, which reads as a problem with your data "
                    "rather than with your command."
                    % (args.labels, exc)
                )

    except (OSError, ValueError, TypeError) as exc:
        print("calibrate: %s" % exc, file=sys.stderr)
        return 1

    errors = []
    agreement_result = _run_section(
        "agreement",
        lambda: analysis.agreement_section(
            data,
            level=args.level,
            categories=categories,
            seed=args.seed,
            n_resamples=args.resamples,
        ),
        {
            "judge_human": {"alpha": None, "ci": None, "n": 0, "why": None},
            "human_human": None,
            "ceiling_available": False,
            "verdict": None,
            "notes": [],
        },
        errors,
    )
    bias_result = _run_section(
        "judge bias",
        lambda: analysis.bias_section(
            data, judge_model=args.judge_model, categories=categories
        ),
        {"length": None, "self_preference": None, "unavailable": []},
        errors,
    )
    clusters = _run_section(
        "disagreement clusters",
        lambda: analysis.disagreement_clusters(data),
        None,
        errors,
    )
    power_result = _run_section(
        "statistical power",
        lambda: analysis.power_section(data, mid=args.mid),
        {
            "n": 0,
            "rows": data.n,
            "baseline": None,
            "mde": None,
            "mid": args.mid,
            "n_required": None,
            "sufficient": None,
        },
        errors,
    )

    text = report.render(
        data,
        agreement_result,
        bias_result,
        clusters,
        power_result,
        title=args.title,
        section_errors=errors,
    )

    try:
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
        else:
            print(text)
    except OSError as exc:
        print("calibrate: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
