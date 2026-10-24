"""The Understand commands' arguments and flags: list, log, owners, metrics, and digest."""

from __future__ import annotations

import argparse

from aidd import tracking
from aidd.cli import arguments


def register(cmd, flag) -> None:
    """Add the understand commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""

    def list_args(s: argparse.ArgumentParser) -> None:
        s.add_argument("repos", nargs="*", metavar="REPO", help="the repositories of a project, such as api web infra; default: this one")
        flag(s, "--json", "print the steps as JSON")
        flag(s, "--mine", "only work you own (`owner`), with a Task assigned to you, or that you added (git user.email/name, GitHub login)")
        s.add_argument("--agent", nargs="?", const="", metavar="ROLE", help="only Specs with a todo Task assigned to an agent (to agent:ROLE when given)")
        flag(s, "--blocked", "only blocked work: blockers set, blocked_by unfinished work, or a Task out of retries")
        flag(s, "--waiting-on-me", "the Approver inbox: approvals waiting on you, and a warning past limits.max_open_per_approver")
        s.add_argument("--label", metavar="LABEL", help="only Specs with this label")
        s.add_argument(
            "--priority", choices=["urgent", "high", "medium", "low"], metavar="LEVEL", help="only work at this priority or higher (urgent, high, medium, low)"
        )

    s = cmd(
        "list",
        "all open work, one copy of each item from the base branch and every open branch, with its derived status, its next "
        "step, and who holds it: the agent, the author, an Approver, a triager, or a decision maker; --branch shows only this branch's change",
        "understand:cmd_list",
    )
    list_args(s)
    flag(
        s,
        "--branch",
        "only this branch's change: the steps of the Specs it changes, read from the working tree (uncommitted work too), each Spec's "
        "Tasks, and the other branches that change the same code",
    )
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="also write the decision page (experimental): every step listed, with who decides, how, and the page or command for each, as "
        "one self-contained HTML page (default .aidd/views/decisions-<view>.html). With --waiting-on-me, every decision waiting "
        "on you. It never approves",
    )
    flag(
        s,
        "--upkeep",
        "the upkeep that is due instead of the open work: library standards past review, feature flags past cleanup, emergency "
        "backfills, flaky tests (with --events), waivers ending within 30 days, runbooks past their drill, and doctor warnings, "
        "each with the command or skill that takes it (schemas/upkeep.schema.json)",
    )
    s.add_argument("--events", action="append", metavar="PATH", help="with --upkeep: gate events (JSON lines) that name flaky tests (repeatable)")

    s = cmd("log", "one Spec's history from git: status transitions with time in state, approvals, and Assisted-by trailers", "understand:cmd_log")
    s.add_argument("spec", help="the Spec, such as specs/SPEC-1.md or SPEC-1")
    s.add_argument(
        "--record",
        action="append",
        metavar="PATH",
        help="a gate record from `aidd gate --record` (repeatable; default .aidd/evidence/record.json when it exists)",
    )
    flag(s, "--json", "print the log as JSON")

    s = cmd(
        "worktrees",
        "every worktree of this repository: its work item, its state (active, new, merged, stale, uncommitted work, missing), "
        "its loop, and its AIDD_WORKTREE name; clean removes the missing and the merged ones, after a person's yes",
        "worktrees:cmd_worktrees",
    )
    s.add_argument("action", nargs="?", choices=["clean"], help="clean: remove the worktrees that are missing, or merged with nothing uncommitted")
    flag(s, "--json", "print the worktrees and the ones clean would remove as JSON")
    flag(s, "--dry-run", "clean: say what it would remove, and remove nothing")

    s = cmd(
        "config",
        "the settings this repository's config sets, each with its value and where that value comes from (this config, a parent, "
        "or the profile), then the few you may want to set; --all lists every setting .aidd/config.yaml may hold, and what it does; "
        "name one for it in full",
        "understand:cmd_config",
    )
    s.add_argument("setting", nargs="?", help="one setting, such as mode or gates.approvals; a group, such as gates, for all of it")
    flag(s, "--all", "every setting, with the value here, where it comes from (the default too), and what it does")

    s = cmd(
        "help",
        "the everyday commands, the same as `aidd --help`; with --all, every command by group; with a command, its arguments and flags, "
        "the same as `aidd <command> --help`",
        "understand:cmd_help",
    )
    s.add_argument("topic", nargs="*", metavar="COMMAND", help="a command, such as gate, or a command and its action, such as record verify")
    flag(s, "--all", "every command, by group, with the commands for maintainers and harnesses")
    s = cmd("owners", "who decides and who does the work: the Approvers, the specialist Approver pools, and every agent role", "understand:cmd_owners")
    flag(s, "--json", "print the owners as JSON")
    s.add_argument(
        "--changed",
        nargs="+",
        metavar="PATH",
        help="the paths the change touches: each role lists only the standards whose when_changed matches them",
    )

    s = cmd("metrics", "summarize gate events", "understand:cmd_metrics")
    s.add_argument("--tenant", metavar="TENANT", help="only the events of this tenant (the `tenant` their config names)")
    s.add_argument("events", nargs="*", help="JSON-lines files written with --events, from any number of repositories")
    s.add_argument(
        "--guard",
        nargs="?",
        const=arguments.GUARD_LOG_DEFAULT,
        metavar="PATH",
        help="count the guard's denials by reason and by role, from the log `aidd hook pre-tool` keeps (default: guard.jsonl in the git directory, which every worktree shares)",
    )
    s.add_argument("--since", metavar="DATE", help="only events at or after this ISO date or time, such as the last retrospective")
    s.add_argument(
        "--by",
        choices=list(tracking.METRIC_GROUPS),
        help="one summary per repo, org (the organization or company that owns the repository), team (the Spec's owner_team), profile, route, "
        "or author. `aidd metrics --by author` serves agent autonomy and a person's self-review, never ranking or appraising people",
    )
    s.add_argument(
        "--target-wait", type=float, metavar="MINUTES", help="name the approvals and checks whose median wait is above this many minutes (a day is 1440)"
    )
    flag(s, "--autonomy", "gradual release: per agent and change type, how its changes fared and the stage of autonomy the evidence supports")
    flag(s, "--dora", "the five DORA software delivery metrics against the `targets` in the config; exit 1 when one misses")
    flag(
        s,
        "--flaky",
        "per test: on how many heads it ran, and how often it passed on a re-run after failing on the same head; "
        "a rate over 5%% is over the limit (display only, exit 0)",
    )
    s.add_argument(
        "--specs",
        metavar="DIR",
        help="add the change fail rate and recovery days from the Specs' outcome (DORA stability); with --roles, where the Specs are (default: specs_dir)",
    )
    s.add_argument(
        "--cost",
        metavar="FILE",
        help="join a host-exported cost log (JSON lines: ts, amount, currency, agent, spec, branch, sha) to the changes; display only, never a gate",
    )
    flag(
        s,
        "--suggest-standard-changes",
        "with --autonomy: print a `standard_changes` entry for each class that meets the thresholds, for a person to merge",
    )
    flag(
        s,
        "--autopilot",
        "the autopilot runs' measures from the run events in the git directory (and the event files given): "
        "human decisions per change, decision wait, agent steps per decision, rework, cost per change, and guard denials during runs",
    )
    flag(
        s,
        "--roles",
        "one row per aidd-team role, from the gate events, the Specs' Tasks, the guard's log, the trunk's reverts, and --eval-record; "
        f"never the journal or handoff notes, and under {tracking.ROLE_MIN_CHANGES} changes a row is too few to judge (display only, exit 0)",
    )
    s.add_argument("--eval-record", metavar="FILE", help="with --roles: an `aidd eval roles --record` file, for each role's latest fresh pass@1 and lift")
    s.add_argument("--render", metavar="NAME", help="print the summary with an installed aidd.renderers extension instead")
    flag(s, "--json", "print JSON")

    s = cmd(
        "digest",
        "a status rollup since a date or a git ref, from what aidd already knows: what landed, what is in progress, who it waits "
        "on, what is blocked, the risks, the overdue items, feedback themes, and the gate metrics; --client for the client's view: "
        "a RAG status with its rules, milestones, what landed in plain words, what we need from them, the deprecation calendar, and next steps",
        "understand:cmd_digest",
    )
    s.add_argument("--since", metavar="DATE_OR_REF", help="an ISO date (2026-09-01) or a git ref (default: the last tag HEAD holds, else the last 7 days)")
    flag(s, "--client", "the client's view; it never holds internal cost data unless --include-cost")
    s.add_argument("--events", nargs="+", metavar="PATH", help="gate events (`aidd gate --events`) for the metrics (default aidd-events.jsonl when it exists)")
    s.add_argument("--cost", metavar="FILE", help="join a cost log to the changes: shown in the team view, and in the client view only with --include-cost")
    flag(s, "--include-cost", "with --client: show the cost to the client too")
    s.add_argument("--blocked-days", type=int, default=5, metavar="N", help="the client view is red when an item has been blocked for more than N days")
    s.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="with --client: also write the client status as one self-contained HTML page (default .aidd/views/digest-client-<date>.html)",
    )
    flag(s, "--json", "print JSON (schemas/digest.schema.json)")
