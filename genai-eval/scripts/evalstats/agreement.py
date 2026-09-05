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
