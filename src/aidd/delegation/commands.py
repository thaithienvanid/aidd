"""A delegated command against its action's exact template (schemas/risks.json, `delegation.actions`): one program, its
words in the template's order, and no chain, pipe, redirection, substitution, wrapper, or environment assignment."""

from __future__ import annotations

import re
import shlex

# What each `<name>` in a template may be. A sha is a full commit id, so a command names one exact commit.
PLACEHOLDERS = {
    "sha": r"[0-9a-f]{40}",
    "branch": r"(?![-/.])(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9._/-]{1,200}(?<![./])",
    "number": r"[1-9][0-9]{0,9}",
    "repo": r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
    "method": r"--squash|--merge",
    "message": r"[\s\S]+",
}
# The one placeholder a first call may leave out, with the flag before it: the check fills it with the trailers.
MESSAGE = "<message>"
# Characters a command may never hold, quoted or not: a substitution, an escape, or a byte a reader cannot see.
_NEVER = re.compile(r"[$`\\\x00-\x08\x0b-\x1f\x7f]")
_OPERATOR = re.compile(r"^[;&|<>()]+$")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Words that widen what a command reaches, wherever they stand: GitHub's admin override, another repository or folder.
_WIDENING = ("--admin", "-C", "--git-dir", "--work-tree", "-R", "--hostname")


def words(line: str) -> tuple[list[str], str]:
    """The command's words as the shell reads them, and "" or why the line is no single command."""
    if _NEVER.search(line):
        return [], "it holds a `$`, a backtick, a backslash, or a control character, so the shell could run more than it shows"
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # a `#` is a word, so a comment never hides text the shell drops
    try:
        found = list(lexer)
    except ValueError as exc:
        return [], f"the shell cannot read it ({exc})"
    if any(_OPERATOR.match(w) for w in found):
        return [], "it chains, pipes, or redirects, so it is more than one command"
    return found, ""


def widening(found: list[str]) -> str:
    """Why the words reach further than the template allows, or "": an assignment first, or a widening flag."""
    if found and _ASSIGNMENT.match(found[0]):
        return f"it starts with the environment assignment {found[0].split('=', 1)[0]}="
    hit = next((w for w in found if w in _WIDENING or w.startswith(("--admin=", "--repo=", "-R="))), None)
    return f"it names {hit}" if hit else ""


def _pattern(word: str) -> re.Pattern[str]:
    """A template word as a pattern: its literal text, with each `<name>` as that placeholder's group."""
    parts = re.split(r"(<[a-z]+>)", word)
    body = "".join(f"(?P<{p[1:-1]}>{PLACEHOLDERS[p[1:-1]]})" if p.startswith("<") else re.escape(p) for p in parts)
    return re.compile(body)


def fit(template: list[str], line: str) -> tuple[dict[str, str] | None, str]:
    """The values a command gives the template's placeholders, or None and why it does not fit. A command may leave
    out the message and its flag, which the check fills."""
    found, problem = words(line)
    if problem:
        return None, problem
    shapes = [template]
    if MESSAGE in template:
        i = template.index(MESSAGE)
        shapes.append(template[: i - 1] + template[i + 1 :])
    for shape in shapes:
        if len(shape) != len(found):
            continue
        values: dict[str, str] = {}
        for want, got in zip(shape, found, strict=True):
            matched = _pattern(want).fullmatch(got)
            if not matched:
                break
            values.update(matched.groupdict())
        else:
            if "\n" in line and line != canonical(shape, values):
                # A line break outside quotes would end the command, so a command over lines is only the exact one.
                return None, "it spans lines but is not the exact command the check gives"
            return values, ""
    return None, "its words are not the template's: " + " ".join(template)


def canonical(template: list[str], values: dict[str, str]) -> str:
    """The template with its placeholders filled, quoted for the shell: the exact command an accept covers."""
    filled = [re.sub(r"<([a-z]+)>", lambda m: values[m.group(1)], word) for word in template]
    return shlex.join(filled)
