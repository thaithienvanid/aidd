---
description: "Write the blameless postmortem and finish the backfill Spec after an incident"
disable-model-invocation: true
argument-hint: "<incident backfill Spec, such as specs/INC-481.md>"
---

Loop step: **Learn**, on a signal: an incident, a rollback, a Merge approval rejection, or three failed retries.

Lanes: fast, spec, emergency.

<!-- aidd:gen roles:lead -->
**You are the lead.** You run this command and the roles do its work:

1. You route, and you place each role: play it yourself, or start it. Play only a role that adds a view to work you are writing, for a small step, when your session runs on its tier. Take its pack with `aidd context <ID> --role <role> --play --session ${CLAUDE_SESSION_ID}`, so the guard holds you to its files, and run `--stop-playing` when the step ends, before you start a role. Never play a role that checks, tests, or reviews work you wrote. The verifier, the reviewer, the security engineer, the compliance analyst, and the designer's review always start. Never write both the tests and the code. Start a role too when a cheaper tier does it, it works in parallel on its own scope, or it would fill your context. Under autopilot, start every role. Pass on each role's handoff note.
2. Hand each role you start the paths it reads, never pasted facts or a summary. With a Spec, that is its context pack, `aidd context <ID> --role <role>`, else the files by path. It returns its work in the file it owns, and its handoff note.
3. Launch the roles of one group in parallel, in one message, and wait for all of them before you act. Do not take a turn per completion. A role that returns no report, or a partial one, stopped at its turn cap: never take it as done. Resume that agent, which keeps its history, and ask for its report; where you cannot, start it again from the files it wrote. After two such stops, ask the person.
4. Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (`opus` for reasoning, `sonnet` for execution). Read-only search helpers (Explore) take the execution tier's model.
5. Start each command in a fresh session (or after `/clear`). It begins from the files and the latest handoff note, never from an earlier command's conversation.
6. A revision changes each affected section with one Edit (Write only a new or mostly rewritten file). It reruns only the roles whose part the new facts change.
7. End with the handoff note, its Spend line included, and stop where the command stops.
8. Take only the team's decisions, each on its evidence, never an approval: Who decides what, in the roles reference (the aidd-team skill's `references/roles.md`, or `.aidd/team-roles.md`), lists them. Sort each request first: a question (answer it from the files), new work (triage), a change to an approved Spec (`aidd revise`), or a production repair (the emergency route).
<!-- aidd:end -->

1. The SRE writes `docs/postmortems/` only inside a Task's scope, and it does not edit the Spec. So first add a Task to the backfill Spec in $ARGUMENTS. Assign the Task to `agent:sre`, with the postmortem's path in its `scope`, such as `docs/postmortems/INC-481.md`. The author edits the Spec, and the lead never does. The backfill Spec is on the emergency route, so nothing in it is frozen yet. Without such a Task, the SRE returns the postmortem as text instead.
2. Run the `aidd-team:sre` subagent on $ARGUMENTS. It produces:
   - a blameless postmortem at that path: impact, timeline, contributing factors, what went well, and action items with owners
   - the backfill Spec's sections, returned for the author to complete
   - the postmortem's path, handed over for `outcome.learn_ref` before `review_due`
3. Action items that change code become new Spec stubs for the product manager. Each re-enters the loop at Plan as a new change, whose route the gate gives before the first edit (`aidd gate --paths`).
4. An action item can hold a lesson for the team's knowledge: a check a domain pack lacked, or a step a practice skill got wrong. Such an item carries `target: pack:<slug>` or `target: skill:<name>` in the postmortem's `actions`. `aidd validate` refuses an id the registry does not know. `aidd list` shows the action until it is done. For each such action, the SRE drafts a suggested Spec for the project's own standards (config `standards:`), or a report upstream that `aidd upgrade` takes in, in its handoff note. The `aidd-team:product-manager` writes it (`suggested_by: agent:sre`). It first searches the declined Specs (`grep -rl 'decision: "declined"' <specs folder>`) for the same idea. If one is there, it links the new Spec to it as `duplicates`, and quotes its `triage.reason`. It records the suggested Spec's id in the action's `tracked_in`. The suggested Spec stays a draft until a person triages it, and an Approver approves it. Show the author the result and stop.
