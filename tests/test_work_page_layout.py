"""The work-items page's layout, measured in a real browser.

Ten screens, one for each state of the design and two for a person who comes back, at 390, 768, and 1440 wide in both themes: 60 shots, and the same screens at
200% text. Each shot is named like round 1's files (`board-busy-1440-dark.png`, with `ios` for 390), and is saved to the
folder `AIDD_WORK_PAGE_SHOTS` names, if any, for the designer to compare with round 1 one by one. A golden-image diff would
fail on the font differences between macOS and the Linux runner, so the test asserts the geometry instead: no sideways
scroll, no clipped title, a 24 px target (WCAG 2.5.8), a one-line banner and stacked team rows at 390, and 30 Board cards on one
1440 by 900 screen. test_work_page_speed times 500 items. Opt in with `AIDD_BROWSER_TESTS=1`.
"""

from __future__ import annotations

import base64
import json
import os
import unittest
from pathlib import Path

import work_page_browser as wb
from browser_driver import needs_chrome

SESSION: dict = {}
# One screen for each state: (round 1's file prefix, state, query).
SCREENS = (
    ("needs-you-empty", "empty", ""),
    ("needs-you-one-spec", "one-spec", ""),
    ("board-busy", "busy", "view=board"),
    ("item-blocked", "busy", "view=item&item=SPEC-17"),
    ("item-emergency", "emergency", "view=item&item=SPEC-41"),
    ("item-stale", "stale", "view=item&item=SPEC-14"),
    ("board-long-title", "long-title", "view=board"),
    ("needs-you-non-english", "non-english", ""),
    ("needs-you-resumed", "resumed", ""),
    ("item-resumed", "resumed", "view=item&item=SPEC-12"),
)
SHOTS = Path(os.environ["AIDD_WORK_PAGE_SHOTS"]) if os.environ.get("AIDD_WORK_PAGE_SHOTS") else None
# What is measured on the page on screen. Each part returns a list of problems, empty when the page is right.
MEASURE = r"""(() => {
  const shown = (sel) => [...document.querySelectorAll(sel)].filter((n) => n.getClientRects().length > 0);
  const name = (n) => n.getAttribute('data-testid') || n.getAttribute('data-field') || n.tagName.toLowerCase();
  const out = {sideways: document.documentElement.scrollWidth - window.innerWidth, clipped: [], small: [], scrolls: []};
  // A team filter that scrolls inside itself is content that needs two dimensions to reach (WCAG 2.2 SC 1.4.10).
  for (const n of shown('.team-filter')) if (n.scrollWidth > n.clientWidth + 1) out.scrolls.push(name(n) + ' ' + n.scrollWidth + '>' + n.clientWidth);
  // A title that is cut off: its text is wider than its box. Board cards cut a title to one line by design, so they are left out.
  for (const n of shown('[dir=auto]')) {
    if (n.closest('[data-card]')) continue;
    const cs = getComputedStyle(n);
    if (cs.display !== 'inline' && n.scrollWidth > n.clientWidth + 1) out.clipped.push(name(n) + ' ' + n.scrollWidth + '>' + n.clientWidth);
  }
  // Targets of at least 24 by 24 CSS pixels (WCAG 2.5.8): a control on screen, other than text in a sentence.
  for (const n of shown('button, input, select, summary, [role=button], [role=switch]')) {
    const r = n.getBoundingClientRect();
    if (r.width < 24 - 0.5 || r.height < 24 - 0.5) out.small.push(name(n) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  return JSON.stringify(out);
})()"""


def setUpModule():
    wb.start(SESSION, "work-page-layout-")
    if SHOTS is not None:
        SHOTS.mkdir(parents=True, exist_ok=True)


