"""The data rules, R1 to R6 and V1 to V4, as functions over every schema: what a machine can decide, and the judged lists it cannot.

Each rule takes the loaded schemas and the judged lists and returns its breaks, `{where: why}`, where `where` is
`<schema file>#<pointer>`. tests/test_data_rules.py compares the breaks with the dated exceptions in
tests/fixtures/design/data_rules/exceptions.json. The walk is the shared one of tests/schema_walk.py, so a property is found in
the same places, including inside `additionalProperties`, `patternProperties`, and the editor's copy of the config schema.

A rule finds a field by its name and its shape, as the design's families do, and never only by a `$ref`: a who field is a name
that ends in `by`, or an agent noun beside the event it did; an instant, a day, a duration, a commit, and a link each have their
names. What a name cannot say is a judged list in judged.json, and each entry on it carries its reason.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import NamedTuple

import helpers  # noqa: F401  (puts src on sys.path)
import schema_walk as walk
from helpers import ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "design"
DATA = FIXTURES / "data_rules"
EDITOR = "editor/config.json"
ID_REFS = ("common.schema.json#/$defs/id", "editor/config.json#/$defs/common.id")
SHA_REFS = ("common.schema.json#/$defs/sha", "editor/config.json#/$defs/common.sha")
WHO_NAME = re.compile(r"(^|_)by$")
DURATION_UNIT = re.compile(r"_(seconds|minutes|hours|days|ms)$")
DURATION_TEXT = re.compile(r"(\\d|\[0-9\])\+[(\[][smhdw|]+[)\]]")
INSTANT_TEXT = re.compile(r"T(\\d|\[0-9\])\{2\}:")
DAY_TEXT = re.compile(r"^\^?(\\d|\[0-9\])\{4\}-")
DATE_NAME = re.compile(r"_(date|time|day|timestamp|datetime)$")
COMMIT_NAME = re.compile(r"(^|_)(sha|commit|rev|revision)$")
PARTICIPLE = re.compile(r"(ed|_back|_off|_out)$")


class Prop(NamedTuple):
    """One property a schema declares: where it is, its name, its node, and the object that declares it."""

    where: str
    file: str
    key: str
    node: dict
    owner: dict
    owner_where: str


def load_schemas(root=ROOT) -> dict[str, dict]:
    """Every `schemas/*.schema.json`, and the editor's copy of the config schema, by file name."""
    folder = root / "schemas"
    found = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.schema.json"))}
    found[EDITOR] = json.loads((folder / "editor" / "config.json").read_text(encoding="utf-8"))
    return found


def load_json(name: str) -> object:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def packages() -> dict[str, str]:
    """The packages of the redesign, in the order they land, each with what it does: the words an exception or a case waits on."""
    return json.loads((FIXTURES / "packages.json").read_text(encoding="utf-8"))["packages"]


def load_item_types() -> dict:
    return json.loads((ROOT / "schemas" / "item-types.json").read_text(encoding="utf-8"))["types"]


def plain_words() -> list[str]:
    """aidd's plain words for a kind of thing, which a qualifier must not be joined onto without a person's reason."""
    return load_json("plain_words.json")["words"]


def risk_actions() -> set[str]:
    return set(json.loads((ROOT / "schemas" / "risks.json").read_text(encoding="utf-8"))["actions"])


def properties(schemas: dict[str, dict]) -> Iterator[Prop]:
    for name, root in schemas.items():
        for pointer, node, _label in walk.schema_nodes(root):
            declared = node.get("properties")
            for key, sub in (declared if isinstance(declared, dict) else {}).items():
                if isinstance(sub, dict):
                    yield Prop(f"{name}{pointer}/properties/{key}", name, key, sub, node, f"{name}{pointer}")


def reach(node: dict, file: str, into_items: bool = False) -> tuple[set[str], set[str]]:
    """What a node is and refs, through its `$ref`s and choices; a `$ref` to a definition the files do not hold yet is only named."""
    try:
        return walk.reach(node, file, into_items)
    except KeyError:
        return {str(node[k]) for k in ("type", "format") if isinstance(node.get(k), str)}, {walk.canonical(node["$ref"], file)}


def words(prop: Prop, node: dict | None = None) -> set[str]:
    """The `type` and `format` words a property is, through its `$ref`s and choices."""
    return reach(prop.node if node is None else node, prop.file)[0]


def refs(prop: Prop) -> set[str]:
    """The schemas a property refs, through its choices and its list items."""
    return reach(prop.node, prop.file, True)[1]


def values(prop: Prop) -> set[str]:
    """Every string a property allows through `enum`, `const`, a `$ref`, its items, or a choice."""
    try:
        return walk.values_of(prop.node, prop.file)
    except KeyError:
        return {v for v in prop.node.get("enum", []) if isinstance(v, str)}


def siblings(prop: Prop) -> dict[str, dict]:
    return {k: v for k, v in prop.owner["properties"].items() if isinstance(v, dict) and k != prop.key}


