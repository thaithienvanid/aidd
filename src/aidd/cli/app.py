"""Run one `aidd` command: build the parser, run the command, and map an error to exit code 2."""

from __future__ import annotations

import os
import sys
import traceback

from aidd.cli import parser
from aidd.kernel import git, http

BUG_REPORT_URL = "https://github.com/thaithienvanid/aidd/issues/new?template=bug.yml"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.build_parser().parse_args(argv)
    stopped = False
    try:
        return args.func(args)
    except (ValueError, OSError, LookupError, git.GitError, http.HttpError, RuntimeError) as exc:
        _traceback_when_debugging()
        # git's own "not a git repository" names no next step, so aidd says it in words, wherever a command met it.
        print(f"aidd: {git.no_repository_problem(args.command) if git.is_no_repository(exc) else exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # Ctrl-C: the person stopped it, so one line and the shell's code for SIGINT, no traceback
        stopped = True
        print("aidd: stopped", file=sys.stderr)
        return 130
    except Exception as exc:  # a bug is an error (exit 2), never a failed check
        debugging = _traceback_when_debugging()
        print(f"aidd: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(crash_next_step(debugging), file=sys.stderr)
        return 2
    finally:
        # Once a day, after a command a person ran at a terminal: say when a newer aidd is out (aidd.setup.self_updating).
        # Never after Ctrl-C: a person who stopped aidd wants it to stop, with no network call.
        if not stopped:
            from aidd import setup

            setup.auto_update(getattr(args, "command", None))


def _traceback_when_debugging() -> bool:
    """With `AIDD_DEBUG=1`, print the traceback of the error being handled to stderr; whether it did."""
    if os.environ.get("AIDD_DEBUG") != "1":
        return False
    traceback.print_exc(file=sys.stderr)
    return True


def crash_next_step(debugging: bool) -> str:
    """What a person does after a crash: it is a bug in aidd, so they report it with what its maintainers need, and
    with no private detail, because the report is public."""
    where = (
        f"report it at {BUG_REPORT_URL} with the output of `aidd --version` and `aidd doctor --json`. The report is public, "
        "so first remove anything private from that output, such as emails, tokens, and paths with your name in them"
    )
    if debugging:
        return f"aidd: this is a bug in aidd: add the traceback above, and {where}"
    return f"aidd: this is a bug in aidd: run the command again with AIDD_DEBUG=1 for the traceback, and {where}"
