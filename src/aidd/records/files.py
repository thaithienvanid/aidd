"""Records as files: one immutable JSON file for each thing that happened, in the clone's shared git folder.

A record is `{id, type, recorded_at, by, written_with?, subject?, data}` (schemas/records.schema.json, `$defs/record`), and
schemas/records.json gives each type's `data` shape. The files live in `.git/aidd/records/<yyyy>/<mm>/<id>.json`: never in the working
tree or a PR's diff, shared by every worktree of the clone, and untouched by a squash or a rebase. A record is the
agent's account, kept as history, never a person's yes and never evidence. Only the delegation reads records to decide,
and only its own two types: a delegate's defer, which only narrows, and its accept, which points at a commit the check
recomputes. A file that does not read as a record defers that check. A `decision` is never read as an approval.

Two readers, two rules. Writing checks the record against its type, so a record is well formed when it is written, and a
retired value is never written again. A reader of history is lenient: it keeps every record it can parse, of a type this aidd
knows or not and with a field it does not know, reads a retired name as today's (`record` rows of schemas/retired-names.json),
and names the records it reads only in part (`partly_read`). So an older aidd reads a newer one's records, and a record
reads the same whenever it was written. The delegation counts an accept only from a record that is today's shape in full,
as it was written (`read_records(as_written=True)`), and it counts a defer from any record, since a defer only narrows.
"""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aidd.kernel import documents, git, json_schema, regular_files, resources, retired_names, secret_patterns, timestamps


class RecordError(ValueError):
    """A record that cannot be written: what is wrong with it, and what to fix."""


# What writes the records now: `cli`, `aidd records add`, unless the MCP server's `record` tool runs it inside
# `written_with_mcp`. A context variable, never a flag, so no command line can claim either.
_WRITTEN_WITH: contextvars.ContextVar[str] = contextvars.ContextVar("written_with", default="cli")


@contextlib.contextmanager
def written_with_mcp() -> Iterator[None]:
    """Each record written inside is the MCP `record` tool's: it says `written_with: mcp`, and a decision's `answer.by`
    is never filled from the git name, since the tool runs with no prompt and the name would read as the person's."""
    token = _WRITTEN_WITH.set("mcp")
    try:
        yield
    finally:
        _WRITTEN_WITH.reset(token)


# The record types aidd itself writes under a standing delegation: `aidd delegate check` and the delegate's MCP
# `delegate_answer` tool, inside `written_by_delegation`. `aidd records add` and the MCP `record` tool refuse them, so an
# agent cannot write a delegate's answer in its own words.
DELEGATION_TYPES = ("delegate_check", "delegate_answer")
_BY_DELEGATION: contextvars.ContextVar[bool] = contextvars.ContextVar("by_delegation", default=False)


@contextlib.contextmanager
def written_by_delegation() -> Iterator[None]:
    """Each record written inside may be a delegation type: the delegation package's own check and answer."""
    token = _BY_DELEGATION.set(True)
    try:
        yield
    finally:
        _BY_DELEGATION.reset(token)


def agent_record_types() -> list[str]:
    """The record types an agent writes with `aidd records add` or the MCP `record` tool: all but the delegation's."""
    return sorted(t for t in record_types() if t not in DELEGATION_TYPES)


def record_types() -> dict[str, dict]:
    """Each record type aidd knows, by name: its description and its `data` schema."""
    return resources.load_json("records.json")["types"]


def records_dir(cwd: str = ".") -> Path:
    """`.git/aidd/records` of the clone `cwd` is in: the common git folder, so every worktree shares it."""
    return git.aidd_dir(cwd) / "records"


def git_folder(cwd: str = ".") -> Path:
    """The common git folder the records lie in: every read and write of them stays inside it, through no link."""
    return git.aidd_dir(cwd).parent


