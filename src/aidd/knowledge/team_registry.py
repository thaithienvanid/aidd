"""The team registry, schemas/roles.json (with its parts: the packs in packs.json, the industry standards in
industry-standards.json), as the docs, the evals, and the agents read it: every standard reference
resolved, each role's loop contract and shared rules, and the model each harness runs for a tier."""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, resources
from aidd.kernel import text as kernel_text

# Days between reviews of a standard, by its maturity: the registry's entries (schemas/industry-standards.json) and the library's
# standards share it. An entry's own `review_every_days` overrides it.
REVIEW_EVERY_DAYS = {"established": 365, "emerging": 90}
# The maturity of a registry entry that names none: the schema owns it (`default` of `$defs/maturity`), and docs/STANDARDS.md
# states it (tests/test_knowledge_maintenance.py checks).
DEFAULT_MATURITY: str = resources.load_json("roles.schema.json")["$defs"]["maturity"]["default"]


def standard_edition_text(standard: dict) -> str | None:
    """One line for a person: the edition, when it was published, and the notes."""
    head = " ".join(x for x in (standard.get("edition"), f"(published {standard['published']})" if standard.get("published") else None) if x)
    return "; ".join(x for x in (head, standard.get("notes")) if x) or None


def resolve_standard(ref, table: dict) -> dict:
    """A role's or pack's standard reference as the full entry: its id, `as` wording in place of the name, and one `edition` line."""
    sid, as_ = (ref, None) if isinstance(ref, str) else (ref["id"], ref.get("as"))
    entry = dict(table[sid], id=sid)
    if as_:
        entry["name"] = as_
    text = standard_edition_text(entry)
    if entry.get("edition"):
        entry["release"] = entry["edition"]  # the bare edition, without the publication date and notes
    entry.pop("edition", None)
    if text:
        entry["edition"] = text
    return entry


def skill_ref(slug: str) -> str:
    """The name a team skill is loaded by: `aidd-packs:<slug>` for a domain pack, `aidd-team:<slug>` for any other."""
    is_pack = any(d["slug"] == slug for d in roles()["domains"])
    return f"{config.PACKS_PLUGIN if is_pack else 'aidd-team'}:{slug}"


def found_by(slug: str) -> str:
    """How a model reaches a team skill. `name`: a role or the lead names it, so its description is no part of the finding: a
    domain pack, and a practice skill that a role preloads or `file_practices` names. `description`: the model finds it alone from
    the session's listing, which holds the router and every other practice skill."""
    data = roles()
    named = {p for r in data["roles"].values() for p in r.get("preload", [])} | {p for f in data["loop"].get("file_practices", []) for p in f["practices"]}
    is_pack = any(d["slug"] == slug for d in data["domains"])
    return "name" if is_pack or slug in named - {CORE_PRELOAD} else "description"


def lists_description(text: str) -> bool:
    """Whether Claude Code puts a skill's or command's description in the model's context. With `disable-model-invocation: true` in
    its front matter it does not, and the model cannot load the skill on its own either (config.LISTING_FACTS)."""
    try:
        front = documents.split_front_matter(text)[0]
    except documents.DocumentError:
        return True
    return front.get("disable-model-invocation") is not True


def skill_folders() -> list[Path]:
    """Every team skill's folder, in name order: the router and the practice skills of the aidd-team plugin, and the domain
    packs of the aidd-packs plugin."""
    folders = (p for plugin in ("team", "packs") for p in (resources.data_dir(plugin) / "skills").iterdir() if p.is_dir())
    return sorted(folders, key=lambda p: p.name)


# A limit's default in a text of roles.json: `{{limit:max_task_retries}}` reads `limits.max_task_retries` in the config schema, its one owner.
LIMIT_MARK = re.compile(r"\{\{limit:([a-z_.]+)\}\}")


def with_limits(data: dict) -> dict:
    """`data` with every `{{limit:<name>}}` in its texts replaced by that limit's default in the config schema, so no text states a
    number the schema owns. A name the schema lacks raises KeyError."""
    return json.loads(LIMIT_MARK.sub(lambda m: str(config.setting_default(f"limits.{m[1]}")), json.dumps(data)))


