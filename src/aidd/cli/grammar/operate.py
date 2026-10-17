"""The Operate commands' arguments and flags: ship, goal, integrate, sync, observe, and release-notes."""

from __future__ import annotations

from aidd import config
from aidd.cli import arguments


def register(cmd, flag) -> None:
    """Add the operate commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd("ship", "local-first: merge the current branch into the base branch once the gate passes, keeping its history or squashing it", "operate:cmd_ship")
    s.add_argument("--base", help="the base branch; default: the repository's default branch")
    flag(s, "--squash", "one commit on the base branch, keeping every Assisted-by trailer")
    s.add_argument("--message", help="the merge or squash commit message; default: the Spec's title, or the newest commit's subject")
    s.add_argument(
        "--body-file",
        help="the change description holding the Change Request block (default: the newest branch commit that holds one, else the Spec in the diff)",
    )
    s.add_argument("--out", default=config.EVIDENCE_DIR, help="where the tests ship runs on the head write their evidence and logs")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)
    flag(s, "--skip-cooloff", "skip the route's cool-off, on record: locally it starts at a committer date, so it is a reminder, not a control")
    flag(s, "--show", "print what would ship as JSON (the branch, its head, what changed, what the gate still waits on, and problems); ship nothing")
    s.add_argument(
        "--confirmed",
        metavar="HEAD",
        help="ship what a person confirmed in a dialog (aidd-mods in Claude Code, or an MCP client) for exactly this head commit, without "
        "the terminal question; the tests still run first, and a Merge approval it records says where. The guard denies it to agents",
    )
    s.add_argument("--confirmed-in", default="claude-code", metavar="WHERE", help="with --confirmed: claude-code (default), or mcp:<client>")

    s = cmd(
        "integrate",
        "the team's step: merge this Spec's branch into its goal branch (the Spec's `base: goal/<name>`) as a merge commit, once its "
        "approval holds, its tests pass on the merged tree, and the gate against the goal waits only for the release decisions; "
        "no person is asked, as the goal's release to the default branch proves each Spec again",
        "goals:cmd_integrate",
    )
    s.add_argument("--goal", metavar="BRANCH", help="the goal branch, for a fast-lane fix with no Spec that was cut from it")
    s.add_argument("--undo", metavar="SPEC_ID", help="take an integrated Spec out of its goal again: one commit that reverts its integration")
    s.add_argument("--out", default=config.EVIDENCE_DIR, help="where the tests on the merged tree write their evidence and logs")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)

    s = cmd(
        "goal",
        "open the goal branch, goal/<EPIC>, of a small goal that ships batched, cut from the default branch once the plan "
        "holding the Epic is there; or list each goal and the branches with unmerged work, from git alone",
        "goals:cmd_goal",
    )
    s.add_argument(
        "action",
        choices=["open", "list"],
        help="open: create the goal branch (and push it to origin when there is one); list: each goal, and the branches with unmerged work",
    )
    s.add_argument("epic", nargs="?", metavar="EPIC_ID", help="open: the Epic, such as EPIC-3, with `ships: batched`")
    flag(s, "--json", "list: print JSON (the `goals` and `flow` of `aidd list --json`)")

    s = cmd(
        "sync",
        "merge newer work in, never rebasing: the goal branch into a Spec's branch cut from it, and the default branch into a "
        "goal branch or any other branch, daily; a conflict merges nothing and lists the files",
        "goals:cmd_sync",
    )
    s.add_argument("--from", dest="source", metavar="BRANCH", help="the branch to merge in (default: the goal, or on a goal branch the default branch)")

    s = cmd(
        "release-notes",
        "release notes from the Specs shipped since a tag or a date: each one's title, intent, and flags, grouped as Added, Changed, "
        "Deprecated, Removed, Fixed, and Security (Keep a Changelog), for users or for developers",
        "operate:cmd_release_notes",
    )
    s.add_argument("--since", required=True, metavar="TAG_OR_DATE", help="the last release's tag (or any git ref), or an ISO date")
    s.add_argument(
        "--audience",
        choices=["users", "developers"],
        default="users",
        help="users: the changes they notice (feat, fix, perf, security); developers: every change",
    )
    flag(s, "--json", "print JSON (schemas/release-notes.schema.json)")

    s = cmd(
        "observe",
        "after release: run a Spec's observe command once, or poll it for the observe window (--window); exit 0 healthy (the window "
        "ended with the rollback trigger never firing), 1 unhealthy (the trigger fired), 2 error. It never rolls back. With --band "
        "METRIC, judge a metric series against its control band instead (no model); exit 1 when an agent may diagnose or suggest a change",
        "operate:cmd_observe",
    )
    s.add_argument("target", metavar="SPEC|SERIES", help="the Spec file, such as specs/SPEC-42.md; with --band, the metric series file")
    s.add_argument(
        "--window",
        nargs="?",
        const="spec",
        metavar="DURATION",
        help="poll until the Spec's observe.window ends, or this long (such as 90s, 30m, 24h); stop as soon as the rollback trigger fires",
    )
    s.add_argument("--every", default="5m", metavar="DURATION", help="--window: how often to run the observe command, such as 30s or 5m")
    s.add_argument("--consecutive", type=int, default=1, metavar="N", help="--window: the rollback trigger fires after this many unhealthy checks in a row")
    s.add_argument(
        "--write",
        nargs="?",
        const="auto",
        metavar="SPEC_ID",
        help="record outcome.observe_result in the Spec (a bookkeeping field Spec approval ignores); with --band, on a breach, write a "
        "draft Spec with the evidence (default id OBS-<metric>-<date>)",
    )
    s.add_argument("--timeout", type=int, default=600, help="seconds before the command counts as failed")
    s.add_argument("--pass-env", action="append", metavar="NAME", help=arguments.PASS_ENV_HELP)
    s.add_argument(
        "--band",
        metavar="METRIC",
        help="judge SERIES (values, oldest first: JSON lines with a value field, CSV ending in the value, or one number per line) "
        "against this metric's control band; a matching `observe.bands` entry sets the thresholds",
    )
    s.add_argument("--baseline", type=int, metavar="N", help="--band: how many recent values make the baseline (default 30)")
    s.add_argument("--diagnose-sigma", type=float, help="--band: standard deviations at which an agent may diagnose read-only (default 2)")
    s.add_argument("--propose-sigma", type=float, help="--band: standard deviations at which an agent may suggest a change (default 3)")
    flag(s, "--json", "--band: print the reading as JSON")
