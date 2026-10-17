"""Autopilot's one decision per turn: from the inputs `gather` read, the next action (run a flow, ask a person, or stop), pure, so the same inputs give the same action."""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass, field

from aidd import config, workitems
from aidd.autopilot import lease as leasemod
from aidd.kernel import globs, resources, timestamps

SCHEMA_VERSION = "1"
PAGE = "aidd list --waiting-on-me --html"
PAGE_ALL = "aidd list --html"
# The autopilot command as the aidd-team plugin names it; `aidd init --team` installs it as `/aidd-autopilot`.
RESUME = "/aidd-team:autopilot"
# Stops a person ends by starting autopilot again: the plan to agree to, or a limit of this run.
RESUMES = frozenset({"plan_ready", "timebox", "token_cap", "cost_cap"})
# The decisions a message lists in full; the rest are counted and left to `aidd list --waiting-on-me`.
LISTED = 10

# Codes only `aidd autopilot next` emits, each an agent step with its flow in roles.json: the loop's steps between two
# engine states (Verify and Review before Merge approval), the return to Implement after a "no", the entry from a goal,
# and the retro on a cadence.
AUTOPILOT_CODES: dict[str, str] = {
    "spec.verify": workitems.AGENT,
    "spec.review": workitems.AGENT,
    "spec.rework": workitems.AGENT,
    "goal.product": workitems.AGENT,
    "goal.client": workitems.AGENT,
    "learn.retro": workitems.AGENT,
}
GOALS = ("goal.product", "goal.client")
# Steps that start new work, which adds a decision for an Approver later: the WIP limit holds them, never work in flight.
STARTS_NEW = frozenset({"spec.draft", "spec.ready", "lane.spec", "lane.fast", "goal.product", "goal.client", "proposal.drafting"})


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
        "spec.ship_ready",
        "spec.merge_standing",
        "spec.integrate",
    }
)
# Agent steps that run an aidd command, not a team command: the approvals the person's standing approval covers, and
# a goal Spec's integration. `aidd ship` and `aidd integrate` test what lands again and merge only if the gate passes;
# the Spec approval takes the Spec's path.
SHELL_STEPS = {
    "spec.approve_standing": "aidd approve spec",
    "spec.ship_ready": "aidd ship",
    "spec.merge_standing": "aidd approve merge",
    "spec.integrate": "aidd integrate",
    "goal.ship_ready": "aidd ship",
}


def contract() -> dict[str, str]:
    """Every step code the engine can emit, with who takes it: `aidd list`'s codes and autopilot's own."""
    return workitems.STEP_CODES | AUTOPILOT_CODES


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
    merged: int = 0  # Specs merged so far (shipped, done, or rolled back)
    goal: str | None = None
    client: bool = False
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    resume: str = RESUME  # how this install names the autopilot command
    measured: int | None = None  # the tokens the harness's transcripts show this run used (usage.py); None: not measured


in_work = leasemod.in_work


def spent(journal: list[dict], lease: dict) -> tuple[int, dict[str, float]]:
    """The tokens and the cost by currency the lease's run recorded (self-reported by the autopilot command)."""
    tokens, cost = 0, dict[str, float]()
    for e in _run(journal, lease):
        tokens += int(e.get("tokens") or 0)
        if isinstance(e.get("cost"), dict):
            c = e["cost"]
            cost[c["currency"]] = cost.get(c["currency"], 0.0) + float(c["amount"])
    return tokens, cost


def _run(journal: list[dict], lease: dict) -> list[dict]:
    """The journal lines of this lease's run."""
    return [e for e in journal if e.get("session_id") == lease["session_id"] and str(e.get("at")) >= str(lease["started_at"])]


def _of(journal: list[dict], spec: str, codes: frozenset[str] | set[str] | tuple[str, ...]) -> list[dict]:
    return [e for e in journal if e.get("spec") == spec and e.get("code") in codes]


def _implement_codes() -> frozenset[str]:
    return frozenset(c for c, f in flow_map().items() if f == "implement")


def _same_head(e: dict, head: str | None) -> bool:
    return head is None or e.get("head") == head


