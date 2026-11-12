"""The browser driver the browser tests share: Chrome's DevTools protocol over a pipe, which the prototype tool's own client speaks
(`prototype_capture.py`: how Chrome is found and started, and the pipe's framing), so aidd holds one client. This file adds the
tab helpers a test needs.

It needs only the standard library and opens no debugging port. A test module starts one Chrome for the whole module with
`start_browser`, and one server on 127.0.0.1 with `start_server`. Chrome quits when the pipe closes, so it ends with the
test run, even a run that is interrupted; a run killed with SIGKILL skips its exit hooks, so it can leave the temporary
folders, and Chrome still quits because the pipe closes with the process.

A browser opening is a nuisance on a desktop, because macOS shows a Dock icon and a window at each launch. So the tests are
opt-in locally: they run only with `AIDD_BROWSER_TESTS=1`, and otherwise every test skips. CI runs them on Linux on every pull
request, where the runner has Chrome (`aidd-tests.yml`, `main.yml`, and `weekly.yml` set the variable). A run that opts in and finds no Chrome
fails, and never skips quietly. They need a POSIX system, because the pipe is Chrome's own
files 3 and 4. The driver looks for `CHROME_BIN`, then Chrome or Chromium on the PATH, in the usual app folders, and in
Playwright's browser cache. `CHROME_BIN` set to an empty string hides every browser. Chrome starts with a throwaway profile
and a mock keychain, so it never reads the person's profile or keychain. The only server is the test module's own, on 127.0.0.1.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from helpers import BROWSER_TESTS_OPTED_IN, REAL_HOME

from aidd.kernel import resources

chrome_pipe = resources.team_tool("prototype")._sibling("prototype_capture")  # the tool's own file, not a copy of it

KEYS = {"ArrowRight": 39, "ArrowLeft": 37, "ArrowDown": 40, "ArrowUp": 38, "Home": 36, "End": 35, "Escape": 27, "Enter": 13}
CALL_SECONDS = 30  # each answer from a running Chrome
# Chrome's first answer, which a cold start on a new runner image can delay well past a call's. Its own deadline, and
# never a retry: a Chrome that never answers still fails.
START_SECONDS = 120


# Where an element is, in page pixels: a page element, or one inside the viewer's frame, which the device scale shrinks.
POINT = """((sel, i, inFrame) => {
  const f = document.getElementById('frame');
  const d = inFrame ? f.contentDocument : document;
  const n = [...d.querySelectorAll(sel)].filter((x) => x.getClientRects().length)[i];
  if (!n) return null;
  n.scrollIntoView({block: 'center', inline: 'center'});
  const r = n.getBoundingClientRect();
  if (!inFrame) return [r.left + r.width / 2, r.top + r.height / 2];
  const o = f.getBoundingClientRect(), s = o.width / f.offsetWidth;
  return [o.left + (r.left + r.width / 2) * s, o.top + (r.top + r.height / 2) * s];
})"""


CHROME = chrome_pipe.find_chrome(REAL_HOME) if BROWSER_TESTS_OPTED_IN else None  # no search of the disk for a run that skips
ENABLED = BROWSER_TESTS_OPTED_IN and os.name == "posix"
if not BROWSER_TESTS_OPTED_IN:
    SKIP_REASON = "set AIDD_BROWSER_TESTS=1 to run the viewer in a real browser"
else:
    SKIP_REASON = "the viewer's behavior tests talk to Chrome over its files 3 and 4, a POSIX pipe, so they run on Linux and macOS"
needs_chrome = unittest.skipUnless(ENABLED, SKIP_REASON)


class Browser(chrome_pipe.CDP):
    """The tool's client on one Chrome, with tabs: several share the pipe, each under its own session."""

    def page(self, target: str | None = None, ready: str = "document.readyState === 'complete'") -> Page:
        """A tab: the first one Chrome opened, or a new one. `ready` is true once a page of the module has loaded."""
        if target is None:
            found = self.call("Target.getTargets")["targetInfos"]
            target = next(t["targetId"] for t in found if t["type"] == "page")
        else:
            target = self.call("Target.createTarget", url="about:blank")["targetId"]
        session = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
        return Page(self, session, target, ready)


