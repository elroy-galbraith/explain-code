"""Inter-rater agreement statistics.

Every function here answers one question: how much of the observed agreement
between raters is more than you would get by chance? A judge that agrees with a
human 90% of the time on a task where 88% of items get the same label is not a
good judge, and only a chance-corrected statistic shows that.
"""

import random


def scale_order(categories, observed):
    """The stated scale order, checked against the ratings actually present.

    Shared by every statistic that accepts a `categories` argument, because
    each of them builds the same index from it and each of them is wrong in
    the same two ways without these checks.

    A repeated value is rejected by name. The index built from the list keeps
    only a duplicate's last position, so `low,medium,high,low` silently makes
    `low` the top of the scale — a trailing paste-typo that returns a
    plausible number rather than an error.

    A rating outside the list is rejected too: there is no position on the
    stated scale to give it, and guessing one is how a confident wrong answer
    gets made.
    """
    scale = list(categories)

    seen = set()
    repeated = []
    for value in scale:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    if repeated:
        raise ValueError(
            "categories repeats %s; a repeated value takes its last position "
            "in the scale order, which silently ranks the earlier one wrong"
            % ", ".join(str(v) for v in repeated)
        )

    unknown = set(observed) - seen
    if unknown:
        raise ValueError(
            "ratings not present in the supplied categories: %s"
            % ", ".join(sorted(str(v) for v in unknown))
        )
    return scale


