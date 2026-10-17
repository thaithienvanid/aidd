"""The arguments and flags of the commands for maintainers and harnesses: eval, mcp, hook, and gen-docs."""

from __future__ import annotations


def register(cmd, flag) -> None:
    """Add the maintain commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd(
        "eval",
        "run the example suite, an agent routing eval, the role evals, the standards check, the pack and practice template check, "
        "or your own agent tasks; report recorded runs",
        "maintain:cmd_eval",
    )
    s.add_argument("suite", choices=["examples", "routing", "roles", "standards", "packs", "tasks", "report"])
    s.add_argument("paths", nargs="*", metavar="PATH", help="report: JSON-lines files written with --record, printed as one markdown table")
    s.add_argument(
        "--root", help="examples, routing, roles: the aidd source checkout (default: this installation's source, if any); tasks: your repository (default: .)"
    )
    s.add_argument("--scenarios", help="directory of scenario .yaml files")
    s.add_argument("--cmd", help='agent command that reads a prompt on stdin, such as "claude -p"')
    flag(s, "--no-embed", "routing: rely on the harness loading the skill instead of embedding routes.md")
    s.add_argument(
        "--min-accuracy", type=float, default=0.9, help="fail below this mean pass@1: the share of correct routes, passed role scenarios, or passed tasks"
    )
    s.add_argument("--repeat", type=int, default=1, metavar="K", help="routing, roles, tasks: run each scenario K times; report pass@1 and pass^K")
    flag(
        s,
        "--control",
        "routing, roles: also run every scenario without the aidd material (the skill reference, the role playbook) and report the lift; never gates",
    )
    s.add_argument("--record", metavar="PATH", help="routing, roles, tasks: append this run to a JSON-lines file (read it with `aidd eval report`)")
    s.add_argument("--model-label", metavar="TEXT", help="the model name to record with the run, as you name it (aidd never infers it)")
    s.add_argument(
        "--max-days",
        type=int,
        help="standards: fail when an entry was last checked more than this many days ago, for every entry "
        "(default: each entry's cadence: its review_every_days, else 90 days emerging and 365 established)",
    )
    flag(
        s,
        "--online",
        "standards: fetch each evidence URL again and report whether its quote is still there (ok, moved, missing, unreachable); never edits the registry",
    )
    flag(s, "--strict", "standards --online: exit 1 when an entry is moved or missing (never for unreachable)")
    s.add_argument("--due", type=int, metavar="DAYS", help="standards: list each entry that comes due for review within DAYS days, soonest first")
    flag(
        s,
        "--unreviewed",
        "standards: list each registry entry no person has reviewed yet, the laws and regulations first, with how a person records a review",
    )
    flag(
        s,
        "--json",
        "standards --online: print the report as JSON (schemas/knowledge.schema.json); "
        "packs: print each pack's and practice skill's estimated size, and the problems, as JSON",
    )
    s.add_argument("--timeout", type=float, default=15.0, metavar="SECONDS", help="standards --online: each request's timeout")
    s.add_argument("--max-seconds", type=float, default=600.0, metavar="SECONDS", help="standards --online: the whole run's time cap")
    s.add_argument("--max-bytes", type=int, default=3_000_000, metavar="N", help="standards --online: the most bytes read from one page")
    s.add_argument("--concurrency", type=int, default=2, choices=[1, 2], help="standards --online: requests in flight (one per host)")
    s.add_argument(
        "--materialize",
        metavar="DIR",
        help="examples: write every case and mutation as a resolved context plus its expectation, for another gate implementation to run",
    )

    cmd(
        "mcp",
        "serve aidd to agents as MCP tools over stdio (check_edit, validate, approval_line, approve_spec, approve_merge, ship, and approve_all, which ask the person in the client's own dialog, "
        "describe, and gate, which also forecasts the route of planned paths)",
        "maintain:cmd_mcp",
    )
    s = cmd(
        "hook",
        "agent harness hooks; pre-tool (pre-edit, its earlier name, still works) reads a Claude Code PreToolUse event and denies edits outside "
        "the active Spec; session-start adds "
        "this change's route and next steps to a new session; prompt-submit adds the next step to each prompt (UserPromptSubmit); stop reminds the agent "
        "to run `aidd test` (Stop and SubagentStop); pre-compact saves the state of the work in the git directory",
        "maintain:cmd_hook",
    )
    s.add_argument("event", choices=["pre-tool", "pre-edit", "session-start", "prompt-submit", "stop", "pre-compact"])

    s = cmd("gen-docs", "maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills", "maintain:cmd_gen_docs")
    flag(s, "--check", "fail when any generated block is stale")
