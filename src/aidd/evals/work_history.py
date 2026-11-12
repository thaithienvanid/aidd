"""The work history reader: baselines and signals about how a repository's work went, read from git and its files with no model.

It reads commits and their `Assisted-by` trailers, the Specs' status and `approved_at`, the records, and the handoff
notes in each Spec's committed history. The stall reading (work_stall) places each Spec at its furthest step. It starts no agent and writes nothing. Each measure says how many cases it
rests on (`n`) and whether that is `enough` to read (MIN_SAMPLE), so a thin history says "too little data" and never a
number that looks firm.

What git and files cannot tell is said, not guessed. A decision record holds the time of the answer and not of the ask,
so the wait for a decision is read only for Spec approval (a Spec's newest `ready` commit before its `approved_at`).
`aidd test` writes no record, so runs per head count only the workflow runs an agent reported with a head. A step's
harness and model are those its handoff note's `by` names, and a note without `by` takes those of the commit that
posted it. Each harness counts under one spelling, its id (`workitems.assisted_by_spelling`).
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from aidd import config, records, workitems
from aidd.evals import work_stall
from aidd.kernel import documents, git, regular_files

# The fewest cases a rate or an average rests on before it reads as a baseline.
MIN_SAMPLE = 5
# The most commits it reads, and the most versions of one Spec it reads for handoff notes (the newest ones).
MAX_COMMITS = 5000
MAX_VERSIONS = 200
# A gap between two commits on one change longer than this counts as waiting, not working. A proxy: git cannot see queues.
IDLE_SECONDS = 4 * 3600
# The steps whose `next_role: developer` sends the work back.
CHECK_STEPS = ("verifier", "reviewer")
# The one risk action whose report can hold a run of a workflow, with the head it ran on.
RUN_ACTION = "workflow.run"
STEP_ATTRIBUTION = (
    "Each step's harness and model are those its note's `by` names, and a person's `by` counts as `person` and their identity. "
    "A note without `by` takes those of the commit that posted it, "
    "usually the lead's, not the role's own."
)

_REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,64})")
_TOKENS = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?\s*(?:tokens?|tok)\b")
_COST = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_READY = re.compile(r"^status: ready\s*$", re.M)
UNMARKED = "unmarked"
# The harness a step counts under when a person, not an agent, wrote its note.
PERSON = "person"
# Each baseline's plain name and its unit.
LABELS = {
    "flow_efficiency": ("share of time working, not waiting", "share"),
    "suite_runs_per_head": ("reported workflow runs per head", "runs per head"),
    "decisions_per_change": ("decisions per change", "decisions per Spec"),
    "decision_wait": ("wait for Spec approval", "hours"),
}


@dataclass
class Commit:
    sha: str
    at: int
    message: str
    harness: str = UNMARKED
    model: str = UNMARKED


@dataclass
class Note:
    next_role: str
    spend: str
    harness: str
    model: str
    named: bool = False  # the harness and model come from the note's own `by`, not from its commit


@dataclass
class Row:
    """One role step as one harness and model did it."""

    step: str
    harness: str
    model: str
    notes: int = 0
    to_verify: int = 0
    rejected_at_verify: int = 0
    sent_back: int = 0
    reworked: int = 0
    spend_known: int = 0
    tokens: float = 0
    cost: float = 0


def harness_and_model(message: str) -> tuple[str, str]:
    """The first `Assisted-by: <harness>/<model>` value of a message as (harness, model), each harness under its id
    whatever its spelling; (unmarked, unmarked) without one."""
    values = workitems.assisted_by_values(message)
    return _split(values[0]) if values else (UNMARKED, UNMARKED)


def _split(value: str) -> tuple[str, str]:
    harness, _, model = workitems.assisted_by_spelling(value).partition("/")
    return harness or UNMARKED, model or UNMARKED


def parse_spend(text: str) -> tuple[float | None, float | None]:
    """(tokens, cost in dollars) a Spend line gives, each None when the line does not say it (`unknown` says neither)."""
    tokens = cost = None
    if m := _TOKENS.search(text):
        tokens = float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
    if m := _COST.search(text):
        cost = float(m.group(1))
    return tokens, cost


def _read_commits(root: Path) -> tuple[list[Commit], bool]:
    """The commits of HEAD, oldest first, and whether the history was longer than MAX_COMMITS. A commit's time is its
    author time, which a rebase or a squash keeps."""
    try:
        rows = git.log_fields([f"-{MAX_COMMITS + 1}"], ["%H", "%at"], str(root), check=False)
        bodies = git.messages([r[0] for r in rows], str(root))
    except (git.GitError, OSError):
        return [], False
    commits = []
    for sha, stamp in rows:
        message = bodies.get(sha, "")
        harness, model = harness_and_model(message)
        commits.append(Commit(sha, int(stamp), message, harness, model))
    return commits[:MAX_COMMITS][::-1], len(commits) > MAX_COMMITS


def _enough(n: int) -> bool:
    return n >= MIN_SAMPLE


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _measure(name: str, value: float | None, n: int, says: str, **extra: object) -> dict:
    """A baseline: its plain name, value, the cases it rests on, whether that is enough to read, and one plain sentence."""
    ok = _enough(n) and value is not None
    return {
        "label": LABELS[name][0],
        "value": round(value, 3) if ok and value is not None else None,
        "unit": LABELS[name][1],
        "n": n,
        "enough": ok,
        "says": says if ok else f"too little data: {says}",
        **extra,
    }


def _efficiency(times: list[int]) -> float | None:
    """The share of the span from the first to the last commit that lies in gaps of IDLE_SECONDS or less."""
    times = sorted(times)
    span = times[-1] - times[0] if times else 0
    if len(times) < 2 or span <= 0:
        return None
    return sum(g for g in (b - a for a, b in zip(times, times[1:], strict=False)) if g <= IDLE_SECONDS) / span


def _spec_items(root: Path) -> list[dict]:
    try:
        answer = workitems.open_work(root, workitems.config_at(root), include_done=True)
    except (OSError, ValueError):
        return []
    return [i for i in answer["items"] if i.get("type") == "spec"]


def flow_efficiency(commits: list[Commit], items: list[dict]) -> dict:
    """Per Spec: the commits that name it, and the share of their span spent in short gaps; the median across Specs."""
    known = {str(i["id"]) for i in items}
    times: dict[str, list[int]] = defaultdict(list)
    for c in commits:
        for item_id in workitems.work_ids_in(c.message, known):
            times[item_id].append(c.at)
    per = [v for t in times.values() if (v := _efficiency(t)) is not None]
    stream = _efficiency([c.at for c in commits])
    says = f"{_plural(len(per), 'Spec')} with two commits or more naming them (the median share of time in gaps of {IDLE_SECONDS // 3600} hours or less)"
    if stream is not None:
        says += f"; the whole history as one stream gives {stream:.2f}"
    return _measure("flow_efficiency", statistics.median(per) if per else None, len(per), says, stream=None if stream is None else round(stream, 3))


def _ready_before(root: Path, path: str, approved: int) -> int | None:
    """When the Spec file last stored `status: ready` at or before `approved`: its newest commit that has that line."""
    try:
        for sha, stamp in git.log_fields(["-G^status: ready", "--", path], ["%H", "%at"], str(root), check=False):
            if int(stamp) <= approved and _READY.search(git.show(sha, path, str(root)) or ""):
                return int(stamp)
    except (git.GitError, OSError):
        pass
    return None


def _approved_at(root: Path, path: str) -> int | None:
    try:
        data, _ = documents.split_front_matter(regular_files.repository_text(root, path, documents.MAX_DOCUMENT_BYTES) or "", path)
        return int(dt.datetime.fromisoformat(str(data["approved_at"])).timestamp())
    except (OSError, documents.DocumentError, KeyError, ValueError, TypeError):
        return None


def decision_wait(root: Path, items: list[dict]) -> dict:
    """The hours from a Spec's newest `ready` commit before its `approved_at` to that `approved_at`, the median."""
    hours = []
    for item in items:
        approved = _approved_at(root, str(item["path"]))
        ready = None if approved is None else _ready_before(root, str(item["path"]), approved)
        if ready is not None and approved is not None:
            hours.append((approved - ready) / 3600)
    says = (
        f"{_plural(len(hours), 'Spec')} with a `ready` commit and an `approved_at` (the median hours between them). "
        "A decision record holds the time of the answer only, so the wait for any other ask is not on file"
    )
    return _measure("decision_wait", statistics.median(hours) if hours else None, len(hours), says)


