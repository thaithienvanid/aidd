"""Which actions a shell command is, from the actions' `commands` patterns, and which branch a `git push` reaches.

A pattern matches a whole simple command, with `*` for any run of characters (`git push --force*`). A command line is
split at `&&`, `||`, `;`, `|`, and new lines outside quotes, and each part is matched alone, so `make && git push -f`
is `git.push.force`. Git's own options before its subcommand (`git -C repo -c k=v push`) are set aside first.

This is advice, never a control: an alias, a script, or a variable gets past any pattern. SECURITY.md says so.
"""

from __future__ import annotations

import re
import shlex

from aidd.kernel import git
from aidd.risk.rules import LEVEL_RANK, RuleSet, level_of

# Git's options that take a value before the subcommand, and those that take none.
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_GIT_FLAG_OPTIONS = {"--no-pager", "-p", "--paginate", "--bare", "--no-replace-objects", "--literal-pathspecs", "--no-optional-locks", "-P"}


def split(line: str) -> list[str]:
    """The simple commands of a command line, split at `&&`, `||`, `;`, `|`, and new lines outside quotes."""
    parts, buf, quote, i = [], [], "", 0
    while i < len(line):
        c = line[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"' and i + 1 < len(line):
                buf.append(line[i + 1])
                i += 1
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c == "\\" and i + 1 < len(line):
            buf.append(line[i : i + 2])
            i += 1
        elif line.startswith(("&&", "||"), i):
            parts.append("".join(buf))
            buf = []
            i += 1
        elif c in ";|\n":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def normalize(command: str) -> str:
    """One simple command as the patterns read it: words joined by one space, with git's own options set aside."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        words = words[1:]  # an environment assignment before the program
    if words and words[0].rsplit("/", 1)[-1] == "git":
        rest, out = words[1:], ["git"]
        while rest and rest[0].startswith("-"):
            opt = rest.pop(0)
            if opt in _GIT_VALUE_OPTIONS and rest:
                rest.pop(0)
            elif "=" in opt or opt in _GIT_FLAG_OPTIONS:
                continue
        words = out + rest
    return " ".join(words)


def _pattern(p: str) -> re.Pattern[str]:
    return re.compile("".join(".*" if ch == "*" else re.escape(ch) for ch in " ".join(p.split())) + r"\Z", re.S)


def matching_actions(rs: RuleSet, line: str) -> list[tuple[str, str]]:
    """Each (action, simple command) the command line matches, in the order of the line."""
    out: list[tuple[str, str]] = []
    for part in split(line):
        simple = normalize(part)
        for action, spec in rs.actions.items():
            if any(_pattern(p).match(simple) for p in spec.get("commands", [])):
                out.append((action, simple))
    return out


def push_branch(simple: str, cwd: str = ".") -> str | None:
    """The branch a `git push` reaches, as a rule names it: `default` when it names the repository's default branch,
    pushes HEAD while that branch is checked out, or pushes every branch (`--all`, `--mirror`); `own` for the branch
    checked out; `shared` for another branch it names, since aidd cannot tell whose it is; and None when the command is
    not a push or git cannot tell."""
    words = simple.split()
    if words[:2] != ["git", "push"]:
        return None
    if {"--all", "--mirror", "--branches"} & set(words[2:]):
        return "default"
    args = [w for w in words[2:] if not w.startswith("-")]
    default = _default_branch(cwd)
    current = git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()
    refspecs = args[1:] if len(args) > 1 else []
    if not refspecs:
        if not current:
            return None
        return "default" if current == default else "own"
    reached = []
    for spec in refspecs:
        dest = spec.lstrip("+").split(":")[-1].removeprefix("refs/heads/")
        dest = current if dest == "HEAD" else dest
        if default and dest == default:
            return "default"
        reached.append("own" if dest and dest == current else "shared")
    return "shared" if "shared" in reached else "own"


def _default_branch(cwd: str) -> str | None:
    """The repository's default branch by name (`main`), or None when git cannot tell."""
    try:
        return git.default_base(cwd).split("/", 1)[-1]
    except (git.GitError, OSError, ValueError):
        return None


def command_level(rs: RuleSet, line: str, *, branch: str | None = None, role: str | None = None, cwd: str = ".") -> dict:
    """What a command line is: each action it matches, with its level and the rule that decided it, and the highest
    level of them all (`allow` when it matches no action)."""
    found = []
    top = "allow"
    for action, simple in matching_actions(rs, line):
        where = branch or (push_branch(simple, cwd) if action.startswith("git.push") else None)
        level, rule = level_of(rs, action, branch=where, role=role)
        found.append({"action": action, "command": simple, "branch": where, "level": level, "rule": rule.label() if rule else None})
        if LEVEL_RANK[level] > LEVEL_RANK[top]:
            top = level
    return {"command": line, "level": top, "actions": found}
