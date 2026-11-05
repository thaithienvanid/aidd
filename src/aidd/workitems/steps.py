"""Who holds a step of the work, and the step codes `aidd status` gives."""

from __future__ import annotations

from aidd.workitems.ids import is_id

# Who takes a step, as a role noun: `aidd status` shows these, and an agent reads "you" as itself. Nobody takes a step
# that waits on other work, or the step of finished work.
AGENT, PERSON, NOBODY = "agent", "person", "nobody"


# The step-code contract: every code `aidd status` can give, and who takes it. The docs table lists them in this order.
STEP_CODES: dict[str, str] = {
    "setup.missing": PERSON,
    "spec.emergency": AGENT,
    "spec.triage": PERSON,
    "spec.blocked_by": NOBODY,
    "spec.blocked": PERSON,
    "spec.planned": AGENT,
    "spec.draft": AGENT,
    "spec.ask_approval": AGENT,
    "spec.consumers": AGENT,
    "spec.approval": PERSON,
    "spec.approved": AGENT,
    "spec.in_progress": AGENT,
    "spec.merge": PERSON,
    "spec.done": NOBODY,
    "spec.outcome_due": PERSON,
    "spec.rolled_back": AGENT,
    "spec.cancelled": NOBODY,
    "spec.task_person": PERSON,
    "intent.agree": PERSON,
    "intent.slice": AGENT,
    "intent.close": PERSON,
    "exploration.open": PERSON,
    "proposal.qualifying": PERSON,
    "proposal.drafting": AGENT,
    "proposal.signed_off": PERSON,
    "proposal.submitted": PERSON,
    "proposal.accepted": AGENT,
    "flag.overdue": AGENT,
    "deprecation.overdue": AGENT,
    "nothing_open": PERSON,
}


# What each step code means, in one line: a person who meets the code in `aidd status` reads what moves it on.
STEP_MEANINGS: dict[str, str] = {
    "setup.missing": "aidd is not set up in this repository: run `aidd init`",
    "spec.emergency": "an emergency Spec is open: restore service inside its scope first, then complete the Spec before its `review_due`",
    "spec.triage": "an agent suggested this work: a person triages it (accepted, declined, or snoozed) before anyone builds it",
    "spec.blocked_by": "the approved Spec waits for the work its `blocked_by` relation names: Implement starts when that work finishes",
    "spec.blocked": "the Spec names a blocker in `blockers`: clear it and remove the entry, or re-plan",
    "spec.planned": "the Spec is planned, and nobody has started it: Specify writes it and its tests when its turn comes",
    "spec.draft": "the Spec and its tests are not finished: finish them, run `aidd validate`, then ask for Spec approval",
    "spec.ask_approval": "the Spec has no placeholder and `aidd validate` finds no error: set `status: ready`, then ask for Spec approval",
    "spec.consumers": "the revised Spec provides an interface that open Specs consume: finish it, then name those Specs and their owners in the Spec approval question",
    "spec.approval": "the Spec, its tests, and its design wait for a person's yes: the agent asked, and the person answers",
    "spec.approved": "the Spec is approved: implement it inside its Tasks' scope",
    "spec.in_progress": "the Spec is being built: finish its Tasks and get the tests green with `aidd test`",
    "spec.merge": "the built change waits for a person's Merge approval: they read the report, then say yes, or review the PR/MR",
    "spec.done": "the Spec is done: nothing to do",
    "spec.outcome_due": "the Spec's hypothesis is past due: measure its metric and record `outcome.result`",
    "spec.rolled_back": "the change was rolled back: write the postmortem",
    "spec.cancelled": "the Spec was cancelled: nothing to do",
    "spec.task_person": "a Task is assigned to a person: they do it, then record `done: true` on it",
    "intent.agree": "the Intent's goal and slices wait for a person's agreement: they read it, then say yes in the chat, and the agent records `agreed_by` and `agreed_at`",
    "intent.slice": "a slice of the agreed Intent is ready and has no Spec yet: write its Spec with `aidd new spec <id>`",
    "intent.close": "every slice of the Intent is finished: a person sets its status `done` (or `cancelled`)",
    "exploration.open": "an exploration waits for a person's pick: they read its options and its recommendation, then pick one in the chat",
    "proposal.qualifying": "a proposal waits for its go/no-go decision, which its decision maker records",
    "proposal.drafting": "the proposal is being drafted: `/aidd-team:propose`, then `aidd validate`",
    "proposal.signed_off": "the proposal is signed off: send it to its addressee, then record `outcome: submitted`",
    "proposal.submitted": "the proposal waits for its addressee to decide: record their answer in `outcome`",
    "proposal.accepted": "the proposal was accepted: plan the delivery work as an Intent and its phases",
    "flag.overdue": "a feature flag is past its `cleanup_due`: write the cleanup Spec that lists it in `removes_flags`",
    "deprecation.overdue": "a deprecation is past its `sunset`: write the removal Spec that lists it in `removes_deprecations`",
    "nothing_open": "nothing is open: describe the next change to the agent",
}


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
    "spec.consumers": "Go on with {id}",
    "spec.ask_approval": "Ask me to approve {id}",
    "spec.approval": "Show me {id} for Spec approval",
    "spec.approved": "Go on with {id}",
    "spec.in_progress": "Go on with {id}",
    "spec.merge": "Show me the report on {id} for Merge approval",
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