@functools.cache
def roles() -> dict:
    """roles.json with every standard reference resolved against the `standards` object, as the docs and the evals read it.

    `load_json("roles.json")` is the file itself, which the schema validates.
    """
    data = with_limits(resources.load_json("roles.json"))
    table = data.get("standards", {})
    for r in data["roles"].values():
        r["standards"] = [resolve_standard(x, table) for x in r["standards"]]
    for d in data["domains"]:
        d["standards"] = [resolve_standard(x, table) for x in d["standards"]]
    for p in data.get("practices", {}).values():
        p["standards"] = [resolve_standard(x, table) for x in p["standards"]]
    # A contract rule is its text; `contract_applies_to` keeps, in the same order, the roles or steps a scoped rule binds.
    # The shared rules, the hard rules in short, have the same shape: `shared_rules_applies_to` keeps each scoped rule's
    # roles or steps.
    contract_items = data["loop"].get("contract", [])
    for name in ("contract", "shared_rules"):
        items = data["loop"].get(name, [])
        data["loop"][name] = [x if isinstance(x, str) else x["rule"] for x in items]
        data["loop"][f"{name}_applies_to"] = [x.get("applies_to") if isinstance(x, dict) else None for x in items]
        data["loop"][f"{name}_needs"] = [x.get("needs") if isinstance(x, dict) else None for x in items]
        data["loop"][f"{name}_in_core_skill"] = [x.get("in_core_skill") if isinstance(x, dict) else None for x in items]
    data["loop"]["contract_reviewed_as"] = [x.get("reviewed_as") if isinstance(x, dict) else None for x in contract_items]
    # The lead names, in each role's prompt, the practice skills for the files the role writes; `file_practices` owns that list.
    named = "; ".join(f"for {x['files']}, " + " and ".join(f"`{p}`" for p in x["practices"]) for x in data["loop"].get("file_practices", []))
    data["loop"]["lead"] = [x.replace("FILE_PRACTICES", named) for x in data["loop"]["lead"]]
    # A decision right that is a gate holds its gate's name once, in `gate`; the loaded text names the gate before what is decided.
    for right in data["loop"]["decision_rights"]:
        if right.get("gate"):
            right["decision"] = f"{right['gate']}: {right['decision']}"
    # A role that starts on named areas owns that list once (`starts_on_areas`); its `starts_when` says STARTS_ON_AREAS.
    for r in data["roles"].values():
        if r.get("starts_on_areas"):
            r["starts_when"] = r["starts_when"].replace("STARTS_ON_AREAS", areas_phrase(r["starts_on_areas"]))
    return data


def areas_phrase(areas: list[str]) -> str:
    """A list of area names as one phrase, each in code marks: `` `auth`, `secrets`, or `ai` ``."""
    return kernel_text.series([f"`{a}`" for a in areas], "or")


def can_act_on(role: dict, need: str | None) -> bool:
    """Whether `role` has what a rule `needs`: the harness's own tools (a role with only `mcp_tools`, the delegate, has none),
    or a write area. A rule with no need binds every role."""
    return {None: True, "tools": not role.get("mcp_tools"), "write": bool(role["writes"])}[need]


def _scoped_for(key: str, data: dict, name: str) -> list[str]:
    role = data["roles"][key]
    needs = data["loop"].get(f"{name}_needs") or [None] * len(data["loop"][name])
    return [
        rule
        for rule, scope, need in zip(data["loop"][name], data["loop"][f"{name}_applies_to"], needs, strict=True)
        if (scope is None or key in scope or set(role["steps"]) & set(scope)) and can_act_on(role, need)
    ]


# The name of the aidd skill in a role's `preload` (11 KB into every run): a role that writes a Spec, an Intent, or tests,
# where the Spec format and the frozen-test rules are the work itself, lists it.
CORE_PRELOAD = "aidd"


