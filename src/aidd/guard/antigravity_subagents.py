"""The agent type an Antigravity conversation was started as, read from the parent's message in its folder.

An Antigravity subagent is a conversation of its own, and its hook events carry no parent or role (agy 1.4.7, seen
live). Antigravity writes the parent's message into the subagent's own folder
(`brain/<id>/.system_generated/messages/*.json`), with the parent as `sender` and its `invoke_subagent` call, whose
arguments' `TypeName` names the agent. The guard denies agents any write there (HARNESS_RECORDS); a program the agent
runs could still write it (SECURITY.md).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import time
from pathlib import Path

# What a subagent's first message from its parent may weigh, and how many messages the guard reads, so the hook never
# reads a large or crowded folder.
PARENT_MESSAGE_BYTES = 4 * 1024 * 1024  # past any prompt agy takes, so a long delegation keeps its role
PARENT_MESSAGES_READ = 4  # the oldest few: the parent's message is the first one written into a subagent's folder
_BRAIN = re.compile(r"/\.gemini/antigravity[^/]*/brain$", re.I)
_READ_LEDGER = "read.json"  # Antigravity's record of which messages were read, rewritten on each read: never a message
_UNREADABLE = object()


def started_as(event: dict) -> str | None:
    """None for a main session: no message folder, or no message from a parent. The agent type for a subagent, and ""
    for one whose type the message does not name. Failing closed, "" too for a folder that links elsewhere, or a message
    the guard cannot read: a read-only helper, never a main session."""
    try:
        return _started_as(event)
    except Exception:  # noqa: BLE001  # a folder or message the guard cannot read (deep nesting on 3.11-3.13)
        return ""


def messages_folder(event: dict) -> tuple[Path | None, bool]:
    """The messages folder of the conversation an event names, and whether its folder links elsewhere: (None, False)
    for an event that names no conversation's own folder right under Antigravity's brain folder."""
    conversation, folder = event.get("conversationId"), event.get("artifactDirectoryPath")
    if not (isinstance(conversation, str) and conversation and isinstance(folder, str) and folder):
        return None, False
    given = os.path.normpath(os.path.expanduser(folder))
    if os.path.basename(given) != conversation or not _BRAIN.search(os.path.dirname(given).replace("\\", "/")):
        return None, False
    real = os.path.realpath(given)
    messages = Path(real, ".system_generated", "messages")
    if real != os.path.join(os.path.realpath(os.path.dirname(given)), conversation) or os.path.realpath(messages) != str(messages):
        return None, True
    return messages, False


def _started_as(event: dict) -> str | None:
    messages, linked = messages_folder(event)
    if messages is None:
        return "" if linked else None  # a folder that links out of Antigravity's records fails closed
    conversation, real = event["conversationId"], str(messages.parent.parent)
    try:
        with os.scandir(messages) as listing:
            entries = [e for e in listing if e.name.endswith(".json") and e.name != _READ_LEDGER]
    except FileNotFoundError:
        return None
    if not all(e.is_file(follow_symlinks=False) for e in entries):
        return ""  # a link, a pipe, or a folder named as a message
    found = []
    for entry in entries:
        with contextlib.suppress(FileNotFoundError):  # one removed since the listing
            found.append((entry.stat(follow_symlinks=False).st_mtime, entry.name))
    for _, name in sorted(found)[:PARENT_MESSAGES_READ]:
        data = _read_json(messages / name)
        if data is _UNREADABLE:
            return ""
        if not isinstance(data, dict) or data.get("recipient") != conversation:
            continue
        sender, source = data.get("sender"), data.get("sourceMetadata")
        tool = source.get("tool") if isinstance(source, dict) else None
        call, caller = (tool.get("toolCall"), tool.get("conversationId")) if isinstance(tool, dict) else (None, None)
        if not isinstance(call, dict) or call.get("name") != "invoke_subagent" or not isinstance(sender, str) or sender in ("", ".", "..", conversation):
            continue
        if os.path.basename(sender) != sender or caller != sender or not os.path.isdir(os.path.join(os.path.dirname(real), sender)):
            continue  # the parent is a conversation of its own, beside this one, and made the call
        arguments = call.get("argumentsJson")  # agy 1.4.7 keeps the call's arguments as a JSON string
        args = json.loads(arguments, object_pairs_hook=_unrepeated) if isinstance(arguments, str) else call.get("args")
        kind = args.get("TypeName") if isinstance(args, dict) else None
        return kind if isinstance(kind, str) else ""
    return None


def _unrepeated(pairs: list[tuple[str, object]]) -> dict:
    """An object whose keys are each spelled once, in any case: a parser that keeps another copy of `TypeName` would
    start another agent than the guard reads."""
    if len({key.casefold() for key, _ in pairs}) != len(pairs):
        raise ValueError("a key repeats")
    return dict(pairs)


def _read_json(path: Path, again: bool = True) -> object:
    """A regular file's JSON, read without following a link or waiting on a pipe, up to the cap; None for one removed
    since the listing, and _UNREADABLE for any other the guard cannot read. An empty or cut-short file is read once more
    after a moment, since Antigravity may still be writing it."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None
    except OSError:
        return _UNREADABLE
    raw = b""
    try:
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read(PARENT_MESSAGE_BYTES + 1) if stat.S_ISREG(os.fstat(fh.fileno()).st_mode) else b""
        return json.loads(raw) if len(raw) <= PARENT_MESSAGE_BYTES else _UNREADABLE
    except ValueError:
        if again and len(raw) <= PARENT_MESSAGE_BYTES:
            time.sleep(0.05)
            return _read_json(path, again=False)
        return _UNREADABLE
    except (OSError, RecursionError):
        return _UNREADABLE
