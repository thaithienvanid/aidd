"""The sections aidd writes into an instruction file (AGENTS.md and the files agents read in its place), each between its
own marks, as Ansible's blockinfile does: `<!-- aidd -->` opens aidd's section and `<!-- /aidd -->` closes it, and
`<!-- aidd-team -->` and `<!-- /aidd-team -->` do the same for the team section. The text between a pair is aidd's to
replace. Everything outside it is the person's.

A file an older aidd wrote has the opening mark only. Its section then ends at the next `#` or `##` heading, which may
cut a person's own lines off, so aidd replaces such a section only when its text is one aidd shipped.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from aidd import config

AGENTS_MARK = "<!-- aidd -->"
TEAM_MARK = config.TEAM_MARK
_OPEN_MARKS = (AGENTS_MARK, TEAM_MARK)
VERIFY_HEADING = "### Verifying your work"
PLUGIN_PHRASE = "load the `aidd` skill (installed as a plugin)"
VENDORED_PHRASE = "load the skill at `.agents/skills/aidd/SKILL.md`"

# SHA-256 of the whitespace-collapsed text of each aidd section's lead that aidd shipped (templates/AGENTS.snippet.md),
# before its verification block: the gate-era text, and the text of this release. A section with an end mark needs none.
SHIPPED_LEADS = frozenset(
    {
        "77d5381604088f29e33f6617ae0944079f501af9b21a9e0f650bdf0029ae1a88",
        "4cb6ada1a8bc6881445a1041d1bbf01a026d424b1b910ba46ecf17299b3a6a32",
    }
)


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
    `## ` heading on the next line. A closed section runs to the end of its end mark's line. An older one runs to the next
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


def lead_is_shipped(old: str, blocks: Iterable[str] = ()) -> bool:
    """Whether `old`, an older section without an end mark, is a text aidd shipped: its lead matches a shipped one, and
    what follows is none, or exactly one of the verification `blocks` aidd writes (compared apart from spacing). A line
    of the person's after the lead is not aidd's, so it makes the section an edited one."""
    cut = old.find(VERIFY_HEADING)
    lead = old if cut == -1 else old[:cut]
    lead = " ".join(lead.replace(PLUGIN_PHRASE, VENDORED_PHRASE).split())
    rest = "" if cut == -1 else " ".join(old[cut:].split())
    return hashlib.sha256(lead.encode()).hexdigest() in SHIPPED_LEADS and (not rest or rest in {" ".join(b.split()) for b in blocks})


def line_range(text: str, found: Section) -> tuple[int, int]:
    """The first and last line (counted from 1) of `found` in `text`, without the blank lines that end it."""
    first = text.count("\n", 0, found.start) + 1
    body = text[found.start : found.end].rstrip("\n")
    return first, first + body.count("\n")


def _replaceable(text: str, found: Section, section: str, shipped: Callable[[str], bool]) -> bool:
    """Whether `refresh` may replace `found` with `section`: it is closed, already reads as `section` without its end mark, or aidd shipped it."""
    bare = section.rstrip("\n").rsplit("\n", 1)[0].rstrip("\n")
    return found.closed or text[found.start : found.end].rstrip("\n") == bare or shipped(text[found.start : found.end])


def left_alone(text: str, mark: str, section: str, shipped: Callable[[str], bool] = lambda _: False) -> list[Section]:
    """The sections at `mark` that `refresh` leaves as they are: older ones, with no end mark, that are not a text aidd shipped."""
    return [f for f in sections(text, mark) if text[f.start : f.end].rstrip("\n") != section.rstrip("\n") and not _replaceable(text, f, section, shipped)]


def refresh(text: str, mark: str, section: str, shipped: Callable[[str], bool] = lambda _: False) -> str:
    """`text` with each section at `mark` replaced by `section` (which carries both marks); `left_alone` names the ones it keeps.
    A closed section is replaced. An older section is replaced when it already reads as `section` without its end mark, or
    when `shipped` says aidd wrote it, and else left as it is. Every other line stays."""
    for found in reversed(sections(text, mark)):
        old = text[found.start : found.end]
        if old.rstrip("\n") == section.rstrip("\n"):
            continue
        if not _replaceable(text, found, section, shipped):
            continue
        tail = text[found.end :]
        text = text[: found.start] + section.rstrip("\n") + "\n" + ("\n" if tail and not found.closed else "") + tail
    return text
