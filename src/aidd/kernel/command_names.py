"""A name from a repository, as a command aidd prints may hold it.

A file name, a branch name, and a Spec's id are the repository's text, so they are data: a hostile repository may name one
with `;`, `$(...)`, a backtick, a quote, a space, a line break, or a leading `-`. A person or an agent pastes a command aidd
prints, so one rule holds at every place that prints a command with such a name: the name joins the command only when it
is a SAFE_NAME, quoted, and a command that takes it as a path puts it after `--`. Any other name is described in words, and
no command holds it (`NO_COMMAND` says so)."""

from __future__ import annotations

import re
import shlex

# The names that may join a printed command: letters, digits, `.`, `_`, `/`, and `-`, never first. A shell reads none of them.
SAFE_NAME = re.compile(r"[A-Za-z0-9._/][A-Za-z0-9._/-]*")
# What a note says in the place of a command for any other name.
NO_COMMAND = "its name holds characters a command line could misread, so aidd prints no command for it"


def quoted(name: str) -> str | None:
    """`name` as a command word, quoted as a shell reads it, when it is a SAFE_NAME; None for any other name, which never
    joins a command."""
    return shlex.quote(name) if SAFE_NAME.fullmatch(name) else None
