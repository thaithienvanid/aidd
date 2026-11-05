"""A person's agreement to Intents, recorded from their own terminal: `aidd agree <ID>...`, and the command `aidd status`
offers for it. The commit that records an agreement asks in the harness, so a run that cannot ask, such as a headless
one, stops there. The person then runs `aidd agree` themselves. aidd sets `agreed_by` (their git identity) and
`agreed_at` on the named Intents alone, and commits those files alone with their `Agreed-by:` trailer. Nothing a run
saved is applied: the edit is aidd's own, so a crafted file can never commit anything under the person's name.

`aidd agree` is `intent.agree`, an `ask` in the risk rules, so an agent's harness asks before it runs, as it asks before
the commit. aidd never runs it on its own."""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, git, regular_files, timestamps
from aidd.workitems import ids, objects

# The fields the agreement sets, in the order they are written.
FIELDS = ("agreed_by", "agreed_at")


def person_command(intent_ids: list[str]) -> str:
    """`aidd agree` for the Intents, or "" when there is none or an id holds other text."""
    if not intent_ids or not all(ids.is_id(i) for i in intent_ids):
        return ""
    return "aidd agree " + " ".join(intent_ids)


def _waiting(answer: dict) -> dict[str, dict]:
    """The Intents of `aidd status`' answer that wait for a person's agreement, by id."""
    return {
        str(item["id"]): item
        for item in answer["items"]
        if item["type"] == "intent" and (step := item.get("next")) and step["code"] == "intent.agree" and ids.is_id(str(item["id"]))
    }


def add_to(root: Path, answer: dict) -> None:
    """Add to the sentence of each Intent that waits for its agreement the command that records it from the person's
    own terminal. The Intents of one request, by their `request`, share one command, so one yes records a whole split."""
    waiting = _waiting(answer)
    groups: dict[str, list[str]] = {}
    for iid, item in waiting.items():
        text, _ = objects.read_document(root, str(item["path"]))
        try:
            data, _ = documents.split_front_matter(text, str(item["path"])) if text is not None else ({}, "")
        except documents.DocumentError:
            data = {}
        request = data.get("request")
        groups.setdefault(f"request:{request}" if isinstance(request, str) and request else f"id:{iid}", []).append(iid)
    for group in groups.values():
        if not (command := person_command(group)):
            continue
        for iid in group:
            waiting[iid]["next"]["what"] += f"; to agree from your own terminal instead, run this in the repository: {command}"


def _identity(root: Path) -> str:
    """The person's git identity as `Name <email>`, the value `agreed_by` and the trailer hold; a ValueError with the next
    step when git has none, or when it names an agent or a bot."""
    name = git.run(["config", "user.name"], str(root), check=False).strip()
    email = git.run(["config", "user.email"], str(root), check=False).strip()
    if not name or not email:
        raise ValueError(
            'git knows no identity of yours here: run `git config user.name "Your Name"` and `git config user.email you@example.com`, then run this again'
        )
    who = f"{name} <{email}>"
    if config.is_agent(who) or config.approved_by_kind(who) == "agent":
        raise ValueError(f"your git identity {who} names an agent or a bot, and only a person agrees to an Intent: set your own name and email in git")
    if "\n" in who or "\r" in who:
        raise ValueError("your git identity holds a line break: set a plain name and email in git, then run this again")
    return who


def _set_fields(text: str, values: dict[str, str]) -> str:
    """`text` with each top-level field of its front matter in `values` set to that value: a field it holds is replaced
    on its line, and a new one goes last. Each value is written in double quotes."""
    m = documents.FRONT_MATTER.match(text)
    if not m:
        raise ValueError("no front matter")
    lines = m.group(1).split("\n")
    for field, value in values.items():
        line = f'{field}: "{value}"'
        at = next((i for i, ln in enumerate(lines) if re.match(rf"{field}:(?:[ \t]|$)", ln)), None)
        if at is None:
            lines.append(line)
        else:
            if at + 1 < len(lines) and lines[at + 1][:1] in (" ", "\t", "-"):
                raise ValueError(f"`{field}` spans more than one line")
            lines[at] = line
    return text[: m.start(1)] + "\n".join(lines) + text[m.end(1) :]


def _new_text(rel: str, text: str, iid: str, values: dict[str, str]) -> str:
    """The Intent's text with the agreement set, checked: it parses, and only FIELDS changed. A ValueError otherwise."""
    try:
        before, _ = documents.split_front_matter(text, rel)
        if before.get("type") != "intent" or str(before.get("id")) != iid:
            raise ValueError(f"{rel} is no Intent {iid}")
        new = _set_fields(text, values)
        after, _ = documents.split_front_matter(new, rel)
    except (ValueError, documents.DocumentError) as exc:
        raise ValueError(f"{rel}: cannot set `agreed_by` and `agreed_at` ({exc}); fix the file, then run this again") from None
    if {k: v for k, v in after.items() if k not in FIELDS} != {k: v for k, v in before.items() if k not in FIELDS} or any(
        str(after.get(k)) != v for k, v in values.items()
    ):
        raise ValueError(f"{rel}: setting `agreed_by` and `agreed_at` would change other fields; fix the file, then run this again")
    return new


def record_agreement(root: Path, answer: dict, intent_ids: list[str], *, now: str | None = None) -> tuple[str, str, list[str]]:
    """Record the person's agreement to each Intent `intent_ids` names, in one commit: (the commit, the identity, each
    Intent's path). Each must wait for its agreement in `answer`, `aidd status`' answer, and its file must hold no edit
    that no commit holds, so the commit holds the agreement alone. The commit holds those files alone (`--only`, so
    anything else staged stays out), with the person's git identity as author and as the `Agreed-by:` trailer. Every
    stop is a ValueError with the next step; a failed commit puts each file back as it was."""
    named = list(dict.fromkeys(intent_ids))
    if bad := [i for i in named if not ids.is_id(i)]:
        raise ValueError(f"{bad[0]} is no work item id: name each Intent by its id, such as `aidd agree INTENT-1`")
    waiting = _waiting(answer)
    if not_waiting := [i for i in named if i not in waiting]:
        raise ValueError(f"{not_waiting[0]} waits for no agreement: `aidd status {command_names.quoted(not_waiting[0]) or '<ID>'}` says where it stands")
    who = _identity(root)
    values = {"agreed_by": who, "agreed_at": now or timestamps.utc_stamp()}
    rels = [str(waiting[i]["path"]) for i in named]
    changed = set(git.dirty(str(root), untracked=True))
    edits: dict[str, tuple[str, str]] = {}
    for iid, rel in zip(named, rels, strict=True):
        if regular_files.is_outside(rel) or regular_files.link_on_the_way(root, rel):
            raise ValueError(f"{rel}: {objects.REFUSED[regular_files.LINK]}")
        if rel in changed:
            raise ValueError(f"{rel} holds an edit no commit holds: commit it or drop it first, so your agreement covers what you read")
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
    message = [f"{', '.join(named)}: agreed", f"Agreed-by: {who}"]
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
