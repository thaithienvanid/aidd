"""`aidd assess` and `aidd list`: what to do now, and who does it.

Anyone on the team, an engineer, a product manager, or a team lead, should be able to ask the repository what it is
waiting for and get one plain answer per piece of work: the step, who takes it (named by role: the agent, the author,
an Approver, a triager, or a decision maker), and the command. It reads only local state (the config, the Specs, the
proposals, the branches, the approvals recorded on this machine, and the evidence folder) and never changes anything.

Every status it shows is derived (`state.py`): a Spec is ready once a counted Spec approval names its current hash,
in progress once commits change a Task's scope, in review once the evidence is green on head, and shipped once it is
on the base branch. The stored `status` only answers where nothing local can (a platform's approvals live on the
PR/MR).

Two views, one command each:

- **This change** (`this_change`, `aidd assess`): the route as a header (the higher of what the diff needs and what the
  branch's Spec or Change Request block declares), then the steps for the Specs this branch changes, read from the working
  tree, then the overlaps with other branches. `aidd assess --paths` previews the route before any code exists.
- **All open work** (`backlog`, `aidd list`): one copy of every item, from the base branch and every open local
  and remote-tracking branch (the unmerged branch copy wins), with the open proposals and filters for the user's
  work, agents' Tasks, blocked work, a priority, and the Approver inbox (`--waiting-on-me`). Each Spec in progress
  carries its work item age, flagged once it passes `gates.max_in_progress_days`.

Each Spec step says why the work matters (the why chain: mission, goal, Initiative, Epic with its progress,
hypothesis) and its status group. Work an agent suggested waits for a person's triage; blocked work shows as blocked;
the latest handoff note names the role that has the work and what it needs from a person. None of it approves
anything or changes what the gate decides: the gate never reads relations, labels, triage, priority, owners, or
handoff notes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfgmod
from . import gitutil, globs, inputs, model, project, repo, rules, speclog, state, workitems
from .util import parse_time

# Who takes a step, as a role noun: the session-start hook puts these lines in an agent's context, where "you" would
# read as the agent itself.
AGENT, AUTHOR, APPROVER = "agent", "author", "Approver"
PERSON = "triager"
COMMIT = "decision maker"
MAX_RETRIES = state.MAX_RETRIES
MAX_BRANCHES = 100
MERGE_WAIT = ("waits for Merge approval on its head commit", "review the PR/MR and its report, then approve the head commit")
_NOTHING_TO_DO = ("spec.done", "spec.cancelled")
_APPROVER_WAITS = ("spec.spec_approval", "spec.in_review")
_PRIORITY_RANK = {p: i for i, p in enumerate(state.PRIORITIES)}
# Work item age: the days a Spec may stay in progress before `aidd list` flags it, while gates.max_in_progress_days is
# unset. Two working weeks: a Spec sliced to its route budget finishes well inside it.
MAX_IN_PROGRESS_DAYS = 10
# The step-code contract (experimental): every code a step here can carry, and who takes it. `aidd autopilot next` maps an agent's
# step to the one flow whose `starts_on` names it (roles.json) and a person's step to none; the lane step maps by its
# lane (`lane.fast`, `lane.spec`). tests/test_autopilot.py fails when this code emits a code the table lacks.
STEP_CODES: dict[str, str] = {
    "setup.missing": AUTHOR,
    "setup.doctor_fail": AUTHOR,
    "spec.emergency": AGENT,
    "spec.backfill": AGENT,
    "spec.blocked_by": AUTHOR,
    "spec.blocked": AUTHOR,
    "spec.spec_approval": APPROVER,
    "spec.draft": AGENT,
    "spec.ready": AGENT,
    "spec.in_progress": AGENT,
    "spec.in_review": APPROVER,
    "spec.shipped": AGENT,
    "spec.done": AUTHOR,
    "spec.rolled_back": AGENT,
    "spec.cancelled": AUTHOR,
    "spec.triage": PERSON,
    "spec.needs": AUTHOR,
    "spec.outcome_due": AUTHOR,
    "epic.close": AUTHOR,
    "initiative.close": AUTHOR,
    "proposal.exploring": COMMIT,
    "proposal.drafting": AGENT,
    "proposal.signed_off": AUTHOR,
    "proposal.submitted": AUTHOR,
    "proposal.accepted": AUTHOR,
    "overlap": AUTHOR,
    "overlap.capped": AUTHOR,
    "backlog.capped": AUTHOR,
    "knowledge.action": AUTHOR,
    "flag.overdue": AUTHOR,
    "queue.over_limit": AUTHOR,
    "wip.over_limit": AUTHOR,
    "nothing_open": AUTHOR,
    "nothing_matches": AUTHOR,
    "lane.fast": AGENT,
    "lane.spec": AGENT,
}


def _step(what: str, who: str, how: str, where: str = "", *, code: str = "") -> dict:
    """One step. `code` names the kind of step (such as `spec.in_review`), stable across wording changes."""
    return {"code": code, "where": where, "what": what, "who": who, "how": how}


# ---- One Spec's steps -----------------------------------------------------------------------------------------


def tasks(
    data: dict,
    status: str | None = None,
    facts: state.Facts | None = None,
    *,
    note: dict | None = None,
    approval: bool | None = None,
    blockers: list[str] | tuple[str, ...] = (),
) -> list[dict]:
    """The Spec's Tasks with their derived state (`state.task_states`), for a coordinator that starts one agent per
    `todo` Task, each in its own worktree. Without `status`, the stored one answers; without `approval`, the default
    profile's routes say whether the Spec needs Spec approval."""
    approval = state.needs_approval(data, None) if approval is None else approval
    return state.task_states(data, status or state.spec_status(data, facts, approval=approval), facts, note=note, approval=approval, blockers=blockers)


