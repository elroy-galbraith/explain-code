"""Statistical power for eval comparisons.

Gate 7 of the SOP asks whether the instrument can detect the smallest difference
you would act on. Most model-versus-model calls are made on item counts far too
small to support them, and the comparison then reports noise with a confident
face. These functions turn "is this enough items?" into a number.
"""

import math
import random
import statistics
from statistics import NormalDist

_NORMAL = NormalDist()


def n_required_two_proportion(p1, p2, alpha=0.05, power=0.80):
    """Items per group needed to detect p1 versus p2, two-sided.

    Returns an unrounded float; the caller decides whether to ceil it. Uses the
    standard normal approximation with unpooled variance:

        n = (z_{1-alpha/2} + z_{power})^2 * (p1*q1 + p2*q2) / (p1 - p2)^2

    The approximation is unreliable when n*p is very small, which in practice
    means proportions within a whisker of 0 or 1.
    """
    for name, value in (("p1", p1), ("p2", p2)):
        if not 0.0 < value < 1.0:
            raise ValueError("%s must be strictly between 0 and 1" % name)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be strictly between 0 and 1")
    if p1 == p2:
        raise ValueError("p1 and p2 are equal; there is no effect to detect")

    z_alpha = _NORMAL.inv_cdf(1.0 - alpha / 2.0)
    z_power = _NORMAL.inv_cdf(power)
    variance = p1 * (1.0 - p1) + p2 * (1.0 - p2)
    return ((z_alpha + z_power) ** 2) * variance / ((p1 - p2) ** 2)


def mde_two_proportion(n, baseline, alpha=0.05, power=0.80, direction="up",
                       tolerance=1e-7):
    """Smallest detectable proportion against `baseline` with `n` items per group.

    Solved by bisection rather than in closed form, because the required-n
    formula has the unknown proportion inside its own variance term.

    `direction` is "up" to search above the baseline or "down" to search below.
    Returns None when nothing in range is detectable at this sample size — which
    is the honest answer for a small eval, and much more useful than a number.
    """
    if direction not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")
    if not 0.0 < baseline < 1.0:
        raise ValueError("baseline must be strictly between 0 and 1")
    if n < 1:
        raise ValueError("n must be at least 1")

    edge = 1.0 - tolerance if direction == "up" else tolerance
    if n_required_two_proportion(baseline, edge, alpha, power) > n:
        return None

    near, far = baseline, edge
    for _ in range(200):
        middle = (near + far) / 2.0
        if abs(middle - baseline) < tolerance:
            break
        if n_required_two_proportion(baseline, middle, alpha, power) > n:
            near = middle  # not detectable, move away from the baseline
        else:
            far = middle  # detectable, try closer to the baseline
    return far


def discordant_counts(a_results, b_results):
    """Discordant pair counts for two systems run on the same items.

    Returns (b, c): b is the number of items the first system passed and the
    second failed, c the reverse. Items where both agree carry no information
    about which system is better and are discarded.
    """
    if len(a_results) != len(b_results):
        raise ValueError("result sequences must be the same length")
    b = sum(1 for x, y in zip(a_results, b_results) if x and not y)
    c = sum(1 for x, y in zip(a_results, b_results) if y and not x)
    return b, c


def mcnemar_exact(b, c):
    """Two-sided exact McNemar test on discordant counts.

    Under the null, each discordant item is a fair coin flip, so the p-value is
    an exact binomial tail rather than a chi-square approximation. Use the exact
    form always: the approximation is unreliable at exactly the small discordant
    counts eval comparisons usually produce.

    Returns 1.0 when there are no discordant pairs — two systems that never
    differ provide no evidence that they differ.
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts cannot be negative")
    n = b + c
    if n == 0:
        return 1.0
    smaller = min(b, c)
    tail = sum(math.comb(n, i) for i in range(smaller + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def paired_bootstrap_diff(a_scores, b_scores, n_resamples=2000, confidence=0.95,
                          seed=None):
    """Bootstrap interval for the mean score difference between two systems.

    Use this where McNemar does not fit: ordinal rubric scores rather than
    binary pass/fail, on the same items for both systems.

    Resampling draws item *indices* and takes both systems' scores for each
    drawn item, so the pairing survives. Resampling the two systems
    independently would discard exactly the information that makes a paired
    design worth running.

    Returns mean_diff (mean of a minus mean of b), ci, and n. An interval that
    excludes zero is the paired equivalent of a significant difference.
    """
    if len(a_scores) != len(b_scores):
        raise ValueError("score sequences must be the same length")
    n = len(a_scores)
    if n < 2:
        raise ValueError("paired bootstrap needs at least two items")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1")

    differences = [a - b for a, b in zip(a_scores, b_scores)]
    observed = statistics.mean(differences)

    rng = random.Random(seed)
    estimates = []
    for _ in range(n_resamples):
        sample = [differences[rng.randrange(n)] for _ in range(n)]
        estimates.append(statistics.mean(sample))

    estimates.sort()
    tail = (1.0 - confidence) / 2.0
    low = estimates[int(tail * len(estimates))]
    high = estimates[min(len(estimates) - 1, int((1.0 - tail) * len(estimates)))]
    return {"mean_diff": observed, "ci": (low, high), "n": n}