def tripped(run: list[dict], spec: str | None, code: str, head: str | None = None, *, progress: bool = False) -> bool:
    """The circuit breaker: the last two times this run noted `code` for `spec`, neither moved the work on. A try that
    failed never does; with `progress`, an `ok` on the same head (the derived state unchanged) does not either. Both
    tries must be on the current head, when it is known."""
    tries = [e for e in run if e.get("code") == code and e.get("spec") == spec]

    def stuck(e: dict) -> bool:
        if head is not None and e.get("head") != head:
            return False  # a new head is progress: the breaker never trips across heads
        return e.get("result") == "fail" or (progress and e.get("result") == "ok" and head is not None)

    return len(tries) >= 2 and all(stuck(e) for e in tries[-2:])


def resolve(step: dict, i: Inputs) -> str:
    """The code autopilot acts on for this step: the step's own, or the loop's step that comes next. A Spec waiting for
    Merge approval is first verified, then reviewed, on its current head; a failed Verify or Review, or changes a
    listed person requested on that head, return it to Implement. A minor Spec specified with no Spec approval to wait
    for goes on to Implement. A Spec whose Merge approval the person's standing approval covers, or a goal's Spec
    that integrates into its goal, is verified and reviewed the same way first."""
    code, sid = flow_key(step), str(step.get("id") or "")
    head = i.heads.get(sid)
    impl = _implement_codes()
    if code == "spec.draft":
        if step.get("unready"):
            return code  # still holds placeholders: Specify again, whatever the last run reported
        hist = _of(i.journal, sid, impl | {"spec.draft"})
        return "spec.ready" if hist and hist[-1]["code"] == "spec.draft" and hist[-1]["result"] == "ok" else code
    if code in ("spec.in_review", "spec.ship_ready", "spec.merge_standing", "spec.integrate", "spec.in_progress"):
        if code != "spec.in_progress" and sid in i.rejected:
            return "spec.rework"
        hist = _of(i.journal, sid, impl | {"spec.verify", "spec.review"})
        if hist and hist[-1]["code"] in ("spec.verify", "spec.review") and hist[-1]["result"] == "fail":
            return "spec.rework"
        if code == "spec.in_progress":
            return code
        since = hist[max((n for n, e in enumerate(hist) if e["code"] in impl), default=-1) + 1 :]
        if not any(e["code"] == "spec.verify" and e["result"] == "ok" and _same_head(e, head) for e in since):
            return "spec.verify"
        if not any(e["code"] == "spec.review" and e["result"] == "ok" and _same_head(e, head) for e in since):
            return "spec.review"
    return code


def effective(step: dict, i: Inputs) -> tuple[str, dict]:
    """(the code autopilot acts on, the step to show for it). A person-owned field (`triage`, `suggested_by`) that only
    the head says asks a triager; an agent step at or past Implement on a Spec not cleared asks the Approver: the route
    needs Spec approval and no person's record approves the current hash, or the route cannot be computed. Neither the
    declared route nor the stored status clears a Spec."""
    sid = str(step.get("id") or "")
    if sid in i.unverified:
        what = f"{sid}: {i.unverified[sid]}; a person decides it"
        how = "declare or triage it where a person's decision is recorded: on the base branch through a reviewed merge, or approve the Spec's hash"
        return "spec.triage", step | {"who": workitems.PERSON, "what": what, "how": how}
    acted = resolve(step, i)
    if (acted in PAST_SPECIFY or acted == "lane.fast") and sid not in i.cleared:
        where = step.get("where") or sid
        how = f"read the Spec, then approve its hash: `aidd hash {where} --line` (`aidd approve spec {where}` at your own terminal)"
        return "spec.spec_approval", step | {
            "who": workitems.APPROVER,
            "what": f"{sid} needs a person's Spec approval of its current hash before Implement",
            "how": how,
        }
    return acted, step


def observe_due(data: dict, now: dt.datetime) -> bool:
    """A shipped Spec's observe result is due: its release plus its observe window has passed, and none is recorded."""
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


