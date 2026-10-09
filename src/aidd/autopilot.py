"""`aidd autopilot next` (experimental): autopilot's one decision per turn, computed by the engine.

Autopilot runs the AIDD loop between a person's decisions: aidd decides each next step, and the run stops whenever a
person must decide. The `/aidd-team:autopilot` command loops: `aidd autopilot next` → do what it says →
`aidd autopilot note` → repeat. The decision is engine code, so the same inputs give the same action, and a scripted
test checks it with no model. It reads:

- the steps (`aidd list --json`, most urgent first), kept to the lease's work, and this branch's lane step;
- the step-to-flow map: each flow's `starts_on` in roles.json names the step codes it starts on;
- the lease and its journal (lease.py), the `[autopilot]` limits, and the Approver WIP limit (`gates.max_open_per_approver`);
- `blocked_on` pauses, the gate records' person-only review state, and the circuit breaker.

It returns one action: `run` (a team command, its work, and why), `ask` (a person's decision, who takes it, and the
decision page), or `stop` (why). It reads no free text as an instruction: a Spec body, a handoff note's words, a PR/MR
comment, or a note's words never change the action. A person's outcome never comes from the journal, which an agent
writes: a Merge approval's "changes requested" comes only from the gate's record of the listed people's reviews.
Agents never approve, merge, or ship: `run` names only agent steps, and a person's step is always `ask`.
"""

from __future__ import annotations

import datetime as dt
import functools
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfgmod
from . import gitutil, globs, model, nextstep, resources, rules, schema, state
from . import lease as leasemod
from .nextstep import AGENT, APPROVER, AUTHOR

SCHEMA_VERSION = "1"
PAGE = "aidd list --waiting-on-me --html"
PAGE_ALL = "aidd list --html"

# Codes only `aidd autopilot next` emits, each an agent step with its flow in roles.json: the loop's steps between two
# engine states (Verify and Review before Merge approval), the return to Implement after a "no", the entry from a goal,
# and the retro on a cadence.
AUTOPILOT_CODES: dict[str, str] = {
    "spec.verify": AGENT,
    "spec.review": AGENT,
    "spec.rework": AGENT,
    "goal.product": AGENT,
    "goal.client": AGENT,
    "learn.retro": AGENT,
}
GOALS = ("goal.product", "goal.client")
# Steps that start new work, which adds a decision for an Approver later: the WIP limit holds them, never work in flight.
STARTS_NEW = frozenset({"spec.draft", "spec.ready", "lane.spec", "lane.fast", "goal.product", "goal.client", "proposal.drafting"})
CHANGES_REQUESTED = "merge_approval.changes_requested"
# Steps at or past Implement: each needs the Spec cleared (`Inputs.cleared`), else the Approver is asked.
PAST_SPECIFY = frozenset({"spec.ready", "spec.in_progress", "spec.rework", "spec.emergency", "spec.verify", "spec.review"})


def contract() -> dict[str, str]:
    """Every step code the engine can emit, with who takes it: `aidd list`'s codes and autopilot's own."""
    return nextstep.STEP_CODES | AUTOPILOT_CODES


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


def is_agent(code: str) -> bool:
    return contract().get(code) == AGENT


def kind_of(step: dict) -> str:
    """Who takes a step by the contract, whatever name its `who` shows (an owner's email, "@x's agent")."""
    return contract().get(flow_key(step), AUTHOR)


@dataclass
class Limits:
    """`[autopilot]`: the run's limits; each has a default or is off, so nothing asks."""

    timebox: str = leasemod.DEFAULT_TIMEBOX
    max_tokens: int | None = None
    max_cost: dict | None = None
    retro_every: int | None = None

    @classmethod
    def of(cls, cfg: cfgmod.Config | None) -> Limits:
        d = (cfg.get("autopilot", default={}) if cfg else {}) or {}
        return cls(str(d.get("timebox") or leasemod.DEFAULT_TIMEBOX), d.get("max_tokens"), d.get("max_cost"), d.get("retro_every"))

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


