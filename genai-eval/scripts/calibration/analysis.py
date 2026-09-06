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


def _pairable(units):
    """How many units the statistic can actually use.

    Krippendorff's alpha drops every unit with fewer than two present ratings,
    so the row count overstates the sample behind the figure — with seven of
    ten judge cells blank the report said n = 10 for a number computed from
    three. The n printed next to a figure has to be the n it was computed
    from, or it invites a reader to treat a three-item result as a ten-item
    one.
    """
    return sum(
        1 for unit in units if sum(1 for v in unit if v is not None) >= 2
    )


def _alpha_with_ci(units, level, categories, seed, n_resamples):
    """Point estimate plus interval, with both failures reported honestly."""

    def statistic(sample):
        return agreement.krippendorff_alpha(sample, level=level, categories=categories)

    n = _pairable(units)

    try:
        point = statistic(units)
    except ValueError as exc:
        return {"alpha": None, "ci": None, "n": n, "why": str(exc)}

    try:
        interval = agreement.bootstrap_ci(
            units, statistic, n_resamples=n_resamples, seed=seed
        )
    except ValueError as exc:
        return {"alpha": point, "ci": None, "n": n, "why": str(exc)}

    return {"alpha": point, "ci": interval, "n": n, "why": None}


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


def _all_numeric(values):
    """True when every rating that is present is a real number.

    Both probes need this for different reasons: the length probe ranks the
    ratings, and `statistics.mean` inside the self-preference probe refuses
    strings outright.
    """
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in values
        if v is not None
    )


def _on_scale(values, index):
    """Rewrite ratings as their position on the stated scale.

    Returns None when a rating is absent from `index` — putting it somewhere on
    the scale would mean inventing a place the caller never stated.
    """
    encoded = []
    for value in values:
        if value is None:
            encoded.append(None)
        elif value in index:
            encoded.append(index[value])
        else:
            return None
    return encoded


def bias_section(data, judge_model=None, categories=None):
    """Whichever judge bias probes the available columns support.

    Each probe that cannot run is named in `unavailable` together with what it
    would need. A silently skipped probe reads as a probe that found nothing.

    `categories` is the stated scale order, low to high, and matters here as
    much as it does for alpha: the length probe ranks the ratings, and ranking
    "low", "medium", "high" with no stated order sorts them alphabetically into
    high < low < medium. That can flip the sign of the reported gap, so word
    labels with no `categories` skip the probe rather than rank as text.

    Rows where any of the three aligned columns is blank are dropped before the
    correlation, and the surviving count travels with the result as `n`. The
    rest of this pipeline already treats a blank cell as missing rather than as
    a rating; sorting one would raise instead.
    """
    unavailable = []
    index = {c: i for i, c in enumerate(categories)} if categories else None

    length = None
    if data.lengths is None:
        unavailable.append(
            "Length bias: needs a response length column (characters, tokens "
            "or words)."
        )
    else:
        human_name = next(iter(data.human_columns))
        judge = data.judge_scores
        human = data.human_columns[human_name]
        if index is not None:
            judge, human = _on_scale(judge, index), _on_scale(human, index)

        if judge is None or human is None:
            unavailable.append(
                "Length bias: a rating is missing from the stated scale order, "
                "so its rank on that scale is unknown. Name every rating value "
                "in --categories."
            )
        elif not (_all_numeric(judge) and _all_numeric(human)):
            unavailable.append(
                "Length bias: needs numeric ratings, or --categories stating "
                "the scale order low to high. Ranking word labels without a "
                "stated order sorts them alphabetically, which can report the "
                "judge penalising length when it rewards it."
            )
        else:
            rows = [
                (j, h, size)
                for j, h, size in zip(judge, human, data.lengths)
                if j is not None and h is not None and size is not None
            ]
            if len(rows) < 2:
                unavailable.append(
                    "Length bias: %d row(s) have a judge score, a human label "
                    "and a length together; the correlation needs at least two."
                    % len(rows)
                )
            else:
                length = bias.length_bias(
                    [r[0] for r in rows],
                    [r[1] for r in rows],
                    [r[2] for r in rows],
                )
                length["n"] = len(rows)

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
    elif not _all_numeric(data.judge_scores):
        unavailable.append(
            "Self-preference: comparing means needs numeric scores, and this "
            "judge column holds labels. Rescore on a numeric scale to run it."
        )
    else:
        scored = [
            (s, g)
            for s, g in zip(data.judge_scores, data.generators)
            if s is not None
        ]
        if not scored:
            unavailable.append(
                "Self-preference: no row carries a judge score."
            )
        else:
            preference = bias.self_preference(
                [s for s, _ in scored], [g for _, g in scored], judge_model
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

    `n` is the number of comparable rows — rows carrying both a judge score
    and a human label — not the file's row count. The baseline was only ever
    computed over those, so passing the row count to the power calculation
    credited the sample with items that contributed nothing to it.
    """
    human_name = next(iter(data.human_columns))
    human = data.human_columns[human_name]

    comparable = [
        (h, j)
        for h, j in zip(human, data.judge_scores)
        if h is not None and j is not None
    ]
    n = len(comparable)

    if baseline is None:
        baseline = (
            sum(1 for h, j in comparable if h == j) / n if comparable else None
        )

    result = {
        "n": n,
        "rows": data.n,
        "baseline": baseline,
        "mde": None,
        "mid": mid,
        "n_required": None,
        "sufficient": None,
    }
    if n < 1 or baseline is None or not 0.0 < baseline < 1.0:
        return result

    result["mde"] = power.mde_two_proportion(n, baseline)

    if mid is not None:
        target = min(baseline + mid, 1.0 - 1e-9)
        result["n_required"] = math.ceil(
            power.n_required_two_proportion(baseline, target)
        )
        result["sufficient"] = n >= result["n_required"]

    return result
