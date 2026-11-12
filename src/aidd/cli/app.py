"""Run one `aidd` command: build the parser, run the command, and map an error to exit code 2."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback

from aidd import config
from aidd.cli import arguments, parser
from aidd.kernel import findings, git, http

BUG_REPORT_URL = "https://github.com/thaithienvanid/aidd/issues/new?template=bug.yml"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    args = _parse(argv)
    stopped = False
    try:
        code = args.func(args)
        # A view that went on without a config that does not load shows what it can, then says it failed (`config_or_none_quiet`).
        return 1 if code == 0 and getattr(args, "config_unreadable", False) else code
    except (ValueError, OSError, LookupError, git.GitError, http.HttpError, RuntimeError) as exc:
        _traceback_when_debugging()
        # git's own "not a git repository" names no next step, so aidd says it in words, wherever a command met it.
        said = git.no_repository_problem(args.command) if git.is_no_repository(exc) else str(exc)
        print(f"aidd: {said}", file=sys.stderr)
        _print_error_object(args, error_finding(exc, said))
        return 2
    except KeyboardInterrupt:  # Ctrl-C: the person stopped it, so one line and the shell's code for SIGINT, no traceback
        stopped = True
        print("aidd: stopped", file=sys.stderr)
        return 130
    except Exception as exc:  # a bug is an error (exit 2), never a failed check
        debugging = _traceback_when_debugging()
        said = f"internal error: {type(exc).__name__}: {exc}"
        print(f"aidd: {said}", file=sys.stderr)
        print(crash_next_step(debugging), file=sys.stderr)
        _print_error_object(args, findings.finding("cli.internal_error", said))
        return 2
    finally:
        # Once a day, after a command a person ran at a terminal: say when a newer aidd is out (aidd.setup.self_updating).
        # Never after Ctrl-C: a person who stopped aidd wants it to stop, with no network call.
        if not stopped:
            from aidd import setup

            setup.auto_update(getattr(args, "command", None))


def _parse(argv: list[str]):
    """The parsed command line. A command line the parser refuses exits 2 with its words on stderr, as it does alone, and with
    `--json` among the arguments it also prints the error object on stdout."""
    seen = io.StringIO()
    try:
        with contextlib.redirect_stderr(seen):
            return parser.build_parser().parse_args(argv)
    except SystemExit as stop:
        sys.stderr.write(seen.getvalue())
        if stop.code == 2 and "--json" in argv[: argv.index("--") if "--" in argv else len(argv)]:
            said = seen.getvalue().strip().removeprefix("aidd: ") or "the command line is not one aidd can run"
            print(json.dumps(arguments.error_object(findings.finding("cli.bad_arguments", said)), indent=2))
        raise


def error_finding(exc: BaseException, said: str) -> dict:
    """The finding for an error that stopped a command, by what stopped it; `said` is the words a person reads."""
    if isinstance(exc, config.ConfigUnreadable):
        return config.config_unreadable_finding(exc)
    if isinstance(exc, arguments.NoRepositoryError) or git.is_no_repository(exc):
        return findings.finding("cli.no_repository", said)
    if isinstance(exc, git.GitError):
        return findings.finding("cli.git_failed", said)
    if isinstance(exc, http.HttpError):
        return findings.finding("cli.network_failed", said)
    if isinstance(exc, RuntimeError):
        return findings.finding("cli.failed", said)
    if isinstance(exc, OSError):
        return findings.finding("cli.file_unreadable", said)
    if isinstance(exc, LookupError):
        return findings.finding("cli.not_found", said)
    return findings.finding("cli.invalid", said)


def _print_error_object(args, finding: dict) -> None:
    """With `--json`, the error object on stdout, for a script that reads the command's output."""
    if getattr(args, "json", False):
        print(json.dumps(arguments.error_object(finding), indent=2))


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
