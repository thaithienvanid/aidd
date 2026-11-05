"""Who holds a step of the work, and the step codes `aidd status` gives."""

from __future__ import annotations

# Who takes a step, as a role noun: `aidd status` shows these, and an agent reads "you" as itself. Nobody takes a step
# that waits on other work, or the step of finished work.
AGENT, PERSON, NOBODY = "agent", "person", "nobody"


# The step-code contract: every code `aidd status` can give, and who takes it.
STEP_CODES: dict[str, str] = {
    "setup.missing": PERSON,
    "spec.emergency": AGENT,
    "spec.triage": PERSON,
    "spec.blocked_by": NOBODY,
    "spec.blocked": PERSON,
    "spec.draft": AGENT,
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
    "epic.close": PERSON,
    "initiative.close": PERSON,
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
    "spec.blocked_by": "the Spec waits for the work its `blocked_by` relation names, and starts when that work finishes",
    "spec.blocked": "the Spec names a blocker in `blockers`: clear it and remove the entry, or re-plan",
    "spec.draft": "the Spec and its tests are not finished: finish them, run `aidd validate`, then ask for Spec approval",
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
    "epic.close": "every child of the Epic is finished: a person sets its status `done` (or `cancelled`)",
    "initiative.close": "every child of the Initiative is finished: a person sets its status `done` (or `cancelled`)",
    "proposal.qualifying": "a proposal waits for its go/no-go decision, which its decision maker records",
    "proposal.drafting": "the proposal is being drafted: `/aidd-team:propose`, then `aidd validate`",
    "proposal.signed_off": "the proposal is signed off: send it to its addressee, then record `outcome: submitted`",
    "proposal.submitted": "the proposal waits for its addressee to decide: record their answer in `outcome`",
    "proposal.accepted": "the proposal was accepted: plan the delivery work as an Initiative and its Epics",
    "flag.overdue": "a feature flag is past its `cleanup_due`: write the cleanup Spec that lists it in `removes_flags`",
    "deprecation.overdue": "a deprecation is past its `sunset`: write the removal Spec that lists it in `removes_deprecations`",
    "nothing_open": "nothing is open: describe the next change to the agent",
}
