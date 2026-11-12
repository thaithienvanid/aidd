"""A cache of typed rows in one SQLite file, refilled place by place when a place changes. It knows no domain.

One table holds every row, in the single-table style: `entry(place, type, id, subject, at, data)`, where `place` is
where the copy lives (`worktree:<path>`, `branch:<name>`), `id` names the row inside its place, and `data` is JSON.
A second table, `source`, holds each place's stamp: what the place looked like when it was read. Before a read, the
caller gives every place with its stamp and a loader; a place whose stamp changed is read again, and a place that is
gone loses its rows. So the cache is fresh on every read, with no hooks.

It is only a cache: the files and the refs are the truth. A file that is not a database, or of another version, is
rebuilt; one that stays locked or cannot be opened is skipped, and the caller then reads the places directly.
Agents in parallel worktrees share it through SQLite's rollback journal and a busy timeout: a refresh is a few rows,
so a reader waits for a writer only briefly, and the last writer is right, because it replaces a place's rows from
its files. It uses no WAL: WAL's shared-memory file kills a process outright when something truncates it, and a
crash is the one failure a cache must never cause.

The same file holds passages for a search: lines of text, each with where it is, in SQLite's full-text table (FTS5),
and their places' stamps in a table of their own (since SCHEMA_VERSION 2). A place of passages that is not given stays, so callers that search
different places share the file without reading each other's places again, unless the caller's `gone` says the place
no longer exists, such as a worktree that was removed: then it loses its rows. Where SQLite has no FTS5, or the file does
not open, a search reads the places directly and matches each term as plain text.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import NamedTuple

from aidd.kernel import regular_files

SCHEMA_VERSION = 2  # 2 added the passages; a file of another version is rebuilt, never migrated
BUSY_TIMEOUT_SECONDS = 5.0


class Entry(NamedTuple):
    """One row: its type, its id inside its place, the work item it belongs to, its time, and its data. A work item's
    row leaves `subject` and `at` empty; they are for rows that have them, such as records, which no view indexes yet
    (`aidd records` reads the files)."""

    type: str
    id: str
    subject: str | None
    at: str | None
    data: dict


_TABLES = (
    "CREATE TABLE entry (place TEXT NOT NULL, type TEXT NOT NULL, id TEXT NOT NULL, subject TEXT, at TEXT, data TEXT NOT NULL, PRIMARY KEY (place, type, id))",
    "CREATE TABLE source (name TEXT PRIMARY KEY, stamp TEXT NOT NULL)",
    "CREATE TABLE passage_source (name TEXT PRIMARY KEY, stamp TEXT NOT NULL)",
)
# The passages' full-text table, built with the rest where SQLite has FTS5. Without FTS5 the statement fails, the other
# tables stay, and a search reads its places directly.
PASSAGE_TABLE = "CREATE VIRTUAL TABLE passage USING fts5(text, place UNINDEXED, ref UNINDEXED, line UNINDEXED, at UNINDEXED)"
# The errors that mean the file is junk nothing can use, so it is rebuilt. A locked or unreadable file is never removed,
# because another process may be using it.
_JUNK = ("SQLITE_NOTADB", "SQLITE_CORRUPT")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")  # the mode the index needs: no side files beside the cache
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            # Each statement on its own: `executescript` would commit the transaction first. The version is read again
            # under the lock, so of two first runs at once, only one builds the tables.
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                drops = (f"DROP TABLE IF EXISTS {t}" for t in ("entry", "source", "passage", "passage_source"))
                for statement in (*drops, *_TABLES, f"PRAGMA user_version = {SCHEMA_VERSION}"):
                    conn.execute(statement)
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(PASSAGE_TABLE)
            conn.execute("COMMIT")
    except BaseException:
        conn.close()
        raise
    return conn


def refusal(git_folder: Path, path: Path) -> str:
    """Why aidd never opens the index at `path` (`<git folder>/aidd/index.sqlite`), or "": SQLite follows a link at the
    file, at its journal, or on the way from `git_folder`, so one would send the cache, and its rebuild, outside the git
    folder. Then the index reads as one that cannot be opened, and each command reads the files themselves, which loses
    nothing."""
    return next((why for p in (path, path.with_name(path.name + "-journal")) if (why := regular_files.write_refusal(git_folder, p))), "")


@contextlib.contextmanager
def opened(path: Path) -> Iterator[sqlite3.Connection | None]:
    """The index at `path`, created when missing and rebuilt when it is junk or of another version; None when it cannot
    be opened, such as when it stays locked or its folder cannot be written."""
    conn = None
    try:
        if why := refusal(path.parent.parent, path):
            raise OSError(why)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = _connect(path)
        except sqlite3.DatabaseError as exc:
            if getattr(exc, "sqlite_errorname", "") not in _JUNK:
                raise
            path.unlink(missing_ok=True)
            conn = _connect(path)
    except (OSError, sqlite3.Error):
        conn = None
    try:
        yield conn
    finally:
        if conn is not None:
            conn.close()


def refresh(conn: sqlite3.Connection, places: Mapping[str, tuple[str, Callable[[], list[Entry]]]]) -> None:
    """Make the index hold exactly `places`: each one's rows read again when its stamp changed, and the rows of a place
    no longer given removed."""
    stored = dict(conn.execute("SELECT name, stamp FROM source").fetchall())
    stale = {name: load for name, (stamp, load) in places.items() if stored.get(name) != stamp}
    gone = set(stored) - set(places)
    if not stale and not gone:
        return
    loaded = {name: load() for name, load in stale.items()}  # read before the write lock, so a slow read blocks no one
    conn.execute("BEGIN IMMEDIATE")
    try:
        for name in gone | set(loaded):
            conn.execute("DELETE FROM entry WHERE place = ?", (name,))
            conn.execute("DELETE FROM source WHERE name = ?", (name,))
        for name, rows in loaded.items():
            conn.executemany(
                "INSERT OR REPLACE INTO entry (place, type, id, subject, at, data) VALUES (?, ?, ?, ?, ?, ?)",
                [(name, e.type, e.id, e.subject, e.at, json.dumps(e.data, sort_keys=True)) for e in rows],
            )
            conn.execute("INSERT INTO source (name, stamp) VALUES (?, ?)", (name, places[name][0]))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def entries(conn: sqlite3.Connection) -> dict[str, list[Entry]]:
    """Every row, by place, in the order of each place's ids."""
    out: dict[str, list[Entry]] = {}
    for place, entry_type, eid, subject, at, data in conn.execute("SELECT place, type, id, subject, at, data FROM entry ORDER BY place, id, type"):
        out.setdefault(place, []).append(Entry(entry_type, eid, subject, at, json.loads(data)))
    return out


