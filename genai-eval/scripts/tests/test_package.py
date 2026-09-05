#!/usr/bin/env python3
"""Package-level tests for evalstats. Run directly: python3 test_package.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evalstats


class TestSubmodulesAreBound(unittest.TestCase):
    def test_submodule_attributes_resolve_after_plain_import(self):
        """__all__ names the submodules, but naming them in __all__ does not
        import them — only `from . import agreement, ...` in __init__.py does.
        Without that import, `import evalstats; evalstats.power` raises
        AttributeError even though "power" is right there in __all__, because
        nothing has bound the name on the package object yet."""
        for name in evalstats.__all__:
            module = getattr(evalstats, name)
            self.assertEqual(module.__name__, "evalstats.%s" % name)


if __name__ == "__main__":
    unittest.main()
