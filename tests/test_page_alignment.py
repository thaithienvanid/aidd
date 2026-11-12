"""Alignment on the design reference page and the work-items page, measured in a real browser, as the viewer's is in
`test_viewer_layout.py`: an icon sits in the middle of its control, and beside text it shares the text's middle (rules 3 and 4 of
docs/design/DESIGN.md, Layout > Alignment), and each button, field, and segment has equal opposite paddings (rule 5). The probes
are in `alignment_probe.py`, so the three pages are measured the same way. Each exception is below, with its reason. Opt in with
`AIDD_BROWSER_TESTS=1`."""

from __future__ import annotations

import unittest

import helpers
import work_page_browser as wb
from alignment_probe import ICON_PROBE, PADDING_PROBE, centre_problems, padding_problems
from browser_driver import needs_chrome

SESSION: dict = {}
REFERENCE = (helpers.ROOT / "docs" / "design" / "reference.html").resolve().as_uri()
WIDTHS = ((1400, 900), (800, 900), (400, 844))
# The work-items page: each view at a phone and a desktop width. (state, query)
SCREENS = (("busy", ""), ("busy", "view=board"), ("busy", "view=tree"), ("busy", "view=item&item=SPEC-17"), ("empty", ""))
# Opposite paddings are equal, except where a control's own parts need room on one side. Each exception is a tag or a class, with
# the four paddings it keeps (left, right, top, bottom, in px) and its reason: another amount on the same control is found.
UNEQUAL_PADDING_ON_PURPOSE = {
    "select": ((8, 24, 0, 0), "a select keeps 24 px at its end for its arrow, against 8 px at its start"),
    "search-btn": (
        (8, 6, 0, 0),
        "its key hint sits as far from the end as from the top and bottom, about 5 px, so the end padding is 6 px against 8 px at the start",
    ),
    "back": ((0, 8, 0, 0), "the back link's arrow lines up with the page's start edge, so it has no start padding and 8 px at its end"),
}
# No icon sits over its text on purpose on these two pages.
NO_STACKED = frozenset()


def setUpModule():
    wb.start(SESSION, "page-alignment-")


@needs_chrome
class AlignmentTests(wb.PageCase):
    session = SESSION

    def open_reference(self, size: tuple[int, int]) -> None:
        ready, self.page.ready = self.page.ready, "document.readyState === 'complete'"
        self.addCleanup(setattr, self.page, "ready", ready)
        self.page.open(REFERENCE, size)

    def test_an_icon_is_centred_in_its_control_on_the_reference_page_at_every_width(self):
        for size in WIDTHS:
            with self.subTest(width=size[0]):
                self.open_reference(size)
                rows = self.page.js(ICON_PROBE)
                self.assertGreater(len(rows), 5, "the probe found the controls")
                self.assertEqual(centre_problems(rows, width=size[0], stacked_on_purpose=NO_STACKED), [], "icons off the middle")

    def test_opposite_paddings_are_equal_on_the_reference_page_at_every_width(self):
        for size in WIDTHS:
            with self.subTest(width=size[0]):
                self.open_reference(size)
                rows = self.page.js(PADDING_PROBE)
                self.assertGreater(len(rows), 20, "the probe found the buttons, fields, and segments")
                self.assertEqual(padding_problems(rows, UNEQUAL_PADDING_ON_PURPOSE), [], "unequal paddings")

    def test_an_icon_is_centred_in_its_control_on_the_work_items_page(self):
        for size in (wb.PHONE, wb.DESKTOP):
            for state, query in SCREENS:
                with self.subTest(width=size[0], state=state, query=query):
                    self.open(state, query, size)
                    rows = self.page.js(ICON_PROBE)
                    self.assertGreater(len(rows), 0, "the probe found the controls")
                    self.assertEqual(centre_problems(rows, width=size[0], stacked_on_purpose=NO_STACKED), [], "icons off the middle")

    def test_an_icon_stays_on_the_first_line_of_a_title_that_wraps_at_200_percent_text(self):
        for size in (wb.PHONE, wb.DESKTOP):
            for state, query in (("busy", "view=tree"), ("long-title", "view=tree")):
                with self.subTest(width=size[0], state=state):
                    self.open(state, query, size, scale=2.0)
                    wrapped = self.page.js(
                        "[...document.querySelectorAll('.disc')].some((n) => n.getBoundingClientRect().height > 2 * parseFloat(getComputedStyle(n).lineHeight))"
                    )
                    self.assertTrue(wrapped, "a title wraps to more than two lines")
                    rows = self.page.js(ICON_PROBE)
                    self.assertGreater(len(rows), 0, "the probe found the controls")
                    self.assertEqual(centre_problems(rows, width=size[0], stacked_on_purpose=NO_STACKED), [], "icons off the first line")

    def test_opposite_paddings_are_equal_on_the_work_items_page(self):
        for size in (wb.PHONE, wb.DESKTOP):
            for state, query in SCREENS:
                with self.subTest(width=size[0], state=state, query=query):
                    self.open(state, query, size)
                    rows = self.page.js(PADDING_PROBE)
                    self.assertGreater(len(rows), 3, "the probe found the buttons and fields")
                    self.assertEqual(padding_problems(rows, UNEQUAL_PADDING_ON_PURPOSE), [], "unequal paddings")


if __name__ == "__main__":
    unittest.main()
