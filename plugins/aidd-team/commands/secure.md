---
description: "Threat-model a Spec or security-review a PR/MR with the security engineer"
disable-model-invocation: true
argument-hint: "<SPEC id or path, or PR/MR number>"
---

Loop steps: **Specify** (before Spec approval) for a Spec, **Review** (before Merge approval) for a PR/MR.

Lanes: spec, emergency.

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

Run the `aidd-team:security-engineer` subagent on $ARGUMENTS:

- For a Spec: a threat model (STRIDE), the ASVS level, and the security tests the verifier must write. It returns them in the security return template (the aidd skill's Spec reference), for the architect to fold into a Spec.
- For a PR/MR: a vulnerability review. Each finding has a confidence (1 to 10) and a `file:line` quote, as `REVIEW.md` asks.

**Challenge each PR/MR finding** before the human security pool sees it:

1. Run a second pass that is read-only: a fresh `aidd-team:security-engineer` subagent in review mode, which writes no file. Give it the findings and the diff's paths, never the first pass's reasoning.
2. It tries to refute each finding with evidence: the `file:line` that blocks the attack, a check that already runs, or a test that shows the path is safe.
3. A finding it cannot refute stays in the findings. A refuted finding goes to a separate list, "Refuted", with the reason and its evidence. You never drop a finding.

The security engineer writes no test itself: the verifier does, in Specify. For a Spec, stop and name the next step: `/aidd-team:specify <ID>`, where the architect folds the return and the verifier adds the abuse cases. For a PR/MR, show the author both lists and stop. The human reviewer from the security pool decides, and can restore a refuted finding.
