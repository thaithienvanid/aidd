"""The closed registry of eval claims, read from `evals/claims.json` (the shape is schemas/eval-claims.schema.json).

A claim is `kind:name`. Each kind has one owner that says which names are real:

- `action:` is an action in schemas/risks.json, and `route:` is one of its areas, or a route outcome the registry's `routes` maps
  to one of the four routes.
- `gate:` is one of the gates, mapped to the action a person's yes opens.
- `stop:` is a stop a case makes an agent take, mapped to one of the stop codes in schemas/common.schema.json.
- `duty:` is `<role>.<name>`: a role in schemas/roles.json, or the lead that runs the team's flows, and a duty the registry lists.
- `control:` and `principle:` are rules the registry states in one line and ties to the file that holds them.
- `trigger:` is a practice skill in schemas/roles.json.

A case may claim only what is registered, and every registered claim is required: a case proves it, or `known_gaps` says why
none does yet. Nothing here runs an agent.
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config
from aidd.kernel import resources

# The agent that runs the team's flows is the lead. It is not a role in schemas/roles.json, but a duty can be its own.
LEAD = "lead"
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def _stop_codes() -> list[str]:
    """The stop codes a run can name, without `none`, which says the step is done."""
    return [c for c in resources.load_json("common.schema.json")["$defs"]["stop_code"]["enum"] if c != "none"]


def registry_claims(file: dict) -> list[str]:
    """Every claim the registry lists, in the order of its sections: gates, stops, routes, duties, controls, principles, triggers."""
    out = [f"gate:{n}" for n in file.get("gates", {})] + [f"stop:{n}" for n in file.get("stops", {})]
    out += [f"route:{n}" for n in file.get("routes", {})]
    out += [f"duty:{role}.{n}" for role, names in file.get("duties", {}).items() for n in names]
    out += [f"control:{n}" for n in file.get("controls", {})] + [f"principle:{n}" for n in file.get("principles", {})]
    return out + [f"trigger:{n}" for n in file.get("triggers", [])]


def uncovered_stop_codes(file: dict) -> list[str]:
    """The stop codes no `stop:` claim and no principle names, so no case can make an agent take that stop."""
    named = set(file.get("stops", {}).values()) | {p["stop_code"] for p in file.get("principles", {}).values() if "stop_code" in p}
    return [c for c in _stop_codes() if c not in named]


def is_registered(claim: str, file: dict) -> bool:
    """Whether the claim's owner knows its name: risks.json for an action or an area, roles.json for a practice, the registry for the rest."""
    kind, _, name = claim.partition(":")
    risks = resources.load_json("risks.json")
    if kind == "action":
        return name in risks["actions"]
    if kind == "route" and name in risks["areas"]:
        return True
    return claim in registry_claims(file)


def registry_problems(file: dict, root: Path) -> list[str]:
    """Each way the registry disagrees with the files that own its facts: a gate on an unknown action, a stop code, a route, a role,
    a practice, or a source file that does not exist, a name that is not lower-case words, a known gap that nothing requires."""
    risks, roles = resources.load_json("risks.json"), resources.load_json("roles.json")
    codes, problems = _stop_codes(), []

    def bad(where: str, name: str, ok: bool, why: str) -> None:
        if not ok:
            problems.append(f"{where} {name!r}: {why}")

    for name, action in file.get("gates", {}).items():
        bad("gate", name, action in risks["actions"], f"names {action!r}, which is no action in schemas/risks.json")
    for name, code in file.get("stops", {}).items():
        bad("stop", name, code in codes, f"names {code!r}, which is no stop code in schemas/common.schema.json")
    for name, route in file.get("routes", {}).items():
        bad("route", name, route in config.ROUTES, f"names {route!r}, which is no route")
    for role, names in file.get("duties", {}).items():
        bad("duty role", role, role == LEAD or role in roles["roles"], "is no role in schemas/roles.json, and not the lead")
        bad("duty role", role, names == sorted(set(names)), "lists its duties unsorted or twice")
        problems += [f"duty {role}.{n!r}: not lower-case words with hyphens" for n in names if not _NAME.match(n)]
    for kind in ("controls", "principles"):
        for name, entry in file.get(kind, {}).items():
            bad(kind[:-1], name, (root / entry["source"]).is_file(), f"has source {entry['source']!r}, which is no file")
            bad(kind[:-1], name, entry.get("stop_code", codes[0]) in codes, "names a stop code that does not exist")
    for name in file.get("triggers", []):
        bad("trigger", name, name in roles["skills"], "is no practice in schemas/roles.json")
    for kind in ("gates", "stops", "routes", "controls", "principles"):
        problems += [f"{kind[:-1]} {n!r}: not lower-case words with hyphens" for n in file.get(kind, {}) if not _NAME.match(n)]
    claims = registry_claims(file)
    problems += [f"claim {c!r} is listed twice" for c in sorted({c for c in claims if claims.count(c) > 1})]
    return problems
