"""What `aidd extensions suggest` prints: the registry's installable extensions that fit this repository, for the
roles that use them. It reads the team registry only; it never installs, since an install changes what the agents can
do, and a person reviews the pin first."""

from __future__ import annotations

from aidd.knowledge import team_registry

# The marketplaces an `install` line may name, and the repository a person adds each from. The official one comes with
# Claude Code; any other is added once before its plugins install.
MARKETPLACES = {"claude-plugins-official": "anthropics/claude-plugins-official", "knowledge-work-plugins": "anthropics/knowledge-work-plugins"}
BUILT_IN = "claude-plugins-official"
PLUGIN_INSTALL = "claude plugin install "  # the lines that name a marketplace; an MCP server's line (`claude mcp add`) names none


def suggestions(stacks: set[str], role: str | None = None) -> list[dict]:
    """Each extension with an `install` line whose `suggest_when` stacks meet `stacks` (or that names none), once per
    install line, with every role that lists it, in the registry's role order. `role` keeps one role's."""
    data = team_registry.roles()
    out: dict[str, dict] = {}
    for name in data["order"]:
        if role and name != role:
            continue
        for e in data["roles"][name].get("extends", []):
            line = e.get("install")
            when = (e.get("suggest_when") or {}).get("stacks")
            if not line or (when and not set(when) & stacks):
                continue
            row = out.setdefault(
                line,
                {
                    "name": e["name"],
                    "tier": e["tier"],
                    "maturity": e.get("maturity", "established"),
                    "capabilities": list(e.get("capabilities", [])),
                    "pin": e.get("pin"),
                    "license": e.get("license"),
                    "install": line,
                    "roles": [],
                    "adds": {},
                },
            )
            row["roles"].append(name)
            row["adds"][name] = e["adds"]
    return list(out.values())


_PART_KEYS = ("name", "tier", "maturity", "capabilities", "telemetry_opt_out", "license", "pin", "source", "install")


def toolsets(role: str | None = None) -> list[dict]:
    """Each role's named toolsets (`toolsets` in the registry), whatever the stacks: what the role uses, the role's
    default with none enabled, any test command, and each extension it installs with its tier, what it can touch,
    its telemetry, pin, and source, as the registry holds them. `role` keeps one role's."""
    data = team_registry.roles()
    rows = []
    for name in data["order"]:
        r = data["roles"][name]
        if role and name != role:
            continue
        by_name = {e["name"]: e for e in r.get("extends", [])}
        for key, spec in r.get("toolsets", {}).items():
            parts = [{k: by_name[n][k] for k in _PART_KEYS if k in by_name[n]} for n in spec["extensions"]]
            rows.append({"role": name, "toolset": key, "default": r.get("toolset_default"), **spec, "parts": parts})
    return rows


def toolsets_text(rows: list[dict]) -> str:
    """The toolsets as a person reads them, after the suggestions: each part with what it can touch, its telemetry, and
    its pin, since a person installs each; empty with none."""
    if not rows:
        return ""
    lines = ["", "Toolsets, whatever the stacks: a person picks one by enabling its parts in this project's settings."]
    for r in rows:
        lines += ["", f"{r['role']}: {r['toolset']}  ({', '.join(r['extensions'])})", f"  {r['uses']}"]
        lines += [f"  with none enabled: {r['default']}"] if r.get("default") else []
        lines += [f"  test command: {r['test_command']}"] if r.get("test_command") else []
        for part in r["parts"]:
            telemetry = "; telemetry always on" if part.get("telemetry_opt_out") is False and "telemetry" in part.get("capabilities", []) else ""
            emerging = ", emerging" if part.get("maturity") == "emerging" else ""
            touches = ", ".join(part.get("capabilities", [])) or "read-only"
            lines.append(f"  - {part['name']}  ({part.get('tier')}{emerging}; {touches}{telemetry}; {part.get('license')}; pin {part.get('pin')})")
            lines.append(f"    {part['install']}" if part.get("install") else f"    source: {part.get('source')}")
    return "\n".join(lines) + "\n"


def suggestions_text(rows: list[dict], stacks: set[str]) -> str:
    """The suggestions as a person reads them: each with its tier, what it can touch, its pin, the roles it serves,
    and the line to install it, after the one sentence that says aidd installs none of them."""
    found = ", ".join(sorted(stacks)) or "none detected"
    head = [
        f"Stacks: {found}. These plugins fit aidd's roles here. aidd installs none of them: each changes what the agents can do,",
        "so a person reads its source at the pin, then runs its install line, and commits the pin through a change.",
    ]
    if not rows:
        return "\n".join([*head, "", "No installable extension in the registry fits this repository."]) + "\n"
    lines = head
    added = sorted({r["install"].rsplit("@", 1)[1] for r in rows if r["install"].startswith(PLUGIN_INSTALL)} - {BUILT_IN})
    if added:
        lines += ["", "Once, to add the marketplaces they come from:", *(f"  claude plugin marketplace add {MARKETPLACES[m]}" for m in added)]
    for r in rows:
        touches = ", ".join(r["capabilities"]) or "read-only"
        emerging = ", emerging" if r["maturity"] == "emerging" else ""
        lines += ["", f"{r['name']}  ({r['tier']}{emerging}; {touches}; {r['license']}; pin {r['pin']})"]
        lines += [f"  {role}: {adds}" for role, adds in r["adds"].items()]
        lines.append(f"  {r['install']}")
    return "\n".join(lines) + "\n"
