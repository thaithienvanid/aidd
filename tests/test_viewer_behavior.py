"""The prototype viewer's keys and links, driven in a real browser: the drawers and full screen, Back from the Board, the
state radio group, the shortcut sheet and its switch, the deep-link keys, and a link to a screen or state the design lacks.

The set-up they share, and how the browser starts, is in `viewer_browser.py`.
"""

from __future__ import annotations

import unittest

import viewer_browser as vb
from browser_driver import needs_chrome
from viewer_browser import BROKEN_PAGE, NARROW, STATES


SESSION: dict = {}  # the module's one server and browser: "origin", "browser", and "page"


def setUpModule():
    vb.start(SESSION)


class ViewerCase(vb.ViewerCase):
    session = SESSION


@needs_chrome
class DrawerTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.open("#sitters/success", NARROW)
        self.page.js(
            "window.__clicks = []; document.getElementById('frame').contentDocument.addEventListener('click', (e) => window.__clicks.push(e.target.tagName), true)"
        )

    def inert(self) -> bool:
        return self.page.js("document.getElementById('artboard').inert")

    def frame_click(self, x_share: float) -> int:
        """A real click at a share of the way across the frame; how many clicks the frame has received."""
        left, top, width = self.page.js(
            "(() => { const r = document.getElementById('frame').getBoundingClientRect(); return [r.left, r.top + r.height / 2, r.width]; })()"
        )
        self.page.click_at(left + width * x_share, top)
        return self.page.js("window.__clicks.length")

    def test_the_screens_drawer_makes_the_artboard_inert_and_blocks_the_frame(self):
        self.assertFalse(self.inert())
        self.page.click('[data-testid="proto-screens-toggle"]')
        self.assertTrue(self.inert())
        self.assertFalse(self.page.js("document.getElementById('screen-menu').hidden"))
        self.assertEqual(self.frame_click(0.9), 0, "a click on an inert artboard must not reach the frame")

    def test_the_inspector_drawer_makes_the_artboard_inert_too(self):
        self.page.click('[data-testid="proto-inspector-toggle"]')
        self.assertTrue(self.inert())
        self.page.press("Escape")
        self.assertFalse(self.inert())

    def test_f_leaves_the_drawer_and_the_frame_takes_clicks(self):
        self.page.click('[data-testid="proto-screens-toggle"]')
        self.assertTrue(self.inert())
        self.page.press("f")
        self.page.wait("document.getElementById('workspace').dataset.present === 'true'")
        self.assertFalse(self.inert())
        self.assertEqual(self.page.js("document.getElementById('present').getAttribute('aria-pressed')"), "true")
        self.assertEqual(self.frame_click(0.5), 1, "a click in full screen must reach the frame")
        self.page.press("Escape")
        self.page.wait("document.getElementById('workspace').dataset.present === 'false'")

    def test_the_artboard_stays_inert_only_while_a_drawer_is_open(self):
        self.page.click('[data-testid="proto-screens-toggle"]')
        self.page.press("Escape")
        self.assertFalse(self.inert())
        self.assertEqual(self.frame_click(0.5), 1)


@needs_chrome
class NavigationTests(ViewerCase):
    def board(self, screen_state: str) -> None:
        self.open("#sign-in/empty?view=board")
        self.page.wait("document.querySelectorAll('#board .pv-thumb').length >= 3")
        self.assertEqual(self.page.js("document.getElementById('tab-board').getAttribute('aria-selected')"), "true")
        self.page.click(f'[data-testid="proto-board-{screen_state}"]')
        self.page.wait(f"location.hash === '#{screen_state.replace('-success', '/success')}'")
        self.assertEqual(self.page.js("document.getElementById('tab-prototype').getAttribute('aria-selected')"), "true")

    def assert_on_the_board(self):
        self.page.wait("location.hash === '#sign-in/empty?view=board'")
        self.assertEqual(self.page.js("document.getElementById('tab-board').getAttribute('aria-selected')"), "true")
        self.assertEqual(self.page.js("document.getElementById('tab-prototype').getAttribute('aria-selected')"), "false")
        self.assertFalse(self.page.js("document.getElementById('panel-board').hidden"))
        self.assertTrue(self.page.js("document.getElementById('panel-prototype').hidden"))

    def test_history_back_from_a_screen_opened_on_the_board_returns_to_the_board(self):
        self.board("sitters-success")
        self.page.js("history.back()")
        self.assert_on_the_board()

    def test_the_frames_back_button_returns_to_the_board(self):
        self.board("sitter-success")
        self.assertFalse(self.frame_js("d.querySelector('[data-back]').hidden"))
        self.page.click("[data-back]", frame=True)
        self.assert_on_the_board()

    def test_back_then_forward_returns_to_the_screen(self):
        self.board("sitters-success")
        self.page.js("history.back()")
        self.assert_on_the_board()
        self.page.js("history.forward()")
        self.page.wait("location.hash === '#sitters/success'")
        self.assertEqual(self.page.js("document.getElementById('tab-prototype').getAttribute('aria-selected')"), "true")


