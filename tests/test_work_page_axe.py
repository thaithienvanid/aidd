"""axe-core on the work-items page, about 30 screens, and on the exploration page, in both themes: no violation.
Each screen meets both widths and both themes, and one screen of each layout meets every pair of them (`matrix`).

axe-core 4.14.0 (MPL-2.0, from npm, read 2026-11-07) comes from `tools/axe/`, a package file and lockfile like
`tools/mermaid/`: `npm ci --prefix tools/axe`. `AIDD_AXE_JS` names another copy of `axe.min.js`. DevTools injects it, so the
page keeps its Content-Security-Policy. The rules are scoped to WCAG with the tags the accessible-ui criteria name; without
tags axe also runs best-practice rules, which are advice and no WCAG failure. An axe finds part of the failures, so the
keyboard flows in `test_work_page_behavior.py` and the designer's pass still run. Opt in with `AIDD_BROWSER_TESTS=1`; an
opted-in run with no axe fails, and never skips.
"""

from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path

import helpers
import test_explorations as ex
import work_page_browser as wb
import work_page_fixtures as fx
from browser_driver import ENABLED, needs_chrome

from aidd.views import exploration_page

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
SESSION: dict = {}
# A phone and a laptop: the system's layout changes below 40rem, so each screen is checked on both sides of it.
LAPTOP = (1280, 800)
# A tablet (768 px, 48rem) sits in the zones a phone and a laptop both miss: 40 to 64rem here, 48 to 80rem in the viewer.
TABLET = (768, 1024)
WIDTHS = (wb.PHONE, LAPTOP)
ALL_WIDTHS = (wb.PHONE, TABLET, LAPTOP)
CSS = (
    helpers.ROOT / "src" / "aidd" / "views" / "work_item_page.css",
    helpers.ROOT / "src" / "aidd" / "views" / "design" / "components.css",
)
AXE = Path(helpers.AXE_JS or helpers.ROOT / "tools" / "axe" / "node_modules" / "axe-core" / "axe.min.js")
# axe in a page's own document only: never in about:blank between pages, and never in a frame, where an evaluate in the
# top document never put it either.
TOP_DOCUMENT_ONLY = "if (window === window.top && location.protocol !== 'about:') {\n%s\n}"
# The screens: (state, query), named by what a person sees.
SCREENS = (
    ("empty", ""),
    ("empty", "view=board"),
    ("empty", "view=tree"),
    ("one-spec", ""),
    ("one-spec", "view=item&item=SPEC-1"),
    ("busy", ""),
    ("busy", "view=board"),
    ("busy", "view=board&columns=groups"),
    ("busy", "view=board&rows=team"),
    ("busy", "view=board&team=catalog"),
    ("busy", "view=tree"),
    ("busy", "view=tree&open=INTENT-1&open=INTENT-2"),
    ("busy", "view=item&item=SPEC-17"),
    ("busy", "view=item&item=SPEC-22"),
    ("busy", "view=item&item=SPEC-14"),
    ("busy", "view=search&q=card"),
    ("busy", "view=search&q=pallet"),
    ("busy", "view=keys"),
    ("stale", "view=item&item=SPEC-14"),
    ("emergency", ""),
    ("emergency", "view=board"),
    ("emergency", "view=item&item=SPEC-41"),
    ("emergency-overdue", ""),
    ("emergency-overdue", "view=board"),
    ("emergency-overdue", "view=item&item=SPEC-41"),
    ("long-title", "view=board"),
    ("long-title", "view=item&item=SPEC-44"),
    ("non-english", ""),
    ("non-english", "view=search&q=الطلب"),
    ("resumed", ""),
    ("resumed", "view=item&item=SPEC-12"),
)
# Each screen is checked at a phone's width in the light theme and at a laptop's in the dark one, so each width and each
# theme meets every screen. One screen of each layout is also checked in the other two pairs, so a fault that shows only
# with one width and one theme together still shows on the layout it breaks, and at a tablet's width too, for the rules
# that apply between a phone's and a laptop's. A layout is a view (`view=`) with the options
# that reshape it (`columns=`, `rows=`): each has a screen here, and `MatrixTests` fails when one has none.
PAIRS = ((wb.PHONE, "light"), (LAPTOP, "dark"))
EVERY_PAIR = (
    ("busy", ""),
    ("busy", "view=board"),
    ("busy", "view=board&columns=groups"),
    ("busy", "view=board&rows=team"),
    ("busy", "view=tree&open=INTENT-1&open=INTENT-2"),
    ("busy", "view=item&item=SPEC-17"),
    ("non-english", "view=search&q=الطلب"),
    ("busy", "view=keys"),
    ("emergency-overdue", ""),
)


