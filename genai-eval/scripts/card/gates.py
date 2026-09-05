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


def _objects(value):
    """The dict entries of a list, ignoring anything else.

    The loader reports a non-object entry as a structural finding, but it
    returns findings rather than raising, so a caller may still run the gates
    over a card it has already complained about. A gate that crashed there
    would take the whole report down with it — and this module's contract is
    that a gate never raises.
    """
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _mapping(value):
    """A block as a dict, or an empty one if the card put something else there.

    Same reason as `_objects`: the loader reports the wrong shape, but it
    returns findings instead of raising, so the gates still run over the card
    and must not die reaching into it.
    """
    return value if isinstance(value, dict) else {}


def gate_1_decision(card):
    """Gate 1: is there a named decision-owner and an action for every outcome?

    Without both, the eval is a vanity metric: it will be optimised against and
    then ignored, because nobody was ever going to do anything different on any
    of its results.
    """
    findings = []
    decision = _mapping(card.get("decision"))

    if _blank(decision.get("owner")):
        findings.append(Finding(
            "error", "decision.owner",
            "no named decision-owner; an eval nobody owns is a vanity metric",
            gate=1,
        ))

    outcomes = decision.get("outcomes") or []
    seen = {o.get("result") for o in _objects(outcomes)}
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


def gate_2_harm_pathways(card):
    """Gate 2: is each measure traceable to a ranked harm pathway?

    Without the trace you measure what is easy rather than what matters. The
    *ranking* is what makes the trace mean something — an unranked list
    justifies measuring any pathway on it equally.
    """
    findings = []
    raw = _mapping(card.get("domain")).get("harm_pathways")
    pathways = raw if isinstance(raw, list) else []
    by_id = {p.get("id"): p for p in pathways if isinstance(p, dict)}

    ranks = []
    for index, pathway in enumerate(pathways):
        rank = pathway.get("rank") if isinstance(pathway, dict) else None
        if not isinstance(rank, int) or isinstance(rank, bool):
            findings.append(Finding(
                "error", "domain.harm_pathways[%d].rank" % index,
                "pathway %r has no integer rank, so nothing distinguishes it "
                "from any other" % (pathway.get("id") if isinstance(pathway, dict) else pathway,),
                gate=2,
            ))
        else:
            ranks.append((rank, index))

    seen_ranks = {}
    for rank, index in ranks:
        if rank in seen_ranks:
            findings.append(Finding(
                "error", "domain.harm_pathways[%d].rank" % index,
                "rank %d is already used by pathway %d; duplicate ranks are not "
                "a ranking" % (rank, seen_ranks[rank]),
                gate=2,
            ))
        else:
            seen_ranks[rank] = index

    referenced = set()
    for index, construct in enumerate(card.get("constructs") or []):
        if not isinstance(construct, dict):
            continue
        listed = construct.get("harm_pathways")
        listed = listed if isinstance(listed, list) else []
        if not listed:
            findings.append(Finding(
                "error", "constructs[%d].harm_pathways" % index,
                "construct %r traces to no harm pathway" % construct.get("id"),
                gate=2,
            ))
        for reference in listed:
            referenced.add(reference)
            if reference not in by_id:
                findings.append(Finding(
                    "error", "constructs[%d].harm_pathways" % index,
                    "construct %r references unknown pathway %r"
                    % (construct.get("id"), reference),
                    gate=2,
                ))

    for index, pathway in enumerate(pathways):
        identifier = pathway.get("id") if isinstance(pathway, dict) else None
        if identifier is not None and identifier not in referenced:
            findings.append(Finding(
                "warning", "domain.harm_pathways[%d]" % index,
                "pathway %r is ranked but no construct measures it" % identifier,
                gate=2,
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
        if not isinstance(construct, dict):
            continue
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
    (2, gate_2_harm_pathways, False),
    (3, gate_3_falsifiable, False),
]
