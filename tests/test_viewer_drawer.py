"""The comments drawer in the middle band, from 48rem to 80rem (768 to 1279 px at the default text size), where it covers the
right of the artboard, driven in a real browser. The design under it keeps its size, and the next step shows once: in the
drawer's foot while it is open, and in the line to type under the frame while it is closed. That holds at the band's
widths, with a short line and a long one, after the window changes size, and after the line's words change.

The set-up the viewer's browser tests share, and how the browser starts, is in `viewer_browser.py`.
"""

from __future__ import annotations

import unittest

import viewer_browser as vb
from browser_driver import needs_chrome
from viewer_browser import SPEC_PAGE, VIEWER_PAGE


SESSION: dict = {}  # the module's one server and browser: "origin", "browser", and "page"


def setUpModule():
    vb.start(SESSION)


FRAME_WIDTH = "document.getElementById('frame').getBoundingClientRect().width"
# The frame's width and top, the height the artboard's sideways scrollbar takes, and whether the artboard scrolls up and down.
PLACE = """(() => { const r = document.getElementById('frame').getBoundingClientRect(), s = document.getElementById('scroller');
  return { width: r.width, top: r.top, bar: s.offsetHeight - s.clientHeight, scrolls: s.scrollHeight > s.clientHeight }; })()"""
LINE_HIDDEN = "getComputedStyle(document.getElementById('caption-next')).visibility === 'hidden'"
# Every state seen but the first, in the platform group and theme on screen, so the line says one state is left.
LAST = "seenKey('sign-in', 'empty', whereNow())"
ALL_BUT_LAST = f"comments.seen = new Set(allStates().flatMap(([id, state]) => WHERES.map((w) => seenKey(id, state, w))).filter((k) => k !== {LAST}))"
# Two repaints: by then a resize observer has answered the layout the last action changed.
TWO_REPAINTS = "new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))"
# An element shows whole in the part of the artboard a person sees: inside the artboard's box within its scrollbars, left of
# an open drawer, and on top at its middle and both ends, so no drawer, bar, or scrollbar covers any of it.
WHOLE = """((id) => {
  const n = document.getElementById(id), r = n.getBoundingClientRect(), s = document.getElementById('scroller'), a = s.getBoundingClientRect();
  const d = document.getElementById('inspector'), open = d.dataset.open === 'true' && d.getClientRects().length > 0;
  const right = open ? Math.min(a.left + s.clientWidth, d.getBoundingClientRect().left) : a.left + s.clientWidth;
  const inside = r.width > 0 && r.left >= a.left && r.top >= a.top && r.right <= right && r.bottom <= a.top + s.clientHeight;
  const y = r.top + r.height / 2;
  return inside && [r.left + 3, r.left + r.width / 2, r.right - 3].every((x) => n.contains(document.elementFromPoint(x, y)));
})"""
# The drawer's foot, where the next step is while the drawer is open, inside the window and on top.
FOOT_SHOWS = """(() => { const n = document.getElementById('closing'), r = n.getBoundingClientRect();
  return r.width > 0 && r.top >= 0 && r.bottom <= innerHeight && n.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); })()"""