def layout(screen: tuple[str, str]) -> tuple[str, tuple[str, ...]]:
    """The view a screen shows and the options that reshape it, such as ("board", ("rows",))."""
    params = dict(part.partition("=")[::2] for part in screen[1].split("&") if part)
    return params.get("view", ""), tuple(key for key in ("columns", "rows") if key in params)


def pixels(length: str, em: float = 16) -> float:
    """A CSS length of a width query in px: a rem is 16 px, as the pages leave the root's font size, and an em is `em` px."""
    number, unit = re.fullmatch(r"([\d.]+)(rem|em|px)", length).groups()
    return float(number) * {"px": 1, "rem": 16, "em": em}[unit]


MEDIA_STRING = re.compile(r"""matchMedia\(\s*(["'`])(.*?)\1\s*\)""")


def width_bands(css: str, container_em: float = 16, container_inset: float = 0) -> list[tuple[float, float]]:
    """The [low, high) px of the window for each `@media` and `@container` width query in `css`, and each `matchMedia("...")`
    string of a script in it, such as (width < 64rem) or (48rem <= width < 80rem). A container is the window less
    `container_inset` px of padding, and an em in its query is `container_em` px: a test measures both for the viewer's top
    bar, so more than one `@container` query in a file fails until each is measured. A width query in any other form fails
    here, so that none goes unread."""
    queries = [(rule, query) for rule, query in re.findall(r"@(media|container)([^{]*)\{", css)]
    queries += [("media", query) for _, query in MEDIA_STRING.findall(css)]
    if sum(rule == "container" for rule, _ in queries) > 1:
        raise AssertionError("more than one @container query in a file: measure each container's font size and padding, then teach this guard")
    bands = []
    for rule, query in queries:
        if "width" not in query:  # prefers-*, forced-colors, print
            continue
        em, inset = (container_em, container_inset) if rule == "container" else (16, 0)
        words = query.strip().strip("()").split()
        if len(words) == 3 and words[0] == "width" and words[1] in ("<", "<=", ">", ">="):
            value = pixels(words[2], em) + inset
            bands.append((value, math.inf) if words[1].startswith(">") else (0, value))
        elif len(words) == 5 and words[1] == "<=" and words[2] == "width" and words[3] in ("<", "<="):
            bands.append((pixels(words[0], em) + inset, pixels(words[4], em) + inset))
        else:
            raise AssertionError(f"@{rule} {query.strip()}: a width query this guard cannot read; write it as (width < 64rem) or (48rem <= width < 80rem)")
    return bands


def unchecked_zones(sources: tuple[Path, ...], widths: set[int], container_em: float = 16, container_inset: float = 0) -> list[tuple[float, float]]:
    """The zones of the width axis, split at every breakpoint in the CSS `sources` that make one page, that none of the
    `widths` falls inside. Rules change only at a breakpoint, so a width in each zone meets every combination of them."""
    bands = [band for source in sources for band in width_bands(source.read_text(encoding="utf-8"), container_em, container_inset)]
    starts = [0, *sorted({edge for band in bands for edge in band if 0 < edge < math.inf})]
    zones = list(zip(starts, [*starts[1:], math.inf], strict=True))
    return [(low, high) for low, high in zones if not any(low <= width < high for width in widths)]


