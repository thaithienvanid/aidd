---
name: data-access
description: "Practice skill: read and write a database correctly under concurrency. Use in an aidd repository when a Task writes in a transaction, locks rows, queues jobs in a table, or reads a replica."
metadata:
  checked: "2026-10-22"
---

# Data access

**Use it when** a Task writes to a database in more than one statement, or updates a row that others may update at the same time. Use it too when a Task runs background jobs from a table, reads from a replica, or changes how connections are pooled.

**Do not use when** the change is to a schema or a migration (`aidd-team:schema-migration`) or a slow query (`aidd-team:performance`). Retries across a remote call are `aidd-team:resilience`.

## Standards

<!-- aidd:gen practice:data-access -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| PostgreSQL transaction isolation levels | PostgreSQL 18 | 2026-10-17 | <https://www.postgresql.org/docs/current/transaction-iso.html> |
| PostgreSQL explicit locking: row locks, SKIP LOCKED, and advisory locks | PostgreSQL 18 | 2026-10-17 | <https://www.postgresql.org/docs/current/explicit-locking.html> |
| RFC 9110 HTTP semantics: methods, status codes, and conditional requests | RFC 9110 (STD 97) | 2026-10-16 | <https://www.rfc-editor.org/rfc/rfc9110.html> |
<!-- aidd:end -->

## Specify

- For each write path, state the invariant its transaction protects as an Acceptance line, such as "a seat is sold once". Add the concurrent case: two requests at the same moment.
- Name the isolation level each transaction needs, and what the engine's default allows. PostgreSQL's Read Committed allows a lost update and write skew, and MySQL's InnoDB defaults to Repeatable Read. The Spec says how the code prevents them, or it picks Serializable and retries.
- Name the concurrency control for each contended row. Optimistic (a version column, or `If-Match` on an `ETag` over HTTP, RFC 9110) suits rare conflicts a user can resolve. Pessimistic (`SELECT ... FOR UPDATE`) suits short, frequent ones.

## Implement

- Let the database hold each invariant it can, as a unique, check, foreign key, or exclusion constraint. It holds under any concurrency, and code turns the violation into a conflict.
- One transaction per unit of work, opened and closed in one place. Keep it short: no remote call, no wait for a user, and no message send inside it. The outbox carries the message (`aidd-team:resilience`).
- A conditional update checks its count: `UPDATE ... WHERE id = $1 AND version = $2` must touch one row. Otherwise the caller gets a conflict (HTTP 409 or 412), never a silent overwrite.
- Under Serializable or Repeatable Read, retry the whole transaction on a serialization failure (SQLSTATE `40001`) or a detected deadlock (`40P01`), a few times with jitter. Take row locks in one fixed order, so two transactions cannot deadlock.
- A job queue in the database takes work with `SELECT ... FOR UPDATE SKIP LOCKED` and a small `LIMIT`, so two workers never take one job. Mark the job taken in that transaction, with a lease that ends, so a worker that dies frees its job. Each job is idempotent and keyed, with an attempt count and a dead-letter state. A scheduled task runs once, under a lease or an advisory lock.
- Pool connections: one pool per process, sized from the database's limit divided by the instances, with a wait timeout. Put a pooler in front when that leaves too few for each instance. Behind a transaction-mode pooler, a session lock, a `SET`, or a `LISTEN` ends with the transaction, so take the transaction-level advisory lock (`pg_advisory_xact_lock`).
- A replica can lag. A read that must see the caller's own write goes to the primary, or waits for the replica to reach that write.
- Bound every statement with a statement timeout, every lock wait with a lock timeout, and every session with an idle-in-transaction timeout.

## Review

- Each invariant has its transaction, isolation level, and conflict handling, and a test that sends the conflicting requests at once. No remote call sits inside a transaction, and no update ignores how many rows it touched.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Concurrent-write test | two concurrent writers never silently overwrite each other | both run in parallel on a throwaway instance of the production engine (`test-design:integration-test-services`); one wins, the other gets a conflict |
| Invariant under load | the invariant holds after N parallel requests | send N requests at once, then assert the invariant in SQL |
| Job-queue test | each job runs once with several workers | enqueue jobs, start several workers, assert each job ran exactly once |
| Replica-lag test | a read-your-own-write path reads its write | write, then read through that path with the replica delayed |

## Stop if

- The concurrent case is tested on a mock, or on SQLite in place of the production engine.
- A transaction holds a remote call, a lock across a user's wait, or a message send.
- An update can overwrite a change it never read.

## Hand off

- Done: the invariants, their isolation and conflict handling, and the concurrent tests green on the real engine. Next: the reviewer. Needs: a production-engine test database the project lacks. Stopped at: none, or the stop rule that fired.