def decisions_per_change(found: list[dict], items: list[dict]) -> dict:
    """Decision records that name a Spec past draft, per such Spec."""
    changes = {str(i["id"]) for i in items if i["status"] != "draft"}
    decisions = [r for r in found if r.get("type") == "decision"]
    named = [r for r in decisions if r.get("subject") in changes]
    says = f"{_plural(len(named), 'decision')} name {_plural(len(changes), 'Spec')} past draft ({len(decisions) - len(named)} of {len(decisions)} decisions name no such Spec)"
    return _measure("decisions_per_change", len(named) / len(changes) if changes else None, len(changes), says)


def suite_runs_per_head(found: list[dict]) -> dict:
    """Reports of a workflow run that name a head, counted per head. `aidd test` writes no record, so a suite run counts
    only when an agent reported it as a workflow run."""
    heads: Counter[str] = Counter()
    for r in found:
        data: dict = r["data"]
        covers: dict = data["covers"] if isinstance(data.get("covers"), dict) else {}
        if r.get("type") == "report" and data.get("action") == RUN_ACTION and covers.get("head"):
            heads[str(covers["head"])] += 1
    says = (
        f"{_plural(sum(heads.values()), 'reported workflow run')} on {_plural(len(heads), 'head')} (the mean per head). "
        "`aidd test` writes no record, so a suite run no one reported is not counted"
    )
    return _measure("suite_runs_per_head", sum(heads.values()) / len(heads) if heads else None, len(heads), says, most=max(heads.values(), default=0))


