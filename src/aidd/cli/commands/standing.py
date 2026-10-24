"""A person's standing approval (`aidd approve all`): from it on, the agent records each Spec approval and Merge
approval it covers, citing it, until the person stops it (`aidd approve stop`). The record is in
workitems/decision_records.py; `aidd approve` and `aidd land` read it through `standing_for`."""

from __future__ import annotations

import json
import sys

from aidd import gate, platforms, tracking, workitems
from aidd.cli import arguments
from aidd.cli.commands.confirmations import DECIDED_WHERE, confirmation_problem, local_identity_problem, outside_shown, standing_identity
from aidd.kernel import documents, git


def record(args) -> tuple[str, str] | int:
    """`aidd approve all` or `aidd approve stop`: the record and what to say, or the exit code that stops it. Only a
    person starts one, at their terminal or by their typed or confirmed words; anyone may stop one."""
    if args.what == "stop":
        return workitems.standing_line("stop"), "Stopped approving for you: each approval waits for you again" + _auto_merges_off()
    scope = "all" + ("-and-publish" if getattr(args, "and_publish", False) else "") + ("-but-major" if args.but_major else "")
    if args.until and workitems.day(args.until) is None:
        print(f"error: --until {args.until!r} is not a date: use YYYY-MM-DD", file=sys.stderr)
        return 2
    what = scope_text(scope)
    until = f" until {args.until}" if args.until else " until you stop it"
    if args.show:
        # What a dialog shows before the person answers: what it covers, and what changed outside the session since
        # their last decision, which their answer takes in.
        outside, unread = outside_shown()
        print(json.dumps({"scope": scope, "covers": f"{what}{until}", **outside, "problems": [unread] if unread else []}, indent=2))
        return 0
    if args.confirmed is None:
        platforms.check_terminal("A standing approval", "aidd approve all")
    elif args.confirmed != scope:
        print(f"error: you confirmed {args.confirmed!r}, but this asks for {scope!r}. Nothing was recorded", file=sys.stderr)
        return 1
    elif problem := confirmation_problem(args.decided_via):
        print(f"error: not recorded: {problem}", file=sys.stderr)
        return 2 if not DECIDED_WHERE.fullmatch(args.decided_via) else 1
    login, problem = standing_identity()
    if problem := problem or local_identity_problem():
        print(f"error: not recorded: {problem}", file=sys.stderr)
        return 1
    remote, urls = None, None
    if "and-publish" in scope:
        remotes = git.run(["remote"], check=False).split()
        remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None
        if remote is None:
            print("error: not recorded: publishing needs one remote to publish to (`origin`, or the only remote): add it, then approve again", file=sys.stderr)
            return 1
        urls = workitems.remote_urls(".", remote)
        what += f", to {remote} ({', '.join(urls)})"
    line = workitems.with_login(workitems.standing_line(scope, args.until, remote=remote, urls=urls), login)
    who = f" as @{login}" if login else ""
    done = f"Approving {what} for you{who}{until}. To end it: `/aidd stop`, or type `stop approving` (`aidd approve stop` at your own terminal)"
    if args.confirmed is not None:
        return workitems.decided_via(line, args.decided_via), done
    platforms.require_person("A standing approval", command="aidd approve all", question=f"Let the agent record {what} for you{until}?")
    return line, done


def scope_text(scope: str) -> str:
    """What a standing approval of `scope` covers, in the person's words."""
    publish = " and publishing" if "and-publish" in scope else ""
    major = ", except on major changes," if scope.endswith("but-major") else ""
    return f"every Spec approval and Merge approval{publish}{major}"


def standing_for(route: str | None, *, merge: bool = False) -> dict | None:
    """The person's standing approval when it covers a change on `route`, else None (workitems.live_standing_for). A
    route aidd does not know is never covered, and neither is the Merge approval (`merge`) of a launch: the change that
    turns a flagged feature on for users, which stays the person's (launching)."""
    if route not in tracking.ROUTE_ORDER:
        return None
    cfg = arguments.config_or_none_quiet()
    standing = workitems.live_standing_for(cfg, ".")
    if not workitems.standing_covers(standing, route):
        return None
    if merge and (launch := launching(cfg)):
        print(f"note: this change launches {launch}: the launch is a person's decision, so your standing approval does not cover it")
        return None
    return standing


def launching(cfg) -> str | None:
    """The launch this branch carries, as "<Spec> of <Epic>": any Spec its diff against the default branch holds that a
    flagged Epic on the default branch names as its `launch`, whichever Spec binds the branch; None when there is none."""
    if cfg is None:
        return None
    try:
        base = git.default_base(".")
        launches = workitems.launches_at(".", base, cfg.specs_dir)
        fork = git.merge_base(git.rev_parse(base), git.rev_parse("HEAD"))
    except git.GitError:
        return None
    changed = [p for p in git.run(["diff", "--name-only", "-z", fork, "HEAD", "--", cfg.specs_dir], check=False).split("\0") if p.endswith(".md")]
    mine = []
    for path in changed:
        try:
            data = documents.split_front_matter(git.show("HEAD", path) or "", path)[0]
        except documents.DocumentError:
            continue
        if data.get("kind") == "spec":
            mine.append(str(data.get("id")))
    hit = next((s for s in mine if s in launches), None)
    return f"{hit} of {launches[hit]}" if hit else None


def spec_route(data: dict) -> str | None:
    """The route a standing approval must cover to approve a Spec: the higher of the route it declares and the route its
    Tasks' scopes and risk need, as `aidd gate --paths` computes it. An agent writes the declared one. None when either
    is unknown."""
    cfg = arguments.config_or_none_quiet()
    scopes = [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    declared = str(data.get("route") or "normal")
    if cfg is None or not scopes or declared not in tracking.ROUTE_ORDER:
        return None
    risk = data.get("risk") or {}
    tracked = [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]
    try:
        needed = gate.assess_paths(
            cfg,
            scopes,
            ctype=str(data.get("type") or "feat"),
            dimensions=[str(d) for d in risk.get("dimensions") or []],
            irreversible=risk.get("reversible") is False,
            tracked=tracked,
        ).required_route
    except Exception:  # noqa: BLE001  # a route aidd cannot compute is a route the standing approval does not cover
        return None
    return max(declared, needed, key=tracking.ROUTE_ORDER.index) if needed in tracking.ROUTE_ORDER else None


def _auto_merges_off() -> str:
    """Where a platform's gate decides, turn off the auto-merges the standing approval turned on, and say so; the stop
    itself never waits on GitHub."""
    if not gate.trunk_on_platform("."):
        return ""
    cfg = arguments.config_or_none_quiet()
    off, why = platforms.disable_standing_auto_merges(".", list(cfg.approvers) if cfg else [])
    said = f". Turned off the auto-merge it turned on: {', '.join(off)}" if off else ""
    if why:
        said += f". aidd could not turn off every auto-merge it turned on ({why}): turn them off on the open pull requests"
    return said
