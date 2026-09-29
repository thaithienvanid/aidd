"""A small JSON Schema 2020-12 validator covering the keywords AIDD schemas use.

Supported: $ref (local, a sibling file name, or a sibling schema by its `$id`,
urn:aidd:1:<name>, which resolves to <name>.schema.json), type, const, enum, required,
properties, additionalProperties, items, minItems, maxItems, uniqueItems,
minLength, maxLength, pattern, minimum, maximum, allOf, anyOf, oneOf, not,
if/then/else, and format (date and date-time only). Unknown keywords are
ignored, as the spec allows; tests/helpers.py lists the draft 2020-12
assertions this validator does not implement, and a test keeps them out of
every schema.
Patterns use Python regular expressions with fullmatch semantics for $-anchored
patterns; ECMA-only syntax such as \\p{Letter} is not supported.
tests/test_schema_suite.py runs the official JSON Schema Test Suite for every
supported keyword.
"""

from __future__ import annotations

import datetime as dt
import json
import operator
import re
import urllib.parse
from typing import Any

from . import resources

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
# an array is measured by its length, a number by its value.
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


def _resolve(ref: str, base: Any) -> tuple[Any, Any]:
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


def _fmt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _check(inst: Any, sch: Any, path: str, base: Any, errs: list[str], depth: int = 0) -> None:
    if sch is True or sch == {}:
        return
    if sch is False:
        errs.append(f"{path}: not allowed")
        return
    if not isinstance(sch, dict):
        errs.append(f"{path}: schema must be an object or a boolean, got {_fmt(sch)[:60]}")
        return
    if "$ref" in sch:
        if depth > 64:
            errs.append(f"{path}: $ref cycle")
            return
        try:
            target, name = _resolve(sch["$ref"], base)
        except Exception as exc:
            errs.append(f"{path}: cannot resolve $ref {sch['$ref']!r}: {exc}")
            return
        _check(inst, target, path, name, errs, depth + 1)
    if "type" in sch:
        raw_types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        valid_types = [t for t in raw_types if isinstance(t, str) and t in _TYPES]
        errs += [f"{path}: unknown type {t!r}" for t in raw_types if not (isinstance(t, str) and t in _TYPES)]
        if not valid_types:
            return
        if not any(_TYPES[t](inst) for t in valid_types):
            errs.append(f"{path}: expected {' or '.join(valid_types)}, got {_fmt(inst)[:60]}")
            return
    if "const" in sch and not _equal(inst, sch["const"]):
        errs.append(f"{path}: must be {_fmt(sch['const'])}")
    if "enum" in sch and not any(_equal(inst, e) for e in sch["enum"]):
        errs.append(f"{path}: must be one of {', '.join(map(str, sch['enum']))}; got {_fmt(inst)}")
    for key, kind, fails, message in _LIMITS:
        if key in sch and _TYPES[kind](inst) and fails(inst if kind == "number" else len(inst), sch[key]):
            errs.append(f"{path}: {message.format(sch[key])}")
    if isinstance(inst, str):
        if "pattern" in sch:
            pat = sch["pattern"]
            try:
                rx = re.compile(pat)
                m = rx.search(inst)
                if m and pat.endswith("$") and not pat.endswith(r"\$") and inst[m.end() :] in ("\n", "\r\n"):
                    m = None
                if not m:
                    errs.append(f"{path}: {_fmt(inst)} does not match {pat}")
            except re.error as exc:
                errs.append(f"{path}: invalid pattern {pat!r}: {exc}")
        if sch.get("format") in ("date", "date-time"):
            try:
                _FORMATS[sch["format"]](inst)
            except ValueError:
                errs.append(f"{path}: {_fmt(inst)} is not a valid ISO {sch['format']}")
    if isinstance(inst, list):
        if sch.get("uniqueItems") and any(_equal(inst[i], inst[j]) for i in range(len(inst)) for j in range(i + 1, len(inst))):
            errs.append(f"{path}: items must be unique")
        if "items" in sch:
            for i, item in enumerate(inst):
                _check(item, sch["items"], f"{path}[{i}]", base, errs, depth)
    if isinstance(inst, dict):
        for key in sch.get("required", []):
            if key not in inst:
                errs.append(f"{path}: missing required field {key!r}")
        props = sch.get("properties", {})
        for key, value in inst.items():
            if key in props:
                _check(value, props[key], f"{path}.{key}", base, errs, depth)
            elif "additionalProperties" in sch:
                extra = sch["additionalProperties"]
                if extra is False:
                    errs.append(f"{path}: unknown field {key!r}")
                elif isinstance(extra, dict):
                    _check(value, extra, f"{path}.{key}", base, errs, depth)
    for sub in sch.get("allOf", []):
        _check(inst, sub, path, base, errs, depth)
    if "anyOf" in sch and not any(_ok(inst, s, base) for s in sch["anyOf"]):
        errs.append(f"{path}: matches none of the allowed shapes")
    if "oneOf" in sch:
        hits = sum(1 for s in sch["oneOf"] if _ok(inst, s, base))
        if hits != 1:
            errs.append(f"{path}: must match exactly one allowed shape (matched {hits})")
    if "not" in sch and _ok(inst, sch["not"], base):
        errs.append(f"{path}: matches a forbidden shape")
    if "if" in sch:
        branch = "then" if _ok(inst, sch["if"], base) else "else"
        if branch in sch:
            _check(inst, sch[branch], path, base, errs, depth)


def _ok(inst: Any, sch: Any, base: Any) -> bool:
    errs: list[str] = []
    _check(inst, sch, "$", base, errs, 0)
    return not errs


def validate(instance: Any, schema_name: str) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    errs: list[str] = []
    sch, base = _resolve(schema_name, "")
    _check(instance, sch, "$", base, errs)
    return errs
