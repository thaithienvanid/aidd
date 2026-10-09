# Module: TODO: name

<!-- Copy this file to `modules/<name>/README.md` when you add a module. The module owner keeps it true: a change to
     the module's API, data, or events changes this page in the same change. Write the prose at the `ste-80` level
     (the `aidd-team:plain-language` skill). The architecture overview's module map holds one row for each module. -->

- **Purpose:** TODO: one sentence in business words.
- **Owner:** TODO: one team or person, the same as its `[[owners.paths]]` entry and CODEOWNERS line.
- **Subdomain:** TODO: core, supporting, or generic.

## Public API

<!-- Everything other modules may import from `api/`: calls, DTOs, errors, and event types. Everything else is internal. -->

| Call or type | What it does | Used by |
| --- | --- | --- |
| TODO: `place_order(cmd)` | TODO | TODO: `apps/api` |

## Owned data

<!-- The schema (Postgres) or the table prefix (SQLite, D1) is the module's name. No other module reads or writes these
     tables. List each personal data field and why the module keeps it: this is the module's slice of the data map. -->

- Schema or prefix: TODO: `orders` or `orders_`
- Tables: TODO
- Migrations: `modules/TODO/migrations/`

| Personal data field | Why the module keeps it | Retention |
| --- | --- | --- |
| TODO, or "none" | TODO | TODO |

## Events

<!-- Each type is `<module>.<aggregate>.<past-verb>.v<N>`. A consumer keeps a contract fixture for each event it uses. -->

| Direction | Event type | From or to |
| --- | --- | --- |
| Publishes | TODO: `orders.order.placed.v1` | TODO: billing, notifications |
| Consumes | TODO: `billing.payment.captured.v1` | TODO: billing |

## Dependencies

- Calls: TODO: `modules/<other>/api` for what, or "none".

## Decisions

- TODO: link each ADR that shaped this module (`docs/adr/NNNN-title.md`), or "none yet".
