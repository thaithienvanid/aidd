"""Why a step comes next, in one line, read from the data that owns the reason: the loop's routes and its decision rights
(schemas/roles.json), and the meanings and descriptions the schemas give. Nothing here restates a rule; each code names
where its reason lives, and the line is that text."""

from __future__ import annotations

import functools

from aidd import config, knowledge
from aidd.kernel import resources

# Where each step's reason lives. ("route", step): the item's route, and the loop step it is at; a step that route does not
# run, such as Specify on `minor`, is read on `normal`, which runs every Spec's Specify. ("decision",
# gate): the loop's decision right for that gate, which the loop leaves to a person. ("schema", file, pointer, n): the n-th
# sentence of the description or meaning at that JSON pointer (n is 0 when absent). ("needs", file, pointer): what the step
# needs, the noun phrase there. ("stays", file, pointer): the state an object stays in, the first clause there. A code with
# no entry is finished work, or a step whose reason no data owns. Each reason is one sentence of at most 35 words.
SOURCES: dict[str, tuple] = {
    "spec.emergency": ("route", "Implement"),
    "spec.triage": ("needs", "spec.schema.json", "/properties/triage/description"),
    "spec.blocked_by": ("route", "Implement"),
    "spec.blocked": ("schema", "spec.schema.json", "/properties/waiting_on/description", 1),
    "spec.planned": ("route", "Specify"),
    "spec.draft": ("route", "Specify"),
    "spec.ask_approval": ("route", "Specify"),
    "spec.consumers": ("route", "Specify"),
    "spec.approve": ("decision", "Spec approval"),
    "spec.approved": ("route", "Implement"),
    "spec.in_progress": ("route", "Implement"),
    "spec.verify": ("route", "Verify"),
    "pr.merge": ("decision", "Merge approval"),
    "spec.observe": ("route", "Roll out"),
    "spec.outcome_due": ("schema", "spec.schema.json", "/properties/hypothesis/description"),
    "spec.rolled_back": ("schema", "common.schema.json", "/$defs/status/x-meanings/rolled_back"),
    "intent.agree": ("decision", "Intent agreement"),
    "intent.slice": ("route", "Specify"),
    "intent.close": ("schema", "intent.schema.json", "/properties/status/description"),
    "exploration.open": ("stays", "exploration.schema.json", "/properties/status/description"),
}


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


def route_steps(route: str) -> str:
    """The steps a route runs, as the loop writes them."""
    return str(_loop()["routes"][route])


def decision_right(gate: str) -> dict:
    """The loop's decision right for the gate named `gate`, such as `Spec approval`."""
    return next(d for d in _loop()["decision_rights"] if d.get("gate") == gate)


def step_reason(code: str, route: object = None) -> str:
    """Why step `code` comes next, in one line, or "" when no data owns a reason for it. `route` picks the steps."""
    source = SOURCES.get(code)
    if source is None:
        return ""
    if source[0] == "route":
        read = "emergency" if code == "spec.emergency" else str(route) if str(route) in config.ROUTES else "normal"
        if source[1] not in route_steps(read):
            read = "normal"
        return f'"{config.route_words()[read]}" runs {route_steps(read)}, and this is at {source[1]}'
    if source[0] == "decision":
        right = decision_right(source[1])
        return f"the loop leaves {right['gate']} to a person, who reads {right['basis']}"
    text = _pointer(resources.load_json(source[1]), source[2])
    if source[0] == "needs":
        first = _sentence(text)
        return f"it needs {first[:1].lower()}{first[1:]}"
    if source[0] == "stays":
        return f"it stays {text.partition(';')[0].rstrip('.')}."
    return _sentence(text, source[3] if len(source) > 3 else 0)
