# Standards and stacks

This page lists aidd's library of opinionated standards, its stacks, and the open choices they fill. `aidd gen-docs` writes the tables from `schemas/roles.json`, `standards/`, and `stacks/`, so never edit a table by hand.

## The words

- An **industry standard** is what the field agrees on, such as WCAG or SLSA. It lives only in the registry, `schemas/roles.json`, never in a project's `[[standards]]`, and the packs and practice skills cite it. It applies everywhere. A project can only waive it, with a reason and an expiry.
- An **opinionated standard** is one choice that a team or a company commits to, such as Ruff for Python. It applies only where a project adopts it.
- An **open choice** is a decision that a pack or a practice skill leaves to the team. Each one has aidd's default answer. An opinionated standard fills one or more open choices, so it never restates a rule of a pack.
- A **stack** is a set of opinionated standards that go together, plus entries for `[project.stack]`. It holds no rule text of its own.
- The **method** is how aidd works: the routes, the approvals, the gate, Conventional Commits, and `Assisted-by:`. It is never a standard, and never an open choice.

[GLOSSARY.md](GLOSSARY.md) has each term.

## Adopt a standard or a stack

1. Run `aidd standard list` to see the open choices and the library.
2. Run `aidd standard add <id>`, or `aidd stack add <name>` for a set.
3. Review the copies and the config as one change. The change edits `.aidd/config.toml`, a protected path, so its route is major.

Each command copies the file into `docs/standards/`. It writes a `[[standards]]` entry that records the library id, aidd's version, and the SHA-256 of the copy. It also writes the standard's `[[tests]]`, named `std.<group>.<topic>.<name>`, so the gate runs them. `aidd stack add` also merges the stack's entries into `[project.stack]`. Both commands add all the ids or none of them.

Never edit a copy. To change a rule, write your own standard and name it in `[standards_policy] replace`. An edit under `docs/standards/` routes normal at least (`baseline:standards`), so a person approves it as a Spec. `aidd doctor` reports an edited copy, a copy that is older than the library, a deprecated or renamed id, and a policy breach. `aidd upgrade --yes` refreshes each copy that nobody edited.

The library can hold several standards for one open choice in one ecosystem. Exactly one of them is aidd's default, marked `default = true`, and `aidd eval standards` checks it. Where a choice has options, the table below and `aidd standard list` name the default.

A project keeps one standard for each open choice in each ecosystem. A polyglot project can fill `ci-pipeline:linter` once for Python and once for TypeScript. `aidd standard add` refuses a second standard for one choice, and `aidd doctor` warns about one written by hand. A stack picks one standard for each choice, whatever folder each one lives in.

## How the library selects a standard

- A choice can offer a modern or edge-first standard and a battle-tested one, when teams genuinely differ.
- Exactly one option is aidd's default. The default follows the direction of the library's owner: edge-first, Biome, and the other current defaults.
- Hosting cost decides where a workload runs. It does not decide which tool is the default.
- Each standard states its licence plainly. A licence alone is never a reason to drop a mainstream tool.
- Standards are opt-in. A project adopts each one, and an agent loads it only when a change touches its `when_changed` paths.
- A stack picks one standard for each choice.
- A company's org preset can require a standard, exclude it, or replace it with its own, as the next section shows.

## A company's policy

A company writes `[standards_policy]` in its org preset:

```toml
[standards_policy]
require = ["python/uv-tooling"]                     # every project carries it; `aidd doctor` fails until it does
exclude = ["python/mypy-typing"]                    # no project adds it
replace = { "python/ruff-lint-format" = "lint" }    # the company's own [[standards]] entry `lint` takes its place
allow_stacks = ["python-cli"]                       # the only stacks a project may add
```

