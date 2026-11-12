# Module: TODO: name

<!-- Copy this file to `modules/<name>/README.md` when you add a module. The module owner keeps it true: a change to
     the module's API, data, or events changes this page in the same change. Write the prose at the `instruction` level
     (the `aidd-team:plain-language` skill). The architecture overview's module map holds one row for each module. -->

- **Purpose:** TODO: one sentence in business words.
- **Owner:** TODO: one team or person, the same as its `owners.paths` entry and CODEOWNERS line.
- **Subdomain:** TODO: core, supporting, or generic.

## Public API

<!-- Everything other modules may import from `api/`: calls, DTOs, errors, and event types. Everything else is internal. -->

| Call or type | What it does | Used by |
| --- | --- | --- |
| TODO: `place_order(cmd)` | TODO | TODO: `apps/api` |

## Owned data

<!-- The schema, or a table prefix where the store has no schemas, is the module's name. No other module reads or
     writes these tables. The personal data they keep is the data map's (`docs/data-map.md`): name its rows here by data
     item, and never copy their purpose or retention. -->

- Schema or prefix: TODO: `orders` or `orders_`
- Tables: TODO
- Migrations: `modules/TODO/migrations/`
- Personal data: TODO: the data map's rows for these tables, by data item, or "none"

## Events

<!-- Each type is `<module>.<aggregate>.<past-verb>.v<N>`. A consumer keeps a contract fixture for each event it uses. -->

| Direction | Event type | From or to |
| --- | --- | --- |
| Publishes | TODO: `orders.order.placed.v1` | TODO: billing, notifications |
| Consumes | TODO: `billing.payment.captured.v1` | TODO: billing |

## Dependencies

- Calls: TODO: `modules/<other>/api` for what, or "none".

## Decisions

- TODO: link each ADR that shaped this module (`docs/decisions/NNNN-title.md`), or "none yet".
