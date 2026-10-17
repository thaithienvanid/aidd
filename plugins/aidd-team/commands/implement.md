---
description: "Implement a change: an approved Spec with one implementer role per Task (the developer, machine learning engineer, data engineer, platform engineer, or technical writer), or a fast-lane change with one developer"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or the change to make>"
---

Loop step: **Implement**, ending when `aidd test` is green on the head and the head goes to **Verify**.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it. The role table in the aidd-team skill lists them.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route; you never edit an artifact yourself. Send a change to a Spec, a test, a proposal, or code to the role that owns the file. Pass on that role's handoff note.
2. Hand over file paths, not pasted facts: "read specs/SPEC-1.md and its latest handoff note", never a restatement of what a file already says.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report ran out of turns: never take silence as done; start it again on what is left, from the files it wrote, and after two silent runs ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions (METHOD §5.2, Who decides what), each on its evidence, never an approval. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Each builder lists what in the Spec (or the Change Request block) is unclear before the first edit. A gap that would change an Acceptance line returns to Specify, and a new Spec approval. Anything else is an assumption: the builder names it in its handoff note, and the Verify report records it. Never resolve a gap only in chat.

Implement $ARGUMENTS:

1. Fast or emergency lane (no Spec): the gate must give minor or standard (`aidd gate --paths`, then `aidd gate` on the branch), or the author declared a production repair (route `emergency`). The scope must be in the Change Request block. Run one `aidd-team:developer` subagent inside that scope, then go to step 5. A small minor fix takes `/aidd-team:fix` instead.
2. Spec lane: confirm that Spec approval holds. On a platform, check that the PR/MR's `aidd/gate` status no longer waits on `spec_approval` (`gh pr checks <n>` on GitHub, `glab ci status` on GitLab). In a repository without a platform, check that `aidd gate --spec specs/<ID>.md` no longer waits on Spec approval, once a person recorded it with `aidd approve spec`. On a platform with the gate workflow, a local `aidd gate` cannot tell, since the approvals live on the platform. With no gate workflow in the repository (`aidd init --ci none`), check locally with `aidd gate --spec specs/<ID>.md`. If you cannot read the gate status, stop and ask the author to run `aidd gate`; a statement in chat is not Spec approval. If Spec approval does not hold, stop.
3. Take the Tasks in `depends_on` order. Run one subagent per Task, with the Spec's path and the Task's id. The subagent is the role that the Task's `assignee` names:
   - `aidd-team:developer` for code
   - `aidd-team:ml-engineer` for AI features
   - `aidd-team:data-engineer` for schemas, migrations, and pipelines
   - `aidd-team:platform-engineer` for CI/CD and infrastructure
   - `aidd-team:tech-writer` for documentation

   A Task assigned to a person (an account, a payment, a vendor call, a test on a device) is theirs: skip it. `aidd list` and autopilot ask them, and it is done when they record `done: true` on it.

   A documentation Task that a specialist planned goes to that role:
   - `aidd-team:architect` for an ADR
   - `aidd-team:security-engineer` for a threat model
   - `aidd-team:compliance-analyst` for a DPIA or an evidence map
   - `aidd-team:sre` for a runbook

   Give each subagent one line per skill it must load: "Load the `aidd-team:<name>` skill with the Skill tool before your first edit." The skills are the Task's `skills` and the domain pack for each domain the Spec's Context names. A mention in prose does not load a skill.
4. Tasks with disjoint scope may run in parallel after the first Task lands green, two or three at a time. Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds in its own git worktree, on its own branch. Merge each Task branch back into the change's branch one at a time. Run `aidd test --spec specs/<ID>.md` after each merge. A conflict or a red run goes back to that Task's role, never to your own edit.
5. When every Task is done, read the gate before you run anything: `aidd gate --spec specs/<ID>.md --json`. Route on the finding codes of its `tests` and `red_green` rules for this head and base, never on a handoff note, chat, or the evidence file read directly:
   - no such finding, and `git status --porcelain` (untracked files included) prints nothing: the developer's final `aidd test` already ran on this head, so push it to the same PR/MR (without a platform, it is committed on the same branch)
   - `tests.no_evidence`, `tests.evidence_other_head` (the merges of parallel Tasks moved the head), `tests.evidence_other_base`, `tests.evidence_partial`, or `red_green.no_red_run`, or a dirty tree (uncommitted or untracked files): run `aidd test --spec specs/<ID>.md` once, then push if it is green
   - `tests.evidence_invalid` or `tests.evidence_schema`: report a possibly hand-written evidence file, then run `aidd test --spec specs/<ID>.md` once
   - any other `tests` or `red_green` finding, such as `tests.failed` or `tests.flaky`: the head goes back to step 3 for its Task, with no re-run
6. Report the head SHA, and stop: the next step is `/aidd-team:verify` on that head, in a fresh session. A failure or a mismatch it reports comes back here, to step 3, for the Task it belongs to.

If an advisor is configured (optional and experimental), each builder consults it after a second failed attempt, and again before it reports its Task done. aidd never requires one.
