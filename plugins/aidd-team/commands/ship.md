---
description: "Ship an approved change: after Merge approval and the merge, run the observe window with the SRE and follow the rollback trigger"
disable-model-invocation: true
argument-hint: "<SPEC id or path>"
---

Loop step: **Ship**, on the spec and emergency lanes. Start only when Merge approval holds and the change has merged. The merge itself is a human's.

Lanes: spec, emergency. A fast-lane change has no observe window: its Ship is the human's merge.

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

1. Run these subagents in parallel for $ARGUMENTS:
   - `aidd-team:sre`
   - `aidd-team:platform-engineer`, for the rollout mechanism
   - `aidd-team:compliance-analyst`, for the audit evidence map, when the Spec has compliance obligations

   The merged change's scope is closed. So the compliance analyst returns the map as obligation, control, and evidence rows in its return template (the aidd skill's Spec reference). These rows go into the ship report. Writing the map under `docs/compliance/` is a documentation Task in a follow-up change whose scope covers that path.
2. The SRE owns the report:
   1. `aidd observe <spec> --window`, which runs the observe command until the window ends or the trigger fires. It can run for hours, so start it in the background or from the release script
   2. a comparison with the SLO and the rollback trigger
   3. a report to the author

   Agents report. A person records the result in the Spec's `outcome` (`aidd observe <spec> --write`).
3. If the trigger fires, say so first and stop: a person runs the rollback and records it, and the loop goes to Learn (`/aidd-team:postmortem`).
4. Optional, after a clean window: when the merged Spec's Design changed the system's shape, offer the author a follow-up change. The follow-up folds the Design into `docs/architecture/`, the living architecture docs, as its own change through the loop. Open it only if the author agrees.
5. Once the change merged, remove its worktrees and Task branches (`git worktree remove <path>`, `git branch -d <branch>`).
