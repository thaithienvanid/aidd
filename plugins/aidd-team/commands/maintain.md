---
description: "Route the upkeep that is due (stale standards, old flags, open backfills, flaky tests, ending waivers, runbook drills, doctor warnings) to the command that takes each item"
disable-model-invocation: true
argument-hint: "[a CI log or test report that names flaky tests]"
---

Loop step: **Learn**, on a rhythm the team picks (every week, or after each release), never in the middle of a change. It is the loop's upkeep: the work a person would otherwise remember.

Lanes: fast, spec, emergency.

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

Run one `aidd-team:sre` subagent on the upkeep that is due. Its prompt holds: "Read only. Write the routing note, and change no file."

1. **List it.** Read `aidd status --json`, `aidd eval standards`, `aidd doctor`, each date passed in the Specs, config, and runbooks, and $ARGUMENTS for flaky tests. It decides nothing.
2. **Route each item** by its type, in its own line of the handoff note, with the item's `what` and `where`:
   - `standards-update`: a library standard past its review. Run `aidd upgrade` to take the newer library, and update a standard the config adds in its own file. When a weekly standards check, where the project runs one, names a tool with a newer major release, the upgrade is a change of its own, with the aidd-team:dependency-upgrade skill.
   - `release-rollout`: a flag past its `cleanup_due`. `/aidd-team:specify` writes the cleanup Spec, with the aidd-team:release-rollout skill, and the Spec lists the flag in `removes_flags`.
   - `api-design`: a deprecation past its `sunset`. `/aidd-team:specify` writes the removal Spec, with the aidd-team:api-design skill, and the Spec lists it in `removes_deprecations`.
   - `postmortem`: an open emergency backfill. `/aidd-team:postmortem`, then the backfill Spec goes through Spec approval.
   - `flaky-quarantine`: a person decides whether to quarantine the test. A later change fixes it (`/aidd-team:fix`). Never re-run it until it passes.
   - `waiver`: a waiver that ends soon. A person approves a new one, or the team meets the rule in a change.
   - `runbook-drill`: a runbook past its drill. The SRE prepares the drill; a person runs it and records `tested_on`.
   - `doctor`: the fix `aidd doctor` names.
3. **Name who decides.** Each item that needs a decision names the person who takes it: the Spec's owner, the flag's or the runbook's owner, the incident commander, or the waiver's approver. Never decide for that person, and never start the routed command yourself.

Show the person the routing note, and stop. Each item they choose then re-enters the loop as its own change, whose route `aidd risk --paths` gives before the first edit.
