"""This change's forecast and `aidd list`: what to do now, and who does it.

Anyone on the team, an engineer, a product manager, or a team lead, should be able to ask the repository what it is
waiting for and get one plain answer per piece of work: the step, who takes it (named by role: the agent, the author,
an Approver, a triager, or a decision maker), and the command. It reads only local state (the config, the Specs, the
proposals, the branches, the approvals recorded on this machine, and the evidence folder) and never changes anything.

Every status it shows is derived (`derived_status.py`): a Spec is ready once a counted Spec approval names its current hash,
in progress once commits change a Task's scope, in review once the evidence is green on head, and landed once it is
on the base branch. The stored `status` only answers where nothing local can (a platform's approvals live on the
PR/MR).

Two views:

- **This change** (`this_change`, and `forecast` in route_forecast.py): the route as a header (the higher of what the diff needs and what the
  branch's Spec or Change Request block declares), then the steps for the Specs this branch changes, read from the working
  tree, then the overlaps with other branches. The session hooks and autopilot read it; `aidd gate` prints the route and the
  overlaps on a branch, and `aidd gate --paths` forecasts the route of planned paths before any code exists.
- **All open work** (`backlog`, `aidd list`): one copy of every item, from the base branch and every open local
  and remote-tracking branch (the unmerged branch copy wins), with the open proposals and filters for the user's
  work, agents' Tasks, blocked work, a priority, and the Approver inbox (`--waiting-on-me`). Each Spec in progress
  carries its work item age, flagged once it passes `limits.max_in_progress_days`.

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

from aidd import config, gate, workitems
from aidd import setup as repo
from aidd.kernel import documents, git, globs
from aidd.kernel.timestamps import parse_time
from aidd.tracking import approval_changes, branch_overlaps, goal_status
from aidd.tracking.step import new_step

MERGE_WAIT = (
    "waits for Merge approval on its head commit",
    "review the PR/MR and its report, then type `merge it` (or `/aidd merge`), which approves this head there",
)
# The agent's land under the person's standing approval: `aidd land` tests what lands again and merges only if the gate
# passes, recording the Merge approval the standing approval covers.
AGENT_LAND = "`aidd land` on its branch: it runs the tests again on what lands, records the Merge approval, and merges only if the gate passes"
_NOTHING_TO_DO = ("spec.done", "spec.cancelled", "spec.integrated")
APPROVER_WAITS = ("spec.spec_approval", "spec.merge_approval", "goal.release")
_PRIORITY_RANK = {p: i for i, p in enumerate(workitems.PRIORITIES)}
# Work item age: the days a Spec may stay in progress before `aidd list` flags it, while limits.max_in_progress_days is
# unset. Two working weeks: a Spec sliced to its route's changed-line limit finishes well inside it.
MAX_IN_PROGRESS_DAYS = 10


# ---- One Spec's steps -----------------------------------------------------------------------------------------


def tasks(
    data: dict,
    status: str | None = None,
    facts: workitems.Facts | None = None,
    *,
    note: dict | None = None,
    approval: bool | None = None,
    blockers: list[str] | tuple[str, ...] = (),
) -> list[dict]:
    """The Spec's Tasks with their derived state (`derived_status.task_states`), for a coordinator that starts one agent per
    `todo` Task, each in its own worktree. Without `status`, the stored one answers; without `approval`, the default
    profile's routes say whether the Spec needs Spec approval."""
    approval = workitems.needs_spec_approval(data, None) if approval is None else approval
    return workitems.task_states(data, status or workitems.spec_status(data, facts, approval=approval), facts, note=note, approval=approval, blockers=blockers)


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
    covered: bool = False,
    integrated: bool = False,
    publish_first: bool = False,
    publishes: bool = False,
) -> dict:
    """The Spec's next step. `local`: the local gate is the gate (no platform), so a person approves and lands by typing
    it (`approve SPEC-1`, `land it`); `team`: the aidd-team roles are installed, so the step may name their commands;
    `covered`: the person's standing approval covers its route (workitems.standing_covers), so the agent records each
    approval and lands it; `integrated`: its goal branch holds it (`aidd integrate` landed it there); `publish_first`:
    the trunk lives on a platform and this branch is not there yet, so it is published before its Merge approval;
    `publishes`: agents publish here (`publish: agents`, or the person's `approve all and publish`)."""
    sid = data.get("id", rel)
    goal = str(data.get("base") or "")
    goal = goal if goal.startswith(workitems.GOAL_PREFIX) else ""
    if data.get("route") == "emergency" and not (data.get("outcome") or {}).get("learn_ref") and status not in ("cancelled", "rolled_back"):
        due = (data.get("emergency") or {}).get("review_due")
        if status in ("landed", "done"):
            what = f"{sid} restored service: complete the backfill Spec and the post-incident review by {due}"
            return new_step(what, workitems.AGENT, f"/aidd-team:postmortem, then record outcome.learn_ref in {rel}", rel, code="spec.backfill") | {
                "emergency": True
            }
        what = f"{sid} is an emergency: restore service first, then complete the Spec before {due}"
        how = "repair it inside the declared scope, `aidd test` the smoke tests, and land it with the route's approvals and the commander's"
        return new_step(what, workitems.AGENT, how, rel, code="spec.emergency") | {"emergency": True}
    if waits:
        return new_step(
            f"{sid} is blocked by {', '.join(waits)}: it starts when they finish",
            workitems.AUTHOR,
            "finish or re-plan what it waits for; `aidd list --blocked` lists every blocked item",
            rel,
            code="spec.blocked_by",
        ) | {"waiting_on": waits}
    if blockers:
        return new_step(
            f"{sid} is blocked: {'; '.join(blockers)}",
            workitems.AUTHOR,
            "clear the blocker (then remove blockers), or re-plan",
            rel,
            code="spec.blocked",
        )
    if status == "draft" and approval and committed and covered:
        what = f"{sid} waits for Spec approval: your standing approval covers it"
        return new_step(
            what, workitems.AGENT, f"`aidd approve spec {rel}`, which records it under the standing approval", rel, code="spec.spec_approval_standing"
        )
    if status == "draft" and approval and committed:
        how = (
            f"read the Spec, its tests, and its design, then type `approve {sid}` (or `/aidd approve {sid}`)"
            if local
            else f"read the Spec, its tests, and its design, then type `approve {sid}`, which posts the approval on the pull request as you"
        )
        return new_step(f"{sid} waits for Spec approval", workitems.APPROVER, how, rel, code="spec.spec_approval")
    specify = "/aidd-team:specify, then " if team else "finish the Spec and its tests, then "
    if local:
        freeze = f"; a person types `approve {sid}`" + ("" if approval else " (optional on this route; it freezes them)")
    else:
        freeze = f"; an Approver types `approve {sid}`"
    build = "/aidd-team:implement, then " if team else "implement it, then "
    if goal and integrated and status not in ("landed", "done", "rolled_back", "cancelled"):
        what = f"{sid} is integrated into {goal}: it goes out with the goal's release"
        return new_step(
            what,
            workitems.AUTHOR,
            f"nothing for now: the release of {goal} to the default branch asks for the person's Merge approval",
            rel,
            code="spec.integrated",
        )
    if goal and status == "in_review":
        what = f"{sid} is built and green: integrate it into {goal}"
        how = "verify and review it on this head, then `aidd integrate` on its branch: it tests the merge with the goal and lands it once the gate waits only for the release"
        return new_step(what, workitems.AGENT, how, rel, code="spec.integrate")
    if publish_first and status == "in_review" and not goal:
        if publishes:
            how = "`aidd publish` on its branch: it pushes the branch, opens its PR/MR, and carries the Spec approval there"
            return new_step(f"{sid} is built and reviewed: publish it", workitems.AGENT, how, rel, code="spec.publish_standing")
        how = f"read the verifier's and the reviewer's reports (the latest handoff notes in {rel}), then type `publish` (or `/aidd publish`): aidd pushes this branch, opens its PR/MR, and carries your approvals there; then `merge it` once `aidd/gate` passes"
        return new_step(f"{sid} is built and reviewed: it waits for you to publish it", workitems.APPROVER, how, rel, code="spec.publish")
    if covered and status == "in_review":
        if local:
            what = f"{sid} waits for Merge approval: your standing approval covers it, so land it"
            return new_step(what, workitems.AGENT, AGENT_LAND, rel, code="spec.land_standing")
        how = "`aidd approve merge`, which posts the approval on the PR/MR as you; it merges once `aidd/gate` passes (turn on its auto-merge)"
        return new_step(f"{sid} waits for Merge approval: your standing approval covers it", workitems.AGENT, how, rel, code="spec.merge_approval_standing")
    lander = "`aidd test`, `aidd gate`, and `aidd land`" if covered else "`aidd test` and `aidd gate`; a person types `land it`"
    steps = {
        "draft": (
            f"{sid} needs its Spec and tests finished" + (", then Spec approval" if approval else ""),
            workitems.AGENT,
            f"{specify}`aidd validate {rel}` and commit the Spec and its tests{freeze}",
        ),
        "ready": (
            f"{sid}: Spec approval recorded; implement it inside its scope",
            workitems.AGENT,
            build + (lander if local else "`aidd test`, then push it to its PR/MR"),
        ),
        "in_progress": (f"{sid} is being built: finish its Tasks and get the tests green", workitems.AGENT, "`aidd test`, then `aidd gate` locally"),
        "in_review": (
            f"{sid} {MERGE_WAIT[0]}",
            workitems.APPROVER,
            f"read the verifier's and the reviewer's reports (the latest handoff notes in {rel}), then type `land it` (or `/aidd land`)"
            if local
            else MERGE_WAIT[1],
        ),
        "landed": (
            f"{sid} is landed: watch its observe window",
            workitems.AGENT,
            f"`aidd observe {rel} --write`; if the rollback trigger fires, a person rolls back and records outcome.rolled_back",
        ),
        "rolled_back": (
            f"{sid} was rolled back: learn from it",
            workitems.AGENT,
            "/aidd-team:postmortem" if team else "write the postmortem: `aidd new postmortem`",
        ),
    }
    what, who, how = steps.get(status) or (f"{sid} is {status}: nothing to do", workitems.AUTHOR, "none")
    # A built Spec's step is named for what it waits on, the person's Merge approval; every other is named for its status.
    return new_step(what, who, how, rel, code="spec.merge_approval" if status == "in_review" else f"spec.{status}")


