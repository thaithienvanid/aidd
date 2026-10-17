---
description: "Route the upkeep that is due (stale standards, old flags, open backfills, flaky tests, ending waivers, runbook drills, doctor warnings) to the command that takes each item"
disable-model-invocation: true
argument-hint: "[gate events file, such as aidd-events.jsonl]"
---

Loop step: **Learn**, on a rhythm the team picks (every week, or after each release), never in the middle of a change. It is the loop's upkeep: the work a person would otherwise remember.

Lanes: fast, spec, emergency.

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

Run one `aidd-team:sre` subagent on the upkeep that is due. Its prompt holds: "Read only. Write the routing note, and change no file."

1. **List it.** `aidd list --upkeep --json`, with `--events $ARGUMENTS` when gate events are given (they name the flaky tests). The list reads only the repository and the event files. It decides nothing.
2. **Route each item** by its `route`, in its own line of the handoff note, with the item's `what` and `where`:
   - `standards-update`: a library standard past its review. Update it as CONTRIBUTING.md's Update a standard says, or run `aidd upgrade` for a copy. When the weekly standards check (`aidd-standards.yml`) names a tool with a newer major release, the upgrade is a change of its own, with the aidd-team:dependency-upgrade skill.
   - `release-rollout`: a flag past its `cleanup_due`. `/aidd-team:specify` writes the cleanup Spec, with the aidd-team:release-rollout skill, and the Spec lists the flag in `removes_flags`.
   - `postmortem`: an open emergency backfill. `/aidd-team:postmortem`, then the backfill Spec goes through Spec approval.
   - `flaky-quarantine`: a person decides whether to quarantine the test. A later change fixes it (`/aidd-team:fix`). Never re-run it until it passes.
   - `waiver`: a waiver that ends soon. A person approves a new one, or the team meets the rule in a change.
   - `runbook-drill`: a runbook past its drill. The SRE prepares the drill; a person runs it and records `tested_on`.
   - `doctor`: the fix `aidd doctor` names.
3. **Name who decides.** Each item that needs a decision names the person who takes it: the Approver, the flag's or the runbook's owner, the incident commander, or the waiver's approver. Never decide for that person, and never start the routed command yourself.

Show the person the routing note, and stop. Each item they choose then re-enters the loop as its own change, whose route the gate gives before the first edit (`aidd gate --paths`).
