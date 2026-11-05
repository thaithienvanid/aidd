"""The set-up the work-items page's browser tests share (R377).

Each test module writes the page for every fixture state into one folder, starts one Chrome, and opens a page by file URL,
as a person does after `aidd status --html`. `AIDD_BROWSER_TESTS=1` opts in (see `browser_driver.py`). Themes come from
`Emulation.setEmulatedMedia`, widths from `Emulation.setDeviceMetricsOverride`, and text at 200% from doubling the root font
size, which the page's Content-Security-Policy allows through the CSS object model.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
import unittest
from pathlib import Path

import work_page_fixtures as fx
from browser_driver import CHROME, ENABLED, finish, start_browser

from aidd import views

# The script sets `data-ready` on the document once it has wired the page. A document that Chrome has just committed has no
# root element for a moment, so `?.` reads it as not ready yet instead of throwing.
READY = "document.documentElement?.getAttribute('data-ready') === '1'"
PHONE, TABLET, DESKTOP = (390, 844), (768, 1024), (1440, 900)
WIDTHS = {"ios": PHONE, "768": TABLET, "1440": DESKTOP}  # named like round 1's screenshots
THEMES = ("light", "dark")
# Whether an element is on screen: it has a box, and no ancestor hides it.
SHOWN = "((sel) => [...document.querySelectorAll(sel)].filter((n) => n.getClientRects().length > 0))"


def start(session: dict, prefix: str) -> None:
    """One folder with a page for each state, one Chrome, and a tab. Call it from `setUpModule`."""
    if not ENABLED:
        return
    if not CHROME:
        raise AssertionError(
            "AIDD_BROWSER_TESTS=1 asks for the work-items page's browser tests, but no Chrome or Chromium was found: install one, or set CHROME_BIN to it"
        )
    atexit.register(finish, session)
    work = Path(tempfile.mkdtemp(prefix=prefix))
    unittest.addModuleCleanup(shutil.rmtree, work, ignore_errors=True)
    session.setdefault("folders", []).append(work)
    session["work"] = work
    for name in fx.VARIANTS:
        write(work, name, fx.state(name))
    session["browser"] = start_browser(session)
    session["page"] = session["browser"].page(ready=READY)


def write(folder: Path, name: str, answer: dict) -> Path:
    path = folder / f"status-work-{name}.html"
    path.write_text(views.status_page(answer, title="The open work in shop", written=fx.WRITTEN, project="shop"), encoding="utf-8")
    return path


class PageCase(unittest.TestCase):
    """Each test opens a clean page. A page error fails the test that caused it."""

    session: dict = {}

    @property
    def page(self):
        return self.session["page"]

    def setUp(self):
        self.page.call("Page.navigate", url="about:blank")
        self.page.wait("location.href === 'about:blank'")
        self.page.call("Storage.clearDataForOrigin", origin="file://", storageTypes="local_storage")
        self.page.drain()
        self.page.errors.clear()
        self.page.warnings.clear()
        self.page.call(
            "Emulation.setEmulatedMedia",
            media="",
            features=[{"name": "prefers-color-scheme", "value": "light"}, {"name": "prefers-reduced-motion", "value": "no-preference"}],
        )

    def tearDown(self):
        self.page.drain()
        self.assertEqual(self.page.errors, [], "the page reported errors")

    def url(self, state: str, query: str = "") -> str:
        return (self.session["work"] / f"status-work-{state}.html").as_uri() + (f"?{query}" if query else "")

    def open(self, state: str, query: str = "", size: tuple[int, int] = DESKTOP, theme: str = "light", scale: float = 1.0) -> None:
        self.page.call("Emulation.setEmulatedMedia", media="", features=[{"name": "prefers-color-scheme", "value": theme}])
        self.page.open(self.url(state, query), size)
        if scale != 1.0:
            self.page.js(f"document.documentElement.style.fontSize = '{round(16 * scale)}px'")

    def shown(self, selector: str) -> list:
        """The `data-testid` or `data-view` of each element matching `selector` that is on screen."""
        return self.page.js(f"{SHOWN}({selector!r}).map((n) => n.getAttribute('data-testid') || n.getAttribute('data-view') || n.id)")

    def count_shown(self, selector: str) -> int:
        return self.page.js(f"{SHOWN}({selector!r}).length")

    def query(self) -> str:
        return self.page.js("location.search")