@needs_chrome
class StateTests(ViewerCase):
    def state(self) -> str:
        return self.page.js("document.querySelector('#state-group [aria-checked=true]').dataset.show")

    def focus(self, state: str) -> None:
        self.page.click(f'[data-testid="proto-state-{state}"]')
        self.assertEqual(self.state(), state)

    def test_arrow_right_checks_the_next_enabled_state_and_updates_the_link(self):
        self.open("#sign-in/loading")  # a sign-in screen has no partial state, so the next enabled one is error
        self.focus("loading")
        self.page.press("ArrowRight")
        self.assertEqual(self.state(), "error")
        self.assertEqual(self.hash(), "#sign-in/error")
        self.assertEqual(self.page.js("document.activeElement.dataset.show"), "error", "focus follows the checked state")
        self.assertEqual(
            self.page.js("[...document.querySelectorAll('#state-group [role=radio]')].filter((r) => r.tabIndex === 0).map((r) => r.dataset.show)"), ["error"]
        )
        self.assertEqual(self.frame_js("d.querySelector('section.shown > [data-state].shown').dataset.state"), "error")

    def test_the_arrows_wrap_and_home_and_end_go_to_the_ends(self):
        self.open("#sign-in/loading")
        self.focus("loading")
        for key, state in (
            ("ArrowLeft", "empty"),
            ("ArrowLeft", "offline"),
            ("ArrowRight", "empty"),
            ("End", "offline"),
            ("Home", "empty"),
            ("ArrowDown", "loading"),
            ("ArrowUp", "empty"),
        ):
            self.page.press(key)
            self.assertEqual((self.state(), self.hash()), (state, f"#sign-in/{state}"), key)

    def test_a_state_the_screen_lacks_cannot_be_checked_and_the_number_keys_skip_none(self):
        self.open("#sign-in/empty")
        self.assertEqual(
            self.page.js("[...document.querySelectorAll('#state-group [role=radio]:disabled')].map((r) => r.dataset.show)"),
            ["partial", "permission-denied", "success", "first-run"],
        )
        self.assertEqual(
            self.page.js("[...document.querySelectorAll('#state-group [role=radio]:not(:disabled) kbd')].map((k) => k.textContent)"), ["1", "2", "3", "4"]
        )
        self.page.press("3")
        self.assertEqual(self.state(), "error", "3 is the third state the list shows")
        self.page.press("5")
        self.assertEqual(self.state(), "error", "a number past the list does nothing")

    def test_keys_1_to_8_still_show_each_state(self):
        self.open("#sitters/empty")
        for number, state in enumerate(STATES, start=1):
            self.page.press(str(number))
            self.assertEqual((self.state(), self.hash()), (state, f"#sitters/{state}"), f"key {number}")
            self.assertEqual(self.frame_js("d.querySelector('section.shown > [data-state].shown').dataset.state"), state)

    def test_a_number_key_still_works_with_focus_on_a_radio(self):
        self.open("#sitters/empty")
        self.focus("empty")
        self.page.press("7")
        self.assertEqual(self.state(), "success")


