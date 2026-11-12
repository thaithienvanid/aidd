"""What `aidd recall` searches, each source a place of the index (aidd.kernel.index), with its stamp and its loader.

A place is `recall:<worktree>:<source>`, so each worktree of a clone keeps its own rows in the shared index. A file
source's stamp is its files' names, sizes, times, and inodes. The records' stamp is their files' names and sizes, since
a record never changes, and the commits' stamp is the head commit. Each stamp also holds ROW_FORMAT, so no index serves
rows of an older shape.

Every file is another's text, read as data. A link, a file outside the repository, one over MAX_FILE_BYTES, and one
past MAX_FILES in its source are skipped, and the answer names each.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from aidd import config, records, workitems
from aidd.kernel import documents, git, index, timestamps

# The shape of a place's rows: a change to how rows are built raises it.
ROW_FORMAT = 1
MAX_FILE_BYTES = documents.MAX_DOCUMENT_BYTES
MAX_FILES = 2000
MAX_COMMITS = 1000
# The documents a repository keeps one of, by their type in `graph.documents` of schemas/roles.json.
ONE_PER_REPOSITORY = ("glossary", "product-brief", "improvement-log")
_UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

Place = tuple[str, Callable[[], list[index.Passage]]]


def _stamp(what: str) -> str:
    return hashlib.sha256(f"{ROW_FORMAT}\0{what}".encode()).hexdigest()


def _document_files(top: Path, cfg: config.Config | None) -> dict[str, list[Path]]:
    """Each document source's candidate files, in path order."""
    cfg = cfg or config.EMPTY
    specs_dir, docs_dir = cfg.specs_dir, cfg.docs_dir
    specs, adrs = top / specs_dir, top / docs_dir / workitems.adr_folder()
    folders = [top / d for d in workitems.work_folders(specs_dir, cfg.product_dir)]  # the Specs' folder, and the Intents' folder
    found = sorted(p for d in folders if d.is_dir() for p in d.rglob("*.md") if not workitems.is_saved_request(p, specs))
    out = {"spec": found, "adr": sorted(adrs.glob("*.md")) if adrs.is_dir() else []}
    for doc_type in ONE_PER_REPOSITORY:
        out[doc_type] = [top / rel.replace("{docs}", docs_dir) for rel, _ in workitems.REPO_DOCS[doc_type]]
    return out


def _readable(top: Path, paths: list[Path], skipped: list[dict]) -> list[tuple[str, Path, os.stat_result]]:
    """The files to read, with their repository paths and stats; each one skipped is added to `skipped`."""
    real_top = top.resolve()
    out: list[tuple[str, Path, os.stat_result]] = []
    for path in paths:
        rel = path.relative_to(top).as_posix()
        if not path.is_symlink() and not path.is_file():
            continue  # a living document the team has not written
        if path.is_symlink():
            reason = "a link, which recall never follows"
        elif not path.resolve().is_relative_to(real_top):
            reason = "outside the repository"
        elif (st := path.stat()).st_size > MAX_FILE_BYTES:
            reason = f"larger than {MAX_FILE_BYTES // 1024} KiB"
        elif len(out) >= MAX_FILES:
            reason = f"past the first {MAX_FILES} files of its source"
        else:
            out.append((rel, path, st))
            continue
        skipped.append({"path": rel, "reason": reason})
    return out


def _lines(files: list[tuple[str, Path, os.stat_result]]) -> list[index.Passage]:
    """Each line of each file that holds more than spaces, numbered as an editor numbers it."""
    out = []
    for rel, path, _ in files:
        try:
            with path.open("rb") as f:
                raw = f.read(MAX_FILE_BYTES + 1)
        except OSError:
            continue
        if len(raw) > MAX_FILE_BYTES:
            continue  # it grew past the cap since its stamp: the next stamp skips it
        text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        out += [index.Passage(rel, n, None, line) for n, line in enumerate(text.split("\n"), 1) if line.strip()]
    return out


def _file_place(files: list[tuple[str, Path, os.stat_result]]) -> Place:
    what = "".join(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_ctime_ns}\0{st.st_ino}\n" for rel, _, st in files)
    return _stamp(what), lambda: _lines(files)


def _record_text(record: dict) -> str:
    """A record's words on one line: its type, its subject, then every string in its data, in key order."""
    out, stack = [str(record["type"]), str(record.get("subject") or "")], [record["data"]]
    while stack:  # a read record nests at most 16 levels (records.parse_record)
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            stack.extend(node[k] for k in sorted(node, reverse=True))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return " ".join(s for s in out if s)


def _record_place(top: Path) -> Place:
    folder = records.records_dir(str(top))
    names = sorted(folder.glob("*/*/*.json")) if folder.is_dir() else []
    what = "".join(f"{p.relative_to(folder).as_posix()}\0{p.stat().st_size}\n" for p in names if p.is_file())

    def load() -> list[index.Passage]:
        found, _ = records.read_records(str(top))
        return [index.Passage(r["id"], 0, r["recorded_at"] if _UTC_TIME.fullmatch(str(r.get("recorded_at"))) else None, _record_text(r)) for r in found]

    return _stamp(what), load


def _commit_place(top: Path) -> Place:
    head = git.run(["rev-parse", "--verify", "-q", "HEAD"], str(top), check=False).strip()

    def load() -> list[index.Passage]:
        rows = git.log_fields(["-n", str(MAX_COMMITS)], ["%H", "%h", "%ct"], str(top), check=False) if head else []
        bodies = git.messages([sha for sha, _, _ in rows], str(top))
        out = []
        for sha, short, seconds in rows:
            subject = bodies.get(sha, "").split("\n", 1)[0].strip()
            if subject:
                at = timestamps.utc_stamp(dt.datetime.fromtimestamp(int(seconds), dt.UTC))
                out.append(index.Passage(short, 0, at, subject))
        return out

    return _stamp(head), load


def gone(name: str) -> bool:
    """Whether a stored place `recall:<worktree>:<source>` names a worktree whose folder is gone, so its rows go too."""
    return name.startswith("recall:") and not Path(name.removeprefix("recall:").rpartition(":")[0]).is_dir()


def places(top: Path, cfg: config.Config | None) -> tuple[dict[str, Place], list[dict]]:
    """Every source of the worktree `top` as a place of the index, by name; and the files skipped, with why."""
    skipped: list[dict] = []
    out = {f"recall:{top}:record": _record_place(top)}
    for source, paths in _document_files(top, cfg).items():
        out[f"recall:{top}:{source}"] = _file_place(_readable(top, paths, skipped))
    out[f"recall:{top}:commit"] = _commit_place(top)
    return out, skipped
