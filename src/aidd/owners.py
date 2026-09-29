"""Who decides and who does the work: every human who approves, and every agent role with what it may write.

A team of people and agents breaks down in predictable ways: nobody knows who owns a decision, people run
private agents on the side and split the context, and agents start work nobody asked for. `aidd owners`
answers the first from the repository itself, and `[agents] proactive_roles` bounds the last. Whether the
team is ready to work this way (the work written down, owners named, the same tools for everyone, a rubric,
a written goal) is part of `aidd doctor`.

The team's own rules live in `[[standards]]`: house standards, each a document the named roles read before
their step when the change touches its `when_changed` paths. `aidd owners --json` lists them per role, so an
agent loads exactly the ones that apply.
"""

from __future__ import annotations

from . import config as cfgmod
from . import docs, globs, resources

DEFAULT_PROACTIVE_ROLES = ("product-manager", "agile-coach", "sre")


def proactive_roles(cfg: cfgmod.Config | None) -> list[str]:
    """The agent roles that may propose work nobody asked for: always as a draft Spec with `proposed_by =
    "agent:<role>"`, which stays a draft until a person records `triage` (see workitems.triage_errors)."""
    configured = cfg.get("agents", "proactive_roles") if cfg else None
    return list(DEFAULT_PROACTIVE_ROLES) if configured is None else list(configured)


def house_standards(cfg: cfgmod.Config | None) -> list[dict]:
    """The team's own standards from `[[standards]]`, each marked enforced (by named `[[tests]]`) or guidance."""
    if cfg is None:
        return []
    suite = {t.get("name") for t in cfg.get("tests", default=[]) or []}
    out = []
    for s in cfg.standards:
        enforced = list(s.get("enforced_by", []))
        out.append(
            {
                "name": s["name"],
                "path": s["path"],
                "roles": list(s["roles"]),
                "when_changed": list(s.get("when_changed", [])),
                "enforced_by": enforced,
                "unknown_tests": [t for t in enforced if t not in suite],
                "enforcement": f"enforced by {', '.join(enforced)}" if enforced else "guidance",
            }
        )
    return out


def standards_for(standards: list[dict], role: str, changed: list[str] | None = None) -> list[dict]:
    """The house standards a role reads before its step: those naming the role (or `*`) whose `when_changed`
    matches a changed path. With no paths given, every standard the role names."""

    def applies(s: dict) -> bool:
        if "*" not in s["roles"] and role not in s["roles"]:
            return False
        return changed is None or not s["when_changed"] or any(globs.match_any(s["when_changed"], p) for p in changed)

    return [s for s in standards if applies(s)]


def build(cfg: cfgmod.Config | None, changed: list[str] | None = None) -> dict:
    roles = resources.roles()
    may_propose = set(proactive_roles(cfg))
    standards = house_standards(cfg)

    def get(*keys: str, default=None):
        return cfg.get(*keys, default=default) if cfg else default

    humans = {
        "approvers": list(get("owners", "approvers", default=[])),
        "specialist_pools": dict(get("owners", "reviewers", default={})),
        "area_owners": [{"paths": e["paths"], "approvers": e["approvers"]} for e in get("owners", "paths", default=[])],
        "codeowners": bool(get("owners", "codeowners", default=False)),
        "default_team": get("owners", "default_team"),
    }
    agents = [
        {
            "role": key,
            "steps": roles["roles"][key]["steps"],
            "lanes": roles["roles"][key]["lanes"],
            "writes": docs.role_area(roles["roles"][key]),
            "tier": roles["roles"][key].get("tier"),
            "proactive": key in may_propose,
            "starts_when": roles["roles"][key]["starts_when"],
            "house_standards": [s["name"] for s in standards_for(standards, key, changed)],
        }
        for key in roles["order"]
    ]
    return {
        "mission": get("mission"),
        "goal": get("goal"),
        "proactive_roles": sorted(may_propose),
        "unknown_proactive_roles": sorted(may_propose - set(roles["roles"])),
        "humans": humans,
        "agent_accounts": sorted(get("identities", "bots", default=[])),
        "agents": agents,
        "house_standards": standards,
        "unknown_standard_roles": sorted({r for s in standards for r in s["roles"] if r != "*" and r not in roles["roles"]}),
    }


def markdown(r: dict) -> str:
    lines = ["# Owners", ""]
    if r.get("mission"):
        lines += [f"**Mission:** {r['mission']}", ""]
    lines += [f"**Goal:** {r['goal'] or '_not set_ (`goal` in .aidd/config.toml)'}", ""]
    h = r["humans"]
    lines += ["## Humans: they decide", "", "| Decides | Who |", "| --- | --- |"]
    lines.append(f"| Spec approval and Merge approval | {', '.join(h['approvers']) or '_nobody named_'} |")
    for pool, members in sorted(h["specialist_pools"].items()):
        lines.append(f"| specialist review: {pool} | {', '.join(members)} |")
    for e in h["area_owners"]:
        lines.append(f"| owners of {', '.join(e['paths'])} | {', '.join(e['approvers'])} |")
    if h["codeowners"]:
        lines.append("| owners of CODEOWNERS areas | the base branch's CODEOWNERS |")
    lines += ["", "## Agents: they do the work, and never approve", ""]
    if r["agent_accounts"]:
        lines += [f"Agent accounts: {', '.join(r['agent_accounts'])}.", ""]
    lines += ["| Role | Steps | Lanes | Writes | Model tier | Proposes work |", "| --- | --- | --- | --- | --- | --- |"]
    for a in r["agents"]:
        lines.append(
            f"| `{a['role']}` | {', '.join(a['steps'])} | {', '.join(a['lanes'])} | {a['writes']} | {a['tier']} | {'yes' if a['proactive'] else 'no'} |"
        )
    lines += house_standards_markdown(r)
    if r["unknown_proactive_roles"]:
        lines += ["", f"Unknown roles in agents.proactive_roles: {', '.join(r['unknown_proactive_roles'])}."]
    return "\n".join(lines) + "\n"


def house_standards_markdown(r: dict) -> list[str]:
    """The house standards by role: what each agent reads before its step, and whether a test enforces it."""
    standards = r.get("house_standards") or []
    if not standards:
        return []
    lines = [
        "",
        "## House standards: read before your step",
        "",
        "Before a step, an agent reads the house standards listed for its role whose `Load when` matches the change.",
        "",
        "| Role | Standard | Document | Load when | Enforcement |",
        "| --- | --- | --- | --- | --- |",
    ]
    groups = [("every role", [s for s in standards if "*" in s["roles"]])]
    for role in [a["role"] for a in r["agents"]] + list(r.get("unknown_standard_roles", [])):
        groups.append((f"`{role}`", [s for s in standards if role in s["roles"] and "*" not in s["roles"]]))
    for who, items in groups:
        for s in items:
            when = ", ".join(f"`{p}`" for p in s["when_changed"]) or "every change"
            how = s["enforcement"]
            if s["unknown_tests"]:
                how += f" (no `[[tests]]` entry named {', '.join(s['unknown_tests'])})"
            lines.append(f"| {who} | `{s['name']}` | [{s['path']}]({s['path']}) | {when} | {how} |")
    if r.get("unknown_standard_roles"):
        lines += ["", f"Unknown roles in standards: {', '.join(r['unknown_standard_roles'])}."]
    return lines
