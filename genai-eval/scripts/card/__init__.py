"""card — the eval card, and the gates a script can actually check.

The design commitment this package exists to serve: a gate that cannot be
checked mechanically will be rubber-stamped. Six of the SOP's eleven gates are
answerable from the card and its item pool, so they are answered here rather
than asked of a model.

    loader.py   read a card, resolve its paths, validate its structure
    gates.py    one function per mechanical gate
"""

from . import loader

__all__ = ["loader"]
