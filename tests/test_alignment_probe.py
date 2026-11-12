"""The padding rule's reader (`alignment_probe.padding_problems`), without a browser: an exception keeps the four paddings it names
and no others, so the opt-in browser tests find another amount on the same control."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts tests on the path)
from alignment_probe import padding_problems

EXCEPTIONS = {"select": ((8, 24, 0, 0), "an arrow"), "back": ((0, 8, 0, 0), "an arrow at the start edge")}


def row(tag: str, classes: tuple[str, ...], left: float, right: float, top: float = 0, bottom: float = 0) -> dict:
    return {"id": tag, "tag": tag, "classes": list(classes), "left": left, "right": right, "top": top, "bottom": bottom}


class PaddingExceptionTests(unittest.TestCase):
    def test_a_control_with_equal_opposite_paddings_needs_no_exception(self):
        self.assertEqual(padding_problems([row("button", (), 8, 8, 4, 4), row("select", (), 12, 12)], EXCEPTIONS), [])

    def test_an_exception_keeps_its_four_paddings_and_no_other_amount(self):
        self.assertEqual(padding_problems([row("select", (), 8, 24), row("button", ("back",), 0, 8)], EXCEPTIONS), [])
        for seed in (row("button", ("back",), 0, 16), row("select", (), 40, 24), row("select", (), 8, 24, 2, 0), row("button", ("back",), 0, 8.5)):
            with self.subTest(seed=seed):
                self.assertEqual(len(padding_problems([seed], EXCEPTIONS)), 1)

    def test_a_control_of_no_exception_with_unequal_paddings_is_found_by_name(self):
        self.assertEqual(padding_problems([row("button", ("btn",), 14, 8)], EXCEPTIONS), ["button (14 left, 8 right, 0 top, 0 bottom)"])


if __name__ == "__main__":
    unittest.main()