def eligible(data: dict, cfg: config.Config) -> list[str]:
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
    facts: workitems.Facts = field(default_factory=workitems.Facts)
    status: str = "draft"

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.rel)

    @property
    def kind(self) -> str:
        return str(self.data.get("kind"))


@dataclass
class Filters:
    """What a view shows. By default, this branch's Specs (`forecast`); `all` reads all open work instead (`aidd list`),
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
    cfg: config.Config
    today: dt.date
    now: dt.datetime
    obs: workitems.Observer
    bots: set[str]
    backlog: bool
    items: dict[str, Item] = field(default_factory=dict)  # every work item by id
    status: dict[str, str] = field(default_factory=dict)  # derived status by id
    progress: dict[str, tuple[int, int]] = field(default_factory=dict)  # container id -> (finished, children)
    by_where: dict[str, Item] = field(default_factory=dict)
    local: bool = False  # the local gate is the gate: no platform
    trunk_on_platform: bool = False  # a remote runs the aidd gate: work reaches the trunk through a PR/MR
    publishes: bool = False  # agents publish: `publish: agents`, or the person's `approve all and publish`
    team: bool = True  # the aidd-team roles are installed
    standing: dict | None = None  # the person's standing approval in force (workitems.live_standing)
    integrations: dict[str, dict[str, str]] = field(default_factory=dict)  # goal branch -> {Spec id: head integrated}

    def integrated_into(self, goal: str) -> dict[str, str]:
        """The Specs `goal` holds (workitems.integrated), read once per goal; nothing for a base that is no goal branch."""
        if not goal.startswith(workitems.GOAL_PREFIX):
            return {}
        if goal not in self.integrations:
            self.integrations[goal] = workitems.integrated(str(self.root), goal)
        return self.integrations[goal]

    @property
    def idx(self) -> dict[str, dict]:
        return {i: it.data for i, it in self.items.items()}


def _read(path: Path) -> tuple[dict, str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
        data, body = documents.split_front_matter(text, str(path))
        return data, body, text
    except (documents.DocumentError, OSError, UnicodeDecodeError):
        return None


def _derive(ctx: _Ctx) -> None:
    """Every item's derived status: Specs from their facts, then Epics from their children, then Initiatives."""
    specs = {it.id: ctx.obs.status(it.facts, it.data) for it in ctx.items.values() if it.kind == "spec"}
    ctx.status, ctx.progress, _ = workitems.container_statuses([it.data for it in ctx.items.values()], specs)
    for it in ctx.items.values():
        it.status = ctx.status.get(it.id, it.status)


