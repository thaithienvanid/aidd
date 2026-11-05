"""The table behind "a backslash escape in a program name never lowers a level".

To a POSIX shell, `g\\h pr merge 3` is `gh pr merge 3`. The table takes every command the risk rules and the risk tests name,
puts a backslash before each character of the program word and of the subcommand word, wraps the command in each wrapper the
reader knows, and returns each row whose level is lower than the same command's without the escape. It takes the function it tests as an argument, so a copy of an older aidd can be held to it.
"""

from __future__ import annotations

import ast
import json
import random
import re
import shlex
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANK = {"allow": 0, "report": 1, "ask": 2}
RISK_TESTS = ("test_risk.py", "test_gh_api_risk.py", "test_local_merge.py", "test_checkout_risk.py", "test_risk_environments.py", "test_secret_reads.py")
PLAIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")


def concrete(pattern: str) -> list[str]:
    """A command that matches a pattern with `*`, with the star empty and with a word in its place."""
    return list(dict.fromkeys(" ".join(pattern.replace("*", fill).split()) for fill in ("", "x")))


def named_commands() -> list[str]:
    """Every command the built-in rules' patterns and examples, and the risk tests' string literals, name, in a fixed order."""
    risks = json.loads((ROOT / "schemas" / "risks.json").read_text(encoding="utf-8"))
    found: list[str] = []
    for spec in risks["actions"].values():
        for pattern in spec.get("commands", []):
            found += concrete(pattern)
        for example in spec.get("examples", []):
            found += re.findall(r"`([^`]+)`", example)
    programs = {c.split()[0] for c in found if c.split()}
    for name in RISK_TESTS:
        for node in ast.walk(ast.parse((ROOT / "tests" / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and " " in node.value.strip() and "\n" not in node.value:
                if node.value.split()[0] in programs:
                    found.append(node.value)
    return sorted(c for c in dict.fromkeys(found) if balanced(c))


def balanced(command: str) -> bool:
    """Whether the quotes close. A shell never runs a command whose quote stays open, and aidd splits one at its spaces."""
    try:
        shlex.split(command)
    except ValueError:
        return False
    return True


def escaped(command: str) -> list[str]:
    """The command with a backslash before each character of its first word and of its second, when that is a plain word."""
    words = command.split(" ")
    out = []
    for at in (0, 1):
        if at < len(words) and PLAIN_WORD.fullmatch(words[at]):
            for i in range(len(words[at])):
                word = words[at][:i] + "\\" + words[at][i:]
                out.append(" ".join([*words[:at], word, *words[at + 1 :]]))
    return out


# The wrappers the reader knows (shell.py), with the command in place of `{}`, or quoted in place of `{q}`.
WRAPPERS = ("{}", "sh -c {q}", "bash -c {q}", "env {}", "sudo {}", "timeout 5 {}", "xargs {}", "eval {q}")


def wrapped(wrapper: str, command: str) -> str:
    return wrapper.format(command, q=shlex.quote(command))


def lower_rows(command_level: Callable[[str], str], limit: int = 30, seed: int = 2611) -> tuple[int, list[tuple[str, str, str]]]:
    """How many escaped commands were read, each in every wrapper, and each (line, level, level without the escape) where the
    escape lowers the level of the same wrapped command. A wrapper may change a level by itself (`env` takes the settings
    that follow it); that is no escape, so each row is held to its own unescaped twin."""
    asked = [c for c in named_commands() if RANK[command_level(c)] > 0]
    random.Random(seed).shuffle(asked)
    read, lower = 0, []
    for command in asked[:limit]:
        for wrapper in WRAPPERS:
            plain = command_level(wrapped(wrapper, command))
            for variant in escaped(command):
                read += 1
                line = wrapped(wrapper, variant)
                if RANK[command_level(line)] < RANK[plain]:
                    lower.append((line, command_level(line), plain))
    return read, lower
