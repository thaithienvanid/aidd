"""The prototype viewer on the design system (R392a), in a real browser: its chrome reflows at 200% text, forced colors keep
its states and its focus ring, and axe finds no WCAG violation on its views at 390 and 1280 px in both themes.

R381's check: with the root's text at 200% (WCAG 1.4.4), the page never scrolls sideways, no control in the chrome
clips its label, no top-bar label runs into the next control, and no label is cut off with an ellipsis, on a phone and
on a laptop. Under emulated `forced-colors: active`, each pressed, chosen, or current
element keeps a `SelectedItem` fill or a `Highlight` bar, and the focus ring takes `Highlight`. axe-core comes from
`tools/axe/`, as `test_work_page_axe.py` says. Opt in with `AIDD_BROWSER_TESTS=1`; an opted-in run with no Chrome or no
axe fails, and never skips.
"""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from browser_driver import CHROME, ENABLED, Page, finish, needs_chrome, start_browser, start_server
from helpers import PROTOTYPE_TOOL
from test_work_page_axe import AXE, TAGS

SESSION: dict = {}
PAGE = "/.aidd/views/prototype-example.html"
PHONE, LAPTOP = (390, 844), (1280, 800)
THEMES = ("light", "dark")
READY = "(() => { const f = document.getElementById('frame'); const d = f && f.contentDocument; return Boolean(d && d.querySelector('section[data-screen].shown')); })()"
# The views a person reviews in: the Prototype, the Board, System, the comments open, and the keys dialog.
VIEWS = (
    ("prototype", "#sitters/success", None),
    ("board", "#sitters/success?view=board", None),
    ("system", "#sitters/success?view=system", None),
    ("comments", "#sitters/success", '[data-testid="proto-inspector-toggle"]'),
    ("keys", "#sitters/success", '[data-testid="proto-shortcuts"]'),
)
# What clips at 200%: the document scrolls sideways, or a visible control in the chrome is cut or runs past the window.
CLIPPED = """(() => {
  const found = [];
  if (document.documentElement.scrollWidth > innerWidth + 0.5) found.push('the page scrolls sideways by ' + (document.documentElement.scrollWidth - innerWidth) + 'px');
  const chrome = document.querySelectorAll('.pv-top, .pv-bar, .pv-nav, .pv-inspector, .pv-dock, #present-exit');
  chrome.forEach((part) => part.querySelectorAll('button, a, select, input, label, [role=tab]').forEach((c) => {
    if (!c.getClientRects().length || c.closest('[hidden], .sr-only, .pv-tab-label') || getComputedStyle(c).visibility === 'hidden') return;
    const r = c.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const name = (c.dataset.testid || c.id || c.className) + ' (' + (c.textContent || '').trim().slice(0, 30) + ')';
    if (r.left < -0.5 || r.right > innerWidth + 0.5) found.push(name + ' runs past the window');
    else if (c.scrollWidth > c.clientWidth + 1 && getComputedStyle(c).overflowX !== 'visible') found.push(name + ' clips its label');
  }));
  // A label's text, as drawn, never runs into the next control in the top bar. Text a screen reader alone reads is left out.
  const drawn = (t) => { for (let n = t.parentElement; n; n = n.parentElement) { const s = getComputedStyle(n);
    if (n.classList.contains('sr-only') || s.clipPath !== 'none' || s.display === 'none') return false; } return t.textContent.trim() !== ''; };
  const textBox = (c) => { const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT); const r = document.createRange(); let box = null;
    for (let t = w.nextNode(); t; t = w.nextNode()) { if (!drawn(t)) continue; r.selectNodeContents(t); const b = r.getBoundingClientRect();
      box = box ? {left: Math.min(box.left, b.left), right: Math.max(box.right, b.right), top: Math.min(box.top, b.top), bottom: Math.max(box.bottom, b.bottom)} : b; }
    return box; };
  const top = [...document.querySelectorAll('.pv-top :is(button, a)')].filter((c) => c.getClientRects().length && !c.closest('[hidden], .sr-only'));
  top.forEach((c, i) => { const t = textBox(c), next = top[i + 1]; if (!t || !next) return; const n = next.getBoundingClientRect();
    if (Math.min(t.right, n.right) - Math.max(t.left, n.left) > 1 && Math.min(t.bottom, n.bottom) - Math.max(t.top, n.top) > 1)
      found.push((c.dataset.testid || c.id) + "'s label runs into " + (next.dataset.testid || next.id)); });
  // No label in the chrome, a control's words or a name in a list, is cut off with an ellipsis.
  const labels = ':is(.pv-top, .pv-bar, .pv-nav, .pv-inspector, .pv-dock) :is(button, a, label, [role=tab], .pv-name)';
  document.querySelectorAll(labels + ', ' + labels + ' *').forEach((n) => {
    if (n.getClientRects().length && getComputedStyle(n).textOverflow === 'ellipsis' && n.scrollWidth > n.clientWidth + 1) found.push((n.className || n.tagName) + ' (' + n.textContent.trim().slice(0, 30) + ') is cut off with an ellipsis');
  });
  return found;
})()"""