def record_bytes(root: Path, path: Path) -> bytes | None:
    """A record file's bytes, read as a regular file inside the git folder `root` (`git_folder`), never through a link
    and never from a pipe; None when aidd refuses it or it is past MAX_RECORD_BYTES."""
    raw, _ = regular_files.named_file_bytes(root, Path(os.path.relpath(path, root)).as_posix(), MAX_RECORD_BYTES)
    return raw


def _new_id(now: dt.datetime) -> str:
    """The UTC time to the millisecond, then 8 random hex characters, so the names sort by time."""
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z-" + secrets.token_hex(4)


def _strings(value: object) -> list[str]:
    """Every string in `value`: each key of an object, each value, and each `key: value` pair, so a credential split
    across a key and its value, such as `{"password": "..."}`, is read as one. A key pairs with each string in a list
    under it too, such as `{"password": ["..."]}`. Walked without recursion, since `record_shape_problem` bounds the
    depth only after it."""
    out: list[str] = []
    stack: list[tuple[object, str | None]] = [(value, None)]
    while stack:
        node, key = stack.pop()
        if isinstance(node, str):
            out += [node] if key is None else [node, f"{key}: {node}"]
        elif isinstance(node, dict):
            for k, v in node.items():
                out.append(str(k))
                stack.append((v, str(k)))
        elif isinstance(node, list):
            stack.extend((item, key) for item in node)
    return out


# The most a record's file may hold. A record is a question and an answer, so anything larger is no record, and a
# bound keeps a crafted one from costing a read or a secret check much.
MAX_RECORD_BYTES = 64 * 1024
# The deepest a record nests: its schema reaches 4 levels, so a deeper one is no record, and a bound keeps every
# later walk inside Python's recursion limit.
MAX_RECORD_DEPTH = 16


