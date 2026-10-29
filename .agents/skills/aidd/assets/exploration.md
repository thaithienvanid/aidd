---
kind: exploration
question: "{{question}}"
owner: "{{owner}}"        # product-designer for a UI question, architect for an architecture one
timebox: "{{timebox}}"    # minutes or a cost, such as "45 minutes" or "2 USD"; a spike's end date (YYYY-MM-DD); when it runs out, stop and present
status: open              # open; decided once a person picks
decided_round: 0          # the round the person picked in, set when status becomes decided
# A technical spike: when the timebox ends, a person records the outcome (adopted, rejected, or inconclusive) and what it rests on.
# outcome: {decision: adopted, by: "@you", decided_on: "2026-01-31"}
# evidence: ["specs/<ID>/explore/<slug>/results.md", "https://..."]
---

# Exploration: {{title}}

Written {{today}}. <!-- `aidd new exploration` wrote this file; `aidd explore <this folder>` renders the one comparison page from it. -->

<!-- A decision card is this file with no visuals: the options as directions, their trade-offs, and a recommendation.
     Name it on the handoff note's Needs line, so a person decides in minutes.
     Otherwise, write two or three directions that differ in approach, not in color: another layout, another
     interaction model, another boundary. A UI direction is its key screen, sketched rough in a design file
     (`aidd prototype --new-design directions/a.html`), with a screenshot per direction. An architecture direction is a Mermaid diagram. Name each
     file in backticks under its direction. An image inside this folder shows on the page. Use real copy and realistic
     sample data, never placeholder text.
     Rounds go in rounds/<N>/: the <screen>-<state>-<target>-<theme>.png files, and the changes.json that answers the
     person's feedback-round-<N-1>.json. The page never records the pick. The owner role writes it, with the reason,
     in the Spec's Design section, DESIGN.md's Decisions, or an ADR.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

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

TODO: which one the owner would pick and why, or "none". A person decides.
