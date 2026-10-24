"""One autopilot turn (`aidd autopilot next`): gather the decision's inputs from the repository, decide, and record the run event the action says."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config, gate, workitems
from aidd.autopilot import clearance, engine, harness_commands, session_transcripts
from aidd.autopilot import lease as leasemod
from aidd.kernel import git

CHANGES_REQUESTED = "merge_approval.changes_requested"


def merged_count(specs: list) -> int:
    return sum(1 for it in specs if it.status in ("landed", "done", "rolled_back"))


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
    lines = leasemod.events(root)  # a run that ended, or waits on a person, holds nothing against this one
    return lease, [x for x in held if x is not lease and not leasemod.ended(root, x, over=leasemod.OVER_FOR_RIVALS, lines=lines)], ambiguous


def _lane(root: Path, cfg: config.Config | None) -> list[dict]:
    """This branch's lane step, for a change no Spec carries, named by the branch (`branch:<name>`)."""

    branch = git.run(["rev-parse", "--abbrev-ref", "HEAD"], str(root), check=False).strip()
    if not branch or branch == "HEAD" or cfg is None:
        return []
    try:
        step = gate.lane_step(root, has_spec=bool(workitems.active_specs(str(root), cfg)))
    except (git.GitError, OSError, ValueError):
        return []
    return [step | {"id": f"branch:{branch}"}] if step else []


def _rejected(obs: workitems.Observer, heads: dict[str, str]) -> set[str]:
    """The Specs whose current head a listed person requested changes on, from the gate records aidd trusts (an
    untracked record for a commit this repository holds, in the evidence folder the base config names); never from
    the journal. It only sends work back to Implement, so it can add work, never skip a person's decision."""
    out = set()
    for r in obs.records():
        sid = str(r.get("spec_id") or "")
        if sid and heads.get(sid) == r.get("head_sha") and any((f or {}).get("code") == CHANGES_REQUESTED for f in r.get("findings") or []):
            out.add(sid)
    return out


def base_config(root: Path, obs: workitems.Observer) -> config.Config | None:
    """The config as the base branch holds it, read offline: the working tree's copy is agent-writable. None when the
    base has none or it does not load."""
    base = obs.base_sha
    text = git.show(base, config.CONFIG_PATH, str(root)) if base else None
    if text is None or base is None:
        return None

    def offline(url: str) -> bytes:
        raise config.ConfigError(f"not fetched: {url}")

    try:
        return config.load_text(text, read=lambda p: git.show(base, p, str(root)), fetch=offline)
    except Exception:  # noqa: BLE001  # an unreadable base config clears nothing: autopilot asks
        return None


def gather(root: Path, *, work: str | None = None, session: str | None = None, goal: str | None = None, now: dt.datetime | None = None) -> engine.Inputs:
    """The decision's inputs, read from the repository: `aidd list`'s steps, the lease and journal, and the config."""
    from aidd import tracking  # inside: the guard reads the lease, which loads this package, on every edit

    t = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    steps, specs = tracking.open_work(root, t.date(), t)
    cfg = None
    if (root / config.CONFIG_PATH).is_file():
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root))
        except (config.ConfigError, OSError, ValueError):
            cfg = None
    if not any(str(s.get("code", "")).startswith("setup.") for s in steps):
        steps = steps + _lane(root, cfg)
    heads = {it.id: it.sha for it in specs if it.sha}
    head = git.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    heads |= {it.id: head for it in specs if not it.sha and head}
    lease, others, ambiguous = _pick_lease(root, session, work, t)
    trusted = base_config(root, workitems.Observer(root, None))
    obs = workitems.Observer(root, trusted)  # local_approvals mode and the evidence folder as the base branch says
    cleared, unverified = clearance.cleared_specs(root, obs, trusted, specs)
    cleared |= clearance.lane_cleared(root, obs, trusted, steps)
    return engine.Inputs(
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
        journal=leasemod.read_journal(root),
        limits=engine.Limits.of(trusted),  # the base branch's: an agent writes the working tree's
        wip_limit=int(trusted.limits.get("max_open_per_approver") or 0) if trusted else 0,  # the base branch's, as the limits
        merged=merged_count(specs),
        goal=goal,
        client=bool(cfg and cfg.get("project", "work") == "client"),
        now=t,
        resume=resume_command(root),
        measured=session_transcripts.measured_tokens(lease["session_id"], str(lease["started_at"])) if lease else None,
    )


