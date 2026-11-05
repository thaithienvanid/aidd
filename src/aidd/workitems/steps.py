"""Who holds a step of the work, and the step codes `aidd status` gives."""

from __future__ import annotations

from aidd.kernel import resources
from aidd.workitems.ids import is_id

# Who takes a step, as a role noun: `aidd status` shows these, and an agent reads "you" as itself. Nobody takes a step
# that waits on other work, or the step of finished work. The common schema's `next.who` lists the same three.
AGENT, PERSON, NOBODY = "agent", "person", "nobody"

# The step-code contract is data: every code `aidd status` can give, who takes it, and what it means, in the order a work item
# moves through them. The common schema's `step_code` owns all three, as `enum`, `x-who`, and `x-meanings`.
_STEP = resources.load_json("common.schema.json")["$defs"]["step_code"]
STEP_CODES: dict[str, str] = {code: _STEP["x-who"][code] for code in _STEP["enum"]}

# A step that waits at a gate has the code of the action a person's yes covers (`intent.agree`, `spec.approve`, `pr.merge`):
# `loop.gates` in schemas/roles.json lists each gate's actions, so a step finds its gate by its code, never by a name. The
# step after a yes is named for the state the yes reached: `spec.approve` waits for the yes, and `spec.approved` builds after it.


# What each step code means, in one line: a person who meets the code in `aidd status` reads what moves it on.
STEP_MEANINGS: dict[str, str] = {code: _STEP["x-meanings"][code] for code in _STEP["enum"]}


# What a person types to their agent to take a step, or the command to run: one line for each code, with `{id}` the item's id,
# `{waits}` the first item a waiting Spec waits for. An id goes in only when it matches the schema's pattern, and no other
# text of the repository ever goes in. The steps nobody takes have none. The status JSON, the MCP tool, and the work-items page all read this table.
STEP_WORDS: dict[str, str] = {
    "setup.missing": "aidd init",
    "spec.emergency": "Show me where the {id} repair stands",
    "spec.triage": "Show me what {id} needs from me, then wait for my answer",
    "spec.blocked_by": "Show me what {waits} still needs",
    "spec.blocked": "Show me what stopped {id}, then wait for my answer",
    "spec.planned": "Write the Spec for {id} and its tests",
    "spec.draft": "Go on with {id}",
    "spec.ask_approval": "Ask me to approve {id}",
    "spec.consumers": "Go on with {id}",
    "spec.approve": "Show me {id} for Spec approval",
    "spec.approved": "Go on with {id}",
    "spec.in_progress": "Go on with {id}",
    "pr.merge": "Show me the report on {id} for Merge approval",
    "spec.done": "",
    "spec.outcome_due": "Show me how {id} did against its hypothesis, then wait for my answer",
    "spec.rolled_back": "Write the postmortem for {id}",
    "spec.cancelled": "",
    "spec.task_person": "Show me what {id} needs from me, then wait for my answer",
    "intent.agree": "Show me {id} to agree to, then wait for my answer",
    "intent.slice": "Start the next slices of {id}",
    "intent.close": "Show me what is left to close {id}",
    "exploration.open": "Show me the open question in {id}, then wait for my pick",
    "proposal.qualifying": "Show me what {id} needs from me, then wait for my answer",
    "proposal.drafting": "Go on with {id}",
    "proposal.signed_off": "Show me {id}, ready to send",
    "proposal.submitted": "Show me what {id} waits for, then wait for my answer",
    "proposal.accepted": "Go on with {id}",
    "flag.overdue": "Write the cleanup Spec for the overdue flag in {id}",
    "deprecation.overdue": "Write the removal Spec for the overdue deprecation in {id}",
    "nothing_open": "Help me plan the next change, and write its Spec",
}


def step_words(code: str, ident: object, *, waits: tuple[str, ...] | list[str] = ()) -> str:
    """The words for step `code` of item `ident`, on one line; "" for a step nobody takes, and for a step whose id or whose
    waited-for id is not a plain id: words hold no text of the repository."""
    template = STEP_WORDS.get(code, "")
    first = waits[0] if waits else "other work"
    if ("{id}" in template and not is_id(ident)) or ("{waits}" in template and waits and not is_id(first)):
        return ""
    return template.format(id=ident, waits=first)
