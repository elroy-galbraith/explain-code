"""Saturation and contamination signals for an item pool.

Gate 11 asks whether the benchmark still measures anything. Two things end its
useful life: every system reaching the ceiling, so the score stops separating
them, and the items leaking into training data, so the score measures recall.

A retired benchmark keeps getting cited. That is why this gate exists and why
its answer belongs in the report rather than in someone's memory.
"""


def ceiling_proportion(scores, max_score):
    """Share of scores sitting at or above the maximum.

    Scores above the stated maximum are counted rather than ignored: a grader
    that exceeds its own scale is a bug worth surfacing, and the item is at
    ceiling either way.
    """
    if not scores:
        raise ValueError("no scores supplied")
    return sum(1 for s in scores if s >= max_score) / len(scores)


def canary_hit_rate(outputs, canary):
    """Share of model outputs containing the canary string.

    A canary is a unique string planted in the item pool. If it comes back out
    of a model, the pool is in that model's training data and every number
    derived from it measures memorisation.

    Any non-zero rate is a finding. This is not a threshold to tune.
    """
    if not outputs:
        raise ValueError("no outputs supplied")
    if not canary:
        raise ValueError(
            "canary string is empty; an empty needle matches every output"
        )
    return sum(1 for text in outputs if canary in text) / len(outputs)


def saturation_report(scores, max_score, ceiling_threshold=0.90):
    """Ceiling summary with a saturation verdict.

    `saturated` is True once the ceiling proportion reaches the threshold. At
    that point the eval can no longer distinguish a good system from a very good
    one, and Gate 11 says retire it and refresh the pool.
    """
    proportion = ceiling_proportion(scores, max_score)
    return {
        "ceiling_proportion": proportion,
        "n": len(scores),
        "saturated": proportion >= ceiling_threshold,
    }
