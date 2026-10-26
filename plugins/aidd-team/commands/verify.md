---
description: "Verify a built head: the verifier runs the Spec's tests on that exact commit and exercises each Acceptance line as a user or caller would. A clean report lets the review count, and a failure goes back to Implement"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or the PR/MR number>"
---

Loop step: **Verify**, after every **Implement**, beside **Review** on the same head. `/aidd-team:review` runs the verifier itself, so run this command alone only to verify a head again, such as after a rework.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it. The role table in the aidd-team skill lists them.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Take its pack with `aidd context <ID> --role <role> --play --session ${CLAUDE_SESSION_ID}`, so the guard holds you to its files, and run `--stop-playing` when the step ends, before you start a role. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Under autopilot, start every role. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary. With a Spec, that is its context pack, `aidd context <ID> --role <role>`, else the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report ran out of turns: never take silence as done; start it again on what is left, from the files it wrote, and after two silent runs ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never an approval: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

Verify $ARGUMENTS:

1. Note the head SHA (`git rev-parse HEAD`). The report is about that commit only: a new push makes it stale, and Verify runs again.
2. Run one `aidd-team:verifier` subagent on that head. It runs its own `aidd test --spec specs/<ID>.md` once on a clean tree (or `aidd test` on the fast and emergency lanes), never the builder's evidence as its result. That run is the head's one full agent run. Then it starts the change the way a user or caller would, and exercises each Acceptance line. It changes nothing.
3. Its report starts with the harness and the model it ran on, and the head SHA it checked. Then it lists each command run, what it saw, and each mismatch with an Acceptance line. Last, it lists the assumptions the builders' handoff notes name.
4. A failed command or a mismatch goes back to `/aidd-team:implement`, for the Task it belongs to. A clean report lets the review of this head count, and `/aidd-team:review` runs next when the head has none yet. Mark the PR/MR ready for review (without a platform, the branch is ready as it stands). Report what `aidd/gate`, or the local `aidd gate`, still waits for, and stop. With no gate workflow in the repository (`aidd init --ci none`), check locally with `aidd gate --spec specs/<ID>.md`.

The report routes the work. It is never evidence. The gate still reads the runner's exit codes bound to the head, and a human still gives Merge approval.
