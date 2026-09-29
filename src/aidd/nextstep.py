"""`aidd next`: what to do now in this repository, and who does it.

Anyone on the team, an engineer, a product manager, or a team lead, should be able to ask the repository what it is
waiting for and get one plain answer per piece of work: the step, who takes it (you, your agent, or a person with
approval rights), and the command. It reads only local state (the config, the Specs this branch changes, and the
proposals) and never changes anything.

Each Spec step says why the work matters (the why chain: mission, goal, Initiative, Epic, hypothesis) and its status
group. `aidd next --all` is the backlog: every object under the Specs folder at HEAD, not only this branch's, with
filters for your work, your agents' ready Tasks, blocked work, and the Approver inbox (`--waiting-on-me`). Work an
agent proposed waits for a person's triage; a Spec blocked_by unfinished work shows as blocked; the latest handoff note
says which role has the work and what it needs from a person. None of it approves anything or changes what the gate
decides: the gate never reads relations, labels, triage, or handoff notes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfgmod
from . import gitutil, globs, inputs, model, repo, rules, workitems
from .util import parse_time

AGENT, YOU, APPROVER = "your agent", "you", "an approver"
PERSON = "a person who triages"
COMMIT = "a person who can commit the team"


def _step(what: str, who: str, how: str, where: str = "", *, code: str = "") -> dict:
    """One step. `code` names the kind of step (such as `spec.in_review`), stable across wording changes."""
    return {"code": code, "where": where, "what": what, "who": who, "how": how}


# Spec statuses after which every Task's work is built, and before which no Task may start.
TASKS_DONE = ("in_review", "released", "done", "rolled_back")
MAX_RETRIES = 3


def tasks(data: dict) -> list[dict]:
    """The Spec's Tasks, for a coordinator that starts one agent per ready Task, each in its own worktree.

    A Task is `done` once the Spec is past implementation (in_review or later), `blocked` while the Spec is not
    approved, blocked, or cancelled, or while the Task waits on `depends_on` or has used its retries, and `ready`
    otherwise. aidd does not record when one Task of an approved Spec finishes: the coordinator starts a Task
    listed in `waiting_on` once the work it waits for is merged into the Spec's branch."""
    status = data.get("status", "draft")
    out = []
    for t in data.get("tasks", []) or []:
        if not isinstance(t, dict):
            continue
        task: dict = {"id": t.get("id"), "title": t.get("title"), "scope": list(t.get("scope", []) or []), "depends_on": list(t.get("depends_on", []) or [])}
        if t.get("skills"):
            task["skills"] = list(t["skills"])
        assignee = str(t.get("assignee") or "")
        if assignee:
            task["assignee"] = assignee
            if assignee.startswith("agent:"):
                task["role"] = assignee.split(":", 1)[1]
        why = ""
        if status in TASKS_DONE:
            task["status"] = "done"
        elif status == "draft":
            why = "the Spec waits for Spec approval; no Task starts before it"
        elif status == "blocked":
            why = f"the Spec is blocked: {data.get('blocked_on', 'see blocked_on')}"
        elif status not in ("ready", "in_progress"):
            why = f"the Spec is {status}"
        elif int(t.get("retry_count") or 0) >= MAX_RETRIES:
            why = f"used its {MAX_RETRIES} retries: the Spec is blocked until a person re-plans it"
        elif task["depends_on"]:
            task["waiting_on"] = task["depends_on"]
            why = f"waits for {', '.join(task['depends_on'])} to be merged into the Spec's branch"
        if "status" not in task:
            task["status"] = "blocked" if why else "ready"
        if why:
            task["why"] = why
        out.append(task)
    return out


def for_spec(rel: str, data: dict) -> dict:
    """The Spec's next step, with its Tasks under `tasks` (see `tasks`)."""
    return _spec_step(rel, data) | {"tasks": tasks(data)}


