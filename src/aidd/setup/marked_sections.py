"""The sections aidd writes into an instruction file (AGENTS.md and the files agents read in its place), each between its
own marks, as Ansible's blockinfile does: `<!-- aidd -->` opens aidd's section and `<!-- /aidd -->` closes it, and
`<!-- aidd-team -->` and `<!-- /aidd-team -->` do the same for the team section. The text between a pair is aidd's to
replace. Everything outside it is the person's.

A section whose end mark is missing ends at the next `#` or `##` heading, which may cut a person's own lines off, so
aidd leaves such a section as it is and says so.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from aidd import config

AGENTS_MARK = "<!-- aidd -->"
TEAM_MARK = config.TEAM_MARK
_OPEN_MARKS = (AGENTS_MARK, TEAM_MARK)
SKILL_CLAUSE = "read the skill at `.agents/skills/aidd/SKILL.md` and `.agents/skills/aidd/references/graph.md`"
PLUGIN_PHRASE = "load the `aidd` skill (installed as a plugin)"


def end_mark(mark: str) -> str:
    """The mark that closes the section `mark` opens: `<!-- aidd -->` closes with `<!-- /aidd -->`."""
    return mark.replace("<!-- ", "<!-- /", 1)


@dataclass(frozen=True)
class Section:
    """A section's place in a text: from its opening mark's line to its end, and whether an end mark closes it."""

    start: int
    end: int
    closed: bool


def _lines(text: str) -> Iterator[tuple[int, int, str]]:
    """(start, end, line) of each line of `text` outside a fenced code block: a mark in a code sample is no mark."""
    fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            fence = not fence
        elif not fence:
            yield offset, offset + len(line), stripped
        offset += len(line)


def mark_lines(text: str, mark: str) -> list[tuple[int, int]]:
    """(start, end) of each line that is `mark` alone, outside a code fence."""
    return [(start, end) for start, end, line in _lines(text) if line == mark]


def sections(text: str, mark: str) -> list[Section]:
    """Every section that opens at `mark`, in order. A mark counts only on a line of its own, outside a code fence, with a
    `## ` heading on the next line. A closed section runs to the end of its end mark's line. One with no end mark runs to the next
    `#` or `##` heading, or the next mark of aidd's."""
    lines = list(_lines(text))
    found = []
    for n, (start, line_end, line) in enumerate(lines):
        if line != mark or not text.startswith("## ", line_end):
            continue
        after = lines[n + 1 :]
        # An end mark closes only the section before the next opening mark: a later section's end mark is not this one's.
        after_next = next((i for i, (_, _, other) in enumerate(after) if other in _OPEN_MARKS), len(after))
        closing = next((end for _, end, other in after[:after_next] if other == end_mark(mark)), None)
        if closing is not None:
            found.append(Section(start, closing, True))
            continue
        # The heading right after the mark opens the section; the next heading or mark of aidd's ends it.
        nxt = next((s for s, _, other in after if s > line_end and (other.startswith(("# ", "## ")) or other in _OPEN_MARKS)), None)
        found.append(Section(start, len(text) if nxt is None else nxt, False))
    return found


def line_range(text: str, found: Section) -> tuple[int, int]:
    """The first and last line (counted from 1) of `found` in `text`, without the blank lines that end it."""
    first = text.count("\n", 0, found.start) + 1
    body = text[found.start : found.end].rstrip("\n")
    return first, first + body.count("\n")


def left_alone(text: str, mark: str, section: str) -> list[Section]:
    """The sections at `mark` that `refresh` leaves as they are: those with no end mark, except one that already reads as `section`."""
    return [f for f in sections(text, mark) if not f.closed and text[f.start : f.end].rstrip("\n") != section.rstrip("\n")]


def refresh(text: str, mark: str, section: str) -> str:
    """`text` with each closed section at `mark` replaced by `section` (which carries both marks); `left_alone` names the
    ones it keeps. Every other line stays."""
    for found in reversed(sections(text, mark)):
        if not found.closed or text[found.start : found.end].rstrip("\n") == section.rstrip("\n"):
            continue
        tail = text[found.end :]
        text = text[: found.start] + section.rstrip("\n") + "\n" + tail
    return text
