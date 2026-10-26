"""The team registry, schemas/roles.json (with its parts: the packs in packs.json, the industry standards in
industry-standards.json), as the docs, the evals, and the agents read it: every standard reference
resolved, each role's loop contract and shared rules, and the model each harness runs for a tier."""

from __future__ import annotations

import functools
import json

from aidd.kernel import resources

# Days between reviews of a standard, by its maturity: the registry's entries (schemas/industry-standards.json) and the library's
# standards share it. An entry's own `review_every_days` overrides it.
REVIEW_EVERY_DAYS = {"established": 365, "emerging": 90}


def standard_edition_text(s: dict) -> str | None:
    """One line for a person: the edition, when it was published, and the notes."""
    head = " ".join(x for x in (s.get("edition"), f"(published {s['published']})" if s.get("published") else None) if x)
    return "; ".join(x for x in (head, s.get("notes")) if x) or None


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


@functools.cache
def roles() -> dict:
    """roles.json with every standard reference resolved against the `standards` object, as the docs and the evals read it.

    `load_json("roles.json")` is the file itself, which the schema validates.
    """
    data = json.loads(json.dumps(resources.load_json("roles.json")))
    table = data.get("standards", {})
    for r in data["roles"].values():
        r["standards"] = [resolve_standard(x, table) for x in r["standards"]]
    for d in data["domains"]:
        d["standards"] = [resolve_standard(x, table) for x in d["standards"]]
    for p in data.get("practices", {}).values():
        p["standards"] = [resolve_standard(x, table) for x in p["standards"]]
    # A contract rule is its text; `contract_applies_to` keeps, in the same order, the roles or steps a scoped rule binds.
    # The shared rules, the hard rules in brief, have the same shape: `shared_rules_applies_to` keeps each scoped rule's
    # roles or steps.
    for name in ("contract", "shared_rules"):
        items = data["loop"].get(name, [])
        data["loop"][name] = [x if isinstance(x, str) else x["rule"] for x in items]
        data["loop"][f"{name}_applies_to"] = [None if isinstance(x, str) else list(x["applies_to"]) for x in items]
    return data


def _scoped_for(key: str, data: dict, name: str) -> list[str]:
    role = data["roles"][key]
    return [
        rule
        for rule, scope in zip(data["loop"][name], data["loop"][f"{name}_applies_to"], strict=True)
        if scope is None or key in scope or set(role["steps"]) & set(scope)
    ]


def contract_for(key: str, data: dict | None = None) -> list[str]:
    """The loop-contract rules that bind role `key`: every unscoped rule, and each scoped one naming the role or one of its steps."""
    return _scoped_for(key, data or roles(), "contract")


def shared_rules_for(key: str, data: dict | None = None) -> list[str]:
    """The hard rules, in brief, that bind role `key`, scoped as the contract is."""
    return _scoped_for(key, data or roles(), "shared_rules")


# A role's `tier` is harness-neutral: it names what the work needs, not who sells it. The team ships
# to 26 harnesses, so the tier is the registry's field and the model each harness runs for it lives
# here, in one place, and nowhere else. A harness with no entry reads the tier and picks its own.
# Claude Code takes an alias (`opus`, `sonnet`, `haiku`, `fable`), `inherit`, or a full model ID in an
# agent's `model:` frontmatter; any other value is not a model it knows. There are two tiers (owner, 2026-10-02):
# `reasoning` decides on the strongest model, and `execution` builds on a mid-size one rather than the session's,
# which is often the strongest, so the roles meant to be cheap are. Sonnet is the smallest model aidd runs an agent
# on in Claude Code. `agents.models` can set `inherit`, or any model by name, per tier or role (agent_models).
MODELS_BY_HARNESS = {
    "claude-code": {"reasoning": "opus", "execution": "sonnet"},
    "codex": {"reasoning": "gpt-6-astra", "execution": "gpt-6-sol"},
}


# What each tier is for, in the order the docs list them.
TIER_MEANING = {
    "reasoning": "decides, designs, or judges where a mistake, or a missing option, is invisible to every later check; the strongest model",
    "execution": "builds, proposes, or runs checks where the tests, the gate, or a person catch the mistake; a mid-size model",
}


# The aidd-team plugin's agent files are Claude Code artifacts, so their `model:` frontmatter is
# derived from this harness. `aidd init --team` writes the same value into a copied agent file.
PLUGIN_HARNESS = "claude-code"


def tier_model(tier: str, harness: str = PLUGIN_HARNESS) -> str | None:
    """The model `harness` runs for `tier`, or None for a harness with no mapping: it reads the tier and picks its own."""
    mapping = MODELS_BY_HARNESS.get(harness)
    return mapping[tier] if mapping else None
