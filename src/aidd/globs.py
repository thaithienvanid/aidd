"""Repo-relative path globs.

`*` and `?` stay inside one path segment, `**` spans segments, and `**/` may
match nothing. A pattern with no wildcard matches that path and everything
under it, so `src/checkout` covers `src/checkout/x.py`. A trailing `/` or `/**`
means the same thing, so `.claude/**` also covers a file or symlink named
`.claude`. Brackets are literal characters, never a class.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable

_WILD = "*?"
MAX_PATTERN_LENGTH = 512

# Pattern tokens. Matching walks them against the path with a table over (token, position), so the time is
# linear in each (tokens x path length) whatever the pattern: no backtracking, however many `**` it holds.
_LIT, _STAR, _QMARK, _DSTAR, _DSTAR_SLASH = range(5)


class GlobError(ValueError):
    """A pattern the matcher refuses, such as one longer than MAX_PATTERN_LENGTH."""


def _fold(c: str) -> str:
    """One character, case-folded without changing the length (so positions still line up)."""
    low = c.lower()
    return low if len(low) == 1 else c


def _normalize(pattern: str) -> str:
    while "**/**" in pattern:
        pattern = pattern.replace("**/**", "**")
    while "***" in pattern:
        pattern = pattern.replace("***", "**")
    return pattern


@functools.lru_cache(maxsize=8192)
def _compile(pattern: str, fold_case: bool = False) -> tuple[tuple[tuple[int, str], ...], bool]:
    """The pattern as tokens, and whether it also covers everything under the matched path."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise GlobError(f"glob pattern is {len(pattern)} characters long; the limit is {MAX_PATTERN_LENGTH}: {pattern[:60]!r}...")
    pat = _normalize(pattern)
    prefix_match = pat.endswith("/") or not any(c in pat for c in _WILD)
    pat = pat.rstrip("/") if pat.endswith("/") else pat
    if pat.endswith("/**"):  # also `dir/**/`: a trailing slash means the same
        pat, prefix_match = pat[:-3], True
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out.append((_DSTAR_SLASH, ""))  # nothing, or anything that ends with `/`
            i += 3
        elif pat.startswith("**", i):
            out.append((_DSTAR, ""))  # anything, across segments
            i += 2
        elif pat[i] == "*":
            out.append((_STAR, ""))  # anything within one segment
            i += 1
        elif pat[i] == "?":
            out.append((_QMARK, ""))
            i += 1
        else:
            out.append((_LIT, _fold(pat[i]) if fold_case else pat[i]))
            i += 1
    return tuple(out), prefix_match


def match(pattern: str, path: str, fold_case: bool = False) -> bool:
    tokens, prefix_match = _compile(pattern, fold_case)
    s = "".join(map(_fold, path)) if fold_case else path
    n = len(s)
    # nxt[j]: whether tokens[i+1:] match s[j:]; filled from the last token backwards.
    nxt = [j == n or (prefix_match and s[j] == "/") for j in range(n + 1)]
    for kind, lit in reversed(tokens):
        cur = [False] * (n + 1)
        if kind == _LIT:
            for j in range(n):
                cur[j] = s[j] == lit and nxt[j + 1]
        elif kind == _QMARK:
            for j in range(n):
                cur[j] = s[j] != "/" and nxt[j + 1]
        elif kind == _STAR:
            cur[n] = nxt[n]
            for j in range(n - 1, -1, -1):
                cur[j] = nxt[j] or (s[j] != "/" and cur[j + 1])
        elif kind == _DSTAR:
            cur[n] = nxt[n]
            for j in range(n - 1, -1, -1):
                cur[j] = nxt[j] or cur[j + 1]
        else:  # _DSTAR_SLASH: skip it, or consume up to and including some later `/`
            later = False
            cur[n] = nxt[n]
            for j in range(n - 1, -1, -1):
                later = (s[j] == "/" and nxt[j + 1]) or later
                cur[j] = nxt[j] or later
        nxt = cur
    return nxt[0]


def match_any(patterns: Iterable[str], path: str, fold_case: bool = False) -> bool:
    return any(match(p, path, fold_case) for p in patterns)


def first_match(patterns: Iterable[str], path: str, fold_case: bool = False) -> str | None:
    return next((p for p in patterns if match(p, path, fold_case)), None)


def is_catch_all(pattern: str) -> bool:
    """True for a pattern that matches every or nearly every path without a concrete directory root."""
    pat = _normalize(pattern).strip()
    if not pat or pat in ("**", "**/*", "**/", "**/*.*"):
        return True
    if not pat.startswith("**"):
        return False
    segments = [s for s in pat.split("/") if s and s != "**"]
    has_fixed_segment = any(not any(c in s for c in _WILD) for s in segments)
    return not literal_prefix(pat) and not has_fixed_segment


def sample_path(pattern: str) -> str:
    """A concrete path the pattern matches, used to reason about patterns before a diff exists."""
    pat = _normalize(pattern)
    s = pat.rstrip("/")
    s = s.replace("**/", "x/").replace("**", "x/y").replace("*", "x").replace("?", "x")
    if pat.endswith("/") or not any(c in pat for c in _WILD):
        s = s + "/x"
    return s


def literal_prefix(pattern: str) -> str:
    cut = min([len(pattern)] + [j for c in _WILD if (j := pattern.find(c)) != -1])
    head = pattern[:cut]
    return head if cut == len(pattern) else head[: head.rfind("/") + 1]


def overlap(a: str, b: str) -> bool:
    """Conservative: True when two patterns could match a common path."""
    if match(a, sample_path(b)) or match(b, sample_path(a)):
        return True
    pa, pb = literal_prefix(a), literal_prefix(b)
    if any(c in a or c in b for c in _WILD):
        return pa.startswith(pb) or pb.startswith(pa)
    return False
