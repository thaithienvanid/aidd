"""The prototype viewer's Board and its layout at each window size, driven in a real browser: the cells, the fit, the
frames in the link, the drawers at each width, the pins, and the images each row shows.

The set-up they share, and how the browser starts, is in `viewer_browser.py`.
"""

from __future__ import annotations

import json
import unittest
import urllib.parse

import viewer_browser as vb
from browser_driver import needs_chrome
from helpers import PROTOTYPE_TOOL
from viewer_browser import CARD, LAPTOP, WIDE


SESSION: dict = {}  # the module's one server and browser: "origin", "browser", and "page"


def setUpModule():
    vb.start(SESSION)


class ViewerCase(vb.ViewerCase):
    session = SESSION


@needs_chrome
class BoardTests(ViewerCase):
    """The Board: screens as rows, states as columns, each cell seen, not seen, or with comments."""

    def setUp(self):
        super().setUp()
        self.open("#sign-in/empty")  # seen: this one state
        self.page.click('[data-testid="proto-view-board"]')
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 15")

    def test_every_state_of_every_screen_is_a_cell_and_the_open_one_is_marked(self):
        self.assertEqual(self.page.js("document.querySelectorAll('#board .pv-rowh').length"), 3)
        self.assertEqual(self.page.js("[...document.querySelectorAll('#board .pv-colh')].length"), 8)
        self.assertEqual(self.page.js("document.querySelector('#board .pv-rowh[aria-current]').dataset.screen"), "sign-in")
        self.assertEqual(self.page.js("document.querySelector('#board .pv-thumb-name[aria-current=true]').dataset.testid"), "proto-board-sign-in-empty")
        self.assertEqual(self.page.js("document.getElementById('board-seen').textContent").split(" ")[0], "1")

    def test_the_filter_dims_the_cells_that_do_not_match(self):
        self.page.click('[data-testid="proto-board-unseen"]')
        self.assertEqual(self.page.js("document.querySelectorAll('#board .pv-thumb[data-dim]').length"), 1, "the one state seen")
        self.page.click('[data-testid="proto-board-commented"]')
        self.assertEqual(self.page.js("document.querySelectorAll('#board .pv-thumb:not([data-dim])').length"), 0, "no comment yet")
        self.page.click('[data-testid="proto-board-all"]')
        self.assertEqual(self.page.js("document.querySelectorAll('#board .pv-thumb[data-dim]').length"), 0)

    def test_a_cell_opens_its_screen_and_state_in_the_prototype(self):
        self.page.click('[data-testid="proto-board-sitters-error"]')
        self.page.wait("location.hash === '#sitters/error'")
        self.assertEqual(self.page.js("document.getElementById('tab-prototype').getAttribute('aria-selected')"), "true")
        self.page.js("history.back()")
        self.page.wait("location.hash === '#sign-in/empty?view=board'")

    def test_fit_and_100_percent_say_which_holds(self):
        pressed = "[...document.querySelectorAll('[data-zoom]')].map((b) => b.getAttribute('aria-pressed'))"
        self.assertEqual(self.page.js(pressed), ["true", "false"])
        self.page.click('[data-testid="proto-zoom-actual"]')
        self.assertEqual(self.page.js(pressed), ["false", "true"])

    def test_fit_grows_a_board_that_leaves_room(self):
        # R257 (5): on a wide screen the board fills the width, larger than its own size.
        self.open("#sign-in/empty?view=board&panels=none", (1920, 1080))
        self.page.wait("document.getElementById('board').dataset.ready === 'true'")
        self.assertGreater(self.page.js("ui.boardZoom"), 1)
        self.assertEqual(self.page.js("ui.boardZoomed"), "fit")

    def test_every_state_off_keeps_each_rows_first_state_and_links_between_screens_draw_arrows(self):
        self.page.click('[data-testid="proto-checks"]')  # the board's options are On or Off toggles in the Checks menu
        self.page.click('[data-testid="proto-board-every-state"]')
        self.assertEqual(self.page.js("document.querySelectorAll('#board .pv-thumb').length"), 3)
        self.assertEqual(self.page.js("document.getElementById('board').dataset.flows"), "off")
        self.page.click('[data-testid="proto-board-flow-lines"]')
        self.assertEqual(self.page.js("document.getElementById('board').dataset.flows"), "on")
        self.page.wait("document.querySelectorAll('#board .pv-edge').length > 0")


