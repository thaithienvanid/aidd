# Handoff note

The note's form and its required keys are in the `aidd-handoff` block that SKILL.md's "Stop and hand back" gives. This page holds the optional keys and what that block does not say.

````text
```aidd-handoff
status: in_progress      # optional: the status you stopped in
head: 3f2c1a9            # optional: the commit you checked; a delegated merge needs the latest note to name its exact head, with needs: none
asked: "a CSV export: a change to the approved Acceptance, so I asked for spec.revise"   # optional: what a person asked you directly, and what you did with it
decided: ["use the stack's own test runner: the stack's default", "retry 3 times: the SRE standard"]   # optional: what you settled yourself, and what settled it
open_decisions:          # optional: each risk or choice you leave for the lead, with what each option blocks
  - id: no-tests-check
    what: "the new check fails a branch that has no tests yet"
    options:
      - {choice: "warn only", blocks: "nothing"}
      - {choice: "fail the run", blocks: "a docs-only change"}
answered: [{id: no-tests-check, choice: "warn only"}]   # optional, the lead's later note: each earlier entry's id and the choice taken, one of its own
run:                     # optional: what the run opened, and the lead's snapshot of a long run, so a later session goes on from it
  opened:                # what you opened that outlives a command, and whether you closed it
    - {what: "a page server on port 8000, process 4242", closed: true}
    - {what: "a preview on port 5173", closed: false, why: "a person has not looked yet", closed_by: lead}
  id: "20261111T221500123Z-1a2b3c4d"   # the lead's: a role's block holds only opened
  attempt_counts: {"SPEC-3:spec.in_progress": 2}
  send_back_counts: {"SPEC-3": 1}
  spend: "412000 tokens"
  unknown_spend_steps: 3
  hours: 2.5
  resumes_at: "2026-11-12T10:00:00Z"
```
````

Append a new block each time: the latest counts, and `aidd status` reads it. List in `run.opened` each role, worktree, branch, background process, port, scratch folder, or PR/MR you opened, and whether you closed it. For one you leave open, say why and who closes it now, the lead or a person: the note passes it to them. A role's `run` block holds only `opened`. `aidd status <ID>` also shows the item's history (asks and answers, reports, commits). A record is never a yes for a new question. Ask again only for what is new: an answer still in force, such as an approved Spec's rows or this session's yes, is not asked twice. When the next role needs a skill, end `done` with it, such as "next role loads aidd-team:schema-migration". `next_role` holds the role alone, and the next role loads each named skill once, before its first edit. A `needs` other than none is a step for a person while the Spec stays in the note's `status`. Once the work moves on, the question is stale.

In a headless run, write `needs` as the plain question, with the action id after its meaning: `needs: "Force-push to main? It replaces 2 commits there (git.push.force)."`. The agent that resumes acts on the person's yes in their next session.

A person may ask any role directly. Sort the request as the lead does. Answer a question from the files, and send new work to triage. Never fold a change to an approved Spec's scope, Acceptance, or tests in: ask for `spec.revise`. Record the request and what you did on the `asked` key, for the lead and the next role.

A standard, the project's rules (the config's `project` and `risks`, the docs), or aidd's default may settle a choice. List each such choice on the `decided` key, with what settled it, as "Clarify first" in `references/loop.md` says. The person reads them there and overrules any with a change. Ask only what none of them settles. Ask too what changes the route, the scope, the Acceptance, the cost, or what users see. Who decides what is in the aidd-team roles reference (`.aidd/team-roles.md` once installed).

A risk you name is a decision, never a note you keep. List a risk in `open_decisions` when a check you wrote or ran may block honest work. List a choice there too when no standard, project rule, or default settles it. List a review there too when the route or the areas of your changed paths call for one you did not run, such as a security review of a change to a control. One option starts it, and one says why none is needed. The lead takes the second only where no rule requires the review. A line in `done` alone is not a request. Give each entry a short `id`, unique in your note, such as `no-tests-check`, then what it is, each option, and the honest work that option blocks, or `nothing`. When a standard, a project rule, or aidd's default does settle it, settle it yourself and write it on the `decided` key. The lead answers each entry before it merges your work, on a later note's `answered`, with the entry's `id` and one of its choices written exactly. Under a delegation, a Spec approval or merge waits until it does. A choice only a person can make reaches them through the lead's `needs`, which names the `id`.

Debt you found and left (outside the scope, or not worth fixing now) goes in `done` as `debt: <what, where>`, with no list of its own. An agent in `agents.proactive_roles` turns each into a suggested Spec with `labels: ["debt"]`. A person triages it.

The note is a report, never evidence. It is not part of the approved Spec, so adding one never needs `spec.revise`. After a compaction, read your latest note back and continue from `stopped_at`.

When `needs` asks a person to choose between options, write a decision card first. A decision card is an exploration with no visuals (`aidd new exploration specs/<ID>/explore/<slug> --title "<the question>"`) in the work item's folder. It holds the options, their trade-offs, and your recommendation. Name its path in `needs`: `needs: "pick a refund limit: specs/SPEC-7/explore/refund-limit/exploration.md"`. The card informs; the person decides.

`aidd validate` checks each note's keys and stop code, and names the fix. It also warns about hidden characters and text posing as a person's words or a harness frame. A warning blocks nothing: a note is never a person's yes.
