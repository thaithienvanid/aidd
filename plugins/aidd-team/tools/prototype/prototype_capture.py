"""Stdlib headless Chrome for the prototype tool: where Chrome is, how it starts, and how this file speaks to it over a pipe
(`find_chrome`, `launch`, and `CDP`), and `shots --capture`, which takes screenshots with them. The browser tests drive Chrome
with the same three (`tests/browser_driver.py`), so aidd holds one client for Chrome's pipe."""

from __future__ import annotations

import base64
import glob
import json
import os
import select
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

_CALL_SECONDS = 30.0
_READY_EXPR = "Boolean(location.href !== 'about:blank' && document.querySelector('#workspace[data-ready=\"true\"]') && document.getElementById('frame'))"
_BOX_EXPR = (
    "(() => { const r = document.getElementById('frame')?.getBoundingClientRect();"
    " return r && r.width > 0 && r.height > 0 ? {x: r.left, y: r.top, width: r.width, height: r.height, scale: 1} : null; })()"
)


def find_chrome(home: str | None = None) -> str | None:
    """Locate Chrome or Chromium from CHROME_BIN, PATH, app installs, or Playwright's cache under `home` (the person's, by default)."""
    if "CHROME_BIN" in os.environ:
        candidate = os.environ["CHROME_BIN"]
        return candidate if candidate and os.path.isfile(candidate) else None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if found := shutil.which(name):
            return found
    home = home or str(Path.home())
    places = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    ]
    for pattern in (
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/*.app/Contents/MacOS/*",
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
    ):
        places.extend(sorted(glob.glob(pattern.replace("~", home, 1)), reverse=True))
    return next((p for p in places if os.path.isfile(p)), None)


class CDP:
    """Chrome's DevTools protocol over a pipe: each message is JSON ended by a NUL byte, sent on Chrome's file 3 and read on its
    file 4. Several tabs share the pipe, each under its own session, and `handlers` answers each session's events as they arrive."""

    def __init__(self, read_fd: int, write_fd: int) -> None:
        self.read_fd, self.write_fd = read_fd, write_fd
        self.closed = False
        self.buf = b""
        self.seq = 0
        self.results: dict[int, dict] = {}
        self.handlers: dict[str, Callable[[dict], None]] = {}

    def send(self, method: str, params: dict, session: str | None = None) -> int:
        self.seq += 1
        payload = {"id": self.seq, "method": method, "params": params}
        if session:
            payload["sessionId"] = session
        raw = json.dumps(payload).encode() + b"\0"
        while raw:  # a write to a pipe may take only part of a long message
            raw = raw[os.write(self.write_fd, raw) :]
        return self.seq

    def pump(self, deadline: float) -> None:
        """Read one message from Chrome, or raise TimeoutError when the deadline passes, or ConnectionError when Chrome has quit."""
        while b"\0" not in self.buf:
            if not select.select([self.read_fd], [], [], max(0.0, deadline - time.monotonic()))[0]:
                raise TimeoutError("Chrome did not answer in time")
            chunk = os.read(self.read_fd, 1 << 20)
            if not chunk:
                raise ConnectionError("Chrome closed the pipe")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\0")
        message = json.loads(line)
        if "id" in message:
            self.results[message["id"]] = message
        elif message.get("sessionId") in self.handlers:
            self.handlers[message["sessionId"]](message)

    def call(self, method: str, session: str | None = None, *, answer_within: float = _CALL_SECONDS, **params: Any) -> dict:
        mine = self.send(method, params, session)
        deadline = time.monotonic() + answer_within
        while mine not in self.results:
            try:
                self.pump(deadline)
            except TimeoutError as late:
                raise TimeoutError(f"Chrome timed out waiting for {method}") from late
        res = self.results.pop(mine)
        if "error" in res:
            raise RuntimeError(f"{method}: {res['error']}")
        return dict(res.get("result", {}))

    def close(self) -> None:
        if self.closed:  # a number closed twice could be one this process opened for something else since
            return
        self.closed = True
        for fd in (self.write_fd, self.read_fd):
            try:
                os.close(fd)
            except OSError:
                pass


def launch(chrome: str, profile: Path, *, stderr: int | IO[Any] | None = subprocess.DEVNULL, client: type[CDP] = CDP) -> tuple[subprocess.Popen, CDP]:
    """Start Chrome with a throwaway `profile` and a mock keychain, so it never reads the person's profile or asks for their keychain.
    It talks over a pipe it shares with this process, so it quits when the pipe closes, however this process ends. Returns the
    process and its `client`, which the caller closes. `stderr` is where Chrome's own messages go."""
    import fcntl

    flags = [
        "--headless=new",
        "--remote-debugging-pipe",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-features=OptimizationHints,Translate,MediaRouter",
        "--disable-sync",
        "--no-proxy-server",
        "--force-device-scale-factor=1",
        "--use-mock-keychain",
        "--password-store=basic",
    ]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        flags.append("--no-sandbox")  # Chrome refuses to run as root without it, as in a container
    # Chrome reads commands on file 3 and writes answers on file 4. bash moves this process's pipe ends there, high numbered so
    # no end is overwritten on the way, and then becomes Chrome. Not `sh`: Ubuntu's sh is dash, which reads no file number past
    # 9 in a redirection ("Bad fd number").
    to_c, from_c = os.pipe(), os.pipe()
    fds: list[int] = []
    try:
        fds = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (*to_c, *from_c)]
    finally:
        for fd in (*to_c, *from_c):
            os.close(fd)
    try:
        proc = subprocess.Popen(
            ["bash", "-c", f'exec "$0" "$@" 3<&{fds[0]} 4>&{fds[3]}', chrome, *flags],
            pass_fds=(fds[0], fds[3]),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
    except OSError:
        for fd in fds:
            os.close(fd)
        raise
    os.close(fds[0])
    os.close(fds[3])
    return proc, client(fds[2], fds[1])


def _wait_expr(cdp: CDP, session: str, expr: str, message: str) -> None:
    end = time.monotonic() + _CALL_SECONDS
    while time.monotonic() < end:
        try:
            res = cdp.call("Runtime.evaluate", session, expression=expr, returnByValue=True)
        except RuntimeError as exc:
            if "navigated or closed" not in str(exc):
                raise
            res = {}
        if res.get("result", {}).get("value"):
            return
        time.sleep(0.02)
    raise TimeoutError(message)


def _capture_one(cdp: CDP, session: str, url: str, shot: dict, dest: Path) -> None:
    if dest.is_symlink():
        raise RuntimeError(f"{dest} is a symlink: write screenshots only into plain files")
    cdp.call("Emulation.setDeviceMetricsOverride", session, width=2200, height=1100, deviceScaleFactor=1, mobile=False)
    cdp.call(
        "Emulation.setEmulatedMedia",
        session,
        features=[
            {"name": "prefers-color-scheme", "value": shot.get("theme", "light")},
            {"name": "prefers-reduced-motion", "value": "reduce"},
        ],
    )
    cdp.call("Page.navigate", session, url="about:blank")
    _wait_expr(cdp, session, "location.href === 'about:blank'", "timed out resetting page to about:blank")
    cdp.call("Page.navigate", session, url=url)
    _wait_expr(cdp, session, _READY_EXPR, "timed out waiting for viewer #workspace[data-ready=true]")
    clip = cdp.call("Runtime.evaluate", session, expression=_BOX_EXPR, returnByValue=True).get("result", {}).get("value")
    shot_params: dict[str, Any] = {"format": "png", "captureBeyondViewport": True}
    if isinstance(clip, dict):
        shot_params["clip"] = clip
    raw = base64.b64decode(cdp.call("Page.captureScreenshot", session, **shot_params)["data"])
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".shot-", suffix=".png", delete=False) as tf:
            tmp_path = tf.name
            tf.write(raw)
        os.replace(tmp_path, dest)
    finally:  # an interrupt too leaves nothing in the design's folder: after the move the temporary path is gone
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def capture_shots(page: Path, shots: list[dict], out_dir: Path) -> tuple[list[Path], list[str]]:
    """Capture screenshots for `shots` from the built viewer `page` into `out_dir`."""
    if os.name != "posix":
        return [], ["shots --capture needs a POSIX system for Chrome's pipe protocol"]
    chrome = find_chrome()
    if not chrome:
        return [], ["no Chrome or Chromium found: install Chrome or set CHROME_BIN to capture shots"]
    if out_dir.is_symlink():
        return [], [f"{out_dir} is a symlink: write screenshots only into a real folder"]
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="aidd-shots-", ignore_cleanup_errors=True) as profile:
        try:
            proc, cdp = launch(chrome, Path(profile))
        except OSError as exc:
            return [], [f"cannot launch Chrome ({chrome}): {exc}"]
        try:
            cdp.call("Browser.getVersion")
            targets = cdp.call("Target.getTargets")["targetInfos"]
            tid = next(t["targetId"] for t in targets if t["type"] == "page")
            session = cdp.call("Target.attachToTarget", targetId=tid, flatten=True)["sessionId"]
            cdp.call("Page.enable", session)
            cdp.call("Runtime.enable", session)
            base_uri = page.resolve().as_uri()
            for shot in shots:
                name = Path(str(shot["file"])).name
                dest = out_dir / name
                _capture_one(cdp, session, base_uri + str(shot["link"]), shot, dest)
                written.append(dest)
        except (OSError, TimeoutError, ConnectionError, RuntimeError, StopIteration, ValueError) as exc:
            return written, [f"Chrome screenshot capture failed: {exc}"]
        finally:
            cdp.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    return written, []
