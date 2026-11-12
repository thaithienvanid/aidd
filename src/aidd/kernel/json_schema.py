"""A small JSON Schema 2020-12 validator covering the keywords aidd schemas use.

Supported: $ref (local, a sibling file name, or a sibling schema by its `$id`,
urn:aidd:1:<name>, which resolves to <name>.schema.json), type, const, enum, required,
properties, additionalProperties, items, minItems, maxItems, uniqueItems,
minLength, maxLength, pattern, minimum, maximum, allOf, anyOf, oneOf, not,
if/then/else, and format (date and date-time only). Unknown keywords are
ignored, as the spec allows, except `x-open: true` on an `enum`: it marks a family of codes that a minor
release may grow, which a reader (`open_set`) accepts a value of that it does not know, if the value has the type of the listed ones. tests/helpers.py lists the draft 2020-12
assertions this validator does not implement, and a test keeps them out of
every schema.
Patterns use Python regular expressions with fullmatch semantics for $-anchored
patterns; ECMA-only syntax such as \\p{Letter} is not supported.
tests/test_schema_suite.py runs the official JSON Schema Test Suite for every
supported keyword.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import operator
import re
import unicodedata
import urllib.parse
from typing import Any

from aidd.kernel import resources, text

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}

# Size and range keywords: (keyword, the instance type it applies to, the failing comparison, the message). A string or
# an array is measured by its length, a number by its value. The errors come in this order.
_LIMITS = (
    ("minLength", "string", operator.lt, "shorter than {}"),
    ("maxLength", "string", operator.gt, "longer than {}"),
    ("minimum", "number", operator.lt, "below minimum {}"),
    ("maximum", "number", operator.gt, "above maximum {}"),
    ("minItems", "array", operator.lt, "needs at least {} item(s)"),
    ("maxItems", "array", operator.gt, "allows at most {} item(s)"),
)
_FORMATS = {"date": dt.date.fromisoformat, "date-time": lambda v: dt.datetime.fromisoformat(v.replace("Z", "+00:00"))}


def _equal(a: Any, b: Any) -> bool:
    """JSON equality: true is not 1, 1 equals 1.0, and object key order does not matter."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _kind(value: Any) -> str:
    """The JSON type of `value`: a boolean is no number here, as in `_equal`."""
    if isinstance(value, bool):
        return "boolean"
    return next((name for name in ("number", "string", "array", "object", "null") if _TYPES[name](value)), "")


def resolve_ref(ref: str, base: Any) -> tuple[Any, Any]:
    """Follow a $ref. `base` is a bundled schema's file name, or an in-memory root schema."""
    file, _, frag = ref.partition("#")
    name: Any
    node: Any
    if isinstance(base, dict) and not file:
        name = node = base
    else:
        name = resources.schema_file(file) if file else base
        node = resources.load_json(name)
    for part in urllib.parse.unquote(frag).split("/")[1:] if frag else []:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node, name


def keyword_at(ref: str, keyword: str) -> Any:
    """What a bundled schema gives for `keyword` (`maxItems`) at `ref`, a `<file>#<pointer>`: the one owner of a size a writer keeps to."""
    return resolve_ref(ref, ref.partition("#")[0])[0][keyword]


def deref(node: dict, base: str) -> tuple[dict, str]:
    """`node` with every `$ref` at its top followed, and the schema file the result is in."""
    while "$ref" in node:
        node, base = resolve_ref(node["$ref"], base)
    return node, base


def _fmt(value: Any) -> str:
    """`value` as JSON for an error message. A value can be repository text, so every control, format, and line or
    paragraph separator character (bidi overrides, zero-width marks, DEL, the C1 controls) is written as its escape;
    printable letters outside ASCII stay readable."""
    return "".join(_escaped(c) for c in json.dumps(value, ensure_ascii=False))


def _escaped(c: str) -> str:
    if c.isascii() and c.isprintable() or unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"):
        return c
    return f"\\u{ord(c):04x}" if ord(c) <= 0xFFFF else f"\\U{ord(c):08x}"


def _check(inst: Any, sch: Any, path: str, base: Any, errs: list[str], depth: int = 0, open_set: bool = False) -> None:
    _Checker(base, errs, open_set).check(inst, sch, path, depth)