def _spec_step(rel: str, data: dict) -> dict:
    status, sid = data.get("status", "draft"), data.get("id", rel)
    if data.get("route") == "emergency" and status not in ("done", "cancelled"):
        due = (data.get("emergency") or {}).get("review_due")
        what = f"{sid} is an emergency: restore service first, then complete the Spec before {due}"
        return _step(what, AGENT, "/aidd-team:postmortem", rel, code="spec.emergency")
    steps = {
        "draft": (
            f"{sid} needs its Spec and tests finished, then Spec approval",
            AGENT,
            f"/aidd-team:specify, then `aidd validate {rel}` and `aidd hash {rel} --comment` for the approver",
        ),
        "ready": (f"{sid} is approved: implement it inside its scope", AGENT, "/aidd-team:implement, then `aidd test` and open the PR/MR"),
        "in_progress": (f"{sid} is being built: finish its Tasks and get the tests green", AGENT, "`aidd test`, then `aidd gate` locally"),
        "in_review": (f"{sid} {MERGE_WAIT[0]}", APPROVER, MERGE_WAIT[1]),
        "released": (f"{sid} is released: watch its observe window", AGENT, f"`aidd observe {rel}`, then set the status to done or rolled_back"),
        "rolled_back": (f"{sid} was rolled back: learn from it", AGENT, "/aidd-team:postmortem"),
        "blocked": (f"{sid} is blocked: {data.get('blocked_on', 'see blocked_on')}", YOU, "clear the blocker, or re-plan"),
    }
    what, who, how = steps.get(status) or (f"{sid} is {status}: nothing to do", YOU, "none")
    return _step(what, who, how, rel, code=f"spec.{status}")


MERGE_WAIT = ("waits for Merge approval on its head commit", "review the PR/MR and its report, then approve the head commit")


def for_proposal(rel: str, data: dict, initiatives: set[str]) -> dict | None:
    status, pid = data.get("status"), data.get("id", rel)
    steps = {
        "exploring": (
            f"{pid} waits for a go/no-go decision",
            YOU if (data.get("go_no_go") or {}).get("decision") else COMMIT,
            f"read the needs and questions, then record `go_no_go` in {rel}",
        ),
        "drafting": (f"{pid} is being drafted", AGENT, "/aidd-team:propose, then `aidd validate` and `aidd proposal matrix`"),
        "ready": (f"{pid} is signed off: send it to {data.get('addressee')}", YOU, "send it, then set the status to submitted"),
        "submitted": (f"{pid} waits for {data.get('addressee')} to decide", YOU, "record accepted, rejected, or withdrawn when they answer"),
    }
    if status == "accepted" and pid not in initiatives:
        steps["accepted"] = (f"{pid} was accepted: turn it into delivery work", YOU, f"`aidd proposal convert {rel}`, then /aidd-team:plan")
    found = steps.get(str(status))
    return _step(*found, rel, code=f"proposal.{status}") if found else None


MAX_BRANCHES = 100


def _scopes(data: dict) -> list[str]:
    return [g for t in data.get("tasks", []) for g in t.get("scope", [])]


