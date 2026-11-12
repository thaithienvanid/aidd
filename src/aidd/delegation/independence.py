"""Whether the delegate runs on another model than the one that wrote the change. A delegate that shares the author's model
shares its blind spots, so its yes is a weaker second look. This is advice, never a refusal: aidd cannot see which model a
harness runs, so it warns only when the config names the delegate's model and a commit's `Assisted-by` names the same one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aidd import knowledge, workitems
from aidd.kernel import git

if TYPE_CHECKING:
    from aidd.delegation.check import Check


def authors(check: Check) -> set[str]:
    """The model names the change's commits say helped write them, from `Assisted-by: <harness>/<model>`, in lowercase."""
    if not (check.tip and check.top):
        return set()
    found = (v for c in git.commits(check.tip, check.req.head, check.top) for v in workitems.assisted_by_values(c["message"]))
    return {v.split("/", 1)[1].strip().casefold() for v in found if "/" in v}


def same_model_warning(check: Check) -> str | None:
    """A warning when `agents.models` puts the delegate on a model an `Assisted-by` of this change names; None when the
    delegate's model is unset or `inherit`, which aidd cannot see, or differs."""
    models = dict((check.cfg.get("agents", "models", default={}) if check.cfg else {}) or {})
    model = knowledge.resolve_agent_model(models, "delegate")
    if not model or model == knowledge.INHERIT_MODEL or "/" not in model:
        return None
    name = model.split("/", 1)[1].casefold()
    if name not in authors(check):
        return None
    return (
        f"the delegate runs on {model}, a model that wrote this change (its `Assisted-by` says {name}), so its yes is a weaker second look. "
        "Set another model for the delegate in `agents.models` (`aidd init --aidd-team` writes it)"
    )
