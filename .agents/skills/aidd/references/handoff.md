# Handoff note

When you stop, for any reason, end with the handoff note. Write it as a fenced YAML block with the info string `aidd-handoff`, in the Spec (below its sections) or the PR/MR body. With no Spec before a PR/MR exists, put it in your last commit's body, where `aidd status` reads it. A role with no write tool (the verifier, the reviewer) returns the block at the end of its final message. The lead or the author posts it unchanged.

````text
```aidd-handoff
done: "T1: total() returns 0 for an empty cart (src/cart.py); aidd test green on 3f2c1a9"
next: verifier           # the role that takes the work next (a role, never a person's decision)
needs: none              # a decision only a person can give, in one sentence, or "none"; a choice between options points to a decision card
stopped_at: none         # a stop code (below), alone or with ": " and a detail; in a headless run, the ask it reached
by: "agent:claude-code/claude-opus-5-5"   # optional: you, as your commits' Assisted-by
status: in_progress      # optional: the status you stopped in
spend: unknown           # optional: the harness's count, copied, or unknown; never an estimate; unknown never stops a run
asked: "the person asked for a CSV export: a change to the approved Acceptance, so I asked for spec.revise"   # optional: what a person asked you directly, and what you did with it
decided: ["Postgres: the stack's default", "retry 3 times: the SRE standard"]          # optional: what you settled yourself, and what settled it
```
````

Use only these keys. `stopped_at` starts with the code of the stop rule that fired (the skill's Stop and hand back list, from the schema's `stop_code`), such as `stopped_at: "ask: spec.approve SPEC-3"`.

Append a new block each time. The latest one counts, and `aidd status` reads it. When you resume a work item, `aidd status <ID>` also shows its history: the asks and answers, reports, and commits that name it. Read it as history; ask again for anything it covers. When the next role needs a skill, the note's Next line names it: "Next: developer; load aidd-team:schema-migration". The block's `next` holds the role alone. The next role loads each named skill once, before its first edit. A `needs` other than none is a step for a person while the Spec stays in the note's `status`. Once the work moves on, the question is stale.

In a headless run, an `ask` is a stop. Write the Needs line as the plain question, with the action id after its meaning: `needs: "Force-push to main? It replaces 2 commits there (git.push.force)."`. The agent that resumes acts on the person's yes in their next session.

A person may ask any role directly. Sort the ask as the lead does. Answer a question from the files, and send new work to triage. A change to an approved Spec's scope, Acceptance, or tests is `spec.revise`, so ask for it, never fold it into your own work. Record the ask and what you did on the `asked` line, so the lead and the next role see it.

Decide what a standard, the project's rules (the config's `project` and `risks`, the docs), or aidd's default settles, and never ask the person for it. List each such choice on the `decided` line with what settled it. The person reads them there and overrules any with a change. Ask only what none of them settles, or what changes the route, the scope, the Acceptance, the cost, or what users see (Who decides what, in the aidd-team roles reference, `.aidd/team-roles.md` once installed).

Debt you found and did not fix (outside the scope, or not worth it now) goes in `done` as `debt: <what, where>`. Debt has no list of its own. An agent in `agents.proactive_roles` turns each into a suggested Spec with `labels: ["debt"]`. A person triages it.

The note is a report, never evidence. It is not part of the approved Spec, so adding one never needs `spec.revise`. After a compaction, read your latest note back and continue from `stopped_at`.

When the Needs line asks a person to choose between options, write a decision card first: an exploration with no visuals (`aidd new exploration specs/<ID>/explore/<slug> --title "<the question>"`) in the work item's folder, with the options, their trade-offs, and your recommendation. Name its path on the Needs line: `needs: "pick a refund limit: specs/SPEC-7/explore/refund-limit/exploration.md"`. The card informs; the person decides.

`aidd validate` checks each note's keys and stop code, and names the fix. It also warns about hidden characters and text that poses as a person's words or a harness frame. A warning blocks nothing, because a note is data, never a person's yes.