def _lets_go(ctx: _Ctx):
    return lambda i: workitems.status_unblocks(ctx.status.get(i, "draft"))


def this_change(ctx: _Ctx, objects: list[tuple[str, dict, str, str]]) -> tuple[list[Item], list[dict]]:
    """The branch view: the Specs this branch changes, from the working tree, and the other branches they overlap.
    Every other item joins the index as the base branch holds it (then as the working tree does, for one the base
    lacks), so the why chain and blocked_by read the same derived statuses the backlog shows."""

    obs = ctx.obs
    mine = workitems.active_specs(str(ctx.root), ctx.cfg)
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
            facts = obs.at(obs.base_sha, rel, text, data) if data.get("kind") == "spec" else workitems.Facts()  # type: ignore[arg-type]
            ctx.items[str(data["id"])] = Item(rel, data, body, text, ref=obs.base, sha=obs.base_sha, facts=facts)
    for rel, data, body, text in objects:
        if data.get("kind") in workitems.WORK_KINDS and data.get("id") and str(data["id"]) not in ctx.items:
            ctx.items[str(data["id"])] = Item(rel, data, body, text, facts=workitems.Facts())
    return ours, branch_overlaps.overlaps(ctx.root, ctx.cfg.specs_dir, mine)


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
            new_step(
                f"only the first {workitems.MAX_OBJECTS} objects under {ctx.cfg.specs_dir}/ were read",
                workitems.AUTHOR,
                "archive finished Specs to another folder",
                code="backlog.capped",
            )
        )
    chosen: dict[str, Item] = {}
    if obs.base:
        refs, total = branch_overlaps.branches(root, obs.base, include_here=True)
        if total > branch_overlaps.MAX_BRANCHES:
            steps.append(branch_overlaps.capped_step(total))
        for ref, sha in refs:  # the merged ones are left out already: their copies are the base's now
            if not sha or sha == obs.base_sha:
                continue
            fork = obs.fork(sha)
            if not fork:
                continue
            changed = [p for p in git.run(["diff", "--name-only", "-z", fork, sha, "--", ctx.cfg.specs_dir], cwd, check=False).split("\0") if p.endswith(".md")]
            for rel, data, body, text in workitems.read_at(root, sha, changed):
                oid = str(data.get("id") or "")
                if data.get("kind") not in workitems.WORK_KINDS or not oid or oid in chosen:
                    continue
                facts = obs.at(sha, rel, text, data) if data.get("kind") == "spec" else workitems.Facts()
                chosen[oid] = Item(rel, data, body, text, ref=ref, sha=sha, facts=facts)
    for rel, data, body, text in found:
        oid = str(data.get("id") or "")
        if data.get("kind") not in workitems.WORK_KINDS or not oid or oid in chosen:
            continue
        facts = obs.at(base_ref, rel, text, data) if data.get("kind") == "spec" else workitems.Facts()
        chosen[oid] = Item(rel, data, body, text, ref=obs.base, sha=base_ref, facts=facts)
    ctx.items.update(chosen)
    return [it for it in chosen.values() if it.kind == "spec"], steps


