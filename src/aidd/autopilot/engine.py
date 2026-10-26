"""Autopilot's one decision per turn: from the inputs `gather` read, the next action (run a flow, ask a person, or stop), pure, so the same inputs give the same action."""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass, field

from aidd import config, workitems
from aidd.autopilot import journal, telling
from aidd.autopilot import lease as leasemod
from aidd.kernel import globs, resources, timestamps

SCHEMA_VERSION = "1"
PAGE = "aidd list --waiting-on-me --html"
PAGE_ALL = "aidd list --html"
# The autopilot command as the aidd-team plugin names it; `aidd init --team` installs it as `/aidd-autopilot`.
RESUME = "/aidd-team:autopilot"
# Stops a person ends by starting autopilot again: the plan to agree to, or a limit of this run.
RESUMES = frozenset({"plan_ready", "timebox", "token_cap", "cost_cap", "stalled"})

# Codes only `aidd autopilot next` emits, each an agent step with its flow in roles.json: the loop's steps between two
# engine states (Verify and Review, side by side before Merge approval), the return to Implement after a "no", the entry
# from a goal, and the retro on a cadence.
AUTOPILOT_CODES: dict[str, str] = {
    "spec.verify": workitems.AGENT,
    "spec.review": workitems.AGENT,
    "spec.rework": workitems.AGENT,
    "ask.product": workitems.AGENT,
    "ask.client": workitems.AGENT,
    "learn.retro": workitems.AGENT,
}
ASKS = ("ask.product", "ask.client")
# Verify and Review: one run asks for both on the same head, and each is noted on its own. A new head voids both.
CHECKS = ("spec.verify", "spec.review")
# Steps that start new work, which adds a decision for an Approver later: the WIP limit holds them, never work in flight.
STARTS_NEW = frozenset({"spec.draft", "spec.ready", "lane.spec", "lane.fast", "ask.product", "ask.client", "proposal.drafting"})


# How many Specs one turn works on at once (`autopilot.parallel`): the main action and, in `also`, the rest.
DEFAULT_PARALLEL = 2

# Steps at or past Implement: each needs the Spec cleared (`Inputs.cleared`), else the Approver is asked.
PAST_SPECIFY = frozenset(
    {
        "spec.ready",
        "spec.in_progress",
        "spec.rework",
        "spec.emergency",
        "spec.verify",
        "spec.review",
        "spec.land_standing",
        "spec.publish_standing",
        "spec.merge_approval_standing",
        "spec.integrate",
    }
)
# Agent steps that run an aidd command, not a team command: the approvals the person's standing approval covers, and
# a goal Spec's integration. `aidd land` and `aidd integrate` test what lands again and merge only if the gate passes;
# the Spec approval takes the Spec's path.
SHELL_STEPS = {
    "spec.spec_approval_standing": "aidd approve spec",
    "spec.land_standing": "aidd land",
    "spec.publish_standing": "aidd publish",
    "spec.merge_approval_standing": "aidd approve merge",
    "spec.integrate": "aidd integrate",
    "goal.land_standing": "aidd land",
}


def contract() -> dict[str, str]:
    """Every step code the engine can emit, with who takes it: `aidd list`'s codes and autopilot's own."""
    return workitems.STEP_CODES | AUTOPILOT_CODES


# What each of autopilot's own codes means, beside workitems.STEP_MEANINGS for `aidd list`'s codes.
AUTOPILOT_MEANINGS: dict[str, str] = {
    "spec.verify": "autopilot runs Verify on the current head, beside Review, before Merge approval",
    "spec.review": "autopilot runs Review on the current head, beside Verify, and it counts once Verify is clean",
    "spec.rework": "Verify or Review failed on the current head, or a person said no: the Spec goes back to Implement once",
    "ask.product": "autopilot plans the goal it was given: an Initiative, its Epics, and Spec stubs",
    "ask.client": "autopilot drafts a proposal for the client goal it was given",
    "learn.retro": "the retro is due on its cadence: autopilot runs it",
}


