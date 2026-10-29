"""The held commands: a command that matches a `guard.held_commands` entry waits for a person."""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Mapping

from aidd import config
from aidd.guard import shell_parser


def _gate_matches(patterns: list[str], text: str) -> bool:
    """Every pattern matches `text`, ignoring case: a pattern with `*`, `?`, or `[` is a glob over the whole
    simple command, any other pattern a substring of it. A glob that ends in ` *` also matches a command that ends
    just before it: `make* deploy *` matches `make deploy` and `make deploy -j4`, never `make deployment`."""
    text = text.lower()

    def one(p: str) -> bool:
        if not any(c in p for c in "*?["):
            return p in text
        return fnmatch.fnmatchcase(text, p) or (p.endswith(" *") and fnmatch.fnmatchcase(text + " ", p))

    return bool(patterns) and all(one(p.lower()) for p in patterns)


# Programs that run the script named by their first word that is not a flag, and package runners that run the program
# named the same way (`npx --yes wrangler@3 deploy` runs wrangler).
_INTERPRETERS = (
    shell_parser.SHELLS | shell_parser.POWERSHELLS | {"source", ".", "py", "node", "ts-node", "tsx", "bun", "deno", "ruby", "perl"}
)  # and python3.12
_INLINE_FLAGS = {"-c", "-e", "-m", "--eval", "-command", "-encodedcommand", "-p", "--print"}
_RUNNERS = {"npx": (), "bunx": (), "pnpx": (), "pnpm": ("exec", "dlx"), "yarn": ("exec", "dlx"), "npm": ("exec",)}
# `_as_run` reads at most this much of a simple command; the match on the command as written reads all of it.
AS_RUN_MAX = 64 * 1024


class CommandTooLong(ValueError):
    """The program a command runs lies past AS_RUN_MAX, so the held-command check cannot see it."""


def _as_run(argv: list[str], programs: frozenset[str] = frozenset()) -> str:
    """The simple command as the program it runs: after environment assignments, wrappers such as `sudo`, and package
    runners such as `npx`, with the program's path cut to its name, a script run by an interpreter taken as the script,
    and `NAME=value` words left out. `AWS_PROFILE=prod ./bin/terraform apply` is `terraform apply`,
    `bash -x scripts/deploy.sh` is `deploy.sh`, and `make deploy ENV=production` is `make deploy`."""
    capped, budget = [], AS_RUN_MAX
    for word in argv:
        budget -= len(word) + 1
        if budget < 0:
            break
        capped.append(word)
    cut = len(capped) < len(argv)
    too_long = CommandTooLong(f"its program lies past the first {AS_RUN_MAX // 1024} KiB")
    words = shell_parser.program_argv(capped)
    lead = next((k for k, w in enumerate(capped) if not shell_parser.assignment(w)), len(capped))
    if programs and lead < len(capped) and shell_parser.program_name(capped[lead]) in shell_parser.WRAPPERS | {"env"}:
        # After a wrapper, the first word that names a held program is the program, whatever options came before it.
        words = next((capped[k:] for k in range(lead + 1, len(capped)) if shell_parser.program_name(capped[k]) in programs), words)
    for _ in range(3):
        if not words:
            if cut:
                raise too_long
            return ""
        name, rest = shell_parser.program_name(words[0]), words[1:]
        interpreter = name in _INTERPRETERS or re.fullmatch(r"python[0-9.]*", name) is not None
        if name in shell_parser.SHELLS:
            inline, at = shell_parser.shell_operand(name, rest)
            if at is None and cut:
                raise too_long
            if inline or at is None:
                break  # an inline script is its own simple command, which the splitter reads
            words = rest[at:]
            continue
        if name in _RUNNERS and (not _RUNNERS[name] or (bool(rest) and rest[0] in _RUNNERS[name])):
            rest = rest[1:] if _RUNNERS[name] else rest
        elif interpreter and not any(a.lower() in _INLINE_FLAGS for a in rest):
            rest = rest[1:] if name in ("bun", "deno") and rest[:1] == ["run"] else rest
        else:
            break
        rest = [a for a in rest if a != "--"]
        rest = rest[next((i for i, a in enumerate(rest) if not a.startswith("-")), len(rest)) :]
        if not rest and cut:
            raise too_long
        if not rest or (interpreter and not re.search(r"[./\\]", rest[0])):
            break
        words = [re.sub(r"(?<=.)@[^/]*$", "", rest[0]), *rest[1:]]
    return " ".join([shell_parser.program_name(words[0]), *(w for w in words[1:] if not shell_parser.assignment(w))])


def _held_programs(gates: list[dict]) -> frozenset[str]:
    """The programs the entries name: the first word of each `match` pattern, without a trailing `*`, such as
    `terraform` from `terraform* apply *` and `deploy.sh` from `deploy.sh *`. A word that is an option or still a glob
    names no program."""
    out = set()
    for gate in gates:
        for pattern in gate.get("match", []):
            first = (pattern.split() or [""])[0].lower().rstrip("*")
            if first and not first.startswith("-") and not any(c in first for c in "*?["):
                out.add(first)
    return frozenset(out)


def held_command(cfg: config.Config, command: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why `command` waits for a person, or None: it matches a `guard.held_commands` entry and the entry's
    `requires` variable is unset or empty in the environment the session started with. The variable must come
    from there, set by the person who approves: a command that names it proves nothing, so it never counts.
    An entry matches each simple command as written and as the program it runs (`_as_run`), unless one of its
    `unless` patterns matches that same text."""
    return held_by(cfg.get("guard", "held_commands", default=[]) or [], command, environ)


def held_by(gates: list[dict], command: str, environ: Mapping[str, str] | None = None) -> str | None:
    """Why `command` waits for a person under the held-command entries `gates`, or None (see held_command)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    simple = shell_parser.simple_commands(command)
    programs = _held_programs(gates)
    # Every reading only adds a match: as written, as run with the held-program scan, and as run without it (so an
    # option value named like a held program, as in `env -C infra/terraform make deploy`, cannot hide the real one).
    readings = (lambda argv: " ".join(argv), lambda argv: _as_run(argv, programs=programs), _as_run)
    texts = [t for sc in simple for t in dict.fromkeys(read(sc.argv) for read in readings) if t] or [command]
    for gate in gates:
        unless = list(gate.get("unless", []))
        if not any(_gate_matches(list(gate.get("match", [])), t) and not any(_gate_matches([u], t) for u in unless) for t in texts):
            continue
        name, env_label, var = gate.get("name", "held command"), gate.get("environment"), gate.get("requires")
        what = f"`{name}` is a held command" + (f" for {env_label}" if env_label else "")
        note = f" {gate['message']}" if gate.get("message") else ""
        if not var:
            return f"{what}: agents never run it.{note} Ask a person to run it outside the agent session."
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(var)}(?![A-Za-z0-9_])", command):
            return (
                f"{what}, and the command names {var}. The approval must come from the environment Claude Code started with, "
                f"set by the person who approves, never from the command itself.{note} Run it without {var}, and ask that person "
                "to set it, or to run the command themselves"
            )
        if not (env.get(var) or "").strip():
            return (
                f"{what} and needs approval.{note} Ask the person who approves the release to set {var} in the environment "
                f"Claude Code starts with, such as `{var}=CHG-1234 claude`. Its value can be a change or ticket reference. "
                "Or ask that person to run the command themselves. An agent cannot set it."
            )
    return None
