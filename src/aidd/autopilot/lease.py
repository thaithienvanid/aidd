"""The autopilot's lease and journal: one autopilot run per piece of work (`work`: a Spec, Epic, or Initiative id, a label, or `all`), and a line per step it did.

Autopilot runs the AIDD loop between a person's decisions. The `/aidd-team:autopilot` command starts a lease
before the first step (`aidd autopilot start`), notes each step's result (`aidd autopilot note`), and stops the lease
when it ends (`aidd autopilot stop`). `aidd autopilot next` reads the lease and the journal to decide each step, and a
later guard reads `current` and `for_session` to tell that a run is active. aidd runs no agent: these only record.

Everything lives in the git directory (`$(git rev-parse --git-common-dir)/aidd/`), never in the working tree, so a run
leaves no file to commit and every worktree of the repository sees the same lease:

- `lease.json`: {"schema_version", "leases": [{session_id, work, by, timebox, started_at, expires_at}]}, written
  whole through an exclusive temporary file. A file aidd cannot read fails closed: it is never taken as empty.
- `journal.jsonl`: one line per note: {at, session_id, work, spec?, head?, code, result, tokens?, cost?, merged?, text?}.
- `events.jsonl`: the run events (schemas/event.schema.json, `kind` = `autopilot`).
- `said.txt`: one line per note the guard gave once (`agents.delegate`'s steer), as `<session> <key>`.
- `snapshots.json`: {"schema_version", "sessions": {session_id: {at, text}}}: the state of the work `aidd hook
  pre-compact` saved before a compaction, which `aidd hook session-start` reads back after it.
- `guard.jsonl`: the guard's denial log (aidd.guard.denial_log), which `aidd metrics --guard` counts.

aidd commands write them, and refuse a symbolic link in their place; an agent with a shell can still edit them, so
what they say guides a cooperating autopilot and is never an approval. Each journal file keeps its last MAX_LINES
lines. One live lease holds a piece of work; a lease is stale once its timebox ends, and `take` may then replace it, saying so.
A lease on `all` holds all the work. Times are UTC ISO 8601.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import math
import os
import re
import secrets
import stat
import time
from pathlib import Path

from aidd import config
from aidd.kernel import git
from aidd.kernel.timestamps import parse_time

SCHEMA_VERSION = "1"
LEASE_FILE = "lease.json"
JOURNAL_FILE = "journal.jsonl"
RUN_EVENTS_FILE = "events.jsonl"
SAID_FILE = "said.txt"
SNAPSHOTS_FILE = "snapshots.json"
MAX_SNAPSHOTS = 20  # sessions whose snapshot is kept, newest first
MAX_SNAPSHOT_TEXT = 4000
DEFAULT_TIMEBOX = "6h"
ALL = "all"
RESULTS = ("ok", "fail", "waiting", "blocked")
ENDED = ("finished", "limit_reached")  # run events after which the run is over
CODE = re.compile(r"^[a-z_]+(\.[a-z_]+)*$")
WORK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
TIMEBOX = re.compile(r"^([1-9][0-9]{0,3})(m|h)$")
MAX_TEXT_CHARS = 200
MAX_LINES = 2000  # each journal file keeps its last MAX_LINES lines
JOURNAL_TAIL_BYTES = 256 * 1024  # what `status` reads from the end of the journal
LOCK_WAIT_SECONDS = 5.0
LOCK_STALE_S = 30.0
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)  # a FIFO in place of the file never hangs the open


class LeaseError(ValueError):
    """An autopilot command that cannot do what it was asked; the message names the next action."""


def stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now(now: dt.datetime | None) -> dt.datetime:
    return (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).replace(microsecond=0)


def timebox_delta(text: str) -> dt.timedelta:
    """`90m` or `2h` as a timedelta; anything else is an error."""
    m = TIMEBOX.match(str(text or "").strip())
    if not m:
        raise LeaseError(f"timebox {text!r} is not minutes or hours, such as 90m or 2h")
    n = int(m.group(1))
    return dt.timedelta(minutes=n) if m.group(2) == "m" else dt.timedelta(hours=n)


def lease_store(root: Path | str) -> Path:
    """The folder in the git directory that holds the lease, the journal, and the run events (config.state_dir)."""
    try:
        return config.state_dir(root)
    except ValueError:
        raise LeaseError("not a git repository: the autopilot lease lives in the git directory") from None


def _folder(root: Path | str, *, create: bool = False) -> Path:
    """The store, refused when it, or what it holds, is not what aidd writes: a symbolic link or another kind of file."""
    folder = lease_store(root)
    if folder.is_symlink():
        raise LeaseError(f"{folder} is a symbolic link: aidd writes only a real folder there; remove it")
    if create:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if folder.exists() and not folder.is_dir():
        raise LeaseError(f"{folder} is not a folder: remove it")
    return folder


def _regular(path: Path) -> bool:
    """True for a regular file, False when absent; any other kind (a link, a folder) is refused."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(st.st_mode):
        raise LeaseError(f"{path} is not a regular file (a symbolic link or a folder): remove it")
    return True


