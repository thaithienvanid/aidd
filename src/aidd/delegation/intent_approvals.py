"""What a delegated change does to a person's approval of an Intent, read from git objects and never the working tree.

What a person's `intent.approve` covers is decided once, in `workitems` (`approved_changes`): everything in an Intent's front matter
and its body except the few fields an agent keeps writing. A delegated push, merge, or Spec approval defers on a change to it,
and a delegated Spec approval defers unless each Intent it answers to stands approved on the default branch's tip.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from aidd import config, workitems
from aidd.delegation import local_run
from aidd.kernel import documents, git, retired_names

if TYPE_CHECKING:
    from aidd.delegation.check import Check

APPROVAL = ("approval",)
# An Intent as a change holds it, by its file: the path, the front matter in today's shape, and the body.
Held = tuple[str, dict, str]


def _approved(data: dict) -> bool:
    """Whether the file claims an approval: `approval` is set, in any shape. Whether a person's commit holds it is another
    question (`workitems.approved_version`); a file that claims one is held to it either way."""
    return any(data.get(field) for field in APPROVAL)


def _intents(ref: str, paths: list[str], cwd: str) -> tuple[dict[str, list[Held]], list[str]]:
    """The Intents among `paths` as `ref` holds them, by id, and the paths of Intents that cannot be read in today's shape. A file
    that is no work item, or holds no Intent, is no Intent here."""
    found: dict[str, list[Held]] = {}
    unreadable = []
    for path in paths:
        text = git.show(ref, path, cwd)
        if text is None:
            continue
        try:
            data, body = documents.split_front_matter(text, path)
        except documents.DocumentError:
            continue
        if data.get("type") != "intent":
            continue
        try:
            found.setdefault(str(data.get("id")), []).append((path, workitems.todays_shape(data), body))
        except retired_names.Refused:
            unreadable.append(path)
    return found, unreadable


_COMMIT_ID = re.compile(r"[0-9a-f]{40,64}")


def _unheld_commits(then: Held, now: Held, tip: str, cwd: str) -> bool:
    """Whether `now` records a slice's `merged_in` that `then` did not, naming no commit that is newer than the approval and on the
    default branch's tip `tip`: only a commit there, after the person approved, can have merged the slice, so an id that names none, one
    only the branch holds, and an old commit such as the first one are a change. A slice delivered in another repository is left out
    (`workitems.new_merged_in`). Fails closed when the approval cannot be dated."""
    try:
        new = workitems.new_merged_in(then[1], now[1])
    except retired_names.Refused:
        return False
    if not new:
        return False
    since = workitems.approval_commit(Path(cwd), then[0], then[1], tip)
    return any(not (since and _COMMIT_ID.fullmatch(sha) and sha != since and _ancestor(sha, tip, cwd) and _ancestor(since, sha, cwd)) for sha in new)


def _ancestor(older: str, newer: str, cwd: str) -> bool:
    """Whether the commit `older` is on the history of `newer`, or is it."""
    return git.ok(["merge-base", "--is-ancestor", older, newer], cwd)


def _differs(then: Held, now: Held, tip: str, cwd: str, kept_commits: bool = True) -> list[str]:
    """What an approval covers that differs between two versions of an Intent, by name; `unreadable` for a shape that cannot be compared.
    A slice's new `merged_in` is one of them unless it names a commit of the default branch newer than the approval, and only for what
    a branch changes (`kept_commits`): the tip's own version is what a person's merge put there."""
    try:
        names = workitems.approved_changes(then[1], now[1], then[2], now[2])
    except retired_names.Refused:
        return ["unreadable"]
    return [*names, "merged_in"] if kept_commits and "merged_in" not in names and _unheld_commits(then, now, tip, cwd) else names


def changes(base: str, head: str, cwd: str, paths: list[str]) -> list[str]:
    """Each way the change `base...head`, which touches `paths`, moves a person's approval, as `path (id): what`: an approved Intent
    that the head changes in anything the approval covers, or no longer holds, and any Intent whose `approval` the
    head sets or changes, which only a person's merge puts on the default branch. An Intent is found by its id, so one moved to
    another path with nothing changed is no change. An Intent that cannot be read counts, because nothing then shows what it covers.
    A draft Intent that no person approved, and what an agent keeps writing (`workitems.AGENT_KEPT`), change none of it."""
    start = git.merge_base(base, head, cwd)
    files = [p for p in paths if p.lower().endswith(".md")]
    before, bad_before = _intents(start, files, cwd)
    after, bad_after = _intents(head, files, cwd)
    out = [f"{path}: it cannot be read as an Intent, so no one can tell what it covers" for path in dict.fromkeys([*bad_before, *bad_after])]
    for ident, olds in before.items():
        news = after.get(ident, [])
        for old in (o for o in olds if _approved(o[1])):
            if not news:
                out.append(f"{old[0]} ({ident}): the approved Intent is gone, or no longer reads as an Intent")
            out += [f"{new[0]} ({ident}): {', '.join(names)} changed" for new in news if (names := _differs(old, new, base, cwd))]
    for ident, news in after.items():
        for path, new, _body in news:
            if _approved(new) and not any(all(old[1].get(f) == new.get(f) for f in APPROVAL) for old in before.get(ident, [])):
                out.append(f"{path} ({ident}): it sets or changes approval: only a person's merge puts an approval on the default branch")
    return out


def intents_listing(check: Check, spec_id: str) -> list[str]:
    """The ids of the Intents that list `spec_id` as a slice, on the default branch's tip and on the head, whatever the Spec says its
    `parent` is. One only the head holds is held to the tip like any other, so it defers: the tip holds no such Intent."""
    return [
        str(data.get("id")) for ref in (check.tip, check.req.head) for _path, data in _intents_at(check, ref) if spec_id in workitems.planned_spec_ids(data)
    ]


def _intents_at(check: Check, ref: str) -> Iterator[tuple[str, dict]]:
    return local_run.intents_at(check.top, ref, local_run.specs_dir(check.cfg), local_run.product_dir(check.cfg))


def _ended(data: dict) -> str:
    """The state a person ended an Intent in (`done` or `cancelled`, a `no_go` being `cancelled`), or ""."""
    state = workitems.intent_status(data, [])
    return state if state in config.status_set("intent", "ended") else ""


def not_approved(check: Check, parent: str, spec_id: str) -> str:
    """Why the Intent `parent` does not stand approved, for the Spec `spec_id`, on the default branch's tip, or "": the tip holds it, a
    person's commit holds its approval (`workitems.approved_document`), nothing the approval covers changed after it, the approved
    version lists the Spec as a slice, and no person ended it."""
    cfg, default = check.cfg, check.default
    found = local_run.intent_by_id(check.top, check.tip, local_run.specs_dir(cfg), local_run.product_dir(cfg), parent)
    if found is None:
        return f"{parent} is no Intent the tip of {default} holds"
    path, data, text, _errors = found
    if state := _ended(data):
        return f"{parent} is {state} on {default}: a person ended it, so ask them whether to reopen it or to drop {spec_id}"
    approved = workitems.approved_document(Path(check.top), path, data, check.tip)
    if approved is None:
        who = workitems.approval_of(data)[0] or "a person"
        return (
            f"no commit on {default} with an Approved-by line of {documents.one_line(who, 120)} and an Approves line of {parent} holds the approval of {parent}"
        )
    names = _differs((path, *approved), (path, data, documents.split_front_matter(text, path)[1]), check.tip, check.top, kept_commits=False)
    if names:
        return f"{parent} changed on {default} after the approval: {', '.join(names)}"
    if spec_id not in workitems.planned_spec_ids(approved[0]):
        return f"{parent} as the person approved it lists no slice {spec_id}: add the slice line, then ask the person to approve the Intent"
    return ""


def head_differs(check: Check, parent: str) -> str:
    """Why the head holds the Intent `parent` differently from what the person approved on the default branch's tip, or "": the
    branch may be behind the approval or ahead of it, and only the tip's approval counts. Read once `not_approved` found one."""
    cfg = check.cfg
    specs, product = local_run.specs_dir(cfg), local_run.product_dir(cfg)
    tip, head = (local_run.intent_by_id(check.top, ref, specs, product, parent) for ref in (check.tip, check.req.head))
    if tip is None:
        return ""
    approved = workitems.approved_document(Path(check.top), tip[0], tip[1], check.tip)
    if approved is None:
        return ""
    if head is None:
        return f"{parent} is gone from the head, though a person approved it on {check.default}: restore it, or update the branch from {check.default}"
    held = (head[0], head[1], documents.split_front_matter(head[2], head[0])[1])
    names = _differs((tip[0], *approved), held, check.tip, check.top, kept_commits=False)
    # A `merged_in` the tip's own version holds is what a person's merge put there. Only one the head adds to it is held to the tip.
    current = (tip[0], tip[1], documents.split_front_matter(tip[2], tip[0])[1])
    if not names and _unheld_commits(current, held, check.tip, check.top):
        names = ["merged_in"]
    if not names:
        return ""
    return f"the head holds {parent} differently from what the person approved on {check.default}: {', '.join(names)}; update the branch from {check.default}, or undo the change"
