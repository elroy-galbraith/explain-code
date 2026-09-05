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