class _Lock:
    """An exclusive lock on the store for one read-modify-write. It holds a random token; whoever finds it older than
    LOCK_STALE_S takes it over by renaming it away, so only one waiter wins, and a holder that lost it says so."""

    def __init__(self, folder: Path):
        self.path = folder / ".lock"
        self.token = f"{os.getpid()}-{secrets.token_hex(8)}"

    def __enter__(self) -> _Lock:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            if time.monotonic() > deadline:
                raise LeaseError(f"{self.path} is held by another aidd command; try again")
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
            except FileExistsError:
                self._maybe_take_over()
                time.sleep(0.02)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self.token)
            return self

    def _maybe_take_over(self) -> None:
        try:
            st = os.lstat(self.path)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(st.st_mode):
            raise LeaseError(f"{self.path} is not a regular file (a symbolic link or a folder): remove it")
        if time.time() - st.st_mtime <= LOCK_STALE_S:
            return
        grave = self.path.with_name(f".lock.stale.{self.token}")
        try:
            os.rename(self.path, grave)  # atomic: of two waiters, one renames it
        except FileNotFoundError:
            return
        if os.lstat(grave).st_ino != st.st_ino:  # a fresh lock replaced the stale one meanwhile: give it back
            with contextlib.suppress(FileExistsError, OSError):
                os.link(grave, self.path)
        with contextlib.suppress(OSError):
            os.unlink(grave)

    def check(self) -> None:
        """Before a write: the lock is still this holder's, and fresh."""
        try:
            held = self.path.read_text(encoding="utf-8")
        except OSError:
            held = ""
        if held != self.token:
            raise LeaseError(f"{self.path} was taken over while this command held it; nothing was written, try again")
        with contextlib.suppress(OSError):
            os.utime(self.path)

    def __exit__(self, *exc) -> None:
        with contextlib.suppress(OSError):
            if self.path.read_text(encoding="utf-8") == self.token:
                self.path.unlink()


def _read_leases(folder: Path) -> list[dict]:
    path = folder / LEASE_FILE
    if not _regular(path):
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LeaseError(f"{path} cannot be read ({type(exc).__name__}): fix or remove it; aidd never overwrites it") from None
    leases = data.get("leases") if isinstance(data, dict) else None
    if not isinstance(leases, list) or not all(isinstance(x, dict) and x.get("session_id") and x.get("work") for x in leases):
        raise LeaseError(f"{path} is not a lease file aidd wrote: fix or remove it; aidd never overwrites it")
    return leases


def _write_leases(lock: _Lock, folder: Path, leases: list[dict]) -> None:
    _replace(lock, folder, LEASE_FILE, json.dumps({"schema_version": SCHEMA_VERSION, "leases": leases}, indent=2, sort_keys=True) + "\n")


