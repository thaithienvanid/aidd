"""`aidd explain <word>`: what one of aidd's words means and why it matters, read from the data that owns the word. An
action or an area from the risk rules, a route, a stage, a loop step, a gate, or a person's decision, a role, a document type, a
status, a profile, a finding code, a step code, or a term of the glossary. Nothing here restates a fact; each answer quotes its source and names it.

The risk rules in force depend on the repository's config, which the `risk` package reads, so the caller passes them in
as `RiskFacts`; with none, the answer reads the built-in rules alone."""

from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from aidd import config
from aidd.kernel import findings, resources, text
from aidd.knowledge import team_registry

# The types of word, in the order an answer lists them and `--list` shows them.
EXPLAIN_TYPES = (
    "action",
    "area",
    "level",
    "route",
    "document_type",
    "stage",
    "loop_step",
    "gate",
    "decision",
    "role",
    "status",
    "profile",
    "finding_code",
    "step_code",
    "term",
)
# The types `aidd explain` answers from their schema's own description: the rows of schemas/item-types.json that say so.
SCHEMA_TYPES = config.types_with("explained_by_schema")
# The parts of an Intent that have a word of their own, each defined in the common schema.
INTENT_PARTS = ("phase", "slice")


@dataclass(frozen=True)
class RiskFacts:
    """The risk rules in force, as the `risk` package reads them: each action's and each area's built-in or config
    description, and the level of the rule that matches it on any branch, with the rule and where it comes from."""

    actions: dict[str, dict] = field(default_factory=dict)  # id -> {"description", "level", "rule", "source"}
    areas: dict[str, dict] = field(default_factory=dict)  # id -> {"description", "level", "rule", "source", "route"}
    profiles: dict[str, list[str]] = field(default_factory=dict)  # profile -> the routes on which it asks for Spec approval


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


def _term_answers() -> Iterator[dict]:
    """The word for each type, such as `action` or `level`, from the description of the schema that owns it, and the three
    levels, from the schema that holds them. Like `stage` and `gate`, a type's word answers as that type."""
    risks = resources.load_json("risks.schema.json")
    said = [sentence.rstrip(".") + "." for sentence in str(risks["description"]).split(". ")]
    levels = risks["$defs"]["level"]["enum"]
    common = _common()
    source = "schemas/risks.schema.json"
    level_sentence = next(s for s in said if s.startswith("A rule sets the level"))
    terms = [
        ("action", next(s for s in said if s.startswith("An action is")), source),
        ("area", next(s for s in said if s.startswith("An area is")), source),
        ("level", f"{level_sentence} A level is {text.series(levels, 'or')}.", source),
        ("route", _first_sentence(common["route"]["description"]), "schemas/common.schema.json"),
        ("profile", _first_sentence(config.profiles()["description"]), "schemas/profiles.json"),
        ("finding_code", _first_sentence(common["finding"]["properties"]["code"]["description"]), "schemas/common.schema.json"),
        ("step_code", _first_sentence(common["step_code"]["description"]), "schemas/common.schema.json"),
    ]
    for name, what, where in terms:
        why = "`aidd risk` gives one with every answer" if name == "level" else f"`aidd explain --list` lists every {name} word"
        yield {"type": name, "name": name, "what": what, "why": why, "source": where}
    for name in levels:
        what = f"A level of a risk rule: {level_meaning(name)}"
        why = "`aidd risk --action <id>` gives the level in force for an action, and `--paths <paths>` for an edit"
        yield {"type": "level", "name": name, "what": what, "why": why, "source": source}


def _risk_answers(risks: RiskFacts) -> Iterator[dict]:
    for name, a in risks.actions.items():
        why = f"{a['rule']} ({a['source']}): {level_meaning(a['level'])}" if a.get("rule") else ""
        yield {"type": "action", "name": name, "what": a["description"], "why": why, "source": "schemas/risks.json"}
    for name, a in risks.areas.items():
        parts = [f"an edit there is {a['level']}: {level_meaning(a['level'])}"] if a.get("level") else []
        parts += [f"a change there takes at least the {a['route']} route"] if a.get("route") not in (None, "minor") else []
        yield {"type": "area", "name": name, "what": a["description"], "why": "; ".join(parts), "source": "schemas/risks.json"}


