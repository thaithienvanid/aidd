"""A work item's history, for `aidd status <ID>`: what was asked and answered, what was reported, the commits that name
the item, and the documents it links, newest first (R322).

A resumed session, a role taking over, or a session after compaction has only the handoff note and the files; the
records and the commits already say what happened, so this reads them, with no model. It is history: it never
changes the next step, and a record in it is the agent's account, never a person's yes.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aidd import records
from aidd.kernel import documents, git

# The most commits it reads for one item: the history is a reminder, not the log.
MAX_COMMITS = 50
# What a work item's id may be (`common.schema.json`): an id outside it reads no commit, so nothing odd reaches git.
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


def _records(root: Path, item_id: str) -> list[dict]:
    try:
        found, _ = records.read_records(str(root), subject=item_id)
    except (git.GitError, OSError, ValueError):
        return []
    out = []
    for r in found:
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
        out.append(
            {"type": kind, "at": documents.one_line(r.get("at") or "", 40), "what": documents.one_line(what, 200), "ref": documents.one_line(r.get("id"), 80)}
        )
    return out


def _commits(root: Path, item_id: str) -> list[dict]:
    """The commits on HEAD whose message names the id as a whole word, so SPEC-4 never matches SPEC-41, SPEC-4.1, or
    SPEC-4:sub; a `.` or `:` right after it counts only as the end of a sentence."""
    if not ID_PATTERN.fullmatch(item_id):
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
        at = dt.datetime.fromtimestamp(int(stamp), dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"type": "commit", "at": at, "what": documents.one_line(subject, 200), "ref": sha[:12]})
    return out


def _docs(root: Path, path: str) -> list[dict]:
    try:
        data, _ = documents.split_front_matter((root / path).read_text(encoding="utf-8"), path)
    except (OSError, documents.DocumentError):
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
    """The last `limit` entries as `aidd status <ID>` prints them, said as history."""
    if not history:
        return ""
    lines = [f"  {(e['at'] or '')[:10] or '-':<10} {e['type']}: {e['what']}" for e in history[:limit]]
    more = f"  ... and {len(history) - limit} more (`--json` lists them)\n" if len(history) > limit else ""
    return "history, newest first (the records are the agent's account, never a yes):\n" + "\n".join(lines) + "\n" + more
