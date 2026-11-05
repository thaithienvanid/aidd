"""axe-core on the prototype viewer's views at the widths and in the themes where its rules change (R392a): no WCAG
violation. The viewer's views split into three files, so that none runs past the suite's 20 seconds a file:
`test_viewer_axe.py` (the Prototype, the keys dialog, the build details), `test_viewer_axe_boards.py` (the Board and the
comments), and `test_viewer_axe_system.py` (System). axe-core comes from `tools/axe/`, as `test_work_page_axe.py` says. Opt
in with `AIDD_BROWSER_TESTS=1`; an opted-in run with no Chrome or no axe fails, and never skips.
"""

from __future__ import annotations

import json
import unittest

import viewer_browser as vb
from browser_driver import ENABLED, needs_chrome
from test_viewer_design import LAPTOP, PHONE, THEMES, VIEWS, DesignPage
from test_work_page_axe import AXE, TABLET, TAGS, load_axe, unchecked_zones

SESSION: dict = {}
# Each file checks the views of one group, and the groups together are every view.
VIEW_GROUPS = (("prototype", "keys", "build"), ("board", "comments"), ("system",))
# axe checks each view at a phone's width in the light theme and at a laptop's in the dark one, as test_work_page_axe.py
# does. The views with a layout of their own also meet every other pair, and the two widths between a phone's and a laptop's
# that fall in a zone of their own (below). The comments are one: on a phone they are a drawer, with a dock toggle only that
# view expands. The keys dialog and the build details have no layout rule, so they open over the Prototype's.
AXE_PAIRS = ((PHONE, "light"), (LAPTOP, "dark"))
# Zones between the viewer's breakpoints that a phone, a tablet (768 px, 48rem) and a laptop all miss: 640 to 767 px, where
# the System view's facts and words stay in rows although the panels are drawers (40rem in system.css against 48rem here);
# and 864 to 1279 px, where the top bar shows its tab labels (the container query below) while the panels are still drawers
# (80rem). A view with a layout of its own meets both, in both themes.
SMALL_TABLET, SMALL_LAPTOP = (700, 900), (1024, 768)
ALL_WIDTHS = (PHONE, SMALL_TABLET, TABLET, SMALL_LAPTOP, LAPTOP)
# The top bar is the container of `@container (width < 60em)`. It sets 14 px, so 840 px, and pads 12 px on each side from
# 48rem up, so the labels show from a window of 864 px (a browser test measures both).
TOP_BAR_EM, TOP_BAR_INSET = 14, 24
CSS = (vb.PROTOTYPE_TOOL / "viewer.html", vb.PROTOTYPE_TOOL / "system.css")
# The views a person reviews in (design's VIEWS), and the build details beside the comments in the side panel.
AXE_VIEWS = (*VIEWS, ("build", "#sitters/success", None))
EVERY_PAIR = ("prototype", "board", "system", "comments")
OPENS_OVER = {"keys": "prototype", "build": "prototype"}
# The side panel's tab to show, and the panel it shows. The side panel is open at a laptop's width, and a drawer below it, so
# the check opens the drawer only when the tab is not on screen.
INSPECTOR_TABS = {"comments": ("proto-inspect-comments", "#comments"), "build": ("proto-inspect-build", "#inspect-screen")}


def axe_matrix(names: tuple[str, ...] | None = None) -> list[tuple[tuple[int, int], str, tuple[str, str, str | None]]]:
    """(size, theme, view) for each axe check of the views in `names` (all by default): every view in AXE_PAIRS, then the
    EVERY_PAIR views in the rest."""
    views = [view for view in AXE_VIEWS if names is None or view[0] in names]
    rest = [(size, theme) for size in ALL_WIDTHS for theme in THEMES if (size, theme) not in AXE_PAIRS]
    return [(size, theme, view) for size, theme in AXE_PAIRS for view in views] + [
        (size, theme, view) for view in views if view[0] in EVERY_PAIR for size, theme in rest
    ]


def start(session: dict) -> None:
    """The module's server and browser, once an opted-in run has axe-core to inject."""
    if ENABLED and not AXE.is_file():
        raise AssertionError(
            f"AIDD_BROWSER_TESTS=1 asks for the viewer's axe tests, but axe-core is not at {AXE}: run `npm ci --prefix tools/axe`, or set AIDD_AXE_JS to axe.min.js"
        )
    vb.start(session)


def setUpModule():
    start(SESSION)


