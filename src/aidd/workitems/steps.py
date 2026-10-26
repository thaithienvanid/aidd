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
    "spec.merge_approval": APPROVER,
    # The person's standing approval covers these: the agent records the approval (`aidd approve spec|merge`) or lands the work.
    "spec.spec_approval_standing": AGENT,
    "spec.land_standing": AGENT,  # no platform: `aidd land`
    "spec.publish": APPROVER,  # the trunk is on a platform: the person types `publish`, which opens the PR/MR
    "spec.publish_standing": AGENT,  # the same, where agents publish (`publish: agents`, or `approve all and publish`)
    "spec.merge_approval_standing": AGENT,  # on a platform: `aidd approve merge`, then the PR/MR merges
    "spec.integrate": AGENT,  # a goal's Spec: `aidd integrate` lands it in the goal branch, with no person asked
    "spec.integrated": AUTHOR,  # in its goal: it reaches users with the goal's release
    "goal.release": APPROVER,  # a goal ready to release: the person's Merge approval of its head
    "goal.land_standing": AGENT,  # the same, under their standing approval: `aidd land` on the goal branch
    "epic.launch_spec": AGENT,  # a flagged Epic built: write its launch Spec, whose Merge approval stays the person's
    "spec.landed": AGENT,
    "spec.done": AUTHOR,
    "spec.rolled_back": AGENT,
    "spec.cancelled": AUTHOR,
    "spec.triage": PERSON,
    "spec.needs": AUTHOR,
    "spec.task_person": AUTHOR,  # a Task assigned to a person: its `who` shows that person
    "spec.outcome_due": AUTHOR,
    "epic.close": AUTHOR,
    "initiative.close": AUTHOR,
    "proposal.qualifying": COMMIT,
    "proposal.drafting": AGENT,
    "proposal.signed_off": AUTHOR,
    "proposal.submitted": AUTHOR,
    "proposal.accepted": AUTHOR,
    "overlap": AUTHOR,
    "overlap.capped": AUTHOR,
    "backlog.capped": AUTHOR,
    "knowledge.action": AUTHOR,
    "flag.overdue": AUTHOR,
    "deprecation.overdue": AUTHOR,
    "approver.over_limit": AUTHOR,
    "wip.over_limit": AUTHOR,
    "nothing_open": AUTHOR,
    "nothing_matches": AUTHOR,
    "lane.fast": AGENT,
    "lane.spec": AGENT,
}