def step_meanings() -> dict[str, str]:
    """What every step code in `contract()` means, in one line (docs/ERRORS.md)."""
    return workitems.STEP_MEANINGS | AUTOPILOT_MEANINGS


@functools.cache
def flow_map() -> dict[str, str]:
    """Step code -> the team command that starts on it, from each flow's `starts_on` (roles.json)."""
    out: dict[str, str] = {}
    for f in resources.load_json("roles.json")["loop"]["flows"]:
        for code in f.get("starts_on") or []:
            out.setdefault(code, f["command"])
    return out


def flow_key(step: dict) -> str:
    """The code a step maps by: its code, or for the lane step, `lane.<its lane>`."""
    return f"lane.{step.get('lane')}" if step.get("code") == "lane" else str(step.get("code"))


def is_agent_step(code: str) -> bool:
    return contract().get(code) == workitems.AGENT


def kind_of(step: dict) -> str:
    """Who takes a step by the contract, whatever name its `who` shows (an owner's email, "@x's agent")."""
    return contract().get(flow_key(step), workitems.AUTHOR)


@dataclass
class Limits:
    """`autopilot`: the run's limits; each has a default or is off, so nothing asks."""

    timebox: str = leasemod.DEFAULT_TIMEBOX
    max_tokens: int | None = None
    max_cost: dict | None = None
    retro_every: int | None = None
    parallel: int = DEFAULT_PARALLEL

    @classmethod
    def of(cls, cfg: config.Config | None) -> Limits:
        d = (cfg.get("autopilot", default={}) if cfg else {}) or {}
        parallel = int(d.get("parallel") or DEFAULT_PARALLEL)
        return cls(str(d.get("timebox") or leasemod.DEFAULT_TIMEBOX), d.get("max_tokens"), d.get("max_cost"), d.get("retro_every"), parallel)

    def as_dict(self) -> dict:
        return {
            k: v
            for k, v in (("timebox", self.timebox), ("max_tokens", self.max_tokens), ("max_cost", self.max_cost), ("retro_every", self.retro_every))
            if v is not None
        }


@dataclass
class Inputs:
    """Everything one decision reads; `decide` reads nothing else."""

    steps: list[dict]
    specs: dict[str, dict] = field(default_factory=dict)  # id -> Spec front matter, for pauses, retries, and observe
    heads: dict[str, str] = field(default_factory=dict)  # id -> the head commit its copy was read at
    rejected: set[str] = field(default_factory=set)  # ids whose current head a listed person requested changes on
    cleared: set[str] = field(default_factory=set)  # Spec ids that may be implemented: no Spec approval needed, or a person's
    unverified: dict[str, str] = field(default_factory=dict)  # Spec id -> a person-owned field only the head says
    lease: dict | None = None
    session: str | None = None
    others: list[dict] = field(default_factory=list)  # every other lease on record
    work: str | None = None  # the work asked for (`--work`), when given
    ambiguous: int = 0  # live leases on record when no session was named
    journal: list[dict] = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    wip_limit: int = 0
    merged: int = 0  # Specs merged so far (landed, done, or rolled back)
    goal: str | None = None
    client: bool = False
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    resume: str = RESUME  # how this install names the autopilot command
    measured: int | None = None  # the tokens the harness's transcripts show this run used (session_transcripts.py); None: not measured


in_work = leasemod.in_work


def _implement_codes() -> frozenset[str]:
    """The codes that build a new head, after which Verify's and Review's reports start afresh: the first build's and
    the rework's (`spec.rework`)."""
    return frozenset(c for c, f in flow_map().items() if f in ("implement", "rework"))


def _checks(sid: str, i: Inputs) -> dict[str, str]:
    """Verify's and Review's last results (`ok` or `fail`) on the Spec's current head since its last Implement, by
    code. A step with no result on this head has no key, so a new head voids both."""
    impl, head = _implement_codes(), i.heads.get(sid)
    hist = journal.of(i.journal, sid, impl | set(CHECKS))
    since = hist[max((n for n, e in enumerate(hist) if e["code"] in impl), default=-1) + 1 :]
    return {e["code"]: e["result"] for e in since if e.get("result") in ("ok", "fail") and journal.same_head(e, head)}


