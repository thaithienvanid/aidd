"""What a harness's ask rules hold of each `ask` action, and what they cannot, computed from the same patterns the writers write.

For one format, each form of an action (a command pattern, a path the harness's file-read tool asks before) is held in full, held
by a narrower rule (a leading-words format asks at a pattern's first words, or only for the remotes `origin` and `upstream`),
or held by no rule. An action no rule holds is one only the skill asks for (`spec.approve` has no command at all), and
`aidd doctor` names it, so a person never reads "asks before" for an action the harness never prompts for. Some forms no
format can hold (`UNHELD`), and the docs and doctor say so. `command_notes` says when a harness asks where `aidd risk` allows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aidd.kernel import globs
from aidd.risk.commands import normalize
from aidd.risk.harness_rules import (
    API_LABEL,
    COMMON_REMOTES,
    FORMATS,
    api_write_note,
    command_entries,
    harness_patterns,
    harness_read_paths,
    labelled_patterns,
    unwritten,
)
from aidd.risk.rules import LEVEL_RANK, RuleSet
from aidd.risk.shell import split, wrapped

# A form of an action that no format holds: a rule would have to match a command that names nothing to match on.
UNHELD = {
    "git.push": "a push that names no branch, such as `git push` or `git push origin HEAD`, while the default branch is checked out",
}


@dataclass(frozen=True)
class Hold:
    """How one format holds one action: its forms in all, those a rule holds in full, and those only a narrower rule holds."""

    forms: int
    full: int
    narrower: int

    @property
    def none(self) -> int:
        return self.forms - self.full - self.narrower


def asking_actions(rs: RuleSet) -> list[str]:
    """The actions with a rule at `ask`, in the order of the rules."""
    return list(dict.fromkeys(r.action for r in rs.rules if r.level == "ask"))


def hold_counts(rs: RuleSet, default_branch: str | Sequence[str] | None, fmt: str) -> dict[str, Hold]:
    """For each asking action, how `fmt`'s rules hold its forms: the command patterns, the `gh api` set for an action with
    `api_endpoints`, and the file-read paths of an action with `file_reads` (held in full where the harness has a file-read
    rule, else by none)."""
    labelled = labelled_patterns(rs, default_branch)
    gaps = set(unwritten(fmt, [p for _, p in labelled]))
    api_set = [p for action, p in labelled if action == API_LABEL]
    out = {}
    for action in asking_actions(rs):
        spec = rs.actions.get(action) or {}
        patterns = [p for a, p in labelled if a == action] + (api_set if spec.get("api_endpoints") else [])
        full = sum(p not in gaps for p in patterns)
        narrower = sum(p in gaps and bool(command_entries(fmt, [p], list(COMMON_REMOTES))) for p in patterns)
        reads = len((spec.get("file_reads") or {}).get("paths") or []) if harness_read_paths(rs) else 0
        out[action] = Hold(len(patterns) + reads, full + reads * FORMATS[fmt].reads, narrower)
    return out


def held_by_none(holds: dict[str, Hold]) -> list[str]:
    """The actions no rule of the format holds in any form: the skill alone asks for them."""
    return [a for a, h in holds.items() if h.full == 0 and h.narrower == 0]


def held_in_part(holds: dict[str, Hold]) -> dict[str, Hold]:
    """The actions some rule holds but not in every form in full."""
    return {a: h for a, h in holds.items() if (h.full or h.narrower) and h.full < h.forms}


def command_notes(rs: RuleSet, answer: dict) -> list[str]:
    """What a person should know about a command line's answer that no action says. Today it is one: a part of the line
    that the harnesses' `gh api` patterns match as typed, while `aidd risk` reads it exactly as a lower level than `ask`,
    such as a GET with a field or a GraphQL query. `answer` is `command_level`'s."""
    asked = [p for p in harness_patterns(rs, None) if p.startswith("gh api")]
    notes = []
    for part in split(answer["command"]):
        typed = {normalize(c) for c in (part, *wrapped(part))}
        levels = [a["level"] for a in answer["actions"] if a["command"] in typed]
        if max(levels, key=LEVEL_RANK.__getitem__, default="allow") != "ask" and any(globs.match_text(p, part) for p in asked):
            notes.append(api_write_note())
    return list(dict.fromkeys(notes))
