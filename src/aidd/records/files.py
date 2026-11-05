"""Records as files: one immutable JSON file for each thing that happened, in the clone's shared git folder.

A record is `{id, type, at, by, written_with?, subject?, data}` (schemas/records.schema.json, `$defs/record`), and
schemas/records.json gives each type's `data` shape. The files live in `.git/aidd/records/<yyyy>/<mm>/<id>.json`: never in the working
tree or a PR's diff, shared by every worktree of the clone, and untouched by a squash or a rebase. A record is the
agent's account, kept as history: nothing reads one to stop a step.

Writing checks the record against its type, so a record is well formed when it is written. Reading keeps every record
it can parse, of a type this aidd knows or not, so an older aidd reads a newer one's records.
"""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import secrets
from collections.abc import Iterator
from pathlib import Path

from aidd.kernel import documents, git, json_schema, resources, secret_patterns


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


def record_problems(record: dict, *, any_type: bool = False) -> list[str]:
    """What is wrong with `record` for writing or sharing: its envelope, its type's `data` schema, the picks against the
    options, its size, and any value that looks like a secret. [] when it is right. With `any_type`, a record of a type
    this aidd does not know passes on its envelope and its values, as a newer aidd's record does.

    The shape and the secret check come first, and each stops the rest: the schema's errors quote the values they name,
    so a record whose value looks like a secret gets only REFUSED_VALUE_MESSAGE, fixed text that quotes nothing. Every message is
    one line, made safe for a terminal and capped, since a pulled record is another's text."""
    shape = record_shape_problem(record)
    if shape:
        return [shape]
    if _holds_secret(record):
        return [REFUSED_VALUE_MESSAGE]
    return [documents.one_line(e, 300) for e in _value_problems(record, any_type=any_type)]


def _value_problems(record: dict, *, any_type: bool) -> list[str]:
    """record_problems past the shape and the secret check: the envelope, the type, its data, and the picks."""
    errors = json_schema.validate(record, "records.schema.json#/$defs/record")
    known = record_types()
    if not errors and record["type"] not in known and not any_type:
        errors.append(f"$.type: {record['type']!r} is not a record type aidd knows ({', '.join(sorted(known))})")
    if errors or record["type"] not in known:
        return errors
    data = record["data"]
    errors = [e.replace("$", "$.data", 1) for e in json_schema.validate(data, f"records.json#/types/{record['type']}/data")]
    if errors:
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
    record: dict = {"id": _new_id(now), "type": record_type, "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "by": by, "written_with": written_with}
    if subject:
        record["subject"] = subject
    record["data"] = data
    errors = record_problems(record)
    if errors:
        raise RecordError("the record was not written:\n  " + "\n  ".join(errors))
    path = records_dir(cwd) / now.strftime("%Y") / now.strftime("%m") / f"{record['id']}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as f:  # "x" fails if the name exists: a record is never overwritten
            f.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
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


def read_records(cwd: str = ".", *, record_type: str | None = None, subject: str | None = None) -> tuple[list[dict], list[str]]:
    """The records, newest first, of `record_type` and for `subject` when given; and the files that do not read as a
    record, which are kept and skipped."""
    folder = records_dir(cwd)
    found: list[dict] = []
    unreadable: list[str] = []
    kept: dict[str, tuple[Path, dict]] = {}
    for path in sorted(folder.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json"), reverse=True):
        try:
            record = None if path.is_symlink() else parse_record(path.read_bytes())
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
    for _path, record in kept.values():
        if (record_type is None or record["type"] == record_type) and (subject is None or record.get("subject") == subject):
            found.append(record)
    return found, unreadable