class _Checker:
    """One walk of an instance against a schema: `base` is the schema file (or root schema) a `$ref` is read from, and
    `errs` collects every problem. `open_set` reads as a reader of newer data does: a field the schema does not list is no
    error, and neither is a value that an `enum` marked `"x-open": true` (a family of codes a minor release may grow) does not
    list, when it has the type of the listed ones. Any other `enum` stays closed. Each method checks one group of keywords, in the order the walk visits them."""

    def __init__(self, base: Any, errs: list[str], open_set: bool = False) -> None:
        self.base, self.errs, self.open_set = base, errs, open_set

    def check(self, inst: Any, sch: Any, path: str, depth: int = 0) -> None:
        if sch is True or sch == {}:
            return
        if sch is False:
            self.errs.append(f"{path}: not allowed")
            return
        if not isinstance(sch, dict):
            self.errs.append(f"{path}: schema must be an object or a boolean, got {_fmt(sch)[:60]}")
            return
        if "$ref" in sch:
            if depth > 64:
                self.errs.append(f"{path}: $ref cycle")
                return
            try:
                target, name = resolve_ref(sch["$ref"], self.base)
            except Exception as exc:
                self.errs.append(f"{path}: cannot resolve $ref {sch['$ref']!r}: {exc}")
                return
            if isinstance(target, dict) and "examples" in sch:
                target = {**target, "examples": sch["examples"]}
            _Checker(name, self.errs, self.open_set).check(inst, target, path, depth + 1)
        if "type" in sch and not self.type_holds(inst, sch["type"], path):
            return
        self.values(inst, sch, path)
        if isinstance(inst, str):
            self.string(inst, sch, path)
        if isinstance(inst, list):
            self.array(inst, sch, path, depth)
        if isinstance(inst, dict):
            self.object(inst, sch, path, depth)
        self.combinators(inst, sch, path, depth)

    def type_holds(self, inst: Any, declared: Any, path: str) -> bool:
        """Whether `inst` has one of the `declared` types; False stops the walk of this node, as an unknown type or a miss does."""
        raw_types = declared if isinstance(declared, list) else [declared]
        valid_types = [t for t in raw_types if isinstance(t, str) and t in _TYPES]
        self.errs += [f"{path}: unknown type {t!r}" for t in raw_types if not (isinstance(t, str) and t in _TYPES)]
        if not valid_types:
            return False
        if not any(_TYPES[t](inst) for t in valid_types):
            self.errs.append(f"{path}: expected {' or '.join(valid_types)}, got {_fmt(inst)[:60]}")
            return False
        return True

    def values(self, inst: Any, sch: dict, path: str) -> None:
        """`const`, `enum`, and the size limits."""
        if "const" in sch and not _equal(inst, sch["const"]):
            self.errs.append(f"{path}: must be {_fmt(sch['const'])}")
        open_family = self.open_set and sch.get("x-open") is True and any(_kind(inst) == _kind(e) for e in sch.get("enum", []))
        if "enum" in sch and not open_family and not any(_equal(inst, e) for e in sch["enum"]):
            self.errs.append(f"{path}: must be one of {', '.join(map(str, sch['enum']))}; got {_fmt(inst)}")
        for key, type_name, fails, message in _LIMITS:
            if key in sch and _TYPES[type_name](inst) and fails(inst if type_name == "number" else len(inst), sch[key]):
                self.errs.append(f"{path}: {message.format(sch[key])}")

    def string(self, inst: str, sch: dict, path: str) -> None:
        """`pattern` and the date formats."""
        examples = sch.get("examples")
        example = f" (for example, {_fmt(examples[0])})" if isinstance(examples, list) and examples else ""
        if "pattern" in sch:
            pat = sch["pattern"]
            try:
                rx = re.compile(pat)
                m = rx.search(inst)
                if m and pat.endswith("$") and not pat.endswith(r"\$") and inst[m.end() :] in ("\n", "\r\n"):
                    m = None
                if not m:
                    self.errs.append(f"{path}: {_fmt(inst)} does not match {pat}{example}")
            except re.error as exc:
                self.errs.append(f"{path}: invalid pattern {pat!r}: {exc}")
        if sch.get("format") in ("date", "date-time"):
            try:
                _FORMATS[sch["format"]](inst)
            except ValueError:
                self.errs.append(f"{path}: {_fmt(inst)} is not a valid ISO {sch['format']}{example}")

    def array(self, inst: list, sch: dict, path: str, depth: int) -> None:
        """`uniqueItems` and `items`."""
        if sch.get("uniqueItems") and any(_equal(inst[i], inst[j]) for i in range(len(inst)) for j in range(i + 1, len(inst))):
            self.errs.append(f"{path}: items must be unique")
        if "items" in sch:
            for i, item in enumerate(inst):
                self.check(item, sch["items"], f"{path}[{i}]", depth)

    def object(self, inst: dict, sch: dict, path: str, depth: int) -> None:
        """`required`, `propertyNames`, `properties`, and `additionalProperties`."""
        for key in sch.get("required", []):
            if key not in inst:
                self.errs.append(f"{path}: missing required field {key!r}")
        if isinstance(sch.get("propertyNames"), dict):
            for key in inst:
                self.check(key, sch["propertyNames"], f"{path}.{key} (name)", depth)
        props = sch.get("properties", {})
        for key, value in inst.items():
            if key in props:
                self.check(value, props[key], f"{path}.{key}", depth)
            elif "additionalProperties" in sch:
                extra = sch["additionalProperties"]
                if extra is False and not self.open_set:
                    guess = text.did_you_mean(str(key), props)
                    self.errs.append(f"{path}: unknown field {key!r}" + (f". {guess}" if guess else ""))
                elif isinstance(extra, dict):
                    self.check(value, extra, f"{path}.{key}", depth)

    def combinators(self, inst: Any, sch: dict, path: str, depth: int) -> None:
        """`allOf`, `anyOf`, `oneOf`, `not`, and `if` with its `then` or `else`."""
        for sub in sch.get("allOf", []):
            self.check(inst, sub, path, depth)
        if "anyOf" in sch and not any(_ok(inst, s, self.base, self.open_set) for s in sch["anyOf"]):
            self.errs.append(f"{path}: matches none of the allowed shapes")
        if "oneOf" in sch:
            hits = sum(1 for s in sch["oneOf"] if _ok(inst, s, self.base, self.open_set))
            if hits != 1:
                self.errs.append(f"{path}: must match exactly one allowed shape (matched {hits})")
        if "not" in sch and _ok(inst, sch["not"], self.base, self.open_set):
            self.errs.append(f"{path}: matches a forbidden shape")
        if "if" in sch:
            branch = "then" if _ok(inst, sch["if"], self.base, self.open_set) else "else"
            if branch in sch:
                self.check(inst, sch[branch], path, depth)


