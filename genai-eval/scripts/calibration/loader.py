"""Read a labels CSV into the structure the analysis needs.

The minimum contract is two columns: one judge score and one human label per
row. Everything else is optional and unlocks part of the analysis, so this
module's real job is not parsing — it is saying plainly what it found and what
each absence costs. Those statements travel in `notes` and the report prints
them verbatim, because a reader who does not know the agreement ceiling was
unavailable will read the judge's score as if it had one.
"""

import csv
from dataclasses import dataclass, field
from typing import Optional

# Name fragments, checked case-insensitively against each column. Order matters
# within a role: the first fragment that matches wins.
JUDGE_HINTS = ("judge", "llm", "model_score", "auto", "ai_")
HUMAN_HINTS = ("human", "gold", "expert", "annotator", "rater", "label")
ITEM_HINTS = ("item_id", "item", "id", "example", "sample")
LENGTH_HINTS = ("length", "chars", "tokens", "len", "words")
GENERATOR_HINTS = ("generator", "system", "model_name", "produced_by")


@dataclass
class CalibrationData:
    """One labels file, parsed and described."""

    judge_column: str
    judge_scores: list
    human_columns: dict
    n: int
    numeric: dict = field(default_factory=dict)
    item_ids: Optional[list] = None
    lengths: Optional[list] = None
    generators: Optional[list] = None
    notes: list = field(default_factory=list)

    @property
    def human_rater_count(self):
        return len(self.human_columns)


def _matches(column, hints):
    lowered = column.lower()
    return any(hint in lowered for hint in hints)


def detect_columns(fieldnames):
    """Guess each column's role from its name.

    Returns a dict with keys judge, humans, item_id, length, generator. A role
    with no match is None (or an empty list for humans) rather than a guess —
    the caller reports the absence instead of proceeding on a hunch.

    Each column is claimed at most once. Judge is resolved first because it is
    the one column the analysis cannot proceed without, so a name like
    `human_judge` counts as the judge rather than as a rater.
    """
    remaining = list(fieldnames)

    judge = next((c for c in remaining if _matches(c, JUDGE_HINTS)), None)
    if judge is not None:
        remaining.remove(judge)

    humans = [c for c in remaining if _matches(c, HUMAN_HINTS)]
    for column in humans:
        remaining.remove(column)

    def claim(hints):
        found = next((c for c in remaining if _matches(c, hints)), None)
        if found is not None:
            remaining.remove(found)
        return found

    return {
        "judge": judge,
        "humans": humans,
        "item_id": claim(ITEM_HINTS),
        "length": claim(LENGTH_HINTS),
        "generator": claim(GENERATOR_HINTS),
    }


def _coerce(values):
    """Convert a column to floats, or leave it entirely as text.

    All-or-nothing per column: a column holding 4, 5 and "n/a" becomes text,
    because a list mixing floats and strings breaks every statistic downstream
    in a way that surfaces far from here. Blank cells become None and do not
    block coercion — Krippendorff's alpha handles missing ratings natively.
    """
    present = [v for v in values if v not in ("", None)]
    try:
        floats = [float(v) for v in present]
    except (TypeError, ValueError):
        return [None if v in ("", None) else v for v in values], False

    numbers = iter(floats)
    return [None if v in ("", None) else next(numbers) for v in values], True


def load_labels(path, judge=None, humans=None, item_id=None, length=None,
                generator=None):
    """Read `path` into a CalibrationData.

    Any of the column arguments overrides detection for that role. A named
    column that is not in the file raises rather than falling back to a guess.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not fieldnames:
        raise ValueError("%s has no header row" % path)
    if not rows:
        raise ValueError("%s has a header but no data rows" % path)
    for number, row in enumerate(rows, start=2):
        if any(value is None for value in row.values()) or None in row:
            raise ValueError(
                "%s line %d has a different number of fields than the header"
                % (path, number)
            )

    detected = detect_columns(fieldnames)

    def resolve(explicit, role, fallback):
        if explicit is None:
            return fallback
        names = explicit if isinstance(explicit, list) else [explicit]
        missing = [n for n in names if n not in fieldnames]
        if missing:
            raise ValueError(
                "column(s) named for %s not in %s: %s"
                % (role, path, ", ".join(missing))
            )
        return explicit

    judge_column = resolve(judge, "the judge", detected["judge"])
    human_names = resolve(humans, "human raters", detected["humans"])
    item_column = resolve(item_id, "item ids", detected["item_id"])
    length_column = resolve(length, "response length", detected["length"])
    generator_column = resolve(generator, "the generator", detected["generator"])

    if judge_column is None:
        raise ValueError(
            "no judge column found in %s (looked for a name containing %s); "
            "name one explicitly" % (path, ", ".join(JUDGE_HINTS))
        )
    if not human_names:
        raise ValueError(
            "no human label column found in %s (looked for a name containing "
            "%s); name one explicitly" % (path, ", ".join(HUMAN_HINTS))
        )

    guessed = []
    if judge is None:
        guessed.append("%s → judge score" % judge_column)
    if humans is None:
        guessed.append("%s → human rater" % ", ".join(human_names))
    if item_id is None and item_column is not None:
        guessed.append("%s → item id" % item_column)
    if length is None and length_column is not None:
        guessed.append("%s → response length" % length_column)
    if generator is None and generator_column is not None:
        guessed.append("%s → generator" % generator_column)

    def column(name):
        return [row[name] for row in rows]

    numeric = {}
    judge_scores, numeric[judge_column] = _coerce(column(judge_column))

    human_columns = {}
    for name in human_names:
        human_columns[name], numeric[name] = _coerce(column(name))

    lengths = None
    if length_column is not None:
        lengths, numeric[length_column] = _coerce(column(length_column))

    notes = []
    if guessed:
        notes.append(
            "Columns matched by name rather than stated explicitly: %s. A wrong "
            "match here produces a confident number from the wrong data — name "
            "the column explicitly if any of these is not what you meant."
            % "; ".join(guessed)
        )
    if len(human_names) < 2:
        notes.append(
            "Only one human rater column was found, so there is no "
            "human-human agreement ceiling. Judge-human agreement cannot be "
            "compared against anything, and Gate 6 cannot be answered."
        )
    if item_column is None:
        notes.append(
            "No item id column, so bootstrap resampling cannot be clustered "
            "by item and disagreements cannot be listed by id."
        )
    if length_column is None:
        notes.append("No response length column, so the length-bias probe is unavailable.")
    if generator_column is None:
        notes.append(
            "No generator column, so the self-preference probe is unavailable."
        )

    return CalibrationData(
        judge_column=judge_column,
        judge_scores=judge_scores,
        human_columns=human_columns,
        n=len(rows),
        numeric=numeric,
        item_ids=column(item_column) if item_column else None,
        lengths=lengths,
        generators=column(generator_column) if generator_column else None,
        notes=notes,
    )
