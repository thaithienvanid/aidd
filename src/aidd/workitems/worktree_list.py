"""The repository's worktrees and what each one holds: its work item, its state, its loop, and its namespace for
the project's dev services. Read from git each time, never from a record that can drift: `git worktree list` names
them, and each one's branch, head, and files say the rest.

A state, the first that holds:
- `missing`: git lists it, but its folder is gone (`aidd worktrees clean` prunes it)
- `uncommitted work`: its folder holds changes nobody committed (never cleaned)
- `merged`: its branch's head is in the base branch, and the base moved past it (cleaned)
- `new`: its head is the base branch's tip: nothing done yet
- `stale`: no commit for STALE_DAYS (listed, never cleaned: a person decides)
- `active`: everything else
The main worktree is never cleaned, whatever its state.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from aidd.kernel import git

STALE_DAYS = 14
# A branch named for a work item: its last path part (`spec/SPEC-3`).
_ITEM = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9]*-[0-9]+)$")


def worktree_slug(top: str) -> str:
    """A stable name for one worktree, safe in a database, bucket, or project name: the folder's name and a short hash
    of its full path (`aidd_wt_v2_3f9a1c`). The project's dev services name what they make per worktree by it."""
    name = re.sub(r"[^a-z0-9]+", "_", Path(top).name.lower()).strip("_")[:24] or "wt"
    return f"{name}_{hashlib.sha256(str(Path(top).resolve()).encode()).hexdigest()[:6]}"


def _listed(root: str) -> list[dict]:
    """`git worktree list --porcelain`, as {path, head, branch} each; the first is the main worktree."""
    rows: list[dict] = []
    for block in git.run(["worktree", "list", "--porcelain"], root, check=False).strip().split("\n\n"):
        row: dict = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree":
                row["path"] = value
            elif key == "HEAD":
                row["head"] = value
            elif key == "branch":
                row["branch"] = value.removeprefix("refs/heads/")
        if row.get("path"):
            rows.append(row)
    return rows


def _state(row: dict, base_tip: str | None, root: str) -> str:
    path, head = row["path"], row.get("head") or ""
    if not Path(path).is_dir():
        return "missing"
    if git.run(["status", "--porcelain"], path, check=False).strip():
        return "uncommitted work"
    if base_tip and head == base_tip:
        return "new"
    if base_tip and head and git.ok(["merge-base", "--is-ancestor", head, base_tip], root):
        return "merged"
    when = git.run(["log", "-1", "--format=%ct", head], root, check=False).strip() if head else ""
    if when.isdigit() and time.time() - int(when) > STALE_DAYS * 86400:
        return "stale"
    return "active"


def worktree_states(root: str) -> list[dict]:
    """Every worktree of the repository at `root`: {path, branch, head, main, item, state, slug}."""
    try:
        base_tip = git.run(["rev-parse", "--verify", "--quiet", git.default_base(root)], root, check=False).strip() or None
    except git.GitError:
        base_tip = None
    out = []
    for i, row in enumerate(_listed(root)):
        branch = row.get("branch")
        m = _ITEM.search(branch or "")
        state = _state(row, base_tip, root)
        out.append(
            {
                "path": row["path"],
                "branch": branch,
                "head": row.get("head"),
                "main": i == 0,
                "item": m.group(1).upper() if m else None,
                "state": state,
                "slug": worktree_slug(row["path"]),
            }
        )
    return out


def cleanable(rows: list[dict], here: str | None = None) -> list[dict]:
    """The worktrees `aidd worktrees clean` removes: missing ones, and merged ones with nothing uncommitted. Never the
    main worktree, and never the one it runs in (`here`)."""
    mine = str(Path(here).resolve()) if here else None
    return [r for r in rows if not r["main"] and r["state"] in ("missing", "merged") and str(Path(r["path"]).resolve()) != mine]
