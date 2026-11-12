"""The prototype viewer on the design system, in a real browser: its chrome reflows at 200% text, forced colors keep
its states and its focus ring, and each state ring on the Board is drawn from the thumbnail it marks, on every platform's
frame and in both themes. Its axe checks are in `test_viewer_axe.py` and `test_viewer_axe_boards.py`.

The check at 200% text: with the root's text at 200% (WCAG 1.4.4), the page never scrolls sideways, no control in the chrome
clips its label, no top-bar label runs into the next control, and no label is cut off with an ellipsis, on a phone and
on a laptop. Under emulated `forced-colors: active`, each pressed, chosen, or current
element keeps a `SelectedItem` fill or a `Highlight` bar, and the focus ring takes `Highlight`. Opt in with
`AIDD_BROWSER_TESTS=1`; an opted-in run with no Chrome fails, and never skips.
"""

from __future__ import annotations

import json
import time
import unittest

from browser_driver import Page, needs_chrome
from helpers import PROTOTYPE_TOOL, ROOT
from test_design_system import ratio
import viewer_browser as vb

SESSION: dict = {}
PAGE = "/.aidd/views/prototype-example.html"
PHONE, LAPTOP = (390, 844), (1280, 800)
THEMES = ("light", "dark")
# The Board's frames, the first of each platform in the device table: a phone's thumbnail draws a bezel, a window's a hairline.
DEVICES = json.loads((PROTOTYPE_TOOL / "devices.json").read_text(encoding="utf-8"))["frames"]
BOARD_FRAMES = tuple(next(k for k, f in DEVICES.items() if f["platform"] == p) for p in dict.fromkeys(f["platform"] for f in DEVICES.values()))
# A Board cell's state ring: its color (red, green, blue, alpha), width, and reach past the frame, the frame's shadows (its
# own edge first, then a halo, then any further ring or glow), each with its color and spread, and the board.
RING = """((cell) => {
  const f = document.querySelector('[data-testid="proto-board-' + cell + '"]').parentElement.querySelector('.pv-thumb-frame'), s = getComputedStyle(f);
  const COLOR = /(rgba?|color)\\(([^)]*)\\)/;
  const rgba = (c) => { const m = c.match(COLOR), n = m[2].match(/[\\d.]+/g).map(Number), k = m[1] === 'color' ? 1 : 255; return [n[0] / k, n[1] / k, n[2] / k, n.length > 3 ? n[3] : 1]; };
  const layers = s.boxShadow === 'none' ? [] : s.boxShadow.split(/,(?![^(]*\\))/).map((l) => ({ color: rgba(l), spread: parseFloat(l.replace(COLOR, '').trim().split(/\\s+/)[3]) }));
  return { kind: f.dataset.platform, ring: s.outlineStyle === 'none' ? null : rgba(s.outlineColor), width: parseFloat(s.outlineWidth),
    reach: parseFloat(s.outlineOffset) + parseFloat(s.outlineWidth), layers, board: rgba(getComputedStyle(document.getElementById('scroller')).backgroundColor) };
})"""
# The state check a project's prototype test calls (accessible-ui's criteria.md, "The state check"), run here as it is
# written there, so the documented check is the one that guards the Board: `look` and `stateProblems` on the page.
CRITERIA = (ROOT / "plugins" / "aidd-team" / "skills" / "accessible-ui" / "references" / "criteria.md").read_text(encoding="utf-8")
STATE_CHECK = CRITERIA.split("## The state check", 1)[1].split("```js\n", 1)[1].split("```", 1)[0]
INSTALL_STATE_CHECK = f"(() => {{ {STATE_CHECK}\n window.look = look; window.stateProblems = stateProblems; return true; }})()"
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
    vb.start(SESSION)