def _replace(lock: _Lock, folder: Path, name: str, text: str) -> None:
    """Write the store's file `name` whole, through an exclusive temporary file; a link in its place is refused."""
    _regular(folder / name)
    tmp = folder / f".{name}.{secrets.token_hex(8)}"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        lock.check()
        os.replace(tmp, folder / name)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def _append(lock: _Lock, path: Path, line: dict) -> None:
    """Append one line; past MAX_LINES lines, keep the last MAX_LINES (rewritten through an exclusive temporary file).

    The file opened must be a regular file with one link that this user owns (CWE-59, CWE-62): a hard link to a file
    elsewhere is refused before a byte is written, as is a file that is not UTF-8 (nothing is appended to it)."""
    _regular(path)
    lock.check()
    try:
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _NONBLOCK, 0o600)
    except OSError as exc:
        raise LeaseError(f"{path} cannot be written ({exc.strerror}): it must be a regular file") from None
    with os.fdopen(fd, "r+b") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or (hasattr(os, "geteuid") and st.st_uid != os.geteuid()):
            raise LeaseError(f"{path} is not a file aidd wrote (a hard link, or another user's file): remove it")
        try:
            kept = fh.read().decode("utf-8")
        except UnicodeDecodeError:
            raise LeaseError(f"{path} holds a line that is not UTF-8: remove that line, or the file") from None
        added = json.dumps(line, sort_keys=True) + "\n"
        fh.write(added.encode("utf-8"))
    lines = (kept + added).splitlines(keepends=True)
    if len(lines) > MAX_LINES:
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(lines[-MAX_LINES:]))
        os.replace(tmp, path)


def _lines(path: Path, *, tail: int | None = None) -> list[dict]:
    if not _regular(path):
        return []
    with open(path, "rb") as fh:
        if tail is not None:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - tail))
            raw = fh.read().decode("utf-8", errors="replace")
            if size > tail:
                raw = raw.split("\n", 1)[-1]  # the first line may be cut
        else:
            raw = fh.read().decode("utf-8", errors="replace")
    out = []
    for text in raw.splitlines():
        with contextlib.suppress(ValueError):
            item = json.loads(text)
            if isinstance(item, dict):
                out.append(item)
    return out


def stale(lease: dict, now: dt.datetime | None = None) -> bool:
    """Whether the lease's timebox has ended (an unreadable expiry counts as ended)."""
    end = parse_time(lease.get("expires_at"))
    return end is None or _now(now) >= end


# A session whose transcripts show nothing for this long is gone (closed or crashed): a new run may take its lease over
# before the timebox ends. A live session writes its transcript at every message, its subagents' too.
ABANDONED_AFTER = dt.timedelta(minutes=20)


def abandoned(lease: dict, now: dt.datetime | None = None) -> dt.datetime | None:
    """When the lease's session last did anything, if that is longer ago than ABANDONED_AFTER (and the lease is older
    than that too), else None. A session aidd finds no transcript for is never taken as gone: its timebox decides."""
    from aidd.autopilot import usage

    t = _now(now)
    started = parse_time(lease.get("started_at"))
    last = usage.last_active(str(lease.get("session_id") or ""))
    if last is None or started is None or t - started < ABANDONED_AFTER or t - last < ABANDONED_AFTER:
        return None
    return last


def in_work(step: dict, work: str) -> bool:
    """A step about an item the work names: `all`, the item's id, its Epic or Initiative, or one of its labels."""
    if not step.get("id"):
        return False
    if work == ALL:
        return True
    return step["id"] == work or work in (step.get("labels") or []) or any(w.get("id") == work for w in step.get("why") or [])


def overlaps(work: str, other: str, steps: list[dict] | None = None, root: Path | str = ".") -> bool:
    """Whether two runs' work can reach the same item: the same name, `all`, or names that cover a common item (an Epic
    and one of its Specs, a label and a Spec that carries it). `steps`: the items with their `why` chains and labels,
    read from `root`'s work-item files when None."""
    if work == other or ALL in (work, other):
        return True
    if steps is None:
        steps = _open_work(root)
    return bool({s["id"] for s in steps if in_work(s, work)} & {s["id"] for s in steps if in_work(s, other)})