@needs_chrome
class DrawerTests(vb.ViewerCase):
    session = SESSION

    def settle(self) -> None:
        self.page.wait("document.getElementById('workspace').dataset.ready === 'true'")
        self.page.js(TWO_REPAINTS, await_promise=True)

    def is_whole(self, element_id: str) -> bool:
        return self.page.js(f"({WHOLE})('{element_id}')")

    def toggle_drawer(self) -> None:
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.page.js(TWO_REPAINTS, await_promise=True)

    def opened(self, size: tuple[int, int], path: str, seen: str, fragment: str = "#sitters/success") -> None:
        """The page at `size`, with the states `seen` sets seen, redrawn as a state a person opens redraws it."""
        self.open(fragment, size, path)
        self.page.js(f"{seen}; commentSave(true); apply()")
        self.settle()

    def every_state_seen(self, size: tuple[int, int], path: str, fragment: str = "#sitters/success") -> None:
        self.opened(size, path, "comments.seen = new Set(allStates().flatMap(([id, state]) => WHERES.map((w) => seenKey(id, state, w))))", fragment)

    def forget_states_seen(self) -> None:
        self.page.call("Storage.clearDataForOrigin", origin=self.origin, storageTypes="local_storage")  # a save joins the stored states seen

    def assert_next_step_shows_once(self) -> None:
        self.assertTrue(self.page.js(FOOT_SHOWS), "the drawer's foot shows the next step")
        self.assertTrue(self.page.js(LINE_HIDDEN), "the line to type under the frame steps aside, so the next step shows once")

    def test_at_each_width_of_the_band_the_drawer_moves_nothing_and_the_next_step_shows_once(self):
        # The band's two ends, and 960, where the review column is open and the drawer leaves the least of the artboard beside
        # it in the layout the viewer opens: each with a short line to type and a long one.
        for size in ((768, 768), (960, 768), (1279, 768)):
            for line, path in (("short", VIEWER_PAGE), ("long", SPEC_PAGE)):
                with self.subTest(size=size, line=line):
                    self.every_state_seen(size, path)
                    self.assertTrue(self.is_whole("caption-next"), "the whole line to type shows under the frame")
                    closed = self.page.js(PLACE)
                    self.toggle_drawer()
                    opened = self.page.js(PLACE)
                    self.assertAlmostEqual(opened["width"], closed["width"], delta=0.01, msg="the drawer resizes nothing it covers")
                    # Where a scrollbar takes room (Linux, Windows), the drawer's sideways scrollbar takes it from the artboard's foot.
                    self.assertLessEqual(abs(opened["top"] - closed["top"]), (opened["bar"] - closed["bar"]) / 2 + 0.5, "the frame stays where it was")
                    self.assertFalse(opened["scrolls"], "nothing under the frame runs past the artboard's foot")
                    self.assert_next_step_shows_once()
                    for part in ("caption-size", "zoom-group"):
                        self.assertTrue(self.is_whole(part), f"{part} shows whole beside the drawer")
                    self.toggle_drawer()
                    self.assertAlmostEqual(self.page.js(FRAME_WIDTH), closed["width"], delta=0.01)
                    self.assertTrue(self.is_whole("caption-next"), "closed again, the whole line shows")

    def test_after_the_drawers_own_step_changes_the_line_the_frame_is_the_size_a_fresh_page_gives(self):
        # A Spec's design, so the line once every state is seen is the long one, which takes a row more.
        self.every_state_seen((1024, 768), SPEC_PAGE, "#sign-in/empty")
        fresh = self.page.js(FRAME_WIDTH)
        self.forget_states_seen()
        self.opened((1024, 768), SPEC_PAGE, ALL_BUT_LAST)
        self.toggle_drawer()
        self.page.click('[data-testid="proto-closing-next"]')  # the drawer's foot opens the last state; the line's words change
        self.page.wait("location.hash.startsWith('#sign-in/empty')")
        self.settle()
        self.assertAlmostEqual(self.page.js(FRAME_WIDTH), fresh, delta=0.01, msg="the frame keeps the room the new line takes with the drawer closed")
        self.assert_next_step_shows_once()
        self.toggle_drawer()
        self.assertAlmostEqual(self.page.js(FRAME_WIDTH), fresh, delta=0.01)
        self.assertTrue(self.is_whole("caption-next"), "closed, the whole new line shows")

    def test_after_the_line_loses_a_row_with_no_redraw_under_the_drawer_the_frame_takes_the_room_back(self):
        # A comment deleted, or a state seen in another tab, changes the line's words and redraws nothing else.
        self.opened((1024, 768), SPEC_PAGE, ALL_BUT_LAST)
        fresh = self.page.js(FRAME_WIDTH)  # one state left: the line takes one row
        self.forget_states_seen()
        self.every_state_seen((1024, 768), SPEC_PAGE)
        self.assertLess(self.page.js(FRAME_WIDTH), fresh - 1, "every state seen on a Spec's design: the line takes a row more")
        self.toggle_drawer()
        self.page.js(f"comments.seen.delete({LAST}); renderRail()")
        self.page.wait(f"Math.abs({FRAME_WIDTH} - {fresh}) < 0.01", timeout=5)
        self.assert_next_step_shows_once()
        self.toggle_drawer()
        self.assertTrue(self.is_whole("caption-next"), "closed, the whole new line shows")

    def test_after_the_window_changes_size_under_the_drawer_the_frame_is_the_size_a_fresh_page_gives(self):
        # A phone frame keeps the review column open, and at 768 the line to type takes a row more than at 1024.
        self.open("#sitters/success?frame=ios", (768, 768))
        self.settle()
        fresh = self.page.js(FRAME_WIDTH)
        self.open("#sitters/success?frame=ios", (1024, 768))
        self.settle()
        self.toggle_drawer()
        self.page.call("Emulation.setDeviceMetricsOverride", width=768, height=768, deviceScaleFactor=1, mobile=False)
        self.page.wait(f"innerWidth === 768 && Math.abs({FRAME_WIDTH} - {fresh}) < 0.01", timeout=5)
        self.assert_next_step_shows_once()
        self.toggle_drawer()
        self.assertAlmostEqual(self.page.js(FRAME_WIDTH), fresh, delta=0.01)
        self.assertTrue(self.is_whole("caption-next"), "closed, the whole line shows")


if __name__ == "__main__":
    unittest.main()
