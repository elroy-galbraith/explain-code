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
