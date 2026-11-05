"""The set-up the prototype viewer's browser tests share.

`test_prototype.py` reads the viewer's script as text. The viewer's browser tests run it: each module builds the showcase
with the tool, serves it from 127.0.0.1, opens it in headless Chrome, and clicks, types, and presses keys as a person
would. They are split by what they cover, so no file runs past the suite's 20 seconds a file: `test_viewer_comments.py`,
`test_viewer_behavior.py`, and `test_viewer_layout.py`.

The browser is driven by `tests/browser_driver.py`, which says how it starts, why the tests are opt-in with
`AIDD_BROWSER_TESTS=1`, and why a run that opts in and finds no Chrome fails. Each module starts one Chrome for all its tests.
"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from browser_driver import CHROME, ENABLED, Page, finish, start_browser, start_server
from helpers import PROTOTYPE_TOOL, copy_showcase_images


STATES = ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")
WIDE = (1600, 1000)  # wide enough for the 1024 frame between both panels
NARROW = (500, 800)  # a drawer window
LAPTOP = (1280, 800)  # both panels open, and the frame fits between them
VIEWER_PAGE = "/.aidd/views/prototype-example.html"
# The nth sitter card shown in the frame (the other states' cards are in the document too, hidden).
CARD = "[...document.getElementById('frame').contentDocument.querySelectorAll('[data-testid=sitter-card]')].filter((n) => n.getClientRects().length)"
SPEC_PAGE = "/.aidd/views/prototype-specs-spec-24-design-prototype.html"  # a design that names a Spec
BROKEN_PAGE = "/.aidd/views/prototype-broken-prototype.html"  # a design with a link to no screen
DIRECTION_PAGE = "/.aidd/views/prototype-specs-spec-24-explore-listing-directions-a.html"  # direction a of an exploration
# The frame has loaded and shows a screen.
READY = "(() => { const f = document.getElementById('frame'); const d = f && f.contentDocument; return Boolean(d && d.querySelector('section[data-screen].shown')); })()"


def start(session: dict) -> None:
    """One server and one browser for every test of a module. Call it from `setUpModule`. Each cleanup runs at the end, and
    also if this function fails part way."""
    if not ENABLED:
        return
    if not CHROME:
        raise AssertionError(
            "AIDD_BROWSER_TESTS=1 asks for the viewer's browser tests, but no Chrome or Chromium was found: install one, or set CHROME_BIN to it"
        )
    atexit.register(finish, session)  # one hook, so Chrome stops before the folders it writes in are removed
    work = Path(tempfile.mkdtemp(prefix="viewer-behavior-"))
    unittest.addModuleCleanup(shutil.rmtree, work, ignore_errors=True)
    session["work"] = work
    session.setdefault("folders", []).append(work)
    tool = [sys.executable, str(PROTOTYPE_TOOL / "prototype.py")]
    subprocess.run([*tool, "example"], cwd=work, check=True, capture_output=True, timeout=60)
    design = work / "specs" / "SPEC-24" / "design"
    design.mkdir(parents=True)
    copy_showcase_images(design)
    showcase = (PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8")
    (design / "prototype.html").write_text(
        re.sub(r'<meta name="aidd-spec" content="[^"]*">', '<meta name="aidd-spec" content="SPEC-24">', showcase), encoding="utf-8"
    )
    subprocess.run([*tool, "build", "specs/SPEC-24/design/prototype.html"], cwd=work, check=True, capture_output=True, timeout=60)
    # Direction a of an exploration, with a comment from round 1 in the exploration's own round folder.
    exploration = work / "specs" / "SPEC-24" / "explore" / "listing"
    (exploration / "directions").mkdir(parents=True)
    (exploration / "rounds" / "1").mkdir(parents=True)
    (exploration / "exploration.md").write_text("---\ntype: exploration\n---\n", encoding="utf-8")
    copy_showcase_images(exploration / "directions")
    (exploration / "directions" / "a.html").write_text(showcase, encoding="utf-8")
    first = {"id": "a-r1-1", "screen": "sitters", "state": "success", "testid": "sitter-card", "comment": "Lead with the distance."}
    # Two agents' comments, with `by`; the second names its writer in markup, which the viewer shows as text.
    agents = [
        dict(first, id="a-r1-2", comment="Say how far each sitter is.", by="agent:claude-code/claude-opus-5-5"),
        dict(first, id="a-r1-3", comment="Name the price unit.", by="agent:<b>bold</b>"),
        dict(first, id="a-r1-4", comment="Show the sitter's photo.", by="agent:"),
    ]
    (exploration / "rounds" / "1" / "comments-a.json").write_text(json.dumps({"round": 1, "items": [first, *agents]}), encoding="utf-8")
    subprocess.run([*tool, "build", "specs/SPEC-24/explore/listing/directions/a.html"], cwd=work, check=True, capture_output=True, timeout=60)
    (work / "broken").mkdir()
    copy_showcase_images(work / "broken")
    (work / "broken" / "prototype.html").write_text(showcase.replace('data-go="sign-in"', 'data-go="sitterz"', 1), encoding="utf-8")
    subprocess.run([*tool, "build", "broken/prototype.html"], cwd=work, capture_output=True, timeout=60)  # exits 1: the page names its problem
    session["origin"] = start_server(work)
    session["browser"] = start_browser(session)
    session["page"] = session["browser"].page(ready=READY)


class ViewerCase(unittest.TestCase):
    """Each test opens a clean page, with no saved comments, in its module's browser (`session`, which `start` fills)."""

    session: dict = {}

    @property
    def page(self) -> Page:
        return self.session["page"]

    @property
    def origin(self) -> str:
        return self.session["origin"]

    def setUp(self):
        # Leave the last test's page first: Chrome logs a refused unload prompt for comments it had unsaved, which is no page error.
        self.page.call("Page.navigate", url="about:blank")
        self.page.wait("location.href === 'about:blank'")
        self.page.call("Storage.clearDataForOrigin", origin=self.origin, storageTypes="local_storage")
        self.page.drain()
        self.page.errors.clear()
        self.page.warnings.clear()

    def tearDown(self):
        self.page.drain()
        self.assertEqual(self.page.errors, [], "the page reported errors")

    def open(self, fragment: str = "", size: tuple[int, int] = WIDE, path: str = VIEWER_PAGE) -> None:
        self.page.open(self.origin + path + fragment, size)

    def hash(self) -> str:
        return self.page.js("location.hash")

    def frame_js(self, expression: str):
        """`expression` run with `d`, the prototype frame's document."""
        return self.page.js(f"((d) => {expression})(document.getElementById('frame').contentDocument)")

    def see_every_state(self) -> None:
        """Every state seen in every platform group and theme, saved through the page's own record, as N would leave it."""
        self.page.js("comments.seen = new Set(allStates().flatMap(([id, state]) => WHERES.map((w) => seenKey(id, state, w)))); commentSave(true); renderRail()")

    def seen_here(self) -> str:
        """How many states are seen in the platform group and theme on screen, such as `1 of 15`."""
        return self.page.js("document.querySelector('#seen-where li[aria-current] span:last-child').textContent")