def _loop_answers() -> Iterator[dict]:
    loop = team_registry.roles()["loop"]
    common = _common()
    words = common["route"]["x-words"]
    for name, meaning in common["route"]["x-meanings"].items():
        what = f'"{words[name]}". {meaning} Its steps: {loop["routes"][name]}.'
        yield {"type": "route", "name": name, "what": what, "why": _first_sentence(common["route"]["description"]), "source": "schemas/common.schema.json"}
    told = " ".join(t for t in loop["loops"].values() if isinstance(t, str)).split(". ")
    for step in loop["steps"]:
        said = [s.rstrip(".") + "." for s in told if re.search(rf"\b{re.escape(step)}\b", s)]
        on = list(dict.fromkeys(f'"{words[route]}"' for route, steps in loop["routes"].items() if step in str(steps)))
        roles = [r for r, spec in team_registry.roles()["roles"].items() if step in (spec.get("steps") or [])]
        why = (f"it runs on {text.series(on, 'and')}" if on else "it runs before the loop or after it") + (
            f", and these roles take it: {text.series(roles, 'and')}" if roles else ""
        )
        yield {"type": "loop_step", "name": step, "what": " ".join(said[:2]), "why": why, "source": "schemas/roles.json"}
    names = text.series([s["name"] for s in loop["stages"]], "and")
    yield {
        "type": "stage",
        "name": "stage",
        "what": f"A group of the loop's steps, said for people: {names}",
        "why": "a Spec stands in one stage at a time, which `aidd status` gives",
        "source": "schemas/roles.json",
    }
    gates = text.series([g["name"] for g in loop["gates"]], "and")
    yield {
        "type": "gate",
        "name": "gate",
        "what": f"A fixed point in the loop where a person decides: {gates}",
        "why": "the agent asks there and acts only on the person's yes",
        "source": "schemas/roles.json",
    }
    for stage in loop["stages"]:
        what = f"A stage of the loop, which groups the {text.series(stage['steps'], 'and')} step{'s' if len(stage['steps']) > 1 else ''}"
        here = [g["name"] for g in loop["gates"] if g["stage"] == stage["name"]]
        why = f"a person decides at {text.series(here, 'and')} here" if here else "no person decides at a fixed point here"
        yield {"type": "stage", "name": stage["name"], "what": what, "why": why, "source": "schemas/roles.json"}
    for gate in loop["gates"]:
        what = f"A gate in the {gate['stage']} stage, before {gate['before']}: a person decides before the work goes on"
        why = f"the agent asks at it, on {text.series([f'`{a}`' for a in gate['actions']], 'or')}, and acts on the person's yes"
        yield {"type": "gate", "name": gate["name"], "what": what, "why": why, "source": "schemas/roles.json"}
    for gate in loop["gates"]:  # each gate is a decision of the person's: the decision right whose `gate` names it (schemas/roles.json)
        name = gate["name"]
        right = next(d for d in loop["decision_rights"] if d.get("gate") == name)
        what = str(right["decision"])
        why = f"Who decides: {right['decided_by']}. On what: {right['basis']}. To undo it: {right['undo']}."
        yield {"type": "decision", "name": name, "what": what[:1].upper() + what[1:], "why": why, "source": "schemas/roles.json"}


def _roles_schema_lifecycle() -> str:
    """What `frozen` and `living` mean, as the team's schema says it."""
    schema = resources.load_json("roles.schema.json")
    docs = schema["properties"]["loop"]["properties"]["documents"]["additionalProperties"]["properties"]
    return str(docs["lifecycle"]["description"])


def _team_answers() -> Iterator[dict]:
    loop = team_registry.roles()["loop"]
    for name, role in team_registry.roles()["roles"].items():
        why = f"It starts when: {_first_sentence(role.get('starts_when', ''))} It hands off: {_first_sentence(role.get('hands_off', ''))}"
        yield {"type": "role", "name": name, "what": _first_sentence(role.get("does", "")), "why": why, "source": "schemas/roles.json"}
    lifecycles = dict(part.split(": ", 1) for part in str(_roles_schema_lifecycle()).rstrip(".").split("; ") if ": " in part)
    for name, doc in loop["documents"].items():
        what = f"The {doc['written_by']} writes it; it lives in {doc['home']}"
        why = f"it is {doc['lifecycle']}: {lifecycles.get(doc['lifecycle'], '')}"
        yield {"type": "document_type", "name": name, "what": what, "why": why, "source": "schemas/roles.json"}
    for name in SCHEMA_TYPES:
        schema_file = config.item_type_rows()[name]["schema"]
        yield {
            "type": "document_type",
            "name": name,
            "what": _first_sentence(resources.load_json(schema_file).get("description", "")),
            "why": "",
            "source": f"schemas/{schema_file}",
        }
    for name in INTENT_PARTS:
        what = f"Part of an Intent: {_first_sentence(_common()[name]['description'])}"
        yield {"type": "document_type", "name": name, "what": what, "why": "", "source": "schemas/common.schema.json"}


