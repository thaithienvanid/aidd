"""The Understand commands: list, log, owners, metrics, and digest."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aidd import config, tracking
from aidd.cli import arguments, local_events
from aidd.kernel import extensions, git

# The version of `aidd owners --json` (schemas/owners.schema.json): a new key keeps it, a renamed or removed one bumps it.
OWNERS_SCHEMA_VERSION = "1"


def cmd_digest(args) -> int:
    """A status rollup for the window: the team view, or the client view with a RAG status (--client)."""
    from aidd import views

    if args.include_cost and not args.client:
        raise ValueError("--include-cost goes with --client: the team view shows the cost whenever --cost is given")
    if args.blocked_days < 0:
        raise ValueError("--blocked-days is a number of days, 0 or more")
    if args.html is not None and not args.client:
        raise ValueError("--html goes with --client: the page is for the client; the team view is Markdown or --json")
    html_path = arguments.html_arg(args.html)
    args.events = [str(Path(p).resolve()) for p in args.events or []]
    arguments.enter_repo(args, file_attrs=("cost",))
    if arguments.config_or_none() is None:
        raise ValueError(f"no {config.CONFIG_PATH}: `aidd init` first")
    args.since = args.since or tracking.default_since(Path("."))
    window = tracking.rollup_window(Path("."), args.since)
    # The team view reads this repository's own events too; the client's view keeps aidd-events.jsonl alone, so no
    # line anyone here can edit reaches a client's cost figure.
    defaults = [p for p in (tracking.ROLLUP_EVENTS_FILE,) if Path(p).is_file()] if args.client else local_events.default_files()
    paths = args.events if args.events else defaults
    events = tracking.load_events(paths, since=window.start.isoformat()) if paths else []
    ledger = tracking.load_ledger(args.cost, since=window.start.isoformat()) if args.cost else None
    d = tracking.status_digest(
        Path("."), args.since, client=args.client, events=events, ledger=ledger, include_cost=args.include_cost, blocked_days=args.blocked_days
    )
    if html_path is not None:
        out = views.write(html_path or views.default_path("digest", f"{d['view']}-{d['generated_on']}"), tracking.digest_page(d))
        print(f"wrote {arguments.repo_relative(out)}", file=sys.stderr)
    print(json.dumps(d, indent=2) if args.json else tracking.digest_markdown(d), end="\n" if args.json else "")
    return 0


def cmd_log(args) -> int:
    """One Spec's history: status transitions, approvals, and Assisted-by trailers."""
    from aidd import workitems

    records = [str(Path(r).resolve()) for r in args.record or []]  # before entering the root: relative to where it ran
    arguments.enter_repo(args, *(("spec",) if args.spec.endswith(".md") else ()))
    log = workitems.build_spec_history(Path("."), args.spec, records)
    print(
        json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION} | log, indent=2) if args.json else workitems.spec_history_markdown(log),
        end="\n" if args.json else "",
    )
    return 0


def _with_standing(listed: dict) -> tuple[dict, str]:
    """`aidd list`'s JSON with the person's standing approval in force, and the line its text starts with: so nobody
    forgets that the agent approves for them."""
    from aidd import workitems

    cfg = arguments.config_or_none_quiet()
    head = ""
    if workitems.is_explore(branch := workitems.current_branch(".")):
        listed["explore_branch"] = branch
        head += f"{workitems.explore_note(branch)}\n"
    standing = workitems.live_standing_for(cfg, ".")
    if standing:
        listed["standing"] = {k: standing[k] for k in ("scope", "since", "by", "until") if standing.get(k)}
        but = " except on major changes" if standing["scope"] == "all-but-major" else ""
        head += f"Approving every Spec approval and Merge approval for you{but}, since {standing['since'][:16]}. Type `stop approving` to end it.\n"
    return listed, head + ("\n" if head else "")


def _goals_and_flow(args, steps: list[dict], listed: dict) -> str:
    """`aidd list`'s goals and its trunk-based flow, added to its JSON when there are any, and the lines its text
    starts with for them."""
    from aidd import workitems

    cfg = arguments.config_or_none_quiet()
    note = ""
    if workitems.goal_branches("."):
        every = tracking.plan(Path("."), filters=tracking.Filters(all=True)) if _list_filters(args).active() else steps
        if found := tracking.goals(".", cfg, every):
            listed["goals"] = found
            note += tracking.goals_markdown(found)
    if branches := workitems.work_branches("."):
        listed["flow"] = {"branches": branches, "warnings": workitems.flow_warnings(branches, cfg)}
        note = "".join(f"{w}\n" for w in listed["flow"]["warnings"]) + note
    return note


def _list_filters(args):

    return tracking.Filters(
        all=not args.branch, mine=args.mine, agent=args.agent, blocked=args.blocked, waiting_on_me=args.waiting_on_me, label=args.label, priority=args.priority
    )


