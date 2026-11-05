---
description: "Roll out an approved change: once it is merged, watch the observe window with the SRE and follow the rollback trigger"
disable-model-invocation: true
argument-hint: "<SPEC id or path>"
---

Loop step: **Roll out**, on the spec and emergency lanes. Start only when Merge approval holds and the change is merged. A deploy is `deploy.run`: ask the person first, and deploy only on their yes.

Lanes: spec, emergency. A fast-lane change has no observe window: its roll out is its merge and the project's usual deploy.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Read its agent file, and keep to its area until the step ends. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary: the Spec, its linked docs, and the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never a person's: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. A role's `ask` comes to you: ask the person in plain words, and on their yes, do the action. Spec approval covers `code.edit` in its Tasks' `scope`, so it asks no more there. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`spec.revise`), or a production repair (the emergency route).
<!-- aidd:end -->

1. Run these subagents in parallel for $ARGUMENTS:
   - `aidd-team:sre`, for the report and for the rollout's stages and their state; a pipeline change is a new change
   - `aidd-team:compliance-analyst`, for the audit evidence map, when the Spec has compliance obligations

   The merged change's scope is closed. So the compliance analyst returns the map as obligation, control, and evidence rows in its return template (the aidd skill's Spec reference). These rows go into the rollout report. Writing the map under `docs/compliance/` is a documentation Task in a follow-up change whose scope covers that path.
2. The SRE owns the report:
   1. the observe window: the Spec's observe signals, on the project's dashboards and alerts, until the window ends or the trigger fires. It can run for hours, so watch it in the background
   2. a comparison with the SLO and the rollback trigger
   3. a report to the author

   Agents report. The person decides the result, and the lead records it in the Spec's `outcome`.
3. If the trigger fires, say so first and stop. Ask the person whether to roll back, and roll back only on their yes. Record it, and the loop goes to Learn (`/aidd-team:postmortem`).
4. Optional, after a clean window: when the merged Spec's Design changed the system's shape, offer the author a follow-up change. The follow-up folds the Design into `docs/architecture/`, the living architecture docs, as its own change through the loop. Open it only if the author agrees.
5. Once the change merged, list the worktrees and Task branches it left (`git worktree list`). Ask before you remove them (`git.branch.delete`).
