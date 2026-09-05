"""One function per mechanical gate.

Each takes a card (some also its path) and returns a list of Findings — never
raises, never prints, never stops at the first problem. A gate that dies on the
first fault makes someone fix a card one error per run.

Gates 6, 7, 8, 10 and 11 need a qualification block that nothing writes yet;
they arrive with card mode. The registry at the bottom is the seam.
"""

from .loader import Finding

REQUIRED_OUTCOMES = ("pass", "fail", "borderline")


def _blank(value):
    return not isinstance(value, str) or not value.strip()


def _nonempty_strings(value):
    return isinstance(value, list) and any(
        isinstance(entry, str) and entry.strip() for entry in value
    )


def gate_1_decision(card):
    """Gate 1: is there a named decision-owner and an action for every outcome?

    Without both, the eval is a vanity metric: it will be optimised against and
    then ignored, because nobody was ever going to do anything different on any
    of its results.
    """
    findings = []
    decision = card.get("decision") or {}

    if _blank(decision.get("owner")):
        findings.append(Finding(
            "error", "decision.owner",
            "no named decision-owner; an eval nobody owns is a vanity metric",
            gate=1,
        ))

    outcomes = decision.get("outcomes") or []
    seen = {o.get("result") for o in outcomes if isinstance(o, dict)}
    for required in REQUIRED_OUTCOMES:
        if required not in seen:
            findings.append(Finding(
                "error", "decision.outcomes",
                "no action recorded for the %r outcome" % required,
                gate=1,
            ))

    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict) or _blank(outcome.get("action")):
            findings.append(Finding(
                "error", "decision.outcomes[%d].action" % index,
                "outcome %r has no action" % (
                    outcome.get("result") if isinstance(outcome, dict) else outcome,),
                gate=1,
            ))

    return findings


def gate_3_falsifiable(card):
    """Gate 3: can you state what output would count as evidence *against* the
    construct?

    If not, the construct is not falsifiable and no result can disconfirm it —
    which means every result confirms it, which means it measures nothing.
    """
    findings = []
    for index, construct in enumerate(card.get("constructs") or []):
        if not _nonempty_strings(construct.get("negative_evidence")):
            findings.append(Finding(
                "error", "constructs[%d].negative_evidence" % index,
                "construct %r states nothing that would count against it, so no "
                "result can disconfirm it" % construct.get("id"),
                gate=3,
            ))
    return findings


# (gate number, callable, needs_card_path). Gates 4, 5 and 9 join in later tasks.
ALL = [
    (1, gate_1_decision, False),
    (3, gate_3_falsifiable, False),
]
