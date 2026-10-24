"""Local events: a local `aidd gate` run on a branch, and an `aidd land` run, keep their decision as one gate line in the
git directory's events.jsonl, and each `aidd test` run keeps one test line; `aidd metrics` and the digest's team view
read them when given no file.

A line is a record of what happened on this machine, never evidence: nothing in the gate, land, or the guard reads it,
and anyone with a shell here can edit it. Keeping it never changes the gate's decision, exit code, or stdout. Any
failure (a link in place of the file, a held lock, a full disk, a byte that is not UTF-8) is one warning on stderr.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from aidd import autopilot, config, gate, tracking
from aidd.kernel import git, json_schema

# The writer skips a file over this size, so a forged huge file cannot slow every gate run (CWE-400).
MAX_BYTES = 8 * 1024 * 1024


def store_file(root: str = ".") -> Path:
    """The git directory's events.jsonl, which every worktree of the repository shares; ValueError outside git."""
    return config.state_dir(root) / autopilot.RUN_EVENTS_FILE


def _change(root: str) -> str:
    """The change a local run is about: the branch, or the commit when the head is detached; never `HEAD`."""
    branch = git.run(["symbolic-ref", "--short", "-q", "HEAD"], root, check=False).strip()
    return branch or git.run(["rev-parse", "--short=12", "HEAD"], root, check=False).strip()


def record(decision: gate.Decision, root: str = ".", *, change: str | None = None) -> None:
    """Append the gate's `decision` as one gate line; on any failure, one warning on stderr and nothing else. `change` names
    the branch when the run has moved off it (`aidd land` ends on the base branch)."""
    _keep(root, "gate", lambda repo: gate.decision_event(decision, repo) | {"change": change or _change(root), "author": None, "run_url": None})


def record_test(ev: dict, passed: bool, root: str = ".") -> None:
    """Append one `aidd test` run (its evidence `ev`) as a test line, for the suite runs per head; never evidence."""
    results = ev.get("results") or []
    test = {
        "head_sha": ev["head_sha"],
        "base_sha": ev["base_sha"],
        "result": "pass" if passed else "fail",
        "red": any(r.get("red_green") == "red" for r in results),
        "partial": bool(ev.get("partial")),
        "commands": sum(1 for r in results if r.get("red_green") == "green"),
        "duration_seconds": round(sum(float(r.get("duration_seconds") or 0) for r in results), 3),
    }
    _keep(root, "test", lambda repo: gate.event_header() | {"kind": "test", "repo": repo, "change": _change(root), "test": test})


def _keep(root: str, what: str, build) -> None:
    """Build a line with `build(repo)` and append it, or say once on stderr why not; never anything else."""
    shown = f".git/{config.STATE_DIR}/{autopilot.RUN_EVENTS_FILE}"
    try:
        path = store_file(root)
        shown = str(path)
        try:
            size = os.lstat(path).st_size
        except FileNotFoundError:
            size = 0
        if size > MAX_BYTES:
            raise ValueError(f"it is over 8 MiB ({size} bytes); remove it, or keep only its last lines")
        # The repository is the folder that holds the git common directory, the same from every worktree.
        line = build(path.parent.parent.parent.name)
        if errs := json_schema.validate(line, "event.schema.json"):
            raise ValueError(f"invalid {what} event: {'; '.join(errs)}")
        autopilot.append_event(root, line)
    except Exception as exc:  # noqa: BLE001  # a record of the run must never change the run
        print(f"warning: the {what} event was not kept in {shown}: {exc}", file=sys.stderr)


def default_files(root: str = ".") -> list[str]:
    """The event files `aidd metrics` and the digest's team view read when given none: the git directory's events.jsonl,
    then aidd-events.jsonl in the working directory, each when it is a file. A gate run writes to one of them only."""
    out = []
    try:
        local = store_file(root)
        if local.is_file():
            out.append(str(local))
    except ValueError:
        pass
    ci = Path(root) / tracking.ROLLUP_EVENTS_FILE
    if ci.is_file():
        out.append(str(ci))
    return out
