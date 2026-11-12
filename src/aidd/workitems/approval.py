"""A person's approval of Intents, recorded from their own terminal: `aidd approve <ID>...`, and the command `aidd status`
offers for it. The commit that records an approval asks in the harness, so a run that cannot ask, such as a headless
one, stops there. The person then runs `aidd approve` themselves. aidd sets `approval: {by, at}` (their git identity and the
time) on the named Intents alone, and commits those files alone with their `Approved-by:` line and an `Approves:` line that names
each Intent, which is the approval's hold (`intent_checks.stamped_version`). Nothing a run saved is applied: the edit is aidd's
own, so a crafted file can never commit anything under the person's name.

`aidd approve` is `intent.approve`, an `ask` in the risk rules, so an agent's harness asks before it runs, as it asks before
the commit. aidd never runs it on its own."""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, git, regular_files, timestamps
from aidd.workitems import approval_commits, ids, objects

# The field the approval sets: one object, `{by, at}`.
FIELD = "approval"


def person_command(intent_ids: list[str]) -> str:
    """`aidd approve` for the Intents, or "" when there is none or an id holds other text."""
    if not intent_ids or not all(ids.is_id(i) for i in intent_ids):
        return ""
    return "aidd approve " + " ".join(intent_ids)


def _waiting(answer: dict) -> dict[str, dict]:
    """The Intents of `aidd status`' answer that wait for a person's approval, by id."""
    return {
        str(item["id"]): item
        for item in answer["items"]
        if item["type"] == "intent" and (step := item.get("next")) and step["code"] == "intent.approve" and ids.is_id(str(item["id"]))
    }


def add_to(root: Path, answer: dict) -> None:
    """Add to the sentence of each Intent that waits for its approval the command that records it from the person's
    own terminal. The Intents of one request, by their `request`, share one command, so one yes records a whole split."""
    waiting = _waiting(answer)
    shallow = bool(waiting) and approval_commits.is_shallow_clone(root)
    groups: dict[str, list[str]] = {}
    for iid, item in waiting.items():
        text, _ = objects.read_document(root, str(item["path"]))
        try:
            data, _ = documents.split_front_matter(text, str(item["path"])) if text is not None else ({}, "")
        except documents.DocumentError:
            data = {}
        if shallow and isinstance(data.get("approval"), dict):
            who = str(data["approval"].get("by") or "")
            item["next"]["what"] = f"its approval has no hold, so aidd reads it as draft: {approval_commits.shallow_clone_sentence(iid, who, 'aidd status')}"
            continue
        if text is not None and _multiline_field(text, FIELD):
            item["next"]["what"] = f"its `{FIELD}` spans more than one line, so `aidd approve` cannot edit it: {_multiline_fix(iid)}"
            continue
        request = data.get("request")
        groups.setdefault(f"request:{request}" if isinstance(request, str) and request else f"id:{iid}", []).append(iid)
    for group in groups.values():
        if not (command := person_command(group)):
            continue
        for iid in group:
            waiting[iid]["next"]["what"] += f"; to approve from your own terminal instead, run this in the repository: {command}"


def _identity(root: Path) -> str:
    """The person's git identity as `Name <email>`, the value `approval.by` and the trailer hold; a ValueError with the next
    step when git has none, or when it names an agent or a bot."""
    name = git.run(["config", "user.name"], str(root), check=False).strip()
    email = git.run(["config", "user.email"], str(root), check=False).strip()
    if not name or not email:
        raise ValueError(
            'git knows no identity of yours here: run `git config user.name "Your Name"` and `git config user.email you@example.com`, then run this again'
        )
    who = f"{name} <{email}>"
    if config.is_agent(who) or config.approved_by_kind(who) == "agent":
        raise ValueError(f"your git identity {who} names an agent or a bot, and only a person approves an Intent: set your own name and email in git")
    if "\n" in who or "\r" in who:
        raise ValueError("your git identity holds a line break: set a plain name and email in git, then run this again")
    return who


class _MultilineFieldError(ValueError):
    pass


def _is_multiline_after(lines: list[str], at: int) -> bool:
    return at + 1 < len(lines) and lines[at + 1][:1] in (" ", "\t", "-")


def _multiline_field(text: str, field: str) -> bool:
    """Whether `field:` in `text`'s front matter spans more than one line."""
    m = documents.FRONT_MATTER.match(text)
    if not m:
        return False
    lines = m.group(1).split("\n")
    at = next((i for i, ln in enumerate(lines) if re.match(rf"{field}:(?:[ \t]|$)", ln)), None)
    return at is not None and _is_multiline_after(lines, at)


def _multiline_fix(iid: str) -> str:
    quoted = command_names.quoted(iid) or "<ID>"
    shown_id = quoted if iid == quoted else "<ID>"
    return (
        f'write `{FIELD}: {{by: "Your Name <you@example.com>", at: "YYYY-MM-DDTHH:MM:SSZ"}}` on one line and commit it with `{approval_commits.APPROVED_BY}:` and `{approval_commits.APPROVES}: {shown_id}` lines, '
        f"or remove `{FIELD}:`, commit that edit, and run `aidd approve {quoted}`"
    )