def read_through(path: Path, places: Mapping[str, tuple[str, Callable[[], list[Entry]]]]) -> dict[str, list[Entry]]:
    """Every place's rows, through the index at `path` when it opens, and straight from the loaders when it does not."""
    with opened(path) as conn:
        if conn is not None:
            try:
                refresh(conn, places)
                return entries(conn)
            except sqlite3.Error:
                pass
    return {name: sorted(load(), key=lambda e: (e.id, e.type)) for name, (_, load) in places.items()}


class Passage(NamedTuple):
    """One line of text to search: what holds it (a file, or an id), its line there (0 for none), its time, and the text."""

    ref: str
    line: int
    at: str | None
    text: str


class Found(NamedTuple):
    """A passage that matched, with its place."""

    place: str
    passage: Passage


_ORDER = "ORDER BY coalesce(at, '') DESC, place, ref, CAST(line AS INTEGER)"


def _passage_table(conn: sqlite3.Connection) -> None:
    """Create the full-text table when it is missing, as when the index was built by a SQLite without FTS5. Raises
    sqlite3.OperationalError where this SQLite has no FTS5 either."""
    exists = "SELECT 1 FROM sqlite_master WHERE name = 'passage'"
    if conn.execute(exists).fetchone():
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        if not conn.execute(exists).fetchone():
            conn.execute(PASSAGE_TABLE)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _refresh_passages(
    conn: sqlite3.Connection, places: Mapping[str, tuple[str, Callable[[], list[Passage]]]], gone: Callable[[str], bool] = lambda name: False
) -> None:
    """Read again each place whose stamp changed; a place not given keeps its rows, unless `gone` says it is gone."""
    stored = dict(conn.execute("SELECT name, stamp FROM passage_source").fetchall())
    loaded = {name: load() for name, (stamp, load) in places.items() if stored.get(name) != stamp}
    dropped = [name for name in stored if name not in places and gone(name)]
    if not loaded and not dropped:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        for name in dropped:
            conn.execute("DELETE FROM passage WHERE place = ?", (name,))
            conn.execute("DELETE FROM passage_source WHERE name = ?", (name,))
        for name, rows in loaded.items():
            conn.execute("DELETE FROM passage WHERE place = ?", (name,))
            conn.executemany("INSERT INTO passage (text, place, ref, line, at) VALUES (?, ?, ?, ?, ?)", [(p.text, name, p.ref, p.line, p.at) for p in rows])
            conn.execute("INSERT OR REPLACE INTO passage_source (name, stamp) VALUES (?, ?)", (name, places[name][0]))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _phrase(term: str) -> str:
    """A term as an FTS5 string that starts a word: quoted, so no character in it is query syntax."""
    return '"' + term.replace('"', '""') + '"*'


def search_passages(
    path: Path,
    places: Mapping[str, tuple[str, Callable[[], list[Passage]]]],
    terms: list[str],
    *,
    limit: int,
    gone: Callable[[str], bool] = lambda name: False,
) -> tuple[list[Found], bool, str]:
    """The passages of `places` that hold every term: the first `limit`, newest first, then those with no time, each
    group by place, ref, and line; whether more matched; and how it searched. `full_text` matches each term at the
    start of a word, through the index at `path`; `substring` matches it anywhere in the line, ignoring case, read
    straight from the loaders, where SQLite has no FTS5 or the index does not open."""
    with opened(path) as conn:
        if conn is not None:
            try:
                _passage_table(conn)
                _refresh_passages(conn, places, gone)
                names = list(places)
                rows = conn.execute(
                    f"SELECT place, ref, line, at, text FROM passage WHERE passage MATCH ? AND place IN ({', '.join('?' * len(names))}) {_ORDER} LIMIT ?",
                    (" ".join(_phrase(t) for t in terms), *names, limit + 1),
                ).fetchall()
                found = [Found(place, Passage(ref, int(line), at, text)) for place, ref, line, at, text in rows]
                return found[:limit], len(found) > limit, "full_text"
            except sqlite3.Error:
                pass
    folded = [t.casefold() for t in terms]
    found = [Found(name, p) for name, (_, load) in places.items() for p in load() if all(t in p.text.casefold() for t in folded)]
    found.sort(key=lambda f: (f.place, f.passage.ref, f.passage.line))
    found.sort(key=lambda f: f.passage.at or "", reverse=True)  # a stable sort keeps the order above inside one time
    return found[:limit], len(found) > limit, "substring"