def setUpModule():
    if not ENABLED:
        return
    if not CHROME or not AXE.is_file():
        raise AssertionError(f"AIDD_BROWSER_TESTS=1 asks for the viewer's design tests: they need Chrome and axe-core at {AXE} (`npm ci --prefix tools/axe`)")
    atexit.register(finish, SESSION)
    work = Path(tempfile.mkdtemp(prefix="viewer-design-"))
    unittest.addModuleCleanup(shutil.rmtree, work, ignore_errors=True)
    SESSION.setdefault("folders", []).append(work)
    subprocess.run([sys.executable, str(PROTOTYPE_TOOL / "prototype.py"), "example"], cwd=work, check=True, capture_output=True, timeout=60)
    SESSION["origin"] = start_server(work)
    SESSION["browser"] = start_browser(SESSION)
    SESSION["page"] = SESSION["browser"].page(ready=READY)


@needs_chrome
class ViewerDesignTests(unittest.TestCase):
    @property
    def page(self) -> Page:
        return SESSION["page"]

    def setUp(self):
        # Each test starts with no saved comment or seen state, as the behavior tests do.
        self.page.call("Page.navigate", url="about:blank")
        self.page.wait("location.href === 'about:blank'")
        self.page.call("Storage.clearDataForOrigin", origin=SESSION["origin"], storageTypes="local_storage")

    def save_a_comment(self, size: tuple[int, int]) -> None:
        self.open("#sitters/success?comments=1", size)
        self.page.click('[data-testid="sitter-card"]', 0, frame=True)
        self.page.js("document.getElementById('comment-text').value = 'Lead with the distance.'; document.getElementById('comment-add').click()")

    def open(self, fragment: str, size: tuple[int, int], theme: str = "light", forced: bool = False) -> None:
        features = [{"name": "prefers-color-scheme", "value": theme}, {"name": "forced-colors", "value": "active" if forced else "none"}]
        self.page.call("Emulation.setEmulatedMedia", media="", features=features)
        self.page.open(SESSION["origin"] + PAGE + fragment, size)

    def test_the_chrome_reflows_at_200_percent_text_on_a_phone_and_a_laptop(self):
        for size in (PHONE, LAPTOP):
            for name, fragment, click in VIEWS:
                with self.subTest(size=size, view=name):
                    self.open(fragment, size)
                    if click:
                        self.page.click(click)
                    self.page.js("document.documentElement.style.fontSize = '200%'")
                    time.sleep(0.15)  # the frame refits on a resize observer
                    self.assertEqual(self.page.js(CLIPPED), [])
            with self.subTest(size=size, view="a saved comment"):  # its count shows beside the Comments tab
                self.save_a_comment(size)
                self.open("#sitters/success", size)
                if size == PHONE:
                    self.page.click('[data-testid="proto-inspector-toggle"]')
                self.page.js("document.documentElement.style.fontSize = '200%'")
                time.sleep(0.15)
                self.assertEqual(self.page.js(CLIPPED), [])

    def test_a_frame_too_wide_for_the_stage_between_the_panels_closes_them(self):
        """The script measures the side panels as the CSS draws them (--pv-nav-column, --pv-inspector-column): a 1440 frame
        fits between them on a 1600 window, and closes them on a 1280 laptop."""
        panels = "document.querySelector('.pv-app').dataset.panels"
        for size, want in (((1600, 1000), "both"), (LAPTOP, "none")):
            with self.subTest(size=size):
                self.open("#sitters/success?frame=1440", size)
                self.assertEqual(self.page.js(panels), want)

    def test_every_style_block_applies_under_the_pages_hashed_policy(self):
        """The policy names each style block by hash (style-src-elem), so the viewer's, the frame's, and the design's all
        apply: a block the policy refused would have no sheet."""
        self.open("#sitters/success", LAPTOP)
        policy = self.page.js("document.querySelector('meta[http-equiv=Content-Security-Policy]').content")
        self.assertRegex(policy, r"style-src-elem 'sha256-[^;']+'( 'sha256-[^;']+')*;", "the style blocks, by hash only")
        self.assertIn("style-src-attr 'unsafe-inline'", policy, "a design's style attributes, which no hash can name")
        unapplied = "(d) => [...d.querySelectorAll('style')].filter((s) => !s.sheet).map((s) => s.id || s.textContent.slice(0, 40))"
        self.assertEqual(self.page.js(f"({unapplied})(document)"), [])
        frame = f"({unapplied})(document.getElementById('frame').contentDocument)"
        self.assertEqual(self.page.js(frame), [])
        self.assertGreater(self.page.js("document.getElementById('frame').contentDocument.querySelectorAll('style').length"), 1)

    def test_one_primary_button_shows_while_a_comment_is_drafted_and_after_it_is_saved(self):
        primaries = (
            "[...document.querySelectorAll('.btn-primary')].filter((b) => b.getClientRects().length && !b.closest('[hidden]')).map((b) => b.dataset.testid)"
        )
        for size in (PHONE, LAPTOP):
            with self.subTest(size=size):
                self.open("#sitters/success?comments=1", size)
                self.page.click('[data-testid="sitter-card"]', 0, frame=True)
                self.assertEqual(len(self.page.js(primaries)), 1, f"drafting: {self.page.js(primaries)}")
                self.page.js("document.getElementById('comment-text').value = 'Lead with the distance.'; document.getElementById('comment-add').click()")
                self.assertEqual(len(self.page.js(primaries)), 1, f"saved: {self.page.js(primaries)}")

    def test_the_round_field_focuses_as_a_field_with_no_second_border(self):
        for theme in THEMES:
            with self.subTest(theme=theme):
                self.open("#sitters/success", LAPTOP, theme)
                got = self.page.js(
                    "(() => { const p = document.createElement('i'); p.style.color = 'var(--ring)'; document.body.append(p); const ring = getComputedStyle(p).color; p.remove();"
                    " const f = document.getElementById('round-number'); f.focus(); const s = getComputedStyle(f); return [ring, s.borderTopColor, s.outlineStyle]; })()"
                )
                self.assertEqual(got[1], got[0], "a focused round field's border is the ring")
                self.assertEqual(got[2], "none", "it draws no outline, so no double border")

    def test_on_a_phone_the_side_panels_tabs_sit_above_their_panel(self):
        self.open("#sitters/success", PHONE)
        self.page.click('[data-testid="proto-inspector-toggle"]')
        tabs, panel = self.page.js(
            "(() => { const t = document.querySelector('.pv-itabs').getBoundingClientRect();"
            " const p = [...document.querySelectorAll('.pv-inspector [role=tabpanel]')].find((n) => !n.hidden).getBoundingClientRect(); return [t.bottom, p.top]; })()"
        )
        self.assertLessEqual(tabs, panel + 0.5, "the tabs come first, then the panel they switch")

    def test_forced_colors_keep_every_pressed_chosen_and_current_state_and_the_focus_ring(self):
        self.open("#sitters/success", LAPTOP, forced=True)
        self.assertTrue(self.page.js("matchMedia('(forced-colors: active)').matches"), "Chrome emulates forced colors")
        system = """((name, prop) => { const p = document.createElement('i'); p.style.cssText = 'forced-color-adjust: none; ' + prop + ': ' + name;
          document.body.append(p); const v = getComputedStyle(p)[prop === 'color' ? 'color' : 'backgroundColor']; p.remove(); return v; })"""
        selected = self.page.js(f"({system})('SelectedItem', 'background-color')")
        highlight = self.page.js(f"({system})('Highlight', 'background-color')")
        fills = {
            "a pressed segment": ".seg > button[aria-pressed='true']",
            "the chosen state": ".pv-states .option[aria-checked='true']",
            "the primary step": "#comments-send:not([hidden]), #closing-next:not([hidden])",
        }
        for what, selector in fills.items():
            with self.subTest(state=what):
                got = self.page.js(
                    f"(() => {{ const n = document.querySelector({json.dumps(selector)}); return n && getComputedStyle(n).backgroundColor; }})()"
                )
                self.assertEqual(got, selected, f"{what} keeps the SelectedItem fill")
        tab = self.page.js("getComputedStyle(document.querySelector('.tabs > [aria-selected=\"true\"]'), '::after').backgroundColor")
        self.assertEqual(tab, highlight, "the current view keeps its Highlight bar")
        for _ in range(2):  # the skip link, then the first control: focus from the keyboard
            for kind in ("keyDown", "keyUp"):
                self.page.call("Input.dispatchKeyEvent", type=kind, key="Tab", code="Tab", windowsVirtualKeyCode=9)
        ring = self.page.js("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineColor]; })()")
        self.assertNotEqual(ring[0], "none", "the focused control draws its ring")
        self.assertEqual(ring[1], highlight, "the ring is Highlight")

    def test_axe_finds_no_wcag_violation_on_any_view_at_390_and_1280_in_both_themes(self):
        source = AXE.read_text(encoding="utf-8")
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify(r.violations.map((v) => ({{id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 4)}}))))"
        found: list[str] = []
        for size in (PHONE, LAPTOP):
            for theme in THEMES:
                for name, fragment, click in VIEWS:
                    self.open(fragment, size, theme)
                    if click:
                        self.page.click(click)
                    self.page.js(source)
                    found += [f"{size[0]} {theme} {name}: {v['id']} at {v['nodes']}" for v in json.loads(self.page.js(run, await_promise=True))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