def _run_action(code: str, spec: str | None, why: str, work: str, *, args: str | None = None, paused: list[dict] | None = None) -> dict:
    if code in SHELL_STEPS:
        # A ship or a Merge approval takes no argument: it acts on the branch checked out, which holds `spec`.
        return _action("run", why, code=code, command=SHELL_STEPS[code], args=args, spec=spec, work=work, paused=paused)
    flow = flow_map()[code]
    return _action(
        "run", why, code=code, flow=flow, command=f"/aidd-team:{flow}", args=args if args is not None else (spec or ""), spec=spec, work=work, paused=paused
    )


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
    """Open approval waits per Approver, as `aidd list` counts them for `gates.max_open_per_approver`."""
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
                f"session {rival['session_id']} ({rival.get('by')}) holds the lease on {rival['work']} until {rival['expires_at']}",
                work=rival["work"],
            )
        return _stop("lease_missing", "no lease: run `aidd autopilot start --work SPEC` (or a label, or all) first, and pass its --session ID")
    if leasemod.stale(lease, i.now):
        return _stop("timebox", f"the timebox ended at {lease['expires_at']}: start autopilot again when you are ready", work=lease["work"])
    tokens, cost = spent(i.journal, lease)
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
    if stalled(_run(i.journal, lease)):
        return _stop(
            "stalled",
            f"the last {STALL_TURNS} steps moved nothing on: each failed, or ran again on a head it had run on. A person reads the "
            "handoff notes and the journal (`aidd autopilot status`), fixes the cause, then starts autopilot again",
            work=lease["work"],
        )
    return None


# The stall breaker, across the whole run: this many steps in a row with no progress stop it (the circuit breaker
# sets one step aside after two; this catches a run that goes round between steps or between Specs).
STALL_TURNS = 6


def stalled(run: list[dict]) -> bool:
    """Whether the run's last STALL_TURNS notes moved nothing on: each failed, or was an `ok` for a step (its code, Spec,
    and head) the run had already done. A merge, a first `ok` of a step on a head, or a plan is progress."""
    if len(run) < STALL_TURNS:
        return False
    done = {(e.get("code"), e.get("spec"), e.get("head")) for e in run[:-STALL_TURNS] if e.get("result") == "ok"}
    for e in run[-STALL_TURNS:]:
        key = (e.get("code"), e.get("spec"), e.get("head"))
        if e.get("merged") or (e.get("result") == "ok" and key not in done):
            return False
        if e.get("result") == "ok":
            done.add(key)
    return True


def _words(goal: str) -> str:
    return " ".join(goal.casefold().split())[: leasemod.GOAL_MAX]


def planned(journal: list[dict], goal: str) -> bool:
    """A goal's plan step ran `ok` for this goal before, in any run: a start with the same goal is the person agreeing
    to that plan, so the run goes on with its work. The journal keeps the ask (`aidd autopilot note --ask`)."""
    want = _words(goal)
    return any(e.get("code") in GOALS and e.get("result") == "ok" and _words(str(e.get("goal") or "")) == want for e in journal)