def cmd_list(args) -> int:
    """All open work, from the base branch and every open branch, and who holds each step; with --branch, only this
    branch's change and the other branches it overlaps."""
    from aidd import workitems

    if args.branch and (args.repos or args.upkeep or args.html is not None):
        raise ValueError("--branch lists this branch's change: run it on the branch, without REPO, --upkeep, or --html")
    if args.html is not None and args.repos:
        raise ValueError("--html renders one repository's decisions: run it in that repository, without REPO")
    if args.events and not args.upkeep:
        raise ValueError("--events goes with --upkeep: the gate events that name flaky tests")
    if args.upkeep:
        if args.repos or args.html is not None:
            raise ValueError("--upkeep lists one repository's upkeep: run it in that repository, without REPO or --html")

        events = [str(Path(e).resolve()) for e in args.events or []]  # as given, before the move to the top
        arguments.enter_repo(args)
        found = tracking.upkeep_items(Path("."), events=events)
        shown = {"schema_version": arguments.JSON_SCHEMA_VERSION, "items": found}
        print(json.dumps(shown, indent=2) if args.json else tracking.upkeep_markdown(found), end="\n" if args.json else "")
        return 0
    if not args.repos:
        arguments.enter_repo(args, file_attrs=("html",))
        steps = tracking.plan(Path("."), filters=_list_filters(args))
        if args.html is not None:
            from aidd import views

            title = "Decisions waiting on you" if args.waiting_on_me else "Open work"
            out = views.write(
                args.html or views.default_path("decisions", "waiting-on-me" if args.waiting_on_me else "list"), views.decision_page(steps, title)
            )
            print(f"wrote {arguments.repo_relative(out)}", file=sys.stderr)
        listed, note = _with_standing({"schema_version": arguments.JSON_SCHEMA_VERSION, "steps": steps})
        if not args.branch:
            note = _goals_and_flow(args, steps, listed) + note
        print(json.dumps(listed, indent=2) if args.json else note + tracking.next_steps_markdown(steps), end="" if not args.json else "\n")
        return 0
    # A project in several repositories: each one answers for itself, from its own root.
    everything: dict[str, list[dict]] = {}
    here = os.getcwd()
    for path in args.repos:
        top = git.toplevel(path) if Path(path).is_dir() else ""
        if not top:
            everything[path] = [tracking.new_step(f"{path} is not a git repository", workitems.AUTHOR, "check the path")]
            continue
        os.chdir(top)
        try:
            everything[path] = tracking.plan(Path(top), filters=_list_filters(args))
        finally:
            os.chdir(here)
    if args.json:
        print(json.dumps({"schema_version": arguments.JSON_SCHEMA_VERSION, "repos": everything}, indent=2))
    else:
        print("\n".join(f"## {path}\n\n{tracking.next_steps_markdown(steps)}" for path, steps in everything.items()), end="")
    return 0


def cmd_owners(args) -> int:
    """Who decides and who does the work: the humans who approve and every agent role, with the team's goal."""
    from aidd import knowledge

    arguments.enter_repo(args)
    r = knowledge.owners_view(arguments.config_or_none(), changed=args.changed, root=Path("."))
    # The JSON carries the version of its shape (schemas/owners.schema.json), like `aidd metrics --json`.
    print(json.dumps({"schema_version": OWNERS_SCHEMA_VERSION} | r, indent=2) if args.json else knowledge.owners_markdown(r))
    return 0


