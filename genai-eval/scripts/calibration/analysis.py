"""Decide which statistics the available columns actually support, then run them.

The rule this module exists to enforce: a judge's agreement number means
nothing on its own. It has to be read against how well humans agree with each
other, because that ceiling is the best any instrument could do on this task.
With one human rater there is no ceiling, so this module reports the judge's
number and states plainly that it cannot be graded — rather than letting a
reader assume it passed a bar that was never measured.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import agreement


def _alpha_with_ci(units, level, categories, seed, n_resamples):
    """Point estimate plus interval, with both failures reported honestly."""

    def statistic(sample):
        return agreement.krippendorff_alpha(sample, level=level, categories=categories)

    try:
        point = statistic(units)
    except ValueError as exc:
        return {"alpha": None, "ci": None, "n": len(units), "why": str(exc)}

    try:
        interval = agreement.bootstrap_ci(
            units, statistic, n_resamples=n_resamples, seed=seed
        )
    except ValueError as exc:
        return {"alpha": point, "ci": None, "n": len(units), "why": str(exc)}

    return {"alpha": point, "ci": interval, "n": len(units), "why": None}


def agreement_section(data, level="nominal", categories=None, seed=None,
                      n_resamples=2000):
    """Judge-human agreement, the human-human ceiling, and the verdict between.

    `data` is a loader.CalibrationData. `level` and `categories` are passed
    through to Krippendorff's alpha — pass `categories` whenever the ratings
    are word labels on an ordinal scale, or the scale order will come from
    sorting them alphabetically.

    verdict is "no_ceiling" when fewer than two human raters exist,
    "at_or_above_ceiling" when the judge's point estimate reaches the humans',
    and "below_ceiling" otherwise.
    """
    human_names = list(data.human_columns)
    notes = []

    pooled_human = []
    for row in range(data.n):
        ratings = [data.human_columns[name][row] for name in human_names]
        present = [r for r in ratings if r is not None]
        pooled_human.append(present[0] if present else None)

    judge_units = [
        [data.judge_scores[row], pooled_human[row]] for row in range(data.n)
    ]
    judge_human = _alpha_with_ci(
        judge_units, level, categories, seed, n_resamples
    )
    if judge_human["alpha"] is None:
        notes.append(
            "Judge-human agreement is undefined: %s" % judge_human["why"]
        )
    elif judge_human["ci"] is None:
        notes.append(
            "No confidence interval for judge-human agreement: %s"
            % judge_human["why"]
        )

    if len(human_names) < 2:
        notes.append(
            "There is no human-human ceiling, because only one human rater "
            "column was supplied. The judge's agreement figure below cannot be "
            "compared against anything, so Gate 6 stays unanswered. Add a "
            "second independent rater on at least a subset of items."
        )
        return {
            "judge_human": judge_human,
            "human_human": None,
            "ceiling_available": False,
            "verdict": "no_ceiling",
            "notes": notes,
        }

    human_units = [
        [data.human_columns[name][row] for name in human_names]
        for row in range(data.n)
    ]
    human_human = _alpha_with_ci(
        human_units, level, categories, seed, n_resamples
    )
    if human_human["alpha"] is None:
        notes.append("The ceiling is undefined: %s" % human_human["why"])
        verdict = "no_ceiling"
    elif judge_human["alpha"] is None:
        verdict = "no_ceiling"
    elif judge_human["alpha"] >= human_human["alpha"]:
        verdict = "at_or_above_ceiling"
    else:
        verdict = "below_ceiling"

    return {
        "judge_human": judge_human,
        "human_human": human_human,
        "ceiling_available": human_human["alpha"] is not None,
        "verdict": verdict,
        "notes": notes,
    }