@needs_chrome
class NarrowTests(ViewerCase):
    """At phone width the panel buttons are the tab bar, and every view stays reachable."""

    def setUp(self):
        super().setUp()
        self.open("#sitters/success", (390, 844))

    def test_the_tab_bar_opens_the_states_the_comments_and_the_build_details(self):
        self.page.click('[data-testid="proto-screens-toggle"]')
        self.assertFalse(self.page.js("document.getElementById('screen-menu').hidden"))
        self.page.click('[data-testid="proto-build-toggle"]')
        self.assertTrue(self.page.js("document.getElementById('screen-menu').hidden"), "one drawer at a time")
        self.assertEqual(self.page.js("document.getElementById('itab-screen').getAttribute('aria-selected')"), "true")
        self.assertFalse(self.page.js("document.getElementById('inspect-screen').hidden"))
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.assertEqual(self.page.js("document.getElementById('itab-comments').getAttribute('aria-selected')"), "true")
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.assertFalse(self.page.js("document.getElementById('artboard').inert"), "a second press closes the panel")

    def test_the_board_the_system_and_compare_are_reachable(self):
        for testid in ("proto-view-board", "proto-view-system", "proto-view-prototype", "proto-compare", "proto-full-screen"):
            self.assertTrue(
                self.page.js(
                    f"(() => {{ const n = document.querySelector('[data-testid=\"{testid}\"]'); return n.getClientRects().length > 0 && n.getBoundingClientRect().width > 0; }})()"
                ),
                testid,
            )
        self.assertEqual(
            self.page.js("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), True, "one column, with no sideways scroll"
        )


@needs_chrome
class WindowTests(ViewerCase):
    """What the window size changes: the frame a phone opens, one row of controls, and the comments panel in the middle band."""

    def test_a_phone_window_opens_the_iphone_frame_and_leaves_it_out_of_the_link(self):
        self.open("#sitters/success", (390, 844))
        self.assertEqual(self.page.js("document.getElementById('frame-pick').value"), "ios")
        self.assertEqual(self.hash(), "#sitters/success", "the window's own frame is no part of the link")

    def test_a_frame_in_the_link_wins_at_any_width(self):
        self.open("#sitters/success?frame=1024", (390, 844))
        self.assertEqual(self.page.js("document.getElementById('frame-pick').value"), "1024")
        self.assertEqual(self.hash(), "#sitters/success?frame=1024")
        self.open("#sitters/success", WIDE)
        self.assertEqual(self.page.js("document.getElementById('frame-pick').value"), "1024")

    def bar_rows(self) -> int:
        """How many rows of controls the bar holds: its height, in rows of about 44 px."""
        return round(self.page.js("document.querySelector('.pv-bar').getBoundingClientRect().height") / 44)

    def test_the_controls_make_one_row_from_1280_up_and_on_the_board_at_1440(self):
        self.open("#sitters/success", LAPTOP)
        self.assertEqual(self.bar_rows(), 1)
        self.open("#sitters/success?view=board", (1440, 900))
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 15")
        self.assertEqual(self.bar_rows(), 1)

    def test_fit_and_100_percent_sit_in_the_caption_and_on_the_board_in_the_bar(self):
        # R257 (2): the caption holds the frame's zoom beside its size, so the bar keeps one row; the Board has no caption.
        for size in (LAPTOP, (1600, 1000)):
            self.open("#sitters/success", size)
            self.assertEqual(self.page.js("document.getElementById('zoom-group').parentElement.id"), "caption")
        self.page.click('[data-testid="proto-view-board"]')
        self.assertEqual(self.page.js("document.getElementById('zoom-group').parentElement.className"), "pv-bar")
        self.page.click('[data-testid="proto-view-prototype"]')
        self.assertEqual(self.page.js("document.getElementById('zoom-group').parentElement.id"), "caption")

    ON_SCREEN = """((id) => { const n = document.getElementById(id); const r = n.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return r.width > 0 && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight && Boolean(hit) && n.contains(hit); })"""

    def assert_on_screen(self, element_id: str, why: str) -> None:
        self.assertTrue(self.page.js(f"({self.ON_SCREEN})({json.dumps(element_id)})"), why)

    SETTLED = "Math.abs(document.getElementById('frame').getBoundingClientRect().width - parseFloat(document.getElementById('device-slot').style.width)) < 1"

    def test_the_comments_drawer_overlays_the_artboard_in_the_middle_band_and_the_approve_line_shows(self):
        self.open("#sitters/success", (1024, 768))
        self.page.wait(self.SETTLED)
        before = self.page.js("document.getElementById('frame').getBoundingClientRect().width")
        self.assertGreater(before / 1024, 0.55)
        self.assert_on_screen("caption-next", "the line to type is on screen with the drawer closed")
        self.assertEqual(self.bar_rows(), 1)
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.assertEqual(
            self.page.js("document.getElementById('frame').getBoundingClientRect().width"), before, "with comments off the drawer covers the artboard"
        )
        self.assertEqual(self.page.js("document.getElementById('workspace').dataset.dock"), "false")
        # The caption sits in the part of the artboard that shows, so the drawer never hides it.
        self.assertTrue(
            self.page.js(
                "(() => { const c = document.getElementById('caption-size').getBoundingClientRect(); const d = document.getElementById('inspector').getBoundingClientRect(); return c.right <= d.left; })()"
            )
        )

    def test_while_add_a_comment_is_on_the_drawer_docks_and_the_frame_fits_the_space_left(self):
        self.open("#sitters/success", (1024, 768))
        self.page.wait(self.SETTLED)
        before = self.page.js("document.getElementById('frame').getBoundingClientRect().width")
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.page.click('[data-testid="proto-comments-toggle"]')
        self.assertEqual(self.page.js("document.getElementById('workspace').dataset.dock"), "true")
        self.page.wait(f"{self.SETTLED} && document.getElementById('frame').getBoundingClientRect().width < {before} - 1")
        after = self.page.js("document.getElementById('frame').getBoundingClientRect().width")
        self.assertLess(after, before, "the artboard made room")
        self.assertTrue(
            self.page.js(
                "(() => { const f = document.getElementById('frame').getBoundingClientRect(); const d = document.getElementById('inspector').getBoundingClientRect(); return f.right <= d.left; })()"
            ),
            "no part of the frame is under the drawer",
        )
        self.page.click('[data-testid="proto-comments-toggle"]')
        self.assertEqual(self.page.js("document.getElementById('workspace').dataset.dock"), "false", "off again, it overlays")

    def test_the_approve_line_is_on_screen_at_phone_width_too(self):
        self.open("#sitters/success", (390, 844))
        self.assert_on_screen("caption-next", "the line to type shows under the frame at 390")

    def test_the_theme_is_an_axis_of_the_frame_control_at_every_width_and_checks_holds_only_the_checks(self):
        # R257 (2): the theme sits with the frame, never in Checks.
        for size in ((1600, 1000), LAPTOP, (1024, 768), (390, 844)):
            with self.subTest(size=size):
                self.open("#sitters/success", size)
                self.assertEqual(self.page.js("document.getElementById('theme-group').parentElement.className"), "pv-frameset")
                self.assertEqual(self.page.js("[...document.getElementById('checks-menu').children].filter((n) => !n.hidden).length"), 3)

    def test_in_the_middle_band_add_a_comment_is_in_the_bar(self):
        # R257 (3): from 48rem to 80rem (768 to 1279 px) the comments are a closed drawer, so the bar holds Add a comment, and it docks the drawer.
        self.open("#sitters/success", (1024, 768))
        self.assert_on_screen("bar-comment", "Add a comment shows in the artboard bar")
        self.assertEqual(self.bar_rows(), 1)
        self.page.click('[data-testid="proto-bar-comment"]')
        self.assertEqual(
            self.page.js("[document.getElementById('bar-comment').getAttribute('aria-pressed'), document.getElementById('workspace').dataset.dock]"),
            ["true", "true"],
        )
        self.open("#sitters/success", LAPTOP)
        self.assertEqual(self.page.js("document.getElementById('bar-comment').getClientRects().length"), 0, "a wide window shows the comments panel itself")

    def test_at_phone_width_a_phone_fits_by_its_width_and_the_artboard_scrolls(self):
        # R257 (4): a whole phone at 390 was half size; by its width it reads, with no sideways scroll.
        self.open("#sitters/success", (390, 844))
        self.page.wait("document.getElementById('workspace').dataset.ready === 'true'")
        scale = self.page.js("parseFloat(document.getElementById('device').style.getPropertyValue('--pv-scale'))")
        self.assertGreater(scale, 0.8)
        self.assertEqual(
            self.page.js(
                "(() => { const s = document.getElementById('scroller'); return [s.scrollWidth <= s.clientWidth, s.scrollHeight > s.clientHeight]; })()"
            ),
            [True, True],
        )

    def test_a_frame_in_the_link_round_trips_on_a_wide_window(self):
        self.open("#sitters/success?frame=1024")
        self.assertEqual(self.hash(), "#sitters/success?frame=1024", "a named frame is written even when it is the default")
        self.page.reload()
        self.assertEqual(self.hash(), "#sitters/success?frame=1024")

    def test_the_first_fit_does_not_animate_and_a_frame_change_does(self):
        self.open("#sitters/success", LAPTOP)
        self.assertEqual(self.page.js("getComputedStyle(document.getElementById('device')).transitionDuration"), "0s")
        self.page.js("document.getElementById('frame-pick').value = 'ios'; document.getElementById('frame-pick').dispatchEvent(new Event('change'))")
        self.assertIn("move", self.page.js("Object.keys(document.getElementById('device').dataset).join()"))


@needs_chrome
class EmptyRoundTests(ViewerCase):
    def test_an_empty_round_draws_download_as_a_plain_button_and_hides_the_count(self):
        self.open("#sitters/success")
        self.assertEqual(self.page.js("getComputedStyle(document.getElementById('comments-download')).opacity"), "1")
        self.assertEqual(self.page.js("document.getElementById('comments-download').getAttribute('aria-disabled')"), "true")
        self.assertEqual(self.page.js("document.getElementById('comments-count').getClientRects().length"), 0)

    def test_the_screens_button_and_the_bracket_key_do_nothing_on_the_board(self):
        self.open("#sitters/success?view=board")
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 15")
        panels = "document.getElementById('workspace').dataset.panels"
        self.assertEqual(self.page.js(panels), "both")
        self.page.click('[data-testid="proto-screens-toggle"]')
        self.assertEqual((self.page.js(panels), self.hash()), ("both", "#sitters/success?view=board"), "the button wrote no panels key")
        self.page.press("[")
        self.assertEqual((self.page.js(panels), self.hash()), ("both", "#sitters/success?view=board"), "the key wrote none")
        self.assertIn("Board", self.page.js("document.querySelector('[data-testid=proto-screens-toggle]').title"))
        self.page.click('[data-testid="proto-view-prototype"]')
        self.assertEqual(self.page.js("getComputedStyle(document.getElementById('screen-menu')).display !== 'none'"), True, "the review column is back")

    def test_the_with_comments_filter_says_when_no_state_has_a_comment(self):
        self.open("#sitters/success?view=board")
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 15")
        self.page.click('[data-testid="proto-board-commented"]')
        self.assertFalse(self.page.js("document.getElementById('board-empty').hidden"))
        self.assertEqual(self.page.js("document.getElementById('board-empty').textContent"), "No state has a comment yet.")


@needs_chrome
class FrameLinkTests(ViewerCase):
    """A frame the link named or a person picked stays in the link at any width; only the phone default stays out."""

    def test_a_link_that_names_the_iphone_keeps_it_at_phone_width(self):
        self.open("#sitters/success?frame=ios", (390, 844))
        self.assertEqual(self.hash(), "#sitters/success?frame=ios")

    def test_a_frame_picked_at_phone_width_is_written(self):
        self.open("#sitters/success", (390, 844))
        self.page.js("document.getElementById('frame-pick').value = '1024'; document.getElementById('frame-pick').dispatchEvent(new Event('change'))")
        self.assertEqual(self.hash(), "#sitters/success?frame=1024")

    def test_a_comment_made_at_phone_width_stores_the_iphone_frame_and_a_link_that_opens_it(self):
        self.open("#sitters/success?comments=1", (390, 844))
        self.page.js("document.getElementById('frame-pick').value === 'ios' || (() => { throw new Error('not the iPhone frame') })()")
        self.page.js(f"{CARD}[0].click()")
        self.page.js("document.getElementById('comment-text').value = 'A comment on the phone.'; document.getElementById('comment-add').click()")
        item = json.loads(urllib.parse.unquote(self.page.js("document.getElementById('comments-download').getAttribute('href')").split(",", 1)[1]))["items"][0]
        self.assertEqual(item["frame"], "ios")
        self.assertIn("frame=ios", item["link"], "the link opens the frame the comment was made in, on any screen")

    def test_the_link_follows_the_window_across_the_phone_width(self):
        self.open("#sitters/success", (390, 844))
        self.assertEqual(self.hash(), "#sitters/success")
        self.page.call("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
        self.page.wait("document.getElementById('frame-pick').value === '1024'")
        self.assertEqual(self.hash(), "#sitters/success", "the default frame is out of the link at either width")


@needs_chrome
class BoardLoadTests(ViewerCase):
    def test_a_far_off_cell_has_no_document_until_it_scrolls_near(self):
        self.open("#sitters/success?view=board", (390, 844))
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 15")
        cell = "document.querySelector('[data-testid=proto-board-sitters-first-run]').parentElement.querySelector('iframe')"
        near = "document.querySelector('[data-testid=proto-board-sitters-empty]').parentElement.querySelector('iframe')"
        self.page.wait(f"{near}.contentDocument && {near}.contentDocument.body && {near}.contentDocument.body.childElementCount > 0")
        self.assertEqual(
            self.page.js(f"({cell}.contentDocument.body || {{childElementCount: 0}}).childElementCount"), 0, "the eighth state is far off the strip"
        )
        self.page.js(f"{cell}.closest('.pv-strip').scrollLeft = 10000")
        self.page.wait(f"({cell}.contentDocument.body || {{childElementCount: 0}}).childElementCount > 0")


@needs_chrome
class BoardPickTests(ViewerCase):
    def cell_text(self) -> str:
        cell = "document.querySelector('[data-testid=proto-board-sitter-success]').parentElement.querySelector('iframe')"
        self.page.wait(f"{cell}.contentDocument && {cell}.contentDocument.body && {cell}.contentDocument.body.childElementCount > 0")
        return self.page.js(f"{cell}.contentDocument.body.textContent")

    def test_a_cell_shows_the_sitter_picked_when_the_board_was_built(self):
        self.open("#sitters/success")
        self.page.click('[data-pick="1"]', 0, frame=True)
        self.page.wait("location.hash === '#sitter/success'")
        self.page.click('[data-testid="proto-view-board"]')
        self.assertIn("Tom\u00e1s Herrera", self.cell_text())
        self.page.click('[data-testid="proto-view-prototype"]')
        self.page.click('[data-testid="proto-screen-sitters"]')
        self.page.click('[data-pick="0"]', 0, frame=True)
        self.page.wait("location.hash === '#sitter/success'")
        self.page.click('[data-testid="proto-view-board"]')
        self.assertIn("Mai Nguyen", self.cell_text(), "a new pick rebuilds the board")


@needs_chrome
class PinTests(ViewerCase):
    """A pin is beside the element it marks and covers no text, at phone width."""

    OVERLAPS = """(() => {
      const frame = document.getElementById('frame'), d = frame.contentDocument, f = frame.getBoundingClientRect(), s = f.width / frame.offsetWidth;
      const rects = [];
      const walker = d.createTreeWalker(d.body, 4);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.nodeValue.trim()) continue;
        const range = d.createRange(); range.selectNodeContents(n);
        for (const r of range.getClientRects()) rects.push({ left: f.left + r.left * s, right: f.left + r.right * s, top: f.top + r.top * s, bottom: f.top + r.bottom * s });
      }
      return [...document.querySelectorAll('#pins .pv-pin')].map((pin) => {
        const p = pin.getBoundingClientRect();
        const hit = rects.filter((r) => p.left < r.right - 2 && p.right > r.left + 2 && p.top < r.bottom - 2 && p.bottom > r.top + 2);
        return [pin.textContent, hit.length];
      });
    })()"""

    def test_no_pin_covers_text_on_the_sitter_rows_or_a_full_width_title(self):
        self.open("#sitters/success?comments=1&frame=ios", (390, 844))
        self.page.click_at(5, 5)
        # The title spans the frame, so it is a full-width text element; give it a test id the way a design would.
        self.frame_js("d.getElementById('screen-title').setAttribute('data-testid', 'probe-title')")
        targets = [("probe-title", 0)] + [("sitter-card", i) for i in range(4)]
        for testid, index in targets:
            self.page.js(
                f"[...document.getElementById('frame').contentDocument.querySelectorAll('[data-testid={testid}]')].filter((n) => n.getClientRects().length)[{index}].click()"
            )
            self.page.js("document.getElementById('comment-text').value = 'A comment.'; document.getElementById('comment-add').click()")
        self.page.wait("document.querySelectorAll('#pins .pv-pin').length === 5")
        self.assertEqual([pin for pin in self.page.js(self.OVERLAPS) if pin[1]], [], "a pin covers text")

    def test_a_comment_on_the_third_card_has_one_pin_that_stays_inside_the_frame(self):
        self.open("#sitters/success?comments=1", WIDE)
        self.page.js(f"{CARD}[2].click()")
        self.page.js("document.getElementById('comment-text').value = 'A comment.'; document.getElementById('comment-add').click()")
        pin = self.page.js(
            "(() => { const p = document.querySelector('#pins .pv-pin'); const f = document.getElementById('frame').getBoundingClientRect(); const r = p.getBoundingClientRect(); return [r.left >= f.left, r.right <= f.right, r.top >= f.top, r.bottom <= f.bottom]; })()"
        )
        self.assertEqual(pin, [True, True, True, True])


@needs_chrome
class ShowScrollTests(ViewerCase):
    def test_show_scrolls_the_element_out_from_under_the_drawer_at_1024(self):
        self.open("#sitters/success?comments=1", (1024, 768))
        self.page.click_at(5, 5)
        self.page.js(f"{CARD}[2].click()")  # the third card's name reaches far to the right
        self.page.js("document.getElementById('comment-text').value = 'A comment.'; document.getElementById('comment-add').click()")
        self.page.js("document.querySelector('[data-comment-toggle]').click()")  # comments off, so the drawer overlays the artboard
        if self.page.js("document.getElementById('inspector').dataset.open") != "true":  # turning comments on opened it
            self.page.click('[data-testid="proto-inspector-toggle"]')
        self.assertEqual(self.page.js("document.getElementById('workspace').dataset.dock"), "false")
        self.page.click('[data-testid="proto-comments-item-r1-1"]')
        clear = """(() => {
          const frame = document.getElementById('frame'), d = frame.contentDocument, f = frame.getBoundingClientRect(), s = f.width / frame.offsetWidth;
          const n = [...d.querySelectorAll('[data-testid=sitter-card]')].filter((x) => x.getClientRects().length)[2];
          const right = f.left + n.getBoundingClientRect().right * s + 30;  // the pin sits just after the element
          return right <= document.getElementById('inspector').getBoundingClientRect().left;
        })()"""
        self.page.wait(clear)


@needs_chrome
class LayoutTests(ViewerCase):
    def test_the_breadcrumb_keeps_the_whole_state_name_at_1280(self):
        self.open("#sitters/permission-denied", LAPTOP)
        # Fonts differ by system (Linux's are wider than macOS's), so the screen name may give way; the state never does.
        cut = "(() => { const s = document.querySelector('#crumb .pv-crumb-state'), c = document.getElementById('crumb'); return s.scrollWidth > s.clientWidth || s.getBoundingClientRect().right > c.getBoundingClientRect().right + 0.5; })()"
        self.assertFalse(self.page.js(cut), "the state's name is cut")
        self.assertEqual(self.page.js("document.querySelector('#crumb .pv-crumb-state').textContent"), "Permission denied")

    def test_the_round_is_a_narrow_field_an_arrow_key_never_changes(self):
        self.open("#sitters/success")
        self.assertLess(self.page.js("document.getElementById('round-number').getBoundingClientRect().width"), 56, "as wide as its number")
        self.assertFalse(self.page.js("getComputedStyle(document.getElementById('round-number')).borderTopColor === 'rgba(0, 0, 0, 0)'"), "it shows its edge")
        self.page.js("document.getElementById('round-number').focus()")
        self.page.press("ArrowUp")
        self.assertEqual((self.page.js("document.getElementById('round-number').value"), self.hash()), ("1", "#sitters/success"))
        self.page.js("document.getElementById('round-number').select()")
        self.page.type_text("2")
        self.page.press("Enter")
        self.assertEqual(self.hash(), "#sitters/success?round=2", "a number and Enter open the round")

    def test_full_screen_hides_the_line_to_type_too(self):
        self.open("#sitters/success", (1024, 768))
        self.assertTrue(self.page.js("document.getElementById('caption-next').getClientRects().length > 0"))
        self.page.press("f")
        self.page.wait("document.getElementById('workspace').dataset.present === 'true'")
        self.assertEqual(self.page.js("document.getElementById('caption-next').getClientRects().length"), 0)


@needs_chrome
class ImageFieldTests(ViewerCase):
    def test_each_row_shows_its_own_sitters_image(self):
        # R249: an image field shows the image each item's fixture names, read into the page as a data URI.
        self.open("#sitters/success")
        sources = self.frame_js(
            "[...d.querySelectorAll('section.shown [data-state].shown img[data-image]')].map((i) => i.currentSrc.slice(0, 26) + ' ' + i.naturalWidth)"
        )
        self.assertEqual(len(sources), 4)
        self.assertTrue(all(s.startswith("data:image/svg+xml;base64") and not s.endswith(" 0") for s in sources), sources)
        self.assertEqual(len(set(self.frame_js("[...d.querySelectorAll('section.shown [data-state].shown img[data-image]')].map((i) => i.src)"))), 4)


@needs_chrome
class DeviceFrameTests(ViewerCase):
    """Each frame is drawn from its row of the device table (devices.json), as a person sees it."""

    TABLE = json.loads((PROTOTYPE_TOOL / "devices.json").read_text(encoding="utf-8"))["frames"]

    def test_each_phone_draws_the_system_bars_of_its_row_and_the_product_clears_them(self):
        phones = {key: f for key, f in self.TABLE.items() if "safe_area" in f}
        self.assertTrue(phones)
        for key, frame in phones.items():
            with self.subTest(frame=key):
                self.open(f"#sitters/success?frame={key}&safe=1")
                drawn = self.page.js(
                    "(() => { const d = document.getElementById('frame').contentDocument.documentElement.style;"
                    " return [document.querySelector('.pv-status').offsetHeight, document.querySelector('.pv-safe-top').offsetHeight,"
                    " document.querySelector('.pv-safe-bottom').offsetHeight, d.getPropertyValue('--safe-area-inset-top'), d.getPropertyValue('--safe-area-inset-bottom')]; })()"
                )
                top, bottom = frame["safe_area"]["top"], frame["safe_area"]["bottom"]
                self.assertEqual(drawn, [top, top, bottom, f"{top}px", f"{bottom}px"])

    def test_every_frame_is_its_rows_size_keeps_it_as_its_content_scrolls_and_fit_shows_it_whole(self):
        measure = (
            "(() => { const f = document.getElementById('frame'), se = f.contentDocument.scrollingElement, size = [f.offsetWidth, f.offsetHeight];"
            " se.scrollTop = se.scrollHeight; const after = [f.offsetWidth, f.offsetHeight], scrolled = se.scrollTop > 0;"
            " const s = document.getElementById('shell').getBoundingClientRect(), a = document.getElementById('scroller').getBoundingClientRect();"
            " return { size, after, scrolled, inside: s.left >= a.left && s.right <= a.right && s.top >= a.top && s.bottom <= a.bottom,"
            " caption: document.getElementById('caption-size').textContent }; })()"
        )
        scrolled = []
        for key, frame in self.TABLE.items():
            with self.subTest(frame=key):
                self.open(f"#sitters/success?frame={key}")
                got = self.page.js(measure)
                want = [frame["width"], frame["height"]]
                self.assertEqual((got["size"], got["after"]), (want, want), "the frame has its row's size and keeps it")
                self.assertTrue(got["inside"], "Fit shows the whole frame in the artboard")
                self.assertTrue(got["caption"].startswith(f"{frame['name']}, {frame['width']} by {frame['height']}"), got["caption"])
                if got["scrolled"]:
                    scrolled.append(key)
        self.assertIn("320", scrolled, "a design longer than the frame scrolls inside it")


if __name__ == "__main__":
    unittest.main()
