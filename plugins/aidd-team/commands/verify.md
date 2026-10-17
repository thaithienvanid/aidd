---
description: "Verify a built head: the Verifier runs the Spec's tests on that exact commit and exercises each Acceptance line the way a user or caller would, then hands a clean head to Review or sends a failure back to Implement"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or the PR/MR number>"
---

Loop step: **Verify**, after every **Implement**, ending when a clean report hands the head to **Review**.

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

Verify $ARGUMENTS:

1. Note the head SHA (`git rev-parse HEAD`). The report is about that commit only: a new push makes it stale, and Verify runs again.
2. Run one `aidd-team:verifier` subagent on that head. It runs its own `aidd test --spec specs/<ID>.md` once (or `aidd test` on the fast and emergency lanes), never the builder's evidence as its result. Then it starts the change the way a user or caller would, and exercises each Acceptance line. It changes nothing.
3. Its report starts with the harness and the model it ran on, and the head SHA it checked. Then it lists each command run, what it saw, and each mismatch with an Acceptance line. Last, it lists the assumptions the builders' handoff notes name.
4. A failed command or a mismatch goes back to `/aidd-team:implement`, for the Task it belongs to. A clean report hands the head to Review. Mark the PR/MR ready for review (without a platform, the branch is ready as it stands). Report what `aidd/gate`, or the local `aidd gate`, still waits for, and stop. With no gate workflow in the repository (`aidd init --ci none`), check locally with `aidd gate --spec specs/<ID>.md`.

The report routes the work. It is never evidence. The gate still reads the runner's exit codes bound to the head, and a human still gives Merge approval.