The policy takes opinionated library ids only. aidd refuses an industry id there: an industry standard is only waived per project, with a reason and an expiry. A project config adds to the policy and tightens it. It cannot drop an entry of the company, require what the company excludes, or allow another stack. [CONFIG.md](CONFIG.md#standards-policy) has the fields.

## Open choices

<!-- aidd:gen standards:open-choices -->
| Choice | Question | aidd's default | Library standards |
| --- | --- | --- | --- |
| `web-front-end:web-framework` | Which framework renders the web front end? | The framework the app already uses. For a new app, one that renders on the server and meets the browser support target. | `typescript/nextjs-app-router` |
| `web-front-end:e2e-test` | Which runner drives a real browser for end-to-end tests? | Playwright (`@playwright/test`), which the browser checks of `aidd-team:accessible-ui` and `aidd-team:product-defaults` also run. | `typescript/playwright-e2e` |
| `web-front-end:component-test` | Which library tests a component the way a person uses it? | Testing Library for the web framework in use, run by the project's test runner. | `typescript/testing-library` |
| `apis-and-services:api-framework` | Which framework serves the API? | The framework the service already uses. For a new service, the ecosystem's common framework that serves the OpenAPI contract. | `dotnet/minimal-apis`, `go/net-http`, `java/spring-boot`, `python/django`, `python/fastapi-api` (default), `rust/axum`, `typescript/fastify-api`, `typescript/hono-api` (default) |
| `apis-and-services:validation-library` | Which library validates input against the contract at the boundary? | A schema library that the contract and the types come from, so one definition checks the input and documents it. | `python/pydantic-validation`, `typescript/zod-validation` |
| `mobile-apps:mobile-framework` | Which framework builds the iOS and Android apps? | The framework the app already uses. For a new cross-platform app, Expo (React Native) when the team writes TypeScript, and Flutter when it writes Dart. | `dart/flutter`, `typescript/expo` |
| `mobile-apps:mobile-ui-test` | Which runner drives the app's UI tests on a device or an emulator? | Maestro for an Expo app, `integration_test` for a Flutter app, XCUITest and Espresso for a native app, and Detox for React Native without Expo. | `dart/integration-test`, `typescript/maestro` |
| `ai-features:llm-gateway` | Does a gateway sit between the code and the model providers? | No gateway for one provider: one module calls its SDK and sets max_tokens, a timeout, and bounded retries. Add a gateway when the product needs two providers, a fallback, or shared spend caps. | `cloudflare/ai-gateway` |
| `ai-features:llm-budget-mechanism` | Where are the caps on model spending enforced? | In the one module that calls the model, through the provider's SDK, with the provider's own spend limit behind it. A gateway's budgets per key take over once the project runs a gateway. | `cost/llm-spend-caps` |
| `ai-agents-and-tools:agent-framework` | Which framework runs the agent loop? | The framework the project already uses. Otherwise the model provider's own SDK, with the loop, its step cap, and its tools in the team's code. | `python/langgraph-agents`, `typescript/ai-sdk` |
| `ai-agents-and-tools:mcp-server-framework` | Which library builds an MCP server? | The official MCP SDK for the server's language, because it follows each new version of the protocol first. FastMCP, a Python framework on top of the protocol, where the team wants its shorter server code. | `python/fastmcp-server`, `typescript/mcp-sdk` |
| `ai-agents-and-tools:trace-backend` | Where do the agent's traces go? | The tracing backend the team already runs, fed over OTLP with the OpenTelemetry GenAI conventions. | — |
| `cloud-and-infrastructure:hosting-target` | Which provider and platform host the application? | The provider the project already uses. For a new project, the lowest-cost provider for the placement that `references/cost-and-performance.md` picks. | `cloudflare/static-assets`, `cost/low-cost-placement` |
| `cloud-and-infrastructure:serverless-compute` | Which product runs the functions or containers that scale to zero? | The host's own: its functions for spiky, short requests, and its container service for steady or long ones, each with a concurrency or instance cap. | `aws/lambda-arm64`, `cloudflare/workers-compute`, `gcp/cloud-run` |
| `cloud-and-infrastructure:object-storage` | Which store holds files and objects? | The host's object store, private by default, with a lifecycle rule that expires what nobody keeps. | `aws/s3-lifecycle`, `cloudflare/r2-storage`, `gcp/registry-cleanup` |
| `cloud-and-infrastructure:database` | Which database holds the application's data? | A managed PostgreSQL with pooled connections, unless the access pattern needs a key-value or an edge store. | `aws/dynamodb-on-demand`, `cloudflare/d1-or-hyperdrive` |
| `cloud-and-infrastructure:queue` | Which queue carries background work and events? | The host's managed queue, with a retry limit and a dead-letter queue on every consumer. | `cloudflare/queues-workflows` |
| `cloud-and-infrastructure:iac-tool` | Which tool defines the infrastructure as code? | OpenTofu. Wrangler alone for a project that runs only on Cloudflare. | `cloudflare/wrangler`, `iac/opentofu` (default), `iac/terraform` |
| `cloud-and-infrastructure:cost-estimate-tool` | Which tool estimates the monthly cost of a plan? | Infracost, whose CLI sends resource parameters to Infracost's pricing API or to a self-hosted endpoint. Without it, the provider's pricing calculator. | `cost/pr-cost-delta-threshold` |
| `cloud-and-infrastructure:policy-tool` | Which tool runs the policies over the plan? | Conftest with OPA policies, as the Policy as code and Tag and budget policy rows run it. | `cost/policy-caps` |
| `cloud-and-infrastructure:budget-alerts` | When does a budget alert fire? | At 50, 80, and 100 percent of each environment's budget, and on the forecast passing it. | `aws/budgets-anomaly`, `cloudflare/budget-alerts`, `cost/alert-thresholds`, `gcp/budgets` |
| `cloud-and-infrastructure:spend-caps` | What stops the spending, beyond an alert? | A hard cap where the provider supports one; otherwise an automated action on a budget alert (AWS Budgets actions; on Google Cloud, a budget notification that runs the team's own shutdown code) or per-service limits (Cloudflare Workers CPU time and subrequest limits). | `aws/hard-caps`, `cloudflare/workers-limits`, `cost/spend-caps`, `gcp/hard-caps` |
| `cloud-and-infrastructure:egress-and-nat` | How does private compute reach the internet? | No NAT gateway unless the change's design names it; private endpoints or public egress from the managed service first. | `aws/no-default-nat` |
| `cloud-and-infrastructure:compute-architecture` | Which processor architecture do functions and containers run on? | arm64 first where the provider and every dependency support it, and x86-64 otherwise. | `cost/arm64-first` |
| `ci-pipeline:formatter` | Which formatter sets the layout of the code? | The ecosystem's common formatter, pinned, run in CI and in a pre-commit hook (`dev_basics`). | `dart/dart-format`, `dotnet/dotnet-format`, `go/golangci-lint`, `java/spotless-format`, `python/ruff-lint-format`, `rust/rustfmt`, `typescript/biome-lint-format` (default), `typescript/eslint-prettier` |
| `ci-pipeline:linter` | Which linter checks the code? | The ecosystem's common linter, pinned, run in CI and in a pre-commit hook (`dev_basics`). | `dart/flutter-analyze`, `dotnet/analyzers-nullable`, `go/golangci-lint`, `java/error-prone`, `python/ruff-lint-format`, `rust/clippy`, `typescript/biome-lint-format` (default), `typescript/eslint-prettier` |
| `ci-pipeline:type-checker` | Which type checker runs in CI? | The language's own strict type check, run in CI (`dev_basics`). | `dotnet/analyzers-nullable`, `python/mypy-typing`, `typescript/tsc-strict` |
| `ci-pipeline:package-manager` | Which tool installs and locks the dependencies? | The ecosystem's standard package manager, with the lockfile committed. | `dotnet/central-package-management`, `go/go-modules`, `java/gradle-kotlin-dsl` (default), `java/maven`, `python/uv-tooling`, `rust/cargo-lockfile`, `typescript/pnpm-tooling` |
| `ci-pipeline:test-runner` | Which test runner runs the unit and integration tests? | The ecosystem's common test runner, pinned, run in CI on every change. | `dart/flutter-test`, `dotnet/xunit-v3`, `go/go-test-race`, `java/junit`, `python/pytest-tests`, `rust/cargo-nextest`, `typescript/jest-expo`, `typescript/vitest-tests` (default) |
| `ci-pipeline:dependency-audit` | Which audit of the locked dependencies runs next to OSV-Scanner? | None beyond OSV-Scanner, which the Dependency scan of `aidd-team:enterprise-controls` pins and runs over every lockfile. A standard that fills this choice adds the ecosystem's own audit. | `go/govulncheck`, `rust/cargo-deny` |
| `ci-pipeline:language-version` | Which language and runtime version does the project target, and where is it pinned? | The newest release with long-term support (or the current stable release where there is no LTS), pinned in one file that CI and every developer read. | `dart/sdk-constraint`, `dotnet/dotnet-lts`, `go/go-version`, `java/java-lts`, `python/python-version`, `rust/msrv`, `typescript/node-lts` |
| `ci-pipeline:workspace` | Which workspace tool holds the apps, modules, and packages in one repository? | The package manager's own workspaces: one package per module, one lockfile, and one version of each dependency. Add a task runner only when builds need a cache. | `dotnet/slnx-central-packages`, `go/single-module`, `java/gradle-multi-project` (default), `java/maven-multi-module`, `python/pants`, `python/uv-workspace` (default), `rust/cargo-workspace`, `typescript/nx-workspace`, `typescript/pnpm-turborepo-workspace` (default) |
| `modular-monolith:module-boundaries` | Which check enforces the module dependency rules in CI? | The language's own visibility first, then an import-rule check over the whole repository on every change, with a violations baseline that never grows. | `cloudflare/d1-table-prefixes`, `dotnet/archunitnet`, `go/depguard-boundaries` (default), `go/go-arch-lint`, `java/archunit`, `java/spring-modulith` (default), `postgres/cross-schema-foreign-keys`, `python/import-linter` (default), `python/tach`, `rust/cargo-modules`, `rust/cargo-workspace-boundaries` (default), `typescript/dependency-cruiser` (default), `typescript/nx-module-boundaries` |
| `observability:logging-library` | Which library writes the structured logs? | The language's standard structured logger, such as slog for Go, writing one JSON line per event. | `go/slog`, `python/structlog`, `typescript/pino-logging` |
| `observability:log-retention` | How long does each log group keep its logs? | 30 days in production, unless a regulation sets another period. | `aws/log-retention`, `gcp/log-retention` |
| `release-rollout:preview-environment-ttl` | When is a preview environment deleted? | Deleted when its pull request closes, and after a set number of days at most, so no preview keeps running unwatched. | `cost/preview-env-ttl` |
| `release-rollout:cost-kill-switch` | How does the team cut a path whose cost runs out of control? | A tested runbook that scales the service to zero or turns off the expensive path, rehearsed like a rollback. | `cost/kill-switch` |
| `schema-migration:orm` | Which library maps the code to the database? | The data-access library the project already uses. For a new project, the ecosystem's common one that checks its models against the schema. | `dotnet/ef-core`, `go/gorm`, `go/sqlc` (default), `java/spring-data-jpa`, `python/django`, `python/sqlalchemy-orm` (default), `rust/sqlx`, `typescript/drizzle-orm` (default), `typescript/prisma-orm` |
| `schema-migration:migration-tool` | Which tool writes and applies the migrations? | The migration tool of the data-access library, with versioned scripts, checksums, and a down path. | `cloudflare/d1-migrations`, `dotnet/ef-core-migrations`, `go/atlas-migrations`, `java/flyway-migrations`, `python/alembic-migrations` (default), `python/django`, `typescript/atlas-migrations` |
| `test-design:integration-test-services` | How does an integration test start the databases and services it needs? | Testcontainers where the ecosystem has a library for it, one throwaway container per test run. | `dotnet/testcontainers`, `go/testcontainers`, `java/testcontainers`, `python/testcontainers`, `typescript/testcontainers` |
<!-- aidd:end -->

## Where a tool is decided

Before the library grew, aidd listed each tool that a pack or a practice skill already pins, and compared it with the choices the library fills. A pack keeps a tool when its own check needs that tool. Otherwise the pack opens a choice, and the tool becomes aidd's default for that choice.

`aidd eval standards` checks both rules. It fails when two packs or skills declare the same choice. It also fails when a pack opens a choice and one of its test commands names one answer alone, without the choice.

| Tool | Where | Decision | Why |
| --- | --- | --- | --- |
| OSV-Scanner | `enterprise-controls`, Dependency scan | Keep | The security workflow and the gate's evidence run it. `ci-pipeline:dependency-audit` asks which ecosystem audit runs next to it. |
| Playwright | `accessible-ui`, `product-defaults`, `prototyping`, `payments-and-finance` | Keep | These checks use what Playwright gives: axe in the page, `emulateMedia`, screenshots, and a record of each script request. |
| Playwright | `web-front-end`, consent test | Open: `web-front-end:e2e-test` | Any browser runner can record cookies, storage, and requests. Playwright is the default. |
| ESLint plugins and Stylelint | `web-front-end` | Keep | They hold the pack's rules for accessibility, security, browser support, and design tokens. `ci-pipeline:linter` picks the main linter. |
| Infracost | `cloud-and-infrastructure`, Cost diff threshold | Open: `cloud-and-infrastructure:cost-estimate-tool` | Infracost is the default, and the provider's calculator is the other answer. The pinned command stays for the default. |
| Conftest | `cloud-and-infrastructure`, Tag and budget policy | Open: `cloud-and-infrastructure:policy-tool` | Conftest is the default. The Policy as code row already allows Kyverno. |
| OpenTofu, Terraform, Pulumi, AWS CDK, Wrangler | `cloud-and-infrastructure`, Plan or dry-run check | Open: `cloud-and-infrastructure:iac-tool` | The check gives a command for each tool, so it decides none. OpenTofu is the default. |
| `uv build`, `npm publish`, `cargo publish` | `package-publishing`, Publish dry run | Keep | Each one is the registry's own publish check. It works with any package manager. |
| squawk | `schema-migration`, Migration lint | Keep | It is a lint for safe DDL on Postgres, not a migration tool. |
| Store SDK floors | `mobile-apps` | Keep | The stores set them on a calendar. `ci-pipeline:language-version` is the version of the language. |
| XCUITest, Espresso, Detox | `mobile-apps`, UI tests | Open: `mobile-apps:mobile-ui-test` | The row runs the team's runner. Maestro is the default for Expo, and `integration_test` for Flutter. |
| XCUITest, Espresso | `accessible-ui`, Mobile accessibility checks; `prototyping` | Keep | The accessibility audits run in them. An Expo app on Maestro still needs both for the audit. |
| Testcontainers | `test-design`, its real-dependencies reference | Open: `test-design:integration-test-services` | The reference teaches the practice, and Testcontainers is the default where the ecosystem has it. |

`schema-migration` holds `orm` and `migration-tool`, because `data-and-analytics` gives the migration plan to it.

The cost guards rest on industry rows that the registry already has. OWASP API Security Top 10, API4:2023 (Unrestricted Resource Consumption), covers rate limits, quotas, timeouts, and spending limits. OWASP Top 10 for LLM Applications 2026, LLM06 (Unbounded Consumption), covers token limits and hard spending caps. The Builders' Library and Google SRE rows cover timeouts, bounded retries, and retry budgets. The cloud pack already requires a concurrency or instance cap on every function and autoscaler.

A requirement is a pack rule that cites the registry. Only the way to meet it is an open choice. So `ai-features` requires caps in layers on model spending (LLM06), and `ai-features:llm-budget-mechanism` asks where they are enforced. `observability` requires a set retention on each log group, and `observability:log-retention` sets the period.

The other cost guards are open choices in the closest pack or skill. `cloud-and-infrastructure` holds `budget-alerts`, `spend-caps`, `egress-and-nat`, and `compute-architecture`. `release-rollout` holds `preview-environment-ttl` and `cost-kill-switch`.

## The library, by ecosystem

<!-- aidd:gen standards:library -->
### aws

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `aws/budgets-anomaly` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/dynamodb-on-demand` | `cloud-and-infrastructure:database` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/hard-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/lambda-arm64` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/log-retention` | `observability:log-retention` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/no-default-nat` | `cloud-and-infrastructure:egress-and-nat` | — | — | 2026-10-07 | 2026-10-07 | active |
| `aws/s3-lifecycle` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-07 | 2026-10-07 | active |

### cloudflare

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `cloudflare/ai-gateway` | `ai-features:llm-gateway` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/budget-alerts` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/d1-migrations` | `schema-migration:migration-tool` | — | — | 2026-10-09 | 2026-10-09 | active |
| `cloudflare/d1-or-hyperdrive` | `cloud-and-infrastructure:database` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/d1-table-prefixes` | `modular-monolith:module-boundaries` | — | — | 2026-10-09 | 2026-10-09 | active |
| `cloudflare/queues-workflows` | `cloud-and-infrastructure:queue` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/r2-storage` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/static-assets` | `cloud-and-infrastructure:hosting-target` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/workers-compute` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/workers-limits` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cloudflare/wrangler` | `cloud-and-infrastructure:iac-tool` | — | — | 2026-10-07 | 2026-10-07 | active |

### cost

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `cost/alert-thresholds` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/arm64-first` | `cloud-and-infrastructure:compute-architecture` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/kill-switch` | `release-rollout:cost-kill-switch` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/llm-spend-caps` | `ai-features:llm-budget-mechanism` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/low-cost-placement` | `cloud-and-infrastructure:hosting-target` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/policy-caps` | `cloud-and-infrastructure:policy-tool` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/pr-cost-delta-threshold` | `cloud-and-infrastructure:cost-estimate-tool` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/preview-env-ttl` | `release-rollout:preview-environment-ttl` | — | — | 2026-10-07 | 2026-10-07 | active |
| `cost/spend-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-07 | 2026-10-07 | active |

### dart

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `dart/dart-format` | `ci-pipeline:formatter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dart/flutter` | `mobile-apps:mobile-framework` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dart/flutter-analyze` | `ci-pipeline:linter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dart/flutter-test` | `ci-pipeline:test-runner` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dart/integration-test` | `mobile-apps:mobile-ui-test` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dart/sdk-constraint` | `ci-pipeline:language-version` | — | — | 2026-10-07 | 2026-10-07 | active |

### dotnet

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `dotnet/analyzers-nullable` | `ci-pipeline:type-checker`, `ci-pipeline:linter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dotnet/archunitnet` | `modular-monolith:module-boundaries` | archunitnet | 0.13.4 | 2026-10-09 | 2026-10-09 | active |
| `dotnet/central-package-management` | `ci-pipeline:package-manager` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dotnet/dotnet-format` | `ci-pipeline:formatter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `dotnet/dotnet-lts` | `ci-pipeline:language-version` | dotnet | 10.0.401 | 2026-10-07 | 2026-10-07 | active |
| `dotnet/ef-core` | `schema-migration:orm` | entity-framework-core | 10.0.12 | 2026-10-07 | 2026-10-07 | active |
| `dotnet/ef-core-migrations` | `schema-migration:migration-tool` | dotnet-ef | 10.0.12 | 2026-10-07 | 2026-10-07 | active |
| `dotnet/minimal-apis` | `apis-and-services:api-framework` | aspnetcore-openapi | 10.0.12 | 2026-10-07 | 2026-10-07 | active |
| `dotnet/slnx-central-packages` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |
| `dotnet/testcontainers` | `test-design:integration-test-services` | testcontainers-dotnet | 4.15.0 | 2026-10-07 | 2026-10-07 | active |
| `dotnet/xunit-v3` | `ci-pipeline:test-runner` | xunit | 4.0.1 | 2026-10-07 | 2026-10-07 | active |

### gcp

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `gcp/budgets` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-07 | 2026-10-07 | active |
| `gcp/cloud-run` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-07 | 2026-10-07 | active |
| `gcp/hard-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-07 | 2026-10-07 | active |
| `gcp/log-retention` | `observability:log-retention` | — | — | 2026-10-07 | 2026-10-07 | active |
| `gcp/registry-cleanup` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-07 | 2026-10-07 | active |

### go

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `go/atlas-migrations` | `schema-migration:migration-tool` | — | — | 2026-10-09 | 2026-10-09 | active |
| `go/depguard-boundaries` | `modular-monolith:module-boundaries` | — | — | 2026-10-09 | 2026-10-09 | active |
| `go/go-arch-lint` | `modular-monolith:module-boundaries` | go-arch-lint | v1.19.0 | 2026-10-09 | 2026-10-09 | active |
| `go/go-modules` | `ci-pipeline:package-manager` | — | — | 2026-10-07 | 2026-10-07 | active |
| `go/go-test-race` | `ci-pipeline:test-runner` | — | — | 2026-10-07 | 2026-10-07 | active |
| `go/go-version` | `ci-pipeline:language-version` | go | 1.27.1 | 2026-10-07 | 2026-10-07 | active |
| `go/golangci-lint` | `ci-pipeline:linter`, `ci-pipeline:formatter` | golangci-lint | v2.14.0 | 2026-10-07 | 2026-10-07 | active |
| `go/gorm` | `schema-migration:orm` | gorm | v1.31.2 | 2026-10-09 | 2026-10-09 | active |
| `go/govulncheck` | `ci-pipeline:dependency-audit` | govulncheck | v1.8.0 | 2026-10-07 | 2026-10-07 | active |
| `go/net-http` | `apis-and-services:api-framework` | — | — | 2026-10-07 | 2026-10-07 | active |
| `go/single-module` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |
| `go/slog` | `observability:logging-library` | — | — | 2026-10-07 | 2026-10-07 | active |
| `go/sqlc` | `schema-migration:orm` | sqlc | v1.31.1 | 2026-10-07 | 2026-10-07 | active |
| `go/testcontainers` | `test-design:integration-test-services` | testcontainers-go | v0.44.0 | 2026-10-09 | 2026-10-09 | active |

### iac

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `iac/opentofu` | `cloud-and-infrastructure:iac-tool` | opentofu | 1.13.1 | 2026-10-07 | 2026-10-07 | active |
| `iac/terraform` | `cloud-and-infrastructure:iac-tool` | terraform | 1.16.5 | 2026-10-09 | 2026-10-09 | active |

### java

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `java/archunit` | `modular-monolith:module-boundaries` | archunit | 1.5.1 | 2026-10-09 | 2026-10-09 | active |
| `java/error-prone` | `ci-pipeline:linter` | error-prone | 2.50.0 | 2026-10-07 | 2026-10-07 | active |
| `java/flyway-migrations` | `schema-migration:migration-tool` | flyway | 13.9.0 | 2026-10-07 | 2026-10-07 | active |
| `java/gradle-kotlin-dsl` | `ci-pipeline:package-manager` | gradle | 9.8.0 | 2026-10-07 | 2026-10-07 | active |
| `java/gradle-multi-project` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |
| `java/java-lts` | `ci-pipeline:language-version` | java | 25 | 2026-10-07 | 2026-10-07 | active |
| `java/junit` | `ci-pipeline:test-runner` | junit | 6.1.3 | 2026-10-07 | 2026-10-07 | active |
| `java/maven` | `ci-pipeline:package-manager` | maven | 3.10.0 | 2026-10-09 | 2026-10-09 | active |
| `java/maven-multi-module` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |
| `java/spotless-format` | `ci-pipeline:formatter` | spotless | 8.10.3 | 2026-10-07 | 2026-10-07 | active |
| `java/spring-boot` | `apis-and-services:api-framework` | spring-boot | 4.1.1 | 2026-10-07 | 2026-10-07 | active |
| `java/spring-data-jpa` | `schema-migration:orm` | spring-data-jpa | 4.1.1 | 2026-10-09 | 2026-10-09 | active |
| `java/spring-modulith` | `modular-monolith:module-boundaries` | spring-modulith | 2.1.1 | 2026-10-09 | 2026-10-09 | active |
| `java/testcontainers` | `test-design:integration-test-services` | testcontainers | 2.0.5 | 2026-10-07 | 2026-10-07 | active |

### postgres

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `postgres/cross-schema-foreign-keys` | `modular-monolith:module-boundaries` | — | — | 2026-10-09 | 2026-10-09 | active |

### python

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `python/alembic-migrations` | `schema-migration:migration-tool` | alembic | 1.20.0 | 2026-10-07 | 2026-10-07 | active |
| `python/django` | `apis-and-services:api-framework`, `schema-migration:orm`, `schema-migration:migration-tool` | django | 6.1.2 | 2026-10-09 | 2026-10-09 | active |
| `python/fastapi-api` | `apis-and-services:api-framework` | fastapi | 0.142.2 | 2026-10-07 | 2026-10-07 | active |
| `python/fastmcp-server` | `ai-agents-and-tools:mcp-server-framework` | fastmcp | 4.0.11 | 2026-10-07 | 2026-10-07 | active |
| `python/import-linter` | `modular-monolith:module-boundaries` | import-linter | 2.15 | 2026-10-09 | 2026-10-09 | active |
| `python/langgraph-agents` | `ai-agents-and-tools:agent-framework` | langgraph | 1.2.14 | 2026-10-07 | 2026-10-07 | active |
| `python/mypy-typing` | `ci-pipeline:type-checker` | mypy | 2.4.0 | 2026-10-07 | 2026-10-07 | active |
| `python/pants` | `ci-pipeline:workspace` | pants | 2.33.1 | 2026-10-09 | 2026-10-09 | active |
| `python/pydantic-validation` | `apis-and-services:validation-library` | pydantic | 2.13.5 | 2026-10-07 | 2026-10-07 | active |
| `python/pytest-tests` | `ci-pipeline:test-runner` | pytest | 9.1.1 | 2026-10-07 | 2026-10-07 | active |
| `python/python-version` | `ci-pipeline:language-version` | python | 3.14.8 | 2026-10-07 | 2026-10-07 | active |
| `python/ruff-lint-format` | `ci-pipeline:linter`, `ci-pipeline:formatter` | ruff | 0.16.10 | 2026-10-07 | 2026-10-07 | active |
| `python/sqlalchemy-orm` | `schema-migration:orm` | sqlalchemy | 2.1.3 | 2026-10-07 | 2026-10-07 | active |
| `python/structlog` | `observability:logging-library` | structlog | 26.1.0 | 2026-10-09 | 2026-10-09 | active |
| `python/tach` | `modular-monolith:module-boundaries` | tach | 0.35.3 | 2026-10-09 | 2026-10-09 | active |
| `python/testcontainers` | `test-design:integration-test-services` | testcontainers-python | 4.15.0 | 2026-10-09 | 2026-10-09 | active |
| `python/uv-tooling` | `ci-pipeline:package-manager` | uv | 0.12.23 | 2026-10-07 | 2026-10-07 | active |
| `python/uv-workspace` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |

### rust

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `rust/axum` | `apis-and-services:api-framework` | axum | 0.8.9 | 2026-10-07 | 2026-10-07 | active |
| `rust/cargo-deny` | `ci-pipeline:dependency-audit` | cargo-deny | 0.20.2 | 2026-10-07 | 2026-10-07 | active |
| `rust/cargo-lockfile` | `ci-pipeline:package-manager` | — | — | 2026-10-07 | 2026-10-07 | active |
| `rust/cargo-modules` | `modular-monolith:module-boundaries` | cargo-modules | 0.27.0 | 2026-10-09 | 2026-10-09 | active |
| `rust/cargo-nextest` | `ci-pipeline:test-runner` | cargo-nextest | 0.9.146 | 2026-10-07 | 2026-10-07 | active |
| `rust/cargo-workspace` | `ci-pipeline:workspace` | — | — | 2026-10-09 | 2026-10-09 | active |
| `rust/cargo-workspace-boundaries` | `modular-monolith:module-boundaries` | — | — | 2026-10-09 | 2026-10-09 | active |
| `rust/clippy` | `ci-pipeline:linter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `rust/msrv` | `ci-pipeline:language-version` | rust | 1.99.0 | 2026-10-07 | 2026-10-07 | active |
| `rust/rustfmt` | `ci-pipeline:formatter` | — | — | 2026-10-07 | 2026-10-07 | active |
| `rust/sqlx` | `schema-migration:orm` | sqlx | 0.9.0 | 2026-10-07 | 2026-10-07 | active |

### typescript

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `typescript/ai-sdk` | `ai-agents-and-tools:agent-framework` | ai | 7.0.136 | 2026-10-09 | 2026-10-09 | active |
| `typescript/atlas-migrations` | `schema-migration:migration-tool` | atlas | 1.3.3 | 2026-10-09 | 2026-10-09 | active |
| `typescript/biome-lint-format` | `ci-pipeline:linter`, `ci-pipeline:formatter` | biome | 2.5.15 | 2026-10-07 | 2026-10-07 | active |
| `typescript/dependency-cruiser` | `modular-monolith:module-boundaries` | dependency-cruiser | 18.5.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/drizzle-orm` | `schema-migration:orm` | drizzle-orm | 0.45.4 | 2026-10-09 | 2026-10-09 | active |
| `typescript/eslint-prettier` | `ci-pipeline:linter`, `ci-pipeline:formatter` | eslint | 10.12.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/expo` | `mobile-apps:mobile-framework` | expo | 57.0.27 | 2026-10-07 | 2026-10-07 | active |
| `typescript/fastify-api` | `apis-and-services:api-framework` | fastify | 5.12.5 | 2026-10-09 | 2026-10-09 | active |
| `typescript/hono-api` | `apis-and-services:api-framework` | hono | 4.13.13 | 2026-10-07 | 2026-10-07 | active |
| `typescript/jest-expo` | `ci-pipeline:test-runner` | jest-expo | 57.0.5 | 2026-10-09 | 2026-10-09 | active |
| `typescript/maestro` | `mobile-apps:mobile-ui-test` | maestro | 2.11.0 | 2026-10-07 | 2026-10-07 | active |
| `typescript/mcp-sdk` | `ai-agents-and-tools:mcp-server-framework` | mcp-typescript-sdk | 2.3.1 | 2026-10-09 | 2026-10-09 | active |
| `typescript/nextjs-app-router` | `web-front-end:web-framework` | next | 16.4.0 | 2026-10-07 | 2026-10-07 | active |
| `typescript/node-lts` | `ci-pipeline:language-version` | node | 24.21.0 | 2026-10-07 | 2026-10-07 | active |
| `typescript/nx-module-boundaries` | `modular-monolith:module-boundaries` | nx-eslint-plugin | 23.3.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/nx-workspace` | `ci-pipeline:workspace` | nx | 23.3.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/pino-logging` | `observability:logging-library` | pino | 10.4.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/playwright-e2e` | `web-front-end:e2e-test` | — | — | 2026-10-07 | 2026-10-07 | active |
| `typescript/pnpm-tooling` | `ci-pipeline:package-manager` | pnpm | 12.10.1 | 2026-10-09 | 2026-10-07 | active |
| `typescript/pnpm-turborepo-workspace` | `ci-pipeline:workspace` | turbo | 2.11.7 | 2026-10-09 | 2026-10-09 | active |
| `typescript/prisma-orm` | `schema-migration:orm` | prisma | 7.10.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/testcontainers` | `test-design:integration-test-services` | testcontainers-node | 12.2.0 | 2026-10-09 | 2026-10-09 | active |
| `typescript/testing-library` | `web-front-end:component-test` | testing-library | 16.3.3 | 2026-10-07 | 2026-10-07 | active |
| `typescript/tsc-strict` | `ci-pipeline:type-checker` | typescript | 7.0.2 | 2026-10-07 | 2026-10-07 | active |
| `typescript/vitest-tests` | `ci-pipeline:test-runner` | vitest | 5.0.3 | 2026-10-07 | 2026-10-07 | active |
| `typescript/zod-validation` | `apis-and-services:validation-library` | zod | 4.6.5 | 2026-10-07 | 2026-10-07 | active |
<!-- aidd:end -->

## Stacks

<!-- aidd:gen standards:stacks -->
| Stack | For | Extends | Standards |
| --- | --- | --- | --- |
| `aws-serverless` | A serverless service on AWS: Lambda on arm64, DynamoDB on demand, S3 lifecycle, log retention, no default NAT, OpenTofu, and the cost guards. | — | `aws/lambda-arm64`, `aws/dynamodb-on-demand`, `aws/s3-lifecycle`, `aws/log-retention`, `aws/no-default-nat`, `aws/budgets-anomaly`, `aws/hard-caps`, `iac/opentofu`, `cost/arm64-first`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `cloudflare-fullstack` | A full web app only on Cloudflare: cloudflare-serverless plus the front end from static assets, R2, D1 or Hyperdrive, and AI Gateway. | `cloudflare-serverless` | `cloudflare/workers-compute`, `cloudflare/workers-limits`, `cloudflare/budget-alerts`, `cloudflare/queues-workflows`, `cloudflare/wrangler`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/kill-switch`, `cloudflare/static-assets`, `cloudflare/r2-storage`, `cloudflare/d1-or-hyperdrive`, `cloudflare/ai-gateway` |
| `cloudflare-serverless` | A service only on Cloudflare: Workers with their limits, budget alerts, Queues and Workflows, Wrangler, and the cost guards that a Wrangler project can run. | — | `cloudflare/workers-compute`, `cloudflare/workers-limits`, `cloudflare/budget-alerts`, `cloudflare/queues-workflows`, `cloudflare/wrangler`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/kill-switch` |
| `dotnet-api` | A .NET HTTP API on ASP.NET Core minimal APIs: the .NET LTS, Central Package Management, dotnet format, analyzers, xUnit, EF Core, Testcontainers, one .slnx, and ArchUnitNET. | — | `dotnet/dotnet-lts`, `dotnet/central-package-management`, `dotnet/dotnet-format`, `dotnet/analyzers-nullable`, `dotnet/xunit-v3`, `dotnet/minimal-apis`, `dotnet/ef-core-migrations`, `dotnet/ef-core`, `dotnet/testcontainers`, `dotnet/slnx-central-packages`, `dotnet/archunitnet` |
| `flutter-mobile` | A Flutter app in Dart: the stable channel, dart format, flutter analyze with flutter_lints, flutter test, integration_test, and the pubspec constraint. | — | `dart/sdk-constraint`, `dart/flutter`, `dart/dart-format`, `dart/flutter-analyze`, `dart/flutter-test`, `dart/integration-test` |
| `gcp-run` | A container service on Google Cloud Run: capped instances, log retention, storage and registry cleanup, budgets, OpenTofu, and the cost guards. | — | `gcp/cloud-run`, `gcp/registry-cleanup`, `gcp/log-retention`, `gcp/budgets`, `gcp/hard-caps`, `iac/opentofu`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `go-service` | A Go HTTP service: the Go toolchain pinned in go.mod, golangci-lint for lint and layout, go test with the race detector, govulncheck, net/http with slog, sqlc, one module, and depguard boundaries. | — | `go/go-version`, `go/go-modules`, `go/golangci-lint`, `go/go-test-race`, `go/govulncheck`, `go/net-http`, `go/slog`, `go/sqlc`, `go/single-module`, `go/depguard-boundaries` |
| `java-spring` | A Java HTTP service on Spring Boot: Gradle Kotlin DSL, Spotless, Error Prone, JUnit, the Java LTS, Flyway, Testcontainers, a multi-project build, and Spring Modulith. | — | `java/gradle-kotlin-dsl`, `java/spotless-format`, `java/error-prone`, `java/junit`, `java/java-lts`, `java/spring-boot`, `java/flyway-migrations`, `java/testcontainers`, `java/gradle-multi-project`, `java/spring-modulith` |
| `python-ai` | A Python agent service: the python-cli base plus pytest, a pinned Python, LangGraph for the agent loop, and Pydantic for structured data. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/langgraph-agents`, `python/pydantic-validation` |
| `python-api` | A Python HTTP service: the python-cli base plus pytest, a pinned Python, FastAPI, Pydantic, SQLAlchemy, Alembic, a uv workspace, and Import Linter. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/fastapi-api`, `python/pydantic-validation`, `python/sqlalchemy-orm`, `python/alembic-migrations`, `python/uv-workspace`, `python/import-linter` |
| `python-cli` | A Python command-line tool or library: uv for the environment, Ruff for lint and format, mypy for types. | — | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing` |
| `python-django` | A Python web service on Django: the python-cli base plus pytest, a pinned Python, and Django with Django REST framework for the API, the ORM, and the migrations. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/django` |
| `python-mcp` | A Python MCP server: the python-cli base plus pytest, a pinned Python, FastMCP, and Pydantic for the tools' input. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/fastmcp-server`, `python/pydantic-validation` |
| `rust-service` | A Rust HTTP service: a pinned toolchain with a declared MSRV, a committed Cargo.lock, rustfmt and Clippy, cargo-nextest, cargo-deny, axum on tokio, SQLx, and a Cargo workspace of module crates. | — | `rust/msrv`, `rust/cargo-lockfile`, `rust/rustfmt`, `rust/clippy`, `rust/cargo-nextest`, `rust/cargo-deny`, `rust/axum`, `rust/sqlx`, `rust/cargo-workspace`, `rust/cargo-workspace-boundaries` |
| `ts-api` | A TypeScript HTTP server on Node.js: the ts-library base plus Fastify, Zod at the boundary, Prisma 7 on a managed PostgreSQL, Atlas for its migrations, Turborepo, and dependency-cruiser. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/fastify-api`, `typescript/zod-validation`, `typescript/prisma-orm`, `typescript/atlas-migrations`, `typescript/pnpm-turborepo-workspace`, `typescript/dependency-cruiser` |
| `ts-api-edge` | A TypeScript API on Cloudflare Workers: the ts-library base plus Hono, Zod at the boundary, Drizzle on D1, Wrangler's forward-only D1 migrations, Turborepo, and dependency-cruiser. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/hono-api`, `typescript/zod-validation`, `typescript/drizzle-orm`, `cloudflare/workers-compute`, `cloudflare/d1-or-hyperdrive`, `cloudflare/d1-migrations`, `cloudflare/wrangler`, `typescript/pnpm-turborepo-workspace`, `typescript/dependency-cruiser` |
| `ts-library` | A TypeScript library or tool on Node.js LTS: pnpm for dependencies, Biome for lint and format, tsc strict for types, Vitest for tests. | — | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts` |
| `ts-mobile` | An Expo (React Native) app in TypeScript: pnpm, Biome, tsc strict, Node.js LTS, the current Expo SDK with EAS, Jest with jest-expo, and Maestro. | — | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/node-lts`, `typescript/jest-expo`, `typescript/expo`, `typescript/maestro` |
| `ts-web` | A TypeScript web app: the ts-library base plus Next.js with the App Router, Zod for input, Testing Library for components, and Playwright end to end. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/nextjs-app-router`, `typescript/zod-validation`, `typescript/testing-library`, `typescript/playwright-e2e` |
<!-- aidd:end -->

## Keep it current

- Each version is a field, never prose. It is read at the tool's release feed on the `checked` day, never typed from memory.
- Each week, the standards workflow runs `aidd eval standards --online`. That run reads the release feed of each tool: PyPI, npm, crates.io, Maven Central, NuGet, the Go module proxy, or GitHub releases. A language version uses its official toolchain feed: go.dev, nodejs.org, the .NET release index, Adoptium, or python.org. It flags a newer major release than `checked_version`. Before 1.0, a newer minor release counts as a major one. For Go and Python, a new minor release is a major one. A pre-release never counts. A standard with `version_policy = "latest_lts"` is compared with the newest LTS release, so a newer release that is not LTS does not flag it.
- Each standard names who read its source in `checked_by`: `agent:<harness>/<model>` for an agent's check, or a person's identity (`@login` or `email:<address>`, as an Approver is named) for a person's review. The catalog's entries are checked by an agent until a person reviews them, and an entry without `checked_by` counts as an agent's check. `aidd standard list` shows each standard's tier, and `aidd eval standards` counts both tiers.
- On a flag, a person reads the release notes. Then the person updates `checked_version`, `pin`, and `checked` in the library file.
- A person reviews each standard again after a year when it is established, and after 90 days when it is emerging.
- A new id never replaces an old one silently. `standards/renames.toml` keeps the old id, and a deprecated standard names its `replaced_by`.
- A new standard joins the library once two projects use it. Each change is a Spec ([CONTRIBUTING.md](../CONTRIBUTING.md#add-a-standard-or-a-stack)), and [plugins/README.md](../plugins/README.md#add-a-library-standard-or-a-stack) has the template.

## The format

A library standard is `standards/<group>/<topic>.md`, with TOML front matter between `+++` lines. Its body has 300 words at most.

<!-- aidd:gen fields:standard -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable id, `<group>/<topic>`, such as `python/ruff-lint-format`. It matches the file's path under `standards/`. A renamed id stays in `standards/renames.toml`. |
| `type` | `"opinionated"` | yes | Always `opinionated`: a choice a team commits to. An industry standard lives in the registry and is only waived per project. |
| `fills` | list of string | yes | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter`. Required for a library standard, so it cannot overlap a pack. |
| `default` | boolean | no | Whether it is aidd's default for each choice it fills, in its ecosystem. The library may hold several options for one choice; exactly one active option per choice and ecosystem is the default. A project adopts one of them. |
| `implements` | string | no | The pack or skill rule it puts to work, `<pack or skill>:<rule>`, such as `product-defaults:dev_basics`. It links the rule and never restates it. |
| `roles` | list of string | yes | aidd-team roles that read it before their step, or `*` for every role. |
| `when_changed` | list of string | no | Load it, and run its tests, only for a change that touches one of these paths. |
| `why` | string | yes | Why this option, in one or two sentences. |
| `reviewed` | string | yes | The day a person last reviewed the choice. Due again after a year when established, after 90 days when emerging. |
| `owner` | string | yes | The person or team who keeps it current: `@user`, `@org/team`, or `email:<address>`; never an agent. |
| `maturity` | `established` \| `emerging` | yes | Established tools are reviewed yearly; emerging ones every 90 days. |
| `tool` | any | no | The tool it chooses, and where its releases are published. The weekly standards check reads that feed and flags a newer major than `checked_version`. It reads stable releases only and, for `version_policy = "latest_lts"`, the newest LTS release where the feed marks one. |
| `version_policy` | `latest_lts` \| `current_stable` \| `current_major` \| `pinned` | no | Which version a project uses. The version itself is a field, never prose. |
| `checked_version` | string | no | The newest release read at the source on the `checked` day. Never typed from memory. |
| `checked` | string | no | The day `checked_version` was read at the tool's release feed, or the standard's claim at its source. It needs `source` and `evidence`. |
| `checked_by` | string | no | Who read `source` on the `checked` day: `agent:<harness>/<model>` for an agent's check, or a person's identity (`@login` or `email:<address>`, as an Approver is named) for a person's review. It sets the trust tier that `aidd standard list` and `aidd eval standards` show: an entry is checked by an agent until a person reviews it, and an entry without `checked_by` counts as an agent's check. |
| `source` | string | no | The official page where `checked_version` or the standard's claim was read on the `checked` day. Required with `checked`. |
| `evidence` | string | no | The sentence read at `source` on the `checked` day, quoted exactly, so the date is never a bare assertion. Required with `checked`. |
| `pin` | string | no | The version the `enforced_by` commands run, such as `0.16.10`. |
| `alternatives` | list of string | no | Other valid options for the same choice, by name. A company picks one through `[standards_policy] replace`. |
| `status` | `active` \| `deprecated` | yes | `deprecated`: kept so projects that copied it hear about it; `replaced_by` names the successor. |
| `replaced_by` | string | when status is `deprecated` | The library standard that replaces a deprecated one. |
| `enforced_by` | list of table | no | `[[tests]]` templates. `aidd standard add` writes each one, so the gate runs it on every change its `when_changed` matches. |
<!-- aidd:end -->

A stack is `stacks/<name>.toml`:

<!-- aidd:gen fields:stack -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | The stack's name, the file's stem, such as `python-cli`. |
| `description` | string | yes | What the stack is for, in one sentence. |
| `extends` | string | no | One other stack this one builds on, one level deep: a stack that extends a stack that extends another is refused, and so is a cycle. |
| `standards` | list of string | yes | Ids of active opinionated standards in the library, at most one per open choice and ecosystem. |
| `project` | table | no | Entries `aidd stack add` merges into the project's config. |
| `reviewed` | string | yes | The day a person last reviewed the stack. |
| `owner` | string | yes | The person or team who keeps the stack current; never an agent. |
<!-- aidd:end -->
