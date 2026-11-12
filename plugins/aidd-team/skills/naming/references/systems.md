# Names for modules, data, events, operations, and history

Load this when you name a folder, schema, event, flag, setting, secret, metric, alert, branch, commit, or document, or rename something others depend on. Load it when you improve a name in steps. Load it too when one word would name things at several scopes, or when two names collide.

**Contents**

<!-- aidd:gen toc -->
- [Folders and modules](#folders-and-modules)
- [Database](#database)
- [Events](#events)
- [Flags, configuration, and secrets](#flags-configuration-and-secrets)
- [Metrics, alerts, and SLOs](#metrics-alerts-and-slos)
- [Branches and commits](#branches-and-commits)
- [Documents](#documents)
- [Improve a name](#improve-a-name)
- [Renaming what others depend on](#renaming-what-others-depend-on)
- [One word at several scopes](#one-word-at-several-scopes)
- [When two names collide](#when-two-names-collide)
<!-- aidd:end -->

## Folders and modules

- Deployables: `apps/<role>` (`apps/server`, `apps/worker`, `apps/web`). Not `apps/api`: `api` is a module's public surface.
- Modules: `modules/<capability>`, kebab-case, the word on the team's whiteboard (`billing`, `order-fulfillment`). Not `core`, `common`, `backend`, or a team name.
- Shared packages: `packages/<purpose>`, never a domain (`shared-kernel`, `api-client`).
- In a module: `api/` is public, `internal/` is private.
- Files follow the language: `order-repository.ts`, `order_repository.py`, `order_repository.go`.
- The module name is the root of its schema, roles, events, flags, and metrics. Choose it with care.

## Database

| Thing | Pattern | Examples |
| --- | --- | --- |
| Schema | the module name, snake_case | `orders`, `order_fulfillment` |
| Roles | `<module>_app` at runtime, `<module>_migrator` for migrations | `orders_app` |
| Table, key, reference | plural snake_case noun, `id`, `<entity>_id` | `line_items`, `customer_id` |
| Instant, date, boolean | `<event>_at` (`timestamptz`, UTC), `<event>_on`, `is_` or `has_` | `placed_at`, `due_on`, `is_paid` |
| Money | `<name>_minor` bigint and `currency` char(3) | `total_minor` |
| Index, unique, foreign key | `<table>_<columns>_idx`, `_key`, `_fkey` | `line_items_order_id_fkey` |
| Migration | the migration tool's own pattern, else `<timestamp>_<verb>_<object>.sql` | `20261009083000_add_currency_to_invoices.sql` |

The `_idx`, `_key`, `_fkey`, and `_pkey` suffixes are PostgreSQL's own defaults, so generated and written names match.

## Events

- Type: `<module>.<aggregate>.<past-verb>.v<N>`, lowercase, the verb in the past tense, kebab-case in a segment: `orders.order.placed.v1`, `identity.user.erasure-requested.v1`.
- A fact, not a command (not `orders.create-order.v1`). Say what changed (`shipping-address-changed`, not `updated`). Always a version.
- CloudEvents 1.0.2 says the type should start with a reverse-DNS name. Add it at least when the event leaves the company: `com.example.orders.order.placed.v1`.
- `source` is `/modules/<module>`, `subject` is the aggregate id. Extension attributes: lowercase letters and digits only, and should not exceed 20 characters (`tenantid`). `data` fields: camelCase, as in the HTTP API.

## Flags, configuration, and secrets

- Flags: `<module>.<feature>`, `<module>.experiment.<name>`, and kill switches `<module>.ops.<capability>`. Name the capability, never a ticket or a person. A kill switch names what it keeps on, never `disable-…`, so `on` is today's behavior.
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

aidd writes these here, and its paths win: ADRs `docs/decisions/NNNN-<decision>.md` (`aidd new adr`), runbooks `docs/runbooks/<ID>.md`, postmortems `docs/postmortems/<ID>.md`, terms `docs/GLOSSARY.md`. A folder's main doc is `README.md`. An ADR title states the decision.

## Improve a name

After Arlo Belshee: rename in small safe steps, each its own refactor commit.

1. Honest: `doStuff` becomes `validateCartAndSaveOrderAndEmailCustomer`. Long and true beats short and wrong.
2. Complete: the name shows every effect, the hidden email too.
3. One thing: split it, and give each part a short honest name (`validateCart`, `saveOrder`, `sendOrderConfirmation`).
4. Intent: name why the parts exist (`placeOrder`).
5. Domain concept: related parts become one named idea (`Checkout`, `OrderPolicy`).

A name others depend on changes by expand and contract (the next section).

## Renaming what others depend on

| What | How |
| --- | --- |
| Private code in a module | a refactor commit, with an IDE or codemod rename |
| A module's API, a column, a table | expand and contract: add the new name, move every caller, remove the old |
| An event type | the new type or version beside the old; consumers move; remove the old |
| A module | an ADR, then folder, schema, roles, events, flags, and metrics in planned steps |
| A business term | the glossary first, then code and docs |

## One word at several scopes

One kind of thing often sits at several scopes: on a company, on each of its departments, and on each project. That is no collision. It keeps one name and one shape at every scope, and where it sits tells the scope: its parent, its file, or its path. Its shape is its type and its parts, never its values. Never join a word for the scope to the name.

A company, a department, and a project each hold a `budget`. Each one answers "how much may this spend, and in what period?", and each holds an amount, a currency, and a period. So all three are `budget`, read with their owner: "the project's budget". A reader who knows one predicts the next. A family such as `budget`, `allocation`, and `allowance` gives that reader three words to learn, and no way to see that they are one idea.

Two questions tell one kind of thing from two. Ask them in this order:

1. **Is it another thing?** It is when it answers another question: "what should be?" against "what happened?", or "what is allowed?" against "what was decided this time?". Then it takes its own word, however alike the two shapes are. A `balance` holds an amount and a currency too, but it answers "how much is left?". It is a record and the budget is a goal, so it never shares the word.
2. **Is it the same kind?** It is when it answers the same question at each scope, and a reader who knows it at one scope would predict it at the next. Then it keeps the one word.

To check a model, write the scopes of each hierarchy side by side. For each question that more than one scope answers, write the name that each scope gives its answer. One question has one word, and each other question has its own.

- The question outranks the shape. A likeness in shape alone never joins two things under one word. One question held in two shapes keeps the word, and `aidd-team:data-model-design` owns the shape.
- The scopes keep their own names, such as company, department, and project, because those names are what tells the scope.
- Where the medium is flat, as a metric name or an environment variable is, write the path before the word. The word itself stays the same: `company.budget`, `project.budget`.
- Where the readers' field has a word of its own for each scope, as a school has a curriculum, a syllabus, and a lesson plan, the familiar word wins (SKILL.md, "Principles").
- The smell is a family of near-synonyms down a hierarchy, one word for each scope: a goal, an objective, an aim, and a target. Words that are not alike hide the same fault better, so ask what question each scope's word answers, and ask both questions above of the whole family at once.

This is Domain-Driven Design's ubiquitous language. Inside one bounded context a word has one meaning, and a context is the setting that gives a word its meaning. [domain-driven-design-bounded-contexts-context]

## When two names collide

Two names collide only when they name different things. One kind of thing at several scopes is no collision (the section above).

1. Ask first whether they are one activity with two outputs. If they are, keep the shared word, and name each output by what it is, such as an import and its import log.
2. For two words that join the same kinds of thing, state the test that tells them apart. If no test does, keep the word more readers already know.
3. If they are two things, rename the one fewer readers meet, to a plain word they already use. Never trade a collision for jargon or a metaphor.
4. Test the new name on someone new to the project. They say what it is from the name alone, before they read its definition.
5. Weigh the cost by where the name is read: code, data, docs, and people's habits. A public name changes before its release, or later with a migration.
