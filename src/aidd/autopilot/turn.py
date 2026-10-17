"""One autopilot turn (`aidd autopilot next`): gather the decision's inputs from the repository, decide, and record the run event the action says."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config, gate, workitems
from aidd.autopilot import clearance, engine, usage
from aidd.autopilot import lease as leasemod
from aidd.kernel import git

CHANGES_REQUESTED = "merge_approval.changes_requested"


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
        limits=engine.Limits.of(cfg),
        wip_limit=int(cfg.gates.get("max_open_per_approver") or 0) if cfg else 0,
        merged=merged_count(specs),
        goal=goal,
        client=bool(cfg and cfg.get("project", "work") == "client"),
        now=t,
        resume=resume_command(root),
        measured=usage.measured_tokens(lease["session_id"], str(lease["started_at"])) if lease else None,
    )


# `aidd init --team` installs the flows as repository files named `aidd-<flow>.md`; without them the plugin's name holds.
_INSTALLED = (".claude/commands/aidd-autopilot.md", ".opencode/commands/aidd-autopilot.md")


def resume_command(root: Path) -> str:
    """The autopilot command as this repository's install names it: `/aidd-autopilot` from repository files, else the
    aidd-team plugin's `/aidd-team:autopilot`."""
    return "/aidd-autopilot" if any((root / f).is_file() for f in _INSTALLED) else engine.RESUME


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
    action = engine.decide(i)
    if i.lease is not None:
        action["lease"] = {"session_id": i.lease["session_id"], "work": i.lease["work"], "expires_at": i.lease["expires_at"]}
    action["limits"] = i.limits.as_dict()
    if write and record(root, action, i.lease, now=i.now) is not None:
        notify(root, action)
    return action


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
