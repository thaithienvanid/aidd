# Cutover: data and clouds

Load this when a slice moves data between stores, or a workload moves from one cloud or data center to another.

## A data cutover, step by step

1. **Freeze the shape.** Write the mapping from each source field to its target field, with each conversion: units, time zones, encodings, and money in minor units. A field with no target is dropped on purpose, and the Spec says so.
2. **Copy.** A bulk copy runs in batches with a checkpoint, so a failed run resumes where it stopped and never doubles a row.
3. **Sync.** Change data capture, or the outbox, carries every write made since the copy began. Measure the lag. The cutover waits until the lag is near zero.
4. **Reconcile.** Count rows per table and per partition on both stores. Then compare checksums over normalized rows, such as a hash of each row's fields in one fixed order, summed per partition. A mismatched partition is copied again, never patched by hand.
5. **Cut over.** Stop writes to the old store for the shortest window you can, drain the sync, reconcile once more, and switch the router.
6. **Keep the way back.** Until the observe window ends, a reverse sync or the old store in read-only mode lets the switch go back without losing a write.

## A cloud-to-cloud move

The 7 Rs apply per workload, whichever cloud is the source. A cloud-to-cloud move adds these:

- **Map each service.** Write the source service, its target equivalent, and each gap, such as a feature, a limit, or a consistency model that differs. A gap is a design decision in the Spec, never a surprise in production.
- **Recreate identity and secrets.** Roles, keys, and certificates are made again in the target with least privilege. Never copy a credential across clouds.
- **Price the egress.** Moving data out of a cloud is billed. Estimate it before the move from the price links in `aidd-team:cloud-and-infrastructure`.
- **Lower the DNS TTL** days before the cutover, so the switch and the switch back both take effect fast.
- **Run both clouds for the observe window.** Retire the source only after the window ends with no rollback trigger.
