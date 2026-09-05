"""Read an eval card and check that it is structurally a card at all.

A finding from this module carries `gate=None`. A malformed card has not failed
a gate — it is a card the gates cannot be run against, and saying "Gate 4
failed" about a file missing its `claims` block would send someone looking in
the wrong place.
"""

import json
import os
from dataclasses import dataclass

SCHEMA_VERSIONS = (1,)
TIERS = (1, 2, 3)
STATUSES = ("draft", "designed", "sealed", "qualified", "retired")

REQUIRED_BLOCKS = (
    "schema_version", "tier", "decision", "domain", "constructs", "claims",
    "evidence_model", "task_model", "items", "grader", "preregistration",
)

# Blocks whose gates iterate their contents. Membership in REQUIRED_BLOCKS
# only tests presence, and `"constructs": []` is present — so without this
# separate check, an empty array would satisfy the structural check and then
# make Gates 2, 3, and 4 pass vacuously (their per-entry loops just run zero
# times). A card with none of these describes no evaluation at all.
NON_EMPTY_BLOCKS = ("constructs", "claims")


@dataclass
class Finding:
    """One problem with one card. `gate` is None for structural problems."""

    level: str
    path: str
    message: str
    gate: int = None

    def render(self):
        label = "structure" if self.gate is None else "Gate %d" % self.gate
        return "%s [%s] %s: %s" % (self.level.upper(), label, self.path, self.message)


def resolve(card_path, relative):
    """Resolve a path found inside a card, against the card's own directory.

    Cards and their item pools travel together. Resolving against the process's
    working directory would break the moment anyone validated a card from
    anywhere but its own folder.
    """
    if os.path.isabs(relative):
        return relative
    return os.path.join(os.path.dirname(os.path.abspath(card_path)), relative)


def load_card(path):
    """Parse a card and check its shape. Returns (card, findings)."""
    if not os.path.isfile(path):
        raise ValueError("no such card: %s" % path)
    try:
        with open(path, encoding="utf-8") as handle:
            card = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("%s is not readable JSON: %s" % (path, exc))

    if not isinstance(card, dict):
        raise ValueError(
            "%s parsed as %s; an eval card must be a JSON object"
            % (path, type(card).__name__)
        )

    findings = []
    for block in REQUIRED_BLOCKS:
        if block not in card:
            findings.append(Finding("error", block, "required block is missing"))

    for block in NON_EMPTY_BLOCKS:
        value = card.get(block)
        if isinstance(value, list) and not value:
            findings.append(Finding(
                "error", block,
                "%s is present but empty. A card with none describes no "
                "evaluation, and the gates that read this block would pass "
                "over it vacuously — their checks iterate this list." % block,
            ))

    version = card.get("schema_version")
    if version is not None and version not in SCHEMA_VERSIONS:
        findings.append(Finding(
            "error", "schema_version",
            "unknown schema version %r; this validator understands %s"
            % (version, ", ".join(str(v) for v in SCHEMA_VERSIONS)),
        ))

    tier = card.get("tier")
    if tier is not None and tier not in TIERS:
        findings.append(Finding(
            "error", "tier", "tier must be 1, 2 or 3; got %r" % (tier,)))

    status = card.get("status")
    if status is not None and status not in STATUSES:
        findings.append(Finding(
            "error", "status",
            "unknown status %r; expected one of %s" % (status, ", ".join(STATUSES)),
        ))

    return card, findings
