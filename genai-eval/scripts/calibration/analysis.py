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
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evalstats import agreement, bias, power


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


def bias_section(data, judge_model=None):
    """Whichever judge bias probes the available columns support.

    Each probe that cannot run is named in `unavailable` together with what it
    would need. A silently skipped probe reads as a probe that found nothing.
    """
    unavailable = []

    length = None
    if data.lengths is None:
        unavailable.append(
            "Length bias: needs a response length column (characters, tokens "
            "or words)."
        )
    else:
        human_name = next(iter(data.human_columns))
        length = bias.length_bias(
            data.judge_scores, data.human_columns[human_name], data.lengths
        )

    preference = None
    if data.generators is None:
        unavailable.append(
            "Self-preference: needs a generator column naming which model "
            "produced each response."
        )
    elif judge_model is None:
        unavailable.append(
            "Self-preference: needs the judge model's name, to know which "
            "generator counts as its own. Pass --judge-model."
        )
    else:
        preference = bias.self_preference(
            data.judge_scores, data.generators, judge_model
        )

    return {
        "length": length,
        "self_preference": preference,
        "unavailable": unavailable,
    }


def disagreement_clusters(data, limit=None):
    """Count which (human label, judge label) pairs disagree, and how often.

    This is the observed half of a failure taxonomy. It does not name the
    categories — that needs someone who understands the rubric, and a name
    invented here would be a guess dressed as a finding. The skill reads these
    counts and supplies the names.

    Rows where either rating is missing are skipped: a blank cell is not a
    disagreement. Pairs are keyed on the first human rater column, which is the
    one a single-rater file has.
    """
    human_name = next(iter(data.human_columns))
    human = data.human_columns[human_name]
    judge = data.judge_scores

    buckets = {}
    for row in range(data.n):
        h, j = human[row], judge[row]
        if h is None or j is None or h == j:
            continue
        entry = buckets.setdefault((h, j), [])
        entry.append(data.item_ids[row] if data.item_ids else None)

    total = sum(len(ids) for ids in buckets.values())
    clusters = [
        {
            "human": h,
            "judge": j,
            "count": len(ids),
            "item_ids": [i for i in ids if i is not None],
            "share": len(ids) / total,
        }
        for (h, j), ids in buckets.items()
    ]
    clusters.sort(key=lambda c: (-c["count"], str(c["human"]), str(c["judge"])))
    return clusters[:limit] if limit else clusters


def power_section(data, mid=None, baseline=None):
    """Can this many items detect the difference you would act on?

    `mid` is the minimum interesting difference in proportion terms — the
    smallest change in judge-human exact agreement that would change a
    decision. Without one there is no sufficiency question to answer, and
    guessing a value would produce a verdict nobody asked for.

    `baseline` defaults to the observed exact-agreement rate.
    """
    human_name = next(iter(data.human_columns))
    human = data.human_columns[human_name]

    if baseline is None:
        comparable = [
            (h, j)
            for h, j in zip(human, data.judge_scores)
            if h is not None and j is not None
        ]
        baseline = (
            sum(1 for h, j in comparable if h == j) / len(comparable)
            if comparable
            else None
        )

    result = {
        "n": data.n,
        "baseline": baseline,
        "mde": None,
        "mid": mid,
        "n_required": None,
        "sufficient": None,
    }
    if baseline is None or not 0.0 < baseline < 1.0:
        return result

    result["mde"] = power.mde_two_proportion(data.n, baseline)

    if mid is not None:
        target = min(baseline + mid, 1.0 - 1e-9)
        result["n_required"] = math.ceil(
            power.n_required_two_proportion(baseline, target)
        )
        result["sufficient"] = data.n >= result["n_required"]

    return result
