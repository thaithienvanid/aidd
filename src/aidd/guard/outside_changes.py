"""What changed outside the agent's session since a person's last decision, shown with their next one.

A program that writes by itself, such as a Python script, a build tool, or a package manager, is out of the shell
check's reach, so it could change the always-on rules' files and refs on this machine. aidd never pauses ordinary work
for it. Instead, when a person's decision is recorded (typed: `approve SPEC-1`, `land it`, `merge it`, `publish`,
`approve all`, DECISION_KINDS; or answered in a dialog, or run at their own terminal), aidd keeps the watched state, what
those rules stand on (watched_state.py): the decision records, the base branch and each remote's copy of it, HEAD's branch, the
config's control keys, the git hooks and every git config key that names a program, the guard's wiring, and this
user's launcher with its program. It keeps the decision's words with it.

What changed since the last decision is never confirmed on its own: it is part of the decision the person makes anyway.
A dialog lists it before they answer, and the line that says what aidd recorded lists it after (`counted_note`): it
counts as theirs, and each change names how to put it back. How far a decision vouches for the person decides what
it takes in (`level`). A looser config or parent, decision records rewritten, and signed ones aidd cannot verify,
need a dialog bound to the hash of what it showed, or the person's own terminal; until then the guard keeps the
stricter rules. A change
that could stop the guard itself (a git config key that names a program, a git hook, the guard's wiring, the
launcher) needs the person's own terminal or aidd's MCP dialog, which this process vouches for: never a dialog whose
answer counts only because the guard denies an agent's `--confirmed`. Typed words take in neither. The commands that act on a decision (`aidd land`, `aidd approve spec|merge|all`, `aidd publish`: CHECKED, and so
the autopilot steps that run them) compare the watched state first (`check_decision`). Run by an agent, they stop when
something changed after the person's decision, and name it with the decision's own words: say them again to go on, or
answer the dialog for a change that weakens the guard. A config edit of only `mission`, `goal`, or `locale` is no change
here (gate.config_controls_changed). A watched state aidd cannot read stops the command where the project fails closed
(repo_config.fails_closed), and lets it go elsewhere.

It shows a change and never prevents one: a program that also rewrites aidd's state in the git directory can hide its
change. The gate in CI, on a clean checkout, and signed approvals are the controls.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import NamedTuple

from aidd import config
from aidd.guard import decision_snapshot
from aidd.guard.watched_state import ABSENT, place, watched_state
from aidd.kernel import documents, git

# The typed decisions that keep the watched state (workitems.parse_typed's kinds), and the commands that check it.
DECISION_KINDS = frozenset({"spec", "merge", "land", "merge-it", "publish", "all"})
CHECKED = frozenset({"land", "approve", "publish"})
MAX_SHOWN = 5
# With a decision: what changed since the last one, which counts as the person's, and how to put each back.
COUNTED = "Since your last decision, these changed outside the session and count as yours: {changes}. If one wasn't you, put it back with {restore}."
# How far a decision vouches for the person, and so what it takes in: an ordinary change (PLAIN); a looser config or
# decision records aidd cannot vouch for (LOOSER: a dialog bound to its hash, or the person's terminal); a change that
# could stop the guard itself (GUARD: the person's terminal, or aidd's MCP dialog).
PLAIN, LOOSER, GUARD = 0, 1, 2
# With a decision that does not take it in: a change that weakens the guard, which waits for a dialog.
HELD = (
    "{since}, this changed outside the session and weakens the guard, so it waits for a dialog: {changes}. Until you answer "
    "it, the guard keeps the stricter rules. {dialog} Or put it back with {restore}."
)
HELD_GUARD = (
    "{since}, this changed outside the session and could stop the guard itself, so only aidd's own dialog or your own "
    "terminal takes it in: {changes}. {dialog} Or put it back with {restore}."
)
# After a decision: what changed since, which stops an agent's command until the person says their words again.
STOPPED = "Since you said `{said}`, this changed outside the session: {changes}. Say `{said}` again to go on with it, or put it back with {restore}."
STOPPED_UNSAID = (
    "Since your last decision, this changed outside the session: {changes}. Say your decision again to go on with it (such as "
    "`land it`), or put it back with {restore}."
)
# What a dialog showed is no longer what changed: its answer takes in nothing it did not show.
MOVED = "what changed outside the session is no longer what the dialog showed, so nothing was done: ask again for a fresh dialog"
UNREAD = "aidd could not read what the always-on rules stand on ({what}), and {fails} requires it. {next}"


def config_text(top: str) -> str | None:
    """The config's text, kept to tell a control key's change from a preference's; None when there is none to read."""
    try:
        return (Path(top) / config.CONFIG_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _save(path: Path, record: dict) -> None:
    """Write the record whole, owner-only, never through a link: a reader sees the old one or the new one."""
    folder = path.parent
    if folder.is_symlink() or folder.parent.is_symlink():
        raise OSError(f"{folder} is a symbolic link")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = folder / f".{path.name}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, sort_keys=True)
    os.replace(tmp, path)


def _top(cwd: str) -> str:
    top = git.toplevel(cwd)
    if not top:
        raise ValueError("not a git repository: aidd keeps the watched state of a person's last decision in the git directory")
    return top


def keep_state_at_decision(cwd: str = ".", said: str = "", *, held_too: bool = True) -> None:
    """Keep the watched state as it is now, at a person's decision, with the decision's words (`said`). Without `held_too`, a
    change that weakens the guard keeps its old value, so it stays held. Never raises: a watched state not kept only means the
    next check has nothing to compare with."""
    with contextlib.suppress(OSError, ValueError, git.GitError):
        top, snap = snapshot(cwd)
        if not held_too:
            snap = _keep_held(top, snap, PLAIN)
        words = said_words(said)
        _save(decision_snapshot.record_path(top), snap | ({"said": words} if words else {}))


def _keep_held(top: str, snap: dict, takes: int, skip: frozenset[str] = frozenset()) -> dict:
    """`snap` with each change above what the decision takes in (`takes`) put back to the value the last decision kept,
    so it stays held; `skip` names the command's own writes."""
    kept, found = _found(top)
    out = {"watched": dict(snap["watched"]), "config_text": snap["config_text"], "parent_texts": dict(snap["parent_texts"])}
    for item, was, _ in found:
        if item in skip or level(item, kept, top) <= takes:
            continue
        kind, _, name = item.partition(":")
        if item == f"file:{config.CONFIG_PATH}":
            out["config_text"] = kept.get("config_text")
        elif kind == "parent":
            out["parent_texts"][name] = (kept.get("parent_texts") or {}).get(name)
        elif was == ABSENT:
            out["watched"].pop(item, None)
        else:
            out["watched"][item] = kept["watched"].get(item, was)
    return out


def snapshot(cwd: str = ".") -> tuple[str, dict]:
    """(the worktree's top, what a decision keeps as it reads now): the watched state, the config's text, and each local parent's
    text. OSError, ValueError, or git.GitError when it cannot be read."""
    with git.system_only():
        top = _top(cwd)
        return top, {"watched": watched_state(place(top))[0], "config_text": config_text(top), "parent_texts": decision_snapshot.parent_texts(top)}


def _kept(top: str) -> dict | None:
    """What the person's last decision kept, or None when there is none. ValueError when it is not what aidd wrote."""
    kept = decision_snapshot.read_record(top)  # today's names, from where aidd kept it before 1.0 too
    if kept is None:
        return None
    if not isinstance(kept.get("watched"), dict):
        raise ValueError("the watched state of the last decision is not one aidd wrote")
    return kept


def _found(top: str) -> tuple[dict, list[tuple[str, str, str]]]:
    """(what the last decision kept, each change since as (item, was, now)); ({}, []) with no decision to compare."""
    from aidd import gate

    with git.system_only():
        kept = _kept(top)
        if kept is None:
            return {}, []
        now = watched_state(place(top))[0]
    was = kept["watched"]
    found = [(k, str(was.get(k, ABSENT)), str(now.get(k, ABSENT))) for k in sorted(set(was) | set(now)) if was.get(k, ABSENT) != now.get(k, ABSENT)]
    controls = gate.config_controls_changed(kept.get("config_text"), config_text(top))
    if controls:
        found.insert(0, (f"file:{config.CONFIG_PATH}", ", ".join(controls), "changed"))
    # Each local parent the config extends, the same way: a parent's control keys count, its preferences do not.
    before = decision_snapshot.recorded_parent_texts(top)
    for rel in sorted(set(before) | set(decision_snapshot.parent_texts(top))):
        if parent := gate.config_controls_changed(before.get(rel), decision_snapshot.read_text(top, rel)):
            found.insert(1, (f"parent:{rel}", ", ".join(parent), "changed"))
    return kept, found


def changes(cwd: str = ".") -> list[tuple[str, str, str]]:
    """Each change since the person's last decision, as (item, was, now); [] when there is no decision to compare with.
    The config counts only when a control key changed. OSError, ValueError, or git.GitError when it cannot be read."""
    return _found(_top(cwd))[1]


def weakens(item: str, kept: dict, top: str) -> bool:
    """Whether a change weakens the guard, so typed words never take it in (`level` above PLAIN)."""
    return level(item, kept, top) > PLAIN


def level(item: str, kept: dict, top: str) -> int:
    """What it takes to take a change in. GUARD for one that could stop the guard running or replace it: a git config key
    that names a program, a git hook, the guard's wiring, or the launcher and its program. LOOSER for a config or a
    parent that loosens a control (repo_config.looser_text, the rule the stricter config follows), and for decision
    records aidd cannot vouch for (`_records_level`), or for the ref that held them before 1.0. PLAIN for HEAD's branch and every other ref (a pull, a branch
    switch, a land), which never decide what the guard allows."""
    from aidd import workitems
    from aidd.guard import repo_config

    kind, _, name = item.partition(":")
    if item == f"ref:{workitems.DECISIONS_REF}":
        return _records_level(str((kept.get("watched") or {}).get(item, ABSENT)), top, kept)
    if kind in ("head", "ref"):
        return PLAIN
    if item == f"file:{config.CONFIG_PATH}":
        return LOOSER if repo_config.looser_text(kept.get("config_text"), config_text(top)) else PLAIN
    if kind == "parent":
        loose = repo_config.looser_text((kept.get("parent_texts") or {}).get(name), decision_snapshot.read_text(top, name))
        return LOOSER if loose else PLAIN
    return GUARD


def _records_level(was: str, top: str, kept: dict) -> int:
    """A change to the decision records that no command of this worktree's decisions wrote, such as a person's decision
    in another worktree (each worktree keeps its own watched state, and the ref is shared). Rewritten or shrunk, it is LOOSER in
    every mode, so only a dialog or the person's terminal takes it in. Grown, it is PLAIN where approvals are unsigned:
    an unsigned local approval is no proof against a local writer, as SECURITY.md says, and signing is that control.
    Where approvals must be signed (`gates.local_approvals: signed`), it is PLAIN only when every new record is a listed
    signer's that counts, which a program cannot forge without the key, and LOOSER otherwise. The signers and the
    Approvers are those of what the last decision kept (`kept`: its config and its base branch), never the live ones,
    so a signer added outside the session never vouches for a record; a config or a base branch that moved since is
    LOOSER."""
    from aidd import workitems
    from aidd.guard import repo_config

    new = git.run(["rev-parse", "-q", "--verify", workitems.DECISIONS_REF], top, check=False).strip()
    if not new:
        return LOOSER
    if was != ABSENT and not git.ok(["merge-base", "--is-ancestor", was, new], top):
        return LOOSER
    # The kept config, resolved as the gate resolves it, with the org preset as its root parent. It fails closed: a
    # config that does not read, or a parent it had to skip (UNREAD_PARENT, such as a preset that sets signing), never
    # reads as unsigned.
    text = kept.get("config_text")
    if not isinstance(text, str):
        return LOOSER
    try:
        parents = kept.get("parent_texts") or {}
        cfg = config.load_text(text, read=lambda rel: parents.get(rel), fetch=repo_config.offline_fetch, skip_unread=True, root_preset=config.org_preset_text())
    except Exception:  # noqa: BLE001  # a config the last decision kept that does not read vouches for nothing
        return LOOSER
    if any(config.UNREAD_PARENT in w for w in cfg.warnings):
        return LOOSER
    if cfg.gates.get("local_approvals") != "signed":
        return PLAIN
    base = git.default_base(top)
    key = f"ref:refs/remotes/{base}" if "/" in base else f"ref:refs/heads/{base}"
    base_was = str((kept.get("watched") or {}).get(key, ABSENT))
    base_now = git.run(["rev-parse", "-q", "--verify", key.removeprefix("ref:")], top, check=False).strip() or ABSENT
    if text != config_text(top) or base_was == ABSENT or base_was != base_now:
        return LOOSER
    approvers, signers = list(cfg.approvers), workitems.base_signers(cfg, base_was, top)
    added = git.run(["rev-list", new if was == ABSENT else f"{was}..{new}"], top, check=False).split()
    counted = {sha for sha, _, _, _, counts in workitems.read_decision_records(top, approvers, True, signers, limit=len(added) + 50) if counts}
    return PLAIN if added and all(sha in counted for sha in added) else LOOSER


class Checked(NamedTuple):
    """What a check read before a decision, or a command that acts on one, did its work. `snapshot` is what the
    always-on rules stood on then, and `outside_hash` its hash. For a person's decision (`person`), it also holds the
    decision's words (`said`), what changed since their last one (`note`), and how far it vouches for them (`takes`:
    PLAIN, LOOSER, or GUARD, the most it takes in)."""

    snapshot: dict
    outside_hash: str
    person: bool = False
    said: str = ""
    note: str | None = None
    takes: int = PLAIN
    command: str = ""
    args: object = None

    @property
    def held_too(self) -> bool:
        """Whether it takes in a change that weakens the guard."""
        return self.takes > PLAIN


class Answer(NamedTuple):
    """A person's confirmed answer (`--confirmed`, from a place app.py checked): the hash of what its dialog showed
    (`seen`, None for typed words), and whether this process vouches for the person who gave it (`vouched`: aidd's
    MCP server asked them itself)."""

    seen: str | None = None
    vouched: bool = False


def check_decision(command: str | None, args: object, cwd: str = ".", confirmed: Answer | None = None) -> Checked | None:
    """Before `aidd land`, `aidd approve`, or `aidd publish` acts (CHECKED), read from the parsed command line `args`.

    A person's decision, by `confirmed` words (typed, or a dialog's answer) or at a terminal no agent started, says what
    changed since their last one, which counts as theirs. How much it takes in (`level`): the person's own terminal
    takes in everything; a dialog whose `seen` is the hash of exactly what it showed takes in a looser config, and a
    change that could stop the guard only when this process `vouched` for the dialog; typed words take in only ordinary
    changes. A dialog that showed something else stops it (RuntimeError). Anywhere else, what changed since the
    person's last decision stops the command (RuntimeError, with each change and the words that go on). Once the command
    is done, `record_checked` keeps what this check read. None for `--show`, which records nothing; `approve stop`,
    which only takes a standing approval back, never stops, and keeps its own record as its own."""
    from aidd import platforms

    if command not in CHECKED or getattr(args, "show", False) is True:
        return None
    outside = shown_outside(cwd)
    shown = outside["outside_changes"]
    snap, outside_hash = outside.get("_snapshot") or {}, str(outside.get("outside_hash") or "")
    if getattr(args, "what", None) == "stop":
        # It only takes a standing approval back, so it never stops; its own record is still its own (record_checked).
        return Checked(snap, outside_hash, command="stop", args=args)
    said = decision_words(command, args)
    if confirmed is None:
        try:
            platforms.check_terminal("A decision")
        except platforms.NotAPerson:
            if shown:
                top = git.toplevel(cwd)
                raise RuntimeError(stop_message(shown, decision_snapshot.recorded_said(top) if top else "")) from None
            return Checked(snap, outside_hash, command=str(command), args=args)
        return Checked(snap, outside_hash, True, said, counted_note(shown, said) if shown else None, GUARD, str(command), args)
    if confirmed.seen and confirmed.seen != outside_hash:
        raise RuntimeError(MOVED)
    takes = (GUARD if confirmed.vouched else LOOSER) if confirmed.seen else PLAIN
    return Checked(snap, outside_hash, True, said, counted_note(shown, said, takes=takes) if shown else None, takes, str(command), args)


def check_typed(cwd: str, typed: str) -> Checked:
    """Before aidd's prompt hook records a typed decision: what it reads, so `record_checked` keeps it afterwards with
    only the decision's own record moved on. Typed words take in only ordinary changes (PLAIN). RuntimeError where the
    watched state cannot be read and the project fails closed."""
    outside = shown_outside(cwd)
    shown, said = outside["outside_changes"], said_words(typed)
    return Checked(
        outside.get("_snapshot") or {},
        str(outside.get("outside_hash") or ""),
        True,
        said,
        counted_note(shown, said, takes=PLAIN) if shown else None,
        PLAIN,
        "typed",
    )


def record_checked(checked: Checked, cwd: str = ".") -> None:
    """After a decision or a command that acts on one did its work: keep what the check read, with only the command's
    own writes moved on (`_own_writes`: the decision records, the base branch a land moved and the branch it left
    checked out, the remote branch a publish pushed). Anything else that changed while it ran keeps the value the check
    read, so the next decision shows it. A person's decision keeps its words, and takes in only what it vouches for
    (`takes`). A run that is not a person's records nothing when something besides its own writes changed, or when
    there is no decision to compare with; only a typed decision, or one that listed changes, starts one. Never raises."""
    if not checked.snapshot:
        return
    with contextlib.suppress(OSError, ValueError, git.GitError):
        top = _top(cwd)
        kept = _kept(top)
        if kept is None and not (checked.person and (checked.note or checked.command == "typed")):
            return
        before, now = checked.snapshot["watched"], snapshot(top)[1]["watched"]
        moved = {k for k in set(before) | set(now) if before.get(k, ABSENT) != now.get(k, ABSENT)}
        own = frozenset(moved & _own_writes(checked, before, now, top))
        if not checked.person and moved - own:
            return
        last = (kept or {}).get("watched") or {}
        # The command's own write moves on only where nothing changed before it: an outside change to the same ref (a
        # forged decision record) stays held, with the write on top of it, until a decision that vouches for it.
        clean = {k for k in own if before.get(k, ABSENT) == last.get(k, ABSENT)}
        if not checked.person:
            # A run that is not a person's decision takes in nothing: the last decision's record, with its own writes.
            mine = {k: v for k, v in last.items() if k not in clean} | {k: now[k] for k in clean if k in now}
            snap = {**(kept or {}), "watched": mine}
            snap = {k: snap[k] for k in ("watched", "config_text", "parent_texts") if k in snap}
        else:
            mine = {k: v for k, v in before.items() if k not in own} | {k: now[k] for k in own if k in now}
            snap = {**checked.snapshot, "watched": mine}
            if checked.takes < GUARD:
                snap = _keep_held(top, snap, checked.takes, frozenset(clean))
        said = said_words(checked.said if checked.person else str((kept or {}).get("said") or ""))
        _save(decision_snapshot.record_path(top), snap | ({"said": said} if said else {}))


def _own_writes(checked: Checked, before: dict, now: dict, top: str) -> set[str]:
    """The watched state's entries the command itself writes, each only where its new value is one it would write: the
    decision records grew from what the check read by exactly the records this process wrote; a land's base branch
    grew, and HEAD names it; a publish's remote-tracking branch names the head it pushed."""
    from aidd import workitems

    def grew(key: str) -> bool:
        old, new = before.get(key, ABSENT), now.get(key, ABSENT)
        return new != ABSENT and (old == ABSENT or git.ok(["merge-base", "--is-ancestor", old, new], top))

    def wrote(key: str) -> bool:
        # The decision records are the command's own only when every commit since the check is one this process wrote:
        # a record a program appended while it ran is judged as any outside change is (`level`).
        if not grew(key):
            return False
        old, new = before.get(key, ABSENT), now.get(key, ABSENT)
        added = git.run(["rev-list", new if old == ABSENT else f"{old}..{new}"], top, check=False).split()
        return bool(added) and set(added) <= workitems.records_written()

    own = {key for key in (f"ref:{workitems.DECISIONS_REF}",) if wrote(key)}
    if checked.command == "land":
        base = getattr(checked.args, "base", None) or git.default_base(top).removeprefix("origin/")
        if grew(f"ref:refs/heads/{base}"):
            own.add(f"ref:refs/heads/{base}")
            if now.get("head") == f"refs/heads/{base}":
                own.add("head")
    if checked.command == "publish":
        head = git.run(["rev-parse", "HEAD"], top, check=False).strip()
        own |= {k for k, v in now.items() if k.startswith("ref:refs/remotes/") and head and v == head}
    return own


def changes_since_decision(cwd: str = ".") -> list[dict]:
    """Each change since the person's last decision, as {"what", "restore", "held"}: [] when none, or no decision to
    compare with. `held` marks one that weakens the guard. A watched state aidd cannot read is RuntimeError where the project
    fails closed, and [] elsewhere."""
    return shown_outside(cwd)["outside_changes"]


def shown_outside(cwd: str = ".") -> dict:
    """What a dialog shows before the person answers: `outside_changes`, and `outside_hash`, the hash of what the
    always-on rules stand on now, which their answer names, so it takes in exactly what they saw and a change made after
    stops it. `_snapshot` is what the hash names, for `check_decision`; a preview leaves it out."""
    from aidd.guard import repo_config, verdicts

    try:
        top = _top(cwd)
        kept, found = _found(top)
        levels = [level(c[0], kept, top) for c in found]
        shown = [{"what": change_line(*c), "restore": _restore(*c), "held": n > PLAIN, "guard": n == GUARD} for c, n in zip(found, levels, strict=True)]
        _, snap = snapshot(top)
        return {"outside_changes": shown, "outside_hash": _hash_of(snap), "_snapshot": snap}
    except (OSError, ValueError, git.GitError) as exc:
        top = git.toplevel(cwd)
        if top and repo_config.fails_closed(top):
            raise RuntimeError(UNREAD.format(what=type(exc).__name__, fails=verdicts.FAILS_CLOSED, next=verdicts.GUARD_BROKE)) from None
        return {"outside_changes": []}


def _hash_of(snap: dict) -> str:
    """The hash a dialog's answer names: the whole snapshot, the decision records included, so anything that moves
    before the answer stops it. A dialog that approves several Specs names it on its first record only, since each
    record moves the decision records, and the first one's check keeps that write as its own."""
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def decision_words(command: str | None, args: object) -> str:
    """The words a person types at the agent's prompt for the decision `args` records, kept with the watched state."""
    what = getattr(args, "what", None)
    if command == "land":
        return "land it"
    if command == "publish":
        return "publish"
    if what == "merge":
        return "merge it" if getattr(args, "auto_merge", False) else "approve merge"
    if what == "all":
        scope = (" and publish" if getattr(args, "and_publish", False) else "") + (" but major" if getattr(args, "but_major", False) else "")
        return f"approve all{scope}"
    named = [str(x) for x in [getattr(args, "spec", None), *(getattr(args, "more", None) or [])] if x]
    return " ".join(["approve", *(Path(x).stem for x in named)])


def said_words(said: str) -> str:
    """A decision's words as aidd says them back: read as aidd reads typed words (workitems.parse_typed), and rebuilt from
    its kind and its checked ids, so no other text ever reaches a message. The record keeping them is a file a program
    could write. "" for anything that is not a decision land, approve, or publish acts on."""
    from aidd import workitems

    kind, rest = workitems.parse_typed(str(said or "")[:300]) or ("", [])
    words = {
        "land": "land it",
        "publish": "publish",
        "merge-it": "merge it",
        "merge": "approve merge",
        "all": "approve all" + (" and publish" if "and-publish" in rest else "") + (" but major" if "but-major" in rest else ""),
        "spec": " ".join(["approve", *rest]),
    }.get(kind, "")
    return documents.one_line(words, 120)


def _level(c: dict) -> int:
    return GUARD if c.get("guard") else LOOSER if c.get("held") else PLAIN


def _listed(shown: list[dict]) -> tuple[str, str]:
    """The changes in a few words each, at most MAX_SHOWN, and how to put each back."""
    first = shown[:MAX_SHOWN]
    what = "; ".join(c["what"] for c in first) + (f", and {len(shown) - MAX_SHOWN} more" if len(shown) > MAX_SHOWN else "")
    return what, "; ".join(dict.fromkeys(c["restore"] for c in first))


def dialog_step(said: str, vouched_only: bool = False) -> str:
    """Where the person answers a dialog for the decision `said`, read as aidd reads typed words (workitems.parse_typed):
    the `/aidd` verb, aidd's MCP dialog, and their own terminal; with `vouched_only`, only the last two."""
    from aidd import workitems

    kind, rest = workitems.parse_typed(said) or ("", [])
    ids = " ".join(rest) if kind == "spec" else ""
    verb, tool, command = {
        "land": ("/aidd land", "land", "aidd land"),
        "publish": ("", "publish", "aidd publish"),
        "merge-it": ("/aidd merge", "approve_merge", "aidd approve merge"),
        "merge": ("/aidd approve merge", "approve_merge", "aidd approve merge"),
        "all": ("/aidd approve all", "approve_all", "aidd approve all"),
        "spec": (f"/aidd approve {ids}".rstrip(), "approve_spec", f"aidd approve spec {ids}".rstrip()),
    }.get(kind, ("", "", ""))
    ways = [*([f"type `{verb}` (aidd-mods in Claude Code, or OpenCode)"] if verb and not vouched_only else [])]
    ways += [f"ask the agent for aidd's `{tool}` dialog"] if tool else []
    ways += [f"run `{command}` at your own terminal"] if command else ["answer the dialog `/aidd` lists for it"]
    return "To answer it: " + ", ".join(ways[:-1]) + (", or " if len(ways) > 1 else "") + ways[-1] + "."


def counted_note(shown: list[dict], said: str = "", *, takes: int = GUARD) -> str:
    """What a recorded decision says when something changed since the last one: what it takes in (`takes`) counts as the
    person's; what weakens the guard beyond it waits for a dialog (HELD), or for aidd's own dialog or the person's
    terminal (HELD_GUARD)."""
    return _said_back(shown, "Since your last decision", said, takes, COUNTED)


def stop_message(shown: list[dict], said: str = "") -> str:
    """What stops an agent's command when something changed since the person's decision: each change, and the words
    that go on with it, which are the decision's own, read back through `said_words`; a change that weakens the guard
    waits for a dialog."""
    words = said_words(said)
    since = f"Since you said `{words}`" if words else "Since your last decision"
    return _said_back(shown, since, words, PLAIN, STOPPED if words else STOPPED_UNSAID)


def _said_back(shown: list[dict], since: str, said: str, takes: int, plain: str) -> str:
    taken = [c for c in shown if _level(c) <= takes]
    looser = [c for c in shown if _level(c) == LOOSER and c not in taken]
    guard = [c for c in shown if _level(c) == GUARD and c not in taken]
    lines = []
    for group, text in ((taken, plain), (looser, HELD), (guard, HELD_GUARD)):
        if group:
            what, restore = _listed(group)
            dialog = dialog_step(said, vouched_only=text is HELD_GUARD)
            lines.append(text.format(since=since, said=said, changes=what, restore=restore, dialog=dialog))
    return " ".join(lines)


def change_line(item: str, was: str, now: str) -> str:
    """One change in a few words, never a value longer than a line: a ref's or a key's name is a program's words, so it
    is shown as one plain line (documents.one_line)."""
    return documents.one_line(_change_line(item, was, now), 300)


def _change_line(item: str, was: str, now: str) -> str:
    kind, _, name = item.partition(":")
    verb = "was removed" if now == ABSENT else "was added" if was == ABSENT else "changed"
    if item == f"file:{config.CONFIG_PATH}":
        return f"{name} changed its control keys ({was})"
    if kind == "parent":
        return f"{name}, which the config extends, changed its control keys ({was})"
    if kind == "file":
        return f"{name} {verb}"
    if kind == "head":
        return f"HEAD names {now}, not {was}"
    if kind == "ref":
        return f"{name} {verb}" + (f" (from {was[:12]} to {now[:12]})" if verb == "changed" else "")
    if kind == "config":
        return f"git config {name} {verb}"
    if kind == "launcher":
        return f"your aidd launcher {name} {verb}"
    if kind == "launcher-target":
        return f"the program your aidd launcher runs, {name}, {verb}"
    return f"the git hook {name} {verb}"


def _restore(item: str, was: str, now: str) -> str:
    return documents.one_line(_restore_step(item, was, now), 300)


def _restore_step(item: str, was: str, now: str) -> str:
    kind, _, name = item.partition(":")
    if kind == "parent":
        return f"`git checkout -- {name}`"
    if kind == "file":
        return f"`git checkout -- {name}`" if was != ABSENT else f"remove {name}"
    if kind == "head":
        return f"`git switch {was.removeprefix('refs/heads/')}`" if was.startswith("refs/heads/") else f"`git switch --detach {was}`"
    if kind == "ref":
        return f"`git update-ref {name} {was}`" if was != ABSENT else f"`git update-ref -d {name}`"
    if kind == "config":
        return f"`git config --unset-all {name}`" if was == ABSENT else f"`git config {name} <its old value>`"
    if kind in ("launcher", "launcher-target"):
        return "`aidd init` in a terminal no agent started, which writes the launcher again"
    return f"remove the hook {name}, or put back the one that was there"