# ---- Steps ----------------------------------------------------------------------------------------------------


def _changed_since_approval(rel: str, data: dict) -> str:
    """For a Spec on this checkout that waits for Spec approval again: what changed since its last approval, the files
    the approval dialog shows first (approval_changes), so the Approver sees it in the list; '' on a first approval."""
    try:
        text = git.show("HEAD", rel)
        h = workitems.spec_hash(text, git.ls_tree("HEAD"), lambda p: git.show("HEAD", p)) if text is not None else None
    except (git.GitError, documents.DocumentError):
        return ""
    since = approval_changes.changed_since(rel, data, h, "HEAD") if h else None
    files = (since or {}).get("files") or []
    if not since or not files:
        return ""
    shown = ", ".join(f"{f['path']} (+{f['added']} -{f['removed']})" for f in files[:3]) + (f", and {len(files) - 3} more" if len(files) > 3 else "")
    return f" again: {len(files)} file{'s' if len(files) > 1 else ''} changed since its last approval at {since['commit'][:12]}: {shown}"


def spec_steps(it: Item, ctx: _Ctx) -> list[dict]:
    """A Spec's steps: a person's triage first when an agent suggested it, then its next step (blocked while it waits
    on unfinished work), then a person's decision its latest handoff note asks for. Nothing for a Spec whose triage
    declined it or snoozed it until a later date, or that `duplicates` another."""
    data, rel = it.data, it.rel
    triage = workitems.triage_state(data, ctx.bots, ctx.today)
    if triage == "hidden" or workitems.is_duplicate(data):
        return []
    sid, status = it.id, it.status
    approval = ctx.obs.needs_spec_approval(data)
    extra: dict = {
        "id": sid,
        "status": status,
        "group": workitems.group(data, status),
        "labels": list(data.get("labels") or []),
        "priority": workitems.item_priority(data, ctx.idx),
        "why": workitems.why(data, ctx.idx, ctx.cfg, ctx.progress),
    }
    if data.get("owner"):
        extra["owner"] = str(data["owner"])
    if files := workitems.item_files(ctx.root, ctx.cfg.specs_dir, sid):  # what its folder, specs/<ID>/, holds
        extra["files"] = files
    if it.ref and ctx.backlog:
        extra["branch"] = it.ref
    if str(data.get("base") or "").startswith(workitems.GOAL_PREFIX):
        extra["goal"] = str(data["base"])  # the goal branch it lands in: `aidd list --json` groups a goal's Specs by it
    if triage == "needed":
        t = data.get("triage") or {}
        what = (
            f"{sid}'s snooze ended on {t.get('until')}: decide on it again"
            if t.get("decision") == "snoozed"
            else f"{sid} was suggested by {data.get('suggested_by')}: accept it, decline it, or snooze it (a duplicate: relate it with `duplicates`)"
        )
        how = (
            f'record `triage: {{decision: accepted, by: "<you>", triaged_on: "{ctx.today.isoformat()}"}}` in {rel} '
            "(or declined; snoozed with until; for a duplicate, `relations: [{type: duplicates, id: <the other>}]`)"
        )
        return [new_step(what, workitems.PERSON, how, rel, code="spec.triage") | extra | {"blocked": False}]
    waits = workitems.waiting_on(data, ctx.idx, _lets_go(ctx)) if status in workitems.CAN_WAIT else []
    blockers = workitems.blocked_reasons(data, status, waits)
    note = workitems.latest_handoff(it.body) if it.body else None
    committed = bool(it.facts.committed) or it.ref is not None
    # A draft that is not finished (placeholders in what the gate runs) goes back to Specify, never to an Approver or
    # to Implement; `unready` says why, and autopilot keeps it in Specify however its last run ended.
    unready = workitems.unready_for_approval(it.text, rel) if status == "draft" and committed else []
    # A launch (the Spec that turns a flagged feature on) is the person's: their standing approval never lands it.
    covered = workitems.standing_covers(ctx.standing, str(data.get("route") or "normal")) and not workitems.is_launch(data, ctx.idx)
    step = _spec_step(
        rel,
        data,
        status,
        committed=committed and not unready,
        approval=approval,
        blockers=blockers,
        waits=waits,
        local=ctx.local,
        team=ctx.team,
        covered=covered,
        integrated=sid in ctx.integrated_into(str(data.get("base") or "")),
        publish_first=ctx.local and ctx.trunk_on_platform,
        publishes=ctx.publishes,
    )
    if unready:
        step["unready"] = unready[0]
    step["tasks"] = workitems.task_states(data, status, it.facts, note=note, approval=approval, blockers=blockers)
    nxt = (note or {}).get("next")
    if nxt in workitems.role_ids() and step["who"] == workitems.AGENT:
        step["who"] = f"{workitems.AGENT} ({nxt})"
    step |= extra | {"blocked": bool(blockers)}
    if step["code"] == "spec.spec_approval" and it.ref is None:
        step["what"] += _changed_since_approval(rel, data)
    if step["code"] in APPROVER_WAITS:
        step["approvers"] = eligible(data, ctx.cfg)
    if note:
        step["handoff"] = note
    ctx.by_where[rel] = it
    steps = [step]
    asked = workitems.needs(note, status)
    if asked and step["code"] not in _NOTHING_TO_DO:
        how = f"decide it and write the answer in {rel} or the PR/MR, where the agent reads it back"
        steps.append(new_step(f"{sid} needs a person: {'; '.join(asked)}", workitems.AUTHOR, how, rel, code="spec.needs") | extra | {"blocked": False})
    # A Task only a person can do (an account, a payment, a vendor call, a test on a device): it waits on that person,
    # and no agent starts it. `done: true` is bookkeeping, so marking it never voids Spec approval.
    for t in step.get("tasks") or []:
        who = str(t.get("assignee") or "")
        if t.get("status") == "todo" and who and not who.startswith("agent:"):
            what = f"{sid} {t.get('id')} waits on {who}: {t.get('title') or 'a Task for a person'}"
            how = f"do it, then record `done: true` on {t.get('id')} in {rel} (or tell the agent it is done; it records it)"
            steps.append(new_step(what, who, how, rel, code="spec.task_person") | extra | {"blocked": False, "id": sid})
    due = workitems.outcome_due(data, status, ctx.today)
    if due is not None:
        how = f"measure the metric the hypothesis names and record outcome.result (met, missed, or inconclusive, with the number) in {rel}"
        steps.append(
            new_step(f"{sid}'s hypothesis was due {due}: record the outcome", workitems.AUTHOR, how, rel, code="spec.outcome_due") | extra | {"blocked": False}
        )
    return steps