def in_work(step: dict, work: str) -> bool:
    """A step about an item the work names: `all`, the item's id, its Epic or Initiative, or one of its labels."""
    if not step.get("id"):
        return False
    if work == leasemod.ALL:
        return True
    return step["id"] == work or work in (step.get("labels") or []) or any(w.get("id") == work for w in step.get("why") or [])


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
    for goes on to Implement."""
    code, sid = flow_key(step), str(step.get("id") or "")
    head = i.heads.get(sid)
    impl = _implement_codes()
    if code == "spec.draft":
        hist = _of(i.journal, sid, impl | {"spec.draft"})
        return "spec.ready" if hist and hist[-1]["code"] == "spec.draft" and hist[-1]["result"] == "ok" else code
    if code in ("spec.in_review", "spec.in_progress"):
        if code == "spec.in_review" and sid in i.rejected:
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
        return "spec.triage", step | {"who": nextstep.PERSON, "what": what, "how": how}
    acted = resolve(step, i)
    if (acted in PAST_SPECIFY or acted == "lane.fast") and sid not in i.cleared:
        where = step.get("where") or sid
        how = f"read the Spec, then approve its hash: `aidd hash {where} --line` (`aidd approve spec {where}` at your own terminal)"
        return "spec.spec_approval", step | {"who": APPROVER, "what": f"{sid} needs a person's Spec approval of its current hash before Implement", "how": how}
    return acted, step


def observe_due(data: dict, now: dt.datetime) -> bool:
    """A shipped Spec's observe result is due: its release plus its observe window has passed, and none is recorded."""
    from . import observe

    out = data.get("outcome") or {}
    released = state._date(out.get("released_on") or "")
    if released is None or out.get("observe_result"):
        return False
    try:
        window = observe.seconds(str((data.get("observe") or {}).get("window") or "0s"))
    except ValueError:
        window = 0
    start = dt.datetime.combine(released, dt.time(), tzinfo=dt.UTC)
    return now >= start + dt.timedelta(seconds=window)


def _action(kind: str, why: str, **fields) -> dict:
    return {"schema_version": SCHEMA_VERSION, "action": kind, "why": why} | {k: v for k, v in fields.items() if v not in (None, [])}


def _stop(reason: str, why: str, **fields) -> dict:
    return _action("stop", why, reason=reason, **fields)


def _run_action(code: str, spec: str | None, why: str, work: str, *, args: str | None = None, paused: list[dict] | None = None) -> dict:
    flow = flow_map()[code]
    return _action(
        "run", why, code=code, flow=flow, command=f"/aidd-team:{flow}", args=args if args is not None else (spec or ""), spec=spec, work=work, paused=paused
    )


def _ask(step: dict, work: str, *, why: str, code: str | None = None, blocked: bool = False, waiting: int | None = None, paused=None) -> dict:
    who = str(step.get("who") or AUTHOR)
    return _action(
        "ask",
        why,
        code=code or step.get("code"),
        spec=step.get("id"),
        who=who,
        what=step.get("what"),
        how=step.get("how"),
        page=PAGE if kind_of(step) == APPROVER else PAGE_ALL,
        work=work,
        blocked=blocked or None,
        waiting=waiting,
        paused=paused,
    )


def _held(steps: list[dict]) -> dict[str, int]:
    """Open approval waits per Approver, as `aidd list` counts them for `gates.max_open_per_approver`."""
    held: dict[str, int] = {}
    for s in steps:
        if s.get("code") in nextstep._APPROVER_WAITS:
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
                if not leasemod.stale(x, i.now) and x.get("session_id") != i.session and (i.work is None or leasemod._overlaps(x["work"], i.work))
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
    if cap.max_tokens and tokens >= cap.max_tokens:
        return _stop("token_cap", f"the run recorded {tokens} tokens, at [autopilot] max_tokens = {cap.max_tokens}", work=lease["work"])
    if cap.max_cost and cost.get(cap.max_cost["currency"], 0.0) >= float(cap.max_cost["amount"]):
        used = round(cost[cap.max_cost["currency"]], 4)
        return _stop("cost_cap", f"the run recorded {used} {cap.max_cost['currency']}, at [autopilot] max_cost = {cap.max_cost['amount']}", work=lease["work"])
    return None


def _retro_due(i: Inputs) -> bool:
    if not i.limits.retro_every:
        return False
    done = [e for e in i.journal if e.get("code") == "learn.retro" and e.get("result") == "ok"]
    since = int(done[-1].get("merged") or 0) if done else 0
    return i.merged - since >= i.limits.retro_every


