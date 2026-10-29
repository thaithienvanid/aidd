"""The autopilot commands' arguments and flags: autopilot, and `aidd context` (experimental)."""

from __future__ import annotations

AUTOPILOT = "autopilot: runs the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide"


def register(cmd, flag) -> None:
    """Add the autopilot commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd(
        "autopilot",
        AUTOPILOT + ". Its lease and one-line journal live in the git directory: one live lease per piece of work, stale after its timebox. "
        "At Spec approval it asks, unless a local approval exists, on GitLab, with no GitHub token, in a fork workflow, or with no "
        "project.repo (set it, or run `aidd init` again)",
        None,
    )
    auto = s.add_subparsers(dest="action", metavar="ACTION", required=True)
    session_help = "the session that holds the lease, the one `start` printed (required: a lone lease may be another session's)"
    a = cmd(
        "start",
        "start autopilot on a piece of work for a session; a live lease of another session refuses it, a stale one is replaced, and starting again "
        "after the run ended (a plan ready, a limit, nothing open) begins a new run",
        "autopilot:cmd_autopilot",
        into=auto,
        short="start autopilot on a piece of work",
    )
    a.add_argument("--work", default="all", metavar="WORK", help="a Spec, Epic, or Initiative id, a label, or all")
    a.add_argument("--session", metavar="ID", help="the harness session's id (default: a new one, printed)")
    a.add_argument("--timebox", metavar="DURATION", help="how long the run may last, such as 90m or 2h (default: `autopilot.timebox`, else 6h)")
    a = cmd(
        "next",
        "the one next action, decided by the engine from the open work, the step-to-flow map, the lease and journal, and the "
        "autopilot limits: run a team command, ask a person (with the decision page), or stop (with why); a stop for a person "
        "lists every decision that waits, how to take each, and the command that goes on",
        "autopilot:cmd_autopilot",
        into=auto,
        short="the one next action",
    )
    a.add_argument("--work", metavar="WORK", help="the run's work: a Spec, Epic, or Initiative id, a label, or all (default: the lease's)")
    a.add_argument("--session", metavar="ID", required=True, help=session_help)
    a.add_argument(
        "--ask",
        dest="goal",
        metavar="TEXT",
        help="what a person asked for, to plan (or propose, for client work) before the open work, unless the journal shows it planned",
    )
    a.add_argument(
        "--harness",
        choices=("claude-code", "codex", "opencode", "grok-build", "antigravity"),
        help="name each team command as this coding agent runs it, with the file that holds it (the autopilot flow passes its own)",
    )
    flag(a, "--json", "print the action as JSON (schemas/autopilot-next.schema.json)")
    a = cmd(
        "note",
        'record a step\'s result in the journal, as "<code> <result>", with the head it ran on; the result is ok, fail, waiting, or blocked. '
        "The code is the one `next` gave. Right after the timebox ends, or the run stops, it still records each step the run had in flight, once",
        "autopilot:cmd_autopilot",
        into=auto,
        short="note a step's result",
    )
    a.add_argument("text", metavar="NOTE", help='"<code> <result>", such as "spec.in_progress ok"; any words after them are kept as data')
    a.add_argument("--session", metavar="ID", required=True, help=session_help)
    a.add_argument("--spec", metavar="ID", help="the Spec the step was about (default: the lease's work)")
    a.add_argument(
        "--head",
        metavar="SHA",
        help="the commit the step ran on, or left: the action's `head` for Verify and Review, else the head of the worktree it ran in (default: HEAD here)",
    )
    a.add_argument("--tokens", type=int, metavar="N", help="the tokens the step used, zero or more (self-reported)")
    a.add_argument("--cost", type=float, metavar="AMOUNT", help="what the step cost, zero or more, with --currency (self-reported)")
    a.add_argument("--currency", metavar="CODE", help="the ISO 4217 currency of --cost, such as USD")
    a.add_argument(
        "--ask",
        dest="goal",
        metavar="TEXT",
        help="a plan step: the ask it planned, so starting again with the same ask goes on with its plan",
    )
    a = cmd(
        "status",
        "print every lease, whether its timebox ended, and the journal's last lines",
        "autopilot:cmd_autopilot",
        into=auto,
        short="the lease and journal",
    )
    a.add_argument("--session", metavar="ID", help="only this session's lease, journal lines, and notices")
    flag(a, "--json", "print them as JSON (schemas/autopilot-status.schema.json)")
    a = cmd("stop", "stop autopilot: remove the session's lease", "autopilot:cmd_autopilot", into=auto, short="stop autopilot")
    a.add_argument("--session", metavar="ID", required=True, help=session_help)

    s = cmd(
        "context",
        "experimental: the minimal context pack for a step of a Spec, as paths with a one-line reason and a token estimate each: the "
        "summary, the Task, the step's own reads (its tests, the Acceptance, the evidence, and the commands that show the rest), the linked docs, "
        "the exemplar Specs on the Specify step, the latest handoff note, the standards for its paths, and the role's playbook with --play. "
        "It never prints a file's contents, and names its head commit and Spec hash",
        "autopilot:cmd_context",
    )
    s.add_argument("spec", nargs="?", help="the Spec, such as specs/SPEC-1.md or SPEC-1 (not with --stop-playing)")
    s.add_argument("--role", metavar="ROLE", help="only this role's Tasks and standards, such as developer")
    s.add_argument(
        "--step", metavar="CODE", help="the step code the pack is for, such as spec.verify: it picks the step's reads (with --role, the role's own steps)"
    )
    flag(s, "--play", "with --role: the pack to play that role in your own session, starting with its playbook")
    s.add_argument(
        "--session",
        metavar="ID",
        help="with --play: this session's id, so the guard holds its edits to the role's area too; with --stop-playing: the session that stops. Where the harness names this shell's session (CLAUDE_CODE_SESSION_ID, AIDD_SESSION_ID), only that id",
    )
    flag(s, "--stop-playing", "with --session: the session plays no role from now on")
    flag(s, "--json", "print the pack as JSON (schemas/context-pack.schema.json)")
