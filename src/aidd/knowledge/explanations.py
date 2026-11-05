"""`aidd explain <word>`: what one of aidd's words means and why it matters, read from the data that owns the word. An
action or an area from the risk rules, a route or a lane, a stage, a loop step, a gate, or a person's decision, a role, a document type, a
status, or a profile. Nothing here restates a fact; each answer quotes its source and names it.

The risk rules in force depend on the repository's config, which the `risk` package reads, so the caller passes them in
as `RiskFacts`; with none, the answer reads the built-in rules alone."""

from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from aidd import config
from aidd.kernel import resources, text
from aidd.knowledge import team_registry

# The kinds of word, in the order an answer lists them and `--list` shows them.
EXPLAIN_KINDS = ("action", "area", "route", "lane", "stage", "loop step", "gate", "decision", "role", "document type", "status", "profile")
# A decision a person makes at a loop step, and the label of its decision right in the loop (schemas/roles.json).
DECISIONS = {"Plan": "D1", "Spec approval": "D2", "Merge approval": "D3"}
WORK_ITEM_TYPES = ("spec", "intent", "proposal", "exploration")
# The parts of an Intent that have a word of their own, each defined in the common schema.
INTENT_PARTS = ("phase", "slice")
# The two levels the Intent replaced, and what each is now, so a person who says the old word finds the new one.
FOLDED_WORDS = {"Epic": "an Epic is now a phase of an Intent", "Initiative": "an Initiative is now an Intent"}
_LABEL = re.compile(r"^D[0-9]+ ")


@dataclass(frozen=True)
class RiskFacts:
    """The risk rules in force, as the `risk` package reads them: each action's and each area's built-in or config
    description, and the level of the rule that matches it on any branch, with the rule and where it comes from."""

    actions: dict[str, dict] = field(default_factory=dict)  # id -> {"description", "level", "rule", "source"}
    areas: dict[str, dict] = field(default_factory=dict)  # id -> {"description", "level", "rule", "source", "route"}


def key(word: str) -> str:
    """A word as a lookup reads it: in any case, with `-`, `_`, and spaces alike, so `in-progress` finds `in_progress`."""
    return " ".join(re.split(r"[-_\s]+", word.strip().casefold()))


def _first_sentence(prose: str) -> str:
    head, dot, _ = str(prose).partition(". ")
    return head + "." if dot else str(prose)


@functools.cache
def _common() -> dict:
    return resources.load_json("common.schema.json")["$defs"]


def level_meaning(level: str) -> str:
    """What a level makes the agent do, as the risk rules' schema says it."""
    found = re.search(rf"\b{re.escape(level)}: ([^.]*)\.", str(resources.load_json("risks.schema.json")["$defs"]["level"]["description"]))
    return found.group(1) if found else ""


def _built_in_risks() -> RiskFacts:
    data = resources.load_json("risks.json")
    return RiskFacts(
        actions={k: {"description": v.get("description", "")} for k, v in data["actions"].items()},
        areas={k: {"description": v.get("description", ""), "route": v.get("route", "minor")} for k, v in data["areas"].items()},
    )


def _risk_answers(risks: RiskFacts) -> Iterator[dict]:
    for name, a in risks.actions.items():
        why = f"{a['rule']} ({a['source']}): {level_meaning(a['level'])}" if a.get("rule") else ""
        yield {"kind": "action", "name": name, "what": a["description"], "why": why, "source": "schemas/risks.json"}
    for name, a in risks.areas.items():
        parts = [f"an edit there is {a['level']}: {level_meaning(a['level'])}"] if a.get("level") else []
        parts += [f"a change there takes at least the {a['route']} route"] if a.get("route") not in (None, "minor") else []
        yield {"kind": "area", "name": name, "what": a["description"], "why": "; ".join(parts), "source": "schemas/risks.json"}


def _loop_answers() -> Iterator[dict]:
    loop = team_registry.roles()["loop"]
    common = _common()
    lanes = common["lane"]["x-meanings"]
    words = common["lane"]["x-words"]
    for name, meaning in common["route"]["x-meanings"].items():
        yield {"kind": "route", "name": name, "what": meaning, "why": _first_sentence(common["route"]["description"]), "source": "schemas/common.schema.json"}
    for name, meaning in lanes.items():
        yield {
            "kind": "lane",
            "name": name,
            "what": f'"{words[name]}". {meaning}',
            "why": _first_sentence(common["lane"]["description"]),
            "source": "schemas/common.schema.json",
        }
    told = " ".join(t for t in loop["loops"].values() if isinstance(t, str)).split(". ")
    for step in loop["steps"]:
        said = [s.rstrip(".") + "." for s in told if re.search(rf"\b{re.escape(step)}\b", s)]
        on = [f'"{words[lane]}"' for lane, text in loop["lanes"].items() if step in str(text)]
        roles = [r for r, spec in team_registry.roles()["roles"].items() if step in (spec.get("steps") or [])]
        why = (f"it runs on {text.series(on, 'and')}" if on else "it runs before the loop or after it") + (
            f", and these roles take it: {text.series(roles, 'and')}" if roles else ""
        )
        yield {"kind": "loop step", "name": step, "what": " ".join(said[:2]), "why": why, "source": "schemas/roles.json"}
    names = text.series([s["name"] for s in loop["stages"]], "and")
    yield {
        "kind": "stage",
        "name": "stage",
        "what": f"A group of the loop's steps, said for people: {names}",
        "why": "a Spec stands in one stage at a time, which `aidd status` gives",
        "source": "schemas/roles.json",
    }
    gates = text.series([g["name"] for g in loop["gates"]], "and")
    yield {
        "kind": "gate",
        "name": "gate",
        "what": f"A fixed point in the loop where a person decides: {gates}",
        "why": "the agent asks there and acts only on the person's yes",
        "source": "schemas/roles.json",
    }
    for stage in loop["stages"]:
        what = f"A stage of the loop, which groups the {text.series(stage['steps'], 'and')} step{'s' if len(stage['steps']) > 1 else ''}"
        here = [g["name"] for g in loop["gates"] if g["stage"] == stage["name"]]
        why = f"a person decides at {text.series(here, 'and')} here" if here else "no person decides at a fixed point here"
        yield {"kind": "stage", "name": stage["name"], "what": what, "why": why, "source": "schemas/roles.json"}
    for gate in loop["gates"]:
        what = f"A gate in the {gate['stage']} stage, before {gate['before']}: a person decides before the work goes on"
        why = f"the agent asks at it, on {text.series([f'`{a}`' for a in gate['actions']], 'or')}, and acts on the person's yes"
        yield {"kind": "gate", "name": gate["name"], "what": what, "why": why, "source": "schemas/roles.json"}
    for name, label in DECISIONS.items():
        right = next(d for d in loop["decision_rights"] if str(d["decision"]).startswith(f"{label} "))
        what = _LABEL.sub("", str(right["decision"]))
        why = f"Who decides: {right['decided_by']}. On what: {right['evidence']}. To undo it: {right['undo']}."
        yield {"kind": "decision", "name": name, "what": what[:1].upper() + what[1:], "why": why, "source": "schemas/roles.json"}


