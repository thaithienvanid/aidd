---
description: "Write the blameless postmortem and finish the backfill Spec after an incident"
argument-hint: "<incident backfill Spec, such as specs/INC-481.md>"
---

Loop step: **Learn**, on a signal: an incident, a rollback, a Merge approval rejection, or three failed retries.

Lanes: fast, spec, emergency.

1. The SRE writes `docs/postmortems/` only inside a Task's scope, and it does not edit the Spec. So first add to the backfill Spec in $ARGUMENTS a Task assigned to `agent:sre` whose `scope` holds the postmortem's path, such as `docs/postmortems/INC-481.md`; the author or this session edits the Spec, and the backfill Spec is on the emergency route, so nothing in it is frozen yet. Without such a Task, the SRE returns the postmortem as text instead.
2. Run the `aidd-team:sre` subagent on $ARGUMENTS: a blameless postmortem at that path (impact, timeline, contributing factors, what went well, action items with owners), the backfill Spec's sections returned for the author to complete, and the postmortem's path handed over for `outcome.learn_ref` before `review_due`.
3. Action items that change code become new Spec stubs for the product manager, and each re-enters the loop at Plan as a new change, which starts with `aidd next`. Show the author the result and stop.
