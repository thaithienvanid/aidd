"""Who holds a step of the work, and the step codes the next steps and the pages use."""

from __future__ import annotations

# Who takes a step, as a role noun: the session-start hook puts these lines in an agent's context, where "you" would
# read as the agent itself.
AGENT, AUTHOR, APPROVER = "agent", "author", "Approver"


PERSON = "triager"


COMMIT = "decision maker"


# The step-code contract: every code a step here can carry, and who takes it. `aidd autopilot next` maps an agent's
# step to the one flow whose `starts_on` names it (roles.json) and a person's step to none; the lane step maps by its
# lane (`lane.fast`, `lane.spec`). tests/test_autopilot.py fails when this code emits a code the table lacks.
STEP_CODES: dict[str, str] = {
    "setup.missing": AUTHOR,
    "setup.doctor_fail": AUTHOR,
    "spec.emergency": AGENT,
    "spec.backfill": AGENT,
    "spec.blocked_by": AUTHOR,
    "spec.blocked": AUTHOR,
    "spec.spec_approval": APPROVER,
    "spec.draft": AGENT,
    "spec.ready": AGENT,
    "spec.in_progress": AGENT,
    "spec.in_review": APPROVER,
    # The person's standing approval covers these: the agent records the approval (`aidd approve spec|merge`) or ships.
    "spec.approve_standing": AGENT,
    "spec.ship_ready": AGENT,  # no platform: `aidd ship`
    "spec.merge_standing": AGENT,  # on a platform: `aidd approve merge`, then the PR/MR merges
    "spec.integrate": AGENT,  # a goal's Spec: `aidd integrate` lands it in the goal branch, with no person asked
    "spec.integrated": AUTHOR,  # in its goal: it ships with the goal's release
    "goal.release": APPROVER,  # a goal ready to release: the person's Merge approval of its head
    "goal.ship_ready": AGENT,  # the same, under their standing approval: `aidd ship` on the goal branch
    "epic.launch_spec": AGENT,  # a flagged Epic built: write its launch Spec, whose Merge approval stays the person's
    "spec.shipped": AGENT,
    "spec.done": AUTHOR,
    "spec.rolled_back": AGENT,
    "spec.cancelled": AUTHOR,
    "spec.triage": PERSON,
    "spec.needs": AUTHOR,
    "spec.task_person": AUTHOR,  # a Task assigned to a person: its `who` shows that person
    "spec.outcome_due": AUTHOR,
    "epic.close": AUTHOR,
    "initiative.close": AUTHOR,
    "proposal.exploring": COMMIT,
    "proposal.drafting": AGENT,
    "proposal.signed_off": AUTHOR,
    "proposal.submitted": AUTHOR,
    "proposal.accepted": AUTHOR,
    "overlap": AUTHOR,
    "overlap.capped": AUTHOR,
    "backlog.capped": AUTHOR,
    "knowledge.action": AUTHOR,
    "flag.overdue": AUTHOR,
    "queue.over_limit": AUTHOR,
    "wip.over_limit": AUTHOR,
    "nothing_open": AUTHOR,
    "nothing_matches": AUTHOR,
    "lane.fast": AGENT,
    "lane.spec": AGENT,
}