class AxeChecks(DesignPage):
    """The axe test for the views of `views`, to mix into a test case that has a `session`."""

    views: tuple[str, ...]

    def test_axe_finds_no_wcag_violation_on_the_views_at_every_checked_width_in_both_themes(self):
        load_axe(self, self.page)
        run = f"axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(TAGS)}}}}}).then((r) => JSON.stringify(r.violations.map((v) => ({{id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')).slice(0, 4)}}))))"
        found: list[str] = []
        for size, theme, (name, fragment, click) in axe_matrix(self.views):
            self.open(fragment, size, theme)
            self.show(name, click)
            found += [f"{size[0]} {theme} {name}: {v['id']} at {v['nodes']}" for v in json.loads(self.page.js(run, await_promise=True))]
        self.assertEqual(found, [])

    def show(self, name: str, click: str | None) -> None:
        """What the view needs on screen: a click, or the side panel with the tab of its panel, which stays shown."""
        if name not in INSPECTOR_TABS:
            if click:
                self.page.click(click)
            return
        tab, panel = INSPECTOR_TABS[name]
        shown = f"document.querySelector('[data-testid=\"{tab}\"]').getClientRects().length > 0"
        self.page.js(f"{shown} || document.getElementById('inspect-toggle').click()")
        self.page.click(f'[data-testid="{tab}"]')
        self.assertTrue(
            self.page.js(f"(() => {{ const n = document.querySelector('{panel}'); return !n.hidden && n.getClientRects().length > 0; }})()"), f"{name} shows"
        )


@needs_chrome
class PrototypeAxeTests(AxeChecks, unittest.TestCase):
    session = SESSION
    views = VIEW_GROUPS[0]

    def test_the_top_bar_is_the_container_of_its_query_and_the_labels_hide_below_60em_of_it(self):
        """`@container (width < 60em)` hides the tab labels. Its container, the top bar, sets 14 px and pads 12 px a side
        from 48rem up, so the labels show from a window of 864 px: the phone, the small tablet, and the tablet fall below it,
        the small laptop and the laptop above, and 863 and 864 px on either side of the edge."""
        edge = 60 * TOP_BAR_EM + TOP_BAR_INSET
        for width, hidden in (
            (PHONE[0], True),
            (SMALL_TABLET[0], True),
            (TABLET[0], True),
            (edge - 1, True),
            (edge, False),
            (SMALL_LAPTOP[0], False),
            (LAPTOP[0], False),
        ):
            with self.subTest(width=width):
                self.open("#sitters/success", (width, 800))
                font, padding, clip = self.page.js(
                    "(() => { const t = document.querySelector('.pv-top'), s = getComputedStyle(t);"
                    " return [s.fontSize, parseFloat(s.paddingLeft) + parseFloat(s.paddingRight),"
                    " getComputedStyle(document.querySelector('.pv-tab-label')).clipPath]; })()"
                )
                self.assertEqual(font, f"{TOP_BAR_EM}px")
                if width >= 768:  # a phone pads 20 px, where the query decides nothing
                    self.assertEqual(padding, TOP_BAR_INSET)
                self.assertEqual(clip != "none", hidden)


class AxeMatrixTests(unittest.TestCase):
    def test_each_view_meets_both_widths_and_both_themes(self):
        checks = axe_matrix()
        names = [name for name, _, _ in AXE_VIEWS]
        self.assertEqual(sorted(name for group in VIEW_GROUPS for name in group), sorted(names), "each view is in one group")
        self.assertEqual(sorted(check for group in VIEW_GROUPS for check in axe_matrix(group)), sorted(checks), "the files together run every check once")
        for view in AXE_VIEWS:
            seen = [(size, theme) for size, theme, v in checks if v == view]
            wanted = ALL_WIDTHS if view[0] in EVERY_PAIR else (PHONE, LAPTOP)
            self.assertEqual({size for size, _ in seen}, set(wanted), view[0])
            self.assertEqual({theme for _, theme in seen}, set(THEMES), view[0])
            self.assertEqual(len(seen), len(wanted) * len(THEMES) if view[0] in EVERY_PAIR else 2, view[0])
        self.assertLessEqual(set(EVERY_PAIR), set(names))
        for name in names:
            self.assertIn(OPENS_OVER.get(name, name), EVERY_PAIR, f"{name}: a view with no layout of its own opens over one, and any other meets every pair")

    def test_every_zone_between_the_css_breakpoints_has_a_checked_width_on_each_view_with_a_layout(self):
        """A rule for one view in one zone (the comments in a drawer between a phone's and a tablet's width, the Board's tabs
        between 864 px and a laptop's) shows only on that view, so the zones are checked on each of them, not on any."""
        for name in EVERY_PAIR:
            widths = {size[0] for size, _, view in axe_matrix() if view[0] == name}
            zones = unchecked_zones(CSS, widths, TOP_BAR_EM, TOP_BAR_INSET)
            self.assertEqual(zones, [], f"a zone of viewer.html and system.css with no checked width on the {name} view")
        self.assertEqual(
            unchecked_zones(CSS, {390, 1280}, TOP_BAR_EM, TOP_BAR_INSET),
            [(640, 768), (768, 864), (864, 1280)],
            "the guard sees the zones a phone and a laptop miss",
        )
