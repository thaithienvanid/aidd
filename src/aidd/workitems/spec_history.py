"""`aidd log <spec>`: one Spec's history from git alone: its status transitions with the time spent in each, the
approvals recorded for it, and the agents that wrote the commits touching its scope.

The status now is derived (`derived_status.py`), as `aidd list` derives it. The history of the stored `status` line, a cache,
comes from `git log -p`, so it needs no tracker and no server: bookkeeping a person or an agent committed is the
record, and the approvals and commits below show what moved the derived status. Approvals come from the decision records
(`refs/aidd/decisions`, written by `aidd approve`) and from gate records written with `aidd gate --record`, when
present. Nothing here is evidence the gate reads; it is a view for the people steering the work.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aidd import config as cfgmod
from aidd.kernel import documents, git, globs
from aidd.kernel.timestamps import parse_time
from aidd.workitems import decision_records, spec_file

MAX_COMMITS = 500
# A top-level `status:` line a diff adds (+) or removes (-), with its value plain or quoted.
_STATUS_LINE = re.compile(r"""^([+-])status:[ \t]*["']?([a-z_]+)["']?[ \t]*(?:#.*)?$""", re.M)
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
DEFAULT_RECORD = f"{cfgmod.EVIDENCE_DIR}/record.json"


def status_transitions(root: Path, rel: str, now: dt.datetime, current: str | None = None, ref: str | None = None) -> list[dict]:
    """Each status the Spec held, oldest first: the status, when it began, the commit and author that set it, and how
    long it lasted (to the next one, or to `now`). A Spec committed with no status is a draft. `current` is the status
    in the working tree; when it differs from the last committed one, it ends the list as uncommitted. `ref`: the
    history up to that commit, not HEAD's."""
    # Each commit is NUL, its id, time, and author each ended by NUL, then its patch. No field and no text patch holds a
    # NUL (git shows a file holding one as binary), so an author name or a Spec line cannot start a commit of its own.
    out = git.run(
        ["log", "--reverse", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=%x00%H%x00%cI%x00%an%x00", *([ref] if ref else []), "--", rel],
        str(root),
        check=False,
    )
    tokens = out.split("\0")[1:]
    held: list[dict] = []
    status: str | None = None
    for i in range(0, len(tokens) - 3, 4):
        sha, when, author, diff = tokens[i : i + 4]
        if not _SHA.fullmatch(sha):
            break  # out of step: stop rather than read a patch as a commit
        added = [m.group(2) for m in _STATUS_LINE.finditer(diff) if m.group(1) == "+"]
        removed = [m for m in _STATUS_LINE.finditer(diff) if m.group(1) == "-"]
        new = added[-1] if added else ("draft" if status is None or removed else status)
        if new != status:
            held.append({"status": new, "since": when, "commit": sha, "by": author})
            status = new
    if current and current != status:
        held.append({"status": current, "since": None, "commit": None, "by": None, "uncommitted": True})
    for i, t in enumerate(held):
        start = parse_time(t["since"])
        end = (parse_time(held[i + 1]["since"]) if i + 1 < len(held) else None) or now  # an uncommitted change has no time yet
        if start and end:
            t["minutes"] = max(0, int((end - start).total_seconds() // 60))
    return held


def _pathspecs(rel: str, data: dict) -> list[str]:
    """The Spec, and its Tasks' scope, test files, and design files, as git pathspecs."""
    globs = [g for t in data.get("tasks", []) or [] if isinstance(t, dict) for g in t.get("scope", []) or []]
    globs += spec_file.frozen_paths(data)
    return [rel] + [f":(glob){g}**" if g.endswith("/") else f":(glob){g}" for g in dict.fromkeys(globs)]


def commits(root: Path, rel: str, data: dict) -> list[dict]:
    """The commits touching the Spec or its scope, newest first (at most MAX_COMMITS), with their Assisted-by trailers."""
    try:
        records = git.log_fields([f"-n{MAX_COMMITS}", "--", *_pathspecs(rel, data)], ["%H", "%cI", "%an"], str(root), check=False)
        bodies = git.messages([r[0] for r in records], str(root))
    except git.GitError:
        return []
    return [
        {"sha": sha, "at": when, "author": author, "assisted_by": [t.strip() for t in cfgmod.extract_trailers(bodies.get(sha, "")) if t.strip()]}
        for sha, when, author in records
    ]


def approvals(root: Path, sid: str, shas: set[str], records: list[Path], rel: str) -> list[dict]:
    """Spec approvals naming this Spec and Merge approvals of one of its commits on the decision records, then the
    approvals and decision each gate record for this Spec carries."""
    out: list[dict] = []
    try:
        reviews, comments, _ = decision_records.load_local_approvals(str(root))
    except git.GitError:
        reviews, comments = [], []
    for c in comments:
        words = str(c.get("body", "")).split()
        if words[:3] == ["/aidd", "approve-spec", sid]:
            out.append(
                {
                    "kind": "spec_approval",
                    "by": c.get("user"),
                    "at": c.get("created_at"),
                    # A line from before approvals named the commit (`ID <hash> <commit>`) names no commit here.
                    "commit": words[3] if len(words) > 3 and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", words[3]) else None,
                    "signed": bool(c.get("verified")),
                    "source": decision_records.DECISIONS_REF,
                }
            )
    for r in reviews:
        if r.get("commit_sha") in shas:
            out.append(
                {
                    "kind": "merge_approval",
                    "by": r.get("user"),
                    "at": r.get("submitted_at"),
                    "commit": r.get("commit_sha"),
                    "signed": bool(r.get("verified")),
                    "source": decision_records.DECISIONS_REF,
                }
            )
    for path in records:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or (rec.get("spec_id") != sid and rec.get("spec") != rel):
            continue
        out.append(
            {
                "kind": "gate_record",
                "decision": rec.get("decision"),
                "head_sha": rec.get("head_sha"),
                "spec_approved_by": rec.get("spec_approved_by") or [],
                "approved_by": rec.get("approved_by") or [],
                "source": path.as_posix(),
            }
        )
    return out


def build_spec_history(root: Path, spec: str, records: list[str] | None = None, now: dt.datetime | None = None) -> dict:
    """The log of one Spec, by repo path (specs/SPEC-1.md) or id."""
    now = now or dt.datetime.now(dt.UTC)
    rel = spec
    if not (root / rel).is_file() and not rel.endswith(".md"):
        from aidd import config

        rel = globs.under(config.load_file(config.CONFIG_PATH, str(root)).specs_dir, f"{spec}.md")
    path = root / rel
    text = path.read_text(encoding="utf-8") if path.is_file() else git.show("HEAD", rel, str(root))
    if text is None:
        raise ValueError(f"{spec}: no such Spec in the working tree or at HEAD")
    data, _ = documents.split_front_matter(text, rel)
    if data.get("kind") != "spec":
        raise ValueError(f"{rel} is a {data.get('kind')}, not a Spec")
    sid = str(data.get("id", rel))
    held = status_transitions(root, rel, now, str(data.get("status") or "draft"))
    touched = commits(root, rel, data)
    files = [root / r for r in records or []]
    if not records and (root / DEFAULT_RECORD).is_file():
        files = [root / DEFAULT_RECORD]
    from aidd.workitems import derived_status, repo_reads

    cfg = repo_reads.config_at(root)
    derived = derived_status.Observer(root, cfg).working_tree(cfg.specs_dir if cfg else "specs", [(rel, data, text)]).get(sid, "draft")
    return {
        "spec": rel,
        "id": sid,
        "status": derived,
        "stored_status": data.get("status"),
        "transitions": held,
        "approvals": approvals(root, sid, {c["sha"] for c in touched}, files, rel),
        "commits": touched,
        "assisted_by": sorted({a for c in touched for a in c["assisted_by"]}),
    }


def duration(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    if minutes < 120:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // (24 * 60)} d"


def spec_history_markdown(log: dict) -> str:
    stored = log.get("stored_status")
    cache = f" (the stored status says `{stored}`)" if stored and stored != log["status"] else ""
    lines = [f"# {log['id']} ({log['spec']})", "", f"Status now: `{log['status']}`, derived{cache}.", "", "## Stored status", ""]
    lines += ["| Status | Since | Time in state | Commit | By |", "| --- | --- | --- | --- | --- |"]
    for t in log["transitions"]:
        commit = (t["commit"] or "")[:12] or "uncommitted"
        lines.append(f"| `{t['status']}` | {t['since'] or '-'} | {duration(t.get('minutes'))} | {commit} | {t['by'] or '-'} |")
    lines += ["", "## Approvals", ""]
    if not log["approvals"]:
        lines.append("None recorded locally (a platform's reviews are on the PR/MR).")
    for a in log["approvals"]:
        if a["kind"] == "gate_record":
            who = ", ".join(a["spec_approved_by"] + a["approved_by"]) or "no approvals"
            lines.append(f"- gate record {a['source']}: {a['decision']} on {str(a['head_sha'] or '')[:12]} ({who})")
        else:
            what = "Spec approval" if a["kind"] == "spec_approval" else f"Merge approval of {str(a['commit'])[:12]}"
            lines.append(f"- {what} by {a['by']} at {a['at']} ({'signed' if a['signed'] else 'unsigned'})")
    lines += ["", f"## Commits touching its scope ({len(log['commits'])})", ""]
    lines += [f"Assisted-by: {', '.join(log['assisted_by']) or 'none'}.", ""]
    if log["commits"]:
        lines += ["| Commit | When | Author | Assisted-by |", "| --- | --- | --- | --- |"]
        lines += [f"| {c['sha'][:12]} | {c['at']} | {c['author']} | {', '.join(c['assisted_by']) or '-'} |" for c in log["commits"]]
    return "\n".join(lines) + "\n"
