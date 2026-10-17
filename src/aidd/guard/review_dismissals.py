"""REVIEW.md's dismissed findings: what looks like one, in every reading of the list, and whether an edit adds or
changes one.
"""

from __future__ import annotations

import re

# A spike's outcome in an exploration (`exploration.md` in specs/<ID>/explore/<slug>/ or specs/explore/<topic>/) is a
# person's decision too: no aidd-team role adds or changes it. The key, in any YAML or TOML spelling, so front matter
# that does not parse is still read as naming it (fail-closed).
OUTCOME_KEY = re.compile(r"""(?:^|[\s{,\[])["']?outcome["']?\s*[:=\]]""", re.M)


# A dismissed review finding in REVIEW.md is a person's decision too: no aidd-team role adds or changes one, so an agent
# cannot hide its own finding. A review honors only DISMISSAL_EXACT lines under the first line that reads exactly
# DISMISSAL_HEADING, up to the next line that starts with `#`. The guard is wider than that reader on purpose:
# - any added or changed line that looks like a dismissal (DISMISSAL_LIKE), in any common shape and anywhere in the file;
# - any edit that brings a dismissal-like line under a heading that names the list, however a reader finds the heading
#   and where the list ends (moving lines, removing or renaming a heading).
# Taking a line out only brings the finding back, and every other edit to REVIEW.md is left to the other rules.
REVIEW_POLICY = "REVIEW.md"
DISMISSAL_HEADING = "## Dismissed findings"
DISMISSAL_EXACT = re.compile(
    r"- (?P<file>[^|\s](?:[^|]*[^|\s])?) \| (?P<kind>[^|\s](?:[^|]*[^|\s])?) \| (?P<hash>[0-9a-f]{16}) \| "
    r"(?P<who>[^|\s](?:[^|]*[^|\s])?) \| (?P<date>\d{4}-\d{2}-\d{2}) \| (?P<why>[^|\s](?:[^|]*[^|\s])?)\Z"
)
# A bar of any common look (ASCII, fullwidth, box drawing, divides, broken bar), and a hex token of 12 to 64 characters.
_BARS = "|\uff5c\u2502\u2223\u00a6"
_HEX_TOKEN = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{12,64}(?![0-9A-Za-z])")
_LIST_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*dismiss", re.I)
_ANY_HEADING = re.compile(r"^\s{0,3}#")
DISMISSAL_DENY = (
    "this edit adds, changes, or moves a line shaped like a dismissed finding (`- <file> | <kind> | <hash> | ...`), and only "
    "a person adds a dismissal. Report the finding, and leave its dismissal to the person who decides"
)


def dismissal_like(line: str) -> bool:
    """Whether a line looks like a dismissed finding in any common shape: at least two bars and a hex token between them
    or beside them, with or without a list marker, a number, a table's bars, tabs, or backticks."""
    bars = sum(line.count(c) for c in _BARS)
    return bars >= 2 and bool(_HEX_TOKEN.search(line))


def _lines(text: str | None) -> list[str]:
    """Lines as git and a reader see them: split on a newline only (with a trailing carriage return dropped), never on
    the other breaks `str.splitlines` honors, such as U+2028, so such a break cannot cut a dismissal in two."""
    return [ln[:-1] if ln.endswith("\r") else ln for ln in (text or "").split("\n")]


def _views(text: str | None) -> list[set[str]]:
    """What each reading of the list would honor: the documented one (exact lines under the first exact heading, up to
    the next `#` line), and wider ones (dismissal-like lines under any heading that names it, to the next heading, or to
    the end of the file). An edit that grows any of them changes what some reader honors."""
    lines = _lines(text)
    exact: set[str] = set()
    near: set[str] = set()
    rest: set[str] = set()
    first = next((i for i, ln in enumerate(lines) if ln == DISMISSAL_HEADING), None)
    if first is not None:
        for ln in lines[first + 1 :]:
            if ln.startswith("#"):
                break
            if DISMISSAL_EXACT.match(ln):
                exact.add(ln)
    inside = False
    seen_heading = False
    for ln in lines:
        if _LIST_HEADING.match(ln):
            inside = seen_heading = True
            continue
        if _ANY_HEADING.match(ln):
            inside = False
        if dismissal_like(ln):
            if inside:
                near.add(ln.strip())
            if seen_heading:
                rest.add(ln.strip())
    return [exact, near, rest]


def _dismissal_lines(text: str | None) -> set[str]:
    """Every line of `text` that looks like a dismissed finding, stripped."""
    return {ln.strip() for ln in _lines(text) if dismissal_like(ln)}


def changes_dismissals(rel: str, old_text: str | None, new_text: str | None) -> bool:
    """Whether the edit adds or changes a dismissal-like line anywhere in REVIEW.md, or brings one under the list's
    heading in any reading of it. A removal is not a change here: it brings a finding back, and never hides one."""
    if new_text is None or rel.casefold() != REVIEW_POLICY.casefold():
        return False
    if _dismissal_lines(new_text) - _dismissal_lines(old_text):
        return True
    return any(after - before for after, before in zip(_views(new_text), _views(old_text), strict=True))
