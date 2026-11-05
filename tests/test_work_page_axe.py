"""axe-core on the work-items page, about 30 screens, and on the exploration page, in both themes: no violation (R377).

axe-core 4.14.0 (MPL-2.0, from npm, read 2026-11-07) comes from `tools/axe/`, a package file and lockfile like
`tools/mermaid/`: `npm ci --prefix tools/axe`. `AIDD_AXE_JS` names another copy of `axe.min.js`. DevTools injects it, so the
page keeps its Content-Security-Policy. The rules are scoped to WCAG with the tags the accessible-ui criteria name; without
tags axe also runs best-practice rules, which are advice and no WCAG failure. An axe finds part of the failures, so the
keyboard flows in `test_work_page_behavior.py` and the designer's pass still run. Opt in with `AIDD_BROWSER_TESTS=1`; an
opted-in run with no axe fails, and never skips.
"""

from __future__ import annotations

import json
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
# A phone and a laptop (R392): the system's layout changes below 40rem, so each screen is checked on both sides of it.
WIDTHS = (wb.PHONE, (1280, 800))
AXE = Path(helpers.AXE_JS or helpers.ROOT / "tools" / "axe" / "node_modules" / "axe-core" / "axe.min.js")
# The screens: (state, query), named by what a person sees. Each is checked in the light and the dark theme.
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

    def test_no_screen_breaks_a_wcag_rule_in_either_theme(self):
        source = AXE.read_text(encoding="utf-8")
        found: list[str] = []
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify(r.violations.map((v) => ({{id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 4)}}))))"
        for size in WIDTHS:
            for theme in wb.THEMES:
                for state, query in SCREENS:
                    self.open(state, query, size, theme=theme)
                    self.page.js(source)
                    violations = json.loads(self.page.js(run, await_promise=True))
                    found += [f"{size[0]} {theme} {state} {query}: {v['id']} ({v['impact']}) at {v['nodes']}" for v in violations]
        self.assertEqual(found, [])

    def test_the_explore_page_breaks_no_wcag_rule_in_either_theme(self):
        ready, self.page.ready = self.page.ready, "document.readyState === 'complete'"  # the explore page runs no script
        self.addCleanup(setattr, self.page, "ready", ready)
        source = AXE.read_text(encoding="utf-8")
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify([r.violations.map((v) => v.id + ' at ' + v.nodes.map((n) => n.target.join(' ')).slice(0, 4)), r.passes.length]))"
        found: list[str] = []
        for size in WIDTHS:
            for theme in wb.THEMES:
                self.page.call("Emulation.setEmulatedMedia", media="", features=[{"name": "prefers-color-scheme", "value": theme}])
                self.page.open((self.session["work"] / "explore.html").as_uri(), size)
                self.page.js(source)
                violations, passes = json.loads(self.page.js(run, await_promise=True))
                self.assertGreater(passes, 10, "axe read a page with content")
                found += [f"{size[0]} {theme}: {v}" for v in violations]
        self.assertEqual(found, [])

    def test_axe_ran_on_a_page_that_has_content(self):
        """A screen with nothing in it passes every rule. Prove the run read the page: it counts the page's nodes."""
        self.open("busy", "view=board")
        self.page.js(AXE.read_text(encoding="utf-8"))
        passes = self.page.js("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a']}}).then((r) => r.passes.length)", await_promise=True)
        self.assertGreater(passes, 10)


if __name__ == "__main__":
    unittest.main()