def decide(i: Inputs) -> dict:
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
        return _stop("plan_ready", "the plan is ready for a person: read it, and start autopilot again to agree to it and go on", work=work)
    paused: list[dict] = []
    if work == leasemod.ALL and _retro_due(i):
        if tripped(run, None, "learn.retro"):
            paused.append({"spec": "learn.retro", "why": "the retro failed twice in this run"})
        else:
            return _run_action("learn.retro", None, f"{i.limits.retro_every} or more changes merged since the last retro ([autopilot] retro_every)", work)
    mine = [s for s in i.steps if in_work(s, work) and flow_key(s) in contract()]
    waits_on_person = {str(s["id"]) for s in mine if not is_agent(effective(s, i)[0])}
    held = _held(i.steps)
    full = sorted(a for a, n in held.items() if i.wip_limit and n >= i.wip_limit)
    asks: list[tuple[dict, str]] = []
    blocked: list[tuple[dict, str, str]] = []
    waiting_other, watching = 0, 0
    held_back: list[dict] = []
    for s in mine:
        code, sid = flow_key(s), str(s.get("id"))
        head = i.heads.get(sid)
        if code in ("spec.blocked", "spec.blocked_by"):
            data = i.specs.get(sid) or {}
            if code == "spec.blocked" and str(data.get("blocked_on") or "").strip():
                paused.append({"spec": sid, "why": "paused with blocked_on"})
            elif code == "spec.blocked" and state.retries_used(data):
                paused.append({"spec": sid, "why": "a Task used its retries"})
                blocked.append((s, code, f"{sid} has a Task out of retries: a person re-plans it, never another agent"))
            else:
                waiting_other += 1
            continue
        acted, shown = effective(s, i)
        if not is_agent(acted):
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
        return _run_action(acted, sid, why, work, args=args, paused=paused)
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
        return _ask(s | {"who": AUTHOR}, work, code=code, why=why, blocked=True, paused=paused)
    if asks:
        s, acted = asks[0]
        return _ask(
            s, work, code=acted, why=f"{len(asks)} decision{'s' if len(asks) != 1 else ''} wait on a person in {work}", waiting=len(asks), paused=paused
        )
    if not mine and i.goal:
        code = "goal.client" if i.client else "goal.product"
        if tripped(run, None, code):
            step = {"code": code, "who": AUTHOR, "what": f"planning the goal failed twice in this run ({code})", "how": "restate the goal, or plan it yourself"}
            return _ask(step, work, why=f"{code} failed twice in a row in this run: a person looks at it", blocked=True)
        flow = flow_map()[code]
        why = f"nothing is planned for {work}: /aidd-team:{flow} turns the goal into work, and the run then stops for a person to agree"
        return _run_action(code, None, why, work, args=i.goal)
    why = f"nothing runnable in {work}"
    if paused:
        why += "; set aside: " + ", ".join(f"{p['spec']} ({p['why']})" for p in paused)
    if waiting_other:
        why += f"; {waiting_other} wait{'s' if waiting_other == 1 else ''} on other work"
    if watching:
        why += f"; {watching} shipped and watched until the observe result is due"
    if not mine:
        why += "; give `aidd autopilot next --goal` a goal to plan new work"
    return _stop("nothing_open", why, work=work, paused=paused)


_WHY = {
    "spec.verify": "built and green: Verify runs its tests and each Acceptance line on this head before Review",
    "spec.review": "verified on this head: Review reads it before a person's Merge approval",
    "spec.rework": "the last Verify or Review failed, or a listed person requested changes on this head: back to Implement",
    "spec.ready": "specified, with no Spec approval to wait for on its route: Implement builds it",
}


# ---- Reading the repository -----------------------------------------------------------------------------------


def merged_count(specs: list) -> int:
    return sum(1 for it in specs if it.status in ("shipped", "done", "rolled_back"))


def _pick_lease(root: Path, session: str | None, work: str | None, now: dt.datetime) -> tuple[dict | None, list[dict], int]:
    """(the lease the decision is for, every other lease, how many live leases make it ambiguous). Never another
    session's: with no session named, only a lone lease on record answers."""
    held = leasemod.leases(root)
    if session:
        found = [x for x in held if x["session_id"] == session]
        lease = found[-1] if found else None
        ambiguous = 0
    else:  # a lone lease may be another session's: never use one without its id
        lease, ambiguous = None, len([x for x in held if not leasemod.stale(x, now)])
    if lease is not None and work and lease["work"] != work:
        lease = None
    return lease, [x for x in held if x is not lease], ambiguous


