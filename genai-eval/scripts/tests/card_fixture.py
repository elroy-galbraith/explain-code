#!/usr/bin/env python3
"""Builds a valid eval card on disk, so each gate test can break exactly one thing.

Every gate test starts from this card and mutates one field. That is what makes
"this gate fires and no other gate fires" a meaningful assertion — if the base
card were already failing something, every test would pass for the wrong reason.
"""

import hashlib
import json
import os

POOL = [
    {"item_id": "i1", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i2", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i3", "claim_id": "cl1", "prompt": "..."},
    {"item_id": "i4", "claim_id": "cl2", "prompt": "..."},
    {"item_id": "i5", "claim_id": "cl2", "prompt": "..."},
    {"item_id": "i6", "claim_id": "cl2", "prompt": "..."},
]

TEST_SPLIT = [POOL[2], POOL[5]]

DEV_SPLIT = [POOL[0], POOL[3]]

# The sealed protocol Gate 9's content_hash is taken over. It has to exist on
# disk and the card's hash has to match it, because Gate 9 recomputes rather
# than trusting the recorded value.
PROTOCOL = "# Fixture protocol\n\ntemperature 0.0, seeds [0, 1, 2].\n"


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_card():
    """A card that passes every gate this phase checks."""
    return {
        "schema_version": 1,
        "id": "fixture",
        "title": "Fixture card",
        "tier": 2,
        "status": "sealed",
        "created": "2026-09-06",
        "decision": {
            "question": "Ship the new prompt?",
            "owner": "eval lead",
            "outcomes": [
                {"result": "pass", "action": "roll out"},
                {"result": "fail", "action": "hold"},
                {"result": "borderline", "action": "escalate to tier 3"},
            ],
        },
        "domain": {
            "users": "support agents",
            "operating_conditions": "live traffic",
            "harm_pathways": [
                {"id": "hp1", "rank": 1, "severity": "high",
                 "description": "cites an unsupported source"},
            ],
        },
        "constructs": [
            {"id": "c_grounding",
             "definition": "answers are traceable to retrieved context",
             "positive_evidence": ["every factual sentence maps to a chunk"],
             "negative_evidence": ["asserts a figure absent from all chunks"],
             "harm_pathways": ["hp1"]},
        ],
        "claims": [
            {"id": "cl1", "construct": "c_grounding", "statement": "no unsupported facts"},
            {"id": "cl2", "construct": "c_grounding", "statement": "no invented citations"},
        ],
        "evidence_model": [
            {"id": "ev1", "claim": "cl1", "observable": "unsupported sentence count",
             "scoring_rule": "binary", "rubric_ref": "rubrics/grounding.md"},
            {"id": "ev2", "claim": "cl2", "observable": "invented citation count",
             "scoring_rule": "binary", "rubric_ref": "rubrics/grounding.md"},
        ],
        "task_model": [
            {"id": "tm1", "claim": "cl1", "task_family": "answer from 5 docs",
             "conditions": ["retrieval returns nothing relevant"]},
            {"id": "tm2", "claim": "cl2", "task_family": "answer from 5 docs",
             "conditions": ["retrieval returns a near-duplicate"]},
        ],
        "items": {
            "source": "items/pool.jsonl",
            "sampling_frame": "prod logs, stratified by intent",
            "contamination_controls": {
                "canary": "CANARY-fixture-9f3b",
                "date_stamped": True,
                "novel_items": 2,
            },
            "splits": {
                "dev": {"path": "items/dev.jsonl"},
                "test": {"path": "items/test.jsonl", "sealed": True,
                         "sha256": "", "sealed_at": "2026-09-06T10:00:00Z"},
            },
        },
        "grader": {
            "kind": "llm_judge",
            "model": "some-judge",
            "mode": "pairwise",
            "rubric_ref": "rubrics/grounding.md",
            "gold_set": "labels/gold.csv",
            "bias_probes": ["position", "length"],
        },
        "preregistration": {
            "sealed_at": "2026-09-06T10:00:00Z",
            "content_hash": "sha256:" + "0" * 64,
            "protocol": {"prompts_ref": "prompts/v4.md", "seeds": [0, 1, 2],
                         "temperature": 0.0, "elicitation_budget": "3 attempts"},
            "baselines": ["human", "prior_model_v3"],
            "threshold": {"metric": "grounding pass rate",
                          "minimum_interesting_difference": 0.03,
                          "decision_rule": "lower bound of 95% CI > 0.90"},
        },
    }


def write_card(directory, mutate=None, items=None, test_split=None,
               protocol=None):
    """Write a valid card and its pool into `directory`; return the card's path.

    `mutate` receives the card dict before it is written. `items` and
    `test_split` replace the default rows, `protocol` the sealed protocol text.
    The test split's sha256 and the protocol's content_hash are both computed
    from what is actually written, *before* `mutate` runs, so Gates 5 and 9
    pass unless a test breaks a seal deliberately.
    """
    pool_path = os.path.join(directory, "items", "pool.jsonl")
    test_path = os.path.join(directory, "items", "test.jsonl")
    _write_jsonl(pool_path, POOL if items is None else items)
    _write_jsonl(test_path, TEST_SPLIT if test_split is None else test_split)
    dev_path = os.path.join(directory, "items", "dev.jsonl")
    _write_jsonl(dev_path, DEV_SPLIT)

    protocol_path = os.path.join(directory, "prompts", "v4.md")
    os.makedirs(os.path.dirname(protocol_path), exist_ok=True)
    with open(protocol_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(PROTOCOL if protocol is None else protocol)

    card = base_card()
    card["items"]["splits"]["test"]["sha256"] = sha256_of(test_path)
    card["preregistration"]["content_hash"] = "sha256:" + sha256_of(protocol_path)
    if mutate is not None:
        mutate(card)

    card_path = os.path.join(directory, "eval-card.json")
    with open(card_path, "w", encoding="utf-8") as handle:
        json.dump(card, handle, indent=2, sort_keys=True)
    return card_path
