"""Run something again whenever a file of the repository changes: `aidd test --watch`. Stdlib only, by polling."""

from __future__ import annotations

import os
import time

from aidd.kernel import git


def snapshot(repo: str = ".", exclude: str | None = None) -> dict[str, tuple[int, int]]:
    """The modification time and size of every tracked or untracked, not ignored file, except those under `exclude`."""
    names = git.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo).split("\0")
    prefix = exclude.rstrip("/") + "/" if exclude else None
    out: dict[str, tuple[int, int]] = {}
    for name in names:
        if not name or (prefix and name.startswith(prefix)):
            continue
        try:
            st = os.stat(os.path.join(repo, name))
        except OSError:
            continue  # deleted: its absence changes the snapshot
        out[name] = (st.st_mtime_ns, st.st_size)
    return out


def watch_tests(run_once, *, repo: str = ".", interval_seconds: float = 1.0, exclude: str | None = None, sleep=time.sleep, max_runs: int | None = None) -> int:
    """Run `run_once` now and again whenever a file changes, polling every `interval` seconds, until Ctrl-C (exit 0).

    Stdlib only: it compares modification times and sizes, so it needs no file-system events. The snapshot is taken
    again after each run, so a test that rewrites a file (a snapshot, a cache) does not start the next run by itself."""
    last: dict[str, tuple[int, int]] | None = None
    runs = 0
    try:
        while True:
            now = snapshot(repo, exclude)
            if now != last:
                run_once()
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    return 0
                last = snapshot(repo, exclude)
            sleep(interval_seconds)
    except KeyboardInterrupt:
        return 0
