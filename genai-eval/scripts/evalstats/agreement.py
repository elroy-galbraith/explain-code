"""Inter-rater agreement statistics.

Every function here answers one question: how much of the observed agreement
between raters is more than you would get by chance? A judge that agrees with a
human 90% of the time on a task where 88% of items get the same label is not a
good judge, and only a chance-corrected statistic shows that.
"""


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


def weighted_kappa(a, b, weights="linear"):
    """Weighted kappa for two raters on an ordinal scale.

    Most rubrics are ordinal (1-5, or fail/weak/adequate/strong), and unweighted
    kappa treats a 4-vs-5 disagreement as harshly as a 1-vs-5. Weighted kappa
    gives partial credit for near-misses.

    Categories are ordered by natural sort, so all labels must be mutually
    comparable. `weights` is "linear" (credit falls off with distance) or
    "quadratic" (credit falls off with squared distance, so near-misses are
    forgiven more and far-misses punished about the same).

    Raises ValueError on length mismatch, empty input, fewer than two distinct
    categories, or an unknown weighting.
    """
    if weights not in ("linear", "quadratic"):
        raise ValueError("weights must be 'linear' or 'quadratic'")
    if len(a) != len(b):
        raise ValueError("rater sequences must be the same length")
    n = len(a)
    if n == 0:
        raise ValueError("no ratings supplied")

    categories = sorted(set(a) | set(b))
    k = len(categories)
    if k < 2:
        raise ValueError(
            "weighted kappa needs at least two distinct categories; only one in use"
        )
    index = {c: i for i, c in enumerate(categories)}

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


def _coincidence(units):
    """Build Krippendorff's coincidence matrix from per-unit rating lists.

    Returns (matrix, values, marginals, total). Each unit contributes every
    ordered pair of its present ratings, weighted 1/(m-1) where m is how many
    ratings that unit actually has. That weighting is what lets units with
    different numbers of raters sit in the same matrix.
    """
    present = [[v for v in unit if v is not None] for unit in units]
    pairable = [unit for unit in present if len(unit) >= 2]
    if not pairable:
        raise ValueError(
            "no unit has two or more ratings; alpha needs at least one pairable unit"
        )

    values = sorted({v for unit in pairable for v in unit})
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


_METRICS = {"nominal": _nominal_metric}


def krippendorff_alpha(units, level="nominal"):
    """Krippendorff's alpha — chance-corrected agreement for any number of raters.

    `units` is one list per item holding that item's ratings, using None for a
    rating that is absent. Units with fewer than two present ratings are dropped
    because they carry no pairable information.

    `level` selects the difference function: "nominal" for unordered categories.
    Later tasks add "ordinal" and "interval".

    Returns 1.0 when expected disagreement is zero, which happens when every
    rating in the data is identical — agreement is perfect and the chance
    correction has nothing to correct.

    Raises ValueError when no unit is pairable or the level is unknown.
    """
    if level not in _METRICS:
        raise ValueError(
            "level must be one of %s" % ", ".join(sorted(_METRICS))
        )

    matrix, values, marginals, total = _coincidence(units)
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
        return 1.0
    return 1.0 - observed / expected