def cohens_kappa(a, b):
    """Cohen's kappa for two raters on nominal categories.

    `a` and `b` are parallel sequences of labels, one entry per item. Labels may
    be any hashable, comparable-by-str value.

    Raises ValueError on length mismatch, empty input, or when expected
    agreement is exactly 1.0 (both raters used a single category, so kappa is
    undefined rather than zero).
    """
    if len(a) != len(b):
        raise ValueError("rater sequences must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("no ratings supplied")

    categories = sorted(set(a) | set(b), key=str)
    index = {c: i for i, c in enumerate(categories)}
    k = len(categories)

    observed = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1

    p_o = sum(observed[i][i] for i in range(k)) / n
    rows = [sum(observed[i]) for i in range(k)]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    p_e = sum(rows[i] * cols[i] for i in range(k)) / (n * n)

    if p_e == 1.0:
        raise ValueError(
            "expected agreement is 1.0 (only one category in use); kappa is undefined"
        )
    return (p_o - p_e) / (1.0 - p_e)


def weighted_kappa(a, b, weights="linear", categories=None):
    """Weighted kappa for two raters on an ordinal scale.

    Most rubrics are ordinal (1-5, or 1/2/3/4 for fail/weak/adequate/strong),
    and unweighted kappa treats a 4-vs-5 disagreement as harshly as a 1-vs-5.
    Weighted kappa gives partial credit for near-misses.

    By default categories are ordered by natural sort, so all labels must be
    mutually comparable. `weights` is "linear" (credit falls off with
    distance) or "quadratic" (credit falls off with squared distance, so
    near-misses are forgiven more and far-misses punished about the same).

    CAVEAT: scale order needs to be stated for word labels. By default order
    comes from sorting the rating values, which is right for 1/2/3/4 and
    wrong for words — sorted({"fail", "weak", "adequate", "strong"}) puts
    "adequate" first and "weak" last, which is not the rubric's order, and
    the function returns a confident, wrong number with no warning. Pass
    `categories` to state the order explicitly:
    weighted_kappa(a, b, categories=["fail", "weak", "adequate", "strong"]).
    Any rating not in that list raises.

    Raises ValueError on length mismatch, empty input, fewer than two distinct
    categories, an unknown weighting, or a rating outside the supplied
    `categories`.
    """
    if weights not in ("linear", "quadratic"):
        raise ValueError("weights must be 'linear' or 'quadratic'")
    if len(a) != len(b):
        raise ValueError("rater sequences must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("no ratings supplied")

    observed = set(a) | set(b)
    if categories is None:
        scale = sorted(observed)
    else:
        scale = scale_order(categories, observed)
    k = len(scale)
    if k < 2:
        raise ValueError(
            "weighted kappa needs at least two distinct categories; only one in use"
        )
    index = {c: i for i, c in enumerate(scale)}

    def weight(i, j):
        d = abs(i - j) / (k - 1)
        return 1.0 - d if weights == "linear" else 1.0 - d * d

    observed = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[index[x]][index[y]] += 1

    rows = [sum(observed[i]) for i in range(k)]
    cols = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    p_o = sum(
        weight(i, j) * observed[i][j] for i in range(k) for j in range(k)
    ) / n
    p_e = sum(
        weight(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k)
    ) / (n * n)

    if p_e == 1.0:
        raise ValueError("expected agreement is 1.0; weighted kappa is undefined")
    return (p_o - p_e) / (1.0 - p_e)


def fleiss_kappa(counts):
    """Fleiss' kappa for a fixed number of raters per item.

    `counts` is one row per item giving how many raters chose each category, so
    `[[3, 0], [2, 1]]` means three raters picked category 0 for item 1, and two
    picked category 0 with one picking category 1 for item 2.

    Unlike Cohen's kappa this does not require the same raters on every item,
    only the same *number* of raters. Use krippendorff_alpha when even that does
    not hold.

    Raises ValueError on ragged rows, fewer than two raters, no items, or when
    expected agreement is exactly 1.0.
    """
    if not counts:
        raise ValueError("no items supplied")
    n_raters = sum(counts[0])
    if n_raters < 2:
        raise ValueError("Fleiss' kappa needs at least two raters per item")
    if any(sum(row) != n_raters for row in counts):
        raise ValueError(
            "every item must have the same number of ratings; use "
            "krippendorff_alpha for ragged or missing data"
        )
    if any(len(row) != len(counts[0]) for row in counts):
        raise ValueError(
            "every item must report counts for the same number of "
            "categories; a matching rating total does not mean the rows "
            "are the same shape"
        )

    n_items = len(counts)
    n_categories = len(counts[0])

    agreements = [
        (sum(c * c for c in row) - n_raters) / (n_raters * (n_raters - 1))
        for row in counts
    ]
    p_bar = sum(agreements) / n_items

    proportions = [
        sum(row[j] for row in counts) / (n_items * n_raters)
        for j in range(n_categories)
    ]
    p_e = sum(p * p for p in proportions)

    if p_e == 1.0:
        raise ValueError("expected agreement is 1.0; kappa is undefined")
    return (p_bar - p_e) / (1.0 - p_e)


def _coincidence(units, categories=None):
    """Build Krippendorff's coincidence matrix from per-unit rating lists.

    Returns (matrix, values, marginals, total). Each unit contributes every
    ordered pair of its present ratings, weighted 1/(m-1) where m is how many
    ratings that unit actually has. That weighting is what lets units with
    different numbers of raters sit in the same matrix.

    `categories`, when given, is the authoritative scale order; a repeated
    value in it, or any observed rating outside it, raises ValueError. When
    None, order comes from sorting the observed values, as before.
    """
    present = [[v for v in unit if v is not None] for unit in units]
    pairable = [unit for unit in present if len(unit) >= 2]
    if not pairable:
        raise ValueError(
            "no unit has two or more ratings; alpha needs at least one pairable unit"
        )

    observed = {v for unit in pairable for v in unit}
    if categories is None:
        values = sorted(observed)
    else:
        values = scale_order(categories, observed)
    index = {v: i for i, v in enumerate(values)}
    k = len(values)

    matrix = [[0.0] * k for _ in range(k)]
    for unit in pairable:
        m = len(unit)
        weight = 1.0 / (m - 1)
        for i, x in enumerate(unit):
            for j, y in enumerate(unit):
                if i != j:
                    matrix[index[x]][index[y]] += weight

    marginals = [sum(row) for row in matrix]
    total = sum(marginals)
    return matrix, values, marginals, total


def _nominal_metric(values, marginals):
    """Squared difference for unordered categories: 0 if equal, 1 if not."""

    def delta(i, j):
        return 0.0 if i == j else 1.0

    return delta


def _interval_metric(values, marginals):
    """Squared numeric distance. Requires values to be numbers."""
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise TypeError(
                "the interval metric needs numeric ratings; got %r" % (v,)
            )

    def delta(i, j):
        d = values[i] - values[j]
        return float(d * d)

    return delta


def _ordinal_metric(values, marginals):
    """Krippendorff's ordinal metric.

    The distance between two ranks depends on how many observations sit between
    them: the squared sum of the marginals spanning the interval, less half of
    each endpoint. Two adjacent categories are far apart if the scale is
    crowded there and close together if it is sparse, which is the behaviour an
    ordinal rubric actually has.
    """
    cumulative = []
    running = 0.0
    for m in marginals:
        running += m
        cumulative.append(running)

    def delta(i, j):
        if i == j:
            return 0.0
        lo, hi = (i, j) if i < j else (j, i)
        span = cumulative[hi] - (cumulative[lo] - marginals[lo])
        adjusted = span - (marginals[lo] + marginals[hi]) / 2.0
        return adjusted * adjusted

    return delta


_METRICS = {
    "nominal": _nominal_metric,
    "ordinal": _ordinal_metric,
    "interval": _interval_metric,
}


def krippendorff_alpha(units, level="nominal", categories=None):
    """Krippendorff's alpha — chance-corrected agreement for any number of raters.

    `units` is one list per item holding that item's ratings, using None for a
    rating that is absent. Units with fewer than two present ratings are dropped
    because they carry no pairable information.

    `level` selects the difference function: "nominal" for unordered categories,
    "ordinal" for ranked categories, "interval" for numeric ratings.

    CAVEAT: ordinal and interval levels need a scale order. By default that
    order comes from sorting the rating values, which is right for 1/2/3 and
    wrong for word labels — sorted(["low", "medium", "high"]) is
    ["high", "low", "medium"], and the resulting alpha is confidently wrong
    rather than an error. Pass `categories` to state the order explicitly:
    krippendorff_alpha(units, level="ordinal", categories=["low", "medium", "high"]).
    Any rating not in that list raises.

    Raises ValueError when no unit is pairable, the level is unknown, or every
    rating in the pairable data is identical — matching cohens_kappa,
    weighted_kappa and fleiss_kappa, which already raise on single-category
    input instead of returning a number for an undefined statistic.
    """
    if level not in _METRICS:
        raise ValueError(
            "level must be one of %s" % ", ".join(sorted(_METRICS))
        )

    matrix, values, marginals, total = _coincidence(units, categories)
    delta = _METRICS[level](values, marginals)
    k = len(values)

    observed = sum(
        matrix[i][j] * delta(i, j) for i in range(k) for j in range(k)
    ) / total
    expected = sum(
        marginals[i] * marginals[j] * delta(i, j)
        for i in range(k)
        for j in range(k)
    ) / (total * (total - 1))

    if expected == 0.0:
        raise ValueError(
            "every rating in the pairable data is identical, so expected "
            "disagreement is zero and alpha is undefined; chance-corrected "
            "agreement has no meaning when chance has no variance to correct"
        )
    return 1.0 - observed / expected


def bootstrap_ci(units, statistic, n_resamples=2000, confidence=0.95, seed=None):
    """Percentile bootstrap confidence interval for a unit-level statistic.

    `units` is the same per-item structure the agreement functions take, and
    `statistic` is any callable mapping a list of units to a float.

    Resampling is by *unit*, not by individual rating. Ratings cluster within an
    item — two raters looking at the same hard item disagree together — so
    resampling ratings independently breaks that dependence and produces
    intervals that are far too narrow.

    Resamples on which `statistic` raises ValueError are skipped, since a
    resample can legitimately contain a single category. If more than half of
    them fail, that is not a skippable edge case and this raises rather than
    returning an interval computed from the survivors.
    """
    n = len(units)
    if n < 2:
        raise ValueError("bootstrap needs at least two units")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1")

    rng = random.Random(seed)
    estimates = []
    for _ in range(n_resamples):
        sample = [units[rng.randrange(n)] for _ in range(n)]
        try:
            estimates.append(statistic(sample))
        except ValueError:
            continue

    if len(estimates) < n_resamples / 2:
        raise ValueError(
            "%d of %d resamples were degenerate; the sample is too small or too "
            "homogeneous for a bootstrap interval" % (n_resamples - len(estimates), n_resamples)
        )

    estimates.sort()
    tail = (1.0 - confidence) / 2.0
    low_index = int(tail * len(estimates))
    high_index = min(len(estimates) - 1, int((1.0 - tail) * len(estimates)))
    return estimates[low_index], estimates[high_index]
