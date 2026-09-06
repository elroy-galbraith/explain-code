#!/usr/bin/env python3
"""Every string these tools print must be encodable on a legacy Windows console.

Docstrings and comments are exempt: they are never written to a terminal. This
is here because the constraint has been broken twice by people who knew about
it, once as an arrow that cp1252 cannot encode and once as an em dash that
cp850 cannot. A rule that depends on remembering is the kind this plugin argues
should be bound to a check.
"""

import ast
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
PACKAGES = ("", "card", "calibration", "evalstats")


def _modules():
    for package in PACKAGES:
        directory = os.path.join(SCRIPTS, package) if package else SCRIPTS
        for name in sorted(os.listdir(directory)):
            if name.endswith(".py"):
                yield os.path.join(directory, name)


def _docstring_nodes(tree):
    """Ids of the string expressions that are docstrings, so they can be skipped."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if ast.get_docstring(node, clean=False) is not None and node.body:
                found.add(id(node.body[0].value))
    return found


def non_ascii_literals(path):
    """Every (line, text, codepoints) for a printed string carrying non-ASCII."""
    with io.open(path, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        bad = sorted({c for c in node.value if ord(c) > 127})
        if bad:
            offenders.append((node.lineno, node.value,
                              ["U+%04X" % ord(c) for c in bad]))
    return offenders


class TestPrintedStringsAreAscii(unittest.TestCase):
    def test_no_shipped_module_prints_a_non_ascii_character(self):
        problems = []
        for path in _modules():
            for line, text, points in non_ascii_literals(path):
                problems.append("%s:%d %s in %r"
                                % (os.path.basename(path), line,
                                   ",".join(points), text[:60]))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_check_would_notice_a_non_ascii_string(self):
        """A test that only ever sees a clean tree proves nothing about its own
        detector. Feed it a module that does contain one."""
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "sample.py")
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write('"""A docstring with an em dash — which is fine."""\n')
            handle.write('MESSAGE = "printed — not fine"\n')
        found = non_ascii_literals(path)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0][2], ["U+2014"])
        self.assertIn("printed", found[0][1])

    def test_every_shipped_module_is_actually_being_checked(self):
        """If the directory walk silently found nothing, the first test would
        pass vacuously."""
        names = [os.path.basename(p) for p in _modules()]
        for expected in ("calibrate.py", "check_eval_card.py", "loader.py",
                         "report.py", "gates.py", "agreement.py"):
            self.assertIn(expected, names)
        self.assertGreater(len(names), 12, names)


if __name__ == "__main__":
    unittest.main()
