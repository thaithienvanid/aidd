# Routes

A change's route is a property of the change. aidd computes the minimum from what it touches, the author may declare higher, and the gate enforces the higher of the two. The lane follows from the route. Before the first edit, ask the gate for the route: `aidd gate --paths` forecasts it from the planned paths, and `aidd gate` computes it again from the branch's diff. Which change to work on is a person's choice; `aidd list` shows the open work and who holds each step. The fast lane is the default. The route is one choice: **no Spec (`minor`), a Spec (`normal`), or a production repair (`emergency`)**. You do not need to guess `major`. When the diff of a Spec-backed `normal` change needs major, the gate raises the route. It then applies the major gates: a specialist Approver and an `observe` block. Add those as soon as the computed route (`aidd gate --paths`, or `aidd new spec --paths`) says major. A `minor` block whose diff needs a Spec still fails. `standard` is for configured bot changes.

**Contents**

<!-- aidd:gen toc -->
- [First match wins](#first-match-wins)
- [Risk dimensions](#risk-dimensions)
- [Route meanings](#route-meanings)
- [Change types](#change-types)
- [Built-in path rules](#built-in-path-rules)
- [Confidence](#confidence)
<!-- aidd:end -->

The gate recomputes the minimum from the real diff. The table is its order.

## First match wins

| Order | Route | Choose it when |
| --- | --- | --- |
| 1 | emergency | Production is broken now (outage, degradation, active security or data incident) and this change is the repair. |
| 2 | major | A protected path changes; a dimension is `data`, `security`, `privacy`, `financial`, or `compliance`; the change cannot be reverted; `type` is `data`, `security`, or `compliance`; or a risk rule says major. |
| 3 | standard | The change matches a configured `standard_changes` class exactly: every path, every author, the line limit, and platform-signed commits. Never major. |
| 4 | minor | Confidence is high, one Task, no risk dimension, no rule above minor, no binary file, no contract change (a judgment the gate cannot check), and the diff fits the minor budget (default 50 lines). |
| 5 | normal | Anything else. |

Stops before any route:

- `confidence: low`: a missing fact could change the route. Ask for it.
- Freeze: Policy answers `freeze`. Only a production repair (route emergency) continues.
- No owner: nobody can be named as `owner_team` (a judgment stop; the gate only checks that the field is set).

## Risk dimensions

Pick every dimension the change can harm. The gate computes the ones the paths imply. An inline Change Request block must declare them, and a missing one fails; on a Spec, it is a warning. `data`, `security`, `privacy`, `financial`, and `compliance` make the change major. Each names the specialist pool that reviews the change (`data`, `security`, `privacy`, `finance`, `compliance`). The others only rule out minor. Irreversibility is not a dimension: set `risk.reversible: false`, which also makes the change major. `confidence: medium` changes nothing in the gate. It tells the Approver which facts you could not check: list them in `open_questions`.

<!-- aidd:gen vocab:dimension -->
| Token | Meaning |
| --- | --- |
| `data` | Reads, writes, migrates, or deletes persistent or production data. Forces major; the `data` pool reviews. |
| `security` | Who can do what, and what can leak: authentication, authorization, roles, tokens, secrets, cryptography, attack surface. Forces major; the `security` pool reviews. |
| `privacy` | Personal data: collection, retention, sharing, deletion, consent. Forces major; the `privacy` pool reviews. |
| `financial` | Money moves or prices change: billing, payouts, pricing, ledgers, tax. Forces major; the `finance` pool reviews. |
| `compliance` | A legal, contractual, or regulatory control. Forces major; the `compliance` pool reviews. |
| `availability` | Can take a service down or degrade it: infrastructure, capacity, timeouts, limits. Rules out minor. |
| `third_party` | Adds or changes third-party code, services, images, or build inputs. Rules out minor. |
| `cost` | Can change spend materially: compute, storage, paid APIs, model tokens. Rules out minor. |
<!-- aidd:end -->

Declare every dimension the diff implies. A path rule that adds a dimension you did not declare fails an inline Change Request block and warns on a Spec.

## Route meanings

<!-- aidd:gen vocab:route -->
| Token | Meaning |
| --- | --- |
| `standard` | A pre-approved change class from config standard_changes, such as a bot's dependency patch. Merges on green tests with no human approval. Never touches protected paths. |
| `minor` | Small, reversible, one Task, no risk dimension, within the minor budget. No Spec file needed; one Merge approval. |
| `normal` | Everything that is not minor, standard, major, or emergency. Spec, Spec approval, SHA-bound tests with red-then-green, one Merge approval. |
| `major` | Touches a protected path, data, security, privacy, money, or compliance, or cannot be reverted. Normal plus an observe block and stricter profile gates, and, from the team profile up, a specialist approval. Computed by the gate, never guessed. |
| `emergency` | Production is broken now and this change is the repair. Allowed under a freeze. Smoke tests still run; the Spec and the review follow by review_due. |
<!-- aidd:end -->

## Change types

Conventional Commits vocabulary, so the type in the Spec is the type in the commit message.

<!-- aidd:gen vocab:type -->
| Token | Meaning |
| --- | --- |
| `feat` | New or changed behavior someone can see. Needs a new-behavior test on normal and major. |
| `fix` | Restores intended behavior. Needs a test that fails before the fix (red) and passes after (green). |
| `refactor` | Structure changes, behavior does not. Existing tests must stay green. |
| `perf` | Same behavior, different cost. Acceptance is a threshold. |
| `docs` | Documentation, content, or generated reference only. |
| `test` | Tests only; no behavior changes. |
| `build` | Build system, packaging, or developer tooling. |
| `ci` | Continuous integration or delivery pipelines and agent configuration. |
| `chore` | Housekeeping that changes no behavior: formatting, renames, cleanup. |
| `deps` | Adds, removes, or upgrades a third-party package. |
| `infra` | Runtime, network, or deployment infrastructure, including infrastructure as code. |
| `data` | Schema, migration, backfill, or production data. Always major. |
| `security` | Identity, access, roles, secrets, or cryptography. Always major. |
| `compliance` | Driven by a legal or regulatory control. Always major. |
<!-- aidd:end -->

## Built-in path rules

Protected paths gate the gate itself: the aidd config (`.aidd/`), CI, CODEOWNERS, and agent instructions and skills. They are always major, and a repo cannot disable them. A repo may add rules and paths. It may also disable a `baseline:` rule by name in the config, which is itself a protected change.

The baseline does not protect `SECURITY.md`. A project that publishes a security contact adds `SECURITY.md`, `docs/SECURITY.md`, and `.github/SECURITY.md` to `protected_paths`.

To find the rule a path matches, run `aidd gate --paths <path>`: it names the rule. Never match a glob by hand. `aidd gate --explain route` says how the gate computes the route.

A rule that names dependencies also fires when the diff adds one of them to a manifest (package.json, requirements, pyproject.toml, go.mod, pom.xml, a .csproj, a Gemfile, and the like). It fires wherever the code that uses the dependency sits. Adding `stripe` routes a change as payments even in `lib/money.ts`. Adding `left-pad` changes nothing beyond the dependency rule. A version change never matches. On a branch, `aidd gate` names the dependency in the route's reasons, and the domain packs the added dependencies call for.

<!-- aidd:gen baseline:summary -->
| Rule | Minimum route | Dimensions | Paths | Added dependencies |
| --- | --- | --- | --- | --- |
| protected (cannot be disabled) | major | none | 95 | none |
| `baseline:dependencies` | normal | third_party | 47 | none |
| `baseline:build-tooling` | normal | third_party | 18 | none |
| `baseline:containers` | normal | third_party | 6 | none |
| `baseline:test-config` | normal | none | 10 | none |
| `baseline:quality-config` | normal | none | 40 | none |
| `baseline:iac` | normal | availability | 34 | none |
| `baseline:mobile-manifests` | normal | none | 4 | none |
| `baseline:design-system` | normal | none | 4 | none |
| `baseline:standards` | normal | none | 1 | none |
| `baseline:module-api` | normal | none | 1 | none |
| `baseline:module-boundaries` | major | none | 9 | none |
| `baseline:migrations` | major | data | 12 | `prisma`, `drizzle-kit`, `knex`, `typeorm`, `alembic`, `flyway-core`, `liquibase-core`, `activerecord`, `github.com/golang-migrate/migrate/`, `github.com/pressly/goose/` |
| `baseline:auth` | major | security | 24 | `next-auth`, `@auth/`, `passport`, `lucia`, `better-auth`, `django-allauth`, `django.contrib.auth`, `flask-login`, `authlib`, `spring-boot-starter-security`, `Microsoft.AspNetCore.Identity`, `Microsoft.AspNetCore.Identity.EntityFrameworkCore`, `devise`, `omniauth` |
| `baseline:personal-data` | major | privacy | 55 | `next-auth`, `@auth/`, `passport`, `lucia`, `better-auth`, `django-allauth`, `django.contrib.auth`, `flask-login`, `authlib`, `spring-boot-starter-security`, `Microsoft.AspNetCore.Identity`, `Microsoft.AspNetCore.Identity.EntityFrameworkCore`, `devise`, `omniauth` |
| `baseline:secrets-crypto` | major | security | 20 | none |
| `baseline:payments` | major | financial | 9 | `stripe`, `@stripe/`, `stripe-java`, `Stripe.net`, `stripe/stripe-php`, `github.com/stripe/stripe-go/`, `laravel/cashier`, `braintree`, `braintree-java`, `@adyen/`, `adyen`, `adyen-java-api-library`, `adyen-ruby-api-library`, `@paypal/`, `paypal-server-sdk`, `paypalrestsdk`, `paypal-checkout-serversdk` |
<!-- aidd:end -->

## Confidence

<!-- aidd:gen vocab:confidence -->
| Token | Meaning |
| --- | --- |
| `high` | Every fact that could change the route is known. open_questions is empty. |
| `medium` | Some facts are missing, and none of them could change the route. List them; the gate does not act on medium. |
| `low` | A missing fact could change the route. Stop and ask. |
<!-- aidd:end -->
