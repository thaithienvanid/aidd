"""What the commit that brings a person's yes says, read from git: the file as a commit holds it, the two lines of the yes in
the commit's last paragraph, the ids those lines name, and whether the commit changes nothing in the item but the yes.

The lines are `Approved-by:` with the person and `Approves:` with each item's exact id, both keys in exactly that case. A commit
whose message holds a delegated yes's trailer holds no person's yes. `intent_checks.stamped_version` puts these reads together
into the hold of an Intent's approval and of a product scope file's.
"""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import command_names, documents, git
from aidd.workitems import delegated_yes, intents

# The two lines of a person's yes, in the last paragraph of the commit that brings it: who said yes, and the exact id of each item.
APPROVED_BY, APPROVES = "Approved-by", "Approves"
# The texts `file_at` read, by (root, commit, path); at most FILE_TEXTS_KEPT of them.
FILE_TEXTS: dict[tuple[str, str, str], str] = {}
FILE_TEXTS_KEPT = 256


def file_at(root: str, sha: str, rel: str) -> str | None:
    """The text of `rel` at commit `sha`, which is a full commit hash and never a name that can move, or None. A commit never
    changes, so a text read once is kept: a search that asks for the same version for each of several stamps starts git once for it.
    A read that fails is not kept, so a process that lives long asks git again."""
    key = (root, sha, rel)
    if key in FILE_TEXTS:
        return FILE_TEXTS[key]
    text = git.show(sha, rel, root)
    if text is not None:
        if len(FILE_TEXTS) >= FILE_TEXTS_KEPT:
            FILE_TEXTS.pop(next(iter(FILE_TEXTS)))
        FILE_TEXTS[key] = text
    return text


def raw_message(root: Path, sha: str) -> str:
    """The raw commit message decoded only as UTF-8, never through an `encoding` header, so trailers stand as literal ASCII bytes."""
    raw = git.raw_commits([sha], str(root)).get(sha, b"")
    _, sep, body = raw.partition(b"\n\n")
    return body.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n") if sep else ""


def trailer_values(message: str, key: str) -> list[str]:
    """The values of the `key` trailers in a commit message's last paragraph, the key in exactly that case; none
    when a delegated yes's trailer stands anywhere in the message, because a delegate's answer is not a person's."""
    keys = {k.lower() for k in delegated_yes.TRAILERS}
    if any(ln.partition(":")[0].strip().lower() in keys for ln in message.split("\n")):
        return []
    last = message.strip("\n").split("\n\n")[-1].split("\n")
    return [ln.partition(":")[2].strip() for ln in last if ln.partition(":")[0] == key]


def approved_ids(message: str, ident: str = "") -> set[str]:
    """The ids or paths a commit message's `Approves:` lines name, in its last paragraph, the key in exactly that case. A line names
    a list of items parted by commas, each trimmed whole. An empty part, or a part with whitespace other than exact `ident`, voids it."""
    out: set[str] = set()
    for value in trailer_values(message, APPROVES):
        parts = [p.strip() for p in value.split(",")]
        if all(p and (not any(c.isspace() for c in p) or (bool(ident) and p == ident)) for p in parts):
            out.update(parts)
    return out


def approves(message: str, ident: str) -> bool:
    """Whether a commit message's `Approves:` lines name the item `ident` exactly: `INTENT-1` is neither `INTENT-1#S1`, `INTENT-10`,
    nor `intent-1`, and the other way round."""
    return bool(ident) and ident in approved_ids(message, ident)


def changes_only_the_yes(root: Path, sha: str, place: str, then: tuple[dict, str], fields: tuple[str, ...]) -> bool:
    """Whether the commit `sha` changes nothing in the file at `place` but the yes: its first parent holds a file there with the same
    front matter apart from the yes's `fields`, and the same body. `then` is the front matter and the body the commit holds. A commit
    with no parent, or whose parent holds no such file, fails, so an amend or an edit folded into the commit of a yes holds no yes."""
    try:
        parent = git.run(["rev-parse", "-q", "--verify", f"{sha}^1^{{commit}}"], str(root), check=False).strip()
    except git.GitError:
        return False
    text = file_at(str(root), parent, place) if parent else None
    if text is None:
        return False
    try:
        before, before_body = documents.split_front_matter(text, place)
    except documents.DocumentError:
        return False
    if not isinstance(before, dict) or {k: v for k, v in before.items() if k not in fields} != {k: v for k, v in then[0].items() if k not in fields}:
        return False
    return intents.approval_body(before_body) == intents.approval_body(then[1])


def is_shallow_clone(root: Path | None) -> bool:
    """True when `root` is a shallow git clone whose history may cut off an approval hold."""
    try:
        return root is not None and git.run(["rev-parse", "--is-shallow-repository"], str(root), check=False).strip() == "true"
    except git.GitError:
        return False


def shallow_clone_sentence(raw_id: str, who: str, command: str) -> str:
    """The sentence naming `git fetch --unshallow` when a shallow clone cuts off an Intent's approval hold."""
    iid = command_names.quoted(raw_id) or "<ID>"
    line = f"`Approved-by: {documents.one_line(who, 120) or '<the person>'}` and `Approves: {iid}`"
    return f"this clone is shallow and may not hold the commit with {line}. Run `git fetch --unshallow` to read its full history, then run `{command}` again"


def no_hold_error(path: Path, root: Path | None, raw_id: str, who: str) -> str:
    """The error when an Intent's approval has no hold, naming `git fetch --unshallow` if a shallow clone cuts off its history."""
    if is_shallow_clone(root):
        return f"{path}: its approval has no hold, so aidd reads it as draft: {shallow_clone_sentence(raw_id, who, 'aidd validate')}"
    iid = command_names.quoted(raw_id) or "<ID>"
    line = f"`Approved-by: {documents.one_line(who, 120) or '<the person>'}` and `Approves: {iid}`"
    return (
        f"{path}: its approval has no hold, so aidd reads it as draft: no commit that changes only its `approval` carries "
        f"{line}. Ask the person to approve it (`intent.approve`): their yes in the chat, or `aidd approve {iid}` in their terminal"
    )