def _side_by_side(acted: str, sid: str, i: Inputs) -> list[str]:
    """The steps one run takes: Review, with Verify beside it on the same head when Verify has no clean report there."""
    return list(CHECKS) if acted == "spec.review" and _checks(sid, i).get("spec.verify") != "ok" else [acted]


def resolve(step: dict, i: Inputs) -> str:
    """The code autopilot acts on for this step: the step's own, or the loop's step that comes next. A Spec waiting for
    Merge approval is verified and reviewed side by side on its current head (`_side_by_side`); a failed Verify or Review
    there, or changes a listed person requested on it, return it to Implement once. A minor Spec specified with no Spec
    approval to wait for goes on to Implement. A Spec whose Merge approval the person's standing approval covers, or a
    goal's Spec that integrates into its goal, is verified and reviewed the same way first."""
    code, sid = flow_key(step), str(step.get("id") or "")
    if code == "spec.draft":
        if step.get("unready"):
            return code  # still holds placeholders: Specify again, whatever the last run reported
        hist = journal.of(i.journal, sid, {"spec.draft"})
        return "spec.ready" if hist and hist[-1]["result"] == "ok" else code  # Implement's own breaker holds what it notes after
    if code in ("spec.merge_approval", "spec.land_standing", "spec.publish_standing", "spec.merge_approval_standing", "spec.integrate", "spec.in_progress"):
        if code != "spec.in_progress" and sid in i.rejected:
            return "spec.rework"
        done = _checks(sid, i)
        if "fail" in done.values():
            return "spec.rework"  # once, with both reports: the rework's Implement note starts both afresh
        if code == "spec.in_progress":
            return code
        return next((c for c in ("spec.review", "spec.verify") if done.get(c) != "ok"), code)  # Review first: Verify goes beside it
    return code


def effective(step: dict, i: Inputs) -> tuple[str, dict]:
    """(the code autopilot acts on, the step to show for it). A person-owned field (`triage`, `suggested_by`) that only
    the head says asks a triager; an agent step at or past Implement on a Spec not cleared asks the Approver: the route
    needs Spec approval and no person's record approves the current hash, or the route cannot be computed. Neither the
    declared route nor the stored status clears a Spec."""
    sid = str(step.get("id") or "")
    if sid in i.unverified:
        what = f"{sid}: {i.unverified[sid]}; a person decides it"
        how = "declare or triage it where a person's decision is recorded: on the base branch through a reviewed merge, or approve the Spec"
        return "spec.triage", step | {"who": workitems.PERSON, "what": what, "how": how}
    acted = resolve(step, i)
    if (acted in PAST_SPECIFY or acted == "lane.fast") and sid not in i.cleared:
        how = f"read the Spec, its tests, and its design, then type `approve {sid}` at the prompt"
        return "spec.spec_approval", step | {
            "who": workitems.APPROVER,
            "what": f"{sid} needs a person's Spec approval before Implement",
            "how": how,
        }
    return acted, step


def observe_due(data: dict, now: dt.datetime) -> bool:
    """A landed Spec's observe result is due: its release plus its observe window has passed, and none is recorded."""
    from aidd import tracking

    out = data.get("outcome") or {}
    released = timestamps.parse_date(out.get("released_on") or "")
    if released is None or out.get("observe_result") or not workitems.observes(data):
        return False
    try:
        window = tracking.window_seconds(str((data.get("observe") or {}).get("window") or "0s"))
    except ValueError:
        window = 0
    start = dt.datetime.combine(released, dt.time(), tzinfo=dt.UTC)
    return now >= start + dt.timedelta(seconds=window)


def _action(kind: str, why: str, **fields) -> dict:
    return {"schema_version": SCHEMA_VERSION, "action": kind, "why": why} | {k: v for k, v in fields.items() if v not in (None, [])}


def _stop(reason: str, why: str, **fields) -> dict:
    return _action("stop", why, reason=reason, **fields)


