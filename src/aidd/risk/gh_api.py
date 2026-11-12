"""Which actions a `gh api` call writes, read from its parsed arguments instead of its text.

A glob cannot follow gh's flags in every order (`-X POST`, `-XPOST`, `--method=POST`, the endpoint before or after the
flags, a field that implies POST), so `aidd risk --command` reads a `gh api` call here, from its parsed arguments. The
harness ask rules do not use this: a harness matches command text, so it asks before any `gh api` write
(`harness_rules.api_write_patterns`). `glab api` has no parser, and its patterns stay in an action's `commands`.

This module holds gh's own syntax: its flags, its methods, and which flags send a body. Which endpoint is which action
is data, the `api_endpoints` of each action, so nothing here names an action.

A GraphQL call is read as a write to the endpoint `graphql#mutation` when its query holds a mutation or aidd cannot read
it: a query from a file (`query=@file`, `--input`), from standard input, or from a shell variable or substitution. aidd
reads no file the command names. The ruleset's pin to GitHub Actions stays the control (GUIDE.md, "Branch protection is
the hard stop").
"""

from __future__ import annotations

import re

from aidd.kernel import globs
from aidd.risk.shell import Word, tokens

# The flags are gh's own syntax (`gh help api`): the ones that take a value, and which of them make a request body.
_SHORT_VALUE = frozenset("XfFHqtp")
_LONG_VALUE = frozenset({"method", "raw-field", "field", "header", "jq", "template", "preview", "input", "hostname", "cache"})
BODY_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")  # the flags that send a request body, so make it a POST
_FIELDS = set(BODY_FLAGS) - {"--input"}
_BODY = set(BODY_FLAGS)
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
_READ_METHODS = {"GET", "HEAD"}
# A GraphQL write has no endpoint of its own (gh posts to `graphql`), so it is read as this one, for the data to name.
GRAPHQL_WRITE = "graphql#mutation"
_EXPANSION = re.compile(r"\$\{[^}]*\}?|\$\([^)]*\)?|\$\w+|`[^`]*`?")  # a variable or a substitution in a word
_METHOD_PREFIX = re.compile(r"([A-Z]+(?:\|[A-Z]+)*) (.+)", re.S)


def entry_parts(entry: str) -> tuple[list[str], str]:
    """An `api_endpoints` entry as (the methods it applies to, its glob); no methods means any write."""
    prefix = _METHOD_PREFIX.fullmatch(entry)
    return (prefix.group(1).split("|"), prefix.group(2)) if prefix else ([], entry)


def _parse(args: list[Word]) -> tuple[list[Word], list[tuple[str, Word]]]:
    """The positional arguments and the (flag, value) pairs of `gh api`'s arguments. A short flag may carry its value
    (`-XPOST`, `-X=POST`) or sit in a run of short flags (`-iXPOST`); a long one is `--method=POST` or `--method POST`;
    `--` ends the flags. A value keeps what its word says about the shell expanding it."""
    positional: list[Word] = []
    flags: list[tuple[str, Word]] = []
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            positional += args[i:]
            break
        if arg.startswith("--"):
            name, eq, text = arg[2:].partition("=")
            value = Word(text, arg.expands)
            if name in _LONG_VALUE and not eq and i < len(args):
                value, i = args[i], i + 1
            flags.append(("--" + name, value))
        elif arg.startswith("-") and len(arg) > 1:
            for pos, char in enumerate(arg[1:], 1):
                if char in _SHORT_VALUE:
                    value = Word(arg[pos + 1 :].removeprefix("="), arg.expands)
                    if not value and i < len(args):
                        value, i = args[i], i + 1
                    flags.append(("-" + char, value))
                    break
        else:
            positional.append(arg)
    return positional, flags


def _call(command: str) -> tuple[list[Word], list[tuple[str, Word]]] | None:
    """The positional arguments and flags of a `gh api` call, or None for any other command. A program by its path is
    read by its name in `shell.wrapped`, which hands it over as `gh`."""
    words = tokens(command)
    if len(words) < 2 or words[0] != "gh" or words[1] != "api":
        return None
    return _parse(words[2:])


def _endpoint(arg: str) -> str:
    return arg.split("?", 1)[0].strip("/")