def _versions(root: Path, path: str) -> tuple[list[tuple[str, str]], bool]:
    """(commit, text) of the newest MAX_VERSIONS committed versions of a file, oldest first, then the working copy as
    ("", text); and whether the file has more versions than that."""
    out: list[tuple[str, str]] = []
    capped = False
    try:
        rows = git.log_fields(["--", path], ["%H", "%at"], str(root), check=False)
        capped = len(rows) > MAX_VERSIONS
        for sha, _ in rows[:MAX_VERSIONS][::-1]:
            if (text := git.show(sha, path, str(root))) is not None:
                out.append((sha, text))
    except (git.GitError, OSError):
        pass
    try:
        if (text := regular_files.repository_text(root, path, documents.MAX_DOCUMENT_BYTES)) is not None:
            out.append(("", text))
    except OSError:
        pass
    return out, capped


def _notes(root: Path, path: str, by_sha: dict[str, Commit]) -> tuple[list[Note], int, bool]:
    """A Spec's handoff notes in the order they first appeared in its history, how many blocks did not parse, and
    whether older versions of the file were not read."""
    seen: set[str] = set()
    notes: list[Note] = []
    bad = 0
    versions, capped = _versions(root, path)
    for sha, text in versions:
        for raw in workitems.HANDOFF_FENCE.findall(text):
            if raw in seen:
                continue
            seen.add(raw)
            try:
                data = documents.parse_yaml(raw, "aidd-handoff block")
            except documents.DocumentError:
                bad += 1
                continue
            commit = by_sha.get(sha)
            by = documents.one_line(data["by"], 200).strip() if isinstance(data.get("by"), str) else ""
            named = bool(by)
            if by.startswith("agent:"):
                harness, model = _split(by)
            elif by and not config.is_agent(by):  # a person wrote the note: their step counts under them, never under the commit's agent
                harness, model = PERSON, by
            else:
                harness, model = (commit.harness, commit.model) if commit else (UNMARKED, UNMARKED)
            notes.append(Note(str(data.get("next_role") or ""), str(data.get("spend") or ""), harness, model, named))
    return notes, bad, capped


