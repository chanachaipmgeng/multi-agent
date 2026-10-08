import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smoke import add, greet  # noqa: E402


class SmokeTests(unittest.TestCase):
    def test_greet(self) -> None:
        self.assertEqual(greet("Hermes"), "สวัสดี Hermes")

    def test_greet_requires_name(self) -> None:
        with self.assertRaises(ValueError):
            greet("")

    def test_add(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_forced_failure_switch(self) -> None:
        """SMOKE_FORCE_FAIL=1 turns the suite red so the self-heal loop can be rehearsed."""
        self.assertFalse(os.environ.get("SMOKE_FORCE_FAIL") == "1", "forced failure requested")

    def test_subtract(self) -> None:
        from smoke import subtract
        self.assertEqual(subtract(5, 2), 3)

    def test_multiply(self) -> None:
        from smoke import multiply
        self.assertEqual(multiply(3, 4), 12)
