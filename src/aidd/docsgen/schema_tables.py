"""The tables that restate a schema: a config or Spec schema's fields, a vocabulary, the status groups, the profiles,
and the baseline rules.
"""

from __future__ import annotations

from aidd import config
from aidd.config import ROUTE_KEYS
from aidd.docsgen import blocks
from aidd.kernel import json_schema, resources

# The schema node each `fields:<key>` block documents: a file, and the path inside it.
FIELD_SCHEMAS = {
    **{k: (f"{k}.schema.json", []) for k in ("spec", "change-request", "config", "evidence", "record", "epic", "initiative", "proposal")},
    **{k: ("spec.schema.json", ["$defs", k]) for k in ("task", "outcome", "triage", "doc", "flag", "deprecation", "experiment")},
    **{k: ("common.schema.json", ["$defs", k]) for k in ("relation", "risk", "tests", "test_command", "emergency", "observe")},
    **{
        f"config-{k}": ("config.schema.json", ["properties", k])
        for k in (
            "owners",
            "targets",
            "agents",
            "policy",
            "observe",
            "preview",
            "gates",
            "limits",
            "identities",
            "evidence",
            "emergency",
            "guard",
            "hooks",
            "autopilot",
        )
    },
    **{f"config-{k}": ("config.schema.json", ["properties", k, "items"]) for k in ("extends", "risk_rules", "standard_changes", "standards")},
    "config-docs": ("config.schema.json", ["properties", "docs"]),
    "config-components": ("config.schema.json", ["properties", "components"]),
    "config-standards_policy": ("config.schema.json", ["properties", "standards_policy"]),
    "standard": ("standard.schema.json", []),
    "stack": ("stack.schema.json", []),
    "config-owners-paths": ("config.schema.json", ["properties", "owners", "properties", "paths", "items"]),
    "config-agents-autonomy": ("config.schema.json", ["properties", "agents", "properties", "autonomy"]),
    "config-guard-held_commands": ("config.schema.json", ["properties", "guard", "properties", "held_commands", "items"]),
    "config-project": ("config.schema.json", ["properties", "project"]),
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


_GATE_ROWS = [
    ("mode", "Mode while the config names none: advisory (the guard and the gate report; no agent decides for a person) or enforce (they block)"),
    ("separation_of_duties", "Approvers must differ from the authors"),
    ("spec_approval_required_routes", "Spec approval on routes"),
    ("specialist_spec_approval", "Specialist pools also approve the Spec on major"),
    ("approvals", "Merge approvals per route"),
    ("specialist_approvals", "Approvals from each specialist pool on major"),
    ("policy_required_routes", "Bound Policy required on routes"),
    ("provenance", "AI provenance"),
    ("red_green", "Red-then-green proof for new behavior"),
    ("standard_changes", "Standard changes allowed"),
    ("observe_required_routes", "Observe block required on routes"),
    ("max_changed_lines", "Changed-line limit per route (standard: its class's own limit; emergency: none)"),
    ("unlinked_authors", "Commit authors with no platform account"),
    ("spec_approval_proof", "Spec approval proven before implementation"),
    ("approval_carry", "A Merge approval carries across a trivial rebase"),
    ("approval_carry_routes", "Routes on which it carries (never emergency)"),
    ("max_open_per_approver", "`limits`: open waits per Approver before `aidd list` warns (0: off; never gated)"),
    ("escalate_after_minutes", "`limits`: minutes before `aidd list` escalates a wait (0: off; never gated)"),
    ("max_in_progress_per_owner", "`limits`: Specs in progress per owner before `aidd list` warns (0: off; never gated)"),
    ("max_in_progress_days", "`limits`: days in progress before `aidd list` flags a Spec as aging (0: off; never gated)"),
    ("max_goal_age_days", "`limits`: days a goal branch lives before `aidd list` and `aidd doctor` warn (0: off; never gated)"),
    ("max_branch_age_days", "`limits`: days a branch with unmerged work lives before `aidd list` and `aidd doctor` warn (0: off; never gated)"),
    ("max_open_branches", "`limits`: branches with unmerged work before `aidd list` and `aidd doctor` warn (0: off; never gated)"),
]
# What a limit no profile sets means while it stays unset: one a config may add.
_UNSET_LIMITS = {
    "max_in_progress_per_owner": "unset (off)",
    "max_in_progress_days": "unset (10)",
    "max_goal_age_days": "unset (7)",
    "max_branch_age_days": "unset (2)",
    "max_open_branches": "unset (3)",
}


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


def _cell(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return ", ".join(v) if v else "none"
    if isinstance(v, dict):
        # Every value, zeros too: `standard 0` says a standard change needs no approval; leaving it out read as if the
        # route did not exist. Routes in their order; a route the profile gives no value stays out, and the label says.
        keys = sorted(v, key=lambda k: (ROUTE_KEYS.index(k) if k in ROUTE_KEYS else len(ROUTE_KEYS), k))
        return ", ".join(f"{k} {v[k]}" for k in keys) if keys else "none"
    return str(v)


def _profile_value(profile: dict, key: str) -> str:
    """A profile's gate, or its limit (`limits`), as a table cell; a limit it leaves unset says what unset means."""
    limits = profile.get("limits") or {}
    return _cell(profile[key]) if key in profile else _cell(limits[key]) if key in limits else _UNSET_LIMITS[key]


def profiles_table() -> str:
    data = config.profiles()
    order = data["order"]
    return blocks.markdown_table(
        "Gate | " + " | ".join(order),
        ([label, *(_profile_value(data["profiles"][p], key) for p in order)] for key, label in _GATE_ROWS),
    )


def _codes(xs: list[str]) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"


def baseline_table() -> str:
    b = config.baseline_data()
    protected = f"<details><summary>{len(b['protected_paths'])} paths</summary>{_codes(b['protected_paths'])}</details>"
    rows = [["protected (cannot be disabled)", "major", "none", protected, "none", "none; also every file a bound Policy or Observe command runs"]]
    rows += [
        [
            f"`{r['name']}`",
            r["route"],
            ", ".join(r["dimensions"]) or "none",
            _codes(r["paths"]),
            _codes(r.get("dependencies", [])),
            _codes(r.get("exclude", [])),
        ]
        for r in b["risk_rules"]
    ]
    return blocks.markdown_table("Rule | Minimum route | Dimensions | Paths | Added dependencies | Excluded", rows)


def baseline_summary() -> str:
    """The built-in rules without their paths (`baseline:summary`), for the agent-facing routes reference: `aidd gate
    --paths` answers for a real path, so the agent never matches globs by hand."""
    b = config.baseline_data()
    rows = [["protected (cannot be disabled)", "major", "none", str(len(b["protected_paths"])), "none"]]
    rows += [
        [f"`{r['name']}`", r["route"], ", ".join(r["dimensions"]) or "none", str(len(r["paths"])), _codes(r.get("dependencies", []))] for r in b["risk_rules"]
    ]
    return blocks.markdown_table("Rule | Minimum route | Dimensions | Paths | Added dependencies", rows)