def _roles_schema_lifecycle() -> str:
    """What `frozen` and `living` mean, as the team's schema says it."""
    schema = resources.load_json("roles.schema.json")
    docs = schema["properties"]["loop"]["properties"]["documents"]["additionalProperties"]["properties"]
    return str(docs["lifecycle"]["description"])


def _team_answers() -> Iterator[dict]:
    loop = team_registry.roles()["loop"]
    for name, role in team_registry.roles()["roles"].items():
        why = f"It starts when: {_first_sentence(role.get('starts_when', ''))} It hands off: {_first_sentence(role.get('hands_off', ''))}"
        yield {"kind": "role", "name": name, "what": _first_sentence(role.get("does", "")), "why": why, "source": "schemas/roles.json"}
    lifecycles = dict(part.split(": ", 1) for part in str(_roles_schema_lifecycle()).rstrip(".").split("; ") if ": " in part)
    for name, doc in loop["documents"].items():
        what = f"The {doc['owner']} writes it; it lives in {doc['home']}"
        why = f"it is {doc['lifecycle']}: {lifecycles.get(doc['lifecycle'], '')}"
        yield {"kind": "document type", "name": name, "what": what, "why": why, "source": "schemas/roles.json"}
    for name in WORK_ITEM_TYPES:
        schema = resources.load_json(f"{name}.schema.json")
        yield {
            "kind": "document type",
            "name": name,
            "what": _first_sentence(schema.get("description", "")),
            "why": "",
            "source": f"schemas/{name}.schema.json",
        }
    for name, now in FOLDED_WORDS.items():
        yield {
            "kind": "document type",
            "name": name,
            "what": f"A word aidd no longer uses: {now}",
            "why": "`aidd upgrade` folds its files into an Intent",
            "source": "schemas/intent.schema.json",
        }
    for name in INTENT_PARTS:
        what = f"Part of an Intent: {_first_sentence(_common()[name]['description'])}"
        yield {"kind": "document type", "name": name, "what": what, "why": "", "source": "schemas/common.schema.json"}


def _status_answers() -> Iterator[dict]:
    common = _common()
    groups = common["status_group"]["x-meanings"]
    tables = [("a Spec", common["status"]), ("an Intent", common["intent_status"])]
    tables += [("a proposal", resources.load_json("proposal.schema.json")["properties"]["status"])]
    for owner, table in tables:
        for name, meaning in table["x-meanings"].items():
            group = (table.get("x-groups") or {}).get(name)
            why = f"its group is {group}: {groups.get(group, '')}" if group else ""
            yield {"kind": "status", "name": name, "what": f"The status of {owner}: {meaning}", "why": why, "source": "schemas/common.schema.json"}
    for name, profile in config.profiles()["profiles"].items():
        routes = profile.get("spec_approval_routes") or []
        why = f"it asks for Spec approval on the {' and '.join(routes)} route{'s' if len(routes) > 1 else ''}" if routes else "it never asks for Spec approval"
        yield {"kind": "profile", "name": name, "what": profile["description"], "why": why, "source": "schemas/profiles.json"}


def answers(risks: RiskFacts | None = None) -> list[dict]:
    """Every word `aidd explain` knows, each with its kind, what it is, why it matters, and the file that owns it, in the
    order of EXPLAIN_KINDS (schemas/explain.schema.json, `matches`)."""
    found = [*_risk_answers(risks or _built_in_risks()), *_loop_answers(), *_team_answers(), *_status_answers()]
    return sorted(found, key=lambda a: EXPLAIN_KINDS.index(a["kind"]))


def explain(word: str, risks: RiskFacts | None = None) -> list[dict]:
    """The answers for `word`, one per kind it names, or [] for a word aidd does not know."""
    wanted = key(word)
    return [a for a in answers(risks) if key(a["name"]) == wanted]


def explain_words(risks: RiskFacts | None = None) -> dict[str, list[str]]:
    """Every word `aidd explain` knows, by kind, in the order of EXPLAIN_KINDS."""
    out: dict[str, list[str]] = {k: [] for k in EXPLAIN_KINDS}
    for a in answers(risks):
        if a["name"] not in out[a["kind"]]:
            out[a["kind"]].append(a["name"])
    return out
