"""Who decides and who does the work: every human who approves, and every agent role with what it may write.

A team of humans and agents breaks down in predictable ways: nobody knows who owns a decision, people run
private agents on the side and split the context, and agents start work nobody asked for. The config's `owners`
answer the first from the repository itself, and `agents.proactive_roles` bounds the last. Whether the
team is ready to work this way (the work written down, owners named, the same tools for everyone, a rubric,
a written goal) is part of `aidd doctor`.

The team's own rules and its copies of library standards live in `standards`, each a document the named roles read before their step when the change touches its `when_changed`
paths, so an agent loads exactly the ones that apply to its role.
"""

from __future__ import annotations

from aidd import config

DEFAULT_PROACTIVE_ROLES = ("product-manager", "sre")


def proactive_roles(cfg: config.Config | None) -> list[str]:
    """The agent roles that may suggest work nobody asked for: always as a draft Spec with `suggested_by =
    "role:<role>"`, which stays a draft until a person records `triage` (see workitems.triage_errors)."""
    configured = cfg.get("agents", "proactive_roles") if cfg else None
    return list(DEFAULT_PROACTIVE_ROLES) if configured is None else list(configured)
