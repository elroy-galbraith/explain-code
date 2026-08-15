#!/usr/bin/env python3
"""
test_check_ste.py — stdlib-only checks for check_ste.py.

Run it directly (no pytest, no packages, matching check_ste.py's own
zero-dependency rule):

    python3 test_check_ste.py

It exits non-zero if any check fails. Two things carry most of the weight here:

  1. **Code is never flagged.** The checker reports at error level and its output
     is meant to be trusted, so a finding fired at an identifier or a shell
     command would train authors to ignore it. The masking tests pin that shut.
  2. **The false-positive traps.** Phrasal verbs reading as noun clusters, and
     adjectival `-ed` words reading as passives, are the two heuristics most
     likely to regress into noise.

It also verifies the vocabulary tables in ../references/engineering-vocabulary.md
still parse, since that file is the checker's data source as well as its
documentation — a formatting change there silently disarms the word-choice rule.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location("check_ste", os.path.join(HERE, "check_ste.py"))
check_ste = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_ste)

SUBS, SYNS = check_ste.load_vocabulary()

_results = []


def check(name, condition):
    _results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")


def run(text, profile="lite", subs=None, syns=None):
    """Check `text` and return the set of rule names that fired."""
    findings = check_ste.check(
        text, profile,
        SUBS if subs is None else subs,
        SYNS if syns is None else syns,
    )
    return {f.rule for f in findings}, findings


# --------------------------------------------------------------------------- #
# Masking — code must never produce a finding
# --------------------------------------------------------------------------- #

def test_masking():
    print("code masking:")

    fenced = (
        "The gateway checks the token.\n\n"
        "```python\n"
        "running_backfill = utilize(thing)  # spin up the low-hanging fruit\n"
        "```\n"
    )
    rules, _ = run(fenced)
    check("fenced code block is not checked", rules == set())

    inline = "Call `utilize_in_order_to_spin_up()` before the run.\n"
    rules, _ = run(inline)
    check("inline backtick span is not checked", "word-choice" not in rules)

    html = "<p>The gateway checks the token.</p>\n<pre>we should leverage this</pre>\n"
    rules, _ = run(html)
    check("<pre> block is not checked", "word-choice" not in rules)

    indented = "The gateway checks the token.\n\n    leverage the low-hanging fruit\n"
    rules, _ = run(indented)
    check("indented code block is not checked", rules == set())

    url = "See https://example.com/spin-up/in-order-to for the details.\n"
    rules, _ = run(url)
    check("URL is not checked", "word-choice" not in rules)

    # Masking must preserve offsets, or every reported line number is wrong.
    text = "```\nleverage\n```\nWe should leverage the queue.\n"
    _, findings = run(text)
    word_choice = [f for f in findings if f.rule == "word-choice"]
    check("line numbers survive masking", len(word_choice) == 1 and word_choice[0].line == 4)


# --------------------------------------------------------------------------- #
# Sentence length
# --------------------------------------------------------------------------- #

def test_sentence_length():
    print("sentence length:")

    twenty_two = "The gateway " + " ".join(f"word{i}" for i in range(20)) + " ends.\n"
    rules, _ = run(twenty_two, "lite")
    check("22-word descriptive sentence passes lite", "sentence-length" not in rules)
    rules, _ = run(twenty_two, "strict")
    check("22-word descriptive sentence fails strict", "sentence-length" in rules)

    long_desc = "The gateway " + " ".join(f"word{i}" for i in range(30)) + " ends.\n"
    rules, _ = run(long_desc, "lite")
    check("32-word descriptive sentence fails lite", "sentence-length" in rules)

    # Procedural sentences get the tighter cap in both profiles.
    proc = "Restart " + " ".join(f"word{i}" for i in range(21)) + ".\n"
    rules, _ = run(proc, "lite")
    check("22-word procedural sentence fails lite", "sentence-length" in rules)

    _, findings = run(proc, "lite")
    msg = next(f.message for f in findings if f.rule == "sentence-length")
    check("procedural sentence is named as procedural", "procedural" in msg)

    # "e.g." must not end a sentence, or word counts split in the wrong place.
    abbrev = "Use a short retry delay, e.g. 200 ms, so the worker does not stall.\n"
    _, findings = run(abbrev)
    check("abbreviation does not split a sentence",
          not any(f.rule == "sentence-length" for f in findings))


# --------------------------------------------------------------------------- #
# Noun clusters — the highest-value rule, and the easiest to overfire
# --------------------------------------------------------------------------- #

def test_noun_cluster():
    print("noun clusters:")

    rules, _ = run("The user session token refresh handler is slow.\n")
    check("four-noun cluster is flagged", "noun-cluster" in rules)

    rules, _ = run("The handler that refreshes session tokens is slow.\n")
    check("rewritten cluster is clean", "noun-cluster" not in rules)

    # Regression: a phrasal verb plus its object is not a noun cluster.
    rules, _ = run("We use the queue to start more workers today.\n")
    check("phrasal verb plus object is not a cluster", "noun-cluster" not in rules)

    rules, _ = run("The gateway validated four hundred requests today.\n")
    check("past-tense verb breaks the run", "noun-cluster" not in rules)


# --------------------------------------------------------------------------- #
# Passive voice
# --------------------------------------------------------------------------- #

def test_passive():
    print("passive voice:")

    rules, _ = run("The token is validated before the request continues.\n")
    check("passive is flagged", "passive-voice" in rules)

    rules, _ = run("The gateway validates the token, then forwards the request.\n")
    check("active is clean", "passive-voice" not in rules)

    # Regression: adjectival -ed after `be` is a state, not a hidden actor.
    rules, _ = run("If the payload is malformed, the gateway rejects it.\n")
    check("adjectival -ed is not passive", "passive-voice" not in rules)

    rules, _ = run("The row was written by the backfill job.\n")
    check("irregular participle is caught", "passive-voice" in rules)

    _, findings = run("The token is validated before the request continues.\n", "lite")
    check("passive is a warning in lite",
          all(f.level == "warn" for f in findings if f.rule == "passive-voice"))
    _, findings = run("The token is validated before the request continues.\n", "strict")
    check("passive is an error in strict",
          all(f.level == "error" for f in findings if f.rule == "passive-voice"))


# --------------------------------------------------------------------------- #
# Participles, conditions, paragraphs, terminology
# --------------------------------------------------------------------------- #

def test_other_rules():
    print("other rules:")

    chain = "Migrating the table while holding the lock, blocking writers, causes timeouts.\n"
    rules, _ = run(chain)
    check("participle chain is flagged", "participle-chain" in rules)

    one_ing = "The scheduler is migrating the table.\n"
    rules, _ = run(one_ing, "lite")
    check("single -ing passes lite", "participle-chain" not in rules)
    rules, _ = run(one_ing, "strict")
    check("single -ing fails strict", "participle-chain" in rules)

    benign = "Check the logging settings and the existing warning thresholds.\n"
    rules, _ = run(benign, "lite")
    check("benign -ing nouns are not a chain", "participle-chain" not in rules)

    rules, _ = run("Restart the worker if the queue depth is high.\n")
    check("trailing condition is flagged", "condition-order" in rules)
    rules, _ = run("If the queue depth is high, restart the worker.\n")
    check("leading condition is clean", "condition-order" not in rules)

    para = "\n".join(f"The gateway checks value {i}." for i in range(8)) + "\n"
    rules, _ = run(para)
    check("over-long paragraph is flagged", "paragraph-length" in rules)

    drift = "The gateway logs each call. The invocation is recorded in order.\n"
    rules, _ = run(drift, syns=[["call", "invocation", "request"]])
    check("terminology drift is flagged", "terminology-drift" in rules)

    consistent = "The gateway logs each call. It records the call in order.\n"
    rules, _ = run(consistent, syns=[["call", "invocation", "request"]])
    check("consistent terminology is clean", "terminology-drift" not in rules)


# --------------------------------------------------------------------------- #
# Vocabulary file — the checker's data source
# --------------------------------------------------------------------------- #

def test_vocabulary():
    print("vocabulary reference:")

    check("substitution table parses", len(SUBS) > 50)
    check("synonym groups parse", len(SYNS) > 5)
    check("every substitution has a level",
          all(level in ("error", "warn") for _, _, level in SUBS))
    check("no duplicate substitution keys",
          len({a for a, _, _ in SUBS}) == len(SUBS))
    check("header rows are not parsed as entries",
          not any(a == "avoid" for a, _, _ in SUBS))

    by_key = {a: (b, lvl) for a, b, lvl in SUBS}
    check("phrasal verbs are loaded", by_key.get("spin up", ("", ""))[0] == "start")
    check("idioms are loaded", "low-hanging fruit" in by_key)
    check("multi-word entries match across whitespace",
          "word-choice" in run("Do this in order\nto finish the job.\n")[0])

    missing, _ = check_ste.load_vocabulary("/nonexistent/vocabulary.md")
    check("missing vocabulary file degrades gracefully", missing == [])
    rules, _ = run("The user session token refresh handler is slow.\n", subs=[], syns=[])
    check("structural rules still run without vocabulary", "noun-cluster" in rules)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli():
    print("cli:")

    tmp = os.path.join(HERE, "_tmp_check_ste_input.md")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("We should leverage the queue.\n")

        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_ste.main([tmp, "--format", "json"])
        payload = json.loads(out.getvalue())
        check("json output parses", isinstance(payload.get("findings"), list))
        check("json reports the error count", payload["errors"] >= 1)
        check("errors exit non-zero", code == 1)

        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("The gateway checks the token.\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_ste.main([tmp])
        check("clean text exits zero", code == 0)
        check("clean run says it is a floor, not a pass", "floor" in out.getvalue())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    try:
        check_ste.check("text", "nonsense")
        check("unknown profile is rejected", False)
    except ValueError as ex:
        check("unknown profile is rejected", "profile" in str(ex))


# --------------------------------------------------------------------------- #

def main():
    test_masking()
    test_sentence_length()
    test_noun_cluster()
    test_passive()
    test_other_rules()
    test_vocabulary()
    test_cli()

    failed = [name for name, ok in _results if not ok]
    total = len(_results)
    print(f"\n{total - len(failed)}/{total} checks passed.")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