@needs_chrome
class DeepLinkTests(ViewerCase):
    CASES = {
        "view=system": (
            "#sign-in/empty?view=system",
            "document.getElementById('tab-system').getAttribute('aria-selected') === 'true' && !document.getElementById('panel-system').hidden && document.querySelectorAll('#system-components .pv-component').length > 0",
        ),
        "safe=1": (
            "#sign-in/empty?frame=ios&safe=1",
            "document.getElementById('shell').dataset.safe === 'on' && document.getElementById('checks-count').textContent === '1' && getComputedStyle(document.querySelector('.pv-safe-top')).display !== 'none'",
        ),
        "comments=1": (
            "#sign-in/empty?comments=1",
            "document.querySelector('[data-comment-toggle]').getAttribute('aria-pressed') === 'true' && !document.getElementById('comments').hidden && document.documentElement.dataset.commenting === 'on'",
        ),
        "text=200": (
            "#sign-in/empty?text=200",
            "document.getElementById('frame').contentDocument.documentElement.style.fontSize === '200%' && document.querySelector('[data-check=text]').getAttribute('aria-pressed') === 'true'",
        ),
        "dir=rtl": (
            "#sign-in/empty?dir=rtl",
            "document.getElementById('frame').contentDocument.documentElement.dir === 'rtl' && document.querySelector('[data-check=dir]').getAttribute('aria-pressed') === 'true'",
        ),
        "show=unseen": (
            "#sign-in/empty?view=board&show=unseen",
            "document.querySelector('[data-testid=proto-board-unseen]').getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#board .pv-thumb[data-dim]').length === 1",
        ),
        "compare=1": (
            "#sign-in/empty?compare=1",
            "document.getElementById('compare').getAttribute('aria-pressed') === 'true' && !document.getElementById('compare-side').hidden && !document.getElementById('compare-beside')",
        ),
        "side=build": ("#sign-in/empty?side=build", "document.getElementById('itab-screen').getAttribute('aria-selected') === 'true'"),
    }

    def test_the_old_board_key_still_opens_the_board(self):
        self.open("#sign-in/empty?view=canvas")
        self.page.wait("document.getElementById('tab-board').getAttribute('aria-selected') === 'true'")
        self.assertEqual(self.hash(), "#sign-in/empty?view=board", "the link is written again with the new key")

    def test_each_key_opens_its_view_and_the_link_round_trips(self):
        for name, (link, shows) in self.CASES.items():
            with self.subTest(name):
                self.open(link)
                self.page.wait(shows)
                self.assertEqual(self.hash(), link, "the viewer rewrites the address to the same link")
                self.page.reload()
                self.page.wait(shows)
                self.assertEqual(self.hash(), link, "and the link survives a reload")

    def test_the_checks_write_their_keys_in_the_link(self):
        self.open("#sign-in/empty")
        self.page.click('[data-testid="proto-checks"]')
        for testid, link in (
            ("proto-check-text", "#sign-in/empty?text=200"),
            ("proto-check-rtl", "#sign-in/empty?text=200&dir=rtl"),
            ("proto-check-safe-areas", "#sign-in/empty?text=200&dir=rtl&safe=1"),
        ):
            self.page.click(f'[data-testid="{testid}"]')
            self.assertEqual(self.hash(), link)
        self.page.click('[data-testid="proto-comments-toggle"]')
        self.assertEqual(self.hash(), "#sign-in/empty?text=200&dir=rtl&safe=1&comments=1")
        link = self.hash()
        self.open(link)
        self.assertEqual(self.page.js("document.getElementById('checks-count').textContent"), "3")
        self.assertEqual(self.hash(), link)

    def test_the_view_tabs_write_the_view_key(self):
        self.open("#sign-in/empty")
        self.page.click('[data-testid="proto-view-system"]')
        self.assertEqual(self.hash(), "#sign-in/empty?view=system")
        self.page.click('[data-testid="proto-view-board"]')
        self.assertEqual(self.hash(), "#sign-in/empty?view=board")
        self.page.click('[data-testid="proto-view-prototype"]')
        self.assertEqual(self.hash(), "#sign-in/empty")


