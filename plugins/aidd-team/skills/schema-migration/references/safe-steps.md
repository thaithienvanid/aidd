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

Two pull requests can each add a migration, each pass against the old `main`, and both merge. So run the check on the merge result: require a branch to be up to date before it merges, or use a merge queue. The second one then regenerates its migration.

Where the file name sets the order, let the tool's generator name it with a UTC timestamp, such as `20261026091500_add_orders_index`. Never use a sequence number, which two branches pick at once, or a hash, which loses the order. A revision graph such as Alembic's orders by its parent links instead. Either way, the tool's checksum file is where a hash belongs, so editing a migration that already ran fails.

| Tool kind | The check |
| --- | --- |
| A revision graph, such as Alembic | `alembic heads` prints exactly one line |
| Versioned scripts, such as Flyway | `flyway validate` passes, with out-of-order apply off |
| A directory with a checksum file, such as Atlas | `atlas migrate validate` passes, and `atlas.sum` matches the files |
| Timestamp-ordered files, such as Prisma Migrate or Rails | every migration replays from an empty database, and the schema matches the committed one |
