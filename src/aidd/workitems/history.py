"""A work item's history, for `aidd status <ID>`: what was asked and answered, what was reported, the commits that name
the item, and the documents it links, newest first.

A resumed session, a role taking over, or a session after compaction has only the handoff note and the files; the
records and the commits already say what happened, so this reads them, with no model. It is history: it never
changes the next step, and a record in it is the agent's account, never a person's yes.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aidd import records
from aidd.kernel import documents, git, regular_files, timestamps
from aidd.workitems.ids import is_id

# The most commits it reads for one item: the history is a reminder, not the log.
MAX_COMMITS = 50
# The most commits the page reads for every item at once.
MAX_BATCH_COMMITS = 500
# What a work item's id may be (`common.schema.json`): an id outside it reads no commit, so nothing odd reaches git.


def _record_entry(r: dict) -> dict:
    data: dict = r["data"] if isinstance(r.get("data"), dict) else {}
    if r.get("type") == "decision":
        question: dict = data["question"] if isinstance(data.get("question"), dict) else {}
        answer: dict = data["answer"] if isinstance(data.get("answer"), dict) else {}
        words = f' ("{answer["words"]}")' if answer.get("words") else ""
        what = f"{data.get('action') or 'asked'}: {question.get('text', '')} → {answer.get('outcome', '')}{words}"
    elif r.get("type") == "report":
        what = f"{data.get('action', '')}: {data.get('said', '')}"
    else:
        what = str(r.get("type"))
    kind = r.get("type") if r.get("type") in ("decision", "report") else "record"
    return {
        "type": kind,
        "at": documents.one_line(r.get("recorded_at") or "", 40),
        "what": documents.one_line(what, 200),
        "ref": documents.one_line(r.get("id"), 80),
    }


def _records(root: Path, item_id: str) -> list[dict]:
    try:
        found, _ = records.read_records(str(root), subject=item_id)
    except (git.GitError, OSError, ValueError):
        return []
    return [_record_entry(r) for r in found]


def _commits(root: Path, item_id: str) -> list[dict]:
    """The commits on HEAD whose message names the id as a whole word, so SPEC-4 never matches SPEC-41, SPEC-4.1, or
    SPEC-4:sub; a `.` or `:` right after it counts only as the end of a sentence."""
    if not is_id(item_id):
        return []
    word = item_id.replace(".", r"\.")
    pattern = f"(^|[^A-Za-z0-9_.:-]){word}([^A-Za-z0-9_.:-]|[.:]([^A-Za-z0-9_.:-]|$)|$)"
    try:
        log = git.run(["log", f"-{MAX_COMMITS}", "-E", f"--grep={pattern}", "--format=%H%x1f%ct%x1f%s"], str(root), check=False)
    except (git.GitError, OSError):
        return []
    out = []
    for line in log.splitlines():
        sha, _, rest = line.partition("\x1f")
        stamp, _, subject = rest.partition("\x1f")
        if not stamp.isdigit():
            continue
        at = timestamps.utc_stamp(dt.datetime.fromtimestamp(int(stamp), dt.UTC))
        out.append({"type": "commit", "at": at, "what": documents.one_line(subject, 200), "ref": sha[:12]})
    return out


def _id_pattern(item_id: str) -> re.Pattern[str]:
    """The pattern `_commits` greps for, as a regex: the id as a whole word."""
    word = item_id.replace(".", r"\.")
    return re.compile(f"(^|[^A-Za-z0-9_.:-]){word}([^A-Za-z0-9_.:-]|[.:]([^A-Za-z0-9_.:-]|$)|$)")


def work_items_history(root: Path, ids: list[str], limit: int = 5) -> dict[str, list[dict]]:
    """The newest `limit` entries of each item's history, for the page, in one records read and one `git log`, never one
    for each item. It reads the newest MAX_BATCH_COMMITS subjects on HEAD, which is a reminder, not the log."""
    wanted = [i for i in dict.fromkeys(ids) if is_id(i)]
    out: dict[str, list[dict]] = {i: [] for i in wanted}
    try:
        found, _ = records.read_records(str(root))
    except (git.GitError, OSError, ValueError):
        found = []
    for r in found:
        if r.get("subject") in out:
            out[r["subject"]].append(_record_entry(r))
    patterns = {i: _id_pattern(i) for i in wanted}
    try:
        log = git.run(["log", f"-{MAX_BATCH_COMMITS}", "--format=%H%x1f%ct%x1f%s"], str(root), check=False)
    except (git.GitError, OSError):
        log = ""
    for line in log.splitlines():
        sha, _, rest = line.partition("\x1f")
        stamp, _, subject = rest.partition("\x1f")
        if not stamp.isdigit():
            continue
        at = timestamps.utc_stamp(dt.datetime.fromtimestamp(int(stamp), dt.UTC))
        for i, pattern in patterns.items():
            if pattern.search(subject):
                out[i].append({"type": "commit", "at": at, "what": documents.one_line(subject, 200), "ref": sha[:12]})
    return {i: sorted(entries, key=lambda e: e["at"], reverse=True)[:limit] for i, entries in out.items()}


def _docs(root: Path, path: str) -> list[dict]:
    text = regular_files.named_file_bytes(root, path, documents.MAX_DOCUMENT_BYTES)[0]
    try:
        data, _ = documents.split_front_matter(text.decode("utf-8", errors="replace"), path) if text is not None else ({}, "")
    except documents.DocumentError:
        return []
    return [
        {"type": "doc", "at": "", "what": documents.one_line(f"{d.get('type', 'doc')}: {d['path']}", 200), "ref": str(d["path"])}
        for d in data.get("docs") or []
        if isinstance(d, dict) and isinstance(d.get("path"), str)
    ]


def work_item_history(root: Path, item_id: str, path: str, *, docs: bool = True) -> list[dict]:
    """The item's records and commits, newest first, then the documents it links; with `docs` false, none, as for a
    version of the item another branch holds, whose links this worktree's file may not say."""
    dated = sorted(_records(root, item_id) + _commits(root, item_id), key=lambda e: e["at"], reverse=True)
    return dated + (_docs(root, path) if docs else [])


def history_text(history: list[dict], limit: int = 10) -> str:
    """The last `limit` entries as `aidd status <ID>` prints them, said as history. Where the item has records, a first line
    counts how many times a person was asked: each `decision` record is one answered ask, so the lead's close-out says it."""
    if not history:
        return ""
    lines = [f"  {(e['at'] or '')[:10] or '-':<10} {e['type']}: {e['what']}" for e in history[:limit]]
    more = f"  ... and {len(history) - limit} more (`--json` lists them)\n" if len(history) > limit else ""
    asked = sum(e["type"] == "decision" for e in history)
    count = (
        f"a person was asked {asked} time{'' if asked == 1 else 's'}, by its decision records\n"
        if any(e["type"] in ("decision", "report") for e in history)
        else ""
    )
    return count + "history, newest first (the records are the agent's account, never a yes):\n" + "\n".join(lines) + "\n" + more
