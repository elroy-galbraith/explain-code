"""One function per mechanical gate.

Each takes a card (some also its path) and returns a list of Findings — never
raises, never prints, never stops at the first problem. A gate that dies on the
first fault makes someone fix a card one error per run.

Gates 6, 7, 8, 10 and 11 need a qualification block that nothing writes yet;
they arrive with card mode. The registry at the bottom is the seam.
"""

import datetime
import hashlib
import json

from .loader import Finding, resolve

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


def _sequence(value):
    """A block as a list, or an empty one if the card put something else there.

    `card.get(block) or []` looks like it guards this and does not: a truthy
    non-list passes straight through and `enumerate` raises on it. Same reason
    as `_mapping` — the loader reports the wrong shape, but it returns findings
    rather than raising, so the gates still run over the card.
    """
    return value if isinstance(value, list) else []


def _known(value, identifiers):
    """Is `value` one of `identifiers`, without raising when it is not an id?

    Every collection passed in here is built with an `isinstance(..., str)`
    filter, so a non-string could never be a member — but `value in
    identifiers` *raises* on an unhashable value (a card that wrote a list
    where an id belongs) rather than answering False. A gate that raises takes
    the whole report down; answering False produces the "references unknown X"
    finding the author actually needs.
    """
    return isinstance(value, str) and value in identifiers


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

    outcomes = _sequence(decision.get("outcomes"))
    seen = {o.get("result") for o in _objects(outcomes)
            if isinstance(o.get("result"), str)}
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
    pathways = _sequence(_mapping(card.get("domain")).get("harm_pathways"))
    by_id = {p.get("id"): p for p in pathways
             if isinstance(p, dict) and isinstance(p.get("id"), str)}

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
    for index, construct in enumerate(_sequence(card.get("constructs"))):
        if not isinstance(construct, dict):
            continue
        listed = _sequence(construct.get("harm_pathways"))
        if not listed:
            findings.append(Finding(
                "error", "constructs[%d].harm_pathways" % index,
                "construct %r traces to no harm pathway" % construct.get("id"),
                gate=2,
            ))
        for reference in listed:
            if isinstance(reference, str):
                referenced.add(reference)
            if not _known(reference, by_id):
                findings.append(Finding(
                    "error", "constructs[%d].harm_pathways" % index,
                    "construct %r references unknown pathway %r"
                    % (construct.get("id"), reference),
                    gate=2,
                ))

    for index, pathway in enumerate(pathways):
        identifier = pathway.get("id") if isinstance(pathway, dict) else None
        if identifier is not None and not _known(identifier, referenced):
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
    for index, construct in enumerate(_sequence(card.get("constructs"))):
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


MINIMUM_ITEMS_PER_CLAIM = 3


def _read_pool(path):
    """Read a JSONL item pool. Returns (rows, findings).

    `rows` is a list of (line number, parsed row) pairs. The line number is
    carried because a row that is missing the field naming it — no `item_id` —
    cannot be pointed at any other way, and "fix the item with no id" is not an
    actionable finding in a pool of five hundred.

    `rows` is None when the file could not be opened at all. There is nothing
    to count in that case, and reporting every claim as having zero items would
    bury the one finding that matters under derivative noise. A malformed
    *line* is a different thing: the rows that parsed still count, so those
    come back normally alongside the finding.
    """
    rows, findings = [], []
    try:
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append((number, json.loads(line)))
                except json.JSONDecodeError as exc:
                    findings.append(Finding(
                        "error", "items.source",
                        "line %d of the item pool is not JSON: %s" % (number, exc),
                        gate=4,
                    ))
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError, not an OSError, so it would
        # otherwise escape this gate and the CLI both. A pool saved as cp1252
        # is not a readable pool, and that is the finding to report.
        findings.append(Finding(
            "error", "items.source",
            "cannot read the item pool: %s" % exc, gate=4))
        return None, findings
    return rows, findings


DUPLICATE_LINES_SHOWN = 5


def _line_list(numbers, limit=DUPLICATE_LINES_SHOWN):
    """Name the repeated lines, but never more than a reader can use.

    A pool where one id is pasted five hundred times has to stay one finding
    on one line, so the tail is counted rather than listed.
    """
    shown = ", ".join(str(n) for n in numbers[:limit])
    label = "line " if len(numbers) == 1 else "lines "
    if len(numbers) > limit:
        return label + shown + " and %d more" % (len(numbers) - limit)
    return label + shown


