"""The walk over a schema's properties, one for every test that reads the schemas as data (tests/test_field_names.py and
tests/data_rules.py): each schema node, each property, what a property is through its `$ref`s, and every string it allows."""

import helpers  # noqa: F401  (puts src on sys.path)
from aidd.kernel import resources


def resolved(ref: str, name: str) -> tuple[dict, str]:
    """The node a `$ref` points at, and the schema file it sits in."""
    file, _, frag = ref.partition("#")
    name = resources.schema_file(file) if file else name
    node = resources.load_json(name)
    for part in frag.split("/")[1:]:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node, name


def values_of(node: dict, name: str, seen: frozenset = frozenset()) -> set[str]:
    """Every string a schema node allows through `enum`, `const`, a `$ref`, `items`, or a choice of schemas."""
    out = {v for v in node.get("enum", []) if isinstance(v, str)}
    if isinstance(node.get("const"), str):
        out.add(node["const"])
    ref = node.get("$ref")
    if ref and (name, ref) not in seen:
        target, home = resolved(ref, name)
        out |= values_of(target, home, seen | {(name, ref)})
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            out |= values_of(node[key], name, seen)
    for key in ("anyOf", "oneOf", "allOf"):
        for choice in node.get(key, []):
            out |= values_of(choice, name, seen)
    return out


# A schema inside one of these holds a condition or a choice, where a single value is how a discriminator works.
CONDITIONAL = ("/if/", "/then/", "/else/", "/oneOf/", "/anyOf/", "/allOf/")
SCHEMA_MAPS = ("properties", "patternProperties", "$defs")
SCHEMA_ONE = ("items", "additionalProperties", "propertyNames", "not", "if", "then", "else", "contains")
SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")


def schema_nodes(node: object, pointer: str = "#", label: str = ""):
    """Each schema of a file as `(pointer, node, label)`, `label` being the nearest property or `$defs` name above it."""
    if not isinstance(node, dict):
        return
    yield pointer, node, label
    for holder in SCHEMA_MAPS:
        for key, sub in (node.get(holder) if isinstance(node.get(holder), dict) else {}).items():
            yield from schema_nodes(sub, f"{pointer}/{holder}/{key}", key)
    for holder in SCHEMA_ONE:
        yield from schema_nodes(node.get(holder), f"{pointer}/{holder}", label)
    for holder in SCHEMA_LISTS:
        for i, sub in enumerate(node.get(holder) if isinstance(node.get(holder), list) else ()):
            yield from schema_nodes(sub, f"{pointer}/{holder}/{i}", label)


def schema_properties(name: str, root: dict):
    """Each property a file declares as `(where, key, node, label of its object)`."""
    for pointer, node, label in schema_nodes(root):
        for key, sub in (node.get("properties") if isinstance(node.get("properties"), dict) else {}).items():
            if isinstance(sub, dict):
                yield f"{name}{pointer}/properties/{key}", key, sub, label


def canonical(ref: str, name: str) -> str:
    file, _, frag = ref.partition("#")
    return f"{resources.schema_file(file) if file else name}#{frag}"


def reach(node: dict, name: str, into_items: bool = False, seen: frozenset = frozenset()) -> tuple[set[str], set[str]]:
    """What a property is, through its `$ref`s and choices (and its list items, if asked): its `type` and `format` words, and the schemas it refs."""
    words = {str(node[k]) for k in ("type", "format") if isinstance(node.get(k), str)}
    refs: set[str] = set()
    if isinstance(node.get("$ref"), str) and (name, node["$ref"]) not in seen:
        refs.add(canonical(node["$ref"], name))
        target, home = resolved(node["$ref"], name)
        more_words, more_refs = reach(target, home, into_items, seen | {(name, node["$ref"])})
        words |= more_words
        refs |= more_refs
    for sub in [c for k in ("anyOf", "oneOf", "allOf") for c in node.get(k, [])]:
        more_words, more_refs = reach(sub, name, into_items, seen)
        words |= more_words
        refs |= more_refs
    if into_items and isinstance(node.get("items"), dict):
        refs |= reach(node["items"], name, into_items, seen)[1]
    return words, refs