def _set_fields(text: str, values: dict[str, dict[str, str]]) -> str:
    """`text` with each top-level field of its front matter in `values` set to that object, on one line: a field it holds is
    replaced on its line, and a new one goes last. Each value of the object is written in double quotes, escaped as JSON."""
    m = documents.FRONT_MATTER.match(text)
    if not m:
        raise ValueError("no front matter")
    lines = m.group(1).split("\n")
    for field, value in values.items():
        line = f"{field}: {{{', '.join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in value.items())}}}"
        at = next((i for i, ln in enumerate(lines) if re.match(rf"{field}:(?:[ \t]|$)", ln)), None)
        if at is None:
            lines.append(line)
        else:
            if _is_multiline_after(lines, at):
                raise _MultilineFieldError(f"`{field}` spans more than one line")
            lines[at] = line
    return text[: m.start(1)] + "\n".join(lines) + text[m.end(1) :]


def _new_text(rel: str, text: str, iid: str, values: dict[str, dict[str, str]]) -> str:
    """The Intent's text with the approval set, checked: it parses, and only FIELD changed. A ValueError otherwise."""
    try:
        before, _ = documents.split_front_matter(text, rel)
        if before.get("type") != "intent" or str(before.get("id")) != iid:
            raise ValueError(f"{rel} is no Intent {iid}")
        new = _set_fields(text, values)
        after, _ = documents.split_front_matter(new, rel)
    except _MultilineFieldError as exc:
        raise ValueError(f"{rel}: cannot set `approval` ({exc}): {_multiline_fix(iid)}") from None
    except (ValueError, documents.DocumentError) as exc:
        raise ValueError(f"{rel}: cannot set `approval` ({exc}); fix the file, then run this again") from None
    if {k: v for k, v in after.items() if k != FIELD} != {k: v for k, v in before.items() if k != FIELD} or any(after.get(k) != v for k, v in values.items()):
        raise ValueError(f"{rel}: setting `approval` would change other fields; fix the file, then run this again")
    return new


def record_approval(root: Path, answer: dict, intent_ids: list[str], *, now: str | None = None) -> tuple[str, str, list[str]]:
    """Record the person's approval of each Intent `intent_ids` names, in one commit: (the commit, the identity, each
    Intent's path). Each must wait for its approval in `answer`, `aidd status`' answer, and its file must hold no edit
    that no commit holds, so the commit holds the approval alone. The commit holds those files alone (`--only`, so
    anything else staged stays out), with the person's git identity as author and in the `Approved-by:` line, and each
    Intent's id in the `Approves:` line beside it. Every stop is a ValueError with the next step; a failed commit puts each file
    back as it was."""
    named = list(dict.fromkeys(intent_ids))
    if bad := [i for i in named if not ids.is_id(i)]:
        raise ValueError(f"{bad[0]} is no work item id: name each Intent by its id, such as `aidd approve INTENT-1`")
    waiting = _waiting(answer)
    if not_waiting := [i for i in named if i not in waiting]:
        known = {str(item.get("id")) for item in answer.get("items", []) if item.get("id")}
        if not_waiting[0] not in known:
            raise ValueError(f"no Intent has the id {not_waiting[0]}; run `aidd status` to see open Intents, or `aidd new intent <title>` to create one")
        raise ValueError(f"{not_waiting[0]} waits for no approval: `aidd status {command_names.quoted(not_waiting[0]) or '<ID>'}` says where it stands")
    who = _identity(root)
    values = {FIELD: {"by": who, "at": now or timestamps.utc_stamp()}}
    rels = [str(waiting[i]["path"]) for i in named]
    changed = set(git.dirty(str(root), untracked=True))
    edits: dict[str, tuple[str, str]] = {}
    for iid, rel in zip(named, rels, strict=True):
        if regular_files.is_outside(rel) or regular_files.link_on_the_way(root, rel):
            raise ValueError(f"{rel}: {objects.REFUSED[regular_files.LINK]}")
        if rel in changed:
            raise ValueError(f"{rel} holds an edit no commit holds: commit it or drop it first, so your approval covers what you read")
        raw, why = regular_files.named_file_bytes(root, rel, documents.MAX_DOCUMENT_BYTES)
        if raw is None:
            raise ValueError(f"{rel}: {objects.REFUSED.get(why, why)}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"{rel} is not UTF-8 text: fix the file, then run this again") from None
        edits[rel] = (text, _new_text(rel, text, iid, values))
    for rel, (_, new) in edits.items():
        _write(root / rel, new)
    message = [f"{', '.join(named)}: approved", f"{approval_commits.APPROVED_BY}: {who}\n{approval_commits.APPROVES}: {', '.join(named)}"]
    try:
        git.run(["commit", "--only", "-q", "-m", message[0], "-m", message[1], "--", *rels], str(root))
    except git.GitError as exc:
        for rel, (old, _) in edits.items():
            _write(root / rel, old)
        raise ValueError(f"the commit did not go through, so nothing changed: {documents.one_line(str(exc), 300)}") from None
    return git.rev_parse("HEAD", str(root)), who, rels


def _write(path: Path, text: str) -> None:
    """Write `text` to `path` as it is, never through a link; the file keeps its own mode."""
    with regular_files.open_for_write(path) as f:
        f.write(text.encode("utf-8"))
