"""The tables that restate a schema: a config or Spec schema's fields, a vocabulary, the status groups,
and the profiles.
"""

from __future__ import annotations

import json

from aidd import config, risk
from aidd.docsgen import blocks
from aidd.kernel import json_schema, resources, retired_names

# The schema node each `fields:<key>` block documents: a file, and the path inside it.
FIELD_SCHEMAS = {
    **{k: (f"{k}.schema.json", []) for k in ("spec", "config", "evidence", "intent", "proposal")},
    **{k: ("spec.schema.json", ["$defs", k]) for k in ("task", "outcome", "triage", "doc", "flag", "deprecation")},
    **{k: ("common.schema.json", ["$defs", k]) for k in ("risk", "tests", "test_command", "emergency", "observe", "phase", "planned_spec")},
    **{
        f"config-{k}": ("config.schema.json", ["properties", k])
        for k in ("owners", "agents", "limits", "preview", "delegation", "mcp", "docs", "standards_policy", "project")
    },
    **{f"config-{k}": ("config.schema.json", ["properties", k, "items"]) for k in ("extends", "standards")},
    "config-development_teams": ("config.schema.json", ["properties", "development_teams", "additionalProperties"]),
    **{f"risks-{k}": ("risks.schema.json", ["$defs", k]) for k in ("risks", "area", "action", "rule")},
    "standard": ("standard.schema.json", []),
    "stack": ("stack.schema.json", []),
    "config-limits-retrospective_every": ("config.schema.json", ["properties", "limits", "properties", "retrospective_every"]),
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


def schema_node(schema_name: str, path: list[str]) -> dict:
    node = resources.load_json(schema_name)
    for p in path:
        node = node[p]
    return node


def _deref(s: dict, base: str) -> tuple[dict, str]:
    return json_schema.resolve_ref(s["$ref"], base) if "$ref" in s else (s, base)


def _type(s: dict, base: str) -> str:
    if "$ref" in s:
        name = s["$ref"].rsplit("/", 1)[-1]
        target, tbase = _deref(s, base)
        if "enum" in target:
            return f"`{name}`"
        if target.get("type") == "object":
            return f"mapping (`{name}`)"
        return _type(target, tbase)
    if "allOf" in s and not (s.get("type") == "object" and any("$ref" in sub for sub in s["allOf"])):  # a mapping that adds to a shared one is a mapping
        narrowed = [sub for sub in s["allOf"] if "enum" in sub]
        return _type(narrowed[-1] if narrowed else s["allOf"][0], base)
    if "anyOf" in s:
        return " \\| ".join(_type(sub, base) for sub in s["anyOf"])
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
    sch, base = schema_node(schema_name, path), schema_name
    for _ in range(16):
        if "$ref" not in sch:
            return sch, base
        sch, base = _deref(sch, base)
    raise ValueError(f"{schema_name} {'/'.join(path)}: $ref chain too deep")


def _default_words(prop: dict, base: str) -> str:
    """` Default 3.` for a field whose schema gives a `default`, with the range of a number and whom it binds: the schema is the one
    owner of the default, so its description never states it. Nothing for a field with no default."""
    node = _deref(prop, base)[0]
    if "default" not in node:
        return ""
    may = {"lower": "; you may only lower it", "raise": "; you may only raise it"}.get(node.get("x-project-may", ""), "")
    span = f"; it takes {node['minimum']} to {node['maximum']}" if "minimum" in node and "maximum" in node else ""
    return f" Default `{json.dumps(node['default'])}`{span}{may}."


def _field_rows(key: str) -> list[list[str]]:
    sch, base = resolve(*FIELD_SCHEMAS[key])
    required, conditional = set(sch.get("required", [])), _conditions(sch)
    rows = []
    for name, prop in sch.get("properties", {}).items():
        desc = prop.get("description") or _deref(prop, base)[0].get("description", "")
        desc += _default_words(prop, base) if "efault" not in desc else ""
        rows.append([f"`{name}`", _type(prop, base), "yes" if name in required else conditional.get(name, "no"), desc.replace("|", "\\|")])
    return rows


def fields_table(key: str) -> str:
    """A schema's fields; `a~b` lists only the rows of `a` that `b` does not already show word for word."""
    key, _, less = key.partition("~")
    shown = _field_rows(less) if less else []
    return blocks.markdown_table("Field | Type | Required | Meaning", [r for r in _field_rows(key) if r not in shown])


def vocab_table(name: str) -> str:
    """A vocabulary's tokens and meanings: a `$defs` entry of the common schema, or `proposal_status`."""
    d = schema_node("proposal.schema.json", ["properties", "status"]) if name == "proposal_status" else schema_node("common.schema.json", ["$defs", name])
    return blocks.markdown_table("Token | Meaning", ([f"`{v}`", d.get("x-meanings", {}).get(v, "")] for v in d["enum"]))


def transitions_table(item_type: str) -> str:
    """Each move of a work item's status (`x-transitions` of its status table): the status it starts in, then each move, with
    who makes it, what moves it, and the fields it leaves set."""
    table = config.status_table(item_type)
    start = table["x-initial"]
    rows = [["new", f"`{start['status']}`", start["who"], start["when"], ""]]
    for move in config.status_transitions(item_type):
        rows.append(
            [
                ", ".join(f"`{s}`" for s in move["from"]),
                f"`{move['to']}`",
                move["who"],
                move["when"].replace("|", "\\|"),
                ", ".join(f"`{f}`" for f in move.get("requires", [])),
            ]
        )
    return blocks.markdown_table("From | To | Who | What moves it | Fields set", rows)


def groups_table() -> str:
    """Each status group, with the statuses of each work item type in it, from the schemas' x-groups: a column for each
    work item type of schemas/item-types.json."""
    work_items = config.types_of_form("work_item")
    sources = [config.status_table(t)["x-groups"] for t in work_items]
    group = resources.load_json("common.schema.json")["$defs"]["status_group"]
    rows = ([f"`{g}`", group["x-meanings"][g], *(", ".join(f"`{s}`" for s, x in src.items() if x == g) or "none" for src in sources)] for g in group["enum"])
    return blocks.markdown_table(" | ".join(["Group", "Meaning", *(t.capitalize() for t in work_items)]), rows)


def profiles_table() -> str:
    """Each profile (schemas/profiles.json): what it is for, the routes that ask for Spec approval, and its own rules."""
    data = config.profiles()
    rows = []
    for name in data["order"]:
        prof = data["profiles"][name]
        rules = ", ".join(f"`{r['action']}` {r['level']}{' on ' + r['route'] if r.get('route') else ''}" for r in prof.get("rules", [])) or "the built-in ones"
        rows.append([f"`{name}`", prof["description"], ", ".join(risk.routes_asking_for_spec_approval(name)), rules])
    return blocks.markdown_table("Profile | What it is for | Spec approval asked on | Risk rules", rows)


def retired_names_table() -> str:
    """Each retired name (schemas/retired-names.json): where it stood, what replaced it, and why. A sentence says so while none is retired."""
    now = lambda r: "cut" if not r["new"] else "the same key, a new value" if r["new"] == r["old"] else f"`{r['new']}`"  # noqa: E731
    rows = [[r["surface"], f"`{r['old']}`", now(r), r["retired_in"], r["note"]] for r in retired_names.rows()]
    if not rows:
        return "No name is retired yet."
    return blocks.markdown_table("File | Old name | Now | Retired in | Why", rows)


def findings_table(group: str) -> str:
    """Each code of one group of the findings registry (schemas/findings.json), with what it means. A group whose rows say
    whether the person decides adds that column."""
    rows = resources.load_json("findings.json")["groups"][group]["codes"]
    reserved = any("reserved" in r for r in rows.values())
    head = "Code | Title | " + ("Reserved | " if reserved else "") + "Why"
    return blocks.markdown_table(
        head, ([f"`{c}`", r["title"], *(["yes" if r.get("reserved") else "no"] if reserved else []), r["why"]] for c, r in rows.items())
    )


def code_list(xs: list[str]) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"
