"""The actions a command line is, without the edits it makes by writing a file (`FILE_WRITES`)."""

from __future__ import annotations

from aidd.risk.commands import FILE_WRITES, command_level
from aidd.risk.rules import RuleSet


def actions_without_edits(rs: RuleSet, line: str, *, cwd: str | None = ".") -> list[dict]:
    """The actions a command line is, as `command_level` lists them, except the `code.edit` steps for the files it writes. Those steps
    need a git call to read each file, so a caller that counts other actions only, such as the deploy actions of a workflow's
    `run:` lines, does not ask for them."""
    token = FILE_WRITES.set(False)
    try:
        return command_level(rs, line, cwd=cwd)["actions"]
    finally:
        FILE_WRITES.reset(token)