@needs_chrome
class KeyGuardTests(ViewerCase):
    """A key typed in a field is the field's own. These send real key presses, which `Input.insertText` does not."""

    KEYS_TO_TRY = ("n", "j", "k", "c", "?", "1", "[", "]", "f", "v", "t", "d")

    def state(self):
        return (
            self.hash(),
            self.page.js("document.getElementById('workspace').dataset.panels"),
            self.page.js("document.getElementById('workspace').dataset.present"),
            self.page.js("document.querySelector('[data-comment-toggle]').getAttribute('aria-pressed')"),
            self.page.js("document.getElementById('shortcuts').open"),
        )

    def assert_keys_do_nothing(self, focus: str):
        before = self.state()
        for key in self.KEYS_TO_TRY:
            self.page.js(focus)
            self.page.press(key)
        self.assertEqual(self.state(), before, focus)

    def test_keys_typed_in_the_comment_the_filter_and_the_round_do_nothing_else(self):
        self.open("#sitters/loading?comments=1")
        for field in ("comment-text", "screen-filter", "round-number", "comment-target"):
            self.assert_keys_do_nothing(f"document.getElementById('{field}').focus()")

    def test_keys_typed_in_a_field_of_the_prototype_do_nothing_else(self):
        self.open("#sign-in/empty")
        self.assert_keys_do_nothing("document.getElementById('frame').contentDocument.querySelector('[data-testid=signin-email]').focus()")
        self.assertIn("n", self.frame_js("d.querySelector('[data-testid=signin-email]').value"), "the field took the key")

    def test_the_open_sheet_takes_the_keys_n_and_f(self):
        self.open("#sitters/loading")
        self.page.press("?")
        self.assertTrue(self.page.js("document.getElementById('shortcuts').open"))
        for key in ("n", "f", "j", "c"):
            self.page.press(key)
        self.assertEqual(self.hash(), "#sitters/loading")
        self.assertNotEqual(self.page.js("document.getElementById('workspace').dataset.present"), "true")
        self.assertTrue(self.page.js("document.getElementById('shortcuts').open"))


@needs_chrome
class SingleKeySwitchTests(ViewerCase):
    """WCAG 2.1.4: single-key shortcuts can be switched off, and the choice is kept."""

    SWITCH = '[data-testid="proto-shortcuts-switch"]'

    def switch(self, state: str):
        self.assertEqual(self.page.js(f"document.querySelector('{self.SWITCH}').getAttribute('aria-checked')"), state)

    def test_off_means_no_key_acts_alone_and_the_buttons_still_do(self):
        self.open("#sitters/empty")
        self.page.click('[data-testid="proto-shortcuts"]')
        self.switch("true")
        self.page.click(self.SWITCH)
        self.switch("false")
        self.page.press("Escape")
        for key in ("n", "j", "2", "c", "f", "[", "?", "v", "t", "d"):
            self.page.press(key)
        self.assertEqual(self.hash(), "#sitters/empty")
        self.assertFalse(self.page.js("document.getElementById('shortcuts').open"))
        self.page.click('[data-testid="proto-next-state"]')
        self.assertEqual(self.hash(), "#sitters/loading", "the button still steps")

    def test_the_choice_is_kept_after_a_reload(self):
        self.open("#sitters/empty")
        self.page.click('[data-testid="proto-shortcuts"]')
        self.page.click(self.SWITCH)
        self.page.reload()
        self.page.click('[data-testid="proto-shortcuts"]')
        self.switch("false")
        self.page.click(self.SWITCH)
        self.page.press("Escape")
        self.page.press("j")
        self.assertEqual(self.hash(), "#sitters/loading", "on again, J steps")


@needs_chrome
class ShortcutsOffTests(ViewerCase):
    SWITCH = '[data-testid="proto-shortcuts-switch"]'

    def test_off_removes_every_hint_of_a_key_and_on_brings_each_back(self):
        self.open("#sitters/loading")
        hints = "[...document.querySelectorAll('[aria-keyshortcuts]')].length"
        titles = "document.querySelector('[data-testid=proto-full-screen]').title"
        self.assertGreater(self.page.js(hints), 0)
        self.assertIn("(F)", self.page.js(titles))
        self.page.click('[data-testid="proto-shortcuts"]')
        self.page.click(self.SWITCH)
        self.assertEqual(self.page.js(hints), 0)
        self.assertNotIn("(F)", self.page.js(titles))
        self.assertEqual(self.page.js("getComputedStyle(document.querySelector('#next-unseen kbd')).display"), "none")
        self.assertNotIn("(?)", self.page.js("document.getElementById('shortcuts-open').getAttribute('aria-label')"))
        self.page.click(self.SWITCH)
        self.assertGreater(self.page.js(hints), 0)
        self.assertIn("(F)", self.page.js(titles))

    def test_off_a_question_mark_does_not_close_the_sheet_but_escape_does(self):
        self.open("#sitters/loading")
        self.page.click('[data-testid="proto-shortcuts"]')
        self.page.click(self.SWITCH)
        self.page.press("?")
        self.assertTrue(self.page.js("document.getElementById('shortcuts').open"))
        self.page.press("Escape")
        self.assertFalse(self.page.js("document.getElementById('shortcuts').open"))

    def test_the_switch_is_reachable_at_phone_width(self):
        self.open("#sitters/success", (390, 844))
        self.page.click('[data-testid="proto-shortcuts"]')
        self.assertTrue(self.page.js("document.getElementById('shortcuts').open"))
        self.page.click(self.SWITCH)
        self.assertEqual(self.page.js(f"document.querySelector('{self.SWITCH}').getAttribute('aria-checked')"), "false")