def matrix() -> list[tuple[tuple[int, int], str, str, str]]:
    """(size, theme, state, query) for each check: every screen in PAIRS, then the EVERY_PAIR screens in the rest, which
    include a tablet's width in both themes."""
    rest = [(size, theme) for size in ALL_WIDTHS for theme in wb.THEMES if (size, theme) not in PAIRS]
    return [(size, theme, *screen) for size, theme in PAIRS for screen in SCREENS] + [(size, theme, *screen) for screen in EVERY_PAIR for size, theme in rest]


def load_axe(test: unittest.TestCase, page) -> None:
    """axe-core in every page the tab opens until the test ends. DevTools sends the file once, and Chrome runs it as each
    page starts, before the page's own script, so the page keeps its Content-Security-Policy."""
    added = page.call("Page.addScriptToEvaluateOnNewDocument", source=TOP_DOCUMENT_ONLY % AXE.read_text(encoding="utf-8"))
    test.addCleanup(page.call, "Page.removeScriptToEvaluateOnNewDocument", identifier=added["identifier"])


def setUpModule():
    wb.start(SESSION, "work-page-axe-")
    if ENABLED and not AXE.is_file():
        raise AssertionError(
            f"AIDD_BROWSER_TESTS=1 asks for the axe test, but axe-core is not at {AXE}: run `npm ci --prefix tools/axe`, or set AIDD_AXE_JS to axe.min.js"
        )
    if ENABLED:
        write_explore_page(SESSION["work"])


def write_explore_page(work: Path) -> None:
    """The exploration page (`aidd explore`) with every part it draws: three directions, a diagram, two rounds with a
    changed, a new, and a gone screen, comments and changes, a file it cannot read, and the choice."""
    folder = work / "explore"
    for n in ("1", "2"):
        (folder / "rounds" / n).mkdir(parents=True)
    (folder / "exploration.md").write_text(ex.exploration_text(), encoding="utf-8")
    for name, data in (
        ("1/split-cards-1024-light.png", ex.PNG2),
        ("1/split-old-1024-light.png", ex.PNG2),
        ("2/split-cards-1024-light.png", ex.PNG2[:-1] + b"\0"),
        ("2/split-new-1024-light.png", ex.PNG2),
    ):
        (folder / "rounds" / name).write_bytes(data)
    comment = {"id": "r1-1", "screen": "split", "state": "cards", "testid": "split-total", "comment": "Show the total first."}
    (folder / "rounds" / "1" / "comments.json").write_text(json.dumps({"round": 1, "items": [comment, dict(comment, id="r1-2")]}), encoding="utf-8")
    changes = {"changes": [{"answers": ["r1-1"], "summary": "Moved the total up.", "screen": "split", "state": "cards"}]}
    (folder / "rounds" / "2" / "changes.json").write_text(json.dumps(changes), encoding="utf-8")
    (folder / "rounds" / "2" / "comments.json").write_text("{not json", encoding="utf-8")
    page = exploration_page.comparison_page(folder, written=fx.WRITTEN, project="shop")
    (work / "explore.html").write_text(page, encoding="utf-8")


