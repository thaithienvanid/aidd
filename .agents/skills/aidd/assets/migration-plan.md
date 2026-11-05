# Migration plan: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec.

<!-- The architect's plan for moving a schema or data without downtime. `aidd validate` asks for one on major when
     a risk dimension or the type is data, or the change is irreversible. Each step below is a separate deploy, so you
     can verify and roll back each one on its own. One change is one PR. This Spec lands the expand step, and each
     later step is its own Spec and PR. The contract step removes data. So it is always a later Spec on major, opened
     only once every consumer has moved.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Current and target

- Current: TODO: the schema or data shape today.
- Target: TODO: the shape after the last step.

## Steps

<!-- Expand, migrate, contract, in this order, each a separate deploy:
     1. Expand adds (a nullable column, a new table) and breaks no reader.
     2. Migrate moves the data and switches the readers.
     3. Contract removes the old shape only once nothing reads it.
     Mark the point of no return: the first step whose rollback cannot restore the prior state. -->

| Step | Spec / PR | Deploy | Change | Rollback | Reversible |
| --- | --- | --- | --- | --- | --- |
| 1. Expand | {{spec}} (this PR) | TODO | TODO: add the new shape; write both (dual-write) | TODO: drop the new shape | yes |
| 2. Migrate | TODO: a later Spec | TODO | TODO: backfill, then switch the readers | TODO: switch the readers back | yes |
| 3. Contract | TODO: a later Spec, on major | TODO | TODO: stop dual-write, remove the old shape | restore from backup only | no: Point of no return |

## Backfill

- Batch: TODO: rows per batch and the pause between batches.
- Idempotency: TODO: why a rerun of any batch is safe; the backfill is idempotent and resumable from a checkpoint.
- Duration: TODO: measured on a copy at the production row count, not estimated.

## Locks and timeouts

TODO: which statements take which lock, and for how long at the production row count. Then the lock timeout and statement timeout each step sets, and what it does when one fires.

## Dual-write window

TODO: when writes go to both shapes, how they are kept consistent, and when the window closes.

## Verification queries

<!-- Run after each step; each has the result that means go on. -->

| After step | Query | Expected |
| --- | --- | --- |
| 2. Migrate | TODO: count rows not yet migrated | 0 |

## Consumers

TODO: every reader and writer of the old shape (services, reports, exports, analytics), and the step each must move by.

## Retention

TODO: how long the old shape and the backups are kept after contract, and who deletes them.

[spec]: {{spec_link}}