@needs_chrome
class LinkProblemTests(ViewerCase):
    """A link that opens something other than it names says so, and the fallback it shows never counts as seen."""

    PROBLEM = "document.getElementById('link-problem')"

    def test_an_unknown_screen_says_what_shows_instead_and_is_not_seen_until_you_move(self):
        self.open("#siters/success?frame=ipad")
        self.assertEqual(
            self.page.js(f"{self.PROBLEM}.hidden ? '' : {self.PROBLEM}.textContent"),
            "No screen siters: showing Sign in, Empty; No frame ipad: showing Web, 1024 wide",
        )
        self.assertIn("aidd prototype viewer: No screen `siters`: showing Sign in, Empty; No frame `ipad`: showing Web, 1024 wide", self.page.warnings)
        self.assertEqual(self.seen_here(), "0 of 15", "the fallback is not what the link asked for")
        self.page.click('[data-testid="proto-state-error"]')
        self.assertTrue(self.page.js(f"{self.PROBLEM}.hidden"), "a person moved on, so the banner goes")
        self.assertEqual(self.seen_here(), "1 of 15")

    def test_a_typed_link_to_a_state_the_screen_lacks_says_so(self):
        self.open("#sitters/success")
        self.page.js("location.hash = '#sign-in/succes'")
        self.page.wait(f"!{self.PROBLEM}.hidden")
        self.assertEqual(self.page.js(f"{self.PROBLEM}.textContent"), "Sign in has no state succes: showing Empty")

    def test_a_dead_link_in_the_design_says_where_it_goes_and_the_page_names_the_designs_problems(self):
        self.open("#sitters/success", path=BROKEN_PAGE)
        self.page.wait("!document.getElementById('design-problems').hidden")
        self.assertRegex(self.page.js("document.getElementById('design-problems-h').textContent"), r"^[0-9]+ problems? in this design$")
        self.assertIn("sitterz", self.page.js("document.getElementById('design-problems-list').textContent"))
        self.frame_js("d.querySelector('[data-go=sitterz]').click()")
        self.assertEqual(self.page.js(f"{self.PROBLEM}.textContent"), "This link goes to sitterz, which no screen has")
        self.assertEqual(self.hash(), "#sitters/success", "the view stays where it was")
        self.open("#sitters/success")
        self.assertTrue(self.page.js("document.getElementById('design-problems').hidden"), "a sound design shows no banner")


@needs_chrome
class ReadyTests(ViewerCase):
    """A script that takes a screenshot waits for `data-ready`: the frame painted with its fonts, and the Board's cells loaded."""

    def test_the_workspace_and_the_board_say_when_they_are_ready(self):
        self.open("#sitters/success")
        self.page.wait("document.getElementById('workspace').dataset.ready === 'true'")
        self.page.js("document.getElementById('frame-pick').value = 'ios'; document.getElementById('frame-pick').dispatchEvent(new Event('change'))")
        self.assertEqual(self.page.js("document.getElementById('workspace').dataset.ready"), "false", "not ready while the device moves")
        self.page.wait("document.getElementById('workspace').dataset.ready === 'true'")
        self.page.click('[data-testid="proto-view-board"]')
        self.page.wait("document.getElementById('board').dataset.ready === 'true'")
        loaded = "[...document.querySelectorAll('#board .pv-thumb iframe')].filter((f) => f.contentDocument && f.contentDocument.querySelector('section.shown')).length"
        self.assertGreaterEqual(self.page.js(loaded), 15, "every cell in view has loaded")


if __name__ == "__main__":
    unittest.main()
