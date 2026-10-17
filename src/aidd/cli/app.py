"""Run one `aidd` command: build the parser, run the command, and map an error to exit code 2."""

from __future__ import annotations

import sys

from aidd.cli import parser
from aidd.kernel import extensions, git, http


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    # A protected command (the gate, the test runner, approvals, ship, the hooks, the MCP server) never discovers
    # extensions: seal discovery before its parser is built, so no plugin module is imported in this process.
    command = extensions.command_of(argv)
    if command in extensions.PROTECTED:
        extensions.seal()
    args = parser.build_parser(plugins=command not in extensions.PROTECTED).parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, LookupError, git.GitError, http.HttpError, RuntimeError) as exc:
        print(f"aidd: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # a bug must never look like a gate decision (exit 1)
        print(f"aidd: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        # Once a day, after a command a person ran at a terminal: update the CLI (aidd.setup.self_updating). Never raises.
        from aidd import setup

        setup.auto_update(command)