def _open_work(root: Path | str) -> list[dict]:
    """Each work item in the working tree's specs folder, as `in_work` reads one: its id, labels, and parent chain. From
    the files alone, so taking a lease never reaches the network."""
    from aidd import workitems
    from aidd.kernel import documents

    cfg = workitems.config_at(Path(root))
    folder = Path(root) / (cfg.specs_dir if cfg else "specs")
    idx: dict[str, dict] = {}
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8"), str(p))
        except (documents.DocumentError, OSError, UnicodeDecodeError):
            continue
        if data.get("id"):
            idx[str(data["id"])] = data
    return [{"id": i, "labels": list(d.get("labels") or []), "why": workitems.why(d, idx, None)} for i, d in idx.items()]


def leases(root: Path | str) -> list[dict]:
    """Every lease on record, live or stale, oldest first."""
    return sorted(_read_leases(_folder(root)), key=lambda x: str(x.get("started_at")))


def current(root: Path | str, now: dt.datetime | None = None, work: str | None = None) -> dict | None:
    """The newest live lease (of `work`, when given), or None: no run is active."""
    live = [x for x in leases(root) if not stale(x, now) and (work is None or x["work"] == work)]
    return live[-1] if live else None


def lease_for_session(root: Path | str, session_id: str, now: dt.datetime | None = None, *, include_stale: bool = False) -> dict | None:
    """The lease `session_id` holds, or None. A stale one only with `include_stale`."""
    found = [x for x in leases(root) if x["session_id"] == session_id and (include_stale or not stale(x, now))]
    return found[-1] if found else None


def resolve(root: Path | str, session_id: str | None, now: dt.datetime | None = None) -> dict:
    """The live lease a command acts for: the one `session_id` holds. Never another session's, so with no id it is an
    error that says how to pass `--session`: a lone lease may be another session's."""
    if not session_id:
        raise LeaseError("no session named: pass --session ID, the one `aidd autopilot start` printed")
    lease = lease_for_session(root, session_id, now)
    if lease is None:
        raise LeaseError(f"session {session_id} holds no live lease: `aidd autopilot start --session {session_id}` first")
    return lease


def _identity(root: Path | str) -> str:
    return git.config_value("user.email", str(root)) or git.config_value("user.name", str(root)) or "unknown"


def ended(root: Path | str, lease: dict) -> bool:
    """Whether the lease's run already said it is over (finished, or a limit)."""
    mine = [e for e in events(root) if (e.get("run") or {}).get("session_id") == lease["session_id"] and str(e.get("ts")) >= str(lease["started_at"])]
    return bool(mine) and mine[-1]["run"]["event"] in ENDED