def gate_4_trace_matrix(card, card_path):
    """Gate 4: does every item trace to a claim, and every claim to 3+ items?

    This is what makes a score readable at the claim level. Without it the
    number says the system did well overall and cannot say what it did well at,
    which is the difference between a result and a leaderboard entry.
    """
    findings = []
    construct_ids = {c.get("id") for c in _objects(card.get("constructs"))
                     if isinstance(c.get("id"), str)}
    claims = _sequence(card.get("claims"))
    claim_ids = {c.get("id") for c in _objects(claims)
                 if isinstance(c.get("id"), str)}

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        if not _known(claim.get("construct"), construct_ids):
            findings.append(Finding(
                "error", "claims[%d].construct" % index,
                "claim %r references unknown construct %r"
                % (claim.get("id"), claim.get("construct")),
                gate=4,
            ))

    for block in ("evidence_model", "task_model"):
        for index, entry in enumerate(_sequence(card.get(block))):
            if not isinstance(entry, dict):
                continue
            if not _known(entry.get("claim"), claim_ids):
                findings.append(Finding(
                    "error", "%s[%d].claim" % (block, index),
                    "%s entry %r references unknown claim %r"
                    % (block, entry.get("id"), entry.get("claim")),
                    gate=4,
                ))

    evidenced = {e.get("claim") for e in _objects(card.get("evidence_model"))
                 if isinstance(e.get("claim"), str)}
    tasked = {t.get("claim") for t in _objects(card.get("task_model"))
              if isinstance(t.get("claim"), str)}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        identifier = claim.get("id")
        if not _known(identifier, evidenced):
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has no evidence model entry, so nothing says what "
                "would be observed to support it" % identifier,
                gate=4,
            ))
        if not _known(identifier, tasked):
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has no task model entry, so nothing elicits it"
                % identifier,
                gate=4,
            ))

    source = _mapping(card.get("items")).get("source")
    if _blank(source):
        # Not `if not source`: a card that put a number here would then reach
        # `resolve()`, which wants a path and raises on anything else. Gate 5
        # already guards its own path this way.
        findings.append(Finding(
            "error", "items.source", "no item pool is named", gate=4))
        return findings

    rows, read_findings = _read_pool(resolve(card_path, source))
    findings.extend(read_findings)
    if rows is None:
        return findings

    # Distinctness first, and independently of whether a row's claim resolves:
    # two rows sharing an id are ambiguous about which item a score belongs to
    # however they are counted afterwards.
    first_seen = {}
    repeats = {}
    unusable_lines = []
    for number, row in rows:
        item_id = row.get("item_id") if isinstance(row, dict) else None
        if _blank(item_id):
            unusable_lines.append(number)
            continue
        if item_id in first_seen:
            repeats.setdefault(item_id, []).append(number)
        else:
            first_seen[item_id] = number

    # One finding for every row with no usable item_id, not one per row: a
    # pool where the field was never populated would otherwise bury every
    # other finding under a hundred repeats of the same fact, for the same
    # reason a duplicated id below is one finding rather than one per repeat.
    # The message has to hold for both causes of "no usable item_id" -- the
    # field absent, or present but not a string, such as an integer id from
    # an ordinary database or spreadsheet export -- so it never tells a
    # reader with the second kind that a field is missing when it is not.
    if unusable_lines:
        findings.append(Finding(
            "error", "items.source",
            "%d row%s in the item pool %s no item_id, or one that is not a "
            "string (%s); a row that cannot be identified cannot be told "
            "apart from any other item or counted toward a claim"
            % (len(unusable_lines), "" if len(unusable_lines) == 1 else "s",
               "has" if len(unusable_lines) == 1 else "have",
               _line_list(unusable_lines)),
            gate=4,
        ))

    # One finding per duplicated id, not one per repeated row. An id pasted
    # five hundred times is one violation, and this tool's contract is that a
    # card gets fixed once rather than once per run - which four hundred and
    # ninety-nine near-identical lines defeat by burying every other finding.
    for item_id, lines in sorted(repeats.items(), key=lambda e: first_seen[e[0]]):
        findings.append(Finding(
            "error", "items.source",
            "item_id %r first appears on line %d and is repeated on %d "
            "further row%s (%s); two rows sharing an id are ambiguous about "
            "which item a score belongs to"
            % (item_id, first_seen[item_id], len(lines),
               "" if len(lines) == 1 else "s", _line_list(lines)),
            gate=4,
        ))

    # Count *distinct* item ids per claim, not rows. Three copies of one item
    # carry no more claim-level information than one copy, so counting rows
    # makes the floor satisfiable by copy-paste.
    counts = {}
    for number, row in rows:
        claim_id = row.get("claim_id") if isinstance(row, dict) else None
        if claim_id is None:
            findings.append(Finding(
                "error", "items.source",
                "item %r has no claim_id, so it traces to nothing"
                % (row.get("item_id") if isinstance(row, dict) else number),
                gate=4,
            ))
            continue
        if not _known(claim_id, claim_ids):
            findings.append(Finding(
                "error", "items.source",
                "item %r references unknown claim %r"
                % (row.get("item_id"), claim_id),
                gate=4,
            ))
            continue
        item_id = row.get("item_id")
        if not _blank(item_id):
            counts.setdefault(claim_id, set()).add(item_id)

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        identifier = claim.get("id")
        count = len(counts[identifier]) if _known(identifier, counts) else 0
        if count < MINIMUM_ITEMS_PER_CLAIM:
            findings.append(Finding(
                "error", "claims[%d]" % index,
                "claim %r has %d distinct items; %d are needed before a score "
                "can be read at the claim level"
                % (identifier, count, MINIMUM_ITEMS_PER_CLAIM),
                gate=4,
            ))

    return findings


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonblank_lines(path):
    """How many non-blank lines a file has, counted over raw bytes.

    Bytes, not decoded text: Gate 5 is a byte-level gate, and decoding to count
    lines would raise UnicodeDecodeError — a ValueError, which the CLI does not
    catch — on a split that is not valid UTF-8. Counting lines rather than
    parsing them is deliberate too; whether each line is a well-formed item is
    Gate 4's question.
    """
    count = 0
    with open(path, "rb") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _normalized_hash(value):
    """A recorded or computed hex digest, normalized for comparison.

    Strips surrounding whitespace and an optional `sha256:` label, then
    lowercases. Hex digest case carries no information — `E68D01` and
    `e68d01` name the same digest — and cards in this repo write
    `sha256:<hex>` for the protocol hash but bare hex for the split hash, so
    rejecting either label or either case would be a gate failing over
    punctuation. Gate 5 and Gate 9 both compare a recorded hash against a
    freshly computed one and must agree on what counts as a match.
    """
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    return text