def overlaps(root: Path, specs_dir: str, mine: list[tuple[str, dict]]) -> list[dict]:
    """Locks, found: another branch's Spec whose Task scope overlaps one of this branch's. With several people, each
    with their own agents, this is how two changes to the same code learn about each other before the merge does."""
    ours = [(data, _scopes(data)) for _, data in mine if _scopes(data)]
    if not ours:
        return []
    cwd = str(root)
    try:
        base = inputs.default_base(cwd)
    except gitutil.GitError:
        return []
    here = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd, check=False).strip()
    head = gitutil.rev_parse("HEAD", cwd)
    refs = [r for r in gitutil.run(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], cwd, check=False).split() if r]
    base_names = {base, base.split("/", 1)[-1]}
    seen: set[str] = set()
    steps = []
    # Filter first, then cap: the base, this branch, and its remote copy must not use up the budget of branches read.
    others = [r for r in refs if not (r in base_names or r.endswith("/HEAD") or r in (here, f"origin/{here}"))]
    if len(others) > MAX_BRANCHES:
        what = f"only the first {MAX_BRANCHES} of {len(others)} other branches were checked for overlapping Specs"
        steps.append(
            _step(what, YOU, "delete merged branches (`git branch --merged`, `git fetch --prune`) so every open one is checked", code="overlap.capped")
        )
    for ref in others[:MAX_BRANCHES]:
        if gitutil.rev_parse(ref, cwd) == head:
            continue
        fork = gitutil.run(["merge-base", base, ref], cwd, check=False).strip()
        if not fork:
            continue
        changed = gitutil.run(["diff", "--name-only", "-z", f"{fork}..{ref}", "--", specs_dir], cwd, check=False).split("\0")
        for rel in [p for p in changed if p]:
            text = gitutil.show(ref, rel, cwd)
            try:
                other, _ = model.split_front_matter(text or "", rel)
            except model.ModelError:
                continue
            oid = str(other.get("id"))
            if other.get("kind") != "spec" or oid in seen or other.get("status") in ("done", "cancelled", "released", "rolled_back"):
                continue
            theirs = _scopes(other)
            for data, scopes in ours:
                if oid == str(data.get("id")):
                    continue
                if any(globs.overlap(a, b) for a in scopes for b in theirs):
                    seen.add(oid)
                    who = gitutil.run(["log", "-1", "--format=%an", ref], cwd, check=False).strip() or "someone"
                    what = f"{data.get('id')} overlaps {oid} on {ref} ({who}): the same code, changed twice"
                    how = f'agree with {who} who goes first; the later change waits with status = "blocked" and blocked_on = "{oid}"'
                    steps.append(_step(what, YOU, how, rel, code="overlap"))
                    break
    return steps


@dataclass
class Filters:
    """What `aidd next` shows. By default, this branch's Specs and the open proposals; `all` reads every object under
    the Specs folder at HEAD instead, and each filter keeps only the Spec steps it matches (all of them must match)."""

    all: bool = False
    mine: bool = False
    agent: str | None = None  # None: no filter; "": a Task any agent may start; a role: that role's Tasks
    blocked: bool = False
    waiting_on_me: bool = False
    label: str | None = None

    def active(self) -> bool:
        return self.mine or self.agent is not None or self.blocked or self.waiting_on_me or self.label is not None


@dataclass
class _Ctx:
    root: Path
    cfg: cfgmod.Config
    today: dt.date
    now: dt.datetime
    idx: dict[str, dict]
    bots: set[str]
    ref: str | None  # "HEAD" when the Specs were read from HEAD; None for the working tree
    by_where: dict[str, dict] = field(default_factory=dict)


# Statuses whose work can still wait on another item; in review or later, the work is built.
_CAN_WAIT = ("draft", "ready", "in_progress", "blocked")
_NOTHING_TO_DO = ("spec.done", "spec.cancelled")
_APPROVER_WAITS = ("spec.in_review", "spec.spec_approval", "spec.merge_approval")


def eligible(data: dict, cfg: cfgmod.Config) -> list[str]:
    """Who may approve this Spec: its own `approvers` when it narrows them, else `owners.approvers`."""
    return [str(a) for a in (data.get("approvers") or cfg.approvers or [])]


def _with_handoff(step: dict, note: dict, rel: str, sid: str, status: str) -> dict:
    """The step as the latest handoff note says it stands: waiting for an approval it asked for, or taken by a role."""
    nxt = note.get("next")
    if nxt == "spec-approval" and status == "draft":
        return _step(
            f"{sid} waits for Spec approval of its current hash",
            APPROVER,
            f"read the Spec, its tests, and its design, then approve the hash `aidd hash {rel} --comment` prints (`aidd approve spec {rel}` locally)",
            rel,
            code="spec.spec_approval",
        ) | {"tasks": step["tasks"]}
    if nxt == "merge-approval" and status == "in_progress":
        return _step(f"{sid} {MERGE_WAIT[0]}", APPROVER, MERGE_WAIT[1], rel, code="spec.merge_approval") | {"tasks": step["tasks"]}
    if nxt in workitems.role_ids() and step["who"] == AGENT:
        step["who"] = f"{AGENT} ({nxt})"
    return step