def _ok(inst: Any, sch: Any, base: Any, open_set: bool = False) -> bool:
    errs: list[str] = []
    _check(inst, sch, "$", base, errs, 0, open_set)
    return not errs


def bundled(schema_name: str) -> dict:
    """`schema_name` as one document with nothing to resolve outside it, for an editor's YAML language server: each
    `$ref` into a sibling schema (`urn:aidd:1:common#/$defs/glob`) points at a copy in its own `$defs`
    (`common.glob`). aidd's own validation reads the sibling files and never needs it."""
    root = copy.deepcopy(resources.load_json(resources.schema_file(schema_name)))
    defs = root.setdefault("$defs", {})
    pending: list[tuple[str, str, str]] = []

    def rewrite(node: Any, home: str) -> None:
        # `home`: the sibling file a fragment-only `$ref` in `node` points into; "" for the schema itself.
        if isinstance(node, list):
            for item in node:
                rewrite(item, home)
        if not isinstance(node, dict):
            return
        for key, value in list(node.items()):
            if key != "$ref" or not isinstance(value, str):
                rewrite(value, home)
                continue
            file, _, frag = value.partition("#")
            other = resources.schema_file(file) if file else home
            if not other:
                continue
            parts = frag.split("/")[1:]
            if len(parts) != 2 or parts[0] != "$defs":
                raise ValueError(f"{schema_name}: cannot bundle $ref {value!r}: only a sibling's $defs entries are bundled")
            name = f"{other.removesuffix('.schema.json')}.{parts[1]}"
            if name not in defs:
                defs[name] = {}
                pending.append((name, other, parts[1]))
            node[key] = f"#/$defs/{name}"

    rewrite(root, "")
    while pending:
        name, other, entry = pending.pop()
        copied = copy.deepcopy(resources.load_json(other)["$defs"][entry])
        rewrite(copied, other)
        defs[name] = copied
    return root


def validate(instance: Any, schema_name: str, *, open_set: bool = False) -> list[str]:
    """Return a list of human-readable errors, each once, in the order found; empty means valid. With `open_set` the instance is read as a reader of newer
    data reads it: a field the schema does not list and a value that an `enum` marked `"x-open": true` does not list are no
    errors, and everything else still is (a missing required field, a wrong type, a value of any other `enum`, a pattern or a size).
    A field that a shared definition and its own place both describe is named once."""
    errs: list[str] = []
    sch, base = resolve_ref(schema_name, "")
    _check(instance, sch, "$", base, errs, 0, open_set)
    return list(dict.fromkeys(errs))
