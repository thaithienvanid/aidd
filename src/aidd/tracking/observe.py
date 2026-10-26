"""`aidd observe --window`: poll a Spec's observe command until its window ends, and say when the rollback trigger fires.

It reports; it never rolls back. The rollback is the release tooling's, or a person's, to run.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

_WINDOW = re.compile(r"^([0-9]+)([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def window_seconds(window: str) -> int:
    """30m, 24h, 7d (the Spec's `observe.window`), or 90s for a short trial run, in seconds."""
    m = _WINDOW.match(window.strip())
    if not m:
        raise ValueError(f"window {window!r} is not a number followed by s, m, h, or d, such as 24h")
    return int(m.group(1)) * _UNIT[m.group(2)]


@dataclass
class WindowResult:
    result: str  # pass: the window ended with the trigger never firing; fail: it fired
    checks: int
    failures: int


def watch_window(
    check: Callable[[], int],
    *,
    window_s: float,
    every_s: float,
    consecutive: int = 1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] = print,
) -> WindowResult:
    """Run `check` (the observe command; 0 is healthy) every `every_s` seconds for `window_s` seconds.

    The rollback trigger fires after `consecutive` failed checks in a row, which ends the watch at once; a single
    flaky check below that threshold is reported and the watch goes on. A last check runs when the window ends."""
    if every_s <= 0 or window_s <= 0 or consecutive < 1:
        raise ValueError("the window and the interval must be positive, and --consecutive at least 1")
    start = clock()
    checks = failures = streak = 0
    while True:
        code = check()
        checks += 1
        elapsed = clock() - start
        if code == 0:
            streak = 0
            report(f"[{_clock(elapsed)}] check {checks}: healthy")
        else:
            failures += 1
            streak += 1
            report(f"[{_clock(elapsed)}] check {checks}: unhealthy (exit {code}), {streak} of {consecutive} in a row")
            if streak >= consecutive:
                return WindowResult("fail", checks, failures)
        if elapsed >= window_s:
            return WindowResult("pass", checks, failures)
        sleep(min(every_s, max(window_s - elapsed, 0.0)))


def _clock(s: float) -> str:
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
