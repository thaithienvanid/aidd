"""Where a delegation stands. The check reads it from the default branch's tip alone, so a `delegation` block in the
checked-out branch's config does nothing until it is there, and nothing else says so."""

from __future__ import annotations

import re

from aidd import config
from aidd.kernel import documents, git

# A branch name this note prints: git's ref rules allow more, and the name comes from the config's text.
PLAIN_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def _tip_ref(name: str, cwd: str) -> str:
    """The full ref of branch `name` in this clone: the local branch, else the one a remote fetched; "" when there is none."""
    for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
        if git.ok(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd):
            return ref
    return ""


def _sets_delegation(text: str | None) -> bool:
    """Whether a config's text sets a `delegation`. A config that does not parse sets none."""
    try:
        data = documents.parse_yaml(text, config.CONFIG_PATH) if text else {}
    except documents.DocumentError:
        return False
    return isinstance(data, dict) and bool(data.get("delegation"))


def not_yet_on_default_note(cwd: str, block: dict) -> str:
    """What `aidd doctor` and `aidd status` say when the checked-out config's `delegation` (`block`) is not in the default
    branch's tip in this clone: it does not count until it is, and the next step. "" when the tip holds one, when there is
    no block, or when this clone has no such branch to read."""
    name = block.get("default_branch") if block else None
    if not isinstance(name, str) or not PLAIN_BRANCH.fullmatch(name) or not (ref := _tip_ref(name, cwd)):
        return ""
    if _sets_delegation(git.show(ref, config.CONFIG_PATH, cwd)):
        return ""
    here = documents.one_line(git.current_branch(cwd), 80)
    if here == name:
        where = f"{config.CONFIG_PATH} on {name} has it uncommitted"
        step = f"commit {config.CONFIG_PATH} on {name}"
    else:
        where = f"{config.CONFIG_PATH} on {here or 'this checkout'} has it, and {name} does not"
        step = f"a person merges the change to {config.CONFIG_PATH} into {name}"
    return (
        f"delegation: {where}, so it does not count until it is on {name}, and every delegated ask comes back to you. "
        f"Next: {step}, then run `aidd doctor` again."
    )
