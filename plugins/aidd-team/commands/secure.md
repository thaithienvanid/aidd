---
description: "Threat-model a Spec or security-review a PR/MR with the security engineer"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or PR/MR number>"
---

Loop steps: **Specify** (before Spec approval) for a Spec, **Review** (before Merge approval) for a PR/MR.

Lanes: spec, emergency.

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

Run the `aidd-team:security-engineer` subagent on $ARGUMENTS:

- For a Spec: a threat model (STRIDE), the ASVS level, and the security tests the tester must write. It returns them in the security return template (the aidd skill's Spec reference), for the architect to fold into a Spec.
- For a PR/MR: a vulnerability review. Each finding has a confidence (1 to 10) and a `file:line` quote, as `REVIEW.md` asks.

**Challenge each PR/MR finding** before the human security pool sees it:

1. Run a second pass that is read-only: a fresh `aidd-team:security-engineer` subagent in review mode, which writes no file. Give it the findings and the diff's paths, never the first pass's reasoning.
2. It tries to refute each finding with evidence: the `file:line` that blocks the attack, a check that already runs, or a test that shows the path is safe.
3. A finding it cannot refute stays in the findings. A refuted finding goes to a separate list, "Refuted", with the reason and its evidence. You never drop a finding.

The security engineer writes no test itself: the tester does, in Specify. Show the author both lists and stop. The human reviewer from the security pool decides, and can restore a refuted finding.
