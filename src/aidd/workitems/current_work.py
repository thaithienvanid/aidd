"""The open work of this worktree, as `aidd status` shows it: `work_list`'s answer, with a draft Spec read as finished
when its file holds no placeholder and `aidd validate` finds no error in it. It sits beside `work_list` because
validation reaches `work_list`."""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, json_schema, regular_files
from aidd.workitems import (
    approval,
    criteria,
    explorations,
    handoff_notes,
    ids,
    intent_branches,
    intent_checks,
    objects,
    product_scope,
    spec_file,
    status,
    validation,
    work_list,
)


def _holds_placeholder(root: Path, rel: str) -> bool:
    """Whether the document a repository names at `rel` is missing, unreadable, or holds a placeholder. It reads as
    `objects.read_document` does, so a link, a device, a path outside the repository, or a file past the cap reads as
    unreadable, and nothing is read from elsewhere on the machine."""
    text, _ = objects.read_document(root, rel)
    return text is None or status.PLACEHOLDER in text


def _tests_exist(root: Path, data: dict) -> bool:
    """Whether every test file the Spec lists is there, inside the repository: a path outside it, absolute or through
    `..`, is never there, and a glob walks only below its literal start (`objects.files_matching`)."""
    tests = data.get("tests")
    if not isinstance(tests, dict):
        return True
    for entry in tests.get("files") or []:
        name = str(entry).partition("#")[0]
        if regular_files.is_outside(name):
            return False
        if globs.is_pattern(name):
            if not objects.files_matching(root, name):
                return False
        elif not (os.path.lexists(root / name) and Path(os.path.realpath(root / name)).is_relative_to(os.path.realpath(root))):
            return False
    return True


def validates_clean(root: Path, rel: str) -> bool:
    """Whether the Spec file `rel` is finished: no placeholder in it or in a frozen doc it links, every test file it lists
    present, and no error from `aidd validate`. A warning does not count against it."""
    text, _ = objects.read_document(root, rel)
    if text is None or status.PLACEHOLDER in text:
        return False
    try:
        data, _ = documents.split_front_matter(text, rel)
    except documents.DocumentError:
        return False
    if any(_holds_placeholder(root, str(doc)) for doc in spec_file.frozen_docs(data)) or not _tests_exist(root, data):
        return False
    return not [f for f in validation.validate_file(root / rel) if validation.is_error(f)]


def open_work(
    root: Path,
    cfg: config.Config | None,
    *,
    today: dt.date | None = None,
    include_done: bool = False,
    shown: work_list.Shown = work_list.EVERYTHING,
) -> dict:
    """Every work item and its next step (schemas/status.schema.json, without its version field), as `shown` says. The
    intent order of the product scope ranks the Intents."""
    found, unreadable = work_list.read_work(root, cfg)
    scope = product_scope.read(root, (cfg or config.EMPTY).product_dir)
    answer = work_list.open_items(
        found,
        unreadable,
        cfg,
        today=today,
        include_done=include_done,
        shown=shown,
        validates=lambda rel: validates_clean(root, rel),
        approved=lambda rel, data: intent_checks.approved_version(root, rel, data),
        order=scope.order,
        scope=scope,
        merged_on=criteria.merged_days_of(str(root), [d for _, d in found]),
    )
    approval.add_to(root, answer)
    add_intent_branches(root, found, answer)
    add_open_decisions(root, answer)
    if waiting := open_explorations(root, (cfg or config.EMPTY).specs_dir, (cfg or config.EMPTY).product_dir):
        # A pick a person owes is a step of theirs: the work no longer waits on nobody, and something is open.
        answer["explorations"] = waiting
        answer.pop("root_blocker", None)
        if (answer.get("next") or {}).get("code") == "nothing_open":
            answer.pop("next")
    elif (answer.get("next") or {}).get("code") == "nothing_open" and git.repository_top(str(root)) is not None and not _has_other_branches(root):
        answer["next"] = {**answer["next"], "what": "nothing is open: describe the next change to the agent"}
    return answer


def _has_other_branches(root: Path) -> bool:
    """Whether `root`'s repository has any local/remote branch or another worktree outside the current branch."""
    top = git.repository_top(str(root))
    if top is None:
        return False
    current = git.current_branch(top)
    branches = git.run(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], top, check=False).splitlines()
    if any(b and b != current and not b.endswith("/HEAD") for b in branches):
        return True
    worktrees = [ln for ln in git.run(["worktree", "list", "--porcelain"], top, check=False).splitlines() if ln.startswith("worktree ")]
    return len(worktrees) > 1