def when_key(prop: Prop, name: str) -> bool:
    """Whether the sibling `name` holds a day or an instant."""
    return bool(words(prop, siblings(prop)[name]) & {"date", "date-time"})


def stored(prop: Prop, judged: dict) -> bool:
    """Whether the property is in a file a person or an agent writes, never in what a command prints."""
    return prop.file not in judged["outputs"]


def conditional(prop: Prop) -> bool:
    """Whether the property sits in an `if`, a `then`, or a choice, where it is a condition and no stored field."""
    return any(c in prop.where for c in walk.CONDITIONAL)


def declared_in(prop: Prop) -> str:
    """The item type whose schema file declares the property, or an empty string."""
    home = prop.file
    return next((name for name, row in load_item_types().items() if row.get("schema") == home), "")


# ---- R1: a fact stored once, and nothing stored that a reader can work out -----------------------------------------


def r1(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    breaks: dict[str, str] = {}
    for prop in properties(schemas):
        if not stored(prop, judged):
            continue
        sibs = siblings(prop)
        if re.search(r"\b(optional )?cache of\b", prop.node.get("description", "")):
            breaks[prop.where] = "its own description calls it a cache of what is read elsewhere"
        counted = prop.key.removesuffix("_count") if prop.key.endswith("_count") else ""
        if counted and "integer" in words(prop) and any("array" in words(prop, sibs[k]) for k in (counted, f"{counted}s") if k in sibs):
            breaks[prop.where] = f"a stored count of `{counted}`, which the list itself gives"
        if "boolean" in words(prop) and (twin := [k for k, v in sibs.items() if prop.key in walk.values_of(v, prop.file)]):
            breaks[prop.where] = f"a boolean named for a word of `{twin[0]}`, which says it too"
    breaks.update(_status_words(schemas, judged))
    breaks.update(_read_values(schemas, judged))
    return breaks


def _status_words(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """A stored `status` holds only the words the design lets a file store; a status the list does not name is a new break."""
    breaks: dict[str, str] = {}
    allowed = judged["R1"]["stored_status_words"]
    for prop in properties(schemas):
        if prop.key != "status" or not stored(prop, judged) or conditional(prop):
            continue
        found = sorted(values(prop))
        if not found:
            continue
        if prop.where not in allowed:
            breaks[prop.where] = "a stored status that the judged list does not name"
        elif not allowed[prop.where]:
            breaks[prop.where] = "every word of this status is read from other facts, so none is stored"
        else:
            for word in found:
                if word not in allowed[prop.where]:
                    breaks[f"{prop.where}/enum/{word}"] = f"`{word}` is read from other facts, so a file does not store it"
    return breaks


def _read_values(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    here = {p.where for p in properties(schemas)}
    return {where: f"stored, and read from {reads}" for where, reads in judged["R1"]["read_values"].items() if where in here}


# ---- R2: a field answers one question ------------------------------------------------------------------------------


def enum_values(schemas: dict[str, dict]) -> Iterator[tuple[str, list[str]]]:
    for name, root in schemas.items():
        for pointer, node, _label in walk.schema_nodes(root):
            found = node.get("enum")
            if isinstance(found, list) and found and all(isinstance(v, str) for v in found):
                yield f"{name}{pointer}", found


def containing(found: list[str]) -> list[tuple[str, str]]:
    """Each value of an enum that contains another value of the same enum as one of its words: two facts in one value."""
    return [(v, w) for v in found for w in found if w != v and (v.startswith(f"{w}_") or v.endswith(f"_{w}") or f"_{w}_" in v)]


def owned_elsewhere(part_values: set[str], here: str, schemas: dict[str, dict], types: set[str]) -> bool:
    """Whether two or more of the values are a vocabulary another schema or the item types already own."""
    if len(part_values & types) >= 2:
        return True
    return any(where != here and len(part_values & set(other)) >= 2 for where, other in enum_values(schemas))


def r2(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """An enum value that contains another value of its own enum, or whose values join two parts that other things own."""
    breaks: dict[str, str] = {}
    actions, types = risk_actions(), set(load_item_types())
    for where, found in enum_values(schemas):
        if set(found) <= actions:
            continue
        if pairs := containing(found):
            if where not in judged["R2"]["contained_ok"]:
                breaks[where] = f"`{pairs[0][0]}` contains `{pairs[0][1]}`, another value of its own enum: two facts in one value"
            continue
        for sep in (".", "_"):
            parts = [v.split(sep, 1) for v in found if sep in v]
            heads, tails = {a for a, _ in parts}, {b for _, b in parts}
            if len(found) >= 3 and len(parts) >= 0.7 * len(found) and len(heads) >= 2 and len(tails) >= 2:
                if (sep == "." or len(parts) / (len(heads) * len(tails)) >= 0.4) and (
                    owned_elsewhere(heads, where, schemas, types) or owned_elsewhere(tails, where, schemas, types)
                ):
                    breaks[where] = f"its values join a head ({len(heads)}) and a tail ({len(tails)}) that other things own: two questions in one field"
                    break
    here = {p.where for p in properties(schemas)}
    breaks.update({w: f"one field that answers several questions: {why}" for w, why in judged["R2"]["several_questions"].items() if w in here})
    return breaks


# ---- R3: a person's decision is one object, absent until it happened, with who and when ----------------------------


def agent_noun_pair(key: str, sibs: dict) -> str:
    """The sibling that records the event a who field did, as `approver` beside `approved_on`, or an empty string."""
    if not key.endswith("er") or len(key) < 6:
        return ""
    base = key[:-2]
    return next((k for k in sibs if re.fullmatch(rf"{base}e?d(_at|_on)?", k)), "")


def r3(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    breaks: dict[str, str] = {}
    fam = judged["R3"]
    for prop in properties(schemas):
        sibs, key = siblings(prop), prop.key
        if WHO_NAME.search(key) and key != "by":
            stem = key[:-3]
            if twins := [t for t in (stem, f"{stem}_at", f"{stem}_on") if t in sibs]:
                breaks[prop.where] = f"`{key}` and `{twins[0]}` are a loose pair, not one object"
        elif pair := agent_noun_pair(key, sibs):
            breaks[prop.where] = f"`{key}` and `{pair}` are a loose pair, not one object"
        if key == "by" and "at" not in sibs and (when := [k for k in sibs if when_key(prop, k)]):
            breaks[prop.where] = f"`by` is beside `{when[0]}`: a decision's time is `at`"
        if "boolean" in words(prop) and (reason := _flag(prop, sibs, fam, judged)):
            breaks[prop.where] = reason
        if key == "status" and stored(prop, judged) and values(prop) & set(fam["bare_words"]) and "by" not in sibs:
            breaks[prop.where] = f"a status that holds a person's decision as a bare word: {sorted(values(prop) & set(fam['bare_words']))}"
        if key in ("approval", "cancellation"):
            breaks.update(_one_definition(schemas, prop))
    return breaks


def _flag(prop: Prop, sibs: dict, fam: dict, judged: dict) -> str:
    """Why a true-or-false records an event with no who and no when of its own, or an empty string."""
    key = prop.key
    if any(k in sibs for k in (f"{key}_by", f"{key}_at", f"{key}_on")) or key in fam["decision_words"]:
        return "a true-or-false that records a decision, with no who and no when of its own"
    if any(noun in key for noun in fam["decision_nouns"]):
        return "a true-or-false named for a decision, with no who and no when of its own"
    if PARTICIPLE.search(key) and stored(prop, judged) and key not in fam["participle_flags"]:
        return "a true-or-false that records an event, beside no fact that says who and when"
    return ""


def _one_definition(schemas: dict[str, dict], prop: Prop) -> dict[str, str]:
    """A decision object is the one shared definition, and absent until it happened."""
    if words(prop) & {"string", "integer", "boolean", "array", "number"}:
        return {}
    problems = []
    if not _reaches_decision(schemas, prop.node, prop.file):
        problems.append("it is not the one shared definition")
    if prop.key in prop.owner.get("required", []):
        problems.append("it is required, so it is never absent")
    return {prop.where: "; ".join(problems)} if problems else {}


# ---- R4: what varies along a dimension is a collection along it -----------------------------------------------------


def vocabularies(schemas: dict[str, dict], judged: dict) -> list[set[str]]:
    """Each closed set of values aidd names: every enum of 3 values or more, and the judged ones."""
    found = [set(v) for _, v in enum_values(schemas) if len(v) >= 3]
    return found + [set(v) for v in judged["R4"]["dimensions"].values()]


def is_object(node: dict, file: str) -> bool:
    return "object" in reach(node, file)[0] or "properties" in node


def r4(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """A value of a dimension inside a property name, and a map with an entry for each value whose members are objects."""
    breaks: dict[str, str] = {}
    sets = vocabularies(schemas, judged)
    for name, root in schemas.items():
        for pointer, node, _label in walk.schema_nodes(root):
            where = f"{name}{pointer}"
            declared = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            keyed = node.get("propertyNames", {}).get("enum")
            if declared:
                if (hit := _in_names(list(declared), sets)) is not None:
                    breaks[where] = f"a dimension's value inside the names of its properties: {hit}"
                    continue
                for vocab in sets:
                    named = [k for k in declared if k in vocab]
                    if (
                        len(named) >= 3
                        and len(named) >= 0.6 * len(declared)
                        and all(is_object(declared[k], name) for k in named if isinstance(declared[k], dict))
                    ):
                        breaks[where] = f"a property for each of {sorted(named)[:4]}, each an object of its own: a list along that dimension"
                        break
            if (
                isinstance(keyed, list)
                and len(keyed) >= 3
                and isinstance(node.get("additionalProperties"), dict)
                and is_object(node["additionalProperties"], name)
            ):
                breaks[where] = f"a map with an entry for each of {sorted(keyed)[:4]}, each an object of its own: a list along that dimension"
    return breaks


def _in_names(names: list[str], sets: list[set[str]]) -> str | None:
    """Three or more names that are one name with a different value of one dimension in it, such as `minor_reviewers`."""
    for vocab in sets:
        groups: dict[str, set[str]] = {}
        for key in names:
            parts = key.split("_")
            for i, token in enumerate(parts):
                if token in vocab and len(parts) > 1:
                    groups.setdefault("_".join([*parts[:i], "*", *parts[i + 1 :]]), set()).add(token)
        for shape, found in groups.items():
            if len(found) >= 3:
                return f"{shape} for {sorted(found)}"
    return None


# ---- R5: the same kind of thing has one shape and one name everywhere -----------------------------------------------


def moment(prop: Prop, kinds: set[str]) -> str:
    """`instant` or `day` when the property says so by its format or its pattern, `other` when it is no string, else `text`."""
    text = "".join(str(n.get("pattern", "")) for n in _chain(prop))
    if "date-time" in kinds or INSTANT_TEXT.search(text):
        return "instant"
    if "date" in kinds or DAY_TEXT.search(text):
        return "day"
    return "text" if "string" in kinds else "other"


def r5(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    breaks: dict[str, str] = {}
    fam = judged["R5"]
    for prop in properties(schemas):
        key, kinds = prop.key, words(prop)
        what = moment(prop, kinds)
        instant_name, day_name = key == "at" or key.endswith("_at"), key == "on" or key.endswith("_on")
        due_name = key == "due" or key.endswith("_due")
        suffixed = key.endswith(("_at", "_on", "_due"))
        if what == "instant" and not instant_name:
            breaks[prop.where] = "an instant is `at`, or ends in `_at`"
        if what == "day" and not (day_name or due_name or key in fam["day_ahead_words"]):
            breaks[prop.where] = "a calendar day is `on`, ends in `_on`, or is a day owed (`due`, `_due`)"
        if DATE_NAME.search(key):
            breaks[prop.where] = "a day is `_on`, and an instant is `_at`: never `_date`, `_time`, `_day`, or `_timestamp`"
        if instant_name and what != "instant" and (suffixed or what == "other"):
            breaks[prop.where] = "a name that ends in `_at` holds no instant"
        if (day_name or due_name) and key not in fam["not_days"] and what != "day" and (suffixed or what == "other"):
            breaks[prop.where] = "a name that ends in `_on` or `_due` holds no day"
        breaks.update(_duration(prop, kinds))
        breaks.update(_who(prop, fam))
        breaks.update(_commit(prop, fam))
        breaks.update(_meaning(prop, kinds, fam))
        breaks.update(_link(prop, judged))
    judged_here = judged["R5"]["qualified_kept"]
    breaks.update({w: why for w, why in qualified(schemas).items() if source_of(w) not in judged_here})
    return breaks


def parent_name(owner_where: str) -> str:
    """The name of the property or definition that holds an object, or an empty string at a schema's top."""
    parts = owner_where.split("#", 1)[1].split("/")
    return next((parts[i] for i in range(len(parts) - 1, 0, -1) if parts[i - 1] in ("properties", "$defs")), "")


def qualified(schemas: dict[str, dict]) -> dict[str, str]:
    """Every candidate for a qualifier joined onto a name: a name of two words or more that ends in a plain word the parent holds
    no property of, a name that begins or ends with its parent's or its schema's own name, and an enum value that does the same.
    A machine cannot say whether the qualifier is the thing itself, so a person decides each one."""
    plain, actions = plain_words(), risk_actions()
    found: dict[str, str] = {}
    for prop in properties(schemas):
        parts = prop.key.split("_")
        if len(parts) >= 2 and parts[-1] in plain and parts[-1] not in prop.owner["properties"]:
            found[prop.where] = f"`{prop.key}` carries a qualifier, and `{parts[-1]}` is free in this parent"
        stem = prop.file.replace(".schema.json", "").replace("editor/config.json", "config").replace("-", "_")
        parent = parent_name(prop.owner_where)
        for own in {stem, parent, parent.removesuffix("s")} - {""}:
            if prop.key.startswith(f"{own}_") or prop.key.endswith(f"_{own}"):
                found[prop.where] = f"`{prop.key}` begins or ends with the name of its parent or its schema, `{own}`"
    for where, values_ in enum_values(schemas):
        if set(values_) <= actions:
            continue
        for value in values_:
            parts = re.split(r"[_.]", value)
            if len(parts) >= 2 and parts[-1] in plain and parts[-1] not in values_:
                found[f"{where}/enum/{value}"] = f"`{value}` carries a qualifier, and `{parts[-1]}` is free among its values"
    return found


def _duration(prop: Prop, kinds: set[str]) -> dict[str, str]:
    """A duration is an integer with its unit in the name; a string that holds a number and a unit is not."""
    if DURATION_UNIT.search(prop.key) and not kinds & {"integer", "number"}:
        return {prop.where: "a name with a unit holds no number"}
    text = "".join(str(n.get("pattern", "")) for n in _chain(prop))
    if "string" in kinds and DURATION_TEXT.search(text):
        return {prop.where: "a duration written as text with a unit inside, not an integer with the unit in the name"}
    return {}


def _chain(prop: Prop) -> list[dict]:
    """The property's node and the nodes its `$ref` and choices lead to."""
    out, todo, seen = [], [(prop.node, prop.file)], set()
    while todo:
        node, home = todo.pop()
        out.append(node)
        for sub in [node] + [c for k in ("anyOf", "oneOf", "allOf") for c in node.get(k, [])]:
            ref = sub.get("$ref")
            if isinstance(ref, str) and (home, ref) not in seen:
                seen.add((home, ref))
                try:
                    todo.append(walk.resolved(ref, home))
                except KeyError:
                    continue
    return out


def _who(prop: Prop, fam: dict) -> dict[str, str]:
    """Who did it is `by` inside the object of what they did. A name that ends in `by`, and is no link to a thing, is a loose who."""
    if WHO_NAME.search(prop.key) and prop.key != "by" and prop.key not in fam["link_by"]:
        return {prop.where: f"`{prop.key}` names who did it outside the object of what they did: that is `by`"}
    return {}


def _commit(prop: Prop, fam: dict) -> dict[str, str]:
    """A commit a fact is about is `commit` inside its object, or `head_sha` and `base_sha`, or the link `merged_in`."""
    holds_sha = any(r in SHA_REFS for r in refs(prop))
    if "string" in words(prop) and (COMMIT_NAME.search(prop.key) or holds_sha) and prop.key not in fam["commit_names"]:
        return {prop.where: f"`{prop.key}` names a commit: that is `commit`, `head_sha`, `base_sha`, or the link `merged_in`"}
    return {}


def _meaning(prop: Prop, kinds: set[str], fam: dict) -> dict[str, str]:
    """A word the design gives one meaning holds that meaning everywhere: `outcome` is a goal, and `approval` is a decision object."""
    meaning = fam["one_meaning"].get(prop.key)
    if meaning and not (kinds & set(meaning["types"]) or not kinds):
        return {prop.where: f"`{prop.key}` is {meaning['means']}, and here it is {sorted(kinds) or 'something else'}"}
    return {}


def _link(prop: Prop, judged: dict) -> dict[str, str]:
    """A property that holds the id of another work item is a link with one of the named verbs."""
    if prop.key == "id" or not any(r in ID_REFS for r in refs(prop)):
        return {}
    if prop.key in judged["R5"]["links"] or not stored(prop, judged):
        return {}
    return {prop.where: f"`{prop.key}` holds an id but is not one of the link names {sorted(judged['R5']['links'])}"}


# ---- R6: embed what is read and decided together; the child names the parent -----------------------------------------


def r6(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    breaks: dict[str, str] = {}
    types = load_item_types()
    files = {name: {p.key for p in properties({name: root})} for name, root in schemas.items()}
    for prop in properties(schemas):
        if not stored(prop, judged) or "array" not in words(prop):
            continue
        if prop.key in judged["R6"]["child_lists"] or prop.key in child_lists_in(prop.file, types) or listed_place(prop, judged):
            breaks[prop.where] = f"a list of children (`{prop.key}`): the child names its parent, so the parent keeps no list"
    for prop in properties(schemas):
        stem = prop.key[:-3] if prop.key.endswith("_by") else ""
        verbs = {stem[:-2], stem[:-1]} if stem.endswith("ed") else set()
        if stored(prop, judged) and any(f"{v}s" in files[prop.file] for v in verbs):
            breaks[prop.where] = f"a link kept at both ends: `{prop.key}` and its active verb in {prop.file}"
    for name, row in types.items():
        schema, parent = row.get("schema"), row.get("parent")
        if parent and schema and "parent" not in files.get(schema, ()):
            breaks[f"{schema}#/properties/parent"] = f"item type `{name}` has a parent type `{parent}` but its schema has no `parent`"
    return breaks


def listed_place(prop: Prop, judged: dict) -> bool:
    """Whether the property is a list of children that its name cannot tell, such as an Intent's plan of planned Specs."""
    return source_of(prop.where) in judged["R6"]["child_list_places"]


def child_lists_in(file: str, types: dict) -> set[str]:
    """The plural of each item type whose parent type is declared in `file`: only there is it a list of children."""
    return {f"{name}s" for name, row in types.items() if row.get("parent") and types.get(row["parent"], {}).get("schema") == file}


# ---- V1-V4: the three layers (4.1, 8.1) and one decision definition (5.1) ---------------------------------------------

DECISION_DEF = "common.schema.json#/$defs/decision"


def _at_pointer(schemas: dict[str, dict], where: str) -> dict | None:
    """The schema node at `<file>#<pointer>` inside `schemas`, or `None` if absent."""
    file, _, frag = where.partition("#")
    cur: object = schemas.get(file)
    for part in frag.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur if isinstance(cur, dict) else None


def _enum_nodes(schemas: dict[str, dict], node: dict, where: str, file: str, seen: frozenset = frozenset()) -> Iterator[tuple[str, dict]]:
    """Each node with an `enum` that `node` is, refers to, or wraps in `allOf`, `anyOf`, or `oneOf`, with the place it sits at."""
    if isinstance(node.get("enum"), list):
        yield where, node
    if isinstance(node.get("$ref"), str):
        target = source_of(walk.canonical(node["$ref"], file))
        found = _at_pointer(schemas, target)
        if found is not None and target not in seen:
            yield from _enum_nodes(schemas, found, target, target.split("#", 1)[0], seen | {target})
    for key in ("allOf", "anyOf", "oneOf"):
        for i, choice in enumerate(node.get(key, [])):
            if isinstance(choice, dict):
                yield from _enum_nodes(schemas, choice, f"{where}/{key}/{i}", file, seen)


def status_enums(schemas: dict[str, dict], judged: dict, *, include_ruled_out: bool = False) -> dict[str, dict]:
    """Every non-conditional `properties/status` enum in `schemas`, through a `$ref` or a wrapping choice, minus the judged non-item statuses.

    Only the key `status` is a status. The enums under `decision`, `state`, `result`, and `outcome` are judged as no status in
    judged.json (`V1.other_enum_keys`), each with its reason."""
    ruled_out = judged["V1"]["ruled_out_statuses"]
    found: dict[str, dict] = {}
    for prop in properties(schemas):
        if prop.key != "status" or conditional(prop):
            continue
        for where, node in _enum_nodes(schemas, prop.node, source_of(prop.where), prop.file):
            if include_ruled_out or where not in ruled_out:
                found.setdefault(where, node)
    return found


def other_enum_keys(schemas: dict[str, dict], judged: dict) -> dict[str, list[str]]:
    """For each key judged as no status (`decision`, `state`, `result`, `outcome`), the places that hold an enum under that key or a key ending in it."""
    found: dict[str, list[str]] = {name: [] for name in judged["V1"]["other_enum_keys"]}
    for prop in properties(schemas):
        for name in found:
            if (prop.key == name or prop.key.endswith(f"_{name}")) and any(True for _ in _enum_nodes(schemas, prop.node, prop.where, prop.file)):
                found[name].append(source_of(prop.where))
    return found


def _status_group_words(schemas: dict[str, dict]) -> set[str]:
    node = _at_pointer(schemas, "common.schema.json#/$defs/status_group")
    return {v for v in (node or {}).get("enum", []) if isinstance(v, str)}


def v1(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """Every status of every discovered status enum belongs to exactly one status group."""
    valid_groups = _status_group_words(schemas)
    breaks: dict[str, str] = {}
    for where, node in status_enums(schemas, judged).items():
        groups = node.get("x-groups")
        if not isinstance(groups, dict) or not groups:
            breaks[where] = "no `x-groups` map: every status must belong to one status group"
            continue
        words_list = [w for w in node["enum"] if isinstance(w, str)]
        for word in words_list:
            if word not in groups:
                breaks[f"{where}/x-groups/{word}"] = f"status `{word}` has no entry in `x-groups`"
            elif not isinstance(groups[word], str) or groups[word] not in valid_groups:
                breaks[f"{where}/x-groups/{word}"] = f"status `{word}` group `{groups[word]!r}` is not one of {sorted(valid_groups)}"
        for extra in set(groups) - set(words_list):
            breaks[f"{where}/x-groups/{extra}"] = f"`x-groups` names `{extra}`, which is not in `enum`"
    return breaks


def v2(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """No status is a frame word (`open`, `closed`, `reopened`), and none is a group word except `cancelled`."""
    frame_words = set(judged["V2"]["frame_words"])
    group_words = _status_group_words(schemas) - {"cancelled"}
    breaks: dict[str, str] = {}
    for where, node in status_enums(schemas, judged).items():
        for word in node["enum"]:
            if not isinstance(word, str):
                continue
            if word in frame_words:
                breaks[f"{where}/enum/{word}"] = f"status `{word}` is a frame word, never a status"
            elif word in group_words:
                breaks[f"{where}/enum/{word}"] = f"status `{word}` is a status group word; only `cancelled` may also be a status"
    return breaks


def _canonical_choice(pairs: list[tuple[str, str]]) -> str:
    """The agreed group or meaning for a shared status word: most common first, then Spec's table, Intent's, or pointer order."""
    counts: dict[str, int] = {}
    for _, val in pairs:
        counts[val] = counts.get(val, 0) + 1
    priority = {"common.schema.json#/$defs/status": 0, "common.schema.json#/$defs/intent_status": 1}
    best_where, best_val = min(pairs, key=lambda item: (-counts[item[1]], priority.get(item[0], 2), item[0]))
    return best_val


def v3(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """A status word occurring in two types has the same group and (where data states `x-meanings`) one meaning in both.

    The meanings of section 8.1 become data with Task N6; until then this rule holds what the schemas state."""
    by_word: dict[str, list[tuple[str, str | None, str | None]]] = {}
    for where, node in status_enums(schemas, judged).items():
        groups = node.get("x-groups") if isinstance(node.get("x-groups"), dict) else {}
        meanings = node.get("x-meanings") if isinstance(node.get("x-meanings"), dict) else {}
        for word in node["enum"]:
            if isinstance(word, str):
                g = groups.get(word) if isinstance(groups.get(word), str) else None
                m = meanings.get(word) if isinstance(meanings.get(word), str) and meanings.get(word, "").strip() else None
                by_word.setdefault(word, []).append((where, g, m))
    breaks: dict[str, str] = {}
    for word, occs in by_word.items():
        if len(occs) < 2:
            continue
        grouped = [(w, g) for w, g, _ in occs if g is not None]
        if len({g for _, g in grouped}) > 1:
            expected_group = _canonical_choice(grouped)
            for where, group in grouped:
                if group != expected_group:
                    breaks[f"{where}/x-groups/{word}"] = f"status `{word}` is `{group}`, unlike `{expected_group}` elsewhere"
        described = [(w, m.strip()) for w, _, m in occs if m is not None]
        if len({m for _, m in described}) > 1:
            expected_meaning = _canonical_choice(described)
            for where, meaning in described:
                if meaning != expected_meaning:
                    breaks[f"{where}/x-meanings/{word}"] = f"status `{word}` has a different `x-meanings` text than other types"
    return breaks


def _reaches_decision(schemas: dict[str, dict], node: dict, file: str, *, into_items: bool = False, seen: frozenset = frozenset()) -> bool:
    """Whether `node` is the one decision definition, or leads to it through a `$ref`, `allOf`, `anyOf`, or `oneOf`, and through `items` if asked."""
    if isinstance(node.get("$ref"), str):
        target = source_of(walk.canonical(node["$ref"], file))
        if target == DECISION_DEF:
            return True
        found = _at_pointer(schemas, target)
        if found is not None and target not in seen and _reaches_decision(schemas, found, target.split("#", 1)[0], into_items=into_items, seen=seen | {target}):
            return True
    parts = [c for key in ("allOf", "anyOf", "oneOf") for c in node.get(key, []) if isinstance(c, dict)]
    parts += [node["items"]] if into_items and isinstance(node.get("items"), dict) else []
    return any(_reaches_decision(schemas, c, file, into_items=into_items, seen=seen) for c in parts)


def _is_who(key: str, judged: dict) -> bool:
    """A key that ends `_by` and is no link to a thing: it holds who did something outside the object of what they did."""
    return key.endswith("_by") and key not in judged["R5"]["link_by"]


def _is_when(prop: Prop, judged: dict) -> bool:
    """A key named `at`, `on`, or ending `_at` or `_on` that holds a day or an instant, and is either named for an event
    (`approved_at`, a participle) or sits beside a who key (`by` or a name ending `_by`)."""
    key = prop.key
    if not (key in ("at", "on") or key.endswith(("_at", "_on"))) or not words(prop) & {"date", "date-time"}:
        return False
    stem = key.removesuffix("_at").removesuffix("_on")
    return key in ("at", "on") or bool(PARTICIPLE.search(stem)) or any(k == "by" or _is_who(k, judged) for k in siblings(prop))


def _in_condition(where: str) -> bool:
    """Whether the place is inside an `if`, `then`, or `else`, where a field is a condition and no stored field."""
    return any(c in where for c in ("/if/", "/then/", "/else/"))


def loose_keys(schemas: dict[str, dict], judged: dict, *, include_judged_out: bool = False) -> dict[str, Prop]:
    """Each key that holds who decided, or when, by its form and outside the one definition: a name that ends `_by`, and a name that ends
    `_at` or `_on` beside a who key or named for an event. A key that is no decision is judged out by name in `V4.not_decisions`."""
    out = judged["V4"]["not_decisions"]
    found: dict[str, Prop] = {}
    for prop in properties(schemas):
        if _in_condition(prop.where) or (prop.key in out and not include_judged_out):
            continue
        if _is_who(prop.key, judged) or (prop.key not in ("at", "on") and _is_when(prop, judged)):
            found.setdefault(source_of(prop.where), prop)
    return found


def _is_delegate_choice(choice: dict, shape: set[str]) -> bool:
    """Whether a choice of a decision is the listed shape that holds no `by`, as a delegate's approval of a Spec does."""
    declared = choice.get("properties", {})
    return bool(shape) and shape <= set(declared) and "by" not in declared


def v4(schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """Every decision refers to `$defs/decision`; no key holds who decided or when outside it; Table 2's shapes are no decision."""
    breaks: dict[str, str] = {}
    cfg = judged["V4"]
    decision_node = _at_pointer(schemas, DECISION_DEF)
    decision_props = decision_node.get("properties") if isinstance(decision_node, dict) else None
    if not isinstance(decision_props, dict) or not {"by", "at"} <= set(decision_props):
        breaks[DECISION_DEF] = "the shared `$defs/decision` definition must exist with `by` and `at`"
    decision_keys = set(cfg["decision_keys"])
    scoped = cfg["scoped_decision_keys"]
    delegate = {item["choice_of"]: set(item["shape"]) for item in cfg["other_shapes"].values() if "choice_of" in item}
    for prop in properties(schemas):
        where = source_of(prop.where)
        if _in_condition(prop.where) or not (prop.key in decision_keys or prop.key in scoped.get(where.split("#", 1)[0], ())):
            continue
        if not _reaches_decision(schemas, prop.node, prop.file):
            breaks[where] = f"decision `{prop.key}` must refer to `{DECISION_DEF}`"
            continue
        for kind in ("anyOf", "oneOf"):
            for i, choice in enumerate(c for c in prop.node.get(kind, []) if isinstance(c, dict)):
                listed = _is_delegate_choice(choice, delegate.get(where, set()))
                if listed == _reaches_decision(schemas, choice, prop.file):
                    what = "both a listed shape and the decision" if listed else "neither the decision nor a listed shape"
                    breaks[f"{where}/{kind}/{i}"] = f"a choice of `{prop.key}` is {what}"
    for where, prop in loose_keys(schemas, judged).items():
        stem = prop.key.removesuffix("_by").removesuffix("_at").removesuffix("_on")
        sibs = siblings(prop)
        if not prop.key.endswith("_by") and f"{stem}_by" in sibs and _is_who(f"{stem}_by", judged) and f"{stem}_by" not in cfg["not_decisions"]:
            continue  # a pair is one break, at its `_by`
        twin = next((k for k in (f"{stem}_at", f"{stem}_on") if prop.key.endswith("_by") and k in sibs), "")
        names = f"`{prop.key}` and `{twin}` hold who decided and when" if twin else f"`{prop.key}` holds who decided or when"
        breaks[where] = f"{names} outside `{DECISION_DEF}`"
    table_2 = {place for item in cfg["other_shapes"].values() for place in item["schema_places"]}
    owners: dict[str, list[Prop]] = {}
    for prop in properties(schemas):
        owners.setdefault(source_of(prop.owner_where), []).append(prop)
    for owner, held in owners.items():
        if owner == DECISION_DEF or owner in table_2 or _in_condition(owner):
            continue
        if _reaches_decision(schemas, held[0].owner, held[0].file):
            continue  # it refers to the definition, and lists `by` and `at` again only to stay closed to other keys
        if any(p.key == "by" for p in held) and any(_is_when(p, judged) and p.key not in cfg["not_decisions"] for p in held):
            breaks[owner] = f"an object that holds who and when itself, where `{DECISION_DEF}` is meant"
    for name, item in cfg["other_shapes"].items():
        for place in item["schema_places"]:
            node = _at_pointer(schemas, place)
            if node is not None and _reaches_decision(schemas, node, place.split("#", 1)[0], into_items=True):
                breaks[place] = f"listed in 5.1 Table 2 (`{name}`), so it must not refer to `{DECISION_DEF}`"
    return breaks


RULES: dict[str, Callable[[dict[str, dict], dict], dict[str, str]]] = {
    "R1": r1,
    "R2": r2,
    "R3": r3,
    "R4": r4,
    "R5": r5,
    "R6": r6,
    "V1": v1,
    "V2": v2,
    "V3": v3,
    "V4": v4,
}
INLINED = re.compile(r"^/\$defs/([a-z-]+)\.(.+)$")


def source_of(where: str) -> str:
    """The place in a schema file that the editor's copy of the config schema repeats, so a break is listed once."""
    if not where.startswith(f"{EDITOR}#"):
        return where
    pointer = where.split("#", 1)[1]
    inlined = INLINED.match(pointer)
    return f"{inlined.group(1)}.schema.json#/$defs/{inlined.group(2)}" if inlined else f"config.schema.json#{pointer}"


def breaks(rule: str, schemas: dict[str, dict], judged: dict) -> dict[str, str]:
    """A rule's breaks over the schemas, the editor's copy counted with the schema it copies."""
    return {source_of(where): why for where, why in RULES[rule](schemas, judged).items()}


def compare(rule: str, found: dict[str, str], exceptions: list[dict]) -> list[str]:
    """The problems between a rule's breaks and its exceptions: a break nobody listed, and a listed one that is gone."""
    listed = {e["where"]: e for e in exceptions if e["rule"] == rule}
    problems = [f"{rule}: {where}: {why}. Fix it, or list it with its package" for where, why in sorted(found.items()) if where not in listed]
    problems += [f"{rule}: {where} no longer breaks the rule: delete its exception" for where in sorted(listed) if where not in found]
    return problems