def _lane(root: Path, cfg: cfgmod.Config | None) -> list[dict]:
    """This branch's lane step, for a change no Spec carries, named by the branch (`branch:<name>`)."""
    from .guard import _specs

    branch = gitutil.run(["rev-parse", "--abbrev-ref", "HEAD"], str(root), check=False).strip()
    if not branch or branch == "HEAD" or cfg is None:
        return []
    try:
        step = rules.lane_step(root, has_spec=bool(_specs(str(root), cfg)))
    except (gitutil.GitError, OSError, ValueError):
        return []
    return [step | {"id": f"branch:{branch}"}] if step else []


def _rejected(obs: state.Observer, heads: dict[str, str]) -> set[str]:
    """The Specs whose current head a listed person requested changes on, from the gate records aidd trusts (an
    untracked record for a commit this repository holds, in the evidence folder the base config names); never from
    the journal. It only sends work back to Implement, so it can add work, never skip a person's decision."""
    out = set()
    for r in obs.records():
        sid = str(r.get("spec_id") or "")
        if sid and heads.get(sid) == r.get("head_sha") and any((f or {}).get("code") == CHANGES_REQUESTED for f in r.get("findings") or []):
            out.add(sid)
    return out


def base_config(root: Path, obs: state.Observer) -> cfgmod.Config | None:
    """The config as the base branch holds it, read offline: the working tree's copy is agent-writable. None when the
    base has none or it does not load."""
    base = obs.base_sha
    text = gitutil.show(base, cfgmod.CONFIG_PATH, str(root)) if base else None
    if text is None or base is None:
        return None

    def offline(url: str) -> bytes:
        raise cfgmod.ConfigError(f"not fetched: {url}")

    try:
        return cfgmod.load_text(text, read=lambda p: gitutil.show(base, p, str(root)), fetch=offline)
    except Exception:  # noqa: BLE001  # an unreadable base config clears nothing: autopilot asks
        return None


class Unknown(Exception):
    """A route autopilot cannot compute: it asks a person."""


