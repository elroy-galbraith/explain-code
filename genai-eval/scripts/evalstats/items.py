"""Classical test theory, and the matrix algebra behind it, for eval item pools.

An eval is a test, and a test made of items nobody gets wrong measures nothing.
This module has two halves.

The classical-test-theory half — `item_difficulty`, `point_biserial`,
`flag_items`, `kr20` — answers the two questions Step 7 of the SOP asks: how
hard is each item, and does it separate stronger systems from weaker ones?
These functions take binary responses (1 = passed the item, 0 = failed) and a
response matrix of one row per respondent, one column per item.

The matrix-algebra half — `correlation_matrix`, `eigenvalues_symmetric`,
`dimensionality` — supports Step 8's structural-validity check: do the items
behave like measurements of one thing? These functions take and return
matrices of floats (a correlation matrix or a general symmetric matrix), not
binary responses; `dimensionality` is the bridge, taking the same binary
response matrix as the first half and running it through `correlation_matrix`
and `eigenvalues_symmetric` to produce a scree summary.
"""

import math
import statistics

# An item whose point-biserial sits below this separates nothing useful.
DISCRIMINATION_FLOOR = 0.2
# Items passed or failed by nearly everyone carry almost no information.
CEILING = 0.95
FLOOR = 0.05


def item_difficulty(responses):
    """Proportion of respondents who passed this item.

    Confusingly, higher means *easier* — this is the classical p-value, and the
    convention is worth keeping because every psychometrics reference uses it.
    """
    if not responses:
        raise ValueError("no responses supplied")
    return sum(responses) / len(responses)


def point_biserial(responses, totals):
    """Point-biserial correlation between one item and total score.

    This is item discrimination: how well passing this item predicts doing well
    overall. Near zero means the item separates nobody. Negative means the item
    is mis-keyed or measures something the rest of the test does not — the
    highest-value finding in the whole procedure.

    Returns None rather than a number when the correlation is undefined: every
    response identical, or no variance in total scores.

    This is the uncorrected, item-total form: each item's own response is part
    of the `totals` it is being correlated against, rather than the
    corrected rest-score form that removes the item's own contribution first.
    Including the item in its own total inflates the correlation, and the
    inflation grows as the item count falls — it is largest on short pools,
    where a single item is a bigger share of the total. A caller who wants the
    corrected rest-score correlation should pass `totals` computed with each
    item's own contribution already subtracted out; this function does not do
    that subtraction itself.
    """
    if len(responses) != len(totals):
        raise ValueError("responses and totals must be the same length")
    if not responses:
        raise ValueError("no responses supplied")

    passed = [t for r, t in zip(responses, totals) if r == 1]
    failed = [t for r, t in zip(responses, totals) if r == 0]
    if not passed or not failed:
        return None

    spread = statistics.pstdev(totals)
    if spread == 0:
        return None

    p = len(passed) / len(responses)
    mean_gap = statistics.mean(passed) - statistics.mean(failed)
    return (mean_gap / spread) * math.sqrt(p * (1.0 - p))


