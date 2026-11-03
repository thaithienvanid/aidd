"""The tables that restate a schema: a config or Spec schema's fields, a vocabulary, the status groups,
and the profiles.
"""

from __future__ import annotations

from aidd import config
from aidd.docsgen import blocks
from aidd.kernel import json_schema, resources

# The schema node each `fields:<key>` block documents: a file, and the path inside it.
FIELD_SCHEMAS = {
    **{k: (f"{k}.schema.json", []) for k in ("spec", "config", "evidence", "epic", "initiative", "proposal")},
    **{k: ("spec.schema.json", ["$defs", k]) for k in ("task", "outcome", "triage", "doc", "flag", "deprecation", "experiment")},
    **{k: ("common.schema.json", ["$defs", k]) for k in ("relation", "risk", "tests", "test_command", "emergency", "observe")},
    **{f"config-{k}": ("config.schema.json", ["properties", k]) for k in ("owners", "agents", "preview", "docs", "standards_policy", "project")},
    **{f"config-{k}": ("config.schema.json", ["properties", k, "items"]) for k in ("extends", "standards")},
    **{f"risks-{k}": ("risks.schema.json", ["$defs", k]) for k in ("risks", "area", "action", "rule")},
    "standard": ("standard.schema.json", []),
    "stack": ("stack.schema.json", []),
    "config-project-stack": ("config.schema.json", ["properties", "project", "properties", "stack"]),
    "config-project-budget": ("config.schema.json", ["properties", "project", "properties", "budget"]),
    "config-project-defaults": ("config.schema.json", ["properties", "project", "properties", "defaults"]),
    "config-project-compliance": ("config.schema.json", ["properties", "project", "properties", "compliance"]),
    "config-project-compliance-support_period": (
        "config.schema.json",
        ["properties", "project", "properties", "compliance", "properties", "support_period"],
    ),
    "config-project-writing": ("config.schema.json", ["properties", "project", "properties", "writing"]),
    "config-project-rules": ("config.schema.json", ["$defs", "project_rule"]),
    "config-project-waivers": ("config.schema.json", ["$defs", "project_waiver"]),
}


def _node(schema_name: str, path: list[str]) -> dict:
    node = resources.load_json(schema_name)
    for p in path:
        node = node[p]
    return node


def _deref(s: dict, base: str) -> tuple[dict, str]:
    return json_schema._resolve(s["$ref"], base) if "$ref" in s else (s, base)


def _type(s: dict, base: str) -> str:
    if "$ref" in s:
        name = s["$ref"].rsplit("/", 1)[-1]
        target, tbase = _deref(s, base)
        if "enum" in target:
            return f"`{name}`"
        if target.get("type") == "object":
            return f"mapping (`{name}`)"
        return _type(target, tbase)
    if "allOf" in s:
        narrowed = [sub for sub in s["allOf"] if "enum" in sub]
        return _type(narrowed[-1] if narrowed else s["allOf"][0], base)
    if "const" in s:
        return f'`"{s["const"]}"`'
    if "enum" in s:
        return " \\| ".join(f"`{v}`" for v in s["enum"])
    t = s.get("type")
    if t == "array":
        return f"list of {_type(s.get('items', {}), base)}"
    if t == "object":
        return "mapping"
    if isinstance(t, list):
        return " or ".join(t)
    return t or "any"


def _absent(negated: dict) -> str:
    """What a `not` condition says is absent: `spec`, or `spec` and `specs` for a `not` of `anyOf` required keys."""
    keys = [k for alt in negated.get("anyOf", [negated]) for k in alt.get("required", [])[:1]]
    return " and ".join(f"`{k}`" for k in keys) + (" are" if len(keys) > 1 else " is")


def _conditions(sch: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub in sch.get("allOf", []):
        cond = sub.get("if", {})
        then = sub.get("then", {})
        props = cond.get("properties", {})
        if props and then.get("required"):
            label = "when " + " and ".join(f"{key} is `{spec.get('const')}`" for key, spec in props.items())
            if "not" in cond:
                label += f" and {_absent(cond['not'])} absent"
            for r in then["required"]:
                out.setdefault(r, label)
        elif "not" in cond and then.get("required"):
            for r in then["required"]:
                out[r] = f"when {_absent(cond['not'])} absent"
    return out


def resolve(schema_name: str, path: list[str]) -> tuple[dict, str]:
    """The schema node at `path`, following `$ref` (also across files) until it is a real definition."""
    sch, base = _node(schema_name, path), schema_name
    for _ in range(16):
        if "$ref" not in sch:
            return sch, base
        sch, base = _deref(sch, base)
    raise ValueError(f"{schema_name} {'/'.join(path)}: $ref chain too deep")


def _field_rows(key: str) -> list[list[str]]:
    sch, base = resolve(*FIELD_SCHEMAS[key])
    required, conditional = set(sch.get("required", [])), _conditions(sch)
    rows = []
    for name, prop in sch.get("properties", {}).items():
        desc = prop.get("description") or _deref(prop, base)[0].get("description", "")
        rows.append([f"`{name}`", _type(prop, base), "yes" if name in required else conditional.get(name, "no"), desc.replace("|", "\\|")])
    return rows


def fields_table(key: str) -> str:
    """A schema's fields; `a~b` lists only the rows of `a` that `b` does not already show word for word."""
    key, _, less = key.partition("~")
    shown = _field_rows(less) if less else []
    return blocks.markdown_table("Field | Type | Required | Meaning", [r for r in _field_rows(key) if r not in shown])


def vocab_table(name: str) -> str:
    """A vocabulary's tokens and meanings: a `$defs` entry of the common schema, or `proposal_status`."""
    d = _node("proposal.schema.json", ["properties", "status"]) if name == "proposal_status" else _node("common.schema.json", ["$defs", name])
    return blocks.markdown_table("Token | Meaning", ([f"`{v}`", d.get("x-meanings", {}).get(v, "")] for v in d["enum"]))


def groups_table() -> str:
    """Each status group, with the Spec, Epic and Initiative, and proposal statuses in it, from the schemas' x-groups."""
    common = resources.load_json("common.schema.json")["$defs"]
    sources = [
        common["status"]["x-groups"],
        common["container_status"]["x-groups"],
        resources.load_json("proposal.schema.json")["properties"]["status"]["x-groups"],
    ]
    group = common["status_group"]
    rows = ([f"`{g}`", group["x-meanings"][g], *(", ".join(f"`{s}`" for s, x in src.items() if x == g) or "none" for src in sources)] for g in group["enum"])
    return blocks.markdown_table("Group | Meaning | Spec | Epic and Initiative | Proposal", rows)


def profiles_table() -> str:
    """Each profile (schemas/profiles.json): what it is for, the routes that ask for Spec approval, and its own rules."""
    data = config.profiles()
    rows = []
    for name in data["order"]:
        prof = data["profiles"][name]
        rules = ", ".join(f"`{r['action']}` {r['level']}" for r in prof.get("rules", [])) or "the built-in ones"
        rows.append([f"`{name}`", prof["description"], ", ".join(prof["spec_approval_routes"]), rules])
    return blocks.markdown_table("Profile | What it is for | Spec approval asked on | Risk rules", rows)


def _codes(xs: list[str]) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"