def _run_action(code: str, spec: str | None, why: str, work: str, *, args: str | None = None, paused: list[dict] | None = None, **both) -> dict:
    """A `run`. `both` holds Verify and Review's `codes`, when one command takes the two, and the `head` they run on."""
    if code in SHELL_STEPS:
        # A land, a publish, or a Merge approval takes no argument: it acts on the branch checked out, which holds `spec`.
        return _action("run", why, code=code, command=SHELL_STEPS[code], args=args, spec=spec, work=work, paused=paused)
    flow, args = flow_map()[code], args if args is not None else (spec or "")
    return _action("run", why, code=code, flow=flow, command=f"/aidd-team:{flow}", args=args, spec=spec, work=work, paused=paused, **both)


def _ask(step: dict, work: str, *, why: str, code: str | None = None, blocked: bool = False, waiting: int | None = None, paused=None) -> dict:
    who = str(step.get("who") or workitems.AUTHOR)
    return _action(
        "ask",
        why,
        code=code or step.get("code"),
        spec=step.get("id"),
        who=who,
        what=step.get("what"),
        how=step.get("how"),
        page=PAGE if kind_of(step) == workitems.APPROVER else PAGE_ALL,
        work=work,
        blocked=blocked or None,
        waiting=waiting,
        paused=paused,
    )


def _held(steps: list[dict]) -> dict[str, int]:
    """Open approval waits per Approver, as `aidd list` counts them for `limits.max_open_per_approver`."""
    from aidd import tracking

    held: dict[str, int] = {}
    for s in steps:
        if s.get("code") in tracking.APPROVER_WAITS:
            for a in s.get("approvers") or []:
                held[a] = held.get(a, 0) + 1
    return held


def _lease_check(i: Inputs) -> dict | None:
    """A stop when the run holds no live lease of its own, or a limit ended it."""
    lease = i.lease
    if lease is None:
        if not i.session:
            live = f"{i.ambiguous} live lease{'s' if i.ambiguous != 1 else ''}" if i.ambiguous else "no live lease"
            return _stop("lease_missing", f"no session named ({live}): pass --session ID, the one `aidd autopilot start` printed")
        rival = next(
            (
                x
                for x in i.others
                if not leasemod.stale(x, i.now) and x.get("session_id") != i.session and (i.work is None or leasemod.overlaps(x["work"], i.work, i.steps))
            ),
            None,
        )
        if rival is not None and i.session:
            return _stop(
                "lease_other",
                f"session {rival['session_id']} ({rival.get('by')}) holds the lease on {rival['work']} until {rival['expires_at']}: wait for it, "
                f"or a person stops it in their own terminal with `aidd autopilot stop --session {rival['session_id']}`",
                work=rival["work"],
            )
        return _stop("lease_missing", "no lease: run `aidd autopilot start --work SPEC` (or a label, or all) first, and pass its --session ID")
    if leasemod.stale(lease, i.now):
        return _stop("timebox", f"the timebox ended at {lease['expires_at']}: start autopilot again when you are ready", work=lease["work"])
    tokens, cost = journal.spent(i.journal, lease)
    cap = i.limits
    # The harness's own count, where it keeps one, over what the steps reported: an agent's report is a claim.
    measured = i.measured is not None and i.measured > tokens
    tokens = max(tokens, i.measured or 0)
    if cap.max_tokens and tokens >= cap.max_tokens:
        how = "used, as the session's transcripts show" if measured else "recorded"
        return _stop("token_cap", f"the run {how} {tokens} tokens, at `autopilot.max_tokens: {cap.max_tokens}`", work=lease["work"])
    if cap.max_cost and cost.get(cap.max_cost["currency"], 0.0) >= float(cap.max_cost["amount"]):
        used = round(cost[cap.max_cost["currency"]], 4)
        return _stop(
            "cost_cap", f"the run recorded {used} {cap.max_cost['currency']}, at `autopilot.max_cost.amount: {cap.max_cost['amount']}`", work=lease["work"]
        )
    if journal.stalled(journal.run_of(i.journal, lease)):
        return _stop(
            "stalled",
            f"the last {journal.STALL_TURNS} steps moved nothing on: each failed, or ran again on a head it had run on. A person reads the "
            "handoff notes and the journal (`aidd autopilot status`), fixes the cause, then starts autopilot again",
            work=lease["work"],
        )
    return None


