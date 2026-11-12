---
type: exploration
question: "{{question}}"
role: "{{role}}"          # product-designer for a UI question, architect for an architecture one
timebox: "{{timebox}}"    # minutes or a cost, such as "45 minutes" or "2 USD"; a spike's end date (YYYY-MM-DD); when it runs out, stop and present
status: open              # open; decided once a person picks
decided_round: 0          # the round the person picked in, set when status becomes decided
# taste_pick: true        # a taste pick: two or three sound looks of one thing, which may differ only in color, size, or spacing
# A technical spike: when the timebox ends, a person records the outcome (adopted, rejected, or inconclusive) and what it rests on.
# outcome: {decision: adopted, by: "@you", decided_on: "2026-01-31"}
# basis: ["specs/<ID>/explore/<slug>/results.md", "https://..."]
---

# Exploration: {{title}}

Written {{today}}. <!-- `aidd new exploration` wrote this file; `aidd explore <this folder>` renders the one comparison page from it. -->

<!-- A decision card is this file with no visuals: the options as directions, their trade-offs, and a recommendation.
     Name it on the handoff note's Needs line, so a person decides in minutes.
     Otherwise, write two or three directions that differ in approach, not in color: another layout, another
     interaction model, another boundary. A taste pick (`taste_pick: true`) is the exception: its options are looks
     of one thing, and they may differ only in color, size, or spacing. A UI direction is its key screen, sketched rough in a design file
     (`aidd prototype --new-design directions/a.html`), with a screenshot per direction. An architecture direction is a Mermaid diagram. Name each
     file in backticks under its direction. An image inside this folder shows on the page. Use real copy and realistic
     sample data, never placeholder text.
     Rounds go in rounds/<N>/. Each direction's screenshots are named a-<screen>-<state>-<frame>-<theme>.png by its design
     file. Its comments-a.json comes from a person or from agents, and an agent's item names itself in `by`. The changes.json answers the comments of round <N-1>. The page never records the pick. The exploration's role writes it, with the reason,
     in the Spec's Design section, DESIGN.md's Decisions, or an ADR.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Direction A: TODO name

TODO: one line on what this direction favors, and for whom.

- Sketch: `directions/a.html`
- Screen: `rounds/1/a-TODO-1024-light.png`

### Trade-offs

- Good: TODO
- Costs: TODO

## Direction B: TODO name

TODO: one line on what this direction favors, and for whom.

### Trade-offs

- Good: TODO
- Costs: TODO

## Direction C: TODO name

TODO: optional; delete this section when two directions cover the space.

### Trade-offs

- Good: TODO
- Costs: TODO

## Recommendation

TODO: which one the role would pick and why, or "none". A person decides.
