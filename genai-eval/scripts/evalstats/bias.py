"""Judge bias probes.

An LLM judge is an instrument, and instruments have systematic errors. These
probes measure the four that show up most: preferring whichever answer came
first, rewarding length, favouring its own model's outputs, and giving different
answers when the rubric is reworded.

None of these is a pass/fail test. They produce numbers you report alongside the
agreement statistic so a reader can see what the judge is actually responding to.
"""

import statistics


def _average_ranks(values):
    """Ranks with ties averaged, which is what Spearman requires."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_correlation(xs, ys):
    """Spearman's rank correlation, with average ranks for ties.

    Rank-based rather than Pearson because judge scores are ordinal: the gap
    between a 4 and a 5 is not necessarily the gap between a 1 and a 2.

    Returns None when either sequence is constant, since correlation is
    undefined rather than zero when nothing varies.
    """
    if len(xs) != len(ys):
        raise ValueError("sequences must be the same length")
    if len(xs) < 2:
        raise ValueError("rank correlation needs at least two points")

    rx = _average_ranks(list(xs))
    ry = _average_ranks(list(ys))
    sx = statistics.pstdev(rx)
    sy = statistics.pstdev(ry)
    if sx == 0 or sy == 0:
        return None

    mx = statistics.mean(rx)
    my = statistics.mean(ry)
    covariance = sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / len(rx)
    return covariance / (sx * sy)


def length_bias(judge_scores, human_scores, lengths):
    """How much more than humans does the judge reward long responses?

    Returns judge_rho, human_rho and their gap. The gap is the finding, not
    judge_rho on its own: longer answers really are better sometimes, and a
    judge that tracks length exactly as much as humans do is not biased, it is
    agreeing. Either rho, and therefore the gap, is None when that side has no
    variance to correlate.
    """
    if not (len(judge_scores) == len(human_scores) == len(lengths)):
        raise ValueError("judge scores, human scores and lengths must align")

    judge_rho = rank_correlation(judge_scores, lengths)
    human_rho = rank_correlation(human_scores, lengths)
    gap = None if judge_rho is None or human_rho is None else judge_rho - human_rho
    return {"judge_rho": judge_rho, "human_rho": human_rho, "gap": gap}


def position_bias(pairs):
    """Does the judge prefer whichever response it saw first?

    `pairs` holds one entry per item: (choice when A was shown first, choice
    when B was shown first). Each choice names the *content* picked, "A" or "B",
    not the slot it sat in.

    A judge with no position effect picks the same content both times, giving
    consistency 1.0 and a first_pick_rate of 0.5. A judge driven entirely by
    position picks whatever came first, giving consistency 0.0 and a
    first_pick_rate of 1.0 (or 0.0 if it always picks the second).

    Report both numbers: first_pick_rate says which direction the judge leans,
    consistency says how much of its output the lean is eating.
    """
    if not pairs:
        raise ValueError("no order-swapped pairs supplied")

    first_picks = 0
    consistent = 0
    for choice_ab, choice_ba in pairs:
        if choice_ab not in ("A", "B") or choice_ba not in ("A", "B"):
            raise ValueError("each choice must be 'A' or 'B'")
        if choice_ab == "A":
            first_picks += 1  # A was shown first and A won
        if choice_ba == "B":
            first_picks += 1  # B was shown first and B won
        if choice_ab == choice_ba:
            consistent += 1

    n = len(pairs)
    return {
        "first_pick_rate": first_picks / (2 * n),
        "consistency": consistent / n,
        "n": n,
    }


def self_preference(scores, generators, judge_model):
    """Does the judge score its own model's outputs higher than everyone else's?

    `generators` names the model that produced each response, aligned with
    `scores`. `delta` is own_mean minus other_mean, and is None when either
    group is empty — with nothing to compare against there is no finding.

    A positive delta is not proof of favouritism on its own; the judge's own
    model may genuinely be better on this task. Read it next to the human scores
    for the same responses.
    """
    if len(scores) != len(generators):
        raise ValueError("scores and generators must be the same length")

    own = [s for s, g in zip(scores, generators) if g == judge_model]
    other = [s for s, g in zip(scores, generators) if g != judge_model]

    own_mean = statistics.mean(own) if own else None
    other_mean = statistics.mean(other) if other else None
    delta = None if own_mean is None or other_mean is None else own_mean - other_mean
    return {
        "own_mean": own_mean,
        "other_mean": other_mean,
        "delta": delta,
        "n_own": len(own),
        "n_other": len(other),
    }


def prompt_sensitivity(variant_scores):
    """How much does rewording the rubric change the judge's output?

    `variant_scores` is one score list per rubric wording, all covering the same
    items in the same order.

    Two numbers, because they fail differently. mean_pairwise_rho near 1.0 means
    the *ranking* survives rewording. mean_range is the largest gap between any
    two variants' mean scores, which catches a rubric that preserves the ranking
    while shifting every score up — harmless for a comparison, fatal for an
    absolute threshold.
    """
    if len(variant_scores) < 2:
        raise ValueError("prompt sensitivity needs at least two rubric variants")
    width = len(variant_scores[0])
    if any(len(v) != width for v in variant_scores):
        raise ValueError("every variant must score the same items")

    correlations = []
    for i in range(len(variant_scores)):
        for j in range(i + 1, len(variant_scores)):
            rho = rank_correlation(variant_scores[i], variant_scores[j])
            if rho is not None:
                correlations.append(rho)

    means = [statistics.mean(v) for v in variant_scores]
    return {
        "mean_pairwise_rho": statistics.mean(correlations) if correlations else None,
        "mean_range": max(means) - min(means),
        "n_variants": len(variant_scores),
    }
