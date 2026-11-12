"""The built-in data of a standing delegation (schemas/risks.json, `delegation`), what a delegation covers, and the
reason codes the check gives (the `delegate` group of schemas/findings.json, their one owner)."""

from __future__ import annotations

import functools

from aidd import config
from aidd.kernel import resources

# The delegate's two tools, by each name a harness gives them: the plugin's server, or a project's own `aidd mcp`. The team's
# data (`mcp_tools` of the `delegate` role in schemas/roles.json) names them, as it names the tools of the agent file, and the
# hook's matcher, its denial to any other agent, and the ask rules on the answer tool are all built from this one list.
ANSWER_TOOL = "delegate_answer"
_TOOL_NAMES = tuple(resources.load_json("roles.json")["roles"]["delegate"]["mcp_tools"])
if ANSWER_TOOL not in _TOOL_NAMES:  # without it the answer tool would have no ask rule and no hook denial
    raise ValueError(f"schemas/roles.json: the `delegate` role's `mcp_tools` must name `{ANSWER_TOOL}`")
DELEGATE_ANSWER_TOOLS = tuple(f"{prefix}{ANSWER_TOOL}" for prefix in config.CLAUDE_TOOL_PREFIXES)
DELEGATE_TOOLS = tuple(f"{prefix}{name}" for prefix in config.CLAUDE_TOOL_PREFIXES for name in _TOOL_NAMES)
# The file that turns a delegation off in one clone, in its common git folder. It only narrows, so any session may write it.
STOP_FILE = ("aidd", "delegation-stopped")


@functools.cache
def builtin() -> dict:
    """schemas/risks.json's `delegation` section."""
    return resources.load_json("risks.json")["delegation"]


@functools.cache
def reasons() -> dict[str, dict]:
    """Each reason code the check can give, with whether it is reserved, what it means, and the next step: the `delegate` group
    of schemas/findings.json, their one owner."""
    return resources.load_json("findings.json")["groups"]["delegate"]["codes"]


def irreversible(action: str) -> bool:
    """Whether the built-in action is one a person cannot undo."""
    return bool(resources.load_json("risks.json")["actions"].get(action, {}).get("irreversible"))


def delegable() -> list[str]:
    """Every action a delegation may cover, in the data's order."""
    return list(builtin()["actions"])


def undoable() -> list[str]:
    """Every delegable action a person can undo, in the data's order: what `aidd init --delegate` writes as `decides`."""
    return [a for a in builtin()["actions"] if not irreversible(a)]


def covered(delegation: dict) -> list[str]:
    """The actions a delegation decides: the list `decides` names, less the config's `reserved`. A `decides` that is no
    list decides nothing."""
    actions = builtin()["actions"]
    decides = delegation.get("decides")
    chosen = [a for a in decides if a in actions] if isinstance(decides, list) else []
    kept = set(delegation.get("reserved") or [])
    return [a for a in chosen if a not in kept]


def template(action: str) -> list[str] | None:
    """The action's exact command template, one word per item, or None for an action that runs no command."""
    entry = builtin()["actions"].get(action) or {}
    return list(entry["template"]) if "template" in entry else None


def reason(code: str, detail: str) -> dict:
    """A reason the check defers, with whether the schema reserves it. An unknown code is a bug, so it raises."""
    return {"code": code, "reserved": bool(reasons()[code]["reserved"]), "detail": detail}