def record_shape_problem(record: object) -> str:
    """Why `record` can't be checked as a record, or "": it nests past MAX_RECORD_DEPTH, it holds text that is no
    valid Unicode (a lone surrogate), or it is larger than MAX_RECORD_BYTES. The message never quotes the record."""
    stack = [(record, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_RECORD_DEPTH:
            return f"the record nests deeper than {MAX_RECORD_DEPTH} levels, so it is no record"
        if isinstance(node, dict):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)
    try:
        size = len(json.dumps(record, ensure_ascii=False).encode())
    except (UnicodeEncodeError, ValueError, TypeError):
        return "the record holds text that is not valid Unicode, so it is no record"
    if size > MAX_RECORD_BYTES:
        return f"the record is larger than {MAX_RECORD_BYTES // 1024} KiB: keep a question, an answer, and what it covered"
    return ""


def parse_record(raw: bytes) -> dict | None:
    """A record file's bytes as a record, or None when they are not one: too large, not JSON, nested past what Python
    reads, or without the envelope's `id`, `type`, and `data`."""
    if len(raw) > MAX_RECORD_BYTES:
        return None
    try:
        record = json.loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    ok = isinstance(record, dict) and isinstance(record.get("id"), str) and isinstance(record.get("type"), str) and isinstance(record.get("data"), dict)
    return record if ok and not record_shape_problem(record) else None


def todays_shape(record: dict) -> dict:
    """`record` with each retired name and value read as today's (the `record` rows of schemas/retired-names.json): `at` as
    `recorded_at`, and a question type `approval` as `yes_no`. A copy: the file is never rewritten."""
    return retired_names.todays_shape(record, "record", {})


def record_problems(record: dict, *, reading: bool = False) -> list[str]:
    """What is wrong with `record` for writing: its envelope, its type's `data` schema, the picks against the options, a
    retired value, its size, and any value that looks like a secret. [] when it is right. With `reading` it is what keeps a
    record from being kept and shared: the size, the secret, and the shape of what this aidd knows, with a retired name read as
    today's, and a type, a field, or an enum value this aidd does not know let through, as a newer aidd's record has.

    The shape and the secret check come first, and each stops the rest: the schema's errors quote the values they name,
    so a record whose value looks like a secret gets only REFUSED_VALUE_MESSAGE, fixed text that quotes nothing. Every message is
    one line, made safe for a terminal and capped, since a pulled record is another's text."""
    shape = record_shape_problem(record)
    if shape:
        return [shape]
    if _holds_secret(record):
        return [REFUSED_VALUE_MESSAGE]
    if reading:
        try:
            errors = _value_problems(todays_shape(record), reading=True)
        except retired_names.Refused as exc:  # an old name beside its replacement has no one reading, so the record is none
            errors = [f"$: {exc}"]
    else:
        errors = [*_value_problems(record, reading=False), *_retired_problems(record)]
    return [documents.one_line(e, 300) for e in errors]


def partly_read(found: list[dict]) -> list[str]:
    """The ids of `found`, records in today's shape (`read_records`), that this aidd reads only in part: a type or a field it does
    not know, as a newer aidd writes, or a field it needs missing. They are kept and shown, and nothing counts them."""
    return [r["id"] for r in found if _value_problems(r, reading=False)]


def _retired_problems(record: dict) -> list[str]:
    """A new record never says a retired value: a `record` row of schemas/retired-names.json with `read_as` lists the old ones."""
    out: list[str] = []
    for row in retired_names.rows("record"):
        for path in retired_names.paths_in(record, row["old"]):
            here: Any = record
            for step in path:
                here = here[step]
            if isinstance(here, str) and here in row.get("read_as", {}):
                out.append(f"$.{retired_names.shown(path)}: {here!r} was retired in {row['retired_in']}; write {row['read_as'][here]!r}")
    return out


def _value_problems(record: dict, *, reading: bool) -> list[str]:
    """The envelope, the type, its data, and the picks. With `reading`, a type, a field, or an enum value this aidd does not
    know is no problem, and the picks (a writer's check) are left out."""
    errors = json_schema.validate(record, "records.schema.json#/$defs/record", open_set=reading)
    known = record_types()
    if not errors and record["type"] not in known and not reading:
        errors.append(f"$.type: {record['type']!r} is not a record type aidd knows ({', '.join(sorted(known))})")
    if errors or record["type"] not in known:
        return errors
    data = record["data"]
    errors = [e.replace("$", "$.data", 1) for e in json_schema.validate(data, f"records.json#/types/{record['type']}/data", open_set=reading)]
    if errors or reading:
        return errors  # the picks are read only once their shape is right
    question, answer = data.get("question") or {}, data.get("answer") or {}
    picked = answer.get("picked")
    if picked is not None and not (question.get("type") == "choice" and answer.get("outcome") == "accept"):
        errors.append("$.data.answer.picked: only an accepted choice has picks")
    option_ids = [o["id"] for o in question.get("options", [])]
    if len(set(option_ids)) != len(option_ids):
        errors.append("$.data.question.options: each option needs its own id")
    if question.get("type") == "choice" and answer.get("outcome") == "accept":
        ids = set(option_ids)
        if not picked:
            errors.append("$.data.answer.picked: an accepted choice names the option ids picked")
        elif set(picked) - ids:
            errors.append(f"$.data.answer.picked: {', '.join(sorted(set(picked) - ids))} is not an option's id")
        elif len(picked) > 1 and not question.get("multiple"):
            errors.append("$.data.answer.picked: the question allows one pick, so set question.multiple to pick more")
    return errors


# The one message a record that looks like it holds a secret gets: fixed text, chosen by a yes-or-no test, so nothing
# the scan read, not even which pattern matched, reaches a terminal, a log, or a CI run.
REFUSED_VALUE_MESSAGE = (
    "a value looks like a key, a token, or a password: keep a secret's value out of a record, and name the secret instead, such as `the STRIPE_KEY variable`"
)


def _holds_secret(record: dict) -> bool:
    """Whether any string in `record`, or any `key: value` pair, has a known secret's shape (`secret_patterns`)."""
    return any(secret_patterns.secret_types(text, loose=True) for text in _strings(record))


def add_record(record_type: str, data: dict, *, by: str, subject: str | None = None, cwd: str = ".") -> tuple[dict, Path]:
    """Write one record and return it with its file. `by` is the writer, such as `agent:claude-code/claude-opus-5-5`.
    A decision's `answer.by` left out is the person's git name, except through the MCP tool (`written_with_mcp`).
    Raises RecordError with every problem found."""
    written_with = _WRITTEN_WITH.get()
    if record_type in DELEGATION_TYPES and not _BY_DELEGATION.get():
        raise RecordError(
            f"the record was not written: aidd writes `{record_type}` records itself, from `aidd delegate check` and the "
            "delegate's MCP `delegate_answer` tool. Record a person's answer as a `decision`, or an action you took as a `report`"
        )
    if record_type == "decision" and isinstance(data.get("answer"), dict) and not data["answer"].get("by"):
        if written_with == "mcp":
            raise RecordError(
                "the record was not written:\n  $.data.answer.by: name who answered. The MCP `record` tool runs with no prompt, "
                "so aidd never fills it from the git name there"
            )
        name = git.run(["config", "user.name"], cwd, check=False).strip()
        if name:
            data = {**data, "answer": {**data["answer"], "by": name}}
    now = dt.datetime.now(dt.UTC)
    record: dict = {"id": _new_id(now), "type": record_type, "recorded_at": timestamps.utc_stamp(now), "by": by, "written_with": written_with}
    if subject:
        record["subject"] = subject
    record["data"] = data
    errors = record_problems(record)
    if errors:
        raise RecordError("the record was not written:\n  " + "\n  ".join(errors))
    path = records_dir(cwd) / now.strftime("%Y") / now.strftime("%m") / f"{record['id']}.json"
    try:  # "new" fails if the name exists: a record is never overwritten, and never written through a link
        regular_files.write_safely(git_folder(cwd), path, json.dumps(record, indent=2, ensure_ascii=False) + "\n", way="new")
    except PermissionError:
        # A sandbox may keep the clone's git folder read-only, as Codex's workspace-write does in every checkout.
        raise RecordError(
            f"{path.parent} cannot be written here, as in a sandbox that keeps the git folder read-only: record it with the "
            "MCP `record` tool instead, which aidd's server writes"
        ) from None
    return record, path


def in_own_month(path: Path, record_id: str) -> bool:
    """Whether a record file sits in the `<yyyy>/<mm>` folder its id names."""
    return (path.parent.parent.name, path.parent.name) == (record_id[:4], record_id[4:6])


def read_records(cwd: str = ".", *, record_type: str | None = None, subject: str | None = None, as_written: bool = False) -> tuple[list[dict], list[str]]:
    """The records, newest first, of `record_type` and for `subject` when given, in today's names (`todays_shape`) unless
    `as_written`; and the files that do not read as a record, which are kept and skipped."""
    folder = records_dir(cwd)
    found: list[dict] = []
    unreadable: list[str] = []
    kept: dict[str, tuple[Path, dict]] = {}
    for path in sorted(folder.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json"), reverse=True):
        try:
            record = None if (raw := record_bytes(folder.parent.parent, path)) is None else parse_record(raw)
        except OSError:
            record = None
        if record is None:
            unreadable.append(str(path))
            continue
        # One id, one record: the file in its id's own year and month is the record, else the one met first, and the other
        # file is named.
        rid = record["id"]
        if rid in kept:
            other_path = kept[rid][0]
            loser = other_path if in_own_month(path, rid) and not in_own_month(other_path, rid) else path
            if loser is other_path:
                kept[rid] = (path, record)
            unreadable.append(f"{loser} (a second file with the id {rid}; the record in the other file is the one shown)")
            continue
        kept[rid] = (path, record)
    for path, record in kept.values():
        if (record_type is None or record["type"] == record_type) and (subject is None or record.get("subject") == subject):
            try:
                found.append(record if as_written else todays_shape(record))
            except retired_names.Refused as exc:  # kept and skipped, as a file that is no record: a check that counts it defers
                unreadable.append(f"{path} ({exc})")
    return found, unreadable
