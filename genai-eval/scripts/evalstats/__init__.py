"""evalstats — stdlib-only measurement statistics for GenAI evaluation.

No I/O, no printing, no formatting. Every function computes a number or raises.

How this package signals "undefined"
------------------------------------
Raises ValueError   structurally invalid input: empty, length mismatch, ragged
                    rows, fewer than two categories, a rating outside the
                    stated categories, n_resamples below 1, a proportion
                    outside (0, 1), no pairable unit, or every rating
                    identical (krippendorff_alpha, cohens_kappa,
                    weighted_kappa, fleiss_kappa — chance-corrected agreement
                    is undefined when nothing varies).
Raises TypeError    interval-level ratings that are not numbers.
Returns None        mathematically undefined but structurally fine:
                    point_biserial and kr20 on zero variance,
                    rank_correlation on a constant sequence,
                    length_bias["gap"] when either side is constant,
                    self_preference["delta"] with an empty group,
                    mde_two_proportion when nothing is detectable at that n,
                    dimensionality["first_ratio"] on a zero total.

Nothing in this package returns a number it cannot justify. A caller that sees
None must say so in its output rather than substituting zero.
"""

from . import agreement, bias, items, power, saturation

__all__ = ["agreement", "bias", "items", "power", "saturation"]