def _moves_from(table: dict, status: str) -> str:
    """What the status table (`x-transitions`) says of the moves that leave `status`: where each goes, who moves it, and what moves it."""
    found = [f"`{m['to']}` ({m['who']}: {m['when']})" for m in table["x-transitions"] if status in m["from"]]
    return f"It moves on to {'; '.join(found)}." if found else "No move leaves it."


def _status_answers(asks_on: dict[str, list[str]]) -> Iterator[dict]:
    common = _common()
    groups = common["status_group"]["x-meanings"]
    tables = [(row["noun"], config.status_table(name)) for name, row in config.item_type_rows().items() if "statuses" in row]
    for owner, table in tables:
        for name, meaning in table["x-meanings"].items():
            group = (table.get("x-groups") or {}).get(name)
            why = f"its group is {group}: {groups.get(group, '')}" if group else ""
            why = f"{why} {_moves_from(table, name)}".strip()
            yield {"type": "status", "name": name, "what": f"The status of {owner}: {meaning}", "why": why, "source": "schemas/common.schema.json"}
    for name, profile in config.profiles()["profiles"].items():
        rules = [f"{r['action']}{' on a ' + r['route'] + ' change' if r.get('route') else ''}: {r['level']}" for r in profile.get("rules", [])]
        routes = asks_on.get(name)
        parts = [f"it asks for Spec approval on {' and '.join(routes) or 'no route'}"] if routes is not None else []
        parts += [f"it changes the built-in rules to {'; '.join(rules)}"] if rules else ["it changes none of the built-in rules"]
        why = "; ".join(parts)
        yield {"type": "profile", "name": name, "what": profile["description"], "why": why, "source": "schemas/profiles.json"}


# Who takes a step, as a phrase that follows "and".
_WHO = {"agent": "an agent takes it", "person": "a person takes it", "nobody": "nobody takes it: it waits"}


def _finding_answers() -> Iterator[dict]:
    """Each code a check gives (schemas/findings.json), by its full code: the code in a few words, why it comes, and the next step."""
    for name, row in findings.codes().items():
        yield {
            "type": "finding_code",
            "name": name,
            "what": row["title"],
            "why": f"{row['why']} Next: {row['next']['what']}",
            "source": "schemas/findings.json",
        }


def _step_code_answers() -> Iterator[dict]:
    """Each step `aidd status` gives as the `code` of a next step (`step_code` in the common schema): what moves it on, and who takes it."""
    step = _common()["step_code"]
    for name, meaning in step["x-meanings"].items():
        yield {
            "type": "step_code",
            "name": name,
            "what": meaning,
            "why": f"`aidd status` gives it as the `code` of a next step, and {_WHO[step['x-who'][name]]}",
            "source": "schemas/common.schema.json",
        }


def _glossary_term_answers() -> Iterator[dict]:
    """The glossary terms the skill and the messages use that no other data names (`term` in the common schema)."""
    for name, meaning in _common()["term"]["x-meanings"].items():
        yield {"type": "term", "name": name, "what": meaning, "why": "docs/GLOSSARY.md has the whole meaning", "source": "schemas/common.schema.json"}


def answers(risks: RiskFacts | None = None) -> list[dict]:
    """Every word `aidd explain` knows, each with its type, what it is, why it matters, and the file that owns it, in the
    order of EXPLAIN_TYPES (schemas/explain.schema.json, `matches`)."""
    found = [
        *_term_answers(),
        *_risk_answers(risks or _built_in_risks()),
        *_loop_answers(),
        *_team_answers(),
        *_status_answers(risks.profiles if risks else {}),
        *_finding_answers(),
        *_step_code_answers(),
        *_glossary_term_answers(),
    ]
    return sorted(found, key=lambda a: EXPLAIN_TYPES.index(a["type"]))


def explain(word: str, risks: RiskFacts | None = None) -> list[dict]:
    """The answers for `word`, one per type it names, or [] for a word aidd does not know. A finding code that a command prints
    without its group, such as the `reasons` of `aidd delegate check`, is the code of the one group that holds it."""
    wanted, found = key(word), answers(risks)
    exact = [a for a in found if key(a["name"]) == wanted]
    bare = [a for a in found if a["type"] == "finding_code" and key(a["name"].partition(".")[2]) == wanted]
    return exact or (bare if len(bare) == 1 else [])


def explain_words(risks: RiskFacts | None = None) -> dict[str, list[str]]:
    """Every word `aidd explain` knows, by type, in the order of EXPLAIN_TYPES."""
    out: dict[str, list[str]] = {k: [] for k in EXPLAIN_TYPES}
    for a in answers(risks):
        if a["name"] not in out[a["type"]]:
            out[a["type"]].append(a["name"])
    return out