def _plan_goal(i: Inputs, work: str, run: list[dict], waiting: int) -> dict:
    """A goal a person gave, not planned yet: its plan step first, before the open work. Planning that failed twice in
    this run asks the person; Approvers at their limit of open waits hold it, as any new work."""
    code = "goal.client" if i.client else "goal.product"
    held = _held(i.steps)
    full = sorted(a for a, n in held.items() if i.wip_limit and n >= i.wip_limit)
    if tripped(run, None, code):
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
            f"{', '.join(full)} hold{'s' if len(full) == 1 else ''} {i.wip_limit} or more open approval waits (gates.max_open_per_approver): "
            "the goal is planned after a decision",
            code="queue.over_limit",
            who=contract()["queue.over_limit"],
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

    Work that cannot go on (paused with `blocked_on`, a Task out of retries, a stop rule, the circuit breaker, a person's
    decision it waits on) is set aside, and the next runnable step in that work goes on; `paused` lists what was set aside.
    Only when nothing is runnable does the run ask a person or stop."""
    stopped = _lease_check(i)
    if stopped is not None:
        return stopped
    lease = i.lease
    assert lease is not None
    work = str(lease["work"])
    run = _run(i.journal, lease)
    setup = next((s for s in i.steps if str(s.get("code", "")).startswith("setup.")), None)
    if setup is not None:
        return _ask(setup, work, why="aidd is not ready in this repository", blocked=True)
    if any(e.get("code") in GOALS and e.get("result") == "ok" for e in run):
        return _stop("plan_ready", "the plan is ready for a person to read and agree to", work=work)
    paused: list[dict] = []
    if work == leasemod.ALL and _retro_due(i):
        if tripped(run, None, "learn.retro"):
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
            if code == "spec.blocked" and str(data.get("blocked_on") or "").strip():
                paused.append({"spec": sid, "why": "paused with blocked_on"})
            elif code == "spec.blocked" and workitems.retries_used(data):
                paused.append({"spec": sid, "why": "a Task used its retries"})
                blocked.append((s, code, f"{sid} has a Task out of retries: a person re-plans it, never another agent"))
            else:
                waiting_other += 1
            continue
        acted, shown = effective(s, i)
        if not is_agent_step(acted):
            asks.append((shown, acted))
            continue
        if sid in waits_on_person:
            continue  # its person's decision comes first; that step is asked below
        if acted == "spec.shipped" and _of(i.journal, sid, ("spec.shipped",)) and not observe_due(i.specs.get(sid) or {}, i.now):
            watching += 1
            continue
        last = [e for e in run if e.get("spec") == sid and e.get("code") == acted]
        if last and last[-1].get("result") == "blocked":
            paused.append({"spec": sid, "why": f"{acted} stopped at a stop rule"})
            blocked.append((s, acted, f"{acted} for {sid} stopped at a stop rule: a person decides how it goes on"))
            continue
        broke = sorted({str(e["code"]) for e in run if e.get("spec") == sid and tripped(run, sid, str(e["code"]), head)})
        if not broke and tripped(run, sid, acted, head, progress=True):
            broke = [acted]
        if broke:
            paused.append({"spec": sid, "why": f"{broke[0]} made no progress twice in this run"})
            blocked.append((s, broke[0], f"{broke[0]} made no progress twice in a row for {sid} in this run: a person looks at it, never another agent"))
            continue
        if full and acted in STARTS_NEW:
            held_back.append(s)
            continue
        why = f"{sid}: {s.get('what')}" if acted == code else f"{sid}: {_WHY.get(acted, acted)}"
        args = None if not sid.startswith("branch:") else f"the change on {sid.removeprefix('branch:')}"
        if acted == "spec.approve_standing":
            args = str(s.get("where") or sid)  # `aidd approve spec <the Spec>`
        if picked and not (_fans_out(acted) and _apart(i, sid, [str(a.get("spec")) for a in picked])):
            continue
        if picked and i.wip_limit and acted in STARTS_NEW and any(a.get("code") in STARTS_NEW for a in picked):
            continue  # under a WIP limit, new work starts one per turn, so each start is counted against the limit first
        picked.append(_run_action(acted, sid, why, work, args=args, paused=list(paused)))
    if picked:
        also = [{k: a[k] for k in ("code", "flow", "command", "args", "spec", "why") if k in a} for a in picked[1:]]
        return picked[0] | ({"also": also} if also else {})
    if held_back:
        s = held_back[0]
        return _action(
            "ask",
            f"{', '.join(full)} hold{'s' if len(full) == 1 else ''} {i.wip_limit} or more open approval waits (gates.max_open_per_approver): "
            f"{s.get('id')} starts after a decision",
            code="queue.over_limit",
            spec=s.get("id"),
            who=contract()["queue.over_limit"],
            what=f"the Approvers decide the waiting approvals, then {s.get('id')} can start",
            how="read the decision page; each Approver approves or answers each wait, or shares them with another eligible Approver",
            page=PAGE,
            work=work,
            waiting=sum(held[a] for a in full),
            paused=paused,
        )
    if blocked:
        s, code, why = blocked[0]
        return _ask(s | {"who": workitems.AUTHOR}, work, code=code, why=why, blocked=True, paused=paused)
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
        why += f"; {watching} shipped and watched until the observe result is due"
    if i.goal:
        why += "; the goal was planned already: `aidd list` shows its work"
    elif not mine:
        why += "; give `aidd autopilot next --ask` what to build, to plan new work"
    return _stop("nothing_open", why, work=work, paused=paused)


def _fans_out(code: object) -> bool:
    """Whether a step may run beside another one: a team flow on one Spec, in that Spec's own worktree. A Spec approval,
    a Merge approval, and a ship act on the branch checked out here, and a goal's plan or the retro on all the work."""
    return isinstance(code, str) and code not in SHELL_STEPS and code not in GOALS and code != "learn.retro" and code in flow_map()


def _apart(i: Inputs, sid: str, others: list[str]) -> bool:
    """Whether the Spec `sid` may run beside `others`: a Spec, not a branch, whose Tasks' scopes overlap none of theirs.
    A Spec with no Tasks yet (a stub being specified) writes only its own files, so it overlaps nothing."""
    if sid.startswith("branch:") or sid in others:
        return False
    mine = _scopes(i.specs.get(sid) or {})
    return not any(globs.overlap(a, b) for o in others for a in mine for b in _scopes(i.specs.get(o) or {}))


