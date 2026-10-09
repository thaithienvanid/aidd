---
description: "Write the blameless postmortem and finish the backfill Spec after an incident"
disable-model-invocation: true
argument-hint: "<incident backfill Spec, such as specs/INC-481.md>"
---

Loop step: **Learn**, on a signal: an incident, a rollback, a Merge approval rejection, or three failed retries.

Lanes: fast, spec, emergency.

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

1. The SRE writes `docs/postmortems/` only inside a Task's scope, and it does not edit the Spec. So first add a Task to the backfill Spec in $ARGUMENTS. Assign the Task to `agent:sre`, with the postmortem's path in its `scope`, such as `docs/postmortems/INC-481.md`. The author edits the Spec, and the lead never does. The backfill Spec is on the emergency route, so nothing in it is frozen yet. Without such a Task, the SRE returns the postmortem as text instead.
2. Run the `aidd-team:sre` subagent on $ARGUMENTS. It produces:
   - a blameless postmortem at that path: impact, timeline, contributing factors, what went well, and action items with owners
   - the backfill Spec's sections, returned for the author to complete
   - the postmortem's path, handed over for `outcome.learn_ref` before `review_due`
3. Action items that change code become new Spec stubs for the product manager. Each re-enters the loop at Plan as a new change, whose route `aidd assess` checks before the first edit.
4. An action item can hold a lesson for the team's knowledge: a check a domain pack lacked, or a step a practice skill got wrong. Such an item carries `target = "pack:<slug>"` or `target = "skill:<name>"` in the postmortem's `[[actions]]`. `aidd validate` refuses an id the registry does not know. `aidd list` shows the action until it is done. For each such action, the SRE raises a suggested Spec (`suggested_by = "agent:sre"`) that updates that pack or skill. It first searches the declined Specs (`grep -rl 'decision = "declined"' <specs folder>`) for the same idea. If one is there, it links the new Spec to it as `duplicates`, and quotes its `triage.reason`. The SRE records the suggested Spec's id in the action's `tracked_in`. The suggested Spec stays a draft until a person triages it, and the pack's steward reviews it. Show the author the result and stop.
