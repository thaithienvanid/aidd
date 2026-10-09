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


def normal_dir(folder: str) -> str:
    """A folder the config names, in the one form git prints paths in: no `./` or `.` segment, no doubled or trailing
    slash. The repository's top comes back as `.`, which no folder may be (`under` refuses it). Without this, `./custom`
    would build `./custom/standards/**`, which matches no path."""
    parts = [p for p in folder.split("/") if p not in ("", ".")]
    return "/".join(parts) or "."


def under(folder: str, rest: str) -> str:
    """A repository-relative path or pattern inside a configured folder. ValueError for the repository's top: a folder
    there would turn a role area or a rule built from it into one over the whole repository."""
    base = normal_dir(folder)
    if base == ".":
        raise ValueError(f"the folder {folder!r} is the repository's top; name a folder inside the repository")
    return f"{base}/{rest}"


class _Pattern:
    """A compiled pattern: its tokens, and the literal text every match must hold, checked first (in C) so most paths are
    turned away without the table walk. Each run of literal tokens consumes exactly those characters, in order, so a path
    that lacks one of them, or does not start with the literal prefix, or (without prefix matching) end with the literal
    suffix, cannot match."""

    __slots__ = ("tokens", "prefix_match", "prefix", "suffix", "runs", "literal")

    def __init__(self, tokens: tuple[tuple[int, str], ...], prefix_match: bool):
        self.tokens, self.prefix_match = tokens, prefix_match
        runs: list[str] = []
        cur: list[str] = []
        for kind, lit in tokens:
            if kind == _LIT:
                cur.append(lit)
            elif cur:
                runs.append("".join(cur))
                cur = []
        tail = "".join(cur)
        if tail:
            runs.append(tail)
        self.runs = tuple(runs)
        wild = next((i for i, (kind, _) in enumerate(tokens) if kind != _LIT), None)
        # A pattern with no wildcard at all: the path itself, or everything under it.
        self.literal: str | None = tail if wild is None else None
        self.prefix = "".join(lit for _, lit in tokens[: len(tokens) if wild is None else wild])
        self.suffix = "" if prefix_match or wild is None or not tail else tail


@functools.lru_cache(maxsize=8192)
def _compile(pattern: str, fold_case: bool = False) -> _Pattern:
    """The pattern as tokens, whether it also covers everything under the matched path, and its literal parts."""
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
    return _Pattern(tuple(out), prefix_match)


@functools.lru_cache(maxsize=65536)
def _folded(path: str) -> str:
    """A path case-folded once, however many patterns it meets."""
    return "".join(map(_fold, path))


def _walk(tokens: tuple[tuple[int, str], ...], prefix_match: bool, s: str) -> bool:
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


def _match_compiled(c: _Pattern, s: str) -> bool:
    if c.literal is not None:
        return s == c.literal or (s.startswith(c.literal) and s[len(c.literal)] == "/")
    if not s.startswith(c.prefix) or (c.suffix and not s.endswith(c.suffix)):
        return False
    at = 0
    for run in c.runs:
        at = s.find(run, at)
        if at < 0:
            return False
        at += len(run)
    return _walk(c.tokens, c.prefix_match, s)


def match(pattern: str, path: str, fold_case: bool = False) -> bool:
    return _match_compiled(_compile(pattern, fold_case), _folded(path) if fold_case else path)


def match_any(patterns: Iterable[str], path: str, fold_case: bool = False) -> bool:
    s = _folded(path) if fold_case else path
    return any(_match_compiled(_compile(p, fold_case), s) for p in patterns)


def first_match(patterns: Iterable[str], path: str, fold_case: bool = False) -> str | None:
    s = _folded(path) if fold_case else path
    return next((p for p in patterns if _match_compiled(_compile(p, fold_case), s)), None)


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


def literal_form(pattern: str) -> str:
    """The plainest path a pattern names: `**/` dropped, a trailing `/**` or `/` dropped, and each other wildcard read as
    `x`. A pattern that matches another's plainest path makes that other one redundant in a list: `**/X` covers `X`,
    and `.clinerules` (no wildcard, so everything under it too) covers `.clinerules/**`."""
    pat = _normalize(pattern).rstrip("/")
    pat = pat.removesuffix("/**")
    return pat.replace("**/", "").replace("**", "x").replace("*", "x").replace("?", "x") or "x"


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
