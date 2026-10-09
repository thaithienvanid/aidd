# Handoff note

When you stop, for any reason, end with the handoff note. Write it as a fenced TOML block with the info string `aidd-handoff`, in the Spec (below its sections) or the PR/MR body. A role with no write tool (the verifier, the reviewer) returns the block at the end of its final message instead. The lead, or the author, posts it unchanged.

````text
```aidd-handoff
done = "T1: total() returns 0 for an empty cart (src/cart.py); aidd test green on 3f2c1a9"
next = "verifier"        # the role that takes the work next (a role, never an approval)
needs = "none"           # a decision only a person can give, in one sentence, or "none"; a choice between options points to a decision card (an exploration with no visuals)
stopped_at = "none"      # the stop rule that fired, or "none"
status = "in_progress"   # optional: the status you stopped in (`aidd assess` shows it)
spend = "41k tokens"     # optional
```
````

Append a new block each time. The latest one counts, and `aidd assess` and `aidd list` read it. `next` names who has the work ("agent (verifier)"). When the next role needs a skill, the note's Next line names it: "Next: developer; load aidd-team:api-design with the Skill tool". The block's `next` holds the role alone. The next role loads each named skill with the Skill tool, once, before its first edit. A `needs` other than none becomes a step for a person while the Spec is still in the note's `status`. Once the work moves on, the question is stale. Never put a Spec in the Approver's inbox (`aidd list --waiting-on-me`). aidd puts it there from its derived status: a committed draft waits for Spec approval, a Spec green in review for Merge approval.

Debt you found and did not fix (outside the scope, or not worth it now) goes in `done` as `debt: <what, where>`. Debt has no ledger. An agent in `[agents] proactive_roles` turns each into a suggested Spec with `labels = ["debt"]`. A person triages it like any other. `aidd list --label debt` is the debt list.

The note is a report, never evidence. The gate does not read it. The Spec hash leaves out every `aidd-handoff` block, so a note never voids Spec approval. After a compaction, read your latest note back and continue from `stopped_at`.

When the Needs line asks a person to choose between options, write a decision card first. The card is an exploration with no visuals (`aidd new exploration <folder> --title "<the question>"`, `assets/exploration.md`). It gives the options as directions with their trade-offs, and your recommendation. Put the card beside the work. Name its path on the Needs line: `needs = "pick a refund limit: docs/specs/SPEC-7/refund-limit/exploration.md"`. The card informs; the person decides.