# What each step code means, in one line, for docs/ERRORS.md (`aidd gen-docs`): a person who meets the code in
# `aidd list` or `aidd autopilot next` reads what it is and what moves it on. A new code in STEP_CODES needs a line here.
STEP_MEANINGS: dict[str, str] = {
    "setup.missing": "aidd is not set up in this repository: run `aidd init`, or ask the agent to install aidd and apply it",
    "setup.doctor_fail": "a setup check fails: `aidd doctor` lists every check and its fix",
    "spec.emergency": "an emergency Spec is open: restore service inside its scope first, then complete the Spec before its `review_due`",
    "spec.backfill": "an emergency restored service: complete the backfill Spec and the post-incident review by its `review_due`",
    "spec.blocked_by": "the Spec waits for the work its `blocked_by` relation names, and starts when that work finishes",
    "spec.blocked": "the Spec names a blocker in `blockers`: clear it and remove the entry, or re-plan",
    "spec.spec_approval": "the Spec, its tests, and its design wait for a person's Spec approval: they type `approve <ID>`",
    "spec.draft": "the Spec and its tests are not finished: finish them, `aidd validate` the Spec, and commit",
    "spec.ready": "Spec approval is recorded: implement the Spec inside its Tasks' scope",
    "spec.in_progress": "the Spec is being built: finish its Tasks and get the tests green",
    "spec.merge_approval": "the built change waits for a person's Merge approval: they read the report, then type `land it` or approve the PR/MR",
    "spec.spec_approval_standing": "the Spec waits for Spec approval, and the person's standing approval covers it: the agent runs `aidd approve spec`",
    "spec.land_standing": "the change waits for Merge approval with no platform, and the standing approval covers it: the agent runs `aidd land`",
    "spec.publish": "the change is built and reviewed: it waits for the person to type `publish`, which opens its PR/MR",
    "spec.publish_standing": "the change is built and reviewed, and agents publish here: the agent runs `aidd publish`",
    "spec.merge_approval_standing": "the standing approval covers Merge approval on a platform: the agent runs `aidd approve merge`, and the PR/MR merges once `aidd/gate` passes",
    "spec.integrate": "a goal's Spec is built and green: `aidd integrate` lands it in the goal branch",
    "spec.integrated": "the Spec is in its goal branch, and reaches users with the goal's release: nothing to do now",
    "goal.release": "a goal is ready to release: it waits for the person's Merge approval of the goal branch's head",
    "goal.land_standing": "a goal is ready to release, and the standing approval covers it: the agent runs `aidd land` on the goal branch",
    "epic.launch_spec": "a flagged Epic is built: write its launch Spec, which turns the flag on; its Merge approval stays the person's",
    "spec.landed": "the Spec landed: watch its observe window with `aidd observe <spec> --write`",
    "spec.done": "the Spec is done: nothing to do",
    "spec.rolled_back": "the change was rolled back: write the postmortem",
    "spec.cancelled": "the Spec was cancelled: nothing to do",
    "spec.triage": "an agent suggested this work: a person triages it (accepted, declined, or snoozed) before anyone builds it",
    "spec.needs": "the Spec's handoff note asks a person to decide something: write the answer in the Spec or the PR/MR",
    "spec.task_person": "a Task is assigned to a person: they do it, then record `done: true` on it",
    "spec.outcome_due": "the Spec's hypothesis is past due: measure its metric and record `outcome.result`",
    "epic.close": "every child of the Epic is finished: a person records its status `done` (or `cancelled`) on the base branch",
    "initiative.close": "every child of the Initiative is finished: a person records its status `done` (or `cancelled`) on the base branch",
    "proposal.qualifying": "a proposal waits for its go/no-go decision, which its decision maker records",
    "proposal.drafting": "the proposal is being drafted: `/aidd-team:propose`, then `aidd validate`",
    "proposal.signed_off": "the proposal is signed off: send it to its addressee, then record `outcome: submitted`",
    "proposal.submitted": "the proposal waits for its addressee to decide: record their answer in `outcome`",
    "proposal.accepted": "the proposal was accepted: `aidd proposal convert`, then plan the delivery work",
    "overlap": "two open changes change the same code, or freeze the same doc: agree who goes first, and the later one waits with `blocked_by`",
    "overlap.capped": "aidd checked only some of the other branches for overlaps: delete merged branches so it checks every open one",
    "backlog.capped": "aidd read only the first objects in the Specs folder: archive finished Specs to another folder",
    "knowledge.action": "a postmortem or retro action that changes the team's knowledge is due: make the change it names",
    "flag.overdue": "a feature flag is past its `cleanup_due`: write the cleanup Spec that lists it in `removes_flags`",
    "deprecation.overdue": "a deprecation is past its `sunset`: write the removal Spec that lists it in `removes_deprecations`",
    "approver.over_limit": "an Approver holds more open approval waits than `limits.max_open_per_approver`: finish a review first, or share them",
    "wip.over_limit": "an owner holds more Specs in progress than `limits.max_in_progress_per_owner`: finish one before starting another",
    "nothing_open": "nothing is open: describe the next change to the agent",
    "nothing_matches": "nothing matches the filters; under `--waiting-on-me`, the step names who aidd took you for, and how to name yourself",
    "lane.fast": "the branch's change takes the fast lane (standard or minor): implement it; the gate takes its route from the diff",
    "lane.spec": "the branch's change needs a Spec (normal or major): specify it first",
}
