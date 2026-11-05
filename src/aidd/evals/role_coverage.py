"""Which role eval cases cover which role operation. An operation is a role at one loop step it works in (`steps` in schemas/roles.json); a case names the step it exercises."""

from __future__ import annotations

from aidd import knowledge


def role_operations() -> list[tuple[str, str]]:
    """Every (role, step) pair the team registry lists, roles in team order and steps in loop order."""
    data = knowledge.roles()
    return [(role, step) for role in data["order"] for step in data["roles"][role]["steps"]]


def cases_by_operation(scenarios: list[dict]) -> dict[tuple[str, str], list[str]]:
    """The ids of the cases for each role operation; an operation no case names maps to an empty list."""
    found: dict[tuple[str, str], list[str]] = {op: [] for op in role_operations()}
    for sc in scenarios:
        key = (str(sc.get("role")), str(sc.get("step")))
        if key in found:
            found[key].append(str(sc["id"]))
    return found


def role_case_problems(scenarios: list[dict]) -> list[str]:
    """Each case that names no `step`, or a step its role does not work in, so it would count toward no operation."""
    steps: dict[str, set[str]] = {}
    for role, step in role_operations():
        steps.setdefault(role, set()).add(step)
    return [
        f"{sc.get('id', '?')}: `step` is {sc.get('step')!r}; the {sc.get('role')} works in {', '.join(sorted(steps.get(str(sc.get('role')), []))) or 'no known role'}"
        for sc in scenarios
        if sc.get("step") not in steps.get(str(sc.get("role")), set())
    ]


def role_coverage_table(scenarios: list[dict]) -> str:
    """The cases per role operation as a Markdown table, in the registry's order; a gap reads `0`."""
    rows = ["| Role | Step | Cases |", "| --- | --- | --- |"]
    rows += [f"| {role} | {step} | {len(ids)} |" for (role, step), ids in cases_by_operation(scenarios).items()]
    return "\n".join(rows)
