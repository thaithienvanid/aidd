"""Extension points: commands, exporters, renderers, and domain packs from installed Python packages.

A package extends aidd by declaring entry points (stdlib `importlib.metadata`, no dependency):

- `aidd.commands`: `register(subparsers)` adds one subcommand with `subparsers.add_parser(...)` and
  `set_defaults(func=run)`, where `run(args) -> int` is the exit code. It cannot replace a built-in command.
- `aidd.exporters`: `export(kind, items) -> str | bytes`, used by `aidd record export ... --format <name>`.
- `aidd.renderers`: `render(summary) -> str`, used by `aidd metrics ... --render <name>`.
- `aidd.packs`: `pack() -> str | Path`, the directory of a domain-pack skill (a SKILL.md), for tooling that lists packs.

Trust boundary. Extension code is ordinary Python in the aidd process, so it is kept out of every command that decides,
proves, or changes what the gate trusts: the commands in PROTECTED never discover extensions. `cli.main` seals discovery
before it builds their parser, and once sealed, discovery in that process is refused for good, so no plugin module is
imported while the gate, the test runner, the approval and ship paths, the hooks, or the MCP server run. Extensions reach
the reporting commands only, and nothing they return is evidence.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import metadata
from typing import Any

GROUPS = ("aidd.commands", "aidd.exporters", "aidd.renderers", "aidd.packs")

# The commands that never discover extensions: they decide (gate), prove (test, hash, validate, record verify), record or
# act on an approval (approve, ship, describe), run inside an agent's harness (hook, mcp), list the work
# (list), or write the files that wire the gate, the hooks, and the CI (init, upgrade, uninstall). A command group's
# action counts as its own command (`command_of`): `record verify` is protected, while `record export` may use an
# installed exporter.
PROTECTED = frozenset(
    {"gate", "test", "validate", "hash", "approve", "ship", "hook", "mcp", "describe", "list", "record verify", "init", "upgrade", "uninstall"}
)
# Commands whose first positional word is an action (`aidd record verify`).
COMMAND_GROUPS = frozenset({"record"})

_sealed = False


class Sealed(RuntimeError):
    """Extension discovery was refused: a protected command runs in this process."""


def seal() -> None:
    """Refuse extension discovery for the rest of this process. One way: nothing unseals it."""
    global _sealed
    _sealed = True


def sealed() -> bool:
    return _sealed


def command_of(argv: list[str]) -> str | None:
    """The subcommand `argv` names: its first word that is not an option, with the next such word for a command group
    (`record verify`). aidd's top-level options take no value, and neither do a group's before its action."""
    words = [a for a in argv if not a.startswith("-")]
    if not words:
        return None
    return f"{words[0]} {words[1]}" if words[0] in COMMAND_GROUPS and len(words) > 1 else words[0]


def entry_points(group: str) -> list[metadata.EntryPoint]:
    """The installed entry points of `group`, sorted by name then value, so discovery is deterministic."""
    if group not in GROUPS:
        raise ValueError(f"unknown extension group {group!r}; the groups are {', '.join(GROUPS)}")
    if _sealed:
        raise Sealed(f"extension discovery is off in this process: a protected command ({', '.join(sorted(PROTECTED))}) runs here")
    return sorted(metadata.entry_points(group=group), key=lambda ep: (ep.name, ep.value))


def _warn(message: str) -> None:
    print(f"aidd: extension: {message}", file=sys.stderr)


def load_extensions(group: str) -> dict[str, Callable[..., Any]]:
    """Each entry point of `group`, loaded, by name. The first of two with one name wins; one that fails to load is
    skipped with a warning, so a broken package never breaks the command it did not ask to extend."""
    out: dict[str, Callable[..., Any]] = {}
    for ep in entry_points(group):
        if ep.name in out:
            _warn(f"{group} {ep.name!r} from {ep.value} is shadowed by an earlier one")
            continue
        try:
            out[ep.name] = ep.load()
        except Exception as exc:  # a plugin's import error is its own, never the command's
            _warn(f"{group} {ep.name!r} did not load: {type(exc).__name__}: {exc}")
    return out


def installed(group: str) -> dict[str, Callable[..., Any]]:
    """`load(group)`, or nothing once discovery is sealed: for a reporting command that may run in a sealed process
    (in-process callers, tests), where no extension is the right answer and never an error."""
    return {} if _sealed else load_extensions(group)


def register_commands(subparsers, builtin: set[str]) -> list[str]:
    """Let each `aidd.commands` entry point add its subcommand; return the names added. An entry point named like a
    built-in or protected command is skipped, and argparse itself refuses a second parser with a built-in's name."""
    added: list[str] = []
    for name, register in load_extensions("aidd.commands").items():
        if name in builtin or name in PROTECTED:
            _warn(f"aidd.commands {name!r} is a built-in command and is ignored")
            continue
        before = set(subparsers.choices)
        try:
            register(subparsers)
        except Exception as exc:
            _warn(f"aidd.commands {name!r} did not register: {type(exc).__name__}: {exc}")
            continue
        added += sorted(set(subparsers.choices) - before)
    return added


def packs() -> dict[str, str]:
    """The domain-pack directories installed packages offer under `aidd.packs`, by name: each must hold a SKILL.md."""
    from pathlib import Path

    out: dict[str, str] = {}
    for name, pack in load_extensions("aidd.packs").items():
        try:
            path = Path(pack())
        except Exception as exc:
            _warn(f"aidd.packs {name!r} failed: {type(exc).__name__}: {exc}")
            continue
        if (path / "SKILL.md").is_file():
            out[name] = str(path)
        else:
            _warn(f"aidd.packs {name!r} names {path}, which holds no SKILL.md")
    return out
