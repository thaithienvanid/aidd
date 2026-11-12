"""The set-up the prototype viewer's browser tests share.

`test_prototype.py` reads the viewer's script as text. The viewer's browser tests run it: each module takes its own copy
of the showcase the tool built (`showcase`), serves it from 127.0.0.1, opens it in headless Chrome, and clicks, types, and
presses keys as a person would. They are split by what they cover, so no file runs past the suite's 20 seconds a file: `test_viewer_comments.py`,
`test_viewer_behavior.py`, `test_viewer_layout.py`, and `test_viewer_drawer.py`.

The browser is driven by `tests/browser_driver.py`, which says how it starts, why the tests are opt-in with
`AIDD_BROWSER_TESTS=1`, and why a run that opts in and finds no Chrome fails. Each module starts one Chrome for all its tests.
"""

from __future__ import annotations

import atexit
import datetime as dt
import hashlib
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
# Where the built showcase is kept between modules and runs (`showcase`).
CACHE = Path(__file__).resolve().parent / "__pycache__"
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
    showcase(work)
    session["origin"] = start_server(work)
    session["browser"] = start_browser(session)
    session["page"] = session["browser"].page(ready=READY)


def showcase(into: Path) -> None:
    """The pages the viewer's tests open, copied into `into`, which each module owns and may write in. The tool builds
    them once for every module: under tests/__pycache__, which git ignores, by the hash of all the build reads, so a
    change to the tool or to this set-up builds them again. A lock lets one module build while the others wait."""
    import fcntl  # POSIX, as the browser tests are

    CACHE.mkdir(exist_ok=True)
    python = f"py{sys.version_info.major}{sys.version_info.minor}"  # one build for each Python, so a run on another keeps it
    built = CACHE / f"viewer-showcase-{python}-{showcase_key()}"
    with open(CACHE / "viewer-showcase.lock", "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for legacy in CACHE.glob("viewer-showcase-*"):  # a build from before the Python tag in the name
            if legacy.is_dir() and re.fullmatch(r"viewer-showcase-[0-9a-f]{20}", legacy.name):
                shutil.rmtree(legacy, ignore_errors=True)
        if not built.is_dir():
            stage = Path(tempfile.mkdtemp(prefix="viewer-showcase-stage-", dir=CACHE))
            try:
                build_showcase(stage)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise
            for old in (*CACHE.glob(f"viewer-showcase-{python}-*"), *CACHE.glob("viewer-showcase-stage-*")):  # an earlier build, or a stage a killed run left
                if old.is_dir() and old != stage:
                    shutil.rmtree(old, ignore_errors=True)
            stage.rename(built)
        shutil.copytree(built, into, dirs_exist_ok=True)


def showcase_key() -> str:
    """The hash of all the showcase build reads: the tool's files, this set-up, helpers.py, the Python that runs it, and
    the day, which the tool may write into a page."""
    digest = hashlib.sha256(f"{sys.version}\0{dt.date.today().isoformat()}".encode())
    here = Path(__file__).resolve().parent
    for path in [
        *sorted(p for p in PROTOTYPE_TOOL.rglob("*") if p.is_file() and "__pycache__" not in p.parts),
        here / "viewer_browser.py",
        here / "helpers.py",
    ]:
        data = path.read_bytes()
        digest.update(f"\0{path.resolve().relative_to(here.parent).as_posix()}\0{len(data)}\0".encode() + data)
    return digest.hexdigest()[:20]


def build_showcase(work: Path) -> None:
    """The tool's example, a design that names SPEC-24, direction a of an exploration with round 1's comments, and a design
    with a link to no screen, each built into `work`."""
    tool = [sys.executable, str(PROTOTYPE_TOOL / "prototype.py")]
    subprocess.run([*tool, "example"], cwd=work, check=True, capture_output=True, timeout=60)
    design = work / "specs" / "SPEC-24" / "design"
    design.mkdir(parents=True)
    copy_showcase_images(design)
    design_text = (PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8")
    (design / "prototype.html").write_text(
        re.sub(r'<meta name="aidd-spec" content="[^"]*">', '<meta name="aidd-spec" content="SPEC-24">', design_text), encoding="utf-8"
    )
    subprocess.run([*tool, "build", "specs/SPEC-24/design/prototype.html"], cwd=work, check=True, capture_output=True, timeout=60)
    # Direction a of an exploration, with a comment from round 1 in the exploration's own round folder.
    exploration = work / "specs" / "SPEC-24" / "explore" / "listing"
    (exploration / "directions").mkdir(parents=True)
    (exploration / "rounds" / "1").mkdir(parents=True)
    (exploration / "exploration.md").write_text("---\ntype: exploration\n---\n", encoding="utf-8")
    copy_showcase_images(exploration / "directions")
    (exploration / "directions" / "a.html").write_text(design_text, encoding="utf-8")
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
    (work / "broken" / "prototype.html").write_text(design_text.replace('data-go="sign-in"', 'data-go="sitterz"', 1), encoding="utf-8")
    subprocess.run([*tool, "build", "broken/prototype.html"], cwd=work, capture_output=True, timeout=60)  # exits 1: the page names its problem


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
