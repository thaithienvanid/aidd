"""The level of an action asked by its name, where a command that is the action reads a repository: a `git commit` on the default
branch with no remote is a merge (`commit_reading`), so `git.commit` there takes the higher of its own level and `git.merge`'s,
as the command reads it. Asked by name, an unreadable folder or branch reads the strictest, as it does for the command."""

from __future__ import annotations

from aidd.risk.commands import session_branch
from aidd.risk.commit_reading import commit_reading
from aidd.risk.rules import LEVEL_RANK, Rule, RuleSet, level_on_any_branch


def action_level(rs: RuleSet, action: str, folder: str | None, **narrow) -> tuple[str, Rule | None]:
    """`level_on_any_branch`, and for `git.commit` the higher of that and `git.merge`'s where `folder` is a repository whose commit
    lands as a merge. `folder` is where the question is asked, or None when it is no repository, which reads the strictest."""
    level, rule = level_on_any_branch(rs, action, **narrow)
    if action != "git.commit":
        return level, rule
    where = narrow.get("branch") or (session_branch(folder) if folder else None)
    reading = commit_reading("git commit", where, folder)
    if reading is None:
        return level, rule
    merged = level_on_any_branch(rs, "git.merge", **(narrow | {"branch": reading[0]}))
    return max((level, rule), merged, key=lambda found: LEVEL_RANK[found[0]])