def _spec_step(
    rel: str,
    data: dict,
    status: str,
    *,
    committed: bool,
    approval: bool,
    blockers: list[str],
    waits: list[str] | None = None,
    local: bool = False,
    team: bool = True,
) -> dict:
    """The Spec's next step. `local`: the local gate is the gate (no platform), so a person approves and ships at their own
    terminal; `team`: the aidd-team roles are installed, so the step may name their commands."""
    sid = data.get("id", rel)
    if data.get("route") == "emergency" and not (data.get("outcome") or {}).get("learn_ref") and status not in ("cancelled", "rolled_back"):
        due = (data.get("emergency") or {}).get("review_due")
        if status in ("shipped", "done"):
            what = f"{sid} restored service: complete the backfill Spec and the post-incident review by {due}"
            return _step(what, AGENT, f"/aidd-team:postmortem, then record outcome.learn_ref in {rel}", rel, code="spec.backfill") | {"emergency": True}
        what = f"{sid} is an emergency: restore service first, then complete the Spec before {due}"
        how = "repair it inside the declared scope, `aidd test` the smoke tests, and ship with the route's approvals and the commander's"
        return _step(what, AGENT, how, rel, code="spec.emergency") | {"emergency": True}
    if waits:
        return _step(
            f"{sid} is blocked by {', '.join(waits)}: it starts when they finish",
            AUTHOR,
            "finish or re-plan what it waits for; `aidd list --blocked` lists every blocked item",
            rel,
            code="spec.blocked_by",
        ) | {"waiting_on": waits}
    if blockers:
        return _step(f"{sid} is blocked: {'; '.join(blockers)}", AUTHOR, "clear the blocker (then remove blocked_on), or re-plan", rel, code="spec.blocked")
    if status == "draft" and approval and committed:
        how = (
            f"read the Spec, its tests, and its design, then run `aidd approve spec {rel}` at your own terminal"
            if local
            else f"read the Spec, its tests, and its design, then approve the hash `aidd hash {rel} --line` prints (`aidd approve spec {rel}` locally)"
        )
        return _step(f"{sid} waits for Spec approval of its current hash", APPROVER, how, rel, code="spec.spec_approval")
    specify = "/aidd-team:specify, then " if team else "finish the Spec and its tests, then "
    if local:
        freeze = f"; a person runs `aidd approve spec {rel}`" + ("" if approval else " (optional on this route; it freezes them)")
    else:
        freeze = f", and `aidd hash {rel} --line` for the Approver"
    build = "/aidd-team:implement, then " if team else "implement it, then "
    steps = {
        "draft": (
            f"{sid} needs its Spec and tests finished" + (", then Spec approval" if approval else ""),
            AGENT,
            f"{specify}`aidd validate {rel}` and commit the Spec and its tests{freeze}",
        ),
        "ready": (
            f"{sid}: Spec approval recorded; implement it inside its scope",
            AGENT,
            build + ("`aidd test` and `aidd gate`; a person runs `aidd ship`" if local else "`aidd test` and open the PR/MR"),
        ),
        "in_progress": (f"{sid} is being built: finish its Tasks and get the tests green", AGENT, "`aidd test`, then `aidd gate` locally"),
        "in_review": (f"{sid} {MERGE_WAIT[0]}", APPROVER, "read the report, then run `aidd ship` at your own terminal" if local else MERGE_WAIT[1]),
        "shipped": (
            f"{sid} is shipped: watch its observe window",
            AGENT,
            f"`aidd observe {rel} --write`; if the rollback trigger fires, a person rolls back and records outcome.rolled_back",
        ),
        "rolled_back": (f"{sid} was rolled back: learn from it", AGENT, "/aidd-team:postmortem" if team else "write the postmortem: `aidd new postmortem`"),
    }
    what, who, how = steps.get(status) or (f"{sid} is {status}: nothing to do", AUTHOR, "none")
    return _step(what, who, how, rel, code=f"spec.{status}")


def eligible(data: dict, cfg: cfgmod.Config) -> list[str]:
    """Who may approve this Spec: its own `approvers` when it narrows them, else `owners.approvers`."""
    return [str(a) for a in (data.get("approvers") or cfg.approvers or [])]


# ---- What a view reads ----------------------------------------------------------------------------------------


@dataclass
class Item:
    """One copy of a Spec, Epic, or Initiative, where it was read, and what aidd derives for it."""

    rel: str
    data: dict
    body: str
    text: str
    ref: str | None = None  # the branch it was read from; None for this working tree
    sha: str | None = None
    facts: state.Facts = field(default_factory=state.Facts)
    status: str = "draft"

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.rel)

    @property
    def kind(self) -> str:
        return str(self.data.get("kind"))


@dataclass
class Filters:
    """What a view shows. By default, this branch's Specs (`aidd assess`); `all` reads all open work instead (`aidd list`),
    and each filter keeps only the steps it matches (all of them must match)."""

    all: bool = False
    mine: bool = False
    agent: str | None = None  # None: no filter; "": a Task any agent may start; a role: that role's Tasks
    blocked: bool = False
    waiting_on_me: bool = False
    label: str | None = None
    priority: str | None = None  # this level or higher

    def active(self) -> bool:
        return self.mine or self.agent is not None or self.blocked or self.waiting_on_me or self.label is not None or self.priority is not None


@dataclass
class _Ctx:
    root: Path
    cfg: cfgmod.Config
    today: dt.date
    now: dt.datetime
    obs: state.Observer
    bots: set[str]
    backlog: bool
    items: dict[str, Item] = field(default_factory=dict)  # every work item by id
    status: dict[str, str] = field(default_factory=dict)  # derived status by id
    progress: dict[str, tuple[int, int]] = field(default_factory=dict)  # container id -> (finished, children)
    by_where: dict[str, Item] = field(default_factory=dict)
    local: bool = False  # the local gate is the gate: no platform
    team: bool = True  # the aidd-team roles are installed

    @property
    def idx(self) -> dict[str, dict]:
        return {i: it.data for i, it in self.items.items()}