def _endpoint_texts(endpoint: str) -> tuple[list[str], bool]:
    """The texts to match an endpoint by, and whether it is blind: built wholly from expansions (`"$A/$B"`, `"${EP:-x}"`),
    so it names nothing. With some text of its own (`repos/$SLUG`), each expansion also stands for one segment and for two,
    so `repos/o/r` matches `repos/$SLUG` and `repos/$O/$R/issues` does not match `repos/*/*`."""
    parts = _EXPANSION.split(endpoint)
    if len(parts) == 1:
        return [endpoint], False
    if not "".join(parts).strip("/"):
        return [endpoint], True
    return [endpoint, *("x/x".join(parts), "x".join(parts))], False


def _graphql_write(flags: list[tuple[str, Word]]) -> bool:
    """Whether a GraphQL call sends a mutation, or a query aidd cannot read: one from a file (`@path`, `@-`), from a
    `--input` file, or built by the shell (a variable, a substitution, `$'...'`). A `$id` inside single quotes is GraphQL's
    own, so it reads as text."""
    for flag, value in flags:
        if flag == "--input":
            return True
        if flag in _FIELDS and value.partition("=")[0] == "query":
            text = value.partition("=")[2]
            if value.expands or text.startswith("@") or re.search(r"\bmutation\b", text):
                return True
    return False


def gh_api_actions(actions: dict[str, dict], command: str) -> list[str]:
    """The ids of the `actions` a simple command writes when it is a `gh api` call, or none for any other command and
    for a read: a GET or HEAD that sends no field or input. An action's `api_endpoints` entry is a glob, with the
    methods it applies to before it (`DELETE */git/refs/*`), or for any write with none. It is matched, ignoring case,
    against the endpoint, then against the endpoint and the call's field values after a space, so a glob can name what a
    dispatch carries (`*dispatches*deploy*`). A file given to `--input` shows as `--input file`. A method aidd cannot
    read matches every entry, and so does an endpoint the shell builds whole (`"$A/$B"`), for a write; `repos/$SLUG` and
    `repos/$O/$R/...` match by their text, each expansion read as one segment or two. A `?` in the glob is one path
    segment, so an entry cannot name a literal `?`, and the endpoint's query string is cut before matching."""
    call = _call(command)
    if call is None:
        return []
    positional, flags = call
    endpoints = [_endpoint(p) for p in positional]
    methods = [v.upper() for f, v in flags if f in ("-X", "--method")]
    method = methods[-1] if methods else "POST" if any(f in _BODY for f, _ in flags) else "GET"
    if any(e == "graphql" or e.endswith("/graphql") for e in endpoints):
        if not _graphql_write(flags):
            return []
        endpoints, method = [GRAPHQL_WRITE], "POST"  # the query decides, not the method
    if method in _READ_METHODS:
        return []
    fields = " ".join((f"--input {v}" if f == "--input" else v) for f, v in flags if f in _BODY)
    seen = [_endpoint_texts(e) for e in endpoints]
    blind = any(b for _, b in seen)
    targets = [t for texts, _ in seen for e in texts for t in (e, f"{e} {fields}")]
    found = []
    for action, spec in actions.items():
        for entry in spec.get("api_endpoints") or []:
            allowed, pattern = entry_parts(entry)
            if allowed and method in _METHODS and method not in allowed:
                continue
            if (blind and not pattern.startswith("graphql#")) or any(globs.match_text(pattern.lower(), t.lower(), segments=True) for t in targets):
                found.append(action)
                break
    return found


def ref_target(command: str) -> tuple[str, str] | None:
    """The ref a `gh api` call moves, as (type, name): `branch` or `tag` with the name `heads/` or `tags/` gives it, or
    `default` for the repository's default branch and for a ref aidd cannot read (a variable, or gh's `{branch}`, the
    current branch). The ref comes from the endpoint (`git/refs/heads/x`), the `ref` field of a new ref, or the `branch`
    of a file write (`contents`) or the `base` of a merge (`merges`), which name the default branch when left out. None
    when the command is no `gh api` call."""
    call = _call(command)
    if call is None:
        return None
    positional, flags = call
    field = lambda key: next((v.partition("=")[2] for f, v in flags if f in _FIELDS and v.partition("=")[0] == key), "")  # noqa: E731
    endpoints = [_endpoint(p) for p in positional]
    name = ""
    if any(re.search(r"/(contents/|merges$)", e) for e in endpoints):
        name = field("branch") or field("base")
    for e in endpoints:
        if found := re.search(r"git/refs/?(.*)", e, re.I):
            name = found.group(1) or field("ref")  # a ref created by POST names itself in a field
            break
    name = name.removeprefix("refs/")
    if name.startswith("tags/"):
        return "tag", name.removeprefix("tags/")
    name = name.removeprefix("heads/")
    return ("default", "") if not name or any(c in name for c in "${`") else ("branch", name)