def _scopes(data: dict) -> list[str]:
    return [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]


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
        out.append({k: v for k, v in (("spec", shown.get("id")), ("who", shown.get("who")), ("what", shown.get("what")), ("how", shown.get("how"))) if v})
    return out


def told(action: dict, inputs: Inputs) -> dict:
    """An `ask`, or a stop in `RESUMES`, with `decisions`, `behind`, `resume`, and the `message` that says them."""
    kind, work = action["action"], action.get("work")
    if not work or not (kind == "ask" or (kind == "stop" and action.get("reason") in RESUMES)):
        return action
    waiting = decisions(inputs, str(work))
    behind = sum(1 for s in inputs.steps if in_work(s, str(work)) and _waits(s))
    resume = f"{inputs.resume} {work}"
    out = action | {"resume": resume} | ({"decisions": waiting} if waiting else {}) | ({"behind": behind} if behind else {})
    return out | {"message": message(out)}


def message(action: dict) -> str:
    """What the autopilot command shows a person when the run ends on `action`, word for word: why it stopped, each
    decision and how to take it, and the command that goes on."""
    reason = action.get("reason")
    if action["action"] == "ask":
        head = "Autopilot stopped at a decision only a person can make."
    elif reason == "plan_ready":
        head = "Autopilot stopped: the plan is ready for you. `aidd list` shows the planned work (`aidd list --html` as a page)."
    else:
        head = f"Autopilot stopped: {action['why']}."
    lines = [head]
    waiting = action.get("decisions") or []
    if waiting:
        lines += ["", f"Waiting on a person ({len(waiting)}):"]
        for d in waiting[:LISTED]:
            lines.append(f"- {d['what']}" + (f" ({d['who']})" if d.get("who") else ""))
            if d.get("how"):
                lines.append(f"  {d['how']}")
        if len(waiting) > LISTED:
            lines.append(f"- and {len(waiting) - LISTED} more: `aidd list --waiting-on-me`")
    if action.get("behind"):
        n = action["behind"]
        lines += ["", f"{n} more {'waits' if n == 1 else 'wait'} on other work and {'starts' if n == 1 else 'start'} when it finishes."]
    agree = " Starting it again is how you agree to the plan." if reason == "plan_ready" else ""
    first = "When you have decided, run" if waiting else "To go on, run"
    lines += [
        "",
        f"{first} `{action['resume']}`.{agree}",
        "This session works. After a long run, start a new session (or `/clear`) first: the run begins again from the files and "
        "the journal, so nothing is lost.",
    ]
    return "\n".join(lines)


_WHY = {
    "spec.verify": "built and green: Verify runs its tests and each Acceptance line on this head before Review",
    "spec.review": "verified on this head: Review reads it before a person's Merge approval",
    "spec.rework": "the last Verify or Review failed, or a listed person requested changes on this head: back to Implement",
    "spec.ready": "specified, with no Spec approval to wait for on its route: Implement builds it",
    "spec.ship_ready": "verified and reviewed on this head, and the person's standing approval covers it: `aidd ship` lands it",
    "spec.merge_standing": "verified and reviewed on this head, and the person's standing approval covers it: `aidd approve merge`",
    "spec.integrate": "verified and reviewed on this head, and its goal holds it until the release: `aidd integrate` lands it there",
    "goal.ship_ready": "every Spec of the goal is integrated, and the person's standing approval covers it: `aidd ship` on the goal branch",
}


def markdown(action: dict) -> str:
    """One action in a few lines, for the autopilot command's start line or a person reading along."""
    kind = action["action"]
    lines = [f"next: {kind}"]
    if kind == "run":
        lines.append(f"  {action['command']} {action.get('args') or ''}".rstrip())
    elif kind == "ask":
        lines += [f"  who: {action.get('who')}", f"  what: {action.get('what')}", f"  page: `{action.get('page')}`"]
    else:
        lines.append(f"  reason: {action.get('reason')}")
    lines.append(f"  why: {action['why']}")
    for p in action.get("paused") or []:
        lines.append(f"  set aside: {p['spec']} ({p['why']})")
    if action.get("message"):
        lines += ["", action["message"]]
    return "\n".join(lines) + "\n"
