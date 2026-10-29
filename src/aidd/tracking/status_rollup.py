"""Status rollups for people: `aidd digest` (the team view and the client view) and `aidd release-notes`.

Both are rendered from what aidd already knows, deterministically and with no model: the Specs and their derived
statuses (`aidd list`), the commits on the checked-out branch since a date or a git ref, the gate events when they are
here (`aidd metrics`), the proposals' and Initiatives' milestones, risks, and reversed scope decisions, the handoff
notes' Needs, the overdue flags, outcomes, waivers, and runbook drills, and the post-launch feedback log. Nothing here is evidence, nothing approves, and
the gate never imports this module: a digest is a report a person sends, never a decision.

A Spec landed in the window when its derived status is landed or done (or rolled back) and a commit in the window
changed one of its Tasks' scopes (or, with no scope, added the Spec). Every list is sorted, so the same repository, the
same window, and the same day give the same bytes.

The client view's delivery status follows three written rules (`DELIVERY_STATUS_RULES`), never a judgment: red when a milestone is past
due or an item has been blocked for more than `blocked_days` days, amber when a risk or an ask of the client is open
(a late dependency is an ask), green otherwise. It never shows internal cost unless asked (`--include-cost`).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config, setup, workitems
from aidd.kernel import documents, git, timestamps
from aidd.kernel.text import md_cell, na
from aidd.kernel.timestamps import parse_time

SCHEMA_VERSION = "1"
ROLLUP_EVENTS_FILE = "aidd-events.jsonl"  # where `aidd gate --events` writes by convention; the digest reads it when it is here
MAX_COMMITS = 5000  # commits read for one window; a longer window is read in part, and says so
BLOCKED_DAYS = 5  # the client view turns red when an item has been blocked for more than this many days
MAX_INTENT_CHARS = 300  # characters of a Spec's Intent in a digest or release notes
DELIVERY_STATUS_RULES = (
    "Red: a milestone is past its due date and not done, or an item has been blocked for more than {days} days.",
    "Amber: not red, and a risk is open or something waits on the client.",
    "Green: neither: no milestone is late, nothing is blocked that long, and no risk or ask is open.",
)
# Keep a Changelog 1.1.0 (keepachangelog.com): the groups, in its order.
CHANGE_GROUPS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
# The group a Spec's type goes to; a `changelog:<group>` label overrides it, and a security fix is Security.
TYPE_GROUP = {"feat": "Added", "fix": "Fixed", "security": "Security"}
# Change types a product's users notice; `--audience users` shows only these (and a Spec labelled `audience:users`).
USER_TYPES = frozenset({"feat", "fix", "perf", "security"})
AUDIENCES = ("users", "developers")
INACTIVE_PROPOSAL = frozenset({"no_go", "rejected", "withdrawn"})
# An accepted proposal's milestones and RAID log moved to its Initiative (`aidd proposal convert`): read there, never twice.
DELIVERED_PROPOSAL = "accepted"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_CLIENT_ASK = re.compile(r"^\s*client\s*:\s*|\bclient\b", re.I)


# ---- the window ------------------------------------------------------------------------------------------------


@dataclass
class Window:
    """The commits on HEAD since a date or a git ref: each as {sha, date, subject, paths}, newest first."""

    since: str
    kind: str  # "date" or "ref"
    start: dt.date
    head: str
    commits: list[dict] = field(default_factory=list)
    truncated: bool = False

    def as_dict(self) -> dict:
        return {
            "since": self.since,
            "kind": self.kind,
            "start": self.start.isoformat(),
            "head": self.head[:12],
            "commits": len(self.commits),
            "truncated": self.truncated,
        }


DEFAULT_WINDOW_DAYS = 7  # the digest's window when no `--since` is given and no tag is reachable


def default_since(root: Path, today: dt.date | None = None) -> str:
    """The digest's window with no `--since`: since the last tag HEAD holds (the last release), else the last week."""
    tag = git.run(["describe", "--tags", "--abbrev=0", "HEAD"], str(root), check=False).strip()
    if tag and not tag.startswith("-"):
        return tag
    return ((today or dt.date.today()) - dt.timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()


def rollup_window(root: Path, since: str) -> Window:
    """The window `--since` names: an ISO date or time (commits at or after it), or a git ref such as a tag (the
    commits on HEAD that it does not hold)."""
    since = (since or "").strip()
    cwd = str(root)
    head = git.run(["rev-parse", "-q", "--verify", "HEAD^{commit}"], cwd, check=False).strip()
    if not since:
        raise ValueError("--since needs an ISO date (2026-09-01) or a git ref (a tag, such as v1.2.0)")
    if _DATE.match(since):
        start_t = parse_time(since)
        if start_t is None:
            raise ValueError(f"--since {since!r} is not an ISO date or time, such as 2026-09-01")
        kind, span = "date", ["HEAD"]
    else:
        sha = "" if since.startswith("-") else git.run(["rev-parse", "-q", "--verify", f"{since}^{{commit}}"], cwd, check=False).strip()
        if not sha:
            raise ValueError(f"--since {since!r} is neither an ISO date nor a git ref in this repository")
        start_t = parse_time(git.run(["log", "-1", "--format=%cI", sha, "--"], cwd, check=False).strip()) or dt.datetime.now(dt.UTC)
        kind, span = "ref", [f"{sha}..HEAD"]
    win = Window(since, kind, start_t.date(), head)
    if not head:
        return win
    raw = git.run(["log", f"--max-count={MAX_COMMITS + 1}", "--format=%x1e%H%x1f%cI%x1f%s", "--name-only", *span, "--"], cwd, check=False)
    for chunk in raw.split("\x1e"):
        if not chunk.strip():
            continue
        first, _, rest = chunk.partition("\n")
        parts = first.split("\x1f")
        if len(parts) < 3:
            continue
        when = parse_time(parts[1])
        if kind == "date" and (when is None or when < start_t):
            continue
        win.commits.append(
            {"sha": parts[0], "date": when.date().isoformat() if when else "", "subject": parts[2], "paths": [p for p in rest.splitlines() if p.strip()]}
        )
    if len(win.commits) > MAX_COMMITS:
        win.commits, win.truncated = win.commits[:MAX_COMMITS], True
    return win


# ---- reading the repository -----------------------------------------------------------------------------------


Objects = list[tuple[str, dict, str, str]]


def _objects(root: Path, cfg: config.Config) -> Objects:
    """(path, front matter, body, text) of every Spec, Epic, Initiative, and proposal in the working tree."""
    out = []
    for p in workitems.object_files(root, cfg.specs_dir) + workitems.object_files(root, cfg.proposals_dir):
        try:
            text = p.read_text(encoding="utf-8")
            data, body = documents.split_front_matter(text, p.as_posix())
        except (OSError, UnicodeDecodeError, documents.DocumentError):
            continue
        out.append((p.relative_to(root).as_posix(), data, body, text))
    return out


def intent(body: str) -> str:
    """The first paragraph of the Spec's Intent (else Problem, else Context), as plain text: no comments, no quote marks,
    no `Source:` line, never a TODO."""
    for name in ("Intent", "Problem", "Context"):
        text = documents._HTML_COMMENT.sub("", documents.markdown_section(body, name, fences=False))
        for para in re.split(r"\n[ \t]*\n", text):
            lines = [re.sub(r"^[ \t]*>[ \t]?", "", ln).strip() for ln in para.splitlines()]
            plain = " ".join(ln for ln in lines if ln and not ln.startswith(("Source:", "|", "#")))
            if plain and not plain.upper().startswith("TODO"):
                return plain if len(plain) <= MAX_INTENT_CHARS else plain[: MAX_INTENT_CHARS - 1].rstrip() + "…"
    return ""


def _scopes(data: dict) -> list[str]:
    return [str(s) for t in data.get("tasks") or [] if isinstance(t, dict) for s in t.get("scope") or [] if "TODO" not in str(s)]


def _touched(data: dict, rel: str, commits: list[dict]) -> list[dict]:
    """The window's commits that changed the Spec's scope, or, when it names none, added the Spec itself."""
    from aidd.kernel import globs

    scopes = _scopes(data)
    if scopes:
        return [c for c in commits if any(globs.match_any(scopes, p) for p in c["paths"])]
    return [c for c in commits if rel in c["paths"]]


def _flags(data: dict) -> list[dict]:
    return sorted(
        ({"name": str(f.get("name")), "default": str(f.get("default") or "off")} for f in data.get("flags") or [] if isinstance(f, dict) and f.get("name")),
        key=lambda f: f["name"],
    )


def _deprecations(data: dict) -> list[dict]:
    return sorted(
        (
            {"what": str(x["what"]), "sunset": str(x.get("sunset") or ""), "replacement": str(x.get("replacement") or "")}
            for x in data.get("deprecations") or []
            if isinstance(x, dict) and x.get("what")
        ),
        key=lambda x: (x["sunset"], x["what"]),
    )


def deprecation_calendar(objects: Objects, today: dt.date, statuses: dict[str, str]) -> list[dict]:
    """The client's deprecation calendar: each deprecation a landed Spec announced by `today` that no landed Spec has
    removed, by sunset, with `passed` once its sunset is behind. `statuses`: the derived status of each Spec, by id, so a
    draft's plans never reach the client."""
    return [
        {
            "id": str(d.get("id") or ""),
            "what": str(dep["what"]),
            "announced": str(dep.get("announced")),
            "sunset": str(dep.get("sunset")),
            "replacement": str(dep.get("replacement") or ""),
            "passed": str(dep.get("sunset")) < today.isoformat(),
        }
        for _, d, dep in workitems.deprecation_calendar([(rel, data) for rel, data, _, _ in objects], statuses, landed_only=True)
        if str(dep.get("announced", "9999")) <= today.isoformat()
    ]


def landed(root: Path, cfg: config.Config, win: Window, statuses: dict[str, str] | None = None) -> list[dict]:
    """The Specs that landed in the window, oldest first: derived status landed, done, or rolled back, and a commit in the
    window changed a Task's scope (or added the Spec when it names no scope)."""
    objects = _objects(root, cfg)
    if statuses is None:
        obs = workitems.Observer(root, cfg)
        statuses = obs.working_tree(cfg.specs_dir, [(rel, d, text) for rel, d, _, text in objects]) if objects else {}
    out = []
    for rel, data, body, _ in objects:
        if data.get("kind") != "spec" or not data.get("id"):
            continue
        status = statuses.get(str(data["id"]), "draft")
        if status not in ("landed", "done", "rolled_back"):
            continue
        hits = _touched(data, rel, win.commits)
        if not hits:
            continue
        risk = data.get("risk") or {}
        out.append(
            {
                "id": str(data["id"]),
                "title": str(data.get("title") or ""),
                "type": str(data.get("type") or "feat"),
                "status": status,
                "path": rel,
                "merged_on": max(c["date"] for c in hits),
                "intent": intent(body),
                "labels": sorted(str(x) for x in data.get("labels") or []),
                "dimensions": sorted(str(x) for x in risk.get("dimensions") or []),
                "flags": _flags(data),
                "removes_flags": sorted(str(x) for x in data.get("removes_flags") or []),
                "deprecations": _deprecations(data),
                "removes_deprecations": sorted(str(x) for x in data.get("removes_deprecations") or []),
            }
        )
    return sorted(out, key=lambda s: (s["merged_on"], s["id"]))


# ---- milestones, risks, asks ----------------------------------------------------------------------------------


def _active_sources(objects: Objects) -> list[tuple[str, dict]]:
    """Where the live milestones and RAID log are: each proposal still being decided, and every Initiative that is not
    cancelled. An accepted proposal is history: its delivery record is the Initiative's."""
    out = []
    for rel, data, _, _ in objects:
        kind = data.get("kind")
        if kind == "proposal" and workitems.proposal_status(data) not in INACTIVE_PROPOSAL | {DELIVERED_PROPOSAL}:
            out.append((rel, data))
        elif kind == "initiative" and data.get("status") != "cancelled":
            out.append((rel, data))
    return out


def milestones(objects: Objects, today: dt.date, landed: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """Every milestone of a live proposal or Initiative. One is done when a person recorded `reached_on`, or when every
    Spec its trigger names is in `landed`; it is late when its `due` date has passed and it is not done."""
    out = []
    for rel, data in _active_sources(objects):
        for m in data.get("milestones") or []:
            if not isinstance(m, dict):
                continue
            due = timestamps.parse_date(m.get("due") or "")
            specs = (m.get("trigger") or {}).get("specs") or []
            done = bool(m.get("reached_on")) or (bool(specs) and all(str(s) in landed for s in specs))
            out.append(
                {
                    "name": str(m.get("name") or m.get("id") or ""),
                    "source": str(data.get("id") or rel),
                    "due": due.isoformat() if due else None,
                    "status": "done" if done else "open",
                    "late": bool(due and due < today and not done),
                }
            )
    return sorted(out, key=lambda m: (m["due"] or "9999-12-31", m["source"], m["name"]))


def risks(objects: Objects) -> list[dict]:
    """The open risks and issues of the live RAID log: each `risks` and `issues` entry of a live proposal or Initiative
    whose status is `open` (resolved, accepted, and invalid are closed)."""
    out = []
    for rel, data in _active_sources(objects):
        for key in ("risks", "issues"):
            for r in data.get(key) or []:
                if not isinstance(r, dict) or r.get("status") != "open" or not str(r.get("text") or "").strip():
                    continue
                out.append(
                    {
                        "kind": key[:-1],
                        "id": str(r.get("id") or ""),
                        "source": str(data.get("id") or rel),
                        "text": str(r["text"]).strip(),
                        "likelihood": str(r.get("likelihood") or ""),
                        "impact": str(r.get("impact") or ""),
                    }
                )
    return sorted(out, key=lambda r: (r["source"], r["kind"], r["id"]))


def reversals(objects: Objects, start: dt.date, today: dt.date) -> list[dict]:
    """The scope decisions reversed in the window: each `decisions` entry of a live proposal or Initiative that names
    the entry it `replaces`, dated from `start` to `today`."""
    out = []
    for rel, data in _active_sources(objects):
        for d in data.get("decisions") or []:
            if not isinstance(d, dict) or not d.get("replaces"):
                continue
            on = timestamps.parse_date(d.get("decided_on") or "")
            if on is None or not start <= on <= today:
                continue
            out.append(
                {
                    "source": str(data.get("id") or rel),
                    "id": str(d.get("id") or ""),
                    "replaces": str(d["replaces"]),
                    "decision": str(d.get("decision") or "").strip(),
                    "by": str(d.get("by") or ""),
                    "decided_on": on.isoformat(),
                    "reason": str(d.get("reason") or "").strip(),
                }
            )
    return sorted(out, key=lambda r: (r["decided_on"], r["source"], r["id"]))


def client_asks(objects: Objects, needs: list[dict], today: dt.date) -> list[dict]:
    """What waits on the client: a proposal's question with no answer yet, an open dependency of a live proposal or
    Initiative whose `due` date has passed, and a handoff note's Needs item that starts with `client:` or names the
    client. A late dependency's text ends with its due date, so the reader sees why it is listed."""
    out = []
    for rel, data, _, _ in objects:
        if data.get("kind") != "proposal" or workitems.proposal_status(data) in INACTIVE_PROPOSAL:
            continue
        for q in data.get("questions") or []:
            if isinstance(q, dict) and q.get("question") and not str(q.get("answer") or "").strip():
                out.append({"source": str(data.get("id") or rel), "text": str(q["question"]).strip()})
    for rel, data in _active_sources(objects):
        for d in data.get("dependencies") or []:
            if not isinstance(d, dict) or d.get("status") != "open" or not str(d.get("text") or "").strip():
                continue
            due = timestamps.parse_date(d.get("due") or "")
            if due is not None and due < today:
                out.append({"source": str(data.get("id") or rel), "text": f"{str(d['text']).strip()} (due {due.isoformat()})"})
    for n in needs:
        if _CLIENT_ASK.search(n["text"]):
            out.append({"source": n["id"], "text": re.sub(r"^\s*client\s*:\s*", "", n["text"], flags=re.I)})
    return sorted(out, key=lambda a: (a["source"], a["text"]))


def delivery_status(late: list[dict], blocked: list[dict], open_risks: list[dict], asks: list[dict], blocked_days: int = BLOCKED_DAYS) -> dict:
    """The client view's status, by the three rules in DELIVERY_STATUS_RULES, with the reasons that decided it."""
    stuck = [b for b in blocked if b["days"] > blocked_days]
    if late or stuck:
        status = "red"
        reasons = [f"milestone {m['name']} ({m['source']}) was due {m['due']}" for m in late]
        reasons += [f"{b['id']} has been blocked for {b['days']} days" for b in stuck]
    elif open_risks or asks:
        status = "amber"
        reasons = [f"{len(open_risks)} open risk(s)"] if open_risks else []
        reasons += [f"{len(asks)} item(s) wait on the client"] if asks else []
    else:
        status = "green"
        reasons = ["no milestone is late, nothing is blocked for long, and no risk or ask is open"]
    return {"status": status, "reasons": reasons, "rules": [r.format(days=blocked_days) for r in DELIVERY_STATUS_RULES]}


# ---- feedback ----------------------------------------------------------------------------------------------------


FEEDBACK_COLUMNS = {
    "date": "date",
    "channel": "channel",
    "customer": "customer",
    "segment": "customer",
    "quote": "quote",
    "theme": "theme",
    "severity": "severity",
    "linked": "linked",
    "score": "score",
}


def _rows(text: str) -> list[dict]:
    """The rows of each table in `text` whose header has a Theme column, keyed by the column's first word."""
    text = documents._HTML_COMMENT.sub("", text)
    out: list[dict] = []
    header: list[str] | None = None
    for line in text.splitlines() + [""]:
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if header is None:
            keys = [FEEDBACK_COLUMNS.get(re.sub(r"[^a-z].*$", "", c.lower()), "") for c in cells]
            header = keys if "theme" in keys else []
            continue
        if not header or all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        out.append({k: v for k, v in zip(header, cells, strict=False) if k})
    return out


def feedback(root: Path, docs_dir: str, start: dt.date | None) -> dict:
    """The post-launch feedback log (`<docs>/feedback/*.md`, from `aidd new feedback`): the entries dated in the window,
    counted by theme and severity, with the Net Promoter Score when entries carry a 0-10 score."""
    themes: Counter = Counter()
    severity: Counter = Counter()
    scores: list[int] = []
    entries = undated = 0
    folder = root / docs_dir / "feedback"
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            rows = _rows(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        for r in rows:
            theme = " ".join(r.get("theme", "").split()).lower()
            if not theme or theme.startswith("todo"):
                continue
            when = timestamps.parse_date(r.get("date", ""))
            if when is None:
                undated += 1
                continue
            if start and when < start:
                continue
            entries += 1
            themes[theme] += 1
            sev = r.get("severity", "").strip().lower()
            if sev and not sev.startswith("todo"):
                severity[sev] += 1
            if re.fullmatch(r"(10|[0-9])", r.get("score", "").strip()):
                scores.append(int(r["score"].strip()))
    nps = None
    if scores:
        promoters, detractors = sum(1 for s in scores if s >= 9), sum(1 for s in scores if s <= 6)
        nps = round(100 * (promoters - detractors) / len(scores))
    return {
        "entries": entries,
        "undated": undated,
        "themes": [{"theme": t, "count": n} for t, n in sorted(themes.items(), key=lambda x: (-x[1], x[0]))],
        "severity": dict(sorted(severity.items())),
        "nps": nps,
        "scores": len(scores),
    }


# ---- the digest -------------------------------------------------------------------------------------------------


def _title(root: Path, step: dict, titles: dict[str, str]) -> str:
    if step.get("id") in titles:
        return titles[str(step["id"])]
    ref, where = step.get("branch"), step.get("where")
    text = git.show(ref, where, str(root)) if ref and where else None
    if text:
        try:
            data, _ = documents.split_front_matter(text, str(where))
            return str(data.get("title") or "")
        except documents.DocumentError:
            return ""
    return ""


def _blocked_days(root: Path, step: dict, today: dt.date) -> int:
    """Days since the blocked item last changed on its branch: when its blocker was written, or later."""
    where = step.get("where") or ""
    ref = step.get("branch") or "HEAD"
    when = parse_time(git.run(["log", "-1", "--format=%cI", ref, "--", where], str(root), check=False).strip()) if where else None
    return max((today - when.date()).days, 0) if when else 0


def _overdue(root: Path, cfg: config.Config, steps: list[dict], today: dt.date) -> dict:
    waivers = []
    for w in cfg.get("project", "waivers", default=[]) or []:
        until = timestamps.parse_date(w.get("until"))
        if until and (until - today).days <= 14:
            waivers.append({"rule": str(w.get("rule")), "until": until.isoformat(), "expired": until < today})
    runbooks = sorted(msg for level, msg in setup.runbook_checks(root, cfg, today) if level == "warn")
    return {
        "flags": sorted(s["what"] for s in steps if s.get("code") == "flag.overdue"),
        "deprecations": sorted(s["what"] for s in steps if s.get("code") == "deprecation.overdue"),
        "outcomes": sorted(s["what"] for s in steps if s.get("code") == "spec.outcome_due"),
        "waivers": sorted(waivers, key=lambda w: (w["until"], w["rule"])),
        "runbooks": runbooks,
    }


def _metrics(events: list[dict], cost_log: list[dict] | None, targets: dict) -> tuple[dict | None, dict | None]:
    from aidd.tracking import metrics

    if not events:
        return None, None
    s = metrics.summarize_events(events, None, targets)
    keep = ("changes", "throughput_per_week", "median_hours_to_pass", "first_pass_tests_rate", "open_waiting", "emergency_rate", "flow_efficiency")
    out = {k: s[k] for k in keep} | {
        "loop_speed": [{"name": r["name"], "value": r["value"], "met": r["met"]} for r in s["loop_speed"]],
        "dora": [{"name": r["name"], "value": r["value"], "met": r["met"]} for r in metrics.dora(events, None, targets)],
    }
    cost = metrics.cost_per_change(events, cost_log, targets, s["first_pass_share"]) if cost_log is not None else None
    return out, cost


OPEN_WORK = ("ready", "in_progress", "in_review")


def _by_id(item: dict) -> tuple[str, str]:
    return (str(item["id"]), str(item["what"]))


def status_digest(
    root: Path,
    since: str,
    *,
    client: bool = False,
    events: list[dict] | None = None,
    cost_log: list[dict] | None = None,
    include_cost: bool = False,
    blocked_days: int = BLOCKED_DAYS,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """The status rollup for the window: the team view by default, the client view with `client`."""
    from aidd.tracking import next_steps

    today = today or dt.date.today()
    cfg = config.load_file(config.CONFIG_PATH, str(root))
    win = rollup_window(root, since)
    objects = _objects(root, cfg)
    titles = {str(d["id"]): str(d.get("title") or "") for _, d, _, _ in objects if d.get("id")}
    steps = [s for s in next_steps.plan(root, today, next_steps.Filters(all=True), now) if s.get("code") not in ("nothing_open", "nothing_matches", "setup")]
    statuses = workitems.Observer(root, cfg).working_tree(cfg.specs_dir, [(rel, d, text) for rel, d, _, text in objects]) if objects else {}
    landed_specs = landed(root, cfg, win, statuses)
    blocked = [
        {"id": str(s.get("id") or ""), "title": _title(root, s, titles), "what": s["what"], "days": _blocked_days(root, s, today)}
        for s in steps
        if s.get("blocked")
    ]
    needs = []
    for s in steps:
        for n in workitems.needs(s.get("handoff"), s.get("status")):
            needs.append({"id": str(s.get("id") or ""), "text": n})
    open_risks = risks(objects)
    asks = client_asks(objects, needs, today)
    ms = milestones(objects, today, {sid for sid, s in statuses.items() if s in workitems.LANDED_STATUSES})
    progress = [
        {"id": str(s.get("id")), "title": _title(root, s, titles), "status": str(s.get("status")), "who": s["who"]}
        for s in steps
        if str(s.get("code", "")).startswith("spec.") and s.get("status") in OPEN_WORK and s.get("code") not in ("spec.needs", "spec.outcome_due")
    ]
    progress.sort(key=lambda p: (OPEN_WORK.index(p["status"]), p["id"]))
    events = events or []
    metrics_out, cost = _metrics(events, cost_log, cfg.get("targets", default={}) or {})
    head: dict = {"schema_version": SCHEMA_VERSION, "view": "client" if client else "team", "generated_on": today.isoformat(), "window": win.as_dict()}
    plain = [{k: s[k] for k in ("id", "title", "type", "merged_on", "intent")} for s in landed_specs]
    # What the team decided on its own (each Spec's handoff notes, `decided`), for the open work and what landed in
    # the window: the person reads it, and overrules any of it with a change order.
    reported = {str(s["id"]) for s in landed_specs} | {sid for sid, st in statuses.items() if st in OPEN_WORK or st == "draft"}
    team_made = [{"id": str(d.get("id")), "decision": x} for _, d, _, text in objects if str(d.get("id")) in reported for x in workitems.team_decisions(text)]
    if client:
        out = head | {
            "delivery_status": delivery_status([m for m in ms if m["late"]], blocked, open_risks, asks, blocked_days),
            "milestones": ms,
            "landed": plain,
            "asks": asks,
            "team_decisions": team_made,
            "deprecations": deprecation_calendar(objects, today, statuses),
            "next_steps": [{"id": p["id"], "title": p["title"], "status": p["status"]} for p in progress]
            + [
                {"id": m["source"], "title": f"milestone {m['name']}" + (f", due {m['due']}" if m["due"] else ""), "status": "milestone"}
                for m in ms
                if m["status"] != "done"
            ],
        }
        if include_cost and cost is not None:
            out["cost"] = cost
        return out
    waiting: dict[str, list[dict]] = {}
    for s in steps:
        if s.get("blocked") or s.get("code") in ("spec.done",):
            continue
        waiting.setdefault(str(s["who"]), []).append({"id": str(s.get("id") or ""), "what": s["what"]})
    for rows in waiting.values():
        rows.sort(key=_by_id)
    decisions = [
        {"id": str(s.get("id") or ""), "what": s["what"]}
        for s in steps
        if s.get("code") in ("spec.triage", "spec.needs") or str(s.get("code", "")).startswith("proposal.") or s.get("who") == workitems.COMMIT
    ]
    out = head | {
        "landed": landed_specs,
        "in_progress": progress,
        "waiting": [{"who": who, "items": rows} for who, rows in sorted(waiting.items())],
        "blocked": sorted(blocked, key=lambda b: (-b["days"], b["id"])),
        "decisions": sorted(decisions, key=lambda d: (d["id"], d["what"])),
        "team_decisions": team_made,
        "reversed": reversals(objects, win.start, today),
        "needs": sorted(needs, key=lambda n: (n["id"], n["text"])),
        "risks": open_risks,
        "milestones": ms,
        "overdue": _overdue(root, cfg, steps, today),
        "feedback": feedback(root, cfg.docs_dir, win.start),
        "metrics": metrics_out,
    }
    if cost is not None:
        out["cost"] = cost
    return out


# ---- Markdown ---------------------------------------------------------------------------------------------------


def deprecation_line(entry: dict) -> str:
    """One entry of the deprecation calendar, in the client's words."""
    when = f"stopped working on {entry['sunset']}" if entry["passed"] else f"stops working on {entry['sunset']}"
    return f"{entry['what']} {when} (announced {entry['announced']}); use {entry['replacement']}"


def _window_line(w: dict) -> str:
    what = f"since {w['since']}" + (f" ({w['start']})" if w["kind"] == "ref" else "")
    return f"{what}, up to {w['head'] or 'no commit'}: {w['commits']} commit(s)" + (
        " (read in part: the window is longer than aidd reads)" if w["truncated"] else ""
    )


def _no_html(text: str) -> str:
    """Markdown whose repository text (titles, intents, asks, written mostly by agents) cannot open an HTML tag or
    comment where the Markdown is rendered: every angle bracket becomes an entity."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def digest_markdown(d: dict) -> str:
    """The digest as Markdown, for a chat message, an email, or a pull request comment."""
    lines = [f"# {'Client status' if d['view'] == 'client' else 'Team digest'}, {d['generated_on']}", "", _window_line(d["window"]), ""]
    if d["view"] == "client":
        r = d["delivery_status"]
        lines += [f"**Status: {r['status'].upper()}**: " + "; ".join(r["reasons"]) + ".", ""]
        lines += ["## Milestones", ""] + (
            [f"- {m['name']}: {'due ' + m['due'] if m['due'] else 'no date'}, {m['status']}{' (late)' if m['late'] else ''}" for m in d["milestones"]]
            or ["- none listed"]
        )
        lines += ["", "## What landed", ""] + (
            [f"- **{s['title']}**" + (f": {s['intent']}" if s["intent"] else "") for s in d["landed"]] or ["- nothing in this window"]
        )
        lines += ["", "## What we need from you", ""] + ([f"- {a['text']} ({a['source']})" for a in d["asks"]] or ["- nothing right now"])
        if d.get("deprecations"):
            lines += ["", "## Deprecations", "", *[f"- {deprecation_line(x)}" for x in d["deprecations"]]]
        if d.get("team_decisions"):
            lines += ["", "## What we decided for you", "", *[f"- {t['id']}: {t['decision']}" for t in d["team_decisions"]]]
            lines += ["", "Any of these is yours to change: say so, and it becomes a change order."]
        lines += ["", "## Next steps", ""] + ([f"- {n['title'] or n['id']} ({n['status'].replace('_', ' ')})" for n in d["next_steps"]] or ["- none planned"])
        if "cost" in d:
            lines += ["", "## Cost", "", *[f"- {cur}: {x['total']} over {x['changes']} change(s)" for cur, x in d["cost"]["currencies"].items()]]
        lines += ["", "How the status is set:", *[f"- {rule}" for rule in r["rules"]]]
        return _no_html("\n".join(lines) + "\n")
    lines += ["## Landed", ""] + ([f"- {s['id']} {s['title']} ({s['type']}, merged {s['merged_on']})" for s in d["landed"]] or ["- nothing in this window"])
    lines += ["", "## In progress", ""] + (
        [f"- {p['id']} {p['title']}: {p['status'].replace('_', ' ')}, with {p['who']}" for p in d["in_progress"]] or ["- nothing"]
    )
    lines += ["", "## Waiting on", ""]
    for w in d["waiting"]:
        lines.append(
            f"- **{w['who']}** ({len(w['items'])}): "
            + "; ".join(f"{i['what']}" for i in w["items"][:5])
            + (f"; and {len(w['items']) - 5} more" if len(w["items"]) > 5 else "")
        )
    if not d["waiting"]:
        lines.append("- nobody")
    lines += ["", "## Blocked", ""] + ([f"- {b['id']} for {b['days']} day(s): {b['what']}" for b in d["blocked"]] or ["- nothing"])
    lines += ["", "## Decisions and Needs", ""] + ([f"- {x['what']}" for x in d["decisions"]] or ["- none open"])
    lines += ["", "## Decisions the team made", ""] + ([f"- {t['id']}: {t['decision']}" for t in d.get("team_decisions", [])] or ["- none recorded"])
    if d["reversed"]:
        lines += ["", "## Scope decisions reversed", ""] + [
            f"- {r['source']} {r['id']} replaces {r['replaces']} ({r['by']}, {r['decided_on']}): {r['decision']}"
            + (f". Why: {r['reason']}" if r["reason"] else "")
            for r in d["reversed"]
        ]
    lines += ["", "## Risks", ""] + (
        [f"- {r['source']} {r['id']}: {r['text']}" + (f" (likelihood {r['likelihood']}, impact {r['impact']})" if r["likelihood"] else "") for r in d["risks"]]
        or ["- none open"]
    )
    if d["milestones"]:
        lines += ["", "## Milestones", ""] + [
            f"- {m['name']} ({m['source']}): {'due ' + m['due'] if m['due'] else 'no date'}, {m['status']}{' (late)' if m['late'] else ''}"
            for m in d["milestones"]
        ]
    o = d["overdue"]
    overdue = (
        o["flags"]
        + o["deprecations"]
        + o["outcomes"]
        + [f"waiver of {w['rule']} {'expired' if w['expired'] else 'expires'} {w['until']}" for w in o["waivers"]]
        + o["runbooks"]
    )
    lines += ["", "## Overdue", ""] + ([f"- {x}" for x in overdue] or ["- nothing"])
    f = d["feedback"]
    lines += ["", "## Feedback", ""]
    if f["entries"]:
        lines.append(f"- {f['entries']} entr{'y' if f['entries'] == 1 else 'ies'}: " + ", ".join(f"{t['theme']} {t['count']}" for t in f["themes"]))
        if f["severity"]:
            lines.append("- by severity: " + ", ".join(f"{k} {v}" for k, v in f["severity"].items()))
        if f["nps"] is not None:
            lines.append(f"- NPS {f['nps']} from {f['scores']} score(s)")
    else:
        lines.append("- none logged in this window (`aidd new feedback`)")
    lines += ["", "## Metrics", ""]
    m = d["metrics"]
    if m:
        lines += ["| Measure | Value |", "| --- | --- |"]
        lines += [
            f"| {md_cell(k.replace('_', ' '))} | {na(m[k])} |"
            for k in ("changes", "throughput_per_week", "median_hours_to_pass", "first_pass_tests_rate", "open_waiting")
        ]
        lines += [f"| {md_cell(r['name'])} | {na(r['value'])} |" for r in m["loop_speed"] + m["dora"]]
    else:
        lines.append("- no gate events in this window (`--events`, from `aidd gate --events`)")
    if "cost" in d:
        lines += ["", "## Cost (display only)", "", *[f"- {cur}: {x['total']} over {x['changes']} change(s)" for cur, x in d["cost"]["currencies"].items()]]
    return _no_html("\n".join(lines) + "\n")


# ---- release notes ----------------------------------------------------------------------------------------------


def change_group(spec: dict) -> str:
    """The Keep a Changelog group of a landed Spec: a `changelog:<group>` label, else Security for a security type or
    a fix with the security dimension, else by type (feat Added, fix Fixed), else Changed."""
    for label in spec.get("labels") or []:
        if label.startswith("changelog:") and label.split(":", 1)[1].capitalize() in CHANGE_GROUPS:
            return label.split(":", 1)[1].capitalize()
    if spec["type"] == "fix" and "security" in (spec.get("dimensions") or []):
        return "Security"
    return TYPE_GROUP.get(spec["type"], "Changed")


def for_audience(spec: dict, audience: str) -> bool:
    """Developers read every change; users read the changes they can notice (USER_TYPES), and any labelled
    `audience:users`; `audience:developers` keeps a Spec out of the users' notes."""
    labels = set(spec.get("labels") or [])
    if audience == "developers":
        return True
    if "audience:developers" in labels:
        return False
    return spec["type"] in USER_TYPES or "audience:users" in labels


def release_notes(root: Path, since: str, *, audience: str = "users") -> dict:
    """The release notes for the window: each landed Spec (title, intent, type, flags) grouped by Keep a Changelog."""
    if audience not in AUDIENCES:
        raise ValueError(f"--audience {audience!r}: one of {', '.join(AUDIENCES)}")
    cfg = config.load_file(config.CONFIG_PATH, str(root))
    win = rollup_window(root, since)
    groups: dict[str, list[dict]] = {}
    for s in landed(root, cfg, win):
        if s["status"] == "rolled_back" or not for_audience(s, audience):
            continue
        entry = {k: s[k] for k in ("id", "title", "type", "intent", "flags", "removes_flags", "deprecations", "removes_deprecations", "merged_on")}
        # A `breaking` label: a reader must act on upgrade (Semantic Versioning's incompatible change).
        entry["breaking"] = "breaking" in (s.get("labels") or [])
        groups.setdefault(change_group(s), []).append(entry)
    return {
        "schema_version": SCHEMA_VERSION,
        "audience": audience,
        "window": win.as_dict(),
        "groups": [{"name": g, "entries": sorted(groups[g], key=lambda e: (e["merged_on"], e["id"]))} for g in CHANGE_GROUPS if g in groups],
    }


def _flag_note(e: dict) -> str:
    parts = [f"behind the flag `{f['name']}` ({f['default']} by default)" for f in e["flags"]]
    parts += [f"the flag `{n}` is removed: on for everyone" for n in e["removes_flags"]]
    parts += [f"`{x['what']}` is deprecated: it stops working on {x['sunset']}; use {x['replacement']}" for x in e.get("deprecations") or []]
    parts += [f"`{n}` is removed, as its deprecation announced" for n in e.get("removes_deprecations") or []]
    return f" ({'; '.join(parts)})" if parts else ""


def release_notes_markdown(d: dict) -> str:
    """The notes in the shape of the release-notes template: the upgrade notes first, when a change is breaking, then
    one Keep a Changelog heading per group with entries."""
    w = d["window"]
    lines = [
        f"# Release notes, since {w['since']}",
        "",
        f"For {d['audience']}. Up to {w['head'] or 'no commit'}, from the Specs that landed: each entry is the Spec's title and intent.",
        "",
    ]
    breaking = [e for g in d["groups"] for e in g["entries"] if e.get("breaking")]
    if breaking:
        lines += ["## Upgrade notes", "", "These changes break what worked before: read them before you upgrade.", ""]
        lines += [f"- **{e['title']}**" + (f": {e['intent']}" if e["intent"] else "") + f" ({e['id']})" for e in breaking]
        lines.append("")
    for g in d["groups"]:
        lines += [f"## {g['name']}", ""]
        for e in g["entries"]:
            lines.append(f"- **{e['title']}**" + (f": {e['intent']}" if e["intent"] else "") + _flag_note(e) + f" ({e['id']})")
        lines.append("")
    if not d["groups"]:
        lines += ["No Spec for this audience landed in this range.", ""]
    return _no_html("\n".join(lines))


# ---- HTML pages (the views renderer: escaped, strict CSP, light and dark) --------------------------------------


def digest_page(d: dict) -> str:
    """The client status page (`aidd digest --client --html`); the team view is Markdown or JSON only."""
    from aidd import views

    if d["view"] != "client":
        raise ValueError("the digest page is the client's: the team view is Markdown or JSON")
    w = d["window"]
    r = d["delivery_status"]
    level = {"red": "fail", "amber": "pending", "green": "pass"}[r["status"]]
    sections = [
        views.Section(
            "status",
            "Status",
            views.join(
                views.el("p", views.badge(level, r["status"].upper()), " ", "; ".join(r["reasons"]) + "."),
                views.el("h3", "How the status is set"),
                views.el("ul", [views.el("li", x) for x in r["rules"]]),
            ),
        ),
        views.Section(
            "milestones",
            "Milestones",
            views.table(
                ["Milestone", "Due", "Status"],
                [[m["name"], m["due"] or "no date", m["status"] + (" (late)" if m["late"] else "")] for m in d["milestones"]],
                label="Milestones",
            )
            if d["milestones"]
            else views.el("p", "None listed."),
        ),
        views.Section(
            "landed",
            "What landed",
            views.el("ul", [views.el("li", views.el("strong", s["title"]), f": {s['intent']}" if s["intent"] else "") for s in d["landed"]])
            if d["landed"]
            else views.el("p", "Nothing in this window."),
        ),
        views.Section(
            "asks",
            "What we need from you",
            views.el("ul", [views.el("li", a["text"], views.el("span", f" ({a['source']})", class_="muted")) for a in d["asks"]])
            if d["asks"]
            else views.el("p", "Nothing right now."),
        ),
        *(
            [views.Section("deprecations", "Deprecations", views.el("ul", [views.el("li", deprecation_line(x)) for x in d["deprecations"]]))]
            if d.get("deprecations")
            else []
        ),
        views.Section(
            "next",
            "Next steps",
            views.el(
                "ul", [views.el("li", n["title"] or n["id"], views.el("span", f" ({n['status'].replace('_', ' ')})", class_="muted")) for n in d["next_steps"]]
            )
            if d["next_steps"]
            else views.el("p", "None planned."),
        ),
    ]
    if "cost" in d:
        sections.append(
            views.Section(
                "cost",
                "Cost",
                views.el("ul", [views.el("li", f"{cur}: {x['total']} over {x['changes']} change(s)") for cur, x in d["cost"]["currencies"].items()]),
            )
        )
    return views.page(f"Client status, {d['generated_on']}", sections, lead=_window_line(w), badge=views.badge(level, r["status"].upper()))
