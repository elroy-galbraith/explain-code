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


def main(argv=None):
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
        "or interval levels with non-numeric labels.",
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

        if categories is not None:
            observed = set(data.judge_scores)
            for values in data.human_columns.values():
                observed.update(values)
            observed.discard(None)
            try:
                agreement.scale_order(categories, observed)
            except ValueError as exc:
                raise ValueError(
                    "--categories does not describe the ratings in %s: %s. A "
                    "scale that omits a rating makes the agreement figure come "
                    "back undefined, and one that repeats a value quietly "
                    "ranks the earlier position wrong; both read as a problem "
                    "with your data rather than with your command."
                    % (args.labels, exc)
                )

        text = report.render(
            data,
            analysis.agreement_section(
                data,
                level=args.level,
                categories=categories,
                seed=args.seed,
                n_resamples=args.resamples,
            ),
            analysis.bias_section(
                data, judge_model=args.judge_model, categories=categories
            ),
            analysis.disagreement_clusters(data),
            analysis.power_section(data, mid=args.mid),
            title=args.title,
        )
    except (OSError, ValueError, TypeError) as exc:
        print("calibrate: %s" % exc, file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
