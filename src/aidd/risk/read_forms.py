"""The commands that provably write nothing, which a pattern would still match by their leading words.

A pattern in schemas/risks.json matches a whole simple command with `*`, so `git tag*` also matches `git tag -l`, and
`kubectl apply*` matches `kubectl apply --dry-run=client`. The file's `read_forms` and `help_forms` list the forms of
a command that are only a listing, a preview the tool documents as sending nothing, or a request for help. A command
reads as one only when every word of it is one the form lists, so an unknown word, a second command, a wrapper, or a
setting before the program keeps the action. The caller passes only a command typed as it runs, never one found inside
a wrapper, because `xargs` adds words and `sudo` changes who runs it (`commands.call_actions`).

This is advice, never a control: SECURITY.md says so.
"""

from __future__ import annotations

import re

from aidd.risk import rules
from aidd.risk.shell import shell_words, tokens

# Unquoted, each of these lets the shell expand, group, or comment a word into something the form never listed.
_SHELL_SPECIAL = "*?[]{}~()#!\\"


def cleared_actions(call: str) -> frozenset[str]:
    """The built-in actions that `call`, one simple command typed as it runs, provably is not: those a read form or a
    help form names, when the command holds nothing the form does not list. Empty for any other command."""
    words = _plain_words(call)
    if not words:
        return frozenset()
    data = rules.builtin()
    cleared: set[str] = set()
    for form in data["read_forms"]:
        if _is_read(words, form):
            cleared.update(form["clears"])
    for form in data["help_forms"]:
        if _is_help(words, form):
            cleared.update(form["clears"])
    return frozenset(cleared)


def _plain_words(call: str) -> list[str] | None:
    """The words of `call` when the shell passes each to the program as typed, else None: no setting before the
    program, no redirection, no `$` or backtick expansion, and nothing unquoted that expands, groups, or comments. A
    form names its program by its bare name, so a path or a group in front never equals it."""
    text = call.strip()
    typed = shell_words(text)
    words = tokens(text)
    if any(operator for _, operator in typed) or [w for w, _ in typed] != [str(w) for w in words]:
        return None  # a redirection writes a file, and a setting before the program was dropped from `words`
    if any(w.expands for w in words) or _unquoted(text, _SHELL_SPECIAL):
        return None
    return [str(w) for w in words]


def _unquoted(text: str, specials: str) -> bool:
    """Whether `text` holds any of `specials` outside quotes. A backslash counts as one wherever it is."""
    quote = ""
    for c in text:
        if c == "\\":
            return True
        if quote:
            quote = "" if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c in specials:
            return True
    return False


def _is_read(words: list[str], form: dict) -> bool:
    """Whether `words` are the form's program and words, then only options and words the form lists."""
    start = 1 + len(form["words"])
    if words[:start] != [form["program"], *form["words"]]:
        return False
    flags, values = set(form.get("flags", [])), set(form.get("values", []))
    seen: list[str] = []
    names: list[str] = []
    args, i = words[start:], 0
    while i < len(args):
        arg = args[i]
        if arg in flags or _carries_value(arg, form):
            seen.append(arg)
        elif arg in values:
            if i + 1 >= len(args) or (args[i + 1].startswith("-") and args[i + 1] != "-"):
                return False  # no value, or a word that may be an option
            seen.append(arg)
            i += 1
        elif arg.startswith("-"):
            return False
        else:
            names.append(arg)
        i += 1
    if any(seen.count(r) != 1 for r in form.get("required", [])):
        return False
    allowed = form.get("positionals", "none")
    return not names or allowed == "any" or (isinstance(allowed, list) and any(o in seen for o in allowed))


def _carries_value(arg: str, form: dict) -> bool:
    """Whether `arg` is a listed option with its value attached: `--sort=key`, `-n`, or `-n5`."""
    if any(arg.startswith(p) and len(arg) > len(p) for p in form.get("attached", [])):
        return True
    return any(re.fullmatch(re.escape(n) + "[0-9]*", arg) for n in form.get("numbered", []))


def _is_help(words: list[str], form: dict) -> bool:
    """Whether `words` are the program, one of its listed commands, and one of its help flags, and nothing else."""
    if words[:1] != [form["program"]] or len(words) < 3:
        return False
    return words[-1] in form["flags"] and words[1:-1] in form["commands"]
