---
description: "Plan work as an Initiative, Epics, and Spec stubs with the product manager"
disable-model-invocation: true
argument-hint: "<idea or request>"
---

Loop step: **Plan**, before the loop, only for work bigger than one Spec.

Lanes: spec.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route; you never edit an artifact yourself. Send a change to a Spec, a test, a proposal, or code to the role that owns the file. Pass on that role's handoff note.
2. Hand over file paths, not pasted facts: "read specs/SPEC-1.md and its latest handoff note", never a restatement of what a file already says.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
<!-- aidd:end -->

Run the `aidd-team:product-manager` subagent on this request: $ARGUMENTS. For a new product built from a brief, `/aidd-team:mvp` runs the plan and the build together.

Each question it asks the author comes with its recommended answer and why. It looks up what the repository answers, and never asks it.

When it returns, show the author the Initiative, the Epics, and the Spec stubs it wrote, and stop. Planning is done only when a human agrees to it. The plan goes on its own branch. Each Spec ships later in its own change, whose route `aidd assess` checks before the first edit. The Initiative, the Epics, and the stubs are files in the repository. Mirroring them to a tracker is optional, and only when the project already has one connected.