def take_lease(
    root: Path | str, *, work: str = ALL, session_id: str | None = None, timebox: str = DEFAULT_TIMEBOX, now: dt.datetime | None = None
) -> tuple[dict, str]:
    """Start the lease on `work` for `session_id` (a new id when None) for `timebox`: (the lease, what happened).
    The same session starting its own live run again changes nothing (the timebox never grows), unless that run already
    ended (finished, a limit, or a plan ready for a person), when a person's start begins a new run. A live lease of
    another session on the same work, or on `all`, refuses it; a stale one is replaced."""
    if not WORK.match(work or ""):
        raise LeaseError(f"work {work!r} is not a Spec id, a label, or all")
    session_id = session_id or secrets.token_hex(8)
    if not SESSION_ID.match(session_id):
        raise LeaseError(f"session id {session_id!r} holds characters a session id never has")
    span = timebox_delta(timebox)
    t = _now(now)
    folder = _folder(root, create=True)
    with _Lock(folder) as lock:
        held = _read_leases(folder)
        mine = [x for x in held if x["session_id"] == session_id and not stale(x, t)]
        restart = False
        if mine and mine[-1]["work"] == work:
            if not ended(root, mine[-1]):
                return mine[-1], f"this session already holds the lease on {work} until {mine[-1]['expires_at']}"
            restart = True
        elif mine:
            raise LeaseError(f"this session holds the lease on {mine[-1]['work']}: `aidd autopilot stop` it first")
        gone = {x["session_id"]: when for x in held if x["session_id"] != session_id and not stale(x, t) and (when := abandoned(x, t))}
        rivals = [x for x in held if x["session_id"] != session_id and not stale(x, t) and x["session_id"] not in gone]
        # The open work, read once and only when two different names must be compared (an Epic and its Spec overlap).
        steps = _open_work(root) if any(x["work"] not in (work, ALL) and work != ALL for x in rivals) else []
        for x in rivals:
            if overlaps(x["work"], work, steps):
                raise LeaseError(
                    f"session {x['session_id']} ({x.get('by')}) holds the lease on {x['work']} until {x['expires_at']}, which covers "
                    f"some of {work}: wait for it, or ask that person to stop it"
                )
        replaced = [x for x in held if x["work"] in (work, ALL) and (stale(x, t) or x["session_id"] in gone) and x["session_id"] != session_id]
        lease = {
            "session_id": session_id,
            "work": work,
            "by": _identity(root),
            "timebox": timebox,
            "started_at": stamp(t),
            "expires_at": stamp(t + span),
        }
        keep = [x for x in held if x not in replaced and x["session_id"] != session_id]
        _write_leases(lock, folder, [*keep, lease])
    what = ("started a new run" if restart else "took the lease") + f" on {work} for session {session_id} until {lease['expires_at']}"
    if replaced:
        what += "; replaced the " + ", ".join(
            f"abandoned lease of session {x['session_id']} (no activity since {stamp(gone[x['session_id']])})"
            if x["session_id"] in gone
            else f"stale lease of session {x['session_id']} (expired {x['expires_at']})"
            for x in replaced
        )
    record_event(root, "started", lease, now=t)
    return lease, what


def release_lease(root: Path | str, *, session_id: str | None = None, now: dt.datetime | None = None) -> dict | None:
    """Stop the run: remove the lease `session_id` holds (with no id, the only lease on record); the removed lease, or
    None when none was held. Writes a `finished` run event unless the run already said it ended."""
    folder = _folder(root, create=True)
    with _Lock(folder) as lock:
        held = _read_leases(folder)
        found = [x for x in held if x["session_id"] == session_id] if session_id else held
        if not found:
            return None
        if not session_id and len(found) > 1:
            raise LeaseError(f"{len(found)} leases ({', '.join(x['session_id'] for x in found)}): pass --session ID to name yours")
        gone = found[-1]
        _write_leases(lock, folder, [x for x in held if x is not gone])
    if not ended(root, gone):
        record_event(root, "finished", gone, reason="stopped", now=now)
    return gone


def parse_note(text: str) -> tuple[str, str, str]:
    """`"<code> <result> [words]"` as (code, result, words). The words are data: aidd never reads them as a command."""
    parts = str(text or "").split(None, 2)
    if len(parts) < 2:
        raise LeaseError(f'a note is "<code> <result>", such as "spec.in_progress ok"; got {text!r}')
    code, result = parts[0], parts[1].lower()
    if not CODE.match(code):
        raise LeaseError(f"{code!r} is not a step code, such as spec.in_progress")
    if result not in RESULTS:
        raise LeaseError(f"result {result!r} is not one of {', '.join(RESULTS)}")
    return code, result, (parts[2] if len(parts) > 2 else "").strip()[:MAX_TEXT_CHARS]


def check_spend(tokens: object, cost: dict | None) -> None:
    """Spend a note records is a count of zero or more, and a non-negative, finite amount with its currency."""
    if tokens is not None and (isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0):
        raise LeaseError("--tokens is a count of zero or more")
    if cost is not None:
        amount = cost.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int | float) or not math.isfinite(amount) or amount < 0:
            raise LeaseError("--cost is an amount of zero or more, such as 0.42")
        if not CURRENCY.match(str(cost.get("currency") or "")):
            raise LeaseError("--currency is an ISO 4217 code, such as USD")