def _words(goal: str) -> str:
    return " ".join(goal.casefold().split())[: leasemod.GOAL_MAX]


def planned(journal: list[dict], goal: str) -> bool:
    """A goal's plan step ran `ok` for this goal before, in any run: a start with the same goal is the person agreeing
    to that plan, so the run goes on with its work. The journal keeps the ask (`aidd autopilot note --ask`)."""
    want = _words(goal)
    return any(e.get("code") in ASKS and e.get("result") == "ok" and _words(str(e.get("goal") or "")) == want for e in journal)


def _plan_goal(i: Inputs, work: str, run: list[dict], waiting: int) -> dict:
    """A goal a person gave, not planned yet: its plan step first, before the open work. Planning that failed twice in
    this run asks the person; Approvers at their limit of open waits hold it, as any new work."""
    code = "ask.client" if i.client else "ask.product"
    held = _held(i.steps)
    full = sorted(a for a, n in held.items() if i.wip_limit and n >= i.wip_limit)
    if journal.tripped(run, None, code):
        step = {
            "code": code,
            "who": workitems.AUTHOR,
            "what": f"planning the goal failed twice in this run ({code})",
            "how": "restate the goal, or plan it yourself",
        }
        return _ask(step, work, why=f"{code} failed twice in a row in this run: a person looks at it", blocked=True)
    if full:
        return _action(
            "ask",
            f"{', '.join(full)} hold{'s' if len(full) == 1 else ''} {i.wip_limit} or more open approval waits (limits.max_open_per_approver): "
            "the goal is planned after a decision",
            code="approver.over_limit",
            who=contract()["approver.over_limit"],
            what="the Approvers decide the waiting approvals, then the goal can be planned",
            how="read the decision page; each Approver approves or answers each wait, or shares them with another eligible Approver",
            page=PAGE,
            work=work,
            waiting=sum(held[a] for a in full),
        )
    flow = flow_map()[code]
    why = f"a new goal: /aidd-team:{flow} turns it into work, and the run then stops for a person to agree"
    if waiting:
        why += f"; the {waiting} open item{'s' if waiting != 1 else ''} in {work} go{'es' if waiting == 1 else ''} on after it"
    return _run_action(code, None, why, work, args=i.goal)


def _retro_due(i: Inputs) -> bool:
    if not i.limits.retro_every:
        return False
    done = [e for e in i.journal if e.get("code") == "learn.retro" and e.get("result") == "ok"]
    since = int(done[-1].get("merged") or 0) if done else 0
    return i.merged - since >= i.limits.retro_every