class Page:
    """One DevTools session on one tab. Page errors it sees while it waits go in `errors`."""

    def __init__(self, browser: Browser, session: str, target: str, ready: str = "document.readyState === 'complete'"):
        self.browser, self.session, self.target = browser, session, target
        self.ready = ready  # the expression that is true once a page has loaded and shown its first screen
        browser.handlers[session] = self._event  # a page that asks before it unloads waits for the answer, so events are read at once
        self.errors: list[str] = []
        self.warnings: list[str] = []
        for method in ("Page.enable", "Runtime.enable", "Log.enable"):
            self.call(method)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)

    def _event(self, message: dict) -> None:
        method, params = message.get("method"), message.get("params", {})
        if method == "Runtime.exceptionThrown":
            details = params["exceptionDetails"]
            self.errors.append("exception: " + str(details.get("exception", {}).get("description") or details.get("text")))
        elif method == "Runtime.consoleAPICalled" and params["type"] == "warning":
            self.warnings.append(" ".join(str(a.get("value", a.get("description"))) for a in params["args"]))
        elif method == "Runtime.consoleAPICalled" and params["type"] in ("error", "assert"):
            self.errors.append("console." + params["type"] + ": " + " ".join(str(a.get("value", a.get("description"))) for a in params["args"]))
        elif method == "Log.entryAdded" and params["entry"]["level"] == "error":
            self.errors.append("log: " + params["entry"]["text"] + " " + params["entry"].get("url", ""))
        elif method == "Page.javascriptDialogOpening":
            # A page with unsaved comments asks before it unloads. A person leaving would accept, so the test does.
            self.browser.send("Page.handleJavaScriptDialog", {"accept": True}, self.session)

    def close(self) -> None:
        """Close this tab."""
        self.browser.call("Target.closeTarget", targetId=self.target)

    def call(self, method: str, **params):
        return self.browser.call(method, self.session, **params)

    def drain(self) -> None:
        """Read what the page has reported so far."""
        self.js("0")

    # What a person does.
    def js(self, expression: str, *, await_promise: bool = False):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in result:
            raise AssertionError(f"{expression[:120]}: {result['exceptionDetails'].get('exception', {}).get('description')}")
        return result["result"].get("value")

    def wait(self, expression: str, timeout: float = 10.0):
        end = time.monotonic() + timeout
        while True:
            try:
                value = self.js(expression)
            except RuntimeError as error:
                if "navigated or closed" not in str(error):  # a page that is loading answers nothing yet
                    raise
                value = None
            if value:
                return value
            if time.monotonic() > end:
                raise AssertionError(f"timed out waiting for {expression[:200]}\nthe page is at {self.js('location.href')}\nerrors: {self.errors}")
            time.sleep(0.02)

    def open(self, url: str, size: tuple[int, int]) -> None:
        self.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
        self.call("Page.navigate", url="about:blank")  # a new document, never a same-page hash change
        self.wait("location.href === 'about:blank'")
        self.call("Page.navigate", url=url)
        self.wait(self.ready)

    def reload(self) -> None:
        self.js("window.__old = true")
        self.call("Page.reload")
        self.wait("!window.__old && " + self.ready)

    def point(self, selector: str, index: int = 0, frame: bool = False) -> tuple[float, float]:
        script = f"({POINT})({json.dumps(selector)}, {index}, {json.dumps(frame)})"
        self.wait(script)
        seen = None
        for _ in range(100):  # the device scales with a short transition, so wait until the element holds still
            now = self.js(script)
            if now == seen:
                return now[0], now[1]
            seen = now
            time.sleep(0.05)
        raise AssertionError(f"{selector} never held still")

    def click(self, selector: str, index: int = 0, frame: bool = False) -> None:
        self.click_at(*self.point(selector, index, frame))

    def click_at(self, x: float, y: float) -> None:
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

    def press(self, key: str) -> None:
        if key in KEYS:
            down = {"type": "rawKeyDown", "key": key, "code": key, "windowsVirtualKeyCode": KEYS[key]}
        else:
            down = {
                "type": "keyDown",
                "key": key,
                "text": key,
                "code": ("Digit" if key.isdigit() else "Key") + key.upper(),
                "windowsVirtualKeyCode": ord(key.upper()),
            }
        self.call("Input.dispatchKeyEvent", **down)
        self.call("Input.dispatchKeyEvent", **{**{k: v for k, v in down.items() if k != "text"}, "type": "keyUp"})

    def type_text(self, text: str) -> None:
        self.call("Input.insertText", text=text)


def start_server(directory: Path) -> str:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/favicon.ico":  # an empty answer, so the browser logs no missing icon
                self.send_response(204)
                self.end_headers()
                return
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    unittest.addModuleCleanup(server.server_close)
    unittest.addModuleCleanup(server.shutdown)
    return f"http://127.0.0.1:{server.server_address[1]}"


def start_browser(session: dict) -> Browser:
    """Chrome, started by the tool's own `launch`, with a throwaway profile. It talks over a pipe it shares with this process, so
    it exits when this process does, however the run ends. The module's `session` dict keeps its process, its browser, and the
    folders it wrote in, for `finish`."""
    profile = tempfile.mkdtemp(prefix="viewer-chrome-")
    unittest.addModuleCleanup(shutil.rmtree, profile, ignore_errors=True)
    log = Path(profile) / "chrome-stderr.log"  # what Chrome says, read back only when it fails to start
    with log.open("wb") as stderr:
        proc, browser = chrome_pipe.launch(CHROME, Path(profile), stderr=stderr, client=Browser)
    unittest.addModuleCleanup(stop_browser, proc, browser)
    session["proc"], session["browser"] = proc, browser  # both before the check below, so finish() can stop a Chrome that died at once
    session.setdefault("folders", []).append(Path(profile))
    try:
        browser.call("Browser.getVersion", answer_within=START_SECONDS)  # the first answer proves Chrome started; a Chrome that quit has closed its pipe
    except (OSError, AssertionError) as failed:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        said = " ".join(log.read_text(encoding="utf-8", errors="replace").split()[-60:]) or "nothing"
        raise AssertionError(
            f"Chrome at {CHROME} did not start ({failed}; exit code {proc.returncode}). It said: {said}. "
            "If it says it has no usable sandbox, let it make one (on Ubuntu 24.04, kernel.apparmor_restrict_unprivileged_userns=0), "
            "run the tests as root, which adds --no-sandbox, or set CHROME_BIN to another browser"
        ) from failed
    return browser


def stop_browser(proc: subprocess.Popen, browser: Browser) -> None:
    browser.close()  # closing the pipe is Chrome's cue to quit; closing it twice, once by a cleanup and once at exit, is harmless
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def finish(session: dict) -> None:
    """At exit: stop Chrome, then remove the folders it and the tests wrote in. atexit runs the hook registered last first, so
    this one hook keeps that order, and no folder goes while Chrome still writes in it."""
    if session.get("proc") is not None:
        stop_browser(session["proc"], session["browser"])
    for folder in session.get("folders", []):
        shutil.rmtree(folder, ignore_errors=True)