def flag_items(matrix):
    """Difficulty, discrimination and flags for every item in a response matrix.

    `matrix` is one row per respondent, one column per item, entries 0 or 1.
    Returns one dict per item with keys index, difficulty, discrimination and
    flags. An empty flag list means the item is doing its job.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    width = len(matrix[0])
    if width == 0:
        raise ValueError("no items supplied")
    if any(len(row) != width for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    totals = [sum(row) for row in matrix]
    report = []
    for j in range(width):
        column = [row[j] for row in matrix]
        difficulty = item_difficulty(column)
        discrimination = point_biserial(column, totals)

        flags = []
        if difficulty >= CEILING:
            flags.append("ceiling")
        if difficulty <= FLOOR:
            flags.append("floor")
        if discrimination is None:
            flags.append("undefined")
        elif discrimination < 0:
            flags.append("mis-keyed")
        elif discrimination < DISCRIMINATION_FLOOR:
            flags.append("non-discriminating")

        report.append(
            {
                "index": j,
                "difficulty": difficulty,
                "discrimination": discrimination,
                "flags": flags,
            }
        )
    return report


def kr20(matrix):
    """Kuder-Richardson 20 — internal-consistency reliability for binary items.

    Answers "if I built a second eval from the same item pool, how much would
    the scores agree?". Low reliability caps every comparison you can make: an
    instrument that disagrees with itself cannot detect a difference between two
    models.

    Uses the *population* variance of total scores (divisor N), which is the
    classical KR-20 form. Sample variance produces a slightly higher number, and
    mixing the two silently across a codebase is a real source of irreproducible
    reliability figures.

    Returns None when total-score variance is zero, since reliability is
    undefined rather than zero when nobody differs.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    n_items = len(matrix[0])
    if n_items < 2:
        raise ValueError("KR-20 needs at least two items")
    if any(len(row) != n_items for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    totals = [sum(row) for row in matrix]
    total_variance = statistics.pvariance(totals)
    if total_variance == 0:
        return None

    item_variance_sum = 0.0
    for j in range(n_items):
        column = [row[j] for row in matrix]
        p = sum(column) / len(column)
        item_variance_sum += p * (1.0 - p)

    return (n_items / (n_items - 1)) * (1.0 - item_variance_sum / total_variance)


def eigenvalues_symmetric(matrix, max_sweeps=100, tol=1e-12):
    """Eigenvalues of a real symmetric matrix, descending, via Jacobi rotation.

    Jacobi is slow for large matrices and perfectly adequate here: item pools
    have tens of items, not thousands, and it needs nothing but the standard
    library.
    """
    n = len(matrix)
    if n == 0:
        raise ValueError("empty matrix")
    if any(len(row) != n for row in matrix):
        raise ValueError("matrix must be square")
    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j] - matrix[j][i]) > 1e-9:
                raise ValueError("matrix must be symmetric")

    a = [list(map(float, row)) for row in matrix]

    for _ in range(max_sweeps):
        off_diagonal = math.sqrt(
            sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        )
        if off_diagonal < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < tol:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                sign = 1.0 if theta >= 0 else -1.0
                t = sign / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk

    return sorted((a[i][i] for i in range(n)), reverse=True)


def correlation_matrix(matrix):
    """Item-by-item Pearson correlation matrix from a response matrix.

    An item with zero variance correlates with nothing, so its row and column
    are zero apart from a 1.0 on the diagonal. That keeps the matrix square and
    symmetric instead of propagating a division by zero.
    """
    if not matrix:
        raise ValueError("no respondents supplied")
    n_items = len(matrix[0])
    if any(len(row) != n_items for row in matrix):
        raise ValueError("every respondent must answer the same number of items")

    columns = [[row[j] for row in matrix] for j in range(n_items)]
    means = [statistics.mean(c) for c in columns]
    spreads = [statistics.pstdev(c) for c in columns]

    result = [[0.0] * n_items for _ in range(n_items)]
    for i in range(n_items):
        result[i][i] = 1.0
        for j in range(i + 1, n_items):
            if spreads[i] == 0 or spreads[j] == 0:
                continue
            covariance = sum(
                (x - means[i]) * (y - means[j])
                for x, y in zip(columns[i], columns[j])
            ) / len(matrix)
            r = covariance / (spreads[i] * spreads[j])
            result[i][j] = result[j][i] = r
    return result


def dimensionality(matrix):
    """Eigenvalue summary of a response matrix's item correlation structure.

    Gate 8's internal-structure category asks whether the items behave like
    measurements of one thing. A first component carrying most of the variance
    with everything else below 1.0 is consistent with that; several components
    above 1.0 says the eval is measuring more than one construct and the single
    headline score is hiding it.

    This is a scree summary, not factor analysis. Real factor analysis needs
    numpy and is out of scope for this package.
    """
    correlations = correlation_matrix(matrix)
    values = eigenvalues_symmetric(correlations)
    total = sum(values)
    return {
        "eigenvalues": values,
        "first_ratio": (values[0] / total) if total > 0 else None,
        "n_above_one": sum(1 for v in values if v > 1.0),
    }