def task_route(data: dict, cfg: cfgmod.Config, tracked: list[str]) -> str:
    """The route the Spec's Task paths and risk need (`rules.assess_paths`), as an agent wrote them."""
    scopes = [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    if not scopes:
        raise Unknown("no Task scope")
    risk = data.get("risk") or {}
    try:
        return rules.assess_paths(
            cfg,
            scopes,
            ctype=str(data.get("type") or "feat"),
            dimensions=[str(d) for d in risk.get("dimensions") or []],
            irreversible=risk.get("reversible") is False,
            tracked=tracked,
        ).required_route
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc


MAX_UNTRACKED_BYTES = 20 * 1024 * 1024  # an untracked file larger than this counts as a binary
TERMINAL = frozenset({"shipped", "done", "rolled_back", "cancelled"})


def _untracked(top: str) -> list[dict]:
    """Each untracked file (ignored ones left out) as a diff entry: its lines as added, or binary as git would call it
    (a NUL byte), so the line budget counts what the working tree adds."""
    out = []
    for rel in (p for p in gitutil.run(["ls-files", "--others", "--exclude-standard", "-z"], top, check=False).split("\0") if p):
        path = Path(top) / rel
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                continue
            data = path.read_bytes() if st.st_size <= MAX_UNTRACKED_BYTES else b"\0"
        except OSError:
            continue
        binary = b"\0" in data[:8000] or st.st_size > MAX_UNTRACKED_BYTES
        lines = 0 if binary else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        out.append({"path": rel, "previous_path": None, "additions": lines, "deletions": 0, "binary": binary})
    return out


def diff_files(root: Path, base_sha: str, sha: str, *, worktree: bool) -> tuple[str, list[dict]]:
    """(the fork, every file the branch changes from it to `sha` with its lines). For this working tree: to the working
    tree instead (committed, staged, and unstaged), plus the untracked files and their lines."""
    top = str(root)
    fork = gitutil.merge_base(base_sha, sha, top)
    if not worktree:
        return fork, gitutil.numstat(fork, sha, top)
    return fork, gitutil.numstat(fork, None, top) + _untracked(top)


def diff_route(root: Path, cfg: cfgmod.Config, base_sha: str, sha: str, data: dict, *, worktree: bool) -> str | None:
    """The route the branch's real diff needs, as the gate computes it: every file from the fork to `sha` (for this
    working tree, to the working tree, untracked files included), with its changed lines (less the Specs and their
    frozen files, as the gate counts them), binaries, and added dependencies, under the base config. None when
    nothing changed."""
    from . import depdiff

    top = str(root)
    try:
        fork, files = diff_files(root, base_sha, sha, worktree=worktree)
        listed = rules.changed_paths(files)
        if not listed:
            return None
        after = (lambda p: rules._worktree_text(top, p)) if worktree else (lambda p: gitutil.show(sha, p, top))
        deps = depdiff.added(listed, lambda p: gitutil.show(fork, p, top), after)
        risk = data.get("risk") or {}
        return rules.assess(
            paths=listed,
            cfg=cfg,
            ctype=str(data.get("type") or "feat"),
            risk={"dimensions": list(risk.get("dimensions") or []), "reversible": risk.get("reversible") is not False},
            confidence="high",
            task_count=max(1, len([t for t in data.get("tasks") or [] if isinstance(t, dict)])),
            changed_lines=rules.budget_lines(files, cfg, rules._reviewed_on_branch(top, cfg, listed) + rules.proposal_only(listed, cfg)),
            binary_files=rules.counted_binaries(files, cfg, listed),
            dependencies=deps,
            binary_paths=rules.binary_paths(files),
        ).required_route
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc


def _scopes(data: dict) -> list[tuple[str, tuple[str, ...]]]:
    return sorted((str(t.get("id")), tuple(str(g) for g in t.get("scope") or [])) for t in data.get("tasks") or [] if isinstance(t, dict))


def emergency_finished(obs: state.Observer, rel: str, base: dict, text: str) -> bool:
    """Whether the base branch's copy of an emergency is finished: its post-incident review recorded
    (`outcome.learn_ref`), its repair shipped on the base branch (the facts git proves there, as `aidd list` derives
    them, since nobody stores a status in the normal flow), or a status, derived or stored, of shipped, done, rolled
    back, or cancelled."""
    if (base.get("outcome") or {}).get("learn_ref") or state.spec_status(base, approval=False) in TERMINAL:
        return True
    if not obs.base_sha:
        raise Unknown("no base branch")
    try:
        facts = obs.at(obs.base_sha, rel, text, base)
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc
    return bool(facts.shipped) or obs.status(facts, base) in TERMINAL


def same_open_emergency(root: Path, obs: state.Observer, sha: str, rel: str, data: dict, base: tuple[str, dict, str], *, worktree: bool) -> bool:
    """An emergency the base branch already holds, still open, that this copy only continues: the base copy (its
    path, front matter, and text) is an emergency and not finished (`emergency_finished`), the emergency block and
    every Task's scope are the base copy's, and the branch changes nothing beyond that scope, the Spec, and its frozen
    files. A finished emergency's id is never reused: a person declares a new emergency."""
    base_rel, data_base, text = base
    if data_base.get("route") != "emergency" or not obs.base_sha or emergency_finished(obs, base_rel, data_base, text):
        return False
    if data.get("emergency") != data_base.get("emergency") or _scopes(data) != _scopes(data_base):
        return False
    allowed = [g for _, scope in _scopes(data_base) for g in scope] + model.frozen_paths(data_base) + [rel]
    try:
        _, files = diff_files(root, obs.base_sha, sha, worktree=worktree)
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc
    return all(globs.match_any(allowed, p) for p in rules.changed_paths(files))


def needs_approval(routes: list[str | None], cfg: cfgmod.Config) -> bool:
    """Spec approval is needed on the highest of the routes given (declared, from the Tasks, from the diff)."""
    order = nextstep._ROUTE_ORDER
    known = [r for r in routes if r]
    if any(r not in order for r in known):
        raise Unknown(f"an unknown route among {known}")
    route = max(known, key=order.index)
    return route in ((cfg.gates.get("spec_approval_routes") if cfg else None) or state.DEFAULT_ROUTES)


def person_approved(root: Path, obs: state.Observer, sid: str, h: str | None, platform=None) -> bool:
    """A person approved the Spec's current hash, by a source an agent cannot write: the local approvals ref (signature-
    checked under `gates.local_approvals = "signed"`, from the base config), or the platform's own approval lines as
    the gate reads them (`github.spec_approval_holds`, with a token), only from the repository the base config pins
    (`[project] repo`) and only for this head and Spec hash. Never a record file: the evidence folder is in the working
    tree."""
    if h and any(i == sid and x == h for i, x in obs._approval_lines() or []):
        return True
    from . import github

    pinned = obs.cfg.get("project", "repo") if obs.cfg else None  # the base branch's config: a person pinned it
    return bool((platform or github.spec_approval_holds)(str(root), sid, pinned=pinned, spec_hash=h))


def _clearance(root: Path, obs: state.Observer, cfg: cfgmod.Config | None, specs: list, platform=None) -> tuple[set[str], dict[str, str]]:
    """(the Specs that may be implemented, the Specs a person must look at first, with why). A Spec is cleared when the
    highest of its declared route, the route its Tasks need, and the route the branch's real diff needs (under the base
    config) needs no Spec approval, or a person approved its current hash (`person_approved`). An emergency counts
    only when it continues an open emergency the base branch holds with the same scope (`same_open_emergency`), or a
    person approved it. Person-owned fields count only as the base branch holds them. A Spec its schema refuses is
    unknown. Never the stored status, a record file, or the declared route alone; anything unknown asks."""
    unverified: dict[str, str] = {}
    cleared: set[str] = set()
    if cfg is None or not obs.base_sha:
        return cleared, unverified
    from . import workitems

    tracked = [p for p in gitutil.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    at_base = {str(d.get("id")): (r, d, t) for r, d, _, t in workitems.objects_at(root, obs.base_sha, cfg.specs_dir)[0]}
    head = gitutil.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    for it in specs:
        data, sid = it.data, it.id
        base_copy = at_base.get(sid)
        base = base_copy[1] if base_copy else {}
        if it.sha != obs.base_sha:
            for key in ("triage", "suggested_by"):
                if data.get(key) is not None and data.get(key) != base.get(key):
                    unverified[sid] = f"`{key}` is set on the branch only"
        sha = it.sha or head
        h = obs.hash_at(sha, it.text) if sha else None
        # The diff to judge: the Spec's own branch; for a copy read from the base branch, the branch here, where
        # autopilot's Implement would run.
        work = head if it.sha in (None, obs.base_sha) else it.sha
        declared = str(data.get("route") or "normal")
        try:
            if data.get("kind", "spec") == "spec" and schema.validate(data, "spec.schema.json"):
                raise Unknown("its schema refuses the Spec")
            if declared == "emergency":
                if base_copy and h is not None and h == obs.hash_at(obs.base_sha, base_copy[2]) and emergency_finished(obs, base_copy[0], base, base_copy[2]):
                    continue  # the base branch's own copy, finished: its backfill goes on, and there is nothing to clear
                continues = bool(work) and base_copy is not None and same_open_emergency(root, obs, work, it.rel, data, base_copy, worktree=work == head)
                if continues or person_approved(root, obs, sid, h, platform):
                    cleared.add(sid)
                else:
                    unverified.setdefault(
                        sid,
                        "its emergency is not one the base branch holds open with this scope (a finished emergency's id is never reused), and no person approved it",
                    )
                continue
            routes = [declared, task_route(data, cfg, tracked), diff_route(root, cfg, obs.base_sha, work, data, worktree=work == head) if work else None]
            if not needs_approval(routes, cfg) or person_approved(root, obs, sid, h, platform):
                cleared.add(sid)
        except Unknown:
            continue  # not cleared: autopilot asks
    return cleared, unverified


_SPEC_LANE = "the spec lane: this change needs a Spec, approved before any code"


def _lane_cleared(root: Path, obs: state.Observer, cfg: cfgmod.Config | None, steps: list[dict]) -> set[str]:
    """The branch's lane step may run Implement only when its real diff, judged under the base config (not the working
    tree's), needs no Spec approval: the fast lane as the gate would find it. A fast-lane step whose diff needs Spec
    approval becomes the spec lane's step: no Spec carries the change, so no Spec approval can be given, and a Spec
    comes first."""
    head = gitutil.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    out = set()
    for s in steps:
        if s.get("code") != "lane" or cfg is None or not obs.base_sha or not head:
            continue
        try:
            route = diff_route(root, cfg, obs.base_sha, head, {}, worktree=True)
            if route and not needs_approval([route], cfg):
                out.add(str(s["id"]))
            elif route and s.get("lane") == "fast":
                s.update(lane="spec", route=route, what=_SPEC_LANE, how='write the Spec and its tests first: `aidd new spec <ID> --title "..."`')
        except Unknown:
            continue
    return out


def gather(root: Path, *, work: str | None = None, session: str | None = None, goal: str | None = None, now: dt.datetime | None = None) -> Inputs:
    """The decision's inputs, read from the repository: `aidd list`'s steps, the lease and journal, and the config."""
    t = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    steps, specs = nextstep.open_work(root, t.date(), t)
    cfg = None
    if (root / cfgmod.CONFIG_PATH).is_file():
        try:
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(root))
        except (cfgmod.ConfigError, OSError, ValueError):
            cfg = None
    if not any(str(s.get("code", "")).startswith("setup.") for s in steps):
        steps = steps + _lane(root, cfg)
    heads = {it.id: it.sha for it in specs if it.sha}
    head = gitutil.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    heads |= {it.id: head for it in specs if not it.sha and head}
    lease, others, ambiguous = _pick_lease(root, session, work, t)
    trusted = base_config(root, state.Observer(root, None))
    obs = state.Observer(root, trusted)  # local_approvals mode and the evidence folder as the base branch says
    cleared, unverified = _clearance(root, obs, trusted, specs)
    cleared |= _lane_cleared(root, obs, trusted, steps)
    return Inputs(
        steps=steps,
        specs={it.id: it.data for it in specs},
        heads=heads,
        rejected=_rejected(obs, heads),
        cleared=cleared,
        unverified=unverified,
        lease=lease,
        session=session,
        others=others,
        work=work,
        ambiguous=ambiguous,
        journal=leasemod.journal(root),
        limits=Limits.of(cfg),
        wip_limit=int(cfg.gates.get("max_open_per_approver") or 0) if cfg else 0,
        merged=merged_count(specs),
        goal=goal,
        client=bool(cfg and cfg.get("project", "work") == "client"),
        now=t,
    )


_EVENT = {"timebox": "limit_reached", "token_cap": "limit_reached", "cost_cap": "limit_reached", "nothing_open": "finished", "plan_ready": "finished"}


def record(root: Path, action: dict, lease: dict | None, now: dt.datetime | None = None) -> dict | None:
    """The run event an action says, once: an `ask` waits on a person (or is blocked); a stop at a limit, with a plan
    ready, or with nothing open ends the run. Nothing for a `run` (its note says it) or with no lease. Not repeated
    while the run's last event already says the same."""
    if lease is None:
        return None
    if action["action"] == "ask":
        event, fields = ("blocked" if action.get("blocked") else "waiting_on_person"), {"code": action.get("code"), "who": action.get("who")}
    elif action["action"] == "stop" and action.get("reason") in _EVENT:
        event, fields = _EVENT[action["reason"]], {"reason": action["reason"]}
    else:
        return None
    spec = action.get("spec")
    mine = [e["run"] for e in leasemod.events(root) if (e.get("run") or {}).get("session_id") == lease["session_id"]]
    key = {"event": event, "spec_id": spec, **fields}
    if mine and all(mine[-1].get(k) == v for k, v in key.items() if v is not None) and mine[-1].get("event") == event:
        return None
    return leasemod.record_event(root, event, lease, spec_id=spec, now=now, **fields)


def next_action(
    root: Path, *, work: str | None = None, session: str | None = None, goal: str | None = None, now: dt.datetime | None = None, write: bool = True
) -> dict:
    """`aidd autopilot next`: gather, decide, and (with `write`) record the run event the action says."""
    i = gather(root, work=work, session=session, goal=goal, now=now)
    action = decide(i)
    if i.lease is not None:
        action["lease"] = {"session_id": i.lease["session_id"], "work": i.lease["work"], "expires_at": i.lease["expires_at"]}
    action["limits"] = i.limits.as_dict()
    if write:
        record(root, action, i.lease, now=i.now)
    return action


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
    return "\n".join(lines) + "\n"
