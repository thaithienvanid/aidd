"""Why a step comes next, in one line, read from the data that owns the reason: the loop's lanes and its decision rights
(schemas/roles.json), and the meanings and descriptions the schemas give. Nothing here restates a rule; each code names
where its reason lives, and the line is that text."""

from __future__ import annotations

import functools
import re

from aidd import config, knowledge
from aidd.kernel import resources

# Where each step's reason lives. ("lane", step): the lane the item's route takes, and the loop step it is at; a step that
# lane does not run, such as Specify on the fast lane, is read on the spec lane, which runs every Spec's Specify. ("decision",
# label): the loop's decision right with that label, which the loop leaves to a person. ("schema", file, pointer, n): the n-th
# sentence of the description or meaning at that JSON pointer (n is 0 when absent). ("needs", file, pointer): what the step
# needs, the noun phrase there. ("stays", file, pointer): the state an object stays in, the first clause there. A code with
# no entry is finished work, or a step whose reason no data owns. Each reason is one sentence of at most 35 words.
SOURCES: dict[str, tuple] = {
    "spec.emergency": ("lane", "Implement"),
    "spec.triage": ("needs", "spec.schema.json", "/properties/triage/description"),
    "spec.blocked_by": ("lane", "Implement"),
    "spec.blocked": ("schema", "spec.schema.json", "/properties/blockers/description", 1),
    "spec.planned": ("lane", "Specify"),
    "spec.draft": ("lane", "Specify"),
    "spec.ask_approval": ("lane", "Specify"),
    "spec.consumers": ("lane", "Specify"),
    "spec.approval": ("decision", "D2"),
    "spec.approved": ("lane", "Implement"),
    "spec.in_progress": ("lane", "Implement"),
    "spec.merge": ("decision", "D3"),
    "spec.outcome_due": ("schema", "spec.schema.json", "/properties/hypothesis/description"),
    "spec.rolled_back": ("schema", "common.schema.json", "/$defs/status/x-meanings/rolled_back"),
    "intent.agree": ("decision", "D1"),
    "intent.slice": ("lane", "Specify"),
    "intent.close": ("schema", "intent.schema.json", "/properties/status/description"),
    "exploration.open": ("stays", "exploration.schema.json", "/properties/status/description"),
}

# The lane each route takes, as the lane's own meaning says (common.schema.json, `lane`).
LANE_OF = {"minor": "fast", "normal": "spec", "major": "spec", "emergency": "emergency"}
_LABEL = re.compile(r"^D[0-9]+ ")


def _pointer(doc: object, pointer: str) -> str:
    for part in pointer.strip("/").split("/"):
        doc = doc[part] if isinstance(doc, dict) else None
    return doc if isinstance(doc, str) else ""


def _sentence(text: str, n: int = 0) -> str:
    """The n-th sentence of `text`, with its period."""
    parts = text.split(". ")
    found = parts[n] if n < len(parts) else ""
    return found if not found or found.endswith(".") else found + "."


@functools.cache
def _loop() -> dict:
    return knowledge.roles()["loop"]


def lane_steps(lane: str) -> str:
    """The steps a lane runs, as the loop writes them, without the routes it names first."""
    return str(_loop()["lanes"][lane]).partition(": ")[2]


def decision_right(label: str) -> dict:
    """The loop's decision right whose `decision` starts with `label`, such as `D2` or `A choice`."""
    return next(d for d in _loop()["decision_rights"] if str(d["decision"]).startswith(f"{label} "))


def step_reason(code: str, route: object = None) -> str:
    """Why step `code` comes next, in one line, or "" when no data owns a reason for it. `route` picks the lane."""
    source = SOURCES.get(code)
    if source is None:
        return ""
    if source[0] == "lane":
        lane = "emergency" if code == "spec.emergency" else LANE_OF.get(str(route), "spec")
        if source[1] not in lane_steps(lane):
            lane = "spec"
        return f'"{config.lane_words()[lane]}" runs {lane_steps(lane)}, and this is at {source[1]}'
    if source[0] == "escalates":
        right = decision_right(source[1])
        return f"{str(right['decision']).partition(':')[0]}, unless {right['escalates_when']}; then a person decides"
    if source[0] == "decision":
        right = decision_right(source[1])
        name = _LABEL.sub("", str(right["decision"])).partition(":")[0]
        return f"the loop leaves {name} to a person, who reads {right['evidence']}"
    text = _pointer(resources.load_json(source[1]), source[2])
    if source[0] == "needs":
        first = _sentence(text)
        return f"it needs {first[:1].lower()}{first[1:]}"
    if source[0] == "stays":
        return f"it stays {text.partition(';')[0].rstrip('.')}."
    return _sentence(text, source[3] if len(source) > 3 else 0)