def _decide(i: Inputs) -> dict:
    """The one action for this turn. Pure: the same inputs give the same action.

    Work that cannot go on (paused with `blockers`, a Task out of retries, a stop rule, the circuit breaker, a person's
    decision it waits on) is set aside, and the next runnable step in that work goes on; `paused` lists what was set aside.
    Only when nothing is runnable does the run ask a person or stop."""
    stopped = _lease_check(i)
    if stopped is not None:
        return stopped
    lease = i.lease
    assert lease is not None
    work = str(lease["work"])
    run = journal.run_of(i.journal, lease)
    setup = next((s for s in i.steps if str(s.get("code", "")).startswith("setup.")), None)
    if setup is not None:
        return _ask(setup, work, why="aidd is not ready in this repository", blocked=True)
    if any(e.get("code") in ASKS and e.get("result") == "ok" for e in run):
        return _stop("plan_ready", "the plan is ready for a person to read and agree to", work=work)
    paused: list[dict] = []
    if work == leasemod.ALL and _retro_due(i):
        if journal.tripped(run, None, "learn.retro"):
            paused.append({"spec": "learn.retro", "why": "the retro failed twice in this run"})
        else:
            return _run_action("learn.retro", None, f"{i.limits.retro_every} or more changes merged since the last retro (`autopilot.retro_every`)", work)
    mine = [s for s in i.steps if in_work(s, work) and flow_key(s) in contract()]
    waits_on_person = {str(s["id"]) for s in mine if not is_agent_step(effective(s, i)[0])}
    held = _held(i.steps)
    full = sorted(a for a, n in held.items() if i.wip_limit and n >= i.wip_limit)
    if i.goal and not planned(i.journal, i.goal):
        return _plan_goal(i, work, run, len(mine))
    asks: list[tuple[dict, str]] = []
    blocked: list[tuple[dict, str, str]] = []
    waiting_other, watching = 0, 0
    held_back: list[dict] = []
    picked: list[dict] = []  # the turn's actions: the first is the main one, the rest run beside it (`also`)
    for s in mine:
        if picked and (len(picked) >= i.limits.parallel or not _fans_out(picked[0].get("code"))):
            break
        code, sid = flow_key(s), str(s.get("id"))
        head = i.heads.get(sid)
        if code in ("spec.blocked", "spec.blocked_by"):
            data = i.specs.get(sid) or {}
            if code == "spec.blocked" and str(data.get("blockers") or "").strip():
                paused.append({"spec": sid, "why": "paused with blockers"})
            elif code == "spec.blocked" and workitems.retries_used(data):
                paused.append({"spec": sid, "why": "a Task used its retries"})
                blocked.append((s, code, "a Task used its retries: a person re-plans it, never another agent"))
            else:
                waiting_other += 1
            continue
        acted, shown = effective(s, i)
        if not is_agent_step(acted):
            asks.append((shown, acted))
            continue
        if sid in waits_on_person:
            continue  # its person's decision comes first; that step is asked below
        if acted == "spec.landed" and journal.of(i.journal, sid, ("spec.landed",)) and not observe_due(i.specs.get(sid) or {}, i.now):
            watching += 1
            continue
        codes = _side_by_side(acted, sid, i)
        aside = _set_aside(run, sid, acted, codes, head)
        if aside:
            paused.append({"spec": sid, "why": aside[2]})
            blocked.append((s, aside[0], aside[1]))
            continue
        if acted in SHELL_STEPS and _shell_waits(run, sid, acted, head):
            # The note's words are the agent's report: the ask points to them, and never says them as aidd's own.
            what = f"`{SHELL_STEPS[acted]}` for {sid} waits on something a person clears, such as a failing check"
            how = f"run `{SHELL_STEPS[acted]}` yourself to see why, or read the step's note in `aidd autopilot status --session {lease['session_id']}`"
            asks.append((s | {"who": workitems.AUTHOR, "what": what, "how": how}, acted))
            continue
        if full and acted in STARTS_NEW:
            held_back.append(s)
            continue
        said = str(s.get("what")) if acted == code else (_SIDE_BY_SIDE if len(codes) > 1 else _WHY.get(acted, acted))
        why = said if said.startswith(f"{sid} ") or said.startswith(f"{sid}:") else f"{sid}: {said}"
        args = None if not sid.startswith("branch:") else f"the change on {sid.removeprefix('branch:')}"
        if acted == "spec.spec_approval_standing":
            args = str(s.get("where") or sid)  # `aidd approve spec <the Spec>`
        if picked and not (_fans_out(acted) and _apart(i, sid, [str(a.get("spec")) for a in picked])):
            continue
        if picked and i.wip_limit and acted in STARTS_NEW and any(a.get("code") in STARTS_NEW for a in picked):
            continue  # under a WIP limit, new work starts one per turn, so each start is counted against the limit first
        both = {"codes": codes if len(codes) > 1 else None, "head": head}
        picked.append(_run_action(acted, sid, why, work, args=args, paused=list(paused), **both))
    if picked:
        also = [{k: a[k] for k in ("code", "codes", "flow", "command", "args", "spec", "head", "why") if k in a} for a in picked[1:]]
        return picked[0] | ({"also": also} if also else {})
    if held_back:
        s = held_back[0]
        return _action(
            "ask",
            f"{', '.join(full)} hold{'s' if len(full) == 1 else ''} {i.wip_limit} or more open approval waits (limits.max_open_per_approver): "
            f"{s.get('id')} starts after a decision",
            code="approver.over_limit",
            spec=s.get("id"),
            who=contract()["approver.over_limit"],
            what=f"the Approvers decide the waiting approvals, then {s.get('id')} can start",
            how="read the decision page; each Approver approves or answers each wait, or shares them with another eligible Approver",
            page=PAGE,
            work=work,
            waiting=sum(held[a] for a in full),
            paused=paused,
        )
    if blocked:
        s, code, why = blocked[0]
        return _ask(s | {"who": workitems.AUTHOR}, work, code=code, why=why, blocked=True, paused=paused) | {"where": s.get("where")}
    if asks:
        s, acted = asks[0]
        return _ask(
            s, work, code=acted, why=f"{len(asks)} decision{'s wait' if len(asks) != 1 else ' waits'} on a person in {work}", waiting=len(asks), paused=paused
        )
    why = f"nothing runnable in {work}"
    if paused:
        why += "; set aside: " + ", ".join(f"{p['spec']} ({p['why']})" for p in paused)
    if waiting_other:
        why += f"; {waiting_other} wait{'s' if waiting_other == 1 else ''} on other work"
    if watching:
        why += f"; {watching} landed and watched until the observe result is due"
    if i.goal:
        why += "; the goal was planned already: `aidd list` shows its work"
    elif not mine:
        why += "; give `aidd autopilot next --ask` what to build, to plan new work"
    return _stop("nothing_open", why, work=work, paused=paused)