def _add_chain(rows: dict[tuple[str, str, str], Row], notes: list[Note]) -> None:
    """Count one Spec's chain. A note's step is the role the note before it handed to; the first note's step is `first`."""
    for i, note in enumerate(notes):
        writer = notes[i - 1].next_role if i else "first"
        row = rows.setdefault((writer, note.harness, note.model), Row(writer, note.harness, note.model))
        row.notes += 1
        tokens, cost = parse_spend(note.spend)
        row.spend_known += tokens is not None or cost is not None
        row.tokens += tokens or 0
        row.cost += cost or 0
        later = notes[i + 1] if i + 1 < len(notes) else None
        if note.next_role == "verifier":
            row.to_verify += 1
            row.rejected_at_verify += later is not None and later.next_role == "developer"
        if writer in CHECK_STEPS and note.next_role == "developer":
            row.sent_back += 1
        if writer == "developer" and i > 1 and notes[i - 2].next_role in CHECK_STEPS and notes[i - 1].next_role == "developer":
            row.reworked += 1


def _share(count: int, n: int) -> float | None:
    """`count` of `n`, or None when `n` is under MIN_SAMPLE (too few cases to read a share)."""
    return round(count / n, 3) if _enough(n) else None


def _row_text(row: Row) -> dict:
    """A row as JSON. A checker step (verifier, reviewer) has the share of its notes it sent back. A step that hands to
    the verifier has the share of those handoffs the verifier sent back to the developer. Each is None below MIN_SAMPLE."""
    is_check = row.step in CHECK_STEPS
    return {
        "step": row.step,
        "harness": row.harness,
        "model": row.model,
        "notes": row.notes,
        "sent_back": row.sent_back,
        "sent_back_share": _share(row.sent_back, row.notes) if is_check else None,
        "handed_to_verify": row.to_verify,
        "rejected_at_verify": row.rejected_at_verify,
        "rejected_at_verify_share": _share(row.rejected_at_verify, row.to_verify),
        "rework_loops": row.reworked,
        "spend_noted": row.spend_known,
        "tokens": int(row.tokens),
        "cost_dollars": round(row.cost, 2),
    }


def model_rows(commits: list[Commit]) -> list[dict]:
    """Per harness and model: the commits it marked, and how many a later commit reverted."""
    reverted = {m for c in commits for m in _REVERTS.findall(c.message)}
    out: dict[tuple[str, str], dict] = {}
    for c in commits:
        row = out.setdefault((c.harness, c.model), {"harness": c.harness, "model": c.model, "commits": 0, "reverted": 0})
        row["commits"] += 1
        row["reverted"] += any(c.sha.startswith(r) for r in reverted)
    for row in out.values():
        row["revert_rate"] = _share(row["reverted"], row["commits"])
    return sorted(out.values(), key=lambda r: (-r["commits"], r["harness"], r["model"]))


def read_work_history(root: Path) -> dict:
    """The baselines and signals for the repository at `root` (the shape `work_history_text` prints)."""
    commits, truncated = _read_commits(root)
    items = _spec_items(root)
    try:
        found, _ = records.read_records(str(root))
    except (git.GitError, OSError, ValueError):
        found = []
    by_sha = {c.sha: c for c in commits}
    rows: dict[tuple[str, str, str], Row] = {}
    bad = capped_specs = named = noted = 0
    for item in items:
        notes, skipped, capped = _notes(root, str(item["path"]), by_sha)
        bad += skipped
        capped_specs += capped
        named += sum(n.named for n in notes)
        noted += len(notes)
        _add_chain(rows, notes)
    return {
        "root": str(root),
        "commits": {
            "count": len(commits),
            "unmarked": sum(c.harness == UNMARKED for c in commits),
            "truncated": truncated,
            "first": commits[0].at if commits else None,
            "last": commits[-1].at if commits else None,
        },
        "specs": dict(Counter(str(i["status"]) for i in items)),
        "records": len(found),
        "baselines": {
            "flow_efficiency": flow_efficiency(commits, items),
            "suite_runs_per_head": suite_runs_per_head(found),
            "decisions_per_change": decisions_per_change(found, items),
            "decision_wait": decision_wait(root, items),
        },
        "stall": work_stall.read_stall(root),
        "step_attribution": STEP_ATTRIBUTION,
        "notes_named_by": {"named": named, "notes": noted},
        "steps": sorted((_row_text(r) for r in rows.values()), key=lambda r: (r["step"], r["harness"], r["model"])),
        "models": model_rows(commits),
        "unreadable_notes": bad,
        "capped_specs": capped_specs,
    }