def gate_5_sealed_split(card, card_path):
    """Gate 5: is the test split sealed, and is it still the file that was sealed?

    The hash is taken over raw bytes, not parsed JSON, so reformatting the file
    trips it too. That is deliberate: "same items, different whitespace" is
    indistinguishable from "someone edited the split" without reading the diff,
    and the gate exists precisely to make that visible.

    A mismatch is always an error. A warning here would make the gate
    decorative.
    """
    findings = []
    items = _mapping(card.get("items"))

    canary = _mapping(items.get("contamination_controls")).get("canary")
    if _blank(canary):
        findings.append(Finding(
            "error", "items.contamination_controls.canary",
            "no canary string; without one, leakage into a model's training "
            "data cannot be detected later",
            gate=5,
        ))

    split = _mapping(_mapping(items.get("splits")).get("test"))

    if split.get("sealed") is not True:
        findings.append(Finding(
            "error", "items.splits.test.sealed",
            "the test split is not marked sealed", gate=5))

    if _blank(split.get("sealed_at")):
        findings.append(Finding(
            "error", "items.splits.test.sealed_at",
            "no seal timestamp, so nothing records when the split was fixed",
            gate=5,
        ))

    recorded = split.get("sha256")
    path = split.get("path")
    if _blank(recorded):
        findings.append(Finding(
            "error", "items.splits.test.sha256",
            "no recorded hash, so the split cannot be shown to be unchanged",
            gate=5,
        ))
    elif _blank(path):
        findings.append(Finding(
            "error", "items.splits.test.path",
            "no test split file is named", gate=5))
    else:
        resolved = resolve(card_path, path)
        try:
            actual = _sha256_of(resolved)
            items_in_split = _nonblank_lines(resolved)
        except OSError as exc:
            findings.append(Finding(
                "error", "items.splits.test.path",
                "cannot read the test split: %s" % exc, gate=5))
        else:
            if _normalized_hash(actual) != _normalized_hash(recorded):
                findings.append(Finding(
                    "error", "items.splits.test.sha256",
                    "the test split has changed since it was sealed (recorded "
                    "%s..., found %s...); every number computed from it "
                    "measures something other than what was sealed"
                    % (_normalized_hash(recorded)[:12],
                       _normalized_hash(actual)[:12]),
                    gate=5,
                ))
            elif not items_in_split:
                # The hash of an empty file is a perfectly valid sha256, so
                # the seal check alone passes a split that seals nothing. A
                # card can otherwise validate clean while committing to no
                # items at all.
                findings.append(Finding(
                    "error", "items.splits.test.path",
                    "the sealed test split is empty; a split with no items "
                    "seals nothing, and every number computed from it is "
                    "computed from no evidence",
                    gate=5,
                ))

    return findings