def _launch_step(it: Item, ctx: _Ctx) -> list[dict]:
    """A flagged Epic whose planned Specs have all landed, and whose launch Spec nobody has written yet: write it. Its
    Merge approval, the launch, stays the person's."""
    launch = str(it.data.get("launch") or "")
    planned = [str(s) for s in it.data.get("specs") or [] if str(s) != launch]
    if workitems.reaches(it.data) != "flagged" or not launch or launch in ctx.items or not planned:
        return []
    if any(ctx.status.get(s) not in ("landed", "done", "cancelled") for s in planned):
        return []
    flags = sorted({str(f.get("name")) for s in planned for f in (ctx.items[s].data.get("flags") or []) if s in ctx.items and isinstance(f, dict)})
    what = f"{it.id} is built behind {', '.join(flags) or 'its flag'}: write the launch Spec {launch}, which turns it on"
    how = f"`aidd new spec {launch} --parent {it.id}`; its Merge approval is the launch, which stays the person's" + (
        " (/aidd-team:specify)" if ctx.team else ""
    )
    return [new_step(what, workitems.AGENT, how, it.rel, code="epic.launch_spec") | {"id": it.id, "status": it.status, "blocked": False}]


def container_steps(it: Item, ctx: _Ctx) -> list[dict]:
    """In the backlog: close an Epic or Initiative once every child is finished; a person decides. A flagged Epic's launch
    Spec, once its other Specs have landed."""
    if it.kind == "epic" and (launch := _launch_step(it, ctx)):
        return launch
    done, total = ctx.progress.get(it.id, (0, 0))
    if it.status in ("done", "cancelled") or not total or done < total:
        return []
    what = f"close {it.id}: {done}/{total} children finished"
    how = f'record status: "done" in {it.rel} (or "cancelled" if it was stopped), on the base branch'
    return [
        new_step(what, workitems.AUTHOR, how, it.rel, code=f"{it.kind}.close")
        | {
            "id": it.id,
            "status": it.status,
            "group": workitems.group(it.data, it.status),
            "priority": workitems.item_priority(it.data, ctx.idx),
            "blocked": False,
        }
        | ({"files": files} if (files := workitems.item_files(ctx.root, ctx.cfg.specs_dir, it.id)) else {})
    ]


def for_proposal(rel: str, data: dict, initiatives: set[str]) -> dict | None:
    """A proposal's next step in its derived status (`spec_file.proposal_status`)."""
    status, pid = workitems.proposal_status(data), data.get("id", rel)
    record = f'record `outcome: {{decision: <decision>, by: "@you", decided_on: YYYY-MM-DD}}` in {rel}'
    steps = {
        "qualifying": (f"{pid} waits for a go/no-go decision", workitems.COMMIT, f"read the needs and questions, then record `go_no_go` in {rel}"),
        "drafting": (f"{pid} is being drafted", workitems.AGENT, "/aidd-team:propose, then `aidd validate` and `aidd proposal matrix`"),
        "signed_off": (
            f"{pid} is signed off: send it to {data.get('addressee')}",
            workitems.AUTHOR,
            f"send it, then {record.replace('<decision>', 'submitted')}",
        ),
        "submitted": (
            f"{pid} waits for {data.get('addressee')} to decide",
            workitems.AUTHOR,
            f"when they answer, {record.replace('<decision>', 'accepted')} (or rejected, withdrawn)",
        ),
    }
    if status == "accepted" and pid not in initiatives:
        steps["accepted"] = (f"{pid} was accepted: turn it into delivery work", workitems.AUTHOR, f"`aidd proposal convert {rel}`, then /aidd-team:plan")
    found = steps.get(status)
    if not found:
        return None
    return new_step(*found, rel, code=f"proposal.{status}") | {"id": pid, "status": status}