def _day(stamp: object) -> str:
    return dt.datetime.fromtimestamp(int(stamp), dt.UTC).strftime("%Y-%m-%d") if isinstance(stamp, int) else "-"


def _share_text(label: str, count: int, n: int, share: float | None) -> str:
    return f"{label} {count} of {n} ({'share ' + str(share) if share is not None else 'too little data'})"


def _step_line(r: dict) -> str:
    parts = [f"{_plural(r['notes'], 'note')}"]
    if r["step"] in CHECK_STEPS:
        parts.append(_share_text("sent back", r["sent_back"], r["notes"], r["sent_back_share"]))
    if r["handed_to_verify"]:
        parts.append(_share_text("handed to Verify and sent back", r["rejected_at_verify"], r["handed_to_verify"], r["rejected_at_verify_share"]))
    parts.append(f"{_plural(r['rework_loops'], 'rework loop')}")
    parts.append(f"spend noted on {r['spend_noted']} ({r['tokens']} tokens, ${r['cost_dollars']})")
    return f"- {r['step']} / {r['harness']} / {r['model']}: " + ", ".join(parts)


def work_history_text(report: dict) -> str:
    """The reading as a person reads it: what the history holds, each baseline, then the steps and the models."""
    c = report["commits"]
    lines = [
        f"{report['root']}: {_plural(c['count'], 'commit')} ({_day(c['first'])} to {_day(c['last'])}), {c['count'] - c['unmarked']} with an Assisted-by trailer"
        + (f"; read the newest {MAX_COMMITS} only" if c["truncated"] else ""),
        f"Specs: {', '.join(f'{n} {s}' for s, n in sorted(report['specs'].items())) or 'none'}; records: {report['records']}",
        "",
        "Baselines, each marked enough or too little to read:",
    ]
    for m in report["baselines"].values():
        value = "-" if m["value"] is None else f"{m['value']} {m['unit']}"
        lines.append(f"- {m['label']}: {value} (n={m['n']}, need {MIN_SAMPLE}) {m['says']}")
    lines += ["", *work_stall.stall_text(report["stall"])]
    named = report["notes_named_by"]
    lines += ["", "Signals by role step, harness, and model. A step is the role the note before it handed to:", report["step_attribution"]]
    if named["notes"]:
        lines.append(f"{named['named']} of {_plural(named['notes'], 'note')} name their writer in `by`.")
    if not report["steps"]:
        lines.append("- none: no Spec holds a handoff note in its history, so there is no step to count")
    lines += [_step_line(r) for r in report["steps"]]
    lines += ["", "Reverts by harness and model (a revert has no role step on file):"]
    for r in report["models"]:
        share = "too little data" if r["revert_rate"] is None else f"share {r['revert_rate']}"
        lines.append(f"- {r['harness']} / {r['model']}: {_plural(r['commits'], 'commit')}, {r['reverted']} reverted ({share})")
    if not report["models"]:
        lines.append("- none: no commits")
    if report["unreadable_notes"]:
        lines.append(
            f"\n{_plural(report['unreadable_notes'], 'handoff block')} did not parse and {'was' if report['unreadable_notes'] == 1 else 'were'} skipped"
        )
    if report["capped_specs"]:
        lines.append(
            f"{_plural(report['capped_specs'], 'Spec')} had more than {MAX_VERSIONS} versions: only the newest {MAX_VERSIONS} were read for handoff notes"
        )
    return "\n".join(lines) + "\n"
