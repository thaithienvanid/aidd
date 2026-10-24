# Safe steps: locks, backfills, contract, and history

Load this when a migration changes a table people use while it runs, a backfill moves many rows, a contract step drops data, or two branches both wrote migrations.

## Locks

- Set a short lock timeout on each DDL statement, a few seconds, and retry it. A migration that waits for a lock queues every later query behind it, so a slow wait becomes an outage.
- Build an index without blocking writes, such as `CREATE INDEX CONCURRENTLY` in PostgreSQL, in its own step.
- Add a constraint without checking old rows first where the database allows it, then validate it in a later step.

## Backfills

- A backfill runs in batches that log their progress and can restart from the last one.
- It pauses when replication lag or database load passes its bound, and goes on when it drops back.
- It is idempotent, so a second run gives the same row counts and checksums.

## Before the contract step

- Contract only after evidence that nothing reads the old shape, such as zero reads of the old column over the observe window.
- Take a backup before a step that drops data, and prove it restores before the step runs.

## One migration history

After merging from the main branch, the tool shows no fork and no out-of-order version. A merge migration or a renumber comes first.

| Tool kind | The check |
| --- | --- |
| A revision graph, such as Alembic | `alembic heads` prints exactly one line |
| Versioned scripts, such as Flyway | `flyway validate` passes, with out-of-order apply off |
| Timestamp-ordered files, such as Prisma Migrate or Rails | every migration replays from an empty database, and the schema matches the committed one |
