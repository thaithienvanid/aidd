# Say what holds, not what happened

Load this when you write or review a comment, a docstring, a test name, or a message that a program shows a person.

A reader of the code never saw the change being made. They need what holds now and why it holds. History tells them neither. It also ages: a ticket id points at a tracker they may not open, "before the rewrite" means nothing once the rewrite is old, and "raised from 200" says nothing about why 500 is right. Version control and the change's own record keep history, and they keep it better.

## What is history

- A change log in a comment.
- Who or what made the change, such as a person, a team, or an agent.
- A ticket, task, or plan id that its readers cannot open, or that stands in place of the reason.
- The date a number changed, and "raised from" or "lowered from".
- "Before the … change" and "after the … migration".
- A promise of a later change, such as "temporary until …". A TODO with an owner or a link is not a promise: it is a task a person can find.

## Before and after

Each pair is from a different kind of project. The strong text says what holds and why.

| Where | Weak | Strong |
| --- | --- | --- |
| A web service | `# TASK-481: retry the webhook` | `# The payment provider resends a webhook that times out, so the handler must be idempotent.` |
| A command-line tool | `MAX_ROWS = 500  # raised from 200 on 2026-03-04` | `MAX_ROWS = 500  # The export holds about 500 rows in memory before it runs out.` |
| A data pipeline | `# Before the sync rewrite this ran nightly` | `# Runs nightly because the warehouse locks its tables while it loads.` |
| A mobile app | `// Temporary until the new login lands` | `// TODO(owner, issue link): drop this token shim when the identity provider issues refresh tokens.` |
| A test name | `test_fix_for_ticket_1234` | `test_refund_above_the_paid_amount_is_refused` |
| A message | `"Legacy mode from the v2 migration is on"` | `"Legacy mode is on: orders are read from the old table."` |

A deprecation notice that tells a user what to do now is behavior, not history: `"--old is removed; use --new"`.

## Check it

Search the comments, docstrings, test names, and messages for the project's ticket, task, and plan ids, with one lint rule or one short test. Use the project's own prefixes. A generic pattern such as `[A-Z]+-[0-9]+` also matches `UTF-8` and `SHA-256`.

- Allow the ids a reader can open: an ADR, a Spec in the repository, or an issue in the team's tracker ([SKILL.md, rule 7 of comments and docstrings](../SKILL.md#comments-and-docstrings)).
- An id in a test's own data is not this. A fixture about ids, such as a parser test that reads `PROJ-12`, needs the id.
- The words in the list above have no pattern. The reviewer reads for them, and each is a finding.
