"""Classical test theory for eval item pools.

An eval is a test, and a test made of items nobody gets wrong measures nothing.
These functions answer the two questions Step 7 of the SOP asks: how hard is
each item, and does it separate stronger systems from weaker ones?

All functions take binary responses (1 = passed the item, 0 = failed).
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