def spec_steps(rel: str, data: dict, body: str, ctx: _Ctx) -> list[dict]:
    """A Spec's steps: a person's triage first when an agent proposed it, then its next step (blocked while it waits
    on unfinished work, or as its latest handoff note says), then a person's decision the note asks for. Nothing for
    a Spec that is declined, a duplicate, or snoozed until a later date."""
    triage = workitems.triage_state(data, ctx.bots, ctx.today)
    if triage == "hidden" or workitems.is_duplicate(data):
        return []
    sid, status = str(data.get("id", rel)), str(data.get("status") or "draft")
    extra = {"group": workitems.group(data), "labels": list(data.get("labels") or []), "why": workitems.why(data, ctx.idx, ctx.cfg)}
    if triage == "needed":
        t = data.get("triage") or {}
        what = (
            f"{sid}'s snooze ended on {t.get('until')}: decide on it again"
            if t.get("decision") == "snoozed"
            else f"{sid} was proposed by {data.get('proposed_by')}: accept it, decline it, mark it a duplicate, or snooze it"
        )
        how = (
            f'record triage = {{ decision = "accepted", by = "<you>", on = "{ctx.today.isoformat()}" }} in {rel} '
            "(or declined; duplicate with duplicate_of; snoozed with until)"
        )
        return [_step(what, PERSON, how, rel, code="spec.triage") | extra | {"blocked": False}]
    step = for_spec(rel, data)
    note = workitems.latest_handoff(body) if body else None
    waits = workitems.waiting_on(data, ctx.idx) if status in _CAN_WAIT else []
    if waits:
        tasks_ = step["tasks"]
        for t in tasks_:
            if t["status"] == "ready":
                t["status"], t["why"] = "blocked", f"the Spec is blocked by {', '.join(waits)}"
        step = _step(
            f"{sid} is blocked by {', '.join(waits)}: it starts when they finish",
            YOU,
            "finish or re-plan what it waits for; `aidd next --all --blocked` lists every blocked item",
            rel,
            code="spec.blocked_by",
        ) | {"tasks": tasks_, "waiting_on": waits}
    elif note:
        step = _with_handoff(step, note, rel, sid, status)
    step |= extra | {"blocked": status == "blocked" or bool(waits)}
    if step["code"] in _APPROVER_WAITS:
        step["approvers"] = eligible(data, ctx.cfg)
    if note:
        step["handoff"] = note
    steps = [step]
    asked = workitems.needs(note)
    if asked and step["code"] not in _NOTHING_TO_DO:
        how = f"decide it and write the answer in {rel} or the PR/MR, where the agent reads it back"
        steps.append(_step(f"{sid} needs a person: {'; '.join(asked)}", YOU, how, rel, code="spec.needs") | extra | {"blocked": False})
    return steps


def _waiting_since(ctx: _Ctx, step: dict) -> dt.datetime | None:
    """When the wait began: the commit that set the Spec's status for a Merge approval wait in review, else the last
    commit that touched the Spec (the one that asked for the approval). None while the Spec is uncommitted."""
    ref, rel, cwd = ctx.ref or "HEAD", step["where"], str(ctx.root)
    out = ""
    if step["code"] == "spec.in_review":
        out = gitutil.run(["log", "-1", "--format=%cI", "-G", r"^status[[:space:]]*=", ref, "--", rel], cwd, check=False).strip()
    return parse_time(out or gitutil.run(["log", "-1", "--format=%cI", ref, "--", rel], cwd, check=False).strip())


