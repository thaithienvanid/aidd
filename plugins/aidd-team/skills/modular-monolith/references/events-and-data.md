# Events and data between modules

Load this when a Task publishes or consumes an event, adds a read model, or runs a flow across modules.

## Choose how modules talk

| The caller needs | Use |
| --- | --- |
| An answer now | a call to the other module's `api/` |
| To state a fact that others react to | a domain event |
| A reaction that survives a crash | an event through the outbox |
| Another module's data often | a local read model that the owner's events keep current |

A report that needs data from many modules reads a replica or an analytics store, never the module code.

## The envelope

Every event carries the CloudEvents 1.0.2 attributes, so a later move to a broker needs no new names:

| Attribute | Holds |
| --- | --- |
| `id` | a unique event id; consumers use it to drop duplicates |
| `source` | the module that publishes, such as `/modules/orders` |
| `specversion` | `1.0` |
| `type` | `<module>.<aggregate>.<past-verb>.v<N>`, such as `orders.order.placed.v1` |
| `time` | when the fact happened, as an RFC 3339 timestamp in UTC |
| `subject` | the aggregate id |
| `tenantid`, `correlationid` | extension attributes: the tenant and the request that caused the event |

Name the type, the extension attributes, and the data fields as `references/systems.md` in `aidd-team:naming` says (section Events). The data holds IDs and the least that consumers need. It never holds names, emails, or addresses: a consumer that needs personal data asks the owner's `api/` when it uses it. An event states a fact in the past tense. It is never a command.

## Delivery: outbox and inbox

- The default is durable, after commit, at least once. The publisher writes the event to its own `outbox` table in the same transaction as the change. A relay delivers it later.
- Each consumer is idempotent. It writes the event id to its own `inbox` table (unique on event id and consumer) in the same transaction as its change. A second delivery then does nothing.
- A handler inside the publisher's transaction is only for a reaction inside the same module. An in-memory handler after commit is only for a reaction you can lose, such as a cache refresh.
- The relay's retries, dead-letter table, and replay command follow `aidd-team:resilience` (references/recovery.md).
- Order holds only per aggregate. A consumer compares the aggregate's version and drops a stale event.
- When a module leaves the process, the same outbox feeds a broker, and the consumers do not change.

## Versioning

- Version the type from the first release (`.v1`).
- A new optional field keeps the version.
- A removed or renamed field, or a changed meaning, is a new type (`.v2`). Publish both until every consumer has moved, and record it in an ADR.

## Flows across modules: sagas

Avoid one transaction across modules. Model the flow as steps, one module and one transaction each. Each step that can fail has a compensating step. The module that owns the flow runs it and records its state, so a restart continues it.

## Purge and personal data

- A purge job deletes processed outbox and inbox rows after a set retention, such as 30 days, and dead-letter rows after their replay window. They never become a hidden store of personal data.
- Alert on outbox lag: the age of the oldest row that is not delivered.
- Erasure fans out. The owner of identity publishes `identity.user.erasure-requested.v1`. Each module that holds personal data erases its own rows and publishes that it is done. The owner tracks the answers and alerts before the legal deadline.