@needs_chrome
class AxeTests(wb.PageCase):
    session = SESSION

    def test_no_screen_breaks_a_wcag_rule_at_either_width_or_in_either_theme(self):
        load_axe(self, self.page)
        found: list[str] = []
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify(r.violations.map((v) => ({{id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 4)}}))))"
        for size, theme, state, query in matrix():
            self.open(state, query, size, theme=theme)
            violations = json.loads(self.page.js(run, await_promise=True))
            found += [f"{size[0]} {theme} {state} {query}: {v['id']} ({v['impact']}) at {v['nodes']}" for v in violations]
        self.assertEqual(found, [])

    def test_the_explore_page_breaks_no_wcag_rule_in_either_theme(self):
        ready, self.page.ready = self.page.ready, "document.readyState === 'complete'"  # the explore page runs no script
        self.addCleanup(setattr, self.page, "ready", ready)
        load_axe(self, self.page)
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify([r.violations.map((v) => v.id + ' at ' + v.nodes.map((n) => n.target.join(' ')).slice(0, 4)), r.passes.length]))"
        found: list[str] = []
        for size in WIDTHS:
            for theme in wb.THEMES:
                self.page.call("Emulation.setEmulatedMedia", media="", features=[{"name": "prefers-color-scheme", "value": theme}])
                self.page.open((self.session["work"] / "explore.html").as_uri(), size)
                violations, passes = json.loads(self.page.js(run, await_promise=True))
                self.assertGreater(passes, 10, "axe read a page with content")
                found += [f"{size[0]} {theme}: {v}" for v in violations]
        self.assertEqual(found, [])

    def test_axe_ran_on_a_page_that_has_content(self):
        """A screen with nothing in it passes every rule. Prove the run read the page: it counts the page's nodes."""
        load_axe(self, self.page)
        self.open("busy", "view=board")
        passes = self.page.js("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a']}}).then((r) => r.passes.length)", await_promise=True)
        self.assertGreater(passes, 10)


class MatrixTests(unittest.TestCase):
    """The checks the axe test runs, with no browser: each screen meets both widths and both themes."""

    def test_each_screen_meets_both_widths_and_both_themes(self):
        checks = matrix()
        self.assertLessEqual(set(EVERY_PAIR), set(SCREENS))
        for screen in SCREENS:
            seen = [(size, theme) for size, theme, *rest in checks if tuple(rest) == screen]
            self.assertLessEqual(set(WIDTHS), {size for size, _ in seen}, screen)
            self.assertEqual({theme for _, theme in seen}, set(wb.THEMES), screen)
        for screen in EVERY_PAIR:
            self.assertEqual(
                sorted((size, theme) for size, theme, *rest in checks if tuple(rest) == screen), sorted((s, t) for s in ALL_WIDTHS for t in wb.THEMES)
            )
        self.assertEqual(len(checks), len(set(checks)), "no check runs twice")

    def test_each_layout_has_a_screen_in_every_pair(self):
        """A rule that applies to one view only (a media query on its own class) shows at one width and one theme: the view
        needs a screen in all four pairs, or a fault there passes."""
        every = {layout(screen) for screen in EVERY_PAIR}
        self.assertEqual({layout(screen) for screen in SCREENS} - every, set(), "a layout with no screen in every pair")

    def test_every_zone_between_the_css_breakpoints_has_a_checked_width(self):
        self.assertEqual(
            width_bands("@media (width < 64rem) {} @media (48rem <= width < 80rem) {} @media (forced-colors: active) {}"), [(0, 1024), (768, 1280)]
        )
        self.assertEqual(width_bands("@container (width < 60em) {}", container_em=14, container_inset=24), [(0, 864)])
        zones = unchecked_zones(CSS, {size[0] for size, *_ in matrix()})
        self.assertEqual(zones, [], "a zone between two breakpoints of work_item_page.css and components.css that no screen is checked in")
        self.assertEqual(unchecked_zones(CSS, {390, 1280}), [(640, 1024)], "the guard sees a zone no width falls in")
        self.assertEqual(width_bands('narrow = window.matchMedia("(width < 48rem)"); dark = matchMedia("(prefers-color-scheme: dark)")'), [(0, 768)])
        with self.assertRaises(AssertionError):
            width_bands("@media (min-width: 600px) {}")
        with self.assertRaises(AssertionError):
            width_bands("@container (width < 60em) {} @container (width < 30em) {}")


if __name__ == "__main__":
    unittest.main()
