"""The path globs a harness's own file-edit tool asks before: the test files of the Specs whose tests are frozen
(which the caller reads from the Spec files), written as each harness reads a path (`harness_rules.Format.edits`)."""

from __future__ import annotations

from collections.abc import Sequence

from aidd.kernel import globs

# What a harness reads as syntax in a path, or what breaks the rule's own text (`Edit(<path>)`).
_UNSAFE = frozenset("[]{}()\\")


def edit_writable(path: str) -> bool:
    """Whether every harness reads `path` alike: short printable ASCII with no space and none of _UNSAFE."""
    return path.isascii() and path.isprintable() and " " not in path and len(path) <= globs.MAX_PATTERN_LENGTH and _UNSAFE.isdisjoint(path)


def harness_edit_paths(test_globs: Sequence[str]) -> list[str]:
    """The path globs a harness's file-edit tool asks before, each once. A path with no wildcard, and a folder (`dir/` or
    `dir/**`), covers what is under it as the repository's globs do, so it gets both the path and its `/**`. A path a
    harness would read as syntax gets no rule, so no ask guards that file: one over MAX_PATTERN_LENGTH,
    or with a space, a bracket, a brace, a parenthesis, a backslash, or a character that is not printable ASCII."""
    out: list[str] = []
    for g in test_globs:
        folder = g.endswith(("/", "/**"))
        base = g.removesuffix("/**").rstrip("/") if folder else g
        paths = [base, f"{base}/**"] if folder or not globs.is_pattern(base) else [base]
        out += [p for p in paths if p and edit_writable(p)]
    return list(dict.fromkeys(out))