def _read(path: Path) -> tuple[dict, str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
        data, body = model.split_front_matter(text, str(path))
        return data, body, text
    except (model.ModelError, OSError, UnicodeDecodeError):
        return None


def _derive(ctx: _Ctx) -> None:
    """Every item's derived status: Specs from their facts, then Epics from their children, then Initiatives."""
    specs = {it.id: ctx.obs.status(it.facts, it.data) for it in ctx.items.values() if it.kind == "spec"}
    ctx.status, ctx.progress, _ = state.containers([it.data for it in ctx.items.values()], specs)
    for it in ctx.items.values():
        it.status = ctx.status.get(it.id, it.status)


def _lets_go(ctx: _Ctx):
    return lambda i: state.unblocks(ctx.status.get(i, "draft"))


def _branches(root: Path, base: str, *, include_here: bool) -> tuple[list[str], int]:
    """The other local and remote-tracking branches, at most MAX_BRANCHES (the base, and this branch unless
    `include_here`, are left out before the cap), and how many there were."""
    cwd = str(root)
    here = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd, check=False).strip()
    refs = [r for r in gitutil.run(["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], cwd, check=False).split() if r]
    base_names = {base, base.split("/", 1)[-1]}
    mine = () if include_here else (here, f"origin/{here}")
    others = [r for r in refs if not (r in base_names or r.endswith("/HEAD") or r in mine or r == "origin")]
    if include_here and here in others:  # this branch first: its copy wins over another branch's
        others.remove(here)
        others.insert(0, here)
    return others[:MAX_BRANCHES], len(others)


def _capped_step(n: int) -> dict:
    what = f"only the first {MAX_BRANCHES} of {n} other branches were checked for overlapping Specs"
    return _step(what, AUTHOR, "delete merged branches (`git branch --merged`, `git fetch --prune`) so every open one is checked", code="overlap.capped")


def _scopes(data: dict) -> list[str]:
    return [g for t in data.get("tasks", []) or [] if isinstance(t, dict) for g in t.get("scope", []) or []]


def overlaps(root: Path, specs_dir: str, mine: list[tuple[str, dict]]) -> list[dict]:
    """Locks, found: another branch's Spec whose Task scope overlaps one of this branch's, or that freezes a doc one of
    this branch's also freezes (two approved versions of one document). With several people, each with their own
    agents, this is how two changes to the same code learn about each other before the merge does."""
    ours = [(data, _scopes(data)) for _, data in mine if _scopes(data) or model.frozen_docs(data)]
    if not ours:
        return []
    cwd = str(root)
    try:
        base = inputs.default_base(cwd)
    except gitutil.GitError:
        return []
    head = gitutil.rev_parse("HEAD", cwd)
    refs, total = _branches(root, base, include_here=False)
    steps = [_capped_step(total)] if total > MAX_BRANCHES else []
    seen: set[str] = set()
    for ref in refs:
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
            if other.get("kind") != "spec" or oid in seen or state.spec_status(other) in state.UNBLOCKS:
                continue
            theirs, their_docs = _scopes(other), model.frozen_docs(other)
            for data, scopes in ours:
                if oid == str(data.get("id")):
                    continue
                docs = [d for d in model.frozen_docs(data) if any(globs.overlap(d, o) for o in their_docs)]
                if docs or any(globs.overlap(a, b) for a in scopes for b in theirs):
                    seen.add(oid)
                    who = gitutil.run(["log", "-1", "--format=%an", ref], cwd, check=False).strip() or "someone"
                    what = f"{data.get('id')} overlaps {oid} on {ref} ({who}): the same code, changed twice"
                    if docs:
                        what = f"{data.get('id')} overlaps {oid} on {ref} ({who}): both freeze {', '.join(docs)}, two approved versions of one doc"
                    how = f'agree with {who} who goes first; the later change waits with blocked_on = "{oid}", or relations = [{{ type = "blocked_by", id = "{oid}" }}]'
                    steps.append(_step(what, AUTHOR, how, rel, code="overlap"))
                    break
    return steps


def this_change(ctx: _Ctx, objects: list[tuple[str, dict, str, str]]) -> tuple[list[Item], list[dict]]:
    """The branch view: the Specs this branch changes, from the working tree, and the other branches they overlap.
    Every other item joins the index as the base branch holds it (then as the working tree does, for one the base
    lacks), so the why chain and blocked_by read the same derived statuses the backlog shows."""
    from .guard import _specs

    obs = ctx.obs
    mine = _specs(str(ctx.root), ctx.cfg)
    texts = {p: (d, b, t) for p, d, b, t in objects}
    ours = []
    for rel, data in mine:
        _, body, text = texts.get(rel) or (_read(ctx.root / rel) or ({}, "", ""))
        it = Item(rel, data, body, text, facts=obs.worktree(rel, text, data))
        ours.append(it)
        ctx.items[it.id] = it
    at_base = workitems.objects_at(ctx.root, obs.base_sha, ctx.cfg.specs_dir)[0] if obs.base_sha else []
    for rel, data, body, text in at_base:
        if data.get("kind") in workitems.WORK_KINDS and data.get("id") and str(data["id"]) not in ctx.items:
            facts = obs.at(obs.base_sha, rel, text, data) if data.get("kind") == "spec" else state.Facts()  # type: ignore[arg-type]
            ctx.items[str(data["id"])] = Item(rel, data, body, text, ref=obs.base, sha=obs.base_sha, facts=facts)
    for rel, data, body, text in objects:
        if data.get("kind") in workitems.WORK_KINDS and data.get("id") and str(data["id"]) not in ctx.items:
            ctx.items[str(data["id"])] = Item(rel, data, body, text, facts=state.Facts())
    return ours, overlaps(ctx.root, ctx.cfg.specs_dir, mine)


def backlog(ctx: _Ctx) -> tuple[list[Item], list[dict]]:
    """The backlog view: one copy of every item, read from the base branch and every open (unmerged) local and
    remote-tracking branch; a branch's copy wins over the base's, this branch's over another's. Uncommitted work is
    not in it: commit it, and it is."""
    obs, root, cwd = ctx.obs, ctx.root, str(ctx.root)
    steps: list[dict] = []
    base_ref = obs.base_sha or obs.head
    if not base_ref:
        return [], []
    found, capped = workitems.objects_at(root, base_ref, ctx.cfg.specs_dir)
    if capped:
        steps.append(
            _step(
                f"only the first {workitems.MAX_OBJECTS} objects under {ctx.cfg.specs_dir}/ were read",
                AUTHOR,
                "archive finished Specs to another folder",
                code="backlog.capped",
            )
        )
    chosen: dict[str, Item] = {}
    if obs.base:
        refs, total = _branches(root, obs.base, include_here=True)
        if total > MAX_BRANCHES:
            steps.append(_capped_step(total))
        for ref in refs:
            sha = obs.sha(ref)
            if not sha or sha == obs.base_sha or gitutil.ok(["merge-base", "--is-ancestor", sha, obs.base_sha], cwd):  # type: ignore[list-item]
                continue  # merged: its copies are the base's now
            fork = obs.fork(sha)
            if not fork:
                continue
            changed = [
                p for p in gitutil.run(["diff", "--name-only", "-z", fork, sha, "--", ctx.cfg.specs_dir], cwd, check=False).split("\0") if p.endswith(".md")
            ]
            for rel, data, body, text in workitems.read_at(root, sha, changed):
                oid = str(data.get("id") or "")
                if data.get("kind") not in workitems.WORK_KINDS or not oid or oid in chosen:
                    continue
                facts = obs.at(sha, rel, text, data) if data.get("kind") == "spec" else state.Facts()
                chosen[oid] = Item(rel, data, body, text, ref=ref, sha=sha, facts=facts)
    for rel, data, body, text in found:
        oid = str(data.get("id") or "")
        if data.get("kind") not in workitems.WORK_KINDS or not oid or oid in chosen:
            continue
        facts = obs.at(base_ref, rel, text, data) if data.get("kind") == "spec" else state.Facts()
        chosen[oid] = Item(rel, data, body, text, ref=obs.base, sha=base_ref, facts=facts)
    ctx.items.update(chosen)
    return [it for it in chosen.values() if it.kind == "spec"], steps


# ---- Steps ----------------------------------------------------------------------------------------------------


def spec_steps(it: Item, ctx: _Ctx) -> list[dict]:
    """A Spec's steps: a person's triage first when an agent suggested it, then its next step (blocked while it waits
    on unfinished work), then a person's decision its latest handoff note asks for. Nothing for a Spec whose triage
    declined it or snoozed it until a later date, or that `duplicates` another."""
    data, rel = it.data, it.rel
    triage = workitems.triage_state(data, ctx.bots, ctx.today)
    if triage == "hidden" or workitems.is_duplicate(data):
        return []
    sid, status = it.id, it.status
    approval = ctx.obs.approval(data)
    extra: dict = {
        "id": sid,
        "status": status,
        "group": workitems.group(data, status),
        "labels": list(data.get("labels") or []),
        "priority": state.priority(data, ctx.idx),
        "why": workitems.why(data, ctx.idx, ctx.cfg, ctx.progress),
    }
    if data.get("owner"):
        extra["owner"] = str(data["owner"])
    if it.ref and ctx.backlog:
        extra["branch"] = it.ref
    if triage == "needed":
        t = data.get("triage") or {}
        what = (
            f"{sid}'s snooze ended on {t.get('until')}: decide on it again"
            if t.get("decision") == "snoozed"
            else f"{sid} was suggested by {data.get('suggested_by')}: accept it, decline it, or snooze it (a duplicate: relate it with `duplicates`)"
        )
        how = (
            f'record triage = {{ decision = "accepted", by = "<you>", on = "{ctx.today.isoformat()}" }} in {rel} '
            '(or declined; snoozed with until; for a duplicate, relations = [{ type = "duplicates", id = "<the other>" }])'
        )
        return [_step(what, PERSON, how, rel, code="spec.triage") | extra | {"blocked": False}]
    waits = workitems.waiting_on(data, ctx.idx, _lets_go(ctx)) if status in state.CAN_WAIT else []
    blockers = state.blocked(data, status, waits)
    note = workitems.latest_handoff(it.body) if it.body else None
    committed = bool(it.facts.committed) or it.ref is not None
    step = _spec_step(rel, data, status, committed=committed, approval=approval, blockers=blockers, waits=waits, local=ctx.local, team=ctx.team)
    step["tasks"] = state.task_states(data, status, it.facts, note=note, approval=approval, blockers=blockers)
    nxt = (note or {}).get("next")
    if nxt in workitems.role_ids() and step["who"] == AGENT:
        step["who"] = f"{AGENT} ({nxt})"
    step |= extra | {"blocked": bool(blockers)}
    if step["code"] in _APPROVER_WAITS:
        step["approvers"] = eligible(data, ctx.cfg)
    if note:
        step["handoff"] = note
    ctx.by_where[rel] = it
    steps = [step]
    asked = workitems.needs(note, status)
    if asked and step["code"] not in _NOTHING_TO_DO:
        how = f"decide it and write the answer in {rel} or the PR/MR, where the agent reads it back"
        steps.append(_step(f"{sid} needs a person: {'; '.join(asked)}", AUTHOR, how, rel, code="spec.needs") | extra | {"blocked": False})
    due = state.outcome_due(data, status, ctx.today)
    if due is not None:
        how = f"measure the metric the hypothesis names and record outcome.result (met, missed, or inconclusive, with the number) in {rel}"
        steps.append(_step(f"{sid}'s hypothesis was due {due}: record the outcome", AUTHOR, how, rel, code="spec.outcome_due") | extra | {"blocked": False})
    return steps


def container_steps(it: Item, ctx: _Ctx) -> list[dict]:
    """In the backlog: close an Epic or Initiative once every child is finished; a person decides."""
    done, total = ctx.progress.get(it.id, (0, 0))
    if it.status in ("done", "cancelled") or not total or done < total:
        return []
    what = f"close {it.id}: {done}/{total} children finished"
    how = f'record status = "done" in {it.rel} (or "cancelled" if it was stopped), on the base branch'
    return [
        _step(what, AUTHOR, how, it.rel, code=f"{it.kind}.close")
        | {"id": it.id, "status": it.status, "group": workitems.group(it.data, it.status), "priority": state.priority(it.data, ctx.idx), "blocked": False}
    ]


def for_proposal(rel: str, data: dict, initiatives: set[str]) -> dict | None:
    """A proposal's next step in its derived status (`model.proposal_status`)."""
    status, pid = state.proposal_status(data), data.get("id", rel)
    record = f'record outcome = {{ decision = "<decision>", by = "@you", on = "YYYY-MM-DD" }} in {rel}'
    steps = {
        "exploring": (f"{pid} waits for a go/no-go decision", COMMIT, f"read the needs and questions, then record `go_no_go` in {rel}"),
        "drafting": (f"{pid} is being drafted", AGENT, "/aidd-team:propose, then `aidd validate` and `aidd proposal matrix`"),
        "signed_off": (f"{pid} is signed off: send it to {data.get('addressee')}", AUTHOR, f"send it, then {record.replace('<decision>', 'submitted')}"),
        "submitted": (
            f"{pid} waits for {data.get('addressee')} to decide",
            AUTHOR,
            f"when they answer, {record.replace('<decision>', 'accepted')} (or rejected, withdrawn)",
        ),
    }
    if status == "accepted" and pid not in initiatives:
        steps["accepted"] = (f"{pid} was accepted: turn it into delivery work", AUTHOR, f"`aidd proposal convert {rel}`, then /aidd-team:plan")
    found = steps.get(status)
    if not found:
        return None
    return _step(*found, rel, code=f"proposal.{status}") | {"id": pid, "status": status}


def _waiting_since(ctx: _Ctx, step: dict) -> dt.datetime | None:
    """When the wait began: for Merge approval, the head commit the evidence is green on; for Spec approval, the last
    commit that touched the Spec (the one that asked for the approval). None while the Spec is uncommitted."""
    it = ctx.by_where.get(step["where"])
    ref, cwd = (it.sha if it and it.sha else "HEAD"), str(ctx.root)
    if step["code"] == "spec.in_review":
        return parse_time(gitutil.run(["log", "-1", "--format=%cI", ref], cwd, check=False).strip())
    return parse_time(gitutil.run(["log", "-1", "--format=%cI", ref, "--", step["where"]], cwd, check=False).strip())


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


def _entered(ctx: _Ctx, it: Item) -> dt.datetime | None:
    """When the Spec entered in progress. On a branch: the earliest author date (a rebase keeps it) of the commits since
    the fork that changed a Task's scope, the fact that derives in_progress. A cherry-pick may put an older date after a
    newer one, so every date counts. Where the stored status answered instead: the committer date of the commit that
    set it, as `aidd log` (speclog) reads it. None when neither says, and in a shallow clone, whose history is cut."""
    sha = it.sha or ctx.obs.head
    if not sha or ctx.obs.shallow:
        return None
    fork = ctx.obs.fork(sha) if it.facts.changed is not None else None
    scopes = [str(g) for t in it.data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    if fork and scopes:
        specs = [f":(glob){g}**" if g.endswith("/") else f":(glob){g}" for g in scopes]
        out = gitutil.run(["log", "--format=%aI", f"{fork}..{sha}", "--", *specs], str(ctx.root), check=False).split()
        dates = [d for d in map(parse_time, out) if d is not None]
        if dates:
            return min(dates)
    held = speclog.transitions(ctx.root, it.rel, ctx.now, ref=sha)
    return parse_time(held[-1]["since"]) if held and held[-1]["status"] == "in_progress" else None


def _ages(ctx: _Ctx, steps: list[dict]) -> None:
    """Work item age: on each step of a Spec in progress, `age_days` since it entered in progress, and `aged` once that
    passes gates.max_in_progress_days (MAX_IN_PROGRESS_DAYS while unset; 0 turns the flag off). One or two git log
    calls per Spec in progress. A queue signal for people, like `_escalate`; the gate never reads it."""
    raw = ctx.cfg.gates.get("max_in_progress_days")
    limit = MAX_IN_PROGRESS_DAYS if raw is None else int(raw)
    ages: dict[str, int | None] = {}
    for s in steps:
        it = ctx.by_where.get(s["where"])
        if s.get("status") != "in_progress" or not s["code"].startswith("spec.") or it is None:
            continue
        first = s["where"] not in ages
        if first:
            since = _entered(ctx, it)
            ages[s["where"]] = max(0, int((ctx.now - since).total_seconds() // 86400)) if since else None
        days = ages[s["where"]]
        if days is None:
            continue
        s["age_days"] = days
        if limit:
            s["aged"] = days > limit
            if s["aged"] and first:
                s["how"] += f"; aging: past gates.max_in_progress_days = {limit}, so finish it before new work starts, or split it"


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
                AUTHOR,
                "finish a review before another Spec asks for one, or share them with another eligible Approver"
                + (f" (backups: {', '.join(backups)})" if backups else ""),
                code="queue.over_limit",
            )
            | {"approver": who, "waits": waits}
        )
    return out


def _wip(ctx: _Ctx, steps: list[dict]) -> list[dict]:
    """A warning for each person whose Specs in progress (by `owner`) exceed gates.max_in_progress_per_owner. A queue
    signal for people, like `_queue`; the gate never reads it."""
    limit = int(ctx.cfg.gates.get("max_in_progress_per_owner") or 0)
    if not limit:
        return []
    held: dict[str, set[str]] = {}
    for s in steps:
        if s.get("status") == "in_progress" and s.get("owner") and s["code"].startswith("spec."):
            held.setdefault(s["owner"], set()).add(str(s["where"]))
    return [
        _step(
            f"{who} holds {len(specs)} Specs in progress, more than gates.max_in_progress_per_owner = {limit}",
            AUTHOR,
            "finish one before starting another, or hand one to someone with room (change its owner)",
            code="wip.over_limit",
        )
        | {"owner": who, "specs": sorted(specs)}
        for who, specs in sorted(held.items())
        if len(specs) > limit
    ]


class _Authors:
    """Who added each object file, per ref, read once each."""

    def __init__(self, ctx: _Ctx):
        self.ctx, self.cache = ctx, {}  # type: ignore[var-annotated]

    def of(self, ref: str, rel: str) -> set[str] | None:
        folder = self.ctx.cfg.proposals_dir if rel.startswith(globs.under(self.ctx.cfg.proposals_dir, "")) else self.ctx.cfg.specs_dir
        key = (ref, folder)
        if key not in self.cache:
            self.cache[key] = workitems.authors(self.ctx.root, ref, folder)
        return self.cache[key].get(rel)


def _mine(ctx: _Ctx, step: dict, me: set[str], authors: _Authors) -> bool:
    """Work the user drives: its owner, else a Task assigned to them, else the object they added (or have not
    committed yet)."""
    it = ctx.by_where.get(step["where"])
    data = it.data if it else {}
    if data.get("owner"):
        return workitems.is_me(data["owner"], me)
    if any(workitems.is_me(t.get("assignee"), me) for t in data.get("tasks", []) or [] if isinstance(t, dict)):
        return True
    ref = (it.sha if it else None) or "HEAD"
    added = authors.of(ref, step["where"])
    if added is not None:
        return bool(added & me)
    return not ctx.backlog and (it is None or it.ref is None)


def _added_by(added: set[str] | None, me: set[str]) -> bool:
    """A file the user added, or one not committed yet (only its author has it)."""
    return bool(added & me) if added is not None else True


def _filter(ctx: _Ctx, steps: list[dict], f: Filters) -> list[dict]:
    """Each filter keeps the steps it matches. A proposal has no labels, Tasks, blocks, or Approver, so only --mine
    (the proposals the user added) and --priority (a proposal is medium) keep one."""
    me = workitems.my_identities(ctx.root) if (f.mine or f.waiting_on_me) else set()
    authors = _Authors(ctx)
    floor = _PRIORITY_RANK.get(f.priority or "low", 3)
    out = []
    for s in steps:
        proposal = s["code"].startswith("proposal.")
        if not (s["code"].startswith("spec.") or proposal):
            continue
        if proposal and (f.label is not None or f.blocked or f.agent is not None or f.waiting_on_me):
            continue
        if f.priority is not None and _PRIORITY_RANK.get(s.get("priority") or "medium", 2) > floor:
            continue
        if f.label is not None and f.label not in s.get("labels", []):
            continue
        if f.blocked and not s.get("blocked"):
            continue
        if f.waiting_on_me and not (s["code"] in _APPROVER_WAITS and any(workitems.is_me(a, me) for a in s.get("approvers", []))):
            continue
        if f.mine and not (_mine(ctx, s, me, authors) if not proposal else _added_by(authors.of("HEAD", s["where"]), me)):
            continue
        if f.agent is not None:
            todo = [
                t
                for t in s.get("tasks", [])
                if t["status"] == "todo" and str(t.get("assignee", "")).startswith("agent:") and (not f.agent or t.get("role") == f.agent)
            ]
            if not todo or s.get("blocked"):
                continue
            s = s | {"tasks": todo}
        out.append(s)
    return out + (_queue(ctx, steps, me) if f.waiting_on_me else [])


def _rank(who: str) -> int:
    """People's decisions first, then the author's, then the agent's."""
    if who in (APPROVER, PERSON, COMMIT):
        return 0
    if who == AUTHOR:
        return 1
    return 2 if who.startswith(AGENT) else 3


def sort_key(s: dict) -> tuple:
    """Most urgent first: an emergency, then by priority, then who acts (a person's decision before the author's, the author's
    before the agent's), then unblocked before blocked, then the longest wait, then the id (a step about no item, such
    as the route for the branch's diff, after the items)."""
    return (
        0 if s.get("emergency") else 1,
        _PRIORITY_RANK.get(s.get("priority") or "medium", 2),
        _rank(s["who"]),
        1 if s.get("blocked") else 0,
        -int(s.get("waiting_minutes") or 0),
        0 if s.get("id") else 1,
        str(s.get("id") or ""),
    )


def _as_owner(s: dict) -> dict:
    """In the backlog, work someone else drives names them: their agent, not the author's."""
    owner = s.get("owner")
    if not owner:
        return s
    if s["who"] == AUTHOR:
        return s | {"who": owner}
    if s["who"].startswith(AGENT):
        return s | {"who": f"{owner}'s agent" + s["who"][len(AGENT) :]}
    return s


def _setup_step(root: Path) -> dict | None:
    """The only step while aidd is not set up, or its setup fails a check; None when it is ready."""
    if not (root / cfgmod.CONFIG_PATH).is_file():
        return _step(
            "aidd is not set up in this repository",
            AUTHOR,
            'ask the agent: "Install thaithienvanid/aidd and apply it to this project", or run `aidd init`',
            code="setup.missing",
        )
    fails = [msg for level, msg in repo.doctor(root) if level == "fail"]
    if fails:
        return _step(f"the setup has a problem: {fails[0]}", AUTHOR, "`aidd doctor` lists every check and its fix", code="setup.doctor_fail")
    return None


def knowledge_steps(root: Path) -> list[dict]:
    """Learn feeds knowledge: each open postmortem action that targets a pack or a skill, owned by its owner."""
    from . import knowledge

    out = []
    for path in repo.object_files(root, repo.OPS_DIRS["postmortem"]):
        read = _read(path)
        if read is None:
            continue
        data, rel = read[0], path.relative_to(root).as_posix()
        for a in knowledge.open_actions(data):
            what = f"{data.get('id')}'s action {a.get('what')!r} changes the team's knowledge ({a['target']}), due {a.get('due')}"
            out.append(
                _step(what, AUTHOR, repo.knowledge_action_how(a), rel, code="knowledge.action")
                | {"id": str(data.get("id"))}
                | ({"owner": str(a["owner"])} if a.get("owner") else {})
            )
    return out


def _collect(root: Path, f: Filters, today: dt.date | None, now: dt.datetime | None) -> tuple[list[dict], list[Item]]:
    """Every step of the view `f` picks, most urgent first (`sort_key`), and the Specs it read (this branch's, or the
    backlog's)."""
    setup = _setup_step(root)
    if setup is not None:
        return [setup], []
    cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root), skip_unread=True)  # a display: an unread URL parent warns
    ctx = _Ctx(root, cfg, today or dt.date.today(), now or dt.datetime.now(dt.UTC), state.Observer(root, cfg), workitems.bots_of(cfg), f.all)
    from .localctx import platform_of

    ctx.local, ctx.team = platform_of(str(root)) == "local", repo.team_installed(root)
    objects: list[tuple[str, dict, str, str]] = []
    initiatives = set()
    for path in repo.object_files(root, cfg.specs_dir) + repo.object_files(root, cfg.proposals_dir):
        read = _read(path)
        if read is None:
            continue
        data, body, text = read
        objects.append((str(path.relative_to(root).as_posix()), data, body, text))
        if data.get("kind") == "initiative" and data.get("proposal"):
            initiatives.add(data["proposal"])
    steps: list[dict] = []
    if f.all:
        specs, extra = backlog(ctx)
    else:
        specs, extra = this_change(ctx, objects)
    steps += extra
    _derive(ctx)
    for it in specs:
        steps += spec_steps(it, ctx)
    if f.all:
        for it in ctx.items.values():
            if it.kind in ("epic", "initiative"):
                steps += container_steps(it, ctx)
        for rel, data, _, _ in objects:
            if data.get("kind") == "proposal" and (step := for_proposal(rel, data, initiatives)):
                due = data.get("due")
                if due and str(due) < ctx.today.isoformat() and step["status"] in ("exploring", "drafting", "signed_off"):
                    step["what"] += f" (it was due {due})"
                steps.append(step | {"group": workitems.group(data, step["status"])})
        for rel, data, flag in repo.overdue_flags([(r, d) for r, d, _, _ in objects], ctx.today):
            what = f"{data.get('id')}'s flag {flag.get('name')} was due for removal on {flag.get('cleanup_due')}"
            owner = {"owner": str(flag["owner"])} if flag.get("owner") else {}
            steps.append(
                _step(what, AUTHOR, repo.flag_cleanup(flag) + (" (/aidd-team:specify)" if ctx.team else ""), rel, code="flag.overdue")
                | {"id": str(data.get("id"))}
                | owner
            )
        steps += knowledge_steps(root)
        steps = [s for s in steps if s["code"] not in _NOTHING_TO_DO]
    else:  # the lane's step for this branch's diff, when no Spec on the branch carries the change
        steps += [s for s in [rules.lane_step(root, has_spec=bool(specs))] if s]
    _escalate(ctx, steps)
    if f.all:
        _ages(ctx, steps)
    if f.active():
        steps = _filter(ctx, steps, f)
    elif f.all:
        steps += _queue(ctx, steps, None) + _wip(ctx, steps)
    if not steps:
        steps.append(
            _step("nothing matches these filters", AUTHOR, "drop a filter, or `aidd list` for every open item", code="nothing_matches")
            if f.active()
            else _step(
                "nothing is open" + ("" if f.all else " on this branch"),
                AUTHOR,
                "describe the change to the agent (it checks the route with `aidd assess` and follows the loop); "
                + ("" if f.all else "`aidd list` shows the open work; ")
                + "for work someone outside the team must agree to first, `aidd new proposal`",
                code="nothing_open",
            )
        )
    for s in steps:
        s.setdefault("group", None)
    steps.sort(key=sort_key)
    return ([_as_owner(s) for s in steps] if f.all else steps), specs


def open_work(root: Path, today: dt.date | None = None, now: dt.datetime | None = None) -> tuple[list[dict], list[Item]]:
    """All open work, as `aidd list` shows it, and the Specs it read, each with its derived status: what autopilot
    (`autopilot.py`) decides from. Like `plan`, it runs the doctor's checks."""
    return _collect(root, Filters(all=True), today, now)


def plan(root: Path, today: dt.date | None = None, filters: Filters | None = None, now: dt.datetime | None = None) -> list[dict]:
    """The steps of one view, most urgent first (`sort_key`): this change's (`aidd assess`) by default, all open work
    (`aidd list`) with `filters.all`."""
    return _collect(root, filters or Filters(), today, now)[0]


# ---- The route of this change ---------------------------------------------------------------------------------

# Lowest to highest: an emergency is its own lane, above every other route.
_ROUTE_ORDER = ("standard", "minor", "normal", "major", "emergency")


def _declared(root: Path, specs: list[Item]) -> tuple[str, str] | None:
    """(route, by): the highest route this change declares, in a Spec on the branch or in the Change Request block of the
    newest branch commit that holds one (`aidd describe --commit`); None when it declares none."""
    found = [(str(it.data.get("route")), it.id) for it in specs if it.data.get("route") in _ROUTE_ORDER]
    if not found:
        cwd = str(root)
        try:
            fork = gitutil.merge_base(gitutil.rev_parse(inputs.default_base(cwd), cwd), gitutil.rev_parse("HEAD", cwd), cwd)
            block, _ = model.parse_change_block(inputs.commit_block(cwd, fork, "HEAD") or "")
        except (gitutil.GitError, OSError, ValueError):
            block = None
        if block and block.get("route") in _ROUTE_ORDER and not block.get("spec"):
            found = [(str(block["route"]), "the Change Request block")]
    if not found:
        return None
    return max(found, key=lambda x: _ROUTE_ORDER.index(x[0]))


def route_of(root: Path, specs: list[Item] | None = None, *, ctype: str = "feat") -> dict | None:
    """The route of this change: the higher of the minimum the branch's diff needs (`rules.assess_diff`) and the route
    the change declares (`_declared`), as the gate enforces it. The computed summary's fields, with `route` and `lane`
    the effective ones, plus `required` (the diff's minimum, or None), `declared` ({route, by}, or None), and `header`
    (one line). None when there is neither a diff nor a declaration."""
    computed = rules.assess_diff(root, ctype=ctype)
    declared = _declared(root, specs or [])
    if computed is None and declared is None:
        return None
    out: dict = dict(computed or {"reasons": [], "dimensions": [], "pools": [], "basis": "no diff yet", "paths": []})
    out["reasons"] = rules.reason_lines(out) if computed else []
    need = computed["route"] if computed else None
    route = max([r for r in (need, declared[0] if declared else None) if r], key=_ROUTE_ORDER.index)
    out |= {"route": route, "lane": rules.LANES[route], "required": need, "declared": {"route": declared[0], "by": declared[1]} if declared else None}
    head = f"Route: {route} ({out['lane']} lane)"
    if declared and need is None:
        out["header"] = f"{head}, set by {declared[1]}; the branch has no diff yet"
    elif declared and _ROUTE_ORDER.index(declared[0]) >= _ROUTE_ORDER.index(str(need)):
        out["header"] = f"{head}, set by {declared[1]}; " + ("the diff needs the same" if declared[0] == need else f"the diff alone needs {need}")
    elif declared:
        out["header"] = f"{head}, needed by the diff; {declared[1]} declares {declared[0]}, and the gate enforces the higher"
    else:
        out["header"] = f"{head}, needed by {out['basis']}"
    return out


def assess(
    root: Path,
    *,
    paths: list[str] | None = None,
    ctype: str | None = None,
    dimensions: list[str] | tuple[str, ...] = (),
    irreversible: bool = False,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """`aidd assess`: {"route", "steps", "overlaps"}. With `paths`, the route those planned paths need before any code
    exists and the lane's first step; else the route of this branch's change (`route_of`), the steps for the Specs it
    changes, and the other branches whose Specs overlap them."""
    if paths:
        setup = _setup_step(root)
        if setup is not None:
            return {"route": None, "steps": [setup], "overlaps": []}
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root), skip_unread=True)  # a display: an unread URL parent warns
        tracked = [p for p in gitutil.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
        a = rules.assess_paths(cfg, paths, ctype=ctype or "feat", dimensions=dimensions, irreversible=irreversible, tracked=tracked)
        n = len(paths)
        planned = rules.summary(a, f"the planned paths ({n} path{'s' if n != 1 else ''})") | {"paths": list(paths)}
        planned["reasons"] = rules.reason_lines(planned)
        if packs := rules.risk_packs(cfg, a.dimensions):
            planned["packs"] = packs
        planned |= {
            "required": planned["route"],
            "declared": None,
            "header": f"Route: {planned['route']} ({planned['lane']} lane), needed by {planned['basis']}",
        }
        step = rules.lane_step(root, has_spec=False, summary=planned)
        hint = rules.untested_feature_hint(paths, ctype=ctype or "feat", tracked=tracked) if step and step["lane"] == "fast" else None
        if step and hint:
            step["how"] += f". Also: {hint}"
        constraints = project.effective(cfg, list(paths), today)
        return {"route": planned, "steps": [step] if step else [], "overlaps": []} | ({"project": constraints} if constraints else {})
    steps, specs = _collect(root, Filters(), today, now)
    route = route_of(root, specs, ctype=ctype or "feat") if not steps[0]["code"].startswith("setup.") else None
    overlaps = [s for s in steps if s["code"].startswith("overlap")]
    constraints = project.effective(workitems.config_at(root), (route or {}).get("paths") or None, today) if route else None
    answer = {"route": route, "steps": [s for s in steps if not s["code"].startswith("overlap")], "overlaps": overlaps}
    return answer | ({"project": constraints} if constraints else {})


def markdown(steps: list[dict]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        age = "" if s.get("age_days") is None else f"[age {s['age_days']}d{', aging' if s.get('aged') else ''}] "
        lines.append(f"{i}. {age}{s['what']}")
        lines.append(f"   who: {s['who']}")
        lines.append(f"   how: {s['how']}")
        if s.get("why"):
            lines.append(f"   why: {workitems.why_text(s['why'])}")
    return "\n".join(lines) + "\n"


def assess_markdown(answer: dict) -> str:
    """`aidd assess` as text: the route header and its reasons, then this change's steps, then the overlaps."""
    route = answer.get("route")
    if route:
        out = [route["header"], *(f"  - {line}" for line in route["reasons"])]
        added = [p for p in route.get("packs") or [] if p.get("dependency")]
        if added:
            packs = ", ".join(f"`aidd-team:{p['pack']}` ({p['dependency']} in {p['file']})" for p in added)
            out.append(f"Domain packs the added dependencies call for: {packs}")
        if risky := [p for p in route.get("packs") or [] if p.get("reason")]:
            out.append("Domain packs its risk calls for: " + ", ".join(f"`aidd-team:{p['pack']}` ({p['reason']})" for p in risky))
    else:
        out = ["Route: none yet: this branch has no diff; `aidd assess --paths GLOB...` previews the route before any code"]
    if answer.get("steps"):
        out += ["", "Next for this change:", markdown(answer["steps"]).rstrip("\n")]
    if answer.get("overlaps"):
        out += ["", "Overlaps with other branches:", markdown(answer["overlaps"]).rstrip("\n")]
    if answer.get("project"):
        out += ["", *project.markdown(answer["project"])]
    return "\n".join(out) + "\n"