def _carried_for(key: str, data: dict, name: str) -> list[str]:
    """The rules of `name` that bind role `key`, minus the ones the aidd skill gives it: a role that preloads the skill reads
    a rule with `in_core_skill` there, so its agent file leaves the rule out; any other role carries every rule that binds it."""
    given = CORE_PRELOAD in data["roles"][key].get("preload", [])
    proofs = dict(zip(data["loop"][name], data["loop"].get(f"{name}_in_core_skill") or [None] * len(data["loop"][name]), strict=True))
    binding = shared_rules_for if name == "shared_rules" else contract_for  # one reading of which rules bind a role
    return [x for x in binding(key, data) if not (given and proofs[x])]


def contract_for(key: str, data: dict | None = None) -> list[str]:
    """The loop-contract rules that bind role `key`: every unscoped rule, and each scoped one naming the role or one of its steps."""
    return _scoped_for(key, data or roles(), "contract")


def reviewed_rules_for(key: str, data: dict | None = None) -> list[tuple[str, str]]:
    """(the rule's own text, how role `key` applies it) for each contract rule that names `key` in its `reviewed_as`: the rules
    its authors keep and the role checks, so the role reads one text of the rule."""
    data = data or roles()
    reviewed = data["loop"].get("contract_reviewed_as") or [None] * len(data["loop"]["contract"])
    return [(rule, how["as"]) for rule, how in zip(data["loop"]["contract"], reviewed, strict=True) if how and key in how["roles"]]


def shared_rules_for(key: str, data: dict | None = None) -> list[str]:
    """The hard rules, in short, that bind role `key`, scoped as the contract is."""
    return _scoped_for(key, data or roles(), "shared_rules")


def shared_rules_carried_for(key: str, data: dict | None = None) -> list[str]:
    """The hard rules, in short, that role `key`'s agent file carries: the ones that bind it, less the ones its preloaded aidd skill gives."""
    return _carried_for(key, data or roles(), "shared_rules")


def contract_carried_for(key: str, data: dict | None = None) -> list[str]:
    """The loop-contract rules that role `key`'s agent file carries: the ones that bind it, less the ones its preloaded aidd skill gives."""
    return _carried_for(key, data or roles(), "contract")


# A role's `tier` is harness-neutral: it names what the work needs, not who sells it. The team ships
# to every harness in `aidd.config.HARNESSES`, so the tier is the registry's field and the model each harness runs for it lives
# here, in one place, and nowhere else. A harness with no entry reads the tier and picks its own.
# Claude Code takes an alias (`opus`, `sonnet`, `haiku`, `fable`), `inherit`, or a full model ID in an
# agent's `model:` frontmatter; any other value is not a model it knows. There are two tiers:
# `reasoning` decides on the strongest model, and `execution` builds on a mid-size one rather than the session's,
# which is often the strongest, so the roles meant to be cheap are. Sonnet is the smallest model aidd runs an agent
# on in Claude Code. `agents.models` can set `inherit`, or any model by name, per tier or role (agent_models).
MODELS_BY_HARNESS = {
    "claude-code": {"reasoning": "opus", "execution": "sonnet"},
}


# The reasoning effort each tier runs at, in the levels Claude Code's agent
# `effort:` takes (the config schema's `agents.effort` enum). A role that decides or judges thinks hardest; one that builds inside a clear Task, a step lower.
# `agents.effort` sets any level per tier or role; Claude Code's CLAUDE_CODE_EFFORT_LEVEL still overrides both.
EFFORT_BY_TIER = {"reasoning": "xhigh", "execution": "high"}


# What each tier is for, in the order the docs list them.
TIER_MEANING = {
    "reasoning": "decides, designs, or judges where a mistake, or a missing option, is invisible to every later check; the strongest model",
    "execution": "builds, proposes, or runs checks where the tests, the reviewer, or a person catch the mistake; a mid-size model",
}


# The aidd-team plugin's agent files are Claude Code artifacts, so their `model:` frontmatter is
# derived from this harness. `aidd init --aidd-team` writes the same value into a copied agent file.
PLUGIN_HARNESS = "claude-code"


def tier_model(tier: str, harness: str = PLUGIN_HARNESS) -> str | None:
    """The model `harness` runs for `tier`, or None for a harness with no mapping: it reads the tier and picks its own."""
    mapping = MODELS_BY_HARNESS.get(harness)
    return mapping[tier] if mapping else None
