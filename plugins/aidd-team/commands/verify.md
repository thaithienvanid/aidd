---
description: "Verify a built head: the verifier runs the Spec's tests on that exact commit and exercises each Acceptance line the way a user or caller would, then hands a clean head to Review or sends a failure back to Implement"
argument-hint: "<SPEC id or path, or the PR/MR number>"
---

Loop step: **Verify**, after every **Implement**, ending when a clean report hands the head to **Review**.

Lanes: fast, spec, emergency. On each lane, run only the roles whose lanes include it; the role table in the aidd-team skill lists them.

Verify $ARGUMENTS:

1. Note the head SHA (`git rev-parse HEAD`). The report is about that commit only: a new push makes it stale, and Verify runs again.
2. Run one `aidd-team:verifier` subagent on that head. It runs the Spec's test commands (`aidd test --spec specs/<ID>.md`, or `aidd test` on the fast and emergency lanes), then starts the change the way a user or caller would and exercises each Acceptance line. It changes nothing.
3. Its report starts with the harness and the model it ran on and the head SHA it checked, then lists each command run, what it saw, and each mismatch with an Acceptance line.
4. A failed command or a mismatch goes back to `/aidd-team:implement`, for the Task it belongs to. A clean report hands the head to Review: mark the PR/MR ready for review (without a platform, the branch is ready as it stands), report what `aidd/gate`, or the local `aidd gate`, still waits for, and stop.

The report routes the work; it is never evidence. The gate still reads the runner's exit codes bound to the head, and a human still gives Merge approval.
