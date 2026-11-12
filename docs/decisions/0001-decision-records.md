# 1. Each decision gets one record

Accepted on 2026-11-14. In force.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The decisions for the first release lived in the working notes of the people who made them. A reader of the repository could see what aidd does and could not find why. The architecture page held a table of seven decisions and said a `docs/decisions/` folder would come "when a decision outgrows a table row". About thirty decisions outgrew it. How does a reader find the reason for a choice, and how does a change of mind get recorded?

## Considered options

- **Keep the table on the architecture page.** It costs the options and the deciding case, because a table row holds neither, and the page grows past what a contributor reads.
- **One long design document.** It costs a change of mind: the text is edited in place, so the old reason is lost and nothing says what replaced it.
- **One record for each decision, and an index of questions.** It costs about thirty files to keep. They load only when a reader opens one.

## Decision outcome

The chosen option is "one record for each decision", because a reader finds a reason by asking the question and a change of mind costs one new file.

> Each decision that a reader would otherwise ask "why?" about gets one record in `docs/decisions/`, in MADR's shape. A later decision supersedes it with a new record, and the old one stays as written.

### The case that decided it

A reader meets the levels `ask`, `report`, and `allow` and wonders why the level is not called `request`. Before these records the answer sat in a chat. Now [0022](0022-the-levels-ask-report-allow.md) gives the options, their costs, and the day the project owner chose.

### Consequences

- Good, because the reason sits next to the code it explains, and a superseding record shows the history.
- Good, because a record owns the why and links the page that owns the what, so no fact has two homes.
- Bad, because thirty files need upkeep. A record that states what a page says drifts from it, so each record links the page and does not restate it.

### Reopen when

The index no longer fits one screen of questions. Then group the records in folders by topic.

## More information

[The index](README.md) lists every record as the question it answers.
