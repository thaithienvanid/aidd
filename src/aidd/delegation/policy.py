"""The built-in data of a standing delegation (schemas/risks.json, `delegation`), what a delegation covers, and the
reason codes the check gives (schemas/delegate-check.schema.json, their one owner)."""

from __future__ import annotations

import functools
import re

from aidd.kernel import resources

# The one harness whose PermissionRequest hook answers a delegated ask in this version (the live check of Claude Code
# 2.1.319). Every other harness keeps its ask rules, so the check defers there.
DELEGATING_HARNESS = "claude-code"
# Who a delegated yes names in its `Decided-by` trailer: the role, in the harness that ran it. The check runs before the
# delegate does, so it names the role its agent file pins, never a model it cannot see.
DECIDED_BY = "agent:claude-code/aidd-team:delegate"
# The file that turns a delegation off in one clone, in its common git folder. It only narrows, so any session may write it.
STOP_FILE = ("aidd", "delegation-stopped")


@functools.cache
def builtin() -> dict:
    """schemas/risks.json's `delegation` section."""
    return resources.load_json("risks.json")["delegation"]


@functools.cache
def reasons() -> dict[str, dict]:
    """Each reason code the check can give, with whether it is reserved, what it means, and the next step."""
    return resources.load_json("delegate-check.schema.json")["x-reasons"]


def irreversible(action: str) -> bool:
    """Whether the built-in action is one a person cannot undo."""
    return bool(resources.load_json("risks.json")["actions"].get(action, {}).get("irreversible"))


def _version(text: str) -> tuple[int, ...]:
    """`1.0.0` as (1, 0, 0); a version aidd cannot read is the earliest, so `all` covers the least."""
    found = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(text))
    return tuple(int(x) for x in found.groups()) if found else (0, 0, 0)


def delegable() -> list[str]:
    """Every action a delegation may cover, in the data's order."""
    return list(builtin()["actions"])


def covered(delegation: dict, aidd_version: str) -> list[str]:
    """The actions a delegation decides. `all` is each delegable action the config's `aidd_version` knew that a person
    can undo, so an action a later aidd adds, or an irreversible one, is delegated only by name. A list names them. The
    config's `reserved` takes its actions back out."""
    actions = builtin()["actions"]
    decides = delegation.get("decides", [])
    if decides == "all":
        chosen = [a for a, entry in actions.items() if not irreversible(a) and _version(entry["since"]) <= _version(aidd_version)]
    else:
        chosen = [a for a in decides or [] if a in actions]
    kept = set(delegation.get("reserved") or [])
    return [a for a in chosen if a not in kept]


def template(action: str) -> list[str] | None:
    """The action's exact command template, one word per item, or None for an action that runs no command."""
    entry = builtin()["actions"].get(action) or {}
    return list(entry["template"]) if "template" in entry else None


def reason(code: str, detail: str) -> dict:
    """A reason the check defers, with whether the schema reserves it. An unknown code is a bug, so it raises."""
    return {"code": code, "reserved": bool(reasons()[code]["reserved"]), "detail": detail}
