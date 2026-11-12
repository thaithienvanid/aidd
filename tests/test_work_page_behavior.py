"""The work-items page's keyboard and URL behavior, driven in a real browser.

`test_work_item_page.py` reads the page as text. This module runs its script: it opens the page by file URL, presses keys, and
clicks as a person does, by the prototype's `data-testid` names. It covers `/` and a search for "thong bao", Enter, Esc, J and
K, C, 1 to 3, and `?`, the off switch for single keys, no key acting inside the search field, focus on open, and a URL round
trip for each view. Opt in with `AIDD_BROWSER_TESTS=1` (see `browser_driver.py`); an opted-in run with no Chrome fails.
"""

from __future__ import annotations

import json
import unittest

import helpers  # noqa: F401
import work_page_browser as wb
from browser_driver import needs_chrome

SESSION: dict = {}
PREF = "aidd-viewer:single-key-shortcuts"  # the viewer's stored setting, written only when a person flips the switch


def relative_luminance(*rgb: float) -> float:
    """WCAG 2.2's relative luminance of sRGB channels from 0 to 1."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def setUpModule():
    wb.start(SESSION, "work-page-behavior-")


class Behavior(wb.PageCase):
    session = SESSION

    def views(self) -> list[str]:
        return self.shown("section[data-view]")

    def active(self) -> str:
        return self.page.js(
            "(() => { const a = document.activeElement; return a.getAttribute('data-testid') || a.getAttribute('data-field') || a.tagName; })()"
        )

    def selected(self) -> str:
        return self.page.js(
            "(() => { const n = document.querySelector('[aria-current=true]'); return n && (n.getAttribute('data-need') || n.getAttribute('data-card') || n.getAttribute('data-result')); })()"
        )

    def results(self) -> list[str]:
        return self.page.js(f"{wb.SHOWN}('[data-result]').map((n) => n.getAttribute('data-result'))")


@needs_chrome
class ViewTests(Behavior):
    def test_a_page_opens_on_what_needs_you_and_the_tabs_switch_views(self):
        self.open("busy")
        self.assertEqual(self.views(), ["needs-you"])
        self.assertEqual(self.page.js("document.querySelector('[data-testid=tab-needs-you]').getAttribute('aria-current')"), "page")
        for tab, name in (("board", "board"), ("tree", "tree"), ("needs-you", "needs-you")):
            with self.subTest(tab=tab):
                self.page.click(f'[data-testid="tab-{tab}"]')
                self.assertEqual(self.views(), [name])
                self.assertEqual(self.page.js(f"document.querySelector('[data-testid=tab-{tab}]').getAttribute('aria-current')"), "page")
                self.assertEqual(self.query(), "" if name == "needs-you" else f"?view={name}")

    def test_the_digit_keys_open_the_three_views(self):
        self.open("busy")
        for key, name in (("2", "board"), ("3", "tree"), ("1", "needs-you")):
            self.page.press(key)
            self.assertEqual(self.views(), [name], key)

    def test_each_view_survives_a_reload_with_its_filters(self):
        cases = (
            ("view=board", ["board"]),
            ("view=board&team=catalog&columns=groups&rows=team", ["board"]),
            ("view=tree&open=INTENT-2", ["tree"]),
            ("view=item&item=SPEC-17", ["item"]),
            ("view=search&q=thong+bao", ["search"]),
            ("view=keys", ["keys"]),
        )
        for query, views in cases:
            with self.subTest(query=query):
                self.open("busy", query)
                self.assertEqual(self.views(), views)
                self.assertEqual(self.query(), "?" + query, "the page keeps the query it was opened with")
                self.page.reload()
                self.assertEqual((self.views(), self.query()), (views, "?" + query))

    def test_a_value_the_page_does_not_know_falls_back_to_its_default(self):
        self.open("busy", "view=bogus&team=nobody&columns=x&rows=y&intent=zzz")
        self.assertEqual((self.views(), self.query()), (["needs-you"], ""))
        self.open("busy", "view=board&team=nobody&columns=x&rows=y&intent=zzz")
        self.assertEqual((self.views(), self.query()), (["board"], "?view=board"), "each unknown value is dropped, the known view stays")
        self.assertEqual(self.count_shown("[data-board=stages-one] [data-card]"), 24)

    def test_the_intent_comes_from_the_url_sets_its_select_and_goes_back_to_the_url(self):
        self.open("busy", "view=board&intent=INTENT-2")
        self.assertEqual(self.page.js("document.querySelector('[data-testid=intent-filter]').value"), "INTENT-2")
        self.assertEqual(self.count_shown("[data-board=stages-one] [data-card]"), 7)
        self.page.js(
            "(() => { const s = document.querySelector('[data-testid=intent-filter]'); s.value = 'INTENT-3'; s.dispatchEvent(new Event('change', {bubbles: true})); })()"
        )
        self.assertEqual((self.query(), self.count_shown("[data-board=stages-one] [data-card]")), ("?view=board&intent=INTENT-3", 7))

    def test_a_link_to_an_item_opens_its_page(self):
        self.open("busy", "item=SPEC-17")
        self.assertEqual(self.views(), ["item"])
        self.assertEqual(self.page.js(f"{wb.SHOWN}('section[data-view=item]').map((n) => n.getAttribute('data-item'))"), ["SPEC-17"])
        self.open("busy", "view=item&item=SPEC-999")
        self.assertEqual(self.views(), ["needs-you"], "an item the page does not hold falls back to what needs you")

    def test_the_team_the_columns_and_the_rows_follow_the_switches_and_the_url(self):
        self.open("busy", "view=board")
        self.assertEqual(self.count_shown("[data-board=stages-one] [data-card]"), 24)
        self.page.click('[data-testid="team-catalog"]')
        self.assertEqual(self.count_shown("[data-board=stages-one] [data-card]"), 7)
        self.assertEqual(self.query(), "?view=board&team=catalog")
        self.page.click('[data-testid="columns-groups"]')
        self.assertEqual(self.count_shown("[data-board=groups-one] [data-card]"), 7)
        self.page.click('[data-testid="rows-team"]')
        self.assertEqual(self.count_shown("[data-board=groups-team] [data-team-row]"), 1, "the Catalog filter leaves its own row")
        self.assertEqual(self.query(), "?view=board&team=catalog&columns=groups&rows=team")
        self.page.click('[data-testid="team-all"]')
        self.assertNotIn("team=", self.query())
        self.assertEqual(self.count_shown("[data-board=groups-team] [data-team-row]"), 4, "a row for each team, and one for work with no team")

    def test_a_tree_branch_opens_and_closes_and_the_url_remembers_it(self):
        self.open("busy", "view=tree")
        self.assertEqual(self.count_shown("[data-node=INTENT-2] [data-leaf]"), 0)
        self.page.click('[data-testid="tree-toggle-intent-2"]')
        self.assertEqual(self.page.js("document.querySelector('[data-testid=tree-toggle-intent-2]').getAttribute('aria-expanded')"), "true")
        self.assertEqual(self.count_shown("[data-node=INTENT-2] [data-leaf]"), 7)
        self.assertEqual(self.query(), "?view=tree&open=INTENT-2")
        self.page.click('[data-testid="tree-toggle-intent-2"]')
        self.assertEqual(self.count_shown("[data-node=INTENT-2] [data-leaf]"), 0)
        self.assertEqual(self.query(), "?view=tree")

    def test_an_item_opens_from_a_row_a_card_a_leaf_and_the_banner(self):
        self.open("busy")
        self.page.click('[data-testid="need-open-spec-17"]')
        self.assertEqual((self.views(), self.query()), (["item"], "?view=item&item=SPEC-17"))
        self.page.click('[data-testid="item-back"]')
        self.assertEqual(self.views(), ["needs-you"])
        self.page.click('[data-testid="emergency-open"]')
        self.assertEqual(self.query(), "?view=item&item=SPEC-41")
        self.open("busy", "view=board")
        self.page.click('[data-testid="card-spec-20"]')
        self.assertEqual(self.query(), "?view=item&item=SPEC-20")
        self.open("busy", "view=tree&open=INTENT-3")
        self.page.click('[data-testid="tree-open-spec-26"]')
        self.assertEqual(self.query(), "?view=item&item=SPEC-26")


@needs_chrome
class KeyTests(Behavior):
    def test_slash_opens_search_and_a_word_finds_an_item_in_any_script_ignoring_case_and_accents(self):
        self.open("busy")
        self.page.press("/")
        self.assertEqual(self.views(), ["search"])
        self.assertEqual(self.active(), "search-input")
        cases = (
            ("thong bao", ["SPEC-19"]),
            ("THONG BAO", ["SPEC-19"]),
            ("don hang", ["SPEC-19"]),
            ("注文", ["SPEC-20"]),
            ("الطلب", ["SPEC-21"]),
            ("schnittstelle", ["SPEC-40"]),
            ("spec-17", ["SPEC-17"]),
            ("card", ["SPEC-26", "SPEC-36", "SPEC-41", "SPEC-42"]),
        )
        for query, ids in cases:
            with self.subTest(query=query):
                self.page.js(
                    "(() => { const i = document.querySelector('[data-testid=search-input]'); i.value = ''; i.dispatchEvent(new Event('input', {bubbles: true})); i.focus(); })()"
                )
                self.page.type_text(query)
                self.assertEqual(sorted(self.results()), ids)
                self.assertEqual(
                    self.query(),
                    "?view=search&q=" + self.page.js("encodeURIComponent(document.querySelector('[data-testid=search-input]').value).replace(/%20/g, '+')"),
                )

    def test_search_never_guesses_a_close_spelling(self):
        self.open("busy", "view=search")
        self.page.click('[data-testid="search-input"]')
        self.page.type_text("pallet")
        self.assertEqual(self.results(), [])
        self.assertEqual(self.page.js("document.querySelector('[data-testid=search-status]').innerText"), "No open item matches.")
        self.page.js("document.querySelector('[data-testid=search-input]').select()")
        self.page.type_text("recieve")
        self.assertEqual(self.results(), [])

    def test_a_match_is_marked_in_the_title(self):
        self.open("busy", "view=search&q=card")
        marked = self.page.js(f"{wb.SHOWN}('[data-result=SPEC-41] mark').map((n) => n.textContent)")
        self.assertEqual(marked, ["card"])

    def test_enter_opens_the_first_result_and_esc_goes_back_to_where_the_page_was(self):
        self.open("busy", "view=board")
        self.page.press("/")
        self.page.type_text("card")
        self.page.press("Enter")
        self.assertEqual(self.query(), "?view=item&item=SPEC-36", "the first result, in the order of the answer")
        self.assertEqual(self.active(), "title", "focus moves to the item's heading")
        self.page.press("Escape")
        self.assertEqual(self.views(), ["search"], "Esc from the item goes back to the search it came from")
        self.page.press("Escape")
        self.assertEqual(self.views(), ["board"], "and Esc from the search to the view it was opened from")

    def test_j_and_k_move_through_the_rows_and_enter_opens_the_one_selected(self):
        self.open("busy")
        first = self.selected()
        self.assertEqual(first, "SPEC-17", "the first row is selected on open")
        self.page.press("j")
        self.assertEqual(self.selected(), "SPEC-14")
        self.page.press("j")
        self.page.press("k")
        self.assertEqual(self.selected(), "SPEC-14")
        self.page.press("Enter")
        self.assertEqual(self.query(), "?view=item&item=SPEC-14")
        self.page.press("Escape")
        self.assertEqual((self.views(), self.selected()), (["needs-you"], "SPEC-14"), "back on the row it left")

    def test_an_open_question_is_a_row_j_reaches_and_enter_opens_its_item_or_nothing(self):
        self.open("resumed")
        for _ in range(2):
            self.page.press("j")
        self.assertEqual(self.selected(), "specs/SPEC-12/explore/saved-carts/exploration.md")
        self.page.press("Enter")
        self.assertEqual(self.query(), "?view=item&item=SPEC-12", "a question opens the item whose folder holds it")
        self.page.press("Escape")
        self.page.press("j")
        self.assertEqual(self.selected(), "specs/explore/delivery-date/exploration.md")
        self.page.press("Enter")
        self.assertEqual((self.views(), self.query()), (["needs-you"], ""), "a question with no item opens nothing, and nothing breaks")

    def test_a_copy_that_turns_primary_or_back_stays_readable_in_every_frame(self):
        # A fill that faded would pass through tones its already switched text cannot be read on: sample both Copy buttons
        # in the frame right after J, the row leaving the cursor and the row taking it.
        sample = (
            "JSON.stringify(['spec-17', 'spec-14'].map((id) => { const s = getComputedStyle(document.querySelector(`[data-testid=need-copy-${id}]`));"
            " return [s.color, s.backgroundColor]; }))"
        )

        def luminance(css: str) -> float:
            r, g, b = (int(x) / 255 for x in css[css.index("(") + 1 : css.index(")")].split(",")[:3])
            return relative_luminance(r, g, b)

        for theme in wb.THEMES:
            self.open("busy", theme=theme)
            self.page.press("j")
            for fg, bg in json.loads(self.page.js(sample)):
                with self.subTest(theme=theme, colors=(fg, bg)):
                    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
                    self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.5)

    def test_c_copies_the_words_of_the_selected_item_and_the_page_says_so(self):
        self.page.call("Browser.grantPermissions", permissions=["clipboardReadWrite", "clipboardSanitizedWrite"])
        self.open("busy")
        self.page.press("c")
        self.page.wait("document.querySelector('[data-testid=copy-status]').textContent === 'Copied the words for SPEC-17'")
        self.assertEqual(self.page.js("navigator.clipboard.readText()", await_promise=True), "Show me what stopped SPEC-17, then wait for my answer")
        self.page.click('[data-testid="need-copy-spec-12"]')
        self.page.wait("document.querySelector('[data-testid=copy-status]').textContent === 'Copied the words for SPEC-12'")
        self.assertEqual(self.page.js("navigator.clipboard.readText()", await_promise=True), "Show me SPEC-12 for Spec approval")
        self.assertEqual(self.page.js("document.querySelector('[data-testid=copy-status]').textContent"), "Copied the words for SPEC-12")

    def test_question_mark_lists_the_keys_and_esc_closes_the_list(self):
        self.open("busy")
        self.page.press("?")
        self.assertEqual(self.views(), ["keys"])
        self.page.press("Escape")
        self.assertEqual(self.views(), ["needs-you"])

    def test_the_off_switch_turns_single_keys_off_and_a_reload_keeps_it(self):
        self.open("busy")
        self.assertIsNone(self.page.js(f"localStorage.getItem('{PREF}')"), "nothing is stored until a person flips the switch")
        self.page.press("?")
        self.page.press("2")
        self.assertEqual(self.views(), ["keys"], "the list of keys is a dialog: a single key does nothing in it")
        self.assertIsNone(self.page.js(f"localStorage.getItem('{PREF}')"), "using the keys stores nothing either")
        self.page.click('[data-testid="keys-single-off"]')
        self.assertEqual(self.page.js("document.querySelector('[data-testid=keys-single-off]').getAttribute('aria-checked')"), "false")
        self.assertEqual(self.page.js(f"localStorage.getItem('{PREF}')"), "off")
        self.page.press("Escape")
        self.assertEqual(self.views(), ["needs-you"], "Esc still works with single keys off")
        for key in ("2", "3", "j", "c", "/", "?"):
            self.page.press(key)
        self.assertEqual(self.views(), ["needs-you"], "no single key acts")
        self.page.reload()
        self.page.press("2")
        self.assertEqual(self.views(), ["needs-you"], "the choice is kept in this browser")
        self.page.click('[data-testid="keys-open"]')
        self.assertEqual(self.views(), ["keys"], "the keyboard button still opens the list")
        self.page.click('[data-testid="keys-single-off"]')
        self.assertEqual(self.page.js(f"localStorage.getItem('{PREF}')"), "on")

    def test_the_keys_that_always_work_keep_saying_on_when_single_keys_are_off(self):
        self.open("busy", "view=keys")
        self.page.click('[data-testid="keys-single-off"]')
        cells = self.page.js(
            f"{wb.SHOWN}('.keys tbody tr').map((r) => [r.querySelector('kbd').textContent, r.querySelector('td:last-child').innerText.trim()])"
        )
        self.assertEqual(dict(cells)["Enter"], "On")
        self.assertEqual(dict(cells)["Esc"], "On")
        self.assertEqual(dict(cells)["C"], "Off")

    def test_a_title_with_an_emoji_marks_the_word_that_matched_and_nothing_else(self):
        import work_page_fixtures as fx

        answer = fx.state("busy")
        next(i for i in answer["items"] if i["id"] == "SPEC-12")["title"] = "\U0001f600 Let a shopper save a cart for later"
        wb.write(self.session["work"], "emoji", answer)
        self.open("emoji", "view=search&q=cart")
        marked = self.page.js(f"{wb.SHOWN}('[data-result=SPEC-12] mark').map((n) => n.textContent)")
        self.assertEqual(marked, ["cart"], "the mark sits on the word, not one unit off after the emoji")
        self.assertEqual(
            self.page.js("document.querySelector('[data-result=SPEC-12] [data-title]').textContent"), "\U0001f600 Let a shopper save a cart for later"
        )

    def test_the_search_says_how_many_results_in_a_visible_line(self):
        self.open("busy", "view=search&q=card")
        self.assertEqual(self.page.js("document.querySelector('[data-testid=search-status]').innerText"), "4 results for card")
        self.page.js(
            "(() => { const i = document.querySelector('[data-testid=search-input]'); i.value = 'warehouse'; i.dispatchEvent(new Event('input', {bubbles: true})); })()"
        )
        self.assertEqual(self.page.js("document.querySelector('[data-testid=search-status]').innerText"), "1 result for warehouse")

    def test_the_search_count_shows_only_when_there_are_results(self):
        self.open("busy", "view=search&q=pallet")
        status = "document.querySelector('[data-testid=search-status]')"
        self.assertEqual(self.page.js(f"{status}.innerText"), "No open item matches.", "no count, and the miss is said")
        self.assertEqual(self.page.js(f"{status}.getAttribute('role')"), "status", "in the region a screen reader announces (WCAG 4.1.3)")
        self.open("busy", "view=search")
        self.assertEqual(self.page.js(f"{status}.innerText"), "", "nothing is said before there is a query")

    def test_a_branch_the_page_does_not_have_stays_out_of_the_address(self):
        self.open("busy", "view=tree&open=NOPE&open=INTENT-2")
        self.assertEqual(self.query(), "?view=tree&open=INTENT-2")

    def test_no_key_acts_while_a_person_types_in_the_search_field(self):
        self.open("busy", "view=search")
        self.page.click('[data-testid="search-input"]')
        for key in ("j", "k", "c", "1", "?", "/"):
            self.page.press(key)
        self.assertEqual(self.views(), ["search"])
        self.assertEqual(self.page.js("document.querySelector('[data-testid=search-input]').value"), "jkc1?/")

    def test_opening_a_view_moves_focus_into_it_and_closing_gives_it_back(self):
        self.open("busy")
        self.page.click('[data-testid="need-open-spec-14"]')
        self.assertEqual(self.active(), "title")
        self.page.click('[data-testid="item-back"]')
        self.assertEqual(self.active(), "need-open-spec-14")


@needs_chrome
class NarrowTests(Behavior):
    def test_the_emergency_banner_folds_to_one_line_and_its_button_shows_the_words(self):
        self.open("emergency", size=wb.PHONE)
        self.assertEqual(self.count_shown("[data-testid=emergency-copy]"), 0)
        self.page.click('[data-testid="emergency-fold"]')
        self.assertEqual(self.page.js("document.querySelector('[data-testid=emergency-fold]').getAttribute('aria-expanded')"), "true")
        self.assertEqual(self.count_shown("[data-testid=emergency-copy]"), 1)


if __name__ == "__main__":
    unittest.main()
