"""Run one `aidd` command: build the parser, run the command, and map an error to exit code 2."""

from __future__ import annotations

import os
import sys
import traceback

from aidd import guard
from aidd.cli import arguments, parser
from aidd.kernel import extensions, git, http


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    # A protected command (the gate, the test runner, approvals, land, publish, the hooks, the MCP server) never discovers
    # extensions: seal discovery before its parser is built, so no plugin module is imported in this process.
    command = extensions.command_of(argv)
    if command in extensions.PROTECTED:
        extensions.seal()
    args = parser.build_parser(plugins=command not in extensions.PROTECTED).parse_args(argv)
    try:
        # Land, approve, and publish compare what the always-on rules stand on with the person's last decision
        # (guard/outside_changes.py): an agent's run stops on a change, and a person's decision takes it in and says so.
        confirmed = arguments.confirmed_here(args)
        # Only aidd's MCP server, in this process, vouches for the person who answered its dialog; a place that counts
        # because the guard denies an agent's `--confirmed` never takes in a change that could stop that guard.
        answer = guard.Answer(getattr(args, "outside_hash", None), arguments.in_mcp_dialog()) if confirmed else None
        checked = guard.check_decision(command, args, confirmed=answer)
        if checked and checked.note and not confirmed:
            print(checked.note)  # at the person's own terminal, before the command asks them
        code = args.func(args)
        if checked and code == 0:
            # What the check read, with the command's own writes: a decision takes in what changed before it, and what
            # weakens the guard only when it showed it exactly; nothing that changed while the command ran.
            guard.record_checked(checked)
            if checked.note and confirmed and not arguments.in_prompt_hook():
                print(checked.note)  # the prompt hook says it in its own line
        return code
    except (ValueError, OSError, LookupError, git.GitError, http.HttpError, RuntimeError) as exc:
        _traceback_when_debugging()
        print(f"aidd: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # a bug must never look like a gate decision (exit 1)
        debugging = _traceback_when_debugging()
        print(f"aidd: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(crash_next_step(debugging), file=sys.stderr)
        return 2
    finally:
        # Once a day, after a command a person ran at a terminal: update the CLI (aidd.setup.self_updating). Never raises.
        from aidd import setup

        setup.auto_update(command)


def _traceback_when_debugging() -> bool:
    """With `AIDD_DEBUG=1`, print the traceback of the error being handled to stderr; whether it did."""
    if os.environ.get("AIDD_DEBUG") != "1":
        return False
    traceback.print_exc(file=sys.stderr)
    return True


def crash_next_step(debugging: bool) -> str:
    """What a person does after a crash: it is a bug in aidd, so they report it with what its maintainers need, and
    with no private detail, because the report is public."""
    from aidd import gate

    where = (
        f"report it at {gate.BUG_REPORT_URL} with the output of `aidd --version` and `aidd doctor --json`. The report is public, "
        "so first remove anything private from that output, such as emails, tokens, and paths with your name in them"
    )
    if debugging:
        return f"aidd: this is a bug in aidd: add the traceback above, and {where}"
    return f"aidd: this is a bug in aidd: run the command again with AIDD_DEBUG=1 for the traceback, and {where}"
