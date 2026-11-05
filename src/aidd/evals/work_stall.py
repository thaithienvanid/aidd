"""The stall reading of `aidd eval work`: where each Spec stopped, from the files in every worktree and branch, and how long ago
anyone last touched its scope. It reads git and files with no model, starts no agent, and writes nothing.

A Spec's progress is the furthest of five points it has reached, whichever place holds that version: an outline (a placeholder
still in its body or scope), filled (no placeholder, but no test commands yet), tests written (test commands with no
placeholder), ready (stored status `ready`), or approved (stored status approved or later). A stall reads as many Specs at
`outline` and none at `ready`: the loop stopped before a person was asked.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import workitems
from aidd.kernel import documents, git

PROGRESS = ("outline", "filled", "tests written", "ready", "approved")
# The most Specs the reading lists one by one; the counts cover all of them.
MAX_ROWS = 200
PLACEHOLDER = "TODO"


def progress_of(text: str) -> str | None:
    """The furthest point the Spec `text` shows, or None when it is no Spec or was cancelled."""
    try:
        data, body = documents.split_front_matter(text, "spec")
    except documents.DocumentError:
        return None
    if data.get("type") != "spec":
        return None
    status = workitems.stored_status(data) or "draft"
    if status == "cancelled":
        return None
    if status in workitems.PAST_APPROVAL:
        return "approved"
    if status == "ready":
        return "ready"
    tests = data.get("tests")
    if isinstance(tests, dict) and tests.get("commands") and PLACEHOLDER not in str(tests):
        return "tests written"
    return "filled" if PLACEHOLDER not in body and PLACEHOLDER not in str(data.get("tasks")) else "outline"


def _scope(text: str) -> list[str]:
    try:
        data, _ = documents.split_front_matter(text, "spec")
    except documents.DocumentError:
        return []
    tasks = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    return [
        str(p) for t in tasks if isinstance(t.get("scope"), list) for p in t["scope"] if p and PLACEHOLDER not in str(p) and not str(p).startswith((":", "-"))
    ]


def _read_place(root: Path, place: str, path: str) -> str | None:
    """The text of `path` as `place` (`worktree:<path>`, `branch:<name>`, or `remote:<remote>/<name>`) holds it."""
    kind, _, where = place.partition(":")
    if kind == "worktree":
        try:
            return (Path(where) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    return git.show(f"refs/heads/{where}" if kind == "branch" else f"refs/remotes/{where}", path, str(root))


def _last_scope_commit(root: Path, scope: list[str]) -> int | None:
    """When any branch last committed in `scope`, as epoch seconds; None when no commit touches it."""
    if not scope:
        return None
    stamp = git.run(["log", "-1", "--all", "--format=%ct", "--", *scope], str(root), check=False).strip()
    return int(stamp) if stamp.isdigit() else None


_EMPTY: dict = {
    "progress": dict.fromkeys(PROGRESS, 0),
    "specs": [],
    "days_since_last_scope_commit": None,
    "no_holder": 0,
    "open_specs": 0,
    "drafts_valid": 0,
    "drafts": 0,
}


def read_stall(root: Path, today: dt.date | None = None) -> dict:
    """Specs by furthest point across every worktree and branch, with the days since the last commit in each one's scope.

    `no_holder` counts the open Specs of this worktree whose next step belongs to nobody, and `drafts_valid` the drafts of
    it that hold no placeholder and pass `aidd validate`. When the worktrees and branches cannot be read, `error` says why
    and the counts are zero, so a reader never takes them for a finding."""
    today = today or dt.date.today()
    cfg = workitems.config_at(root)
    furthest: dict[str, tuple[str, list[str]]] = {}
    try:
        everything = workitems.all_branches_work(root, cfg, include_done=True, use_index=False)["items"]
        here = workitems.open_work(root, cfg)["items"]
    except (OSError, ValueError, git.GitError) as exc:
        return {**_EMPTY, "error": documents.one_line(exc, 300)}
    for item in everything:
        if item.get("type") != "spec" or not item.get("places"):
            continue
        text = _read_place(root, item["places"][0], str(item["path"]))
        reached = progress_of(text) if text is not None else None
        if reached and (str(item["id"]) not in furthest or PROGRESS.index(reached) > PROGRESS.index(furthest[str(item["id"])][0])):
            furthest[str(item["id"])] = (reached, _scope(text or ""))
    counts = {s: sum(1 for st, _ in furthest.values() if st == s) for s in PROGRESS}
    specs = []
    for sid, (reached, scope) in sorted(furthest.items()):
        last = _last_scope_commit(root, scope)
        specs.append({"id": sid, "progress": reached, "days_since_scope_commit": None if last is None else max(0, (today - dt.date.fromtimestamp(last)).days)})
    open_specs = [i for i in here if i.get("type") == "spec"]
    drafts = [i for i in open_specs if i.get("status") == "draft"]
    clean = [i for i in drafts if i["next"]["code"] == "spec.ask_approval"]
    days = [s["days_since_scope_commit"] for s in specs if s["days_since_scope_commit"] is not None]
    return {
        "error": None,
        "progress": counts,
        "specs": specs[:MAX_ROWS],
        "days_since_last_scope_commit": min(days) if days else None,
        "no_holder": sum(1 for i in open_specs if i.get("next", {}).get("who") == "nobody"),
        "open_specs": len(open_specs),
        "drafts_valid": len(clean),
        "drafts": len(drafts),
    }


def stall_text(stall: dict) -> list[str]:
    """The reading as lines a person reads."""
    if stall.get("error"):
        return [f"Stall: not read ({stall['error']}). Fix that, then run `aidd eval work` again; the counts below would be zeros, not facts."]
    counts = ", ".join(f"{s} {stall['progress'][s]}" for s in PROGRESS)
    days = stall["days_since_last_scope_commit"]
    since = "no commit touches any Spec's scope" if days is None else f"the last commit in any Spec's scope was {days} day{'s' if days != 1 else ''} ago"
    return [
        f"Stall: Specs by furthest point across every worktree and branch: {counts}",
        f"- {since}; {stall['no_holder']} of {stall['open_specs']} open Specs have a next step nobody holds; {stall['drafts_valid']} of {stall['drafts']} drafts pass `aidd validate`",
    ]
