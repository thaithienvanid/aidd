"""The open work of this worktree, as `aidd status` shows it: `work_list`'s answer, with a draft Spec read as finished
when its file holds no placeholder and `aidd validate` finds no error in it. It sits beside `work_list` because
validation reaches `work_list`."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git
from aidd.workitems import explorations, handoff_notes, ids, intent_checks, spec_file, validation, work_list


def _holds_placeholder(path: Path) -> bool:
    """Whether the file is missing, unreadable, or holds a placeholder."""
    try:
        return "TODO" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True


def _tests_exist(root: Path, data: dict) -> bool:
    """Whether every test file the Spec lists is there."""
    tests = data.get("tests")
    if not isinstance(tests, dict):
        return True
    for entry in tests.get("files") or []:
        name = str(entry).partition("#")[0]
        if not (any(root.glob(name)) if any(c in name for c in "*?[") else (root / name).exists()):
            return False
    return True


def validates_clean(root: Path, rel: str) -> bool:
    """Whether the Spec file `rel` is finished: no placeholder in it or in a frozen doc it links, every test file it lists
    present, and no error from `aidd validate`. A warning does not count against it."""
    path = root / rel
    if _holds_placeholder(path):
        return False
    try:
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), rel)
    except (OSError, documents.DocumentError):
        return False
    if any(_holds_placeholder(root / doc) for doc in spec_file.frozen_docs(data)) or not _tests_exist(root, data):
        return False
    return not [f for f in validation.validate_file(path) if validation.is_error(f)]


def open_work(
    root: Path, cfg: config.Config | None, *, today: dt.date | None = None, include_done: bool = False, shown: work_list.Shown = work_list.EVERYTHING
) -> dict:
    """Every work item and its next step (schemas/status.schema.json, without its version field), as `shown` says."""
    found, unreadable = work_list.read_work(root, cfg)
    answer = work_list.open_items(
        found,
        unreadable,
        cfg,
        today=today,
        include_done=include_done,
        shown=shown,
        validates=lambda rel: validates_clean(root, rel),
        agreed=lambda rel, data: intent_checks.agreed_version(root, rel, data),
    )
    if waiting := open_explorations(root, cfg.specs_dir if cfg else "specs"):
        # A pick a person owes is a step of theirs: the work no longer waits on nobody, and something is open.
        answer["explorations"] = waiting
        answer.pop("root_blocker", None)
        if (answer.get("next") or {}).get("code") == "nothing_open":
            answer.pop("next")
    return answer


# The most unsaved paths an item names; the count covers all of them.
MAX_UNSAVED_PATHS = 10


def add_branch_facts(root: Path, answer: dict) -> None:
    """What this worktree's branch adds to the open work: the paths nobody committed on it (`add_unsaved`), and where
    the work stopped, by its last commit's note (`add_last_handoff`)."""
    add_unsaved(root, answer)
    add_last_handoff(root, answer)


# A part of a branch's name that names one of a Spec's Tasks: the Spec's id, then `-T` and the Task's number.
TASK_BRANCH = re.compile(r"(.+)-T\d+")


def branch_item(items: list[dict], branch: str) -> dict | None:
    """The open item a branch is for, by a part of its name that is the item's id or one of its Tasks', such as SPEC-1 on
    `spec/SPEC-1` or `spec/SPEC-1-T2`, or None. `unsaved`, the handoff note, and the work-items page read this one rule."""
    named = {part for part in branch.split("/") if ids.is_id(part)}
    named |= {found.group(1) for part in named if (found := TASK_BRANCH.fullmatch(part))}
    return next((i for i in items if i["id"] in named), None)


def add_unsaved(root: Path, answer: dict) -> None:
    """Mark the work item this worktree's branch is for, such as SPEC-1 on `spec/SPEC-1`, with the paths not yet
    committed there (schemas/status.schema.json, `unsaved`). Removing the worktree loses work in no commit yet, and nobody
    who comes back after a stop can see it. A branch that names no open item, or a clean tree, adds nothing."""
    branch = git.current_branch(str(root))
    item = branch_item(answer["items"], branch)
    if item is None:
        return
    paths = git.dirty(str(root), untracked=True, check=False)
    if paths:
        item["unsaved"] = {"branch": branch, "count": len(paths), "paths": paths[:MAX_UNSAVED_PATHS]}


# The note's fields `aidd status` shows, in the note's own order.
HANDOFF_SHOWN = ("done", "next", "needs", "stopped_at")
TRUNKS = ("main", "master")


def add_last_handoff(root: Path, answer: dict) -> None:
    """Where the work on this branch stopped, from the handoff note in its last commit's message: a change with no Spec
    before a PR/MR exists has no Spec to hold the note, so the team writes it there (schemas/status.schema.json,
    `handoff`). Only on a branch of one's own, and only when no Spec the branch is for holds a note itself. The note is
    the agent's account, never a yes."""
    branch = git.current_branch(str(root))
    if (
        not branch
        or branch in TRUNKS
        or branch == git.run(["symbolic-ref", "-q", "refs/remotes/origin/HEAD"], str(root), check=False).strip().removeprefix("refs/remotes/origin/")
    ):
        return
    home = branch_item(answer["items"], branch)
    if home and _holds_note(root / str(home["path"])):
        return
    head = git.run(["rev-parse", "-q", "--verify", "HEAD^{commit}"], str(root), check=False).strip()
    message = git.messages([head], str(root)).get(head, "") if head else ""
    notes = [note for _, note, _ in handoff_notes.handoff_blocks(message) if isinstance(note, dict)]
    if notes:
        shown = {k: documents.one_line(str(notes[-1][k]), 400) for k in HANDOFF_SHOWN if isinstance(notes[-1].get(k), str)}
        answer["handoff"] = {"branch": branch, "commit": head[:12], **shown}


def _holds_note(path: Path) -> bool:
    try:
        return bool(handoff_notes.handoff_blocks(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def open_explorations(root: Path, specs_dir: str = "specs") -> list[dict]:
    """Each exploration whose `status` is `open`, so a person's pick is owed (schemas/status.schema.json): its file, its
    question, the work item whose folder holds it, and the step. A file that does not parse is left to `aidd validate`."""
    out = []
    for folder in explorations.folders(root, specs_dir):
        path = folder / explorations.EXPLORATION_FILE
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())
        except (OSError, UnicodeDecodeError, documents.DocumentError):
            continue
        if not isinstance(data, dict) or data.get("type") != "exploration" or data.get("status") != "open":
            continue
        owner = folder.parent.parent.name if folder.parent.name == explorations.EXPLORE_FOLDER else ""
        item = owner if ids.is_id(owner) else ""
        step = work_list.spoken(work_list.step_of_code("exploration.open"), item)
        out.append({"path": path.relative_to(root).as_posix(), "question": str(data.get("question") or ""), **({"item": item} if item else {}), "next": step})
    return out