def _waiting_since(ctx: _Ctx, step: dict) -> dt.datetime | None:
    """When the wait began: for Merge approval, the head commit the evidence is green on; for Spec approval, the last
    commit that touched the Spec (the one that asked for the approval). None while the Spec is uncommitted."""
    it = ctx.by_where.get(step["where"])
    ref, cwd = (it.sha if it and it.sha else "HEAD"), str(ctx.root)
    if step["code"] == "spec.merge_approval":
        return parse_time(git.run(["log", "-1", "--format=%cI", ref], cwd, check=False).strip())
    return parse_time(git.run(["log", "-1", "--format=%cI", ref, "--", step["where"]], cwd, check=False).strip())


def _escalate(ctx: _Ctx, steps: list[dict]) -> None:
    """Mark each Approver wait older than limits.escalate_after_minutes and name the backup pool. It changes what this
    list says, never who may approve or what the gate decides."""
    limit = int(ctx.cfg.limits.get("escalate_after_minutes") or 0)
    if not limit:
        return
    backups = [str(b) for b in ctx.cfg.get("owners", "backup_approvers", default=[]) or []]
    for s in steps:
        if s["code"] not in APPROVER_WAITS:
            continue
        since = _waiting_since(ctx, s)
        if since is None:
            continue
        minutes = int((ctx.now - since).total_seconds() // 60)
        s["waiting_minutes"] = minutes
        if minutes > limit:
            s["escalated"] = True
            s["backup_approvers"] = backups
            s["what"] += f" (waiting {age_text(minutes)}, past limits.escalate_after_minutes = {limit})"
            s["how"] += (
                f"; past the limit: ask a backup approver ({', '.join(backups)})"
                if backups
                else "; past the limit, and no owners.backup_approvers are named: ask another eligible Approver"
            )


def _entered(ctx: _Ctx, it: Item) -> dt.datetime | None:
    """When the Spec entered in progress. On a branch: the earliest author date (a rebase keeps it) of the commits since
    the fork that changed a Task's scope, the fact that derives in_progress. A cherry-pick may put an older date after a
    newer one, so every date counts. Where the stored status answered instead: the committer date of the commit that
    set it, as `aidd log` (spec_history) reads it. None when neither says, and in a shallow clone, whose history is cut."""
    sha = it.sha or ctx.obs.head
    if not sha or ctx.obs.is_shallow_clone:
        return None
    fork = ctx.obs.fork(sha) if it.facts.changed is not None else None
    scopes = [str(g) for t in it.data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    if fork and scopes:
        specs = [f":(glob){g}**" if g.endswith("/") else f":(glob){g}" for g in scopes]
        out = git.run(["log", "--format=%aI", f"{fork}..{sha}", "--", *specs], str(ctx.root), check=False).split()
        dates = [d for d in map(parse_time, out) if d is not None]
        if dates:
            return min(dates)
    held = workitems.status_transitions(ctx.root, it.rel, ctx.now, ref=sha)
    return parse_time(held[-1]["since"]) if held and held[-1]["status"] == "in_progress" else None


def _ages(ctx: _Ctx, steps: list[dict]) -> None:
    """Work item age: on each step of a Spec in progress, `age_days` since it entered in progress, and `aged` once that
    passes limits.max_in_progress_days (MAX_IN_PROGRESS_DAYS while unset; 0 turns the flag off). One or two git log
    calls per Spec in progress. A queue signal for people, like `_escalate`; the gate never reads it."""
    raw = ctx.cfg.limits.get("max_in_progress_days")
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
                s["how"] += f"; aging: past limits.max_in_progress_days = {limit}, so finish it before new work starts, or split it"


def age_text(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} minutes"
    if minutes < 2 * 24 * 60:
        return f"{minutes // 60} hours"
    return f"{minutes // (24 * 60)} days"


def _queue(ctx: _Ctx, steps: list[dict], only: set[str] | None) -> list[dict]:
    """A warning for each Approver who holds more open waits than limits.max_open_per_approver (only the user's own
    when `only` names them). A queue signal for people; the gate never reads it."""
    limit = int(ctx.cfg.limits.get("max_open_per_approver") or 0)
    if not limit:
        return []
    held: dict[str, list[str]] = {}
    for s in steps:
        for a in s.get("approvers", []) if s["code"] in APPROVER_WAITS else []:
            held.setdefault(a, []).append(str(s["where"]))
    backups = [str(b) for b in ctx.cfg.get("owners", "backup_approvers", default=[]) or []]
    out = []
    for who, waits in sorted(held.items()):
        if len(waits) <= limit or (only is not None and not workitems.is_me(who, only)):
            continue
        out.append(
            new_step(
                f"{'you hold' if only is not None else who + ' holds'} {len(waits)} open approval waits, more than limits.max_open_per_approver = {limit}",
                workitems.AUTHOR,
                "finish a review before another Spec asks for one, or share them with another eligible Approver"
                + (f" (backups: {', '.join(backups)})" if backups else ""),
                code="approver.over_limit",
            )
            | {"approver": who, "waits": waits}
        )
    return out


def _wip(ctx: _Ctx, steps: list[dict]) -> list[dict]:
    """A warning for each person whose Specs in progress (by `owner`) exceed limits.max_in_progress_per_owner. A queue
    signal for people, like `_queue`; the gate never reads it."""
    limit = int(ctx.cfg.limits.get("max_in_progress_per_owner") or 0)
    if not limit:
        return []
    held: dict[str, set[str]] = {}
    for s in steps:
        if s.get("status") == "in_progress" and s.get("owner") and s["code"].startswith("spec."):
            held.setdefault(s["owner"], set()).add(str(s["where"]))
    return [
        new_step(
            f"{who} holds {len(specs)} Specs in progress, more than limits.max_in_progress_per_owner = {limit}",
            workitems.AUTHOR,
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
        waits_on_me = s["code"] in APPROVER_WAITS and any(workitems.is_me(a, me) for a in s.get("approvers", []))
        if f.waiting_on_me and not (waits_on_me or (s["code"] == "spec.task_person" and workitems.is_me(s.get("who"), me))):
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
    """Humans' decisions first, then the author's, then the agent's."""
    if who in (workitems.APPROVER, workitems.PERSON, workitems.COMMIT):
        return 0
    if who == workitems.AUTHOR:
        return 1
    return 2 if who.startswith(workitems.AGENT) else 3


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
    if s["who"] == workitems.AUTHOR:
        return s | {"who": owner}
    if s["who"].startswith(workitems.AGENT):
        return s | {"who": f"{owner}'s agent" + s["who"][len(workitems.AGENT) :]}
    return s


def setup_step(root: Path) -> dict | None:
    """The only step while aidd is not set up, or its setup fails a check; None when it is ready."""
    if not (root / config.CONFIG_PATH).is_file():
        return new_step(
            "aidd is not set up in this repository",
            workitems.AUTHOR,
            'ask the agent: "Install thaithienvanid/aidd and apply it to this project", or run `aidd init`',
            code="setup.missing",
        )
    fails = [msg for level, msg in repo.doctor(root, failures_only=True) if level == "fail"]
    if fails:
        return new_step(f"the setup has a problem: {fails[0]}", workitems.AUTHOR, "`aidd doctor` lists every check and its fix", code="setup.doctor_fail")
    return None


def knowledge_steps(root: Path) -> list[dict]:
    """Learn feeds knowledge: each open postmortem action that targets a pack or a skill, owned by its owner."""
    from aidd import knowledge

    out = []
    for path in workitems.object_files(root, workitems.OPS_DIRS["postmortem"]):
        read = _read(path)
        if read is None:
            continue
        data, rel = read[0], path.relative_to(root).as_posix()
        for a in knowledge.open_actions(data):
            what = f"{data.get('id')}'s action {a.get('what')!r} changes the team's knowledge ({a['target']}), due {a.get('due')}"
            out.append(
                new_step(what, workitems.AUTHOR, workitems.knowledge_action_how(a), rel, code="knowledge.action")
                | {"id": str(data.get("id"))}
                | ({"owner": str(a["owner"])} if a.get("owner") else {})
            )
    return out


def collect(root: Path, filters: Filters, today: dt.date | None, now: dt.datetime | None) -> tuple[list[dict], list[Item]]:
    """Every step of the view `filters` picks, most urgent first (`sort_key`), and the Specs it read (this branch's, or the
    backlog's)."""
    setup = setup_step(root)
    if setup is not None:
        return [setup], []
    cfg = config.load_file(config.CONFIG_PATH, str(root), skip_unread=True)  # a display: an unread URL parent warns
    ctx = _Ctx(root, cfg, today or dt.date.today(), now or dt.datetime.now(dt.UTC), workitems.Observer(root, cfg), workitems.bots_of(cfg), filters.all)

    ctx.local, ctx.team = gate.platform_of(str(root)) == "local", config.team_installed(root)
    ctx.standing = workitems.live_standing_for(cfg, str(root))
    ctx.trunk_on_platform = gate.trunk_on_platform(str(root))
    ctx.publishes = gate.agents_publish(str(root)) or workitems.standing_publishes(ctx.standing)
    objects: list[tuple[str, dict, str, str]] = []
    initiatives = set()
    for path in workitems.object_files(root, cfg.specs_dir) + workitems.object_files(root, cfg.proposals_dir):
        read = _read(path)
        if read is None:
            continue
        data, body, text = read
        objects.append((str(path.relative_to(root).as_posix()), data, body, text))
        if data.get("kind") == "initiative" and data.get("proposal"):
            initiatives.add(data["proposal"])
    steps: list[dict] = []
    if filters.all:
        specs, extra = backlog(ctx)
    else:
        specs, extra = this_change(ctx, objects)
    steps += extra
    _derive(ctx)
    for it in specs:
        steps += spec_steps(it, ctx)
    if filters.all:
        for it in ctx.items.values():
            if it.kind in ("epic", "initiative"):
                steps += container_steps(it, ctx)
        for rel, data, _, _ in objects:
            if data.get("kind") == "proposal" and (step := for_proposal(rel, data, initiatives)):
                due = data.get("due")
                if due and str(due) < ctx.today.isoformat() and step["status"] in ("qualifying", "drafting", "signed_off"):
                    step["what"] += f" (it was due {due})"
                steps.append(step | {"group": workitems.group(data, step["status"])})
        # A removal counts once its Spec has landed (the derived status), so a draft that removes one never hides it.
        fronts = [(r, d) for r, d, _, _ in objects]
        pending = workitems.pending_removals(fronts, ctx.status, "removes_flags")
        for rel, data, flag in workitems.overdue_flags(fronts, ctx.today, ctx.status):
            what = f"{data.get('id')} adds the flag {flag.get('name')}, which was due for removal on {flag.get('cleanup_due')}"
            owner = {"owner": str(flag["owner"])} if flag.get("owner") else {}
            how = workitems.flag_cleanup(flag, pending.get(str(flag.get("name")))) + (" (/aidd-team:specify)" if ctx.team else "")
            steps.append(new_step(what, workitems.AUTHOR, how, rel, code="flag.overdue") | {"id": str(data.get("id"))} | owner)
        pending = workitems.pending_removals(fronts, ctx.status, "removes_deprecations")
        for rel, data, dep in workitems.overdue_deprecations(fronts, ctx.today, ctx.status):
            what = f"{data.get('id')} deprecates {dep.get('what')}, whose sunset passed on {dep.get('sunset')}"
            how = workitems.deprecation_removal(dep, pending.get(str(dep.get("what")))) + (" (/aidd-team:specify)" if ctx.team else "")
            steps.append(new_step(what, workitems.AUTHOR, how, rel, code="deprecation.overdue") | {"id": str(data.get("id"))})
        steps += knowledge_steps(root)
        if workitems.goal_branches(str(root)):
            majors = {it.id for it in ctx.items.values() if it.kind == "spec" and it.data.get("route") in ("major", "emergency")}
            approvers = [str(a) for a in cfg.approvers or []]
            steps += [
                s | ({"approvers": approvers} if s["code"] in APPROVER_WAITS else {})
                for s in goal_status.goal_steps(goal_status.goals(root, cfg, steps), ctx.standing, majors)
            ]
        steps = [s for s in steps if s["code"] not in _NOTHING_TO_DO]
    else:  # the lane's step for this branch's diff, when no Spec on the branch carries the change
        steps += [s for s in [gate.lane_step(root, has_spec=bool(specs))] if s]
    _escalate(ctx, steps)
    if filters.all:
        _ages(ctx, steps)
    approver_waits = sum(1 for s in steps if s.get("code") in APPROVER_WAITS)
    if filters.active():
        steps = _filter(ctx, steps, filters)
    elif filters.all:
        steps += _queue(ctx, steps, None) + _wip(ctx, steps)
    if not steps:
        only_mine = filters.waiting_on_me and not (
            filters.mine or filters.agent is not None or filters.blocked or filters.label is not None or filters.priority is not None
        )
        # A miss on who you are reads as "nothing waits": say who aidd took you for, and how to name yourself.
        mine = sorted(i for i in workitems.my_identities(ctx.root) if i.startswith(("@", "email:"))) if only_mine and approver_waits else []
        unmatched = (
            f"{approver_waits} item{'s wait' if approver_waits != 1 else ' waits'} on an Approver, none matched to you "
            f"({', '.join(mine) or 'no identity found'}, from git and gh); if one is yours, `git config github.user <your login>`"
        )
        steps.append(
            new_step(
                "nothing waits on you" + (f"; {unmatched}" if approver_waits else ""),
                workitems.AUTHOR,
                "`aidd list` shows all open work",
                code="nothing_matches",
            )
            if only_mine
            else new_step("nothing matches these filters", workitems.AUTHOR, "drop a filter, or `aidd list` for every open item", code="nothing_matches")
            if filters.active()
            else new_step(
                "nothing is open" + ("" if filters.all else " on this branch"),
                workitems.AUTHOR,
                "describe the change to the agent (it checks the route with `aidd gate --paths` and follows the loop); "
                + ("" if filters.all else "`aidd list` shows the open work; ")
                + "for work someone outside the team must agree to first, `aidd new proposal`",
                code="nothing_open",
            )
        )
    for s in steps:
        s.setdefault("group", None)
    steps.sort(key=sort_key)
    return ([_as_owner(s) for s in steps] if filters.all else steps), specs


def open_work(root: Path, today: dt.date | None = None, now: dt.datetime | None = None) -> tuple[list[dict], list[Item]]:
    """All open work, as `aidd list` shows it, and the Specs it read, each with its derived status: what autopilot
    (`aidd.autopilot`) decides from. Like `plan`, it runs the doctor's checks."""
    return collect(root, Filters(all=True), today, now)


def plan(root: Path, today: dt.date | None = None, filters: Filters | None = None, now: dt.datetime | None = None) -> list[dict]:
    """The steps of one view, most urgent first (`sort_key`): this change's (`forecast`) by default, all open work
    (`aidd list`) with `filters.all`."""
    return collect(root, filters or Filters(), today, now)[0]


def next_steps_markdown(steps: list[dict]) -> str:
    if len(steps) == 1 and str(steps[0].get("code") or "").startswith("nothing"):
        # An empty view is one sentence and its next step, not a numbered list of one.
        s = steps[0]
        return f"{s['what'][:1].upper()}{s['what'][1:]}.\nNext: {s['how']}.\n"
    lines = []
    for i, s in enumerate(steps, 1):
        age = "" if s.get("age_days") is None else f"[age {s['age_days']}d{', aging' if s.get('aged') else ''}] "
        lines.append(f"{i}. {age}{s['what']}")
        lines.append(f"   who: {s['who']}")
        lines.append(f"   how: {s['how']}")
        if s.get("why"):
            lines.append(f"   why: {workitems.why_text(s['why'])}")
    return "\n".join(lines) + "\n"