def _set_aside(run: list[dict], sid: str, acted: str, codes: list[str], head: str | None) -> tuple[str, str, str] | None:
    """(the code, why for the person, why in a few words) when this run sets the Spec aside: a step stopped at a stop
    rule, the circuit breaker tripped, or the Spec went back to the same step MAX_ROUNDS times. Else None."""
    stop = next((c for c in codes if [e.get("result") for e in run if e.get("spec") == sid and e.get("code") == c][-1:] == ["blocked"]), None)
    if stop:
        return stop, f"{stop} stopped at a stop rule, and a person decides how it goes on", f"{stop} stopped at a stop rule"
    broke = sorted({str(e["code"]) for e in run if e.get("spec") == sid and journal.tripped(run, sid, str(e["code"]), head)})
    broke = broke or [c for c in codes if journal.tripped(run, sid, c, head, progress=True)][:1]
    if broke:
        return broke[0], f"{broke[0]} made no progress twice in a row in this run", f"{broke[0]} made no progress twice in this run"
    step = journal.ROUNDS.get(acted)
    n = journal.rounds(run, sid, acted) if step else 0
    if step and n >= journal.MAX_ROUNDS + (acted == "spec.draft"):
        why = f"it went back to {step} {n} times in this run, autopilot's limit; the last reports: {journal.last_reports(run, sid)}"
        return acted, why, f"back to {step} {n} times"
    return None


def _shell_waits(run: list[dict], sid: str, code: str, head: str | None) -> bool:
    """Whether an aidd command step's last note on this head was `waiting`, such as `aidd land` holding for a check. Run
    again, it would wait the same, so a person clears it first."""
    last = [e for e in run if e.get("spec") == sid and e.get("code") == code and journal.same_head(e, head)][-1:]
    return bool(last) and last[0].get("result") == "waiting"


def _fans_out(code: object) -> bool:
    """Whether a step may run beside another one: a team flow on one Spec, in that Spec's own worktree. A Spec approval,
    a Merge approval, a land, and a publish act on the branch checked out here, and a goal's plan or the retro on all the work."""
    return isinstance(code, str) and code not in SHELL_STEPS and code not in ASKS and code != "learn.retro" and code in flow_map()