def _parse_timestamp(value):
    """Parse an ISO 8601 timestamp, tolerating a trailing Z. None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A card that writes "2026-09-06T10:00:00Z" for the seal and a bare
        # "2026-09-06T11:00:00" for a result is ordinary. Comparing an aware
        # datetime with a naive one raises TypeError, and a gate that raises
        # takes the whole run down — so read a missing offset as UTC.
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _result_timestamps(card):
    """Result times under `qualification`. Returns (parsed, unreadable).

    Both lists hold (path, ...) pairs: `parsed` carries the datetime for every
    value that could be read, `unreadable` the raw value for every one that
    was written and could not. Dropping the second kind silently is the wrong
    answer -- the card claims a result time, Gate 9's ordering check then
    simply does not happen for it, and nothing says so. A key that is absent
    entirely, or explicitly null, claims nothing and is in neither list.
    """
    found, unreadable = [], []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("computed_at", "run_at", "measured_at"):
                    parsed = _parse_timestamp(value)
                    if parsed is not None:
                        found.append((path + "." + key, parsed))
                    elif value is not None:
                        unreadable.append((path + "." + key, value))
                else:
                    walk(value, path + "." + key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, "%s[%d]" % (path, index))

    # No shape guard needed: `walk` reads a dict or a list and ignores
    # anything else, so a qualification block of the wrong shape yields
    # nothing rather than raising.
    walk(card.get("qualification"), "qualification")
    return found, unreadable


def gate_9_preregistration(card, card_path):
    """Gate 9: was the decision threshold set before the run?

    This is the gate that stops the goalposts moving, and it is checkable only
    because the card records a hash and a timestamp before any result exists.
    Everyone believes they would not move a threshold after seeing the number.

    The hash is recomputed here, not merely required to be present. The schema
    says `content_hash` exists so the protocol "cannot be edited after the fact
    without detection" — a promise that only a recomputation keeps. Gate 5 does
    exactly this for the sealed split, and this gate mirrors it.
    """
    findings = []
    prereg = _mapping(card.get("preregistration"))

    recorded = prereg.get("content_hash")
    prompts_ref = _mapping(prereg.get("protocol")).get("prompts_ref")
    if _blank(recorded):
        findings.append(Finding(
            "error", "preregistration.content_hash",
            "no content hash, so nothing shows the protocol is the one that "
            "was sealed",
            gate=9,
        ))
    elif _blank(prompts_ref):
        findings.append(Finding(
            "error", "preregistration.protocol.prompts_ref",
            "a content hash is recorded but no protocol file is named; a hash "
            "over a file the card does not name proves nothing",
            gate=9,
        ))
    else:
        try:
            actual = _sha256_of(resolve(card_path, prompts_ref))
        except OSError as exc:
            findings.append(Finding(
                "error", "preregistration.protocol.prompts_ref",
                "cannot read the sealed protocol: %s" % exc, gate=9))
        else:
            if _normalized_hash(actual) != _normalized_hash(recorded):
                findings.append(Finding(
                    "error", "preregistration.content_hash",
                    "the protocol has changed since it was sealed (recorded "
                    "%s..., found %s...); the prompts, seeds or decoding "
                    "settings a result was produced under are not the ones "
                    "that were preregistered"
                    % (_normalized_hash(recorded)[:12],
                       _normalized_hash(actual)[:12]),
                    gate=9,
                ))

    sealed_at = _parse_timestamp(prereg.get("sealed_at"))
    if sealed_at is None:
        findings.append(Finding(
            "error", "preregistration.sealed_at",
            "no parseable ISO 8601 seal timestamp; without one, 'before the "
            "run' cannot be established",
            gate=9,
        ))

    threshold = prereg.get("threshold")
    if not isinstance(threshold, dict) or not threshold:
        findings.append(Finding(
            "error", "preregistration.threshold",
            "no threshold fixed before the run; a preregistration that commits "
            "to no number preregisters nothing",
            gate=9,
        ))

    stamps, unreadable = _result_timestamps(card)

    for path, value in unreadable:
        findings.append(Finding(
            "error", path,
            "result timestamp %r is not a parseable ISO 8601 timestamp, so "
            "this gate cannot check it against the preregistration seal"
            % (value,),
            gate=9,
        ))

    if sealed_at is not None:
        for path, stamp in stamps:
            if stamp < sealed_at:
                findings.append(Finding(
                    "error", path,
                    "result timestamp %s predates the preregistration seal at "
                    "%s; the threshold was set knowing the answer"
                    % (stamp.isoformat(), sealed_at.isoformat()),
                    gate=9,
                ))

    return findings


# (gate number, callable, needs_card_path).
ALL = [
    (1, gate_1_decision, False),
    (2, gate_2_harm_pathways, False),
    (3, gate_3_falsifiable, False),
    (4, gate_4_trace_matrix, True),
    (5, gate_5_sealed_split, True),
    (9, gate_9_preregistration, True),
]


def run_all(card, card_path):
    """Run every registered gate, in numeric order, and collect the findings."""
    findings = []
    for number, check, needs_path in sorted(ALL, key=lambda entry: entry[0]):
        findings.extend(check(card, card_path) if needs_path else check(card))
    return findings