def _escalate(ctx: _Ctx, steps: list[dict]) -> None:
    """Mark each Approver wait older than gates.escalate_after_minutes and name the backup pool. It changes what this
    list says, never who may approve or what the gate decides."""
    limit = int(ctx.cfg.gates.get("escalate_after_minutes") or 0)
    if not limit:
        return
    backups = [str(b) for b in ctx.cfg.get("owners", "backup_approvers", default=[]) or []]
    for s in steps:
        if s["code"] not in _APPROVER_WAITS:
            continue
        since = _waiting_since(ctx, s)
        if since is None:
            continue
        minutes = int((ctx.now - since).total_seconds() // 60)
        s["waiting_minutes"] = minutes
        if minutes > limit:
            s["escalated"] = True
            s["backup_approvers"] = backups
            s["what"] += f" (waiting {_age(minutes)}, past gates.escalate_after_minutes = {limit})"
            s["how"] += (
                f"; past the limit: ask a backup approver ({', '.join(backups)})"
                if backups
                else "; past the limit, and no owners.backup_approvers are named: ask another eligible Approver"
            )


def _age(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} minutes"
    if minutes < 2 * 24 * 60:
        return f"{minutes // 60} hours"
    return f"{minutes // (24 * 60)} days"


def _queue(ctx: _Ctx, steps: list[dict], only: set[str] | None) -> list[dict]:
    """A warning for each Approver who holds more open waits than gates.max_open_per_approver (only the user's own
    when `only` names them). A queue signal for people; the gate never reads it."""
    limit = int(ctx.cfg.gates.get("max_open_per_approver") or 0)
    if not limit:
        return []
    held: dict[str, list[str]] = {}
    for s in steps:
        for a in s.get("approvers", []) if s["code"] in _APPROVER_WAITS else []:
            held.setdefault(a, []).append(str(s["where"]))
    backups = [str(b) for b in ctx.cfg.get("owners", "backup_approvers", default=[]) or []]
    out = []
    for who, waits in sorted(held.items()):
        if len(waits) <= limit or (only is not None and not workitems.is_me(who, only)):
            continue
        out.append(
            _step(
                f"{'you hold' if only is not None else who + ' holds'} {len(waits)} open approval waits, more than gates.max_open_per_approver = {limit}",
                YOU,
                "finish a review before another Spec asks for one, or share them with another eligible Approver"
                + (f" (backups: {', '.join(backups)})" if backups else ""),
                code="queue.over_limit",
            )
            | {"approver": who, "waits": waits}
        )
    return out


def _mine(ctx: _Ctx, step: dict, me: set[str], authors: dict[str, set[str]]) -> bool:
    """A Spec the user added (or has not committed yet), or one with a Task assigned to them."""
    data = ctx.by_where.get(step["where"]) or {}
    if any(workitems.is_me(t.get("assignee"), me) for t in data.get("tasks", []) or [] if isinstance(t, dict)):
        return True
    added = authors.get(step["where"])
    return bool(added & me) if added is not None else ctx.ref is None


def _filter(ctx: _Ctx, steps: list[dict], f: Filters) -> list[dict]:
    me = workitems.my_identities(ctx.root) if (f.mine or f.waiting_on_me) else set()
    authors = workitems.authors(ctx.root, "HEAD", ctx.cfg.specs_dir) if f.mine else {}
    out = []
    for s in steps:
        if not s["code"].startswith("spec."):
            continue
        if f.label is not None and f.label not in s.get("labels", []):
            continue
        if f.blocked and not s.get("blocked"):
            continue
        if f.waiting_on_me and not (s["code"] in _APPROVER_WAITS and any(workitems.is_me(a, me) for a in s.get("approvers", []))):
            continue
        if f.mine and not _mine(ctx, s, me, authors):
            continue
        if f.agent is not None:
            ready = [
                t
                for t in s.get("tasks", [])
                if t["status"] == "ready" and str(t.get("assignee", "")).startswith("agent:") and (not f.agent or t.get("role") == f.agent)
            ]
            if not ready or s.get("blocked"):
                continue
            s = s | {"tasks": ready}
        out.append(s)
    return out + (_queue(ctx, steps, me) if f.waiting_on_me else [])


def _read(path: Path) -> tuple[dict, str] | None:
    try:
        return model.split_front_matter(path.read_text(encoding="utf-8"), str(path))
    except (model.ModelError, OSError, UnicodeDecodeError):
        return None


def plan(root: Path, today: dt.date | None = None, filters: Filters | None = None, now: dt.datetime | None = None) -> list[dict]:
    """The next step for every open piece of work, most urgent first."""
    f = filters or Filters()
    if not (root / cfgmod.CONFIG_PATH).is_file():
        return [
            _step(
                "aidd is not set up in this repository",
                YOU,
                'ask your agent: "Install thaithienvanid/aidd and apply it to this project", or run `aidd init`',
                code="setup.missing",
            )
        ]
    fails = [msg for level, msg in repo.doctor(root) if level == "fail"]
    if fails:
        return [_step(f"the setup has a problem: {fails[0]}", YOU, "`aidd doctor` lists every check and its fix", code="setup.doctor_fail")]
    cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
    today = today or dt.date.today()
    now = now or dt.datetime.now(dt.UTC)
    from .guard import _specs

    initiatives = set()
    objects = []
    for path in repo.object_files(root, cfg.specs_dir) + repo.object_files(root, cfg.proposals_dir):
        read = _read(path)
        if read is None:
            continue
        data, body = read
        objects.append((str(path.relative_to(root)), data, body))
        if data.get("kind") == "initiative" and data.get("proposal"):
            initiatives.add(data["proposal"])
    steps: list[dict] = []
    if f.all:
        found, capped = workitems.objects_at(root, "HEAD", cfg.specs_dir)
        if capped:
            steps.append(
                _step(
                    f"only the first {workitems.MAX_OBJECTS} objects under {cfg.specs_dir}/ were read",
                    YOU,
                    "archive finished Specs to another folder",
                    code="backlog.capped",
                )
            )
        ctx = _Ctx(root, cfg, today, now, workitems.index([(p, d) for p, d, _ in found]), workitems.bots_of(cfg), "HEAD")
        specs = [(p, d, b) for p, d, b in found if d.get("kind") == "spec"]
    else:
        ctx = _Ctx(root, cfg, today, now, workitems.index([(p, d) for p, d, _ in objects]), workitems.bots_of(cfg), None)
        mine = _specs(str(root), cfg)
        bodies = {p: b for p, _, b in objects}
        specs = [(rel, data, bodies.get(rel) or ((_read(root / rel) or ({}, ""))[1])) for rel, data in mine]
        steps += overlaps(root, cfg.specs_dir, mine)
    ctx.by_where = {rel: data for rel, data, _ in specs}
    for rel, data, body in specs:
        steps += spec_steps(rel, data, body, ctx)
    if not f.all:  # the entry rule: route and lane for this branch's diff
        steps += [s for s in [rules.route_step(root, has_spec=bool(specs))] if s]
    for rel, data, _ in objects:
        if data.get("kind") == "proposal" and (step := for_proposal(rel, data, initiatives)):
            due = data.get("due")
            if due and str(due) < today.isoformat() and data.get("status") in ("exploring", "drafting", "ready"):
                step["what"] += f" (it was due {due})"
            steps.append(step | {"group": workitems.group(data)})
    if f.all:
        steps = [s for s in steps if s["code"] not in _NOTHING_TO_DO]
    _escalate(ctx, steps)
    if f.active():
        steps = _filter(ctx, steps, f)
    elif f.all:
        steps += _queue(ctx, steps, None)
    if not steps:
        steps.append(
            _step("nothing matches these filters", YOU, "drop a filter, or `aidd next --all` for every open item", code="nothing_matches")
            if f.active()
            else _step(
                "nothing is open" + ("" if f.all else " on this branch"),
                YOU,
                "describe the change to your agent (it assesses the route and follows the loop); "
                "for work someone outside the team must agree to first, `aidd new proposal`",
                code="nothing_open",
            )
        )
    for s in steps:
        s.setdefault("group", None)
    return sorted(steps, key=lambda s: _rank(s["who"]))


def _rank(who: str) -> int:
    """People's decisions first, then yours, then your agent's."""
    if who in (APPROVER, PERSON, COMMIT):
        return 0
    if who == YOU:
        return 1
    return 2 if who.startswith(AGENT) else 3


def markdown(steps: list[dict]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. {s['what']}")
        lines.append(f"   who: {s['who']}")
        lines.append(f"   how: {s['how']}")
        if s.get("why"):
            lines.append(f"   why: {workitems.why_text(s['why'])}")
    return "\n".join(lines) + "\n"