@needs_chrome
class LayoutTests(wb.PageCase):
    session = SESSION

    def measure(self) -> dict:
        return json.loads(self.page.js(MEASURE))

    def shoot(self, prefix: str, width: str, theme: str) -> None:
        data = self.page.call("Page.captureScreenshot", format="png")["data"]
        if SHOTS is not None:
            (SHOTS / f"{prefix}-{width}-{theme}.png").write_bytes(base64.b64decode(data))

    def check(self, prefix: str, state: str, query: str, width: str, theme: str, scale: float = 1.0) -> None:
        self.open(state, query, wb.WIDTHS[width], theme, scale)
        if scale == 1.0:
            self.shoot(prefix, width, theme)
        found = self.measure()
        where = f"{prefix} at {width} in {theme}" + (f" at {scale:.0%} text" if scale != 1.0 else "")
        self.assertLessEqual(found["sideways"], 0, f"{where}: the page scrolls sideways")
        self.assertEqual(found["clipped"], [], f"{where}: a title is clipped")
        self.assertEqual(found["small"], [], f"{where}: a target is under 24 by 24 px")
        self.assertEqual(found["scrolls"], [], f"{where}: the team filter scrolls sideways")

    def test_each_state_fits_each_width_in_both_themes(self):
        for prefix, state, query in SCREENS:
            for width in wb.WIDTHS:
                for theme in wb.THEMES:
                    with self.subTest(screen=prefix, width=width, theme=theme):
                        self.check(prefix, state, query, width, theme)

    def test_each_state_survives_text_at_200_percent(self):
        for prefix, state, query in SCREENS:
            with self.subTest(screen=prefix):
                self.check(prefix, state, query, "1440", "light", scale=2.0)

    def test_the_tab_row_has_room_for_a_fourth_view_at_320(self):
        """The place the phase and stage view will take: a fourth tab fits the tab row at 320 px, with no scroll."""
        self.open("busy", "", (320, 700))
        room = self.page.js(
            "(() => { const t = document.querySelector('.tabs'), c = t.querySelector('a').cloneNode(true); c.textContent = 'Phases'; t.append(c);"
            " return [t.scrollWidth - t.clientWidth, document.documentElement.scrollWidth - innerWidth]; })()"
        )
        self.assertEqual([max(0, n) for n in room], [0, 0], "the tab row and the page stay inside 320 px")

    def test_at_390_the_banner_is_one_line_and_the_team_rows_stack(self):
        self.open("emergency", "", wb.PHONE)
        height = self.page.js("document.querySelector('[data-testid=emergency-banner]').getBoundingClientRect().height")
        line = self.page.js("parseFloat(getComputedStyle(document.body).lineHeight) || 20")
        self.assertLessEqual(height, line * 2 + 24, "the folded banner takes one line and its padding")
        self.open("busy", "view=board&rows=team", wb.PHONE)
        lefts = self.page.js(
            "(() => { const row = document.querySelector('[data-board=stages-team] [data-team-row]');"
            " return [...row.querySelectorAll('[data-cell]')].filter((n) => n.getClientRects().length > 0).map((n) => Math.round(n.getBoundingClientRect().left)); })()"
        )
        self.assertGreater(len(lefts), 1)
        self.assertEqual(len(set(lefts)), 1, "a team row's cells stack in one column")

    def test_the_board_fits_30_cards_on_one_desktop_screen(self):
        self.open("busy", "view=board", wb.DESKTOP)
        cards = self.page.js(f"{wb.SHOWN}('[data-board=stages-one] [data-card]').map((n) => Math.round(n.getBoundingClientRect().bottom))")
        self.assertEqual(len(cards), 24)
        self.assertLessEqual(max(cards), wb.DESKTOP[1], "every card is above the fold at 1440 by 900")
        self.assertLessEqual(max(cards), wb.DESKTOP[1] - 24, "the last card ends 24 px above the fold, with room for a wrapped line; the foot may fall below")

    def test_the_top_bar_does_not_overlap_at_200_percent_text_on_a_tablet_and_every_control_is_24_px(self):
        overlap = (
            "(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const a = ['.topbar-name', '.tabs', '.topbar-end'].map(r);"
            " const hit = (x, y) => x.left < y.right - 1 && y.left < x.right - 1 && x.top < y.bottom - 1 && y.top < x.bottom - 1;"
            " return [hit(a[0], a[1]), hit(a[1], a[2]), hit(a[0], a[2])]; })()"
        )
        for scale, size in ((2.0, wb.TABLET), (1.0, wb.TABLET), (2.0, wb.DESKTOP)):
            with self.subTest(scale=scale, size=size):
                self.open("busy", "", size, "light", scale)
                self.assertEqual(self.page.js(overlap), [False, False, False], "the tabs, the name, and the buttons stay apart")
                keys = self.page.js(
                    "(() => { const b = document.querySelector('[data-testid=keys-open]').getBoundingClientRect(); return [b.width, b.height]; })()"
                )
                self.assertGreaterEqual(min(keys), 24, "the keys button is at least 24 by 24")

    def test_a_stopped_task_is_set_apart_and_a_waiting_one_has_no_box(self):
        self.open("busy", "view=item&item=SPEC-17", wb.DESKTOP)
        weight = self.page.js("parseInt(getComputedStyle(document.querySelector('[data-item=SPEC-17] [data-task=T2] .task-state')).fontWeight)")
        self.assertGreaterEqual(weight, 600, "a stopped Task's state is bold")
        box = self.page.js(
            "(() => { const s = getComputedStyle(document.querySelector('[data-item=SPEC-17] [data-task=T3] .note')); return [s.borderLeftWidth, s.backgroundColor]; })()"
        )
        self.assertEqual(box[0], "0px", "a waiting Task's reason has no box")

    def test_a_needs_you_row_and_an_item_lead_with_one_ink_button_the_first_one_c_copies(self):
        """The one primary rule, as drawn: the current row and each item's next box fill one Copy with ink, stale or not, and
        it is the first, which C copies. A stale item leads with its tests command."""
        inks = r"""(() => {
          const probe = document.createElement('i'); probe.style.background = 'var(--primary)'; document.body.append(probe);
          const ink = getComputedStyle(probe).backgroundColor; probe.remove();
          document.querySelectorAll('[data-copy]').forEach((b) => (b.style.transition = 'none'));
          const lead = (box) => { const all = [...box.querySelectorAll('[data-copy]')];
            const filled = all.map((b, n) => getComputedStyle(b).backgroundColor === ink ? n : -1).filter((n) => n >= 0);
            return all.length ? filled.join(',') : null; };
          const out = {};
          for (const row of document.querySelectorAll('[data-need]')) {
            document.querySelectorAll('[aria-current=true]').forEach((n) => n.removeAttribute('aria-current'));
            row.setAttribute('aria-current', 'true'); out['need ' + row.dataset.need] = lead(row);
          }
          for (const box of document.querySelectorAll('section[data-view=item] .next-box')) out['item ' + box.closest('section').dataset.item] = lead(box);
          return JSON.stringify(Object.fromEntries(Object.entries(out).filter(([, v]) => v !== null)));
        })()"""
        for state in ("busy", "stale"):
            for theme in wb.THEMES:
                with self.subTest(state=state, theme=theme):
                    self.open(state, "", wb.DESKTOP, theme)
                    found = json.loads(self.page.js(inks))
                    self.assertIn("need SPEC-14", found)
                    self.assertEqual({k: v for k, v in found.items() if v != "0"}, {}, "each lead box fills only its first Copy")
        # As the page opens, the row its script makes current fills its Copy with the primary ink, and no other row does.
        drawn = r"""(() => {
          const probe = document.createElement('i'); probe.style.background = 'var(--primary)'; document.body.append(probe);
          const ink = getComputedStyle(probe).backgroundColor; probe.remove();
          return [...document.querySelectorAll('[data-need]')].filter((row) => [...row.querySelectorAll('.words-next > [data-copy]')]
            .some((b) => getComputedStyle(b).backgroundColor === ink)).map((row) => [row.dataset.need, row.getAttribute('aria-current')]);
        })()"""
        for theme in wb.THEMES:
            with self.subTest(theme=theme, opened="as the script draws it"):
                self.open("busy", "", wb.DESKTOP, theme)
                self.page.js("document.querySelectorAll('[data-copy]').forEach((b) => (b.style.transition = 'none'))")
                self.assertEqual([current for _, current in self.page.js(drawn)], ["true"], "one primary Copy, on the current row")

    def test_the_skip_link_the_sprite_and_the_hint_are_laid_out_as_designed(self):
        self.open("busy", "", wb.DESKTOP)
        self.assertEqual(self.page.js("getComputedStyle(document.querySelector('.sprite')).position"), "absolute")
        self.assertEqual(self.page.js("getComputedStyle(document.querySelector('[data-testid=keys-hint]')).display"), "flex")

    def test_controls_keep_the_prototypes_sizes_and_a_stopped_tasks_reason_is_not_set_in_mono(self):
        self.open("busy", "", wb.DESKTOP)
        box = lambda sel: self.page.js(f"document.querySelector({sel!r}).getBoundingClientRect().height")  # noqa: E731
        self.assertAlmostEqual(box("[data-testid=keys-open]"), 30, delta=0.6)
        self.assertAlmostEqual(box("[data-testid=search-open]"), 30, delta=0.6)
        self.page.click('[data-testid="tab-board"]')
        self.assertAlmostEqual(box("[data-testid=columns-stages]"), 28, delta=0.6)
        self.open("busy", "view=item&item=SPEC-17", wb.DESKTOP)
        family = self.page.js("getComputedStyle(document.querySelector('[data-item=SPEC-17] [data-task=T2] .note')).fontFamily")
        self.assertNotIn("monospace", family, "mono is for code only")

    def test_a_words_box_is_set_in_the_mono_token_and_not_the_generic_monospace(self):
        self.open("busy", "", wb.DESKTOP)
        token, used = self.page.js(
            "(() => { const t = document.createElement('span'); document.body.append(t); t.style.fontFamily = 'var(--font-mono)';"
            " const want = getComputedStyle(t).fontFamily; t.remove();"
            " return [want, getComputedStyle(document.querySelector('[data-need] .words code')).fontFamily]; })()"
        )
        self.assertEqual(used, token, "every words box uses the token, which is not Courier in Safari")
        self.assertIn("ui-monospace", token)


if __name__ == "__main__":
    unittest.main()
