# Names for modules, data, events, operations, and history

Load this when you name a folder, schema, event, flag, setting, secret, metric, alert, branch, commit, or document, or rename something others depend on.

## Folders and modules

- Deployables: `apps/<role>` (`apps/server`, `apps/worker`, `apps/web`). Not `apps/api`: `api` is a module's public surface.
- Modules: `modules/<capability>`, kebab-case, the word on the team's whiteboard (`billing`, `order-fulfilment`). Not `core`, `common`, `backend`, or a team name.
- Shared packages: `packages/<purpose>`, never a domain (`shared-kernel`, `api-client`).
- In a module: `api/` is public, `internal/` is private.
- Files follow the language: `order-repository.ts`, `order_repository.py`, `order_repository.go`.
- The module name is the root of its schema, roles, events, flags, and metrics. Choose it with care.

## Database

| Thing | Pattern | Examples |
| --- | --- | --- |
| Schema | the module name, snake_case | `orders`, `order_fulfilment` |
| Roles | `<module>_app` at runtime, `<module>_migrator` for migrations | `orders_app` |
| Table, key, reference | plural snake_case noun, `id`, `<entity>_id` | `line_items`, `customer_id` |
| Instant, date, boolean | `<event>_at` (`timestamptz`, UTC), `<event>_on`, `is_` or `has_` | `placed_at`, `due_on`, `is_paid` |
| Money | `<name>_minor` bigint and `currency` char(3) | `total_minor` |
| Index, unique, foreign key | `<table>_<columns>_idx`, `_key`, `_fkey` | `line_items_order_id_fkey` |
| Migration | `<timestamp>_<verb>_<object>.sql` | `20261009083000_add_currency_to_invoices.sql` |

The `_idx`, `_key`, `_fkey`, and `_pkey` suffixes are PostgreSQL's own defaults, so generated and written names match.

## Events

- Type: `<module>.<aggregate>.<past-verb>.v<N>`, lowercase, the verb in the past tense, kebab-case in a segment: `orders.order.placed.v1`, `identity.user.erasure-requested.v1`.
- A fact, not a command (not `orders.create-order.v1`). Say what changed (`shipping-address-changed`, not `updated`). Always a version.
- CloudEvents 1.0.2 says the type should start with a reverse-DNS name. Add it at least when the event leaves the company: `com.example.orders.order.placed.v1`.
- `source` is `/modules/<module>`, `subject` is the aggregate id. Extension attributes: lowercase letters and digits only, and should not exceed 20 characters (`tenantid`). `data` fields: camelCase, as in the HTTP API.

## Flags, configuration, and secrets

- Flags: `<module>.<feature>`, `<module>.experiment.<name>`, and kill switches `<module>.ops.<capability>`. Name the capability, never a ticket or a person.
- Environment variables: `APP_<MODULE>_<SETTING>` with the unit (`APP_BILLING_RETRY_TIMEOUT_MS`). Secrets: `<env>/<app>/<module>/<name>`.
- Environments: `local`, `staging`, `production`, never `prod2`. Cloud resources: `<env>-<app>-<purpose>`, tagged with the owner and the module.

## Metrics, alerts, and SLOs

- Standard signals keep their OpenTelemetry semantic convention names: `http.server.request.duration`.
- Business metrics: `<module>.<noun>.<measure>`, lowercase with dots, the unit in metadata (`billing.invoice.amount`). A module name must not be an OpenTelemetry namespace (`http`, `db`, `app`); if one is, add the company prefix (`com.example.http…`).
- Custom attributes start with the company's reverse domain or a unique app name (`com.example.tenant.id`). Never use a namespace the conventions define, such as `app.`. Logs use the trace attribute names.
- Alerts: `<module-or-journey>.<symptom>` (`checkout.availability.slo-burn-fast`). SLOs: `<journey>-<indicator>` (`checkout-latency`).

## Branches and commits

- Commit and PR title: Conventional Commits 1.0.0, `<type>(<module>): <imperative summary>`, so history filters by module: `feat(billing): add currency to invoices`. A breaking change adds `!` and a `BREAKING CHANGE:` footer.
- Branch: `<type>/<short-description>`, with the ticket id if the team uses one.

## Documents

aidd writes these here, and its paths win: ADRs `docs/adr/NNNN-<decision>.md` (`aidd new adr`), runbooks `docs/runbooks/<ID>.md`, postmortems `docs/postmortems/<ID>.md`, terms `docs/GLOSSARY.md`. A folder's main doc is `README.md`. An ADR title states the decision.

## Renaming what others depend on

| What | How |
| --- | --- |
| Private code in a module | a refactor commit, with an IDE or codemod rename |
| A module's API, a column, a table | expand and contract: add the new name, move every caller, remove the old |
| An event type | the new type or version beside the old; consumers move; remove the old |
| A module | an ADR, then folder, schema, roles, events, flags, and metrics in planned steps |
| A business term | the glossary first, then code and docs |
