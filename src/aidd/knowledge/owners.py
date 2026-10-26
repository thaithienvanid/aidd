"""Who decides and who does the work: every human who approves, and every agent role with what it may write.

A team of humans and agents breaks down in predictable ways: nobody knows who owns a decision, people run
private agents on the side and split the context, and agents start work nobody asked for. `aidd owners`
answers the first from the repository itself, and `agents.proactive_roles` bounds the last. Whether the
team is ready to work this way (the work written down, owners named, the same tools for everyone, a rubric,
a written goal) is part of `aidd doctor`.

The team's own rules and its copies of library standards live in `standards`, each opinionated (the default) or
industry, and each a document the named roles read before their step when the change touches its `when_changed`
paths. `aidd owners --json` lists them per role with their type, so an agent loads exactly the ones that apply.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.kernel import globs
from aidd.knowledge import role_text, team_registry

DEFAULT_PROACTIVE_ROLES = ("product-manager", "agile-coach", "sre")


def proactive_roles(cfg: config.Config | None) -> list[str]:
    """The agent roles that may suggest work nobody asked for: always as a draft Spec with `suggested_by =
    "agent:<role>"`, which stays a draft until a person records `triage` (see workitems.triage_errors)."""
    configured = cfg.get("agents", "proactive_roles") if cfg else None
    return list(DEFAULT_PROACTIVE_ROLES) if configured is None else list(configured)


def config_standards(cfg: config.Config | None) -> list[dict]:
    """The standards of `standards`, each with its type and marked enforced (by named `tests`) or guidance."""
    if cfg is None:
        return []
    suite = {t.get("name") for t in cfg.get("tests", default=[]) or []}
    out = []
    for s in cfg.standards:
        enforced = list(s.get("enforced_by", []))
        out.append(
            {
                "name": s["name"],
                "type": s.get("type", "opinionated"),
                "fills": list(s.get("fills", [])),
                "library_id": (s.get("from_library") or {}).get("id"),
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
    """The standards a role reads before its step: those naming the role (or `*`) whose `when_changed`
    matches a changed path. With no paths given, every standard the role names."""

    def applies(s: dict) -> bool:
        if "*" not in s["roles"] and role not in s["roles"]:
            return False
        return changed is None or not s["when_changed"] or any(globs.match_any(s["when_changed"], p) for p in changed)

    return [s for s in standards if applies(s)]


def installed_roles(root: Path | None) -> set[str]:
    """The roles installed here: each `aidd init --team` agent file in `.claude/agents/` when there are any, else every
    role (the aidd-team plugin carries them all)."""
    everyone = set(team_registry.roles()["order"])
    folder = root / ".claude" / "agents" if root else None
    found = {p.stem.removeprefix(config.TEAM_PREFIX) for p in folder.glob(f"{config.TEAM_PREFIX}*.md")} if folder and folder.is_dir() else set()
    return found & everyone or everyone


def owners_view(cfg: config.Config | None, changed: list[str] | None = None, root: Path | None = None) -> dict:
    roles = team_registry.roles()
    installed = installed_roles(root)
    may_suggest = set(proactive_roles(cfg))
    standards = config_standards(cfg)

    def get(*keys: str, default=None):
        return cfg.get(*keys, default=default) if cfg else default

    humans = {
        "approvers": list(get("owners", "approvers", default=[])),
        "specialist_pools": dict(get("owners", "specialists", default={})),
        "area_owners": [{"paths": e["paths"], "approvers": e["approvers"]} for e in get("owners", "paths", default=[])],
        "codeowners": bool(get("owners", "codeowners", default=False)),
        "default_owner_team": get("owners", "default_owner_team"),
    }
    agents = [
        {
            "role": key,
            "steps": roles["roles"][key]["steps"],
            "lanes": roles["roles"][key]["lanes"],
            "writes": role_text.role_area(roles["roles"][key]),
            "tier": roles["roles"][key].get("tier"),
            "proactive": key in may_suggest,
            "starts_when": roles["roles"][key]["starts_when"],
            "standards": [s["name"] for s in standards_for(standards, key, changed)],
            "installed": key in installed,
            "fallback": roles["roles"][key].get("fallback"),
        }
        for key in roles["order"]
    ]
    return {
        "mission": get("mission"),
        "goal": get("goal"),
        "proactive_roles": sorted(may_suggest),
        "unknown_proactive_roles": sorted(may_suggest - set(roles["roles"])),
        "humans": humans,
        "agent_accounts": sorted(get("identities", "bots", default=[])),
        "agents": agents,
        "standards": standards,
        "unknown_standard_roles": sorted({r for s in standards for r in s["roles"] if r != "*" and r not in roles["roles"]}),
        "project": config.effective_project(cfg, changed),
    }


def owners_markdown(r: dict) -> str:
    lines = ["# Owners", ""]
    if r.get("mission"):
        lines += [f"**Mission:** {r['mission']}", ""]
    lines += [f"**Goal:** {r['goal'] or '_not set_ (`goal` in .aidd/config.yaml)'}", ""]
    h = r["humans"]
    lines += ["## Humans: they decide", "", "| Decides | Who |", "| --- | --- |"]
    lines.append(f"| Spec approval and Merge approval | {', '.join(h['approvers']) or '_nobody named_'} |")
    for pool, members in sorted(h["specialist_pools"].items()):
        lines.append(f"| specialist Approvers: {pool} | {', '.join(members)} |")
    for e in h["area_owners"]:
        lines.append(f"| owners of {', '.join(e['paths'])} | {', '.join(e['approvers'])} |")
    if h["codeowners"]:
        lines.append("| owners of CODEOWNERS areas | the base branch's CODEOWNERS |")
    lines += ["", "## Agents: they do the work, and never approve", ""]
    if r["agent_accounts"]:
        lines += [f"Agent accounts: {', '.join(r['agent_accounts'])}.", ""]
    lines += ["| Role | Steps | Lanes | Writes | Model tier | Proposes work |", "| --- | --- | --- | --- | --- | --- |"]
    for a in r["agents"]:
        writes = a["writes"] if a["installed"] or not a["fallback"] else f"not installed here: `{a['fallback']}` does its work"
        lines.append(f"| `{a['role']}` | {', '.join(a['steps'])} | {', '.join(a['lanes'])} | {writes} | {a['tier']} | {'yes' if a['proactive'] else 'no'} |")
    lines += standards_markdown(r)
    if r.get("project"):
        lines += ["", *config.project_markdown(r["project"])]
    if r["unknown_proactive_roles"]:
        lines += ["", f"Unknown roles in agents.proactive_roles: {', '.join(r['unknown_proactive_roles'])}."]
    return "\n".join(lines) + "\n"


def standards_markdown(r: dict) -> list[str]:
    """The standards by role: what each agent reads before its step, its type, and whether a test enforces it."""
    standards = r.get("standards") or []
    if not standards:
        return []
    lines = [
        "",
        "## Standards: read before your step",
        "",
        "Before a step, an agent reads the standards listed for its role whose `Load when` matches the change.",
        "",
        "| Role | Standard | Type | Document | Load when | Enforcement |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    groups = [("every role", [s for s in standards if "*" in s["roles"]])]
    for role in [a["role"] for a in r["agents"]] + list(r.get("unknown_standard_roles", [])):
        groups.append((f"`{role}`", [s for s in standards if role in s["roles"] and "*" not in s["roles"]]))
    for who, items in groups:
        for s in items:
            when = ", ".join(f"`{p}`" for p in s["when_changed"]) or "every change"
            how = s["enforcement"]
            if s["unknown_tests"]:
                how += f" (no `tests` entry named {', '.join(s['unknown_tests'])})"
            lines.append(f"| {who} | `{s['name']}` | {s['type']} | [{s['path']}]({s['path']}) | {when} | {how} |")
    if r.get("unknown_standard_roles"):
        lines += ["", f"Unknown roles in standards: {', '.join(r['unknown_standard_roles'])}."]
    return lines