def cmd_metrics(args) -> int:
    if args.flaky and (args.autopilot or args.guard or args.target_wait is not None):
        raise ValueError("--flaky goes alone, not with --autopilot, --guard, or --target-wait")
    if args.autopilot:
        return _metrics_autopilot(args)
    if args.guard:
        if args.guard == arguments.GUARD_LOG_DEFAULT:
            # The hook keeps its log in the git directory, one for every worktree, wherever this runs from.
            try:
                args.guard = str(config.guard_log(git.toplevel(check=True)))
            except (git.GitError, OSError, ValueError):
                raise ValueError("--guard with no path reads the guard's log in the git directory: run it inside a git repository") from None
        counts = tracking.guard_denials(tracking.load_events([args.guard], since=args.since) if Path(args.guard).is_file() else [])
        print(json.dumps(counts, indent=2) if args.json else tracking.guard_markdown(counts, args.guard), end="\n" if args.json else "")
        return 0
    named = bool(args.events)
    # No file named: this repository's own gate events, kept in the git directory by every local gate run.
    args.events = args.events or local_events.default_files()
    if args.suggest_standard_changes and not args.autonomy:
        raise ValueError("--suggest-standard-changes goes with --autonomy")
    if args.cost and (args.by or args.dora or args.autonomy):
        raise ValueError("--cost goes with the summary, not with --by, --dora, or --autonomy")
    if args.flaky and (args.by or args.dora or args.autonomy or args.cost or args.specs or args.render):
        raise ValueError("--flaky goes alone, not with --by, --dora, --autonomy, --cost, --specs, or --render")
    skipped: list[str] = []
    lines = tracking.load_events(args.events, since=args.since, skipped_lines=skipped) if args.events else []
    events = tracking.gate_events(lines)
    tests = [e for e in lines if e.get("kind") == "test"]  # `aidd test` runs, for the suite runs per head
    for line in skipped:
        print(f"warning: {line}", file=sys.stderr)
    if not named and not events and not tests:
        print(
            "aidd metrics: no gate events yet: a local `aidd gate` run on a branch keeps one in .git/aidd/events.jsonl. "
            "Or name event files (the CI's aidd-events.jsonl), or use --guard [PATH]",
            file=sys.stderr,
        )
        return 2
    if args.tenant:
        events = [e for e in events if e.get("tenant") == args.tenant]
    if args.flaky:
        out = tracking.flaky(events)
        print(json.dumps(out, indent=2) if args.json else tracking.flaky_markdown(out), end="\n" if args.json else "")
        return 0
    cfg = arguments.config_or_none()
    targets = cfg.get("targets", default={}) if cfg else {}
    if args.by:
        groups = tracking.grouped_metrics(events, args.by, args.target_wait, targets)
        shown = {"schema_version": tracking.METRICS_SCHEMA_VERSION, "by": args.by, "groups": groups}
        print(json.dumps(shown, indent=2) if args.json else tracking.markdown_grouped(groups, args.by))
        return 0
    if args.dora:
        rows = tracking.dora(events, Path(args.specs) if args.specs else None, targets)
        table = {"schema_version": tracking.METRICS_SCHEMA_VERSION, "rows": rows}
        print(json.dumps(table, indent=2) if args.json else tracking.dora_markdown(rows), end="" if not args.json else "\n")
        return 1 if any(r["met"] is False for r in rows) else 0
    if args.autonomy:
        rows = tracking.autonomy(events, **(cfg.get("agents", "autonomy", default={}) if cfg else {}))
        if args.suggest_standard_changes:
            proposals = tracking.propose_standard_changes(events, rows, arguments.TYPES)
            out = {"schema_version": tracking.METRICS_SCHEMA_VERSION, "proposals": proposals}
            print(json.dumps(out, indent=2) if args.json else tracking.proposals_text(proposals), end="\n" if args.json else "")
            return 0
        print(json.dumps({"schema_version": tracking.METRICS_SCHEMA_VERSION, "rows": rows}, indent=2) if args.json else tracking.autonomy_markdown(rows))
        return 0
    s = tracking.summarize_events(events, args.target_wait, targets) | {"suite_runs": tracking.suite_runs(tests)}
    if args.specs:
        s |= tracking.delivery_outcomes(Path(args.specs)) | {"handoffs": tracking.handoff_health(Path(args.specs))}
    if args.cost:
        cap = cfg.get("agents", "max_cost_per_change") if cfg else None
        s["cost"] = tracking.cost_per_change(events, tracking.load_ledger(args.cost, since=args.since), targets, s["first_pass_share"], cap)
        for o in s["cost"]["over_cap"]:  # a warning per change, never the exit code
            print(
                f"warning: change {o['change']} cost {o['amount']} {o['currency']}, over `agents.max_cost_per_change` ({s['cost']['cap']['amount']} {s['cost']['cap']['currency']})",
                file=sys.stderr,
            )
    if args.render:
        renderers = extensions.installed("aidd.renderers")
        if args.render not in renderers:
            raise ValueError(f"no renderer {args.render!r}; installed: {', '.join(sorted(renderers)) or 'none'}")
        print(renderers[args.render](s), end="")
    else:
        print(json.dumps(s, indent=2) if args.json else tracking.metrics_markdown(s))
    # A missed loop-speed target fails the run, like a DORA target; cost is display only and never sets the exit code.
    return 1 if any(r["met"] is False for r in s["loop_speed"]) else 0


def _metrics_autopilot(args) -> int:
    """`aidd metrics --autopilot`: the autopilot runs' own measures, from the run events in the
    git directory (and any event files given) and the guard's log."""
    from aidd import autopilot

    if args.autonomy:
        raise ValueError("--autopilot goes without --autonomy: --autonomy is the stage of each agent, --autopilot the runs' measures")
    paths = list(args.events or [])
    try:
        top = Path(git.toplevel(check=True))
        mine = autopilot.lease_store(top) / autopilot.RUN_EVENTS_FILE
        if mine.is_file():
            paths.append(str(mine))
        guard = Path(args.guard) if args.guard and args.guard != arguments.GUARD_LOG_DEFAULT else config.guard_log(top)
    except (git.GitError, OSError, ValueError):
        guard = Path(args.guard) if args.guard and args.guard != arguments.GUARD_LOG_DEFAULT else Path(os.devnull)
    events = tracking.load_events(paths, since=args.since) if paths else []
    denials = tracking.load_events([str(guard)], since=args.since) if guard.is_file() else []
    out = tracking.autopilot_run_measures(events, denials)
    print(json.dumps(out, indent=2) if args.json else tracking.runs_markdown(out), end="\n" if args.json else "")
    return 0