def add_intent_branches(root: Path, found: list[tuple[str, dict]], answer: dict) -> None:
    """Mark each `batched` Intent and each of its Specs with its `branch_state`, as git says now
    (`intent_branches`, schemas/status.schema.json). Outside a repository it adds nothing."""
    batched = {str(d["id"]) for _, d in found if d.get("type") == "intent" and d.get("reaches") == "batched" and ids.is_id(d.get("id"))}
    wanted = [i for i in answer["items"] if i["id"] in batched]
    if wanted and (top := git.repository_top(str(root))) is not None:
        intent_branches.add_to(top, wanted, {str(d["id"]) for _, d in found if d.get("type") == "spec"})


# The shape of one entry a role leaves for the lead, as the handoff schema, its one owner, gives it.
OPEN_DECISION = f"{handoff_notes.HANDOFF_SCHEMA}#/$defs/open_decision"


def open_decisions_in(text: str) -> list[dict]:
    """Each `open_decisions` entry of `text`'s handoff notes that has the shape the schema gives, with where its answer
    stands (`handoff_notes.decision_states`). An entry that does not read is `aidd validate`'s to name, and the delegate check
    defers on it."""
    states, _ = handoff_notes.decision_states(handoff_notes.handoff_blocks(text))
    return [s for s in states if not json_schema.validate(s["entry"], OPEN_DECISION)]


def add_open_decisions(root: Path, answer: dict) -> None:
    """Mark each Spec whose handoff notes hold an open decision with each entry and where its answer stands
    (schemas/status.schema.json, `open_decisions`), so a person sees what the lead still owes before a merge."""
    for item in answer["items"]:
        if item["type"] == "spec":
            text, _ = objects.read_document(root, str(item["path"]))
            if text and (found := open_decisions_in(text)):
                item["open_decisions"] = found


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
HANDOFF_SHOWN = ("done", "next_role", "needs", "stopped_at")


def add_last_handoff(root: Path, answer: dict) -> None:
    """Where the work on this branch stopped, from the handoff note in its last commit's message: a change with no Spec
    before a PR/MR exists has no Spec to hold the note, so the team writes it there (schemas/status.schema.json,
    `handoff`). Only on a branch of one's own, and only when no Spec the branch is for holds a note itself. The note is
    the agent's account, never a yes."""
    branch = git.current_branch(str(root))
    if not branch:
        return
    names, told = git.default_branches(str(root))
    if told and branch in names:
        return
    home = branch_item(answer["items"], branch)
    if home and _holds_note(root, str(home["path"])):
        return
    head = git.run(["rev-parse", "-q", "--verify", "HEAD^{commit}"], str(root), check=False).strip()
    message = git.messages([head], str(root)).get(head, "") if head else ""
    notes = [note for _, note, _ in handoff_notes.handoff_blocks(message) if isinstance(note, dict)]
    if notes:
        shown = {k: documents.one_line(str(notes[-1][k]), 400) for k in HANDOFF_SHOWN if isinstance(notes[-1].get(k), str)}
        answer["handoff"] = {"branch": branch, "commit": head[:12], **shown}
        if found := open_decisions_in(message):
            answer["handoff"]["open_decisions"] = found


def _holds_note(root: Path, rel: str) -> bool:
    text, _ = objects.read_document(root, rel)
    return bool(text and handoff_notes.handoff_blocks(text))


def open_explorations(root: Path, specs_dir: str = "specs", product_dir: str = "product") -> list[dict]:
    """Each exploration whose `status` is `open`, so a person's pick is owed (schemas/status.schema.json): its file, its
    question, the work item whose folder holds it, and the step. A file that does not parse is left to `aidd validate`."""
    out = []
    for folder in explorations.folders(root, specs_dir, product_dir):
        path = folder / explorations.EXPLORATION_FILE
        text, _ = objects.read_document(root, path.relative_to(root).as_posix())
        try:
            data, _ = documents.split_front_matter(text, path.as_posix()) if text is not None else ({}, "")
        except documents.DocumentError:
            continue
        if not isinstance(data, dict) or data.get("type") != "exploration" or data.get("status") != "open":
            continue
        owner = folder.parent.parent.name if folder.parent.name == explorations.EXPLORE_FOLDER else ""
        item = owner if ids.is_id(owner) else ""
        step = work_list.spoken(work_list.step_of_code("exploration.open"), item)
        out.append({"path": path.relative_to(root).as_posix(), "question": str(data.get("question") or ""), **({"item": item} if item else {}), "next": step})
    return out
