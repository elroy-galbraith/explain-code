#!/usr/bin/env python3
"""
test_render.py — stdlib-only checks for render.py.

Run it directly (no pytest, no packages, matching render.py's own zero-dependency
rule):

    python3 test_render.py

It exits non-zero on the first failed assertion. The focus is render.py's two
authorial guardrails — the "exactly one correct option" structural check and the
answer-length-bias check — plus a smoke test that the bundled sample_spec.json
still renders. Keeping these locked down matters because the whole test-first gate
is only trustworthy if the answer can't be picked by its shape.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location("render", os.path.join(HERE, "render.py"))
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def q(correct, *distractors, prompt="Question?"):
    """Build one question dict; first arg is the correct option's text."""
    options = [{"text": correct, "correct": True}]
    options += [{"text": d, "correct": False} for d in distractors]
    return {"prompt": prompt, "options": options, "explanation": "because."}


def render_result(spec):
    """Render a spec, capturing outcome and any stderr warning.

    Returns (status, warning) where status is 'ok' or the ValueError message.
    """
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            render.render(spec)
            status = "ok"
        except ValueError as ex:
            status = str(ex)
    return status, err.getvalue()


_results = []


def check(name, condition):
    _results.append((name, bool(condition)))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")


# --------------------------------------------------------------------------- #
# Structural validation (pre-existing behaviour must stay intact)
# --------------------------------------------------------------------------- #

def test_structural():
    print("structural validation:")

    two_correct = {"slug": "s", "quiz": [{
        "prompt": "p",
        "options": [
            {"text": "a", "correct": True},
            {"text": "b", "correct": True},
            {"text": "c", "correct": False},
        ],
    }]}
    status, _ = render_result(two_correct)
    check("two correct options is rejected", "exactly one" in status)

    no_correct = {"slug": "s", "quiz": [{
        "prompt": "p",
        "options": [{"text": "a", "correct": False}, {"text": "b", "correct": False}],
    }]}
    status, _ = render_result(no_correct)
    check("zero correct options is rejected", "exactly one" in status)

    one_option = {"slug": "s", "quiz": [{
        "prompt": "p",
        "options": [{"text": "a", "correct": True}],
    }]}
    status, _ = render_result(one_option)
    check("single-option question is rejected", "at least 2" in status)


# --------------------------------------------------------------------------- #
# Answer-length bias (the guardrail this test file exists for)
# --------------------------------------------------------------------------- #

def test_length_bias():
    print("answer-length bias:")

    # Correct answer is the sole longest in every quiz question -> gameable.
    gamed_quiz = {"slug": "s", "quiz": [
        q("the correct choice is clearly the longest option here", "short", "brief note"),
        q("again the right answer runs much longer than the rest", "nope", "no"),
        q("longest correct option wins yet again in this stem here", "x y", "p q"),
        q("this correct answer is also the wordiest of the bunch", "two words", "three word bit"),
        q("and one more where the correct answer is longest again", "tiny", "small one"),
    ]}
    status, _ = render_result(gamed_quiz)
    check("gamed quiz fails", "length bias" in status and "quiz" in status)

    # A short gate question inoculates the all-or-nothing gate: because getting
    # the gate by 'pick longest' requires winning EVERY question, one short
    # correct answer drops the pass chance to zero.
    gamed_gate = {"slug": "s", "gate": [
        q("the correct answer is the longest option here for sure", "short", "brief"),
        q("again correct is the wordiest choice in this gate item", "no", "nope indeed"),
    ], "quiz": _balanced_quiz()}
    status, _ = render_result(gamed_gate)
    check("gamed gate fails", "length bias" in status and "gate" in status)

    inoculated_gate = {"slug": "s", "gate": [
        q("short", "a much longer distractor option runs on here", "a medium option here"),
        q("the correct answer is the longest option here for sure", "no", "nope indeed"),
    ], "quiz": _balanced_quiz()}
    status, warn = render_result(inoculated_gate)
    check("one short gate answer inoculates the gate", status == "ok")

    # Balanced quiz: correct answer never the longest -> clean render, no warning.
    status, warn = render_result({"slug": "s", "quiz": _balanced_quiz()})
    check("balanced quiz renders", status == "ok")
    check("balanced quiz emits no warning", warn.strip() == "")

    # Mild tell: 3 of 5 correct answers are the sole longest (with the other two
    # deliberately the shortest) -> above chance enough to warn, below the bar to
    # block. The four-option questions keep chance low so the excess is a real tell.
    mild = {"slug": "s", "quiz": [
        q("the correct answer here is clearly the longest of the four", "short one", "brief note", "tiny bit"),
        q("again correct runs longer than every distractor in this item", "no", "nah", "nope"),
        q("correct is the wordiest option among these four choices now", "a", "b c", "d"),
        q("brief", "a distractor that is quite a bit longer here", "another longish distractor option here now", "third longer distractor option here"),
        q("two words", "much longer wrong distractor option here indeed", "another lengthy wrong distractor here now", "yet another long distractor option"),
    ]}
    status, warn = render_result(mild)
    check("mild tell renders", status == "ok")
    check("mild tell warns", "warning" in warn and "longest" in warn)


def _balanced_quiz():
    """A quiz where the correct answer is never the sole longest option."""
    return [
        q("alpha beta gamma delta", "one two three four five", "aa bb cc dd ee"),
        q("aa bb", "cc dd ee ff", "gg hh ii jj"),
        q("mm nn oo", "pp qq rr ss tt", "uu vv ww xx"),
        q("this has four words", "and this one is longer here", "short bit"),
        q("just two", "three plus words here", "one"),
    ]


# --------------------------------------------------------------------------- #
# Position shuffle stays deterministic and spreads the answer
# --------------------------------------------------------------------------- #

def test_shuffle():
    print("position shuffle:")
    spec = {"slug": "fixed-seed", "quiz": [
        q("correct", "b", "c", "d", prompt=f"Q{i}") for i in range(12)
    ]}
    a = render.render(spec)
    b = render.render(spec)
    check("render is deterministic for a fixed slug", a == b)

    positions = {render._normalize_question(
        q("correct", "b", "c", "d"), seed=f"fixed-seed:quiz:{i}"
    )["correct_index"] for i in range(12)}
    check("correct answer lands in more than one position", len(positions) > 1)


# --------------------------------------------------------------------------- #
# The bundled sample must stay clean (it is what authors copy from)
# --------------------------------------------------------------------------- #

def test_sample():
    print("bundled sample_spec.json:")
    sample = json.load(open(os.path.join(HERE, "sample_spec.json"), encoding="utf-8"))
    status, warn = render_result(sample)
    check("sample renders", status == "ok")
    check("sample emits no length-bias warning", warn.strip() == "")


# --------------------------------------------------------------------------- #

def main():
    test_structural()
    test_length_bias()
    test_shuffle()
    test_sample()

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