def resume_command(root: Path) -> str:
    """The autopilot command as this repository's install names it: `/aidd-autopilot` where `aidd init --team` wrote
    the flow as a repository file for any harness (`setup.flow_command_paths`: Claude Code, OpenCode, Grok Build, or
    Antigravity), else the aidd-team plugin's `/aidd-team:autopilot`."""
    from aidd import setup

    return "/aidd-autopilot" if any((root / f).is_file() for f in setup.flow_command_paths("autopilot")) else engine.RESUME


_EVENT = {
    "timebox": "limit_reached",
    "token_cap": "limit_reached",
    "cost_cap": "limit_reached",
    "nothing_open": "finished",
    "plan_ready": "finished",
    "stalled": "blocked",
}


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
    mine = [
        e["run"]
        for e in leasemod.events(root)
        if (e.get("run") or {}).get("session_id") == lease["session_id"] and e["run"].get("result") != leasemod.ANNOUNCED  # a mid-run notice is no stop
    ]
    key = {"event": event, "spec_id": spec, **fields}
    if mine and all(mine[-1].get(k) == v for k, v in key.items() if v is not None) and mine[-1].get("event") == event:
        return None
    return leasemod.record_event(root, event, lease, spec_id=spec, now=now, **fields)


def next_action(
    root: Path,
    *,
    work: str | None = None,
    session: str | None = None,
    goal: str | None = None,
    now: dt.datetime | None = None,
    write: bool = True,
    harness: str | None = None,
) -> dict:
    """`aidd autopilot next`: gather, decide, and (with `write`) record the run event the action says. With `harness`,
    every team command the action names is in that harness's form (`forms.in_harness`)."""
    i = gather(root, work=work, session=session, goal=goal, now=now)
    if harness:
        i.resume = harness_commands.flow_form(root, harness, "autopilot")[0]
    action = engine.decide(i)
    if harness:
        action = harness_commands.in_harness(action, root, harness)
    if i.lease is not None:
        action["lease"] = {"session_id": i.lease["session_id"], "work": i.lease["work"], "expires_at": i.lease["expires_at"]}
    action["limits"] = i.limits.as_dict()
    if write and i.lease is not None:
        specs = [str(a["spec"]) for a in (action, *(action.get("also") or [])) if a.get("spec")]
        leasemod.remember_next(root, i.lease["session_id"], given_codes(action), list(dict.fromkeys(specs)))
    if write and record(root, action, i.lease, now=i.now) is not None:
        notify(root, action)
    elif write and action["action"] == "run" and (new := announce(root, i, now=i.now)):
        action["decisions"] = new
        notify(root, {"message": "Autopilot goes on, and a decision waits on you: " + "; ".join(f"{d['what']} ({d.get('how', '')})" for d in new)})
    return action


def announce(root: Path, inputs: engine.Inputs, now: dt.datetime | None = None) -> list[dict]:
    """The decisions in the run's work that started waiting on a person while the run goes on with other work, each
    recorded once as a `waiting_on_person` event marked as announced, so the person hears of it now, not at the end."""
    if inputs.lease is None:
        return []
    lease = inputs.lease
    said = {
        (e["run"].get("spec_id"), e["run"].get("code"))
        for e in leasemod.events(root)
        if (e.get("run") or {}).get("session_id") == lease["session_id"]
        and str(e.get("ts")) >= str(lease["started_at"])
        and e["run"].get("event") == "waiting_on_person"
    }
    new = [d for d in engine.decisions(inputs, str(lease["work"])) if (d.get("spec"), d.get("code")) not in said]
    for d in new:
        leasemod.record_event(root, "waiting_on_person", lease, spec_id=d.get("spec"), code=d.get("code"), who=d.get("who"), result=leasemod.ANNOUNCED, now=now)
    return new


def given_codes(action: dict) -> list[str]:
    """Every step code an action gives the run to note: its own, those it takes side by side, and those beside it."""
    out = [action.get("code"), *(action.get("codes") or [])]
    for a in action.get("also") or []:
        out += [a.get("code"), *(a.get("codes") or [])]
    return [str(c) for c in dict.fromkeys(out) if c]


NOTIFY_TIMEOUT_S = 10


def notify(root: Path, action: dict) -> None:
    """Run `autopilot.notify` once for a stop a person must hear of (record wrote its event): the base branch's config
    names the command, never the working tree's, since an agent writes that one. Whatever it does, the run goes on."""
    import os
    import subprocess

    cfg = base_config(root, workitems.Observer(root, None))
    argv = (cfg.get("autopilot", "notify") if cfg else None) or []
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        return
    text = " ".join(str(action.get("message") or action.get("why") or "aidd autopilot stopped").split())[:500]
    try:
        subprocess.run([*argv, text], cwd=root, env=os.environ | {"AIDD_NOTICE": text}, timeout=NOTIFY_TIMEOUT_S, capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
