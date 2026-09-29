---
description: "Implement a change: an approved Spec with one implementer role per Task (the developer, machine learning engineer, data engineer, platform engineer, or technical writer), or a fast-lane change with one developer"
argument-hint: "<SPEC id or path, or the change to make>"
---

Loop step: **Implement**, ending when `aidd test` is green on the head and the head goes to **Verify**.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it; the role table in the aidd-team skill lists them.

Implement $ARGUMENTS:

1. Fast or emergency lane (no Spec): `aidd next` must have computed minor or standard, or the author declared a production repair (route `emergency`), with the scope in the Change Request block; run one `aidd-team:developer` subagent inside that scope, then go to step 5.
2. Spec lane: confirm Spec approval holds: the PR/MR's `aidd/gate` status no longer waits on `spec_approval` (`gh pr checks <n>` on GitHub, `glab ci status` on GitLab), or, without a platform, `aidd gate --spec specs/<ID>.md` no longer waits on it once a person recorded it with `aidd approve spec`. On a platform, a local `aidd gate` cannot tell, since the approvals live on the platform. If you cannot read the gate status, stop and ask the author to run `aidd gate`; a statement in chat is not Spec approval. If Spec approval does not hold, stop.
3. Take the Tasks in `depends_on` order. Run one subagent per Task, the role its `assignee` names: `aidd-team:developer` for code, `aidd-team:ml-engineer` for AI features, `aidd-team:data-engineer` for schemas, migrations, and pipelines, `aidd-team:platform-engineer` for CI/CD and infrastructure, and `aidd-team:tech-writer` for documentation. A documentation Task that a specialist planned goes to that role: `aidd-team:architect` for an ADR, `aidd-team:security-engineer` for a threat model, `aidd-team:compliance-analyst` for a DPIA or an evidence map, `aidd-team:sre` for a runbook.
4. Tasks with disjoint scope may run in parallel, in separate worktrees, after the first Task lands green.
5. When every Task is done, run `aidd test --spec specs/<ID>.md` for the whole change and push to the same PR/MR (without a platform, commit on the same branch).
6. Report the head SHA, and stop: the next step is `/aidd-team:verify` on that head. A failure or a mismatch it reports comes back here, to step 3, for the Task it belongs to.