def _apart(i: Inputs, sid: str, others: list[str]) -> bool:
    """Whether the Spec `sid` may run beside `others`: a Spec, not a branch, whose Tasks' scopes overlap none of theirs.
    A Spec with no Tasks yet (a stub being specified) writes only its own files, so it overlaps nothing."""
    if sid.startswith("branch:") or sid in others:
        return False
    mine = _scopes(i.specs.get(sid) or {})
    return not any(globs.overlap(a, b) for o in others for a in mine for b in _scopes(i.specs.get(o) or {}))


def _scopes(data: dict) -> list[str]:
    """What a Spec's work writes: its Tasks' scopes and its test files."""
    tests = data.get("tests")
    tests = tests if isinstance(tests, dict) else {}
    return [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []] + [str(f) for f in tests.get("files") or []]


def decide(i: Inputs) -> dict:
    """The one action for this turn (`_decide`), and on an `ask` or a stop a person ends, what to tell the person: every
    decision that waits on one, how much waits behind them, and the command that goes on. Pure, as `_decide` is."""
    return told(_decide(i), i)


def _waits(step: dict) -> bool:
    return flow_key(step) in ("spec.blocked", "spec.blocked_by")


def decisions(inputs: Inputs, work: str) -> list[dict]:
    """Every decision in the work that waits on a person, in `aidd list`'s order: whose it is, what, and how to take it.
    Blocked work is not a decision: it starts when what it waits on finishes."""
    out: list[dict] = []
    for s in inputs.steps:
        if not in_work(s, work) or flow_key(s) not in contract() or _waits(s):
            continue
        acted, shown = effective(s, inputs)
        if is_agent_step(acted):
            continue
        fields = (("spec", shown.get("id")), ("code", acted), ("who", shown.get("who")), ("what", shown.get("what")), ("how", shown.get("how")))
        out.append({k: v for k, v in fields if v})
    return out


def told(action: dict, inputs: Inputs) -> dict:
    """An `ask`, or a stop in `RESUMES`, with `decisions`, `behind`, `resume`, and the `message` that says them."""
    kind, work = action["action"], action.get("work")
    where = action.pop("where", None)
    if not work or not (kind == "ask" or (kind == "stop" and action.get("reason") in RESUMES)):
        return action
    waiting = decisions(inputs, str(work))
    if kind == "ask" and not action.get("blocked") and not any(d.get("what") == action.get("what") for d in waiting):
        # an ask that is no person's step by the contract, such as `aidd land` that waits: it heads the list
        waiting.insert(0, {k: action[k] for k in ("spec", "code", "who", "what", "how") if action.get(k)})
    behind = sum(1 for s in inputs.steps if in_work(s, str(work)) and _waits(s))
    resume = f"{inputs.resume} {work}"
    out = action | {"resume": resume} | ({"decisions": waiting} if waiting else {}) | ({"behind": behind} if behind else {})
    return out | {"message": telling.message(out, where)}


_SIDE_BY_SIDE = "built and green: Verify and Review run side by side on this head, before a person's Merge approval"
_WHY = {
    "spec.verify": "reviewed on this head with no clean Verify yet: Verify runs its tests and each Acceptance line here",
    "spec.review": "verified on this head: Review reads it before a person's Merge approval",
    "spec.rework": "Verify or Review failed on this head, or a listed person requested changes on it: back to Implement once",
    "spec.ready": "specified, with no Spec approval to wait for on its route: Implement builds it",
    "spec.land_standing": "verified and reviewed on this head, and the person's standing approval covers it: `aidd land` lands it",
    "spec.publish_standing": "verified and reviewed on this head, and agents publish here: `aidd publish` opens its PR/MR",
    "spec.merge_approval_standing": "verified and reviewed on this head, and the person's standing approval covers it: `aidd approve merge`",
    "spec.integrate": "verified and reviewed on this head, and its goal holds it until the release: `aidd integrate` lands it there",
    "goal.land_standing": "every Spec of the goal is integrated, and the person's standing approval covers it: `aidd land` on the goal branch",
}