def _head(root: Path | str) -> str | None:
    sha = git.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


# A goal as the journal keeps it: its words, at most this many characters.
GOAL_MAX = 300


def note_step(
    root: Path | str,
    text: str,
    *,
    session_id: str | None = None,
    spec: str | None = None,
    tokens: int | None = None,
    cost: dict | None = None,
    merged: int | None = None,
    goal: str | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """Append one journal line for the step the run just did, with the head it ran on, and its `step_done` run event.
    It needs the live lease of `session_id` (with no id, the only live lease). A goal's plan step keeps the `goal` it
    planned, so a later start with the same goal goes on with its plan instead of planning it twice."""
    code, result, words = parse_note(text)
    check_spend(tokens, cost)
    t = _now(now)
    lease = resolve(root, session_id, t)
    entry: dict = {"at": stamp(t), "session_id": lease["session_id"], "work": lease["work"], "code": code, "result": result}
    spec = spec or (lease["work"] if lease["work"] != ALL else None)
    if spec:
        entry["spec"] = spec
    head = _head(root)
    if head:
        entry["head"] = head
    if tokens is not None:
        entry["tokens"] = int(tokens)
    if cost is not None:
        entry["cost"] = {"amount": cost["amount"], "currency": cost["currency"]}
    if merged is not None:
        entry["merged"] = int(merged)
    if words:
        entry["text"] = words
    if goal and goal.strip():
        entry["goal"] = " ".join(goal.split())[:GOAL_MAX]
    folder = _folder(root, create=True)
    with _Lock(folder) as lock:
        _append(lock, folder / JOURNAL_FILE, entry)
    extra = {k: entry[k] for k in ("tokens", "cost") if k in entry}
    record_event(root, "step_done", lease, code=code, result=result, spec_id=spec, now=t, **extra)
    return entry


def read_journal(root: Path | str, *, tail: int | None = None) -> list[dict]:
    """The journal's lines, oldest first; with `tail`, only those in its last `tail` bytes."""
    return _lines(_folder(root) / JOURNAL_FILE, tail=tail)


def events(root: Path | str) -> list[dict]:
    """Every run event, oldest first."""
    return _lines(_folder(root) / RUN_EVENTS_FILE)


def run_event(event: str, lease: dict, *, now: dt.datetime | None = None, spec_id: str | None = None, **fields) -> dict:
    """One run line (schemas/event.schema.json with `kind` = `autopilot`), validated."""
    from aidd import gate
    from aidd.kernel import json_schema

    run = {"event": event, "session_id": lease["session_id"], "work": lease["work"]}
    if spec_id:
        run["spec_id"] = str(spec_id)
    run |= {k: v for k, v in fields.items() if v not in (None, "")}
    line = gate.event_header() | {"ts": stamp(_now(now)), "kind": "autopilot", "run": run}
    errs = json_schema.validate(line, "event.schema.json")
    if errs:
        raise RuntimeError(f"invalid run event: {'; '.join(errs)}")
    return line


def append_event(root: Path | str, line: dict) -> None:
    """Append one event line to the git directory's events.jsonl, under the store's lock: the one writer of the store,
    for autopilot run lines and for local gate lines (cli.local_events)."""
    folder = _folder(root, create=True)
    with _Lock(folder) as lock:
        _append(lock, folder / RUN_EVENTS_FILE, line)


def record_event(root: Path | str, event: str, lease: dict, **fields) -> dict:
    """Append a run event to the git directory's events.jsonl."""
    line = run_event(event, lease, **fields)
    append_event(root, line)
    return line


# Run events a person hears about: a decision waits, the run is blocked, a limit stopped it, or it finished. A step
# done is for the journal and the metrics only, never a notice (quiet for the person).
NOTIFY = ("waiting_on_person", "blocked", "limit_reached", "finished")


def notices(lines: list[dict]) -> list[dict]:
    """The run events a notifier may send: never `started` or `step_done`."""
    return [e for e in lines if e.get("kind") == "autopilot" and (e.get("run") or {}).get("event") in NOTIFY]


def show_leases(root: Path | str, now: dt.datetime | None = None, *, last: int = 20) -> dict:
    """`aidd autopilot status --json` (schemas/autopilot-status.schema.json): every lease with whether it is stale, the
    journal's last lines (read from its tail), the last notices a person would hear, and where they live."""
    t = _now(now)
    folder = _folder(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "store": str(folder),
        "leases": [x | {"stale": stale(x, t)} for x in leases(root)],
        "journal": read_journal(root, tail=JOURNAL_TAIL_BYTES)[-last:],
        "notices": [e["run"] for e in notices(events(root))][-5:],
    }


def lease_markdown(shown: dict) -> str:
    lines = []
    if not shown["leases"]:
        lines.append("Autopilot is off: no lease. `aidd autopilot start --work SPEC` starts it.")
    for x in shown["leases"]:
        state = "stale (its timebox ended)" if x["stale"] else "live"
        lines.append(f"Lease on {x['work']}: session {x['session_id']}, by {x.get('by')}, {x['started_at']} to {x['expires_at']}, {state}")
    if shown["journal"]:
        lines += ["", "Journal (newest last):"]
        for e in shown["journal"]:
            spent = "".join([f", {e['tokens']} tokens" if "tokens" in e else "", f", {e['cost']['amount']} {e['cost']['currency']}" if "cost" in e else ""])
            lines.append(f"- {e['at']} {e.get('spec') or e['work']}: {e['code']} {e['result']}{spent}")
    if shown.get("notices"):
        lines += ["", "What a person heard last: " + "; ".join(f"{n['event']} ({n.get('reason') or n.get('code') or n['work']})" for n in shown["notices"])]
    lines += ["", f"Stored in {shown['store']} (the git directory; never committed)."]
    return "\n".join(lines) + "\n"


def is_first_mention(root: Path | str, session_id: str, key: str) -> bool:
    """True the first time `session_id` asks to say `key`, False after (it keeps the last MAX_LINES marks)."""
    line = f"{session_id} {' '.join(str(key).split())}"
    folder = _folder(root, create=True)
    with _Lock(folder) as lock:
        path = folder / SAID_FILE
        said = path.read_text(encoding="utf-8").splitlines() if _regular(path) else []
        if line in said:
            return False
        _replace(lock, folder, SAID_FILE, "\n".join([*said[-(MAX_LINES - 1) :], line]) + "\n")
    return True


def save_snapshot(root: Path | str, session_id: str, text: str, now: dt.datetime | None = None) -> Path:
    """Keep `text` as the session's snapshot (the newest MAX_SNAPSHOTS sessions); the file it went to."""
    if not SESSION_ID.match(session_id or ""):
        raise LeaseError(f"session id {session_id!r} holds characters a session id never has")
    folder = _folder(root, create=True)
    path = folder / SNAPSHOTS_FILE
    with _Lock(folder) as lock:
        sessions = _read_snapshots(path)
        sessions[session_id] = {"at": stamp(_now(now)), "text": text[:MAX_SNAPSHOT_TEXT]}
        newest = sorted(sessions.items(), key=lambda kv: str(kv[1].get("at")), reverse=True)[:MAX_SNAPSHOTS]
        _replace(lock, folder, SNAPSHOTS_FILE, json.dumps({"schema_version": SCHEMA_VERSION, "sessions": dict(newest)}, indent=2, sort_keys=True) + "\n")
    return path


def _read_snapshots(path: Path) -> dict:
    if not _regular(path):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # a snapshot is a convenience: an unreadable file starts over
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return {k: v for k, v in sessions.items() if isinstance(v, dict) and isinstance(v.get("text"), str)} if isinstance(sessions, dict) else {}


def saved_snapshot(root: Path | str, session_id: str) -> dict | None:
    """The snapshot `session_id` saved last ({at, text}), or None."""
    return _read_snapshots(_folder(root) / SNAPSHOTS_FILE).get(session_id)
