"""The command line's reference: every command with its arguments and flags, and which command to use when, read
from the parser `aidd` runs (through `CliFacts`, since the command line sits above this package).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from aidd.docsgen import blocks


@dataclass(frozen=True)
class CliFacts:
    """What the generated blocks read from the command line and the MCP server, which sit above this package: the
    parser `aidd` runs, its help groups, and the MCP revisions and tools. `aidd gen-docs` builds it (`cli.cli_facts()`) and passes
    it in, so this package never imports the CLI."""

    parser: argparse.ArgumentParser
    command_groups: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    hidden_group: str
    everyday: tuple[tuple[str, tuple[str, ...], str], ...]
    when: dict[str, str]
    mcp_supported: tuple[str, ...]
    mcp_protocol: str
    mcp_tools: tuple[str, ...] = ()  # the tools `aidd mcp` lists, by name, in its order
    readme_rows: tuple[tuple[str, str, str], ...] = ()  # the README's table: in the session, at the terminal, what it does
    # Each command and what exit codes 0, 1, 2, and 3 mean for it ("" where it never exits so): arguments.EXIT_CODES.
    exit_codes: tuple[tuple[str, tuple[str, str, str, str]], ...] = ()


def _subcommands(cli: CliFacts) -> dict:
    """The CLI's subcommand parsers, by name, from the same builder `aidd` runs, in the order of its grouped help: a
    command group's actions by their full name (`record verify`)."""

    def actions(parser) -> dict:
        return dict(next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices)

    top = actions(cli.parser)
    out: dict = {}
    for _, rows in cli.command_groups:
        for name, _ in rows:
            nested = [a for a in top[name]._actions if isinstance(a, argparse._SubParsersAction)]
            out |= {f"{name} {sub}": p for sub, p in actions(top[name]).items()} if nested else {name: top[name]}
    return out


def _arg_text(a) -> str:
    """One argument as a reader types it: `[path]`, `--profile solo|team`, `--test COMMAND`, `--json`."""
    if not a.option_strings:
        name = "|".join(str(c) for c in a.choices) if a.choices else (a.metavar or a.dest)
        text = {"?": f"`[{name}]`", "*": f"`[{name} ...]`", "+": f"`{name} ...`"}.get(a.nargs, f"`{name}`")
        return text.replace("|", "\\|")
    flag = max(a.option_strings, key=len)
    if a.nargs == 0:
        text = f"`{flag}`"
    elif a.choices and not a.metavar:
        text = f"`{flag} {'|'.join(str(c) for c in a.choices)}`".replace("|", "\\|")
    else:
        value = a.metavar or a.dest.upper()
        text = f"`{flag} {value}{' ...' if a.nargs in ('+', '*') else ''}`"
    if a.nargs == "?":  # the flag alone is valid: its value is optional
        text = text.replace(" ", " [", 1)[:-1] + "]`"
    notes = []
    if a.required:
        notes.append("required")
    if a.nargs != 0 and a.default not in (None, "", [], False):
        notes.append(f"default `{a.default}`")
    if type(a).__name__ == "_AppendAction":
        notes.append("repeatable")
    return text + (f" ({', '.join(notes)})" if notes else "")


def cli_table(cli: CliFacts) -> str:
    """Every command, its positional arguments, and every flag, from the argparse parser itself."""
    rows = []
    for name, sub in _subcommands(cli).items():
        # A flag with help=SUPPRESS is in no table.
        args = [a for a in sub._actions if a.dest != "help" and a.help != argparse.SUPPRESS]
        positional = "".join(" " + _arg_text(a) for a in args if not a.option_strings)
        flags = ", ".join(_arg_text(a) for a in args if a.option_strings) or "none"
        rows.append([f"`{name}`{positional}", (sub.description or "").replace("|", "\\|"), flags])
    return blocks.markdown_table("Command | What it does | Flags", rows)


def when_table(cli: CliFacts) -> str:
    """Which command when, from the CLI's everyday commands, its `WHEN` notes, and its command groups: the everyday
    commands in the order of the loop, then every other command by its group, then the maintainer and harness commands
    `aidd --help` hides."""
    rows: list[list[str]] = []
    for i, (form, _, when) in enumerate(cli.everyday):
        rows.append(["Every day" if i == 0 else "", form, when])
    for title in ("Now and then", cli.hidden_group):
        names = [n for t, group in cli.command_groups for n, _ in group if (t == cli.hidden_group) == (title == cli.hidden_group) and n in cli.when]
        for i, name in enumerate(names):
            rows.append([title if i == 0 else "", f"`aidd {name}{' <kind>' if name == 'new' else ''}`", cli.when[name]])
    return blocks.markdown_table("Use | Command | When", rows)


def everyday_table(cli: CliFacts) -> str:
    """The README's one everyday table: each job as a person types it in the agent's session, the same at the
    terminal, and what it does (`readme_rows`). An agent runs the rest."""
    return blocks.markdown_table("In the session | At your terminal | What it does", [list(row) for row in cli.readme_rows])