class DesignPage:
    """A page of the viewer to open in a theme and at a size, and no saved comment or seen state at each test's start, as the
    behavior tests do. `session` is the module's server and browser (`viewer_browser.start`)."""

    session: dict = {}

    @property
    def page(self) -> Page:
        return self.session["page"]

    def setUp(self):
        self.page.call("Page.navigate", url="about:blank")
        self.page.wait("location.href === 'about:blank'")
        self.page.call("Storage.clearDataForOrigin", origin=self.session["origin"], storageTypes="local_storage")

    def open(self, fragment: str, size: tuple[int, int], theme: str = "light", forced: bool = False) -> None:
        features = [{"name": "prefers-color-scheme", "value": theme}, {"name": "forced-colors", "value": "active" if forced else "none"}]
        self.page.call("Emulation.setEmulatedMedia", media="", features=features)
        self.page.open(self.session["origin"] + PAGE + fragment, size)


@needs_chrome
class ViewerDesignTests(DesignPage, unittest.TestCase):
    session = SESSION

    def save_a_comment(self, size: tuple[int, int]) -> None:
        self.open("#sitters/success?comments=1", size)
        self.page.click('[data-testid="sitter-card"]', 0, frame=True)
        self.page.js("document.getElementById('comment-text').value = 'Lead with the distance.'; document.getElementById('comment-add').click()")

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

    def ring(self, cell: str) -> dict:
        return self.page.js(f"({RING})({json.dumps(cell)})")

    def look(self, cell: str) -> dict:
        """The state check's `look` of the cell's thumbnail, which draws its rings."""
        thumb = f"document.querySelector('[data-testid=\"proto-board-{cell}\"]').parentElement.querySelector('.pv-thumb-frame')"
        return self.page.js(f"look({thumb})")

    def tab_from(self, cell: str) -> None:
        """Focus the Board's `cell`, then press Tab, so the next cell takes focus from the keyboard."""
        self.page.js(f"document.querySelector('[data-testid=\"proto-board-{cell}\"]').focus()")
        for kind in ("keyDown", "keyUp"):
            self.page.call("Input.dispatchKeyEvent", type=kind, key="Tab", code="Tab", windowsVirtualKeyCode=9)

    def test_each_board_ring_is_drawn_from_the_thumbnail_it_marks(self):
        # One ring for every frame drew ink beside a phone's ink bezel: a second border, not a state. On each frame and in each
        # theme, what touches the thumbnail's edge (a halo, else the ring) keeps 3:1 against that edge, and the ring keeps 3:1
        # against what it sits on and the board.
        for frame in BOARD_FRAMES:
            self.open(f"#sitters/success?view=board&frame={frame}", LAPTOP)
            self.page.wait("document.getElementById('board').dataset.ready === 'true'")
            self.page.js(INSTALL_STATE_CHECK)
            for theme in THEMES:
                with self.subTest(frame=frame, theme=theme):
                    self.page.call("Emulation.setEmulatedMedia", media="", features=[{"name": "prefers-color-scheme", "value": theme}])
                    self.page.js("document.activeElement.blur()")
                    rings = {"rest": self.ring("sitters-offline"), "current": self.ring("sitters-success")}
                    looks = {"rest": self.look("sitters-offline"), "current": self.look("sitters-success")}
                    x, y = self.page.point('[data-testid="proto-board-sitters-partial"]')
                    self.page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
                    rings["hover"], looks["hover"] = self.ring("sitters-partial"), self.look("sitters-partial")
                    self.page.call("Input.dispatchMouseEvent", type="mouseMoved", x=0, y=0)
                    self.tab_from("sitters-partial")
                    rings["focus"], looks["focus"] = self.ring("sitters-error"), self.look("sitters-error")
                    self.tab_from("sitters-permission-denied")
                    rings["current and focus"], looks["current and focus"] = self.ring("sitters-success"), self.look("sitters-success")
                    # The general check first: no two states alike, none told by color alone, no ring in its edge's color.
                    self.assertEqual(self.page.js(f"stateProblems({json.dumps(looks)})"), [])
                    self.assertIsNone(rings["rest"]["ring"], "a cell at rest draws no ring")
                    for state in ("hover", "current", "focus"):
                        got = rings[state]
                        edge, *halo = [layer["color"] for layer in got["layers"]]
                        halo = [c for c in halo[:1] if c != got["board"]]  # a halo in the board's own color is the board
                        beside_edge, under_ring = (halo[0], halo[0]) if halo else (got["ring"], got["board"])
                        self.assertGreaterEqual(ratio(beside_edge[:3], edge[:3]), 3, f"the {state} ring beside the {got['kind']}'s own edge")
                        self.assertGreaterEqual(ratio(got["ring"][:3], under_ring[:3]), 3, f"the {state} ring on what it sits on")
                        self.assertGreaterEqual(ratio(got["ring"][:3], got["board"][:3]), 3, f"the {state} ring on the board")
                    self.assertGreater(rings["current"]["width"], rings["hover"]["width"], "the current ring is thicker than the hover ring")
                    second = {state: got["ring"] in [layer["color"] for layer in got["layers"][2:]] for state, got in rings.items() if got["ring"]}
                    self.assertEqual(
                        second,
                        {"hover": False, "current": False, "focus": True, "current and focus": True},
                        "keyboard focus, and it alone, draws a second ring outside the first",
                    )
                    self.assertEqual(rings["current and focus"]["width"], rings["current"]["width"], "the current ring stays inside it")

    def test_the_state_check_names_each_problem_and_passes_distinct_states(self):
        """The documented state check, on looks a test writes: each row's states and the problems it must name, by their
        first words. An indicator's color counts against the edge only where the rest state draws that edge."""
        self.open("#sitters/success", LAPTOP)
        self.page.js(INSTALL_STATE_CHECK)
        ink, blue, paper = "rgb(28, 27, 25)", "rgb(37, 99, 235)", "rgb(250, 250, 249)"
        rest = {"outline-style": "none", "outline-width": "0px", "outline-color": ink, "box-shadow": f"{ink} 0px 0px 0px 3px", "border-style": "none",
                "border-width": "0px", "border-color": ink, "background-color": paper, "font-weight": "400"}  # fmt: skip
        ring = dict(rest, **{"outline-style": "solid", "outline-width": "2px", "outline-color": blue})
        rows = (
            ("distinct states", {"rest": rest, "hover": ring, "current": dict(ring, **{"outline-width": "3px"})}, []),
            ("two alike", {"rest": rest, "hover": ring, "current": dict(ring)}, ["hover and current look the same"]),
            (
                "color alone",
                {"rest": rest, "hover": ring, "current": dict(ring, **{"outline-color": "rgb(0, 0, 255)"})},
                ["hover and current differ only by color"],
            ),
            ("a ring in its edge's ink", {"rest": rest, "current": dict(ring, **{"outline-color": ink})}, ["the current indicator takes its edge's color"]),
            (
                "the edge's ink with no edge drawn",
                {"rest": dict(rest, **{"box-shadow": "none"}), "current": dict(ring, **{"box-shadow": "none", "outline-color": ink})},
                [],
            ),
            ("no rest state", {"hover": ring, "current": dict(ring, **{"outline-color": ink})}, ["hover and current differ only by color"]),
            ("one state", {"rest": rest}, []),
        )
        for name, looks, want in rows:
            with self.subTest(name):
                got = self.page.js(f"stateProblems({json.dumps(looks)})")
                self.assertEqual(len(got), len(want), got)
                for problem, start in zip(got, want, strict=True):
                    self.assertTrue(problem.startswith(start), problem)

    def test_each_board_ring_keeps_its_width_on_screen_at_every_zoom_and_pixel_ratio(self):
        """A ring's width divides by the Board's zoom, and the browser rounds a drawn width down to whole pixels. At every zoom
        the wheel reaches and at each pixel ratio, each ring draws on screen as wide as its token draws off the Board. The hover
        ring draws the thin width, the current ring the thick width, and the focus ring the focus width. So the current ring
        never draws as thin as the hover ring."""
        self.open("#sitters/success?view=board&frame=320", LAPTOP)
        self.page.wait("document.getElementById('board').dataset.ready === 'true'")
        self.page.call("DOM.enable")
        self.page.call("CSS.enable")
        self.addCleanup(self.page.call, "DOM.disable")  # LIFO: CSS goes first, as it needs the DOM agent
        self.addCleanup(self.page.call, "CSS.disable")
        root = self.page.call("DOM.getDocument")["root"]["nodeId"]
        hovered = self.page.call("DOM.querySelector", nodeId=root, selector='.pv-thumb:has([data-testid="proto-board-sitters-partial"])')["nodeId"]
        self.page.call("CSS.forcePseudoState", nodeId=hovered, forcedPseudoClasses=["hover"])  # the pointer would leave it as the cells move
        self.tab_from("sitters-partial")  # keyboard focus on sitters-error; sitters-success is current
        sweep = """(() => {
          const offBoard = (name) => { const p = document.createElement('i'); p.style.outline = 'var(' + name + ') solid'; document.body.append(p);
            const w = parseFloat(getComputedStyle(p).outlineWidth); p.remove(); return w; };
          const frame = (cell) => document.querySelector('[data-testid="proto-board-' + cell + '"]').parentElement.querySelector('.pv-thumb-frame');
          const rings = { hover: ['sitters-partial', '--border-width-thin'], current: ['sitters-success', '--border-width-thick'], focus: ['sitters-error', '--focus-width'] };
          const wrong = [];
          for (let z = 0.2; z <= 2; z += 0.002) {
            zoomBoard(z, '');
            for (const [state, [cell, name]] of Object.entries(rings)) {
              const want = offBoard(name), drawn = parseFloat(getComputedStyle(frame(cell)).outlineWidth) * z;
              if (Math.abs(drawn - want) > 0.001) wrong.push(state + ' at zoom ' + z.toFixed(3) + ': ' + drawn.toFixed(3) + ' px, not ' + want);
            }
          }
          return wrong;
        })()"""
        for pixel_ratio in (1, 1.5, 2, 3):
            with self.subTest(pixel_ratio=pixel_ratio):
                self.page.call("Emulation.setDeviceMetricsOverride", width=LAPTOP[0], height=LAPTOP[1], deviceScaleFactor=pixel_ratio, mobile=False)
                self.assertEqual(self.page.js(sweep)[:5], [])

    def test_a_strip_at_phone_width_leaves_room_for_its_first_cells_rings(self):
        # A strip scrolls sideways, so it clips what reaches past its padding: the outer ring of a focused current cell too.
        self.open("#sitters/empty?view=board&frame=ios", PHONE)
        self.page.wait("document.getElementById('board').dataset.ready === 'true'")
        self.tab_from("sign-in-offline")
        got = self.ring("sitters-empty")
        reach = max([got["reach"]] + [layer["spread"] for layer in got["layers"] if layer["color"][3] == 1])  # a soft glow may clip
        room = self.page.js(
            "(() => { const f = document.activeElement.parentElement.querySelector('.pv-thumb-frame'), r = f.getBoundingClientRect(),"
            " c = f.closest('.pv-strip').getBoundingClientRect(); return [document.activeElement.dataset.testid, r.left - c.left, r.top - c.top]; })()"
        )
        self.assertEqual(room[0], "proto-board-sitters-empty")
        self.assertGreaterEqual(min(room[1:]), reach, "the rings fit inside the strip on the left and the top")

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

    def test_forced_colors_keep_the_boards_current_cell_and_show_focus_on_it(self):
        self.open("#sitters/success?view=board&frame=ios", LAPTOP, forced=True)
        self.page.wait("document.getElementById('board').dataset.ready === 'true'")
        highlight = self.ring("sitters-success")["ring"]
        self.assertEqual(
            highlight[:3],
            self.page.js(
                "(() => { const p = document.createElement('i'); p.style.cssText = 'forced-color-adjust: none; color: Highlight'; document.body.append(p);"
                " const v = getComputedStyle(p).color.match(/[\\d.]+/g).slice(0, 3).map((n) => n / 255); p.remove(); return v; })()"
            ),
            "the current cell's ring is Highlight",
        )
        self.tab_from("sitters-permission-denied")
        both = self.ring("sitters-success")
        self.assertEqual(both["ring"], highlight, "on a focused current cell, the current ring stays Highlight")
        outer = [layer["color"] for layer in both["layers"][1:]]
        self.assertTrue(outer and outer[-1] != highlight, "and focus draws its own ring outside it")


if __name__ == "__main__":
    unittest.main()
