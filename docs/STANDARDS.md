# Standards and stacks

This page lists aidd's library of opinionated standards, its stacks, and the open choices they fill. `aidd gen-docs` writes the tables from `schemas/industry-standards.json`, `schemas/packs.json`, `standards/`, and `stacks/`, so never edit a table by hand.

## The words

- An **industry standard** is what the field agrees on, such as WCAG or SLSA. It lives only in the registry, `schemas/industry-standards.json`, never in a project's `standards`, and the packs and practice skills cite it. It applies everywhere. A project can only waive it, with a reason and an expiry.
- An **opinionated standard** is one choice that a team or a company commits to, such as Ruff for Python. It applies only where a project adopts it.
- An **open choice** is a decision that a pack or a practice skill leaves to the team. Each one has aidd's default answer. An opinionated standard fills one or more open choices, so it never restates a rule of a pack.
- A **stack** is a set of opinionated standards that go together, plus entries for `project.stack`. It holds no rule text of its own.
- The **method** is how aidd works: the routes, the approvals, the gate, Conventional Commits, and `Assisted-by:`. It is never a standard, and never an open choice.

[GLOSSARY.md](GLOSSARY.md) has each term.

## Adopt a standard or a stack

1. Run `aidd standard list` to see the open choices and the library.
2. Run `aidd standard add <id>`, or `aidd stack add <name>` for a set.
3. Review the copies and the config as one change. The change edits `.aidd/config.yaml`, a protected path, so its route is major.

Each command copies the file into `docs/standards/`. It writes a `standards` entry that records the library id, aidd's version, and the SHA-256 of the copy. It also writes the standard's `tests`, named `std.<group>.<topic>.<name>`, so the gate runs them. `aidd stack add` also merges the stack's entries into `project.stack`. Both commands add all the ids or none of them.

Never edit a copy. To change a rule, write your own standard and name it in `standards_policy.replace`. An edit under `docs/standards/` routes normal at least (`baseline:standards`), so a person approves it as a Spec. `aidd doctor` reports an edited copy, a copy that is older than the library, a deprecated or renamed id, and a policy breach. `aidd upgrade --yes` refreshes each copy that nobody edited.

The library can hold several standards for one open choice in one ecosystem. Exactly one of them is aidd's default, marked `default: true`, and `aidd eval standards` checks it. Where a choice has options, the table below and `aidd standard list` name the default.

A project keeps one standard for each open choice in each ecosystem. A polyglot project can fill `ci-pipeline:linter` once for Python and once for TypeScript. `aidd standard add` refuses a second standard for one choice, and `aidd doctor` warns about one written by hand. A stack picks one standard for each choice, whatever folder each one lives in.

## How the library selects a standard

- A choice can offer a modern or edge-first standard and a battle-tested one, when teams genuinely differ.
- Exactly one option is aidd's default. The default follows the direction of the library's owner: edge-first, Biome, and the other current defaults.
- Hosting cost decides where a workload runs. It does not decide which tool is the default.
- Each standard states its license plainly. A license alone is never a reason to drop a mainstream tool.
- Standards are opt-in. A project adopts each one, and an agent loads it only when a change touches its `when_changed` paths.
- A stack picks one standard for each choice.
- A company's org preset can require a standard, exclude it, or replace it with its own, as the next section shows.

## A company's policy

A company writes `standards_policy` in its org preset:

```yaml
standards_policy:
  require: [python/uv-tooling]  # every project carries it; `aidd doctor` fails until it does
  exclude: [python/mypy-typing]  # no project adds it
  replace: {"python/ruff-lint-format": lint}  # the company's own `standards` entry `lint` takes its place
  allow_stacks: [python-cli]  # the only stacks a project may add
```

The policy takes opinionated library ids only. aidd refuses an industry id there: an industry standard is only waived per project, with a reason and an expiry. A project config adds to the policy and tightens it. It cannot drop an entry of the company, require what the company excludes, or allow another stack. [CONFIG.md](CONFIG.md#standards-policy) has the fields.

## Open choices

<!-- aidd:gen standards:open-choices -->
| Choice | Question | aidd's default | Library standards |
| --- | --- | --- | --- |
| `web-front-end:web-framework` | Which framework renders the web front end? | The framework the app already uses. For a new app, one that renders on the server and meets the browser support target. | `typescript/angular`, `typescript/astro`, `typescript/nextjs-app-router` (default), `typescript/nuxt`, `typescript/sveltekit`, `typescript/tanstack-router`, `typescript/tanstack-start` |
| `web-front-end:styling` | Which tool turns the design tokens into the styles of the components? | Tailwind CSS, with a theme generated from the design tokens and the default palette removed, so a class can name only a token. | `typescript/tailwind-css` |
| `web-front-end:component-library` | Which library gives the front end its accessible components? | The components `DESIGN.md` lists. Else, on a React stack, shadcn/ui items kept as source on Base UI or Radix primitives; on another stack, its accessible headless library. | `typescript/shadcn-ui` |
| `web-front-end:data-fetching` | Which library holds the server data a client screen reads? | TanStack Query, one query cache per app with a staleness set for each query. A page the server renders reads its first data on the server. | `typescript/tanstack-query` |
| `web-front-end:e2e-test` | Which runner drives a real browser for end-to-end tests? | Playwright (`@playwright/test`), which the browser checks of `aidd-team:accessible-ui` and `aidd-team:product-defaults` also run. | `typescript/playwright-e2e` |
| `web-front-end:component-test` | Which library tests a component the way a person uses it? | Testing Library for the web framework in use, run by the project's test runner. | `typescript/testing-library` |
| `apis-and-services:api-framework` | Which framework serves the API? | The framework the service already uses. For a new service, the ecosystem's common framework that serves the OpenAPI contract. | `dotnet/minimal-apis`, `go/net-http`, `java/spring-boot`, `python/django`, `python/fastapi-api` (default), `rust/axum`, `typescript/fastify-api`, `typescript/hono-api` (default) |
| `apis-and-services:validation-library` | Which library validates input against the contract at the boundary? | A schema library that the contract and the types come from, so one definition checks the input and documents it. | `python/pydantic-validation`, `typescript/zod-validation` |
| `apis-and-services:api-test` | Which runner sends the API test requests to the running service and checks each response? | Hurl: plain-text request files in the repository, run by a command whose exit code fails the run. Bruno where the team wants a desktop app, with its collections kept as files in the repository too. | `tooling/bruno`, `tooling/hurl` (default) |
| `apis-and-services:load-test` | Which runner drives the load test, with the SLO as its pass or fail thresholds? | k6, with the SLO as thresholds in the script, so a missed threshold fails the run. Locust for a team that writes Python, and Gatling for a JVM team. | `tooling/gatling`, `tooling/k6` (default), `tooling/locust` |
| `mobile-apps:mobile-framework` | Which framework builds the iOS and Android apps? | The framework the app already uses. For a new cross-platform app, Expo (React Native) when the team writes TypeScript, and Flutter when it writes Dart. | `dart/flutter`, `typescript/expo` |
| `mobile-apps:mobile-ui-test` | Which runner drives the app's UI tests on a device or an emulator? | Maestro for an Expo app, `integration_test` for a Flutter app, XCUITest and Espresso for a native app, and Detox for React Native without Expo. | `dart/integration-test`, `typescript/maestro` |
| `desktop-apps:desktop-framework` | Which framework builds the desktop app for macOS and Windows? | The framework the app already uses. For a new app, Electron, which ships the Chromium the web front end is tested on. Tauri where a small installer and a Rust core matter more. | `desktop/electron` (default), `desktop/tauri` |
| `ai-features:llm-gateway` | Does a gateway sit between the code and the model providers? | No gateway for one provider: one module calls its SDK and sets max_tokens, a timeout, and bounded retries. Add a gateway when the product needs two providers, a fallback, or shared spend caps. | `ai/litellm-gateway`, `cloudflare/ai-gateway` |
| `ai-features:llm-budget-mechanism` | Where are the caps on model spending enforced? | In the one module that calls the model, through the provider's SDK, with the provider's own spend limit behind it. A gateway's budgets per key take over once the project runs a gateway. | `cost/llm-spend-caps` |
| `ai-features:vector-store` | Where are the embeddings stored and searched? | pgvector in the PostgreSQL database the application already runs, until the corpus or the query load needs a dedicated vector database. | `postgres/pgvector` |
| `ai-agents-and-tools:agent-framework` | Which framework runs the agent loop? | The framework the project already uses. Otherwise the model provider's own SDK, with the loop, its step cap, and its tools in the team's code. | `dotnet/agent-framework`, `python/langgraph-agents` (default), `python/pydantic-ai-agents`, `typescript/ai-sdk` |
| `ai-agents-and-tools:mcp-server-framework` | Which library builds an MCP server? | The official MCP SDK for the server's language, because it follows each new version of the protocol first. FastMCP, a Python framework on top of the protocol, where the team wants its shorter server code. | `python/fastmcp-server`, `typescript/mcp-sdk` |
| `ai-agents-and-tools:trace-backend` | Where do the agent's traces go? | The tracing backend the team already runs, fed over OTLP with the OpenTelemetry GenAI conventions. | `ai/langfuse-traces` |
| `cloud-and-infrastructure:hosting-target` | Which provider and platform host the application? | The provider the project already uses. For a new project, the lowest-cost provider for the placement that `references/cost-and-performance.md` picks. | `cloudflare/static-assets`, `cost/low-cost-placement` |
| `cloud-and-infrastructure:serverless-compute` | Which product runs the functions or containers that scale to zero? | The host's own: its functions for spiky, short requests, and its container service for steady or long ones, each with a concurrency or instance cap. | `aws/ecs-fargate-arm64`, `aws/lambda-arm64` (default), `azure/container-apps`, `cloudflare/workers-compute`, `gcp/cloud-run` |
| `cloud-and-infrastructure:object-storage` | Which store holds files and objects? | The host's object store, private by default, with a lifecycle rule that expires what nobody keeps. | `aws/s3-lifecycle`, `cloudflare/r2-storage`, `gcp/registry-cleanup` |
| `cloud-and-infrastructure:database` | Which database holds the application's data? | A managed PostgreSQL with pooled connections, unless the access pattern needs a key-value or an edge store. | `aws/dynamodb-on-demand` (default), `aws/rds-postgres`, `cloudflare/d1-or-hyperdrive`, `postgres/managed-postgres` |
| `cloud-and-infrastructure:queue` | Which queue carries background work and events? | The host's managed queue, with a retry limit and a dead-letter queue on every consumer. | `cloudflare/queues-workflows` |
| `cloud-and-infrastructure:iac-tool` | Which tool defines the infrastructure as code? | OpenTofu. Wrangler alone for a project that runs only on Cloudflare. | `cloudflare/wrangler`, `iac/opentofu` (default), `iac/terraform` |
| `cloud-and-infrastructure:cost-estimate-tool` | Which tool estimates the monthly cost of a plan? | Infracost, whose CLI sends resource parameters to Infracost's pricing API or to a self-hosted endpoint. Without it, the provider's pricing calculator. | `cost/pr-cost-delta-threshold` |
| `cloud-and-infrastructure:policy-tool` | Which tool runs the policies over the plan? | Conftest with OPA policies, as the Policy as code and Tag and budget policy rows run it. | `cost/policy-caps`, `k8s/pod-security-kyverno` |
| `cloud-and-infrastructure:budget-alerts` | When does a budget alert fire? | At 50, 80, and 100 percent of each environment's budget, and on the forecast passing it. | `aws/budgets-anomaly`, `azure/budgets`, `cloudflare/budget-alerts`, `cost/alert-thresholds`, `gcp/budgets` |
| `cloud-and-infrastructure:spend-caps` | What stops the spending, beyond an alert? | A hard cap where the provider supports one; otherwise an automated action on a budget alert (AWS Budgets actions; on Google Cloud, a budget notification that runs the team's own shutdown code) or per-service limits (Cloudflare Workers CPU time and subrequest limits). | `aws/hard-caps`, `azure/budgets`, `cloudflare/workers-limits`, `cost/spend-caps`, `gcp/hard-caps`, `k8s/requests-limits` |
| `cloud-and-infrastructure:egress-and-nat` | How does private compute reach the internet? | No NAT gateway unless the change's design names it; private endpoints or public egress from the managed service first. | `aws/no-default-nat` |
| `cloud-and-infrastructure:compute-architecture` | Which processor architecture do functions and containers run on? | arm64 first where the provider and every dependency support it, and x86-64 otherwise. | `cost/arm64-first` |
| `embedded-automotive-industrial:rtos` | Which RTOS or SDK runs the firmware on the microcontroller? | Zephyr, at its latest stable release or its LTS release, for a new product. FreeRTOS or the chip vendor's SDK where the chip or the code base already needs it. | `embedded/embassy-rust`, `embedded/esp-idf`, `embedded/freertos`, `embedded/zephyr` (default) |
| `embedded-automotive-industrial:misra-checker` | Which checker reports the MISRA C rule violations? | Cppcheck's open-source MISRA addon for the MISRA C:2012 rules it covers. A qualified checker where the safety case needs the edition the pack names in full. | `embedded/misra-cppcheck` |
| `embedded-automotive-industrial:emulation` | Where does the firmware run in CI when no board is attached? | Renode, with a model of the board the product uses. QEMU where only QEMU models the chip, and the RTOS's host build for logic that needs no peripheral. | `embedded/renode-emulation` |
| `embedded-automotive-industrial:firmware-update` | Which bootloader checks the signature and version of a new firmware image? | MCUboot, with signed images, downgrade prevention, and a test swap that reverts after a failed boot. The chip vendor's secure boot where MCUboot has no port for the chip. | `embedded/mcuboot-signed-updates` |
| `embedded-automotive-industrial:mcu-gui` | Which library draws the user interface on a microcontroller's display? | LVGL, with each screen tested on the host against a reference image. | `embedded/lvgl` |
| `internationalization:i18n-library` | Which library formats the messages, plurals, dates, and numbers of the user interface? | The framework's own i18n support. Else ICU MessageFormat through FormatJS on JavaScript, gettext with Babel on Python, and ICU4J on the JVM. | — |
| `internationalization:translation-management` | Where do translators work on the message catalogs? | The catalogs in the repository, exchanged as XLIFF, until the volume of strings or translators needs a translation management system. | — |
| `multi-tenant-saas:tenant-isolation` | How is each tenant's data kept apart in the database? | Shared tables with a tenant id on every row, scoped in the data-access layer, and PostgreSQL row-level security as the second layer. A schema or a database for each tenant only where a contract or a regulator requires it. | `postgres/row-level-security` |
| `enterprise-controls:image-scanner` | Which scanner finds vulnerabilities in a shipped container image? | Trivy, pinned, failing the build on a high or critical vulnerability, with its vulnerability database pinned too. | `iac/trivy` |
| `package-publishing:api-diff-tool` | Which tool compares the public API of a release with the last published one? | The ecosystem's own API diff tool, run in CI before each publish, as the Public API diff test lists for Rust, TypeScript, and Java. | `rust/cargo-semver-checks` |
| `ai-evals:eval-runner` | Which runner runs the eval suite on each change? | DeepEval in a Python project and promptfoo in a TypeScript one, pinned, with telemetry off. Inspect where the agent's path is scored, not only its answer. | `ai/inspect-evals`, `python/deepeval-evals`, `typescript/promptfoo-evals` |
| `api-design:cli-framework` | Which library parses the arguments of a command-line tool and writes its help? | The language's own parser for a tool with a few flags, and the ecosystem's common framework once it has subcommands, so one definition gives the parsing, the help, and the shell completions. | `rust/clap` |
| `ci-pipeline:formatter` | Which formatter sets the layout of the code? | The ecosystem's common formatter, pinned, run in CI and in a pre-commit hook (`dev_basics`). | `cpp/clang-format`, `dart/dart-format`, `dotnet/dotnet-format`, `go/golangci-lint`, `java/spotless-format`, `python/ruff-lint-format`, `rust/rustfmt`, `typescript/biome-lint-format` (default), `typescript/eslint-prettier` |
| `ci-pipeline:linter` | Which linter checks the code? | The ecosystem's common linter, pinned, run in CI and in a pre-commit hook (`dev_basics`). | `cpp/clang-tidy`, `dart/flutter-analyze`, `dotnet/analyzers-nullable`, `go/golangci-lint`, `java/error-prone`, `python/ruff-lint-format`, `rust/clippy`, `typescript/biome-lint-format` (default), `typescript/eslint-prettier`, `typescript/oxlint` |
| `ci-pipeline:type-checker` | Which type checker runs in CI? | The language's own strict type check, run in CI (`dev_basics`). | `dotnet/analyzers-nullable`, `python/mypy-typing`, `typescript/tsc-strict` |
| `ci-pipeline:package-manager` | Which tool installs and locks the dependencies? | The ecosystem's standard package manager, with the lockfile committed. | `cpp/vcpkg`, `dotnet/central-package-management`, `go/go-modules`, `java/gradle-kotlin-dsl` (default), `java/maven`, `python/uv-tooling`, `rust/cargo-lockfile`, `typescript/pnpm-tooling` |
| `ci-pipeline:test-runner` | Which test runner runs the unit and integration tests? | The ecosystem's common test runner, pinned, run in CI on every change. | `cpp/googletest` (default), `cpp/unity-ceedling`, `dart/flutter-test`, `dotnet/xunit-v3`, `go/go-test-race`, `java/junit`, `python/pytest-tests`, `rust/cargo-nextest`, `typescript/jest-expo`, `typescript/vitest-tests` (default) |
| `ci-pipeline:dependency-audit` | Which audit of the locked dependencies runs next to OSV-Scanner? | None beyond OSV-Scanner, which the Dependency scan of `aidd-team:enterprise-controls` pins and runs over every lockfile. A standard that fills this choice adds the ecosystem's own audit. | `go/govulncheck`, `rust/cargo-deny` |
| `ci-pipeline:language-version` | Which language and runtime version does the project target, and where is it pinned? | The newest release with long-term support (or the current stable release where there is no LTS), pinned in one file that CI and every developer read. | `cpp/language-standard`, `dart/sdk-constraint`, `dotnet/dotnet-lts`, `go/go-version`, `java/java-lts`, `python/python-version`, `rust/msrv`, `typescript/node-lts` |
| `ci-pipeline:workspace` | Which workspace tool holds the apps, modules, and packages in one repository? | The package manager's own workspaces: one package per module, one lockfile, and one version of each dependency. Add a task runner only when builds need a cache. | `cpp/cmake-presets`, `dotnet/slnx-central-packages`, `go/single-module`, `java/gradle-multi-project` (default), `java/maven-multi-module`, `python/pants`, `python/uv-workspace` (default), `rust/cargo-workspace`, `typescript/nx-workspace`, `typescript/pnpm-turborepo-workspace` (default) |
| `ci-pipeline:manifest-validation` | What checks the rendered Kubernetes manifests against the API schemas? | kubeconform in strict mode, against the Kubernetes version the cluster runs, on the manifests the deploy-packaging tool renders. | `k8s/kubeconform` |
| `ci-pipeline:toolchain-manager` | Which tool installs the pinned runtimes and command-line tools on each machine and in CI? | mise, with exact versions in `mise.toml` and a `mise.lock` that records each download's checksum. A repository with one language may keep that language's own version file. | `tooling/mise` |
| `modular-monolith:module-boundaries` | Which check enforces the module dependency rules in CI? | The language's own visibility first, then an import-rule check over the whole repository on every change, with a violations baseline that never grows. | `cloudflare/d1-table-prefixes`, `dotnet/archunitnet`, `go/depguard-boundaries` (default), `go/go-arch-lint`, `java/archunit`, `java/spring-modulith` (default), `postgres/cross-schema-foreign-keys`, `python/import-linter` (default), `python/tach`, `rust/cargo-modules`, `rust/cargo-workspace-boundaries` (default), `typescript/dependency-cruiser` (default), `typescript/nx-module-boundaries` |
| `observability:logging-library` | Which library writes the structured logs? | The language's standard structured logger, such as slog for Go, writing one JSON line per event. | `go/slog`, `python/structlog`, `typescript/pino-logging` |
| `observability:log-retention` | How long does each log group keep its logs? | 30 days in production, unless a regulation sets another period. | `aws/log-retention`, `azure/log-retention`, `gcp/log-retention` |
| `performance:benchmark-tool` | Which tool runs the benchmarks and compares the head with its baseline? | The ecosystem's own benchmark harness, run on the base and the head on one machine, with a statistical comparison where the tool has one, such as benchstat or Criterion's change detection. | `dotnet/benchmarkdotnet`, `go/benchstat`, `java/jmh`, `python/pytest-benchmark`, `rust/criterion`, `tooling/hyperfine`, `typescript/vitest-bench` |
| `release-rollout:preview-environment-ttl` | When is a preview environment deleted? | Deleted when its pull request closes, and after a set number of days at most, so no preview keeps running unwatched. | `cost/preview-env-ttl` |
| `release-rollout:cost-kill-switch` | How does the team cut a path whose cost runs out of control? | A tested runbook that scales the service to zero or turns off the expensive path, rehearsed like a rollback. | `cost/kill-switch` |
| `release-rollout:deploy-packaging` | When a service runs on Kubernetes, how are its manifests packaged for each environment? | A Helm chart for each service, with one values file for each environment. Kustomize overlays for a team that keeps plain manifests. | `k8s/helm-charts` (default), `k8s/kustomize` |
| `resilience:durable-execution` | What runs a job whose steps must each finish once, over minutes or days? | An outbox and a sweep, or the durable-execution engine the host already runs, such as Cloudflare Workflows or AWS Step Functions. A dedicated engine where a run waits for a person or chains steps with side effects. | `python/temporal-workflows`, `typescript/temporal-workflows` |
| `schema-migration:orm` | Which library maps the code to the database? | The data-access library the project already uses. For a new project, the ecosystem's common one that checks its models against the schema. | `dotnet/ef-core`, `go/gorm`, `go/sqlc` (default), `java/spring-data-jpa`, `python/django`, `python/sqlalchemy-orm` (default), `rust/sqlx`, `typescript/drizzle-orm` (default), `typescript/prisma-orm` |
| `schema-migration:migration-tool` | Which tool writes and applies the migrations? | The migration tool of the data-access library, with versioned scripts, checksums, and a down path. | `cloudflare/d1-migrations`, `dotnet/ef-core-migrations`, `go/atlas-migrations`, `java/flyway-migrations`, `python/alembic-migrations` (default), `python/django`, `typescript/atlas-migrations` |
| `test-design:integration-test-services` | How does an integration test start the databases and services it needs? | Testcontainers where the ecosystem has a library for it, one throwaway container per test run. | `dotnet/testcontainers`, `go/testcontainers`, `java/testcontainers`, `python/testcontainers`, `typescript/testcontainers` |
| `test-design:coverage-tool` | Which tool measures the coverage of the tests in CI, and which floor fails the run? | The test runner's own coverage report in CI, with a line floor the team sets and only raises. Coverage shows the code no test ran; the Mutation run judges how strong the tests are. | `cpp/coverage`, `rust/coverage` |
| `test-design:fuzzer` | Which fuzzer runs the Parser fuzzing of `aidd-team:secure-coding`, and how does CI keep what it finds? | libFuzzer through the language's own harness, fuzzing each parser for a set time on a schedule, with every crash input kept and replayed as a regression test. | `rust/fuzzing` |
| `test-design:undefined-behavior-check` | Which check finds undefined behaviour in unsafe code, or in code in a memory-unsafe language? | The compiler's sanitizers, AddressSanitizer and UndefinedBehaviorSanitizer, over the test suite in CI, wherever the code can break memory safety. | `cpp/sanitizers`, `rust/miri` |
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
| cargo-semver-checks, API Extractor, japicmp | `package-publishing`, Public API diff | Open: `package-publishing:api-diff-tool` | The check gives a command for each ecosystem, so it decides none. `rust/cargo-semver-checks` holds the Rust pin. |
| libFuzzer, AFL++, Jazzer | `secure-coding`, Parser fuzzing | Open: `test-design:fuzzer` | The row runs the choice, so it names no fuzzer. The choice lives in `test-design`, beside the property-based testing and fuzzing entry it cites. |
| squawk | `schema-migration`, Migration lint | Keep | It is a lint for safe DDL on Postgres, not a migration tool. |
| Store minimum SDK and target levels | `mobile-apps` | Keep | The stores set them on a calendar. `ci-pipeline:language-version` is the version of the language. |
| XCUITest, Espresso, Detox | `mobile-apps`, UI tests | Open: `mobile-apps:mobile-ui-test` | The row runs the team's runner. Maestro is the default for Expo, and `integration_test` for Flutter. |
| XCUITest, Espresso | `accessible-ui`, Mobile accessibility checks; `prototyping` | Keep | The accessibility audits run in them. An Expo app on Maestro still needs both for the audit. |
| Testcontainers | `test-design`, its real-dependencies reference | Open: `test-design:integration-test-services` | The reference teaches the practice, and Testcontainers is the default where the ecosystem has it. |
| promptfoo, Inspect | `ai-evals`, Eval suite | Open: `ai-evals:eval-runner` | DeepEval is the Python default and promptfoo the TypeScript one, each pinned in its standard. Inspect keeps its pin in the row, for scoring an agent's path. |
| k6 | `apis-and-services`, Load test; `performance`, Regression guard; `multi-tenant-saas`, Per-tenant quota enforced | Open: `apis-and-services:load-test` | k6 is the default, and `tooling/k6` holds its pin. Locust and Gatling are the other answers. |
| pytest-benchmark, JMH, Go `testing.B`, Criterion | `performance`, Regression guard | Open: `performance:benchmark-tool` | The row named four harnesses, so it decided none. A standard for each ecosystem fills the choice, and hyperfine fills it for a whole program. |

`schema-migration` holds `orm` and `migration-tool`, because `data-and-analytics` gives the migration plan to it.

The cost guards rest on industry rows that the registry already has. OWASP API Security Top 10, API4:2023 (Unrestricted Resource Consumption), covers rate limits, quotas, timeouts, and spending limits. OWASP Top 10 for LLM Applications 2026, LLM06 (Unbounded Consumption), covers token limits and hard spending caps. The Builders' Library and Google SRE rows cover timeouts, bounded retries, and retry budgets. The cloud pack already requires a concurrency or instance cap on every function and autoscaler.

A requirement is a pack rule that cites the registry. Only the way to meet it is an open choice. So `ai-features` requires caps in layers on model spending (LLM06), and `ai-features:llm-budget-mechanism` asks where they are enforced. `observability` requires a set retention on each log group, and `observability:log-retention` sets the period.

The other cost guards are open choices in the closest pack or skill. `cloud-and-infrastructure` holds `budget-alerts`, `spend-caps`, `egress-and-nat`, and `compute-architecture`. `release-rollout` holds `preview-environment-ttl` and `cost-kill-switch`.

## The library, by ecosystem

<!-- aidd:gen standards:library -->
### ai

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `ai/inspect-evals` | `ai-evals:eval-runner` | inspect-ai | 0.3.283 | 2026-10-24 | 2026-10-22 | active |
| `ai/langfuse-traces` | `ai-agents-and-tools:trace-backend` | langfuse | 5.0.4 | 2026-10-24 | 2026-10-22 | active |
| `ai/litellm-gateway` | `ai-features:llm-gateway` | litellm | 1.105.1 | 2026-10-22 | 2026-10-22 | active |

### aws

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `aws/budgets-anomaly` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/dynamodb-on-demand` | `cloud-and-infrastructure:database` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/ecs-fargate-arm64` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-22 | 2026-10-22 | active |
| `aws/hard-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/lambda-arm64` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/log-retention` | `observability:log-retention` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/no-default-nat` | `cloud-and-infrastructure:egress-and-nat` | — | — | 2026-10-16 | 2026-10-16 | active |
| `aws/rds-postgres` | `cloud-and-infrastructure:database` | — | — | 2026-10-22 | 2026-10-22 | active |
| `aws/s3-lifecycle` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-16 | 2026-10-16 | active |

### azure

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `azure/budgets` | `cloud-and-infrastructure:budget-alerts`, `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-22 | 2026-10-22 | active |
| `azure/container-apps` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-22 | 2026-10-22 | active |
| `azure/log-retention` | `observability:log-retention` | — | — | 2026-10-22 | 2026-10-22 | active |

### cloudflare

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `cloudflare/ai-gateway` | `ai-features:llm-gateway` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/budget-alerts` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/d1-migrations` | `schema-migration:migration-tool` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/d1-or-hyperdrive` | `cloud-and-infrastructure:database` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/d1-table-prefixes` | `modular-monolith:module-boundaries` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/queues-workflows` | `cloud-and-infrastructure:queue` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/r2-storage` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/static-assets` | `cloud-and-infrastructure:hosting-target` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/workers-compute` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/workers-limits` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cloudflare/wrangler` | `cloud-and-infrastructure:iac-tool` | — | — | 2026-10-16 | 2026-10-16 | active |

### cost

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `cost/alert-thresholds` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/arm64-first` | `cloud-and-infrastructure:compute-architecture` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/kill-switch` | `release-rollout:cost-kill-switch` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/llm-spend-caps` | `ai-features:llm-budget-mechanism` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/low-cost-placement` | `cloud-and-infrastructure:hosting-target` | — | — | 2026-10-16 | 2026-10-22 | active |
| `cost/policy-caps` | `cloud-and-infrastructure:policy-tool` | — | — | 2026-10-16 | 2026-10-22 | active |
| `cost/pr-cost-delta-threshold` | `cloud-and-infrastructure:cost-estimate-tool` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/preview-env-ttl` | `release-rollout:preview-environment-ttl` | — | — | 2026-10-16 | 2026-10-16 | active |
| `cost/spend-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-16 | 2026-10-16 | active |

### cpp

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `cpp/clang-format` | `ci-pipeline:formatter` | clang-format | 23.1.3 | 2026-10-22 | 2026-10-22 | active |
| `cpp/clang-tidy` | `ci-pipeline:linter` | clang-tidy | 23.1.3 | 2026-10-22 | 2026-10-22 | active |
| `cpp/cmake-presets` | `ci-pipeline:workspace` | cmake | 4.4.4 | 2026-10-22 | 2026-10-22 | active |
| `cpp/coverage` | `test-design:coverage-tool` | gcovr | 8.7 | 2026-10-24 | 2026-10-22 | active |
| `cpp/googletest` | `ci-pipeline:test-runner` | googletest | 1.18.0 | 2026-10-22 | 2026-10-22 | active |
| `cpp/language-standard` | `ci-pipeline:language-version` | — | — | 2026-10-22 | 2026-10-22 | active |
| `cpp/sanitizers` | `test-design:undefined-behavior-check` | — | — | 2026-10-22 | 2026-10-22 | active |
| `cpp/unity-ceedling` | `ci-pipeline:test-runner` | ceedling | 1.2.0 | 2026-10-22 | 2026-10-22 | active |
| `cpp/vcpkg` | `ci-pipeline:package-manager` | vcpkg | 2026.10.16 | 2026-10-22 | 2026-10-22 | active |

### dart

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `dart/dart-format` | `ci-pipeline:formatter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dart/flutter` | `mobile-apps:mobile-framework` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dart/flutter-analyze` | `ci-pipeline:linter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dart/flutter-test` | `ci-pipeline:test-runner` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dart/integration-test` | `mobile-apps:mobile-ui-test` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dart/sdk-constraint` | `ci-pipeline:language-version` | — | — | 2026-10-16 | 2026-10-16 | active |

### desktop

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `desktop/electron` | `desktop-apps:desktop-framework` | electron | 45.0.0 | 2026-10-22 | 2026-10-22 | active |
| `desktop/tauri` | `desktop-apps:desktop-framework` | tauri | 2.12.4 | 2026-10-24 | 2026-10-22 | active |

### dotnet

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `dotnet/agent-framework` | `ai-agents-and-tools:agent-framework` | microsoft-agents-ai | 1.25.0 | 2026-10-22 | 2026-10-22 | active |
| `dotnet/analyzers-nullable` | `ci-pipeline:type-checker`, `ci-pipeline:linter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dotnet/archunitnet` | `modular-monolith:module-boundaries` | archunitnet | 0.13.4 | 2026-10-16 | 2026-10-16 | active |
| `dotnet/benchmarkdotnet` | `performance:benchmark-tool` | benchmarkdotnet | 0.15.8 | 2026-10-22 | 2026-10-22 | active |
| `dotnet/central-package-management` | `ci-pipeline:package-manager` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dotnet/dotnet-format` | `ci-pipeline:formatter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dotnet/dotnet-lts` | `ci-pipeline:language-version` | dotnet | 10.0.402 | 2026-10-16 | 2026-10-16 | active |
| `dotnet/ef-core` | `schema-migration:orm` | entity-framework-core | 10.0.13 | 2026-10-22 | 2026-10-16 | active |
| `dotnet/ef-core-migrations` | `schema-migration:migration-tool` | dotnet-ef | 10.0.13 | 2026-10-22 | 2026-10-16 | active |
| `dotnet/minimal-apis` | `apis-and-services:api-framework` | aspnetcore-openapi | 10.0.13 | 2026-10-22 | 2026-10-16 | active |
| `dotnet/slnx-central-packages` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |
| `dotnet/testcontainers` | `test-design:integration-test-services` | testcontainers-dotnet | 4.15.0 | 2026-10-16 | 2026-10-16 | active |
| `dotnet/xunit-v3` | `ci-pipeline:test-runner` | xunit | 4.0.2 | 2026-10-22 | 2026-10-16 | active |

### embedded

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `embedded/embassy-rust` | `embedded-automotive-industrial:rtos` | embassy-executor | 0.10.0 | 2026-10-22 | 2026-10-22 | active |
| `embedded/esp-idf` | `embedded-automotive-industrial:rtos` | esp-idf | 6.1 | 2026-10-22 | 2026-10-22 | active |
| `embedded/freertos` | `embedded-automotive-industrial:rtos` | freertos-kernel | 11.3.2 | 2026-10-22 | 2026-10-22 | active |
| `embedded/lvgl` | `embedded-automotive-industrial:mcu-gui` | lvgl | 9.6.0 | 2026-10-22 | 2026-10-22 | active |
| `embedded/mcuboot-signed-updates` | `embedded-automotive-industrial:firmware-update` | mcuboot | 2.4.0 | 2026-10-22 | 2026-10-22 | active |
| `embedded/misra-cppcheck` | `embedded-automotive-industrial:misra-checker` | — | — | 2026-10-22 | 2026-10-22 | active |
| `embedded/renode-emulation` | `embedded-automotive-industrial:emulation` | renode | 1.17.0 | 2026-10-22 | 2026-10-22 | active |
| `embedded/zephyr` | `embedded-automotive-industrial:rtos` | zephyr | 4.4.2 | 2026-10-22 | 2026-10-22 | active |

### gcp

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `gcp/budgets` | `cloud-and-infrastructure:budget-alerts` | — | — | 2026-10-16 | 2026-10-16 | active |
| `gcp/cloud-run` | `cloud-and-infrastructure:serverless-compute` | — | — | 2026-10-16 | 2026-10-16 | active |
| `gcp/hard-caps` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-16 | 2026-10-16 | active |
| `gcp/log-retention` | `observability:log-retention` | — | — | 2026-10-16 | 2026-10-16 | active |
| `gcp/registry-cleanup` | `cloud-and-infrastructure:object-storage` | — | — | 2026-10-16 | 2026-10-16 | active |

### go

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `go/atlas-migrations` | `schema-migration:migration-tool` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/benchstat` | `performance:benchmark-tool` | — | — | 2026-10-22 | 2026-10-22 | active |
| `go/depguard-boundaries` | `modular-monolith:module-boundaries` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/go-arch-lint` | `modular-monolith:module-boundaries` | go-arch-lint | v1.19.0 | 2026-10-16 | 2026-10-16 | active |
| `go/go-modules` | `ci-pipeline:package-manager` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/go-test-race` | `ci-pipeline:test-runner` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/go-version` | `ci-pipeline:language-version` | go | 1.27.3 | 2026-10-22 | 2026-10-16 | active |
| `go/golangci-lint` | `ci-pipeline:linter`, `ci-pipeline:formatter` | golangci-lint | v2.15.0 | 2026-10-20 | 2026-10-16 | active |
| `go/gorm` | `schema-migration:orm` | gorm | v1.31.2 | 2026-10-16 | 2026-10-16 | active |
| `go/govulncheck` | `ci-pipeline:dependency-audit` | govulncheck | v1.8.0 | 2026-10-16 | 2026-10-16 | active |
| `go/net-http` | `apis-and-services:api-framework` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/single-module` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/slog` | `observability:logging-library` | — | — | 2026-10-16 | 2026-10-16 | active |
| `go/sqlc` | `schema-migration:orm` | sqlc | v1.31.1 | 2026-10-16 | 2026-10-16 | active |
| `go/testcontainers` | `test-design:integration-test-services` | testcontainers-go | v0.44.0 | 2026-10-16 | 2026-10-16 | active |

### iac

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `iac/opentofu` | `cloud-and-infrastructure:iac-tool` | opentofu | 1.13.2 | 2026-10-22 | 2026-10-16 | active |
| `iac/terraform` | `cloud-and-infrastructure:iac-tool` | terraform | 1.17.0 | 2026-10-22 | 2026-10-16 | active |
| `iac/trivy` | `enterprise-controls:image-scanner` | trivy | 0.76.1 | 2026-10-22 | 2026-10-22 | active |

### java

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `java/archunit` | `modular-monolith:module-boundaries` | archunit | 1.5.1 | 2026-10-16 | 2026-10-16 | active |
| `java/error-prone` | `ci-pipeline:linter` | error-prone | 2.50.0 | 2026-10-16 | 2026-10-16 | active |
| `java/flyway-migrations` | `schema-migration:migration-tool` | flyway | 13.9.0 | 2026-10-16 | 2026-10-16 | active |
| `java/gradle-kotlin-dsl` | `ci-pipeline:package-manager` | gradle | 9.8.2 | 2026-10-22 | 2026-10-16 | active |
| `java/gradle-multi-project` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |
| `java/java-lts` | `ci-pipeline:language-version` | java | 25 | 2026-10-16 | 2026-10-16 | active |
| `java/jmh` | `performance:benchmark-tool` | jmh | 1.37 | 2026-10-22 | 2026-10-22 | active |
| `java/junit` | `ci-pipeline:test-runner` | junit | 6.1.3 | 2026-10-16 | 2026-10-16 | active |
| `java/maven` | `ci-pipeline:package-manager` | maven | 3.10.0 | 2026-10-16 | 2026-10-16 | active |
| `java/maven-multi-module` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |
| `java/spotless-format` | `ci-pipeline:formatter` | spotless | 8.10.4 | 2026-10-16 | 2026-10-16 | active |
| `java/spring-boot` | `apis-and-services:api-framework` | spring-boot | 4.1.1 | 2026-10-16 | 2026-10-16 | active |
| `java/spring-data-jpa` | `schema-migration:orm` | spring-data-jpa | 4.1.1 | 2026-10-16 | 2026-10-16 | active |
| `java/spring-modulith` | `modular-monolith:module-boundaries` | spring-modulith | 2.1.1 | 2026-10-16 | 2026-10-16 | active |
| `java/testcontainers` | `test-design:integration-test-services` | testcontainers | 2.0.5 | 2026-10-16 | 2026-10-16 | active |

### k8s

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `k8s/helm-charts` | `release-rollout:deploy-packaging` | helm | 4.3.1 | 2026-10-22 | 2026-10-22 | active |
| `k8s/kubeconform` | `ci-pipeline:manifest-validation` | kubeconform | 0.8.0 | 2026-10-22 | 2026-10-22 | active |
| `k8s/kustomize` | `release-rollout:deploy-packaging` | kustomize | 5.8.3 | 2026-10-22 | 2026-10-22 | active |
| `k8s/pod-security-kyverno` | `cloud-and-infrastructure:policy-tool` | kyverno | 1.19.2 | 2026-10-22 | 2026-10-22 | active |
| `k8s/requests-limits` | `cloud-and-infrastructure:spend-caps` | — | — | 2026-10-22 | 2026-10-22 | active |

### postgres

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `postgres/cross-schema-foreign-keys` | `modular-monolith:module-boundaries` | — | — | 2026-10-16 | 2026-10-16 | active |
| `postgres/managed-postgres` | `cloud-and-infrastructure:database` | — | — | 2026-10-22 | 2026-10-22 | active |
| `postgres/pgvector` | `ai-features:vector-store` | — | — | 2026-10-22 | 2026-10-22 | active |
| `postgres/row-level-security` | `multi-tenant-saas:tenant-isolation` | — | — | 2026-10-22 | 2026-10-22 | active |

### python

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `python/alembic-migrations` | `schema-migration:migration-tool` | alembic | 1.20.0 | 2026-10-16 | 2026-10-16 | active |
| `python/deepeval-evals` | `ai-evals:eval-runner` | deepeval | 4.3.1 | 2026-10-22 | 2026-10-22 | active |
| `python/django` | `apis-and-services:api-framework`, `schema-migration:orm`, `schema-migration:migration-tool` | django | 6.1.2 | 2026-10-16 | 2026-10-16 | active |
| `python/fastapi-api` | `apis-and-services:api-framework` | fastapi | 0.153.0 | 2026-10-20 | 2026-10-16 | active |
| `python/fastmcp-server` | `ai-agents-and-tools:mcp-server-framework` | fastmcp | 4.1.3 | 2026-10-22 | 2026-10-16 | active |
| `python/import-linter` | `modular-monolith:module-boundaries` | import-linter | 2.15 | 2026-10-16 | 2026-10-16 | active |
| `python/langgraph-agents` | `ai-agents-and-tools:agent-framework` | langgraph | 1.2.16 | 2026-10-22 | 2026-10-16 | active |
| `python/mypy-typing` | `ci-pipeline:type-checker` | mypy | 2.4.0 | 2026-10-16 | 2026-10-22 | active |
| `python/pants` | `ci-pipeline:workspace` | pants | 2.33.1 | 2026-10-16 | 2026-10-16 | active |
| `python/pydantic-ai-agents` | `ai-agents-and-tools:agent-framework` | pydantic-ai | 2.56.0 | 2026-10-22 | 2026-10-22 | active |
| `python/pydantic-validation` | `apis-and-services:validation-library` | pydantic | 2.14.1 | 2026-10-16 | 2026-10-16 | active |
| `python/pytest-benchmark` | `performance:benchmark-tool` | pytest-benchmark | 5.3.0 | 2026-10-22 | 2026-10-22 | active |
| `python/pytest-tests` | `ci-pipeline:test-runner` | pytest | 9.1.1 | 2026-10-16 | 2026-10-16 | active |
| `python/python-version` | `ci-pipeline:language-version` | python | 3.15.1 | 2026-10-22 | 2026-10-16 | active |
| `python/ruff-lint-format` | `ci-pipeline:linter`, `ci-pipeline:formatter` | ruff | 0.17.1 | 2026-10-20 | 2026-10-16 | active |
| `python/sqlalchemy-orm` | `schema-migration:orm` | sqlalchemy | 2.1.6 | 2026-10-24 | 2026-10-16 | active |
| `python/structlog` | `observability:logging-library` | structlog | 26.1.0 | 2026-10-16 | 2026-10-16 | active |
| `python/tach` | `modular-monolith:module-boundaries` | tach | 0.35.3 | 2026-10-16 | 2026-10-16 | active |
| `python/temporal-workflows` | `resilience:durable-execution` | temporalio | 1.34.0 | 2026-10-22 | 2026-10-22 | active |
| `python/testcontainers` | `test-design:integration-test-services` | testcontainers-python | 4.15.0 | 2026-10-16 | 2026-10-16 | active |
| `python/uv-tooling` | `ci-pipeline:package-manager` | uv | 0.13.5 | 2026-10-22 | 2026-10-16 | active |
| `python/uv-workspace` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |

### rust

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `rust/axum` | `apis-and-services:api-framework` | axum | 0.8.9 | 2026-10-16 | 2026-10-16 | active |
| `rust/cargo-deny` | `ci-pipeline:dependency-audit` | cargo-deny | 0.20.2 | 2026-10-16 | 2026-10-16 | active |
| `rust/cargo-lockfile` | `ci-pipeline:package-manager` | — | — | 2026-10-16 | 2026-10-16 | active |
| `rust/cargo-modules` | `modular-monolith:module-boundaries` | cargo-modules | 0.28.0 | 2026-10-22 | 2026-10-16 | active |
| `rust/cargo-nextest` | `ci-pipeline:test-runner` | cargo-nextest | 0.9.149 | 2026-10-24 | 2026-10-16 | active |
| `rust/cargo-semver-checks` | `package-publishing:api-diff-tool` | cargo-semver-checks | 0.51.0 | 2026-10-22 | 2026-10-22 | active |
| `rust/cargo-workspace` | `ci-pipeline:workspace` | — | — | 2026-10-16 | 2026-10-16 | active |
| `rust/cargo-workspace-boundaries` | `modular-monolith:module-boundaries` | — | — | 2026-10-16 | 2026-10-16 | active |
| `rust/clap` | `api-design:cli-framework` | clap | 4.6.7 | 2026-10-22 | 2026-10-22 | active |
| `rust/clippy` | `ci-pipeline:linter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `rust/coverage` | `test-design:coverage-tool` | cargo-llvm-cov | 0.9.1 | 2026-10-22 | 2026-10-22 | active |
| `rust/criterion` | `performance:benchmark-tool` | criterion | 0.8.2 | 2026-10-22 | 2026-10-22 | active |
| `rust/fuzzing` | `test-design:fuzzer` | cargo-fuzz | 0.13.2 | 2026-10-22 | 2026-10-22 | active |
| `rust/miri` | `test-design:undefined-behavior-check` | — | — | 2026-10-22 | 2026-10-22 | active |
| `rust/msrv` | `ci-pipeline:language-version` | rust | 1.99.1 | 2026-10-22 | 2026-10-16 | active |
| `rust/rustfmt` | `ci-pipeline:formatter` | — | — | 2026-10-16 | 2026-10-16 | active |
| `rust/sqlx` | `schema-migration:orm` | sqlx | 0.9.0 | 2026-10-16 | 2026-10-16 | active |

### tooling

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `tooling/bruno` | `apis-and-services:api-test` | bruno-cli | 4.3.0 | 2026-10-22 | 2026-10-22 | active |
| `tooling/gatling` | `apis-and-services:load-test` | gatling | 3.16.0 | 2026-10-22 | 2026-10-22 | active |
| `tooling/hurl` | `apis-and-services:api-test` | hurl | 8.0.1 | 2026-10-22 | 2026-10-22 | active |
| `tooling/hyperfine` | `performance:benchmark-tool` | hyperfine | 2.0.0 | 2026-10-22 | 2026-10-22 | active |
| `tooling/k6` | `apis-and-services:load-test` | k6 | 2.3.0 | 2026-10-22 | 2026-10-22 | active |
| `tooling/locust` | `apis-and-services:load-test` | locust | 2.47.0 | 2026-10-22 | 2026-10-22 | active |
| `tooling/mise` | `ci-pipeline:toolchain-manager` | mise | 2026.10.17 | 2026-10-22 | 2026-10-22 | active |

### typescript

| Standard | Fills | Tool | Checked version | Checked | Reviewed | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `typescript/ai-sdk` | `ai-agents-and-tools:agent-framework` | ai | 7.0.152 | 2026-10-24 | 2026-10-22 | active |
| `typescript/angular` | `web-front-end:web-framework` | angular | 22.2.3 | 2026-10-22 | 2026-10-22 | active |
| `typescript/astro` | `web-front-end:web-framework` | astro | 7.4.2 | 2026-10-24 | 2026-10-22 | active |
| `typescript/atlas-migrations` | `schema-migration:migration-tool` | atlas | 1.3.4 | 2026-10-16 | 2026-10-16 | active |
| `typescript/biome-lint-format` | `ci-pipeline:linter`, `ci-pipeline:formatter` | biome | 2.5.15 | 2026-10-16 | 2026-10-16 | active |
| `typescript/dependency-cruiser` | `modular-monolith:module-boundaries` | dependency-cruiser | 18.6.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/drizzle-orm` | `schema-migration:orm` | drizzle-orm | 0.45.4 | 2026-10-16 | 2026-10-16 | active |
| `typescript/eslint-prettier` | `ci-pipeline:linter`, `ci-pipeline:formatter` | eslint | 10.13.0 | 2026-10-16 | 2026-10-22 | active |
| `typescript/expo` | `mobile-apps:mobile-framework` | expo | 58.0.19 | 2026-10-24 | 2026-10-22 | active |
| `typescript/fastify-api` | `apis-and-services:api-framework` | fastify | 5.12.7 | 2026-10-16 | 2026-10-16 | active |
| `typescript/hono-api` | `apis-and-services:api-framework` | hono | 4.13.13 | 2026-10-16 | 2026-10-16 | active |
| `typescript/jest-expo` | `ci-pipeline:test-runner` | jest-expo | 58.0.11 | 2026-10-20 | 2026-10-16 | active |
| `typescript/maestro` | `mobile-apps:mobile-ui-test` | maestro | 2.11.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/mcp-sdk` | `ai-agents-and-tools:mcp-server-framework` | mcp-typescript-sdk | 2.3.1 | 2026-10-16 | 2026-10-16 | active |
| `typescript/nextjs-app-router` | `web-front-end:web-framework` | next | 16.4.2 | 2026-10-16 | 2026-10-22 | active |
| `typescript/node-lts` | `ci-pipeline:language-version` | node | 24.22.1 | 2026-10-22 | 2026-10-22 | active |
| `typescript/nuxt` | `web-front-end:web-framework` | nuxt | 4.6.2 | 2026-10-22 | 2026-10-22 | active |
| `typescript/nx-module-boundaries` | `modular-monolith:module-boundaries` | nx-eslint-plugin | 23.3.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/nx-workspace` | `ci-pipeline:workspace` | nx | 23.3.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/oxlint` | `ci-pipeline:linter` | oxlint | 1.89.0 | 2026-10-22 | 2026-10-22 | active |
| `typescript/pino-logging` | `observability:logging-library` | pino | 10.4.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/playwright-e2e` | `web-front-end:e2e-test` | — | — | 2026-10-20 | 2026-10-16 | active |
| `typescript/pnpm-tooling` | `ci-pipeline:package-manager` | pnpm | 12.14.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/pnpm-turborepo-workspace` | `ci-pipeline:workspace` | turbo | 2.11.7 | 2026-10-16 | 2026-10-16 | active |
| `typescript/prisma-orm` | `schema-migration:orm` | prisma | 7.10.0 | 2026-10-09 | 2026-10-16 | active |
| `typescript/promptfoo-evals` | `ai-evals:eval-runner` | promptfoo | 0.124.1 | 2026-10-22 | 2026-10-22 | active |
| `typescript/shadcn-ui` | `web-front-end:component-library` | shadcn | 4.22.1 | 2026-10-22 | 2026-10-22 | active |
| `typescript/sveltekit` | `web-front-end:web-framework` | sveltekit | 3.1.0 | 2026-10-22 | 2026-10-22 | active |
| `typescript/tailwind-css` | `web-front-end:styling` | tailwindcss | 4.3.3 | 2026-10-22 | 2026-10-22 | active |
| `typescript/tanstack-query` | `web-front-end:data-fetching` | tanstack-query | 5.104.5 | 2026-10-22 | 2026-10-22 | active |
| `typescript/tanstack-router` | `web-front-end:web-framework` | tanstack-router | 1.170.46 | 2026-10-24 | 2026-10-22 | active |
| `typescript/tanstack-start` | `web-front-end:web-framework` | tanstack-start | 1.169.3 | 2026-10-22 | 2026-10-22 | active |
| `typescript/temporal-workflows` | `resilience:durable-execution` | temporal-typescript | 1.24.0 | 2026-10-22 | 2026-10-22 | active |
| `typescript/testcontainers` | `test-design:integration-test-services` | testcontainers-node | 12.2.0 | 2026-10-16 | 2026-10-16 | active |
| `typescript/testing-library` | `web-front-end:component-test` | testing-library | 16.3.3 | 2026-10-16 | 2026-10-16 | active |
| `typescript/tsc-strict` | `ci-pipeline:type-checker` | typescript | 7.0.2 | 2026-10-16 | 2026-10-16 | active |
| `typescript/vitest-bench` | `performance:benchmark-tool` | — | — | 2026-10-22 | 2026-10-22 | active |
| `typescript/vitest-tests` | `ci-pipeline:test-runner` | vitest | 5.0.5 | 2026-10-24 | 2026-10-22 | active |
| `typescript/zod-validation` | `apis-and-services:validation-library` | zod | 4.6.7 | 2026-10-16 | 2026-10-16 | active |
<!-- aidd:end -->

## Stacks

<!-- aidd:gen standards:stacks -->
| Stack | For | Extends | Standards |
| --- | --- | --- | --- |
| `aws-containers` | A container service on Amazon ECS with Fargate and PostgreSQL on Amazon RDS, for a team whose service runs steadily or holds long requests. | — | `aws/ecs-fargate-arm64`, `aws/rds-postgres`, `aws/s3-lifecycle`, `aws/log-retention`, `aws/no-default-nat`, `aws/budgets-anomaly`, `aws/hard-caps`, `iac/opentofu`, `cost/arm64-first`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `aws-serverless` | A serverless service on AWS, for a team that wants no servers to run and a bill that follows use. | — | `aws/lambda-arm64`, `aws/dynamodb-on-demand`, `aws/s3-lifecycle`, `aws/log-retention`, `aws/no-default-nat`, `aws/budgets-anomaly`, `aws/hard-caps`, `iac/opentofu`, `cost/arm64-first`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `c-cmake` | A C library or program built with CMake presets and Ninja, tested on the host with Unity, CMock, and Ceedling under sanitizers. | — | `cpp/language-standard`, `cpp/cmake-presets`, `cpp/vcpkg`, `cpp/clang-format`, `cpp/clang-tidy`, `cpp/unity-ceedling` |
| `cloudflare-fullstack` | A full web app, front end and back end, that runs only on Cloudflare. | `cloudflare-serverless` | `cloudflare/workers-compute`, `cloudflare/workers-limits`, `cloudflare/budget-alerts`, `cloudflare/queues-workflows`, `cloudflare/wrangler`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/kill-switch`, `cloudflare/static-assets`, `cloudflare/r2-storage`, `cloudflare/d1-or-hyperdrive`, `cloudflare/ai-gateway` |
| `cloudflare-serverless` | A back-end service that runs only on Cloudflare Workers, for a team that deploys with Wrangler alone. | — | `cloudflare/workers-compute`, `cloudflare/workers-limits`, `cloudflare/budget-alerts`, `cloudflare/queues-workflows`, `cloudflare/wrangler`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/kill-switch` |
| `cpp-cmake` | A C++ library or program built with CMake presets and Ninja, with vcpkg dependencies, and GoogleTest run under sanitizers. | — | `cpp/language-standard`, `cpp/cmake-presets`, `cpp/vcpkg`, `cpp/clang-format`, `cpp/clang-tidy`, `cpp/googletest`, `cpp/sanitizers`, `cpp/coverage` |
| `dotnet-api` | An HTTP API in C# on ASP.NET Core, for a .NET team. | — | `dotnet/dotnet-lts`, `dotnet/central-package-management`, `dotnet/dotnet-format`, `dotnet/analyzers-nullable`, `dotnet/xunit-v3`, `dotnet/minimal-apis`, `dotnet/ef-core-migrations`, `dotnet/ef-core`, `dotnet/testcontainers`, `dotnet/slnx-central-packages`, `dotnet/archunitnet`, `dotnet/benchmarkdotnet`, `tooling/hurl`, `tooling/k6` |
| `dotnet-azure` | An HTTP API in C# on Azure Container Apps with a managed PostgreSQL, for a .NET team that wants its bill to follow use. | `dotnet-api` | `dotnet/dotnet-lts`, `dotnet/central-package-management`, `dotnet/dotnet-format`, `dotnet/analyzers-nullable`, `dotnet/xunit-v3`, `dotnet/minimal-apis`, `dotnet/ef-core-migrations`, `dotnet/ef-core`, `dotnet/testcontainers`, `dotnet/slnx-central-packages`, `dotnet/archunitnet`, `dotnet/benchmarkdotnet`, `tooling/hurl`, `tooling/k6`, `azure/container-apps`, `azure/budgets`, `azure/log-retention`, `postgres/managed-postgres`, `iac/opentofu`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `esp-idf-firmware` | ESP32 firmware on ESP-IDF, tested on the host with Ceedling and in Espressif's QEMU with pytest-embedded. | — | `embedded/esp-idf`, `cpp/clang-format`, `cpp/unity-ceedling` |
| `flutter-mobile` | One mobile app for iOS and Android from a single Dart code base. | — | `dart/sdk-constraint`, `dart/flutter`, `dart/dart-format`, `dart/flutter-analyze`, `dart/flutter-test`, `dart/integration-test` |
| `gcp-run` | A container service on Google Cloud Run, for a team that wants its bill capped. | — | `gcp/cloud-run`, `gcp/registry-cleanup`, `gcp/log-retention`, `gcp/budgets`, `gcp/hard-caps`, `iac/opentofu`, `cost/preview-env-ttl`, `cost/llm-spend-caps`, `cost/pr-cost-delta-threshold`, `cost/policy-caps`, `cost/kill-switch` |
| `go-service` | An HTTP service in Go. | — | `go/go-version`, `go/go-modules`, `go/golangci-lint`, `go/go-test-race`, `go/govulncheck`, `go/net-http`, `go/slog`, `go/sqlc`, `go/single-module`, `go/depguard-boundaries`, `go/benchstat`, `tooling/hurl`, `tooling/k6` |
| `java-spring` | An HTTP service in Java on Spring Boot, for a JVM team. | — | `java/gradle-kotlin-dsl`, `java/spotless-format`, `java/error-prone`, `java/junit`, `java/java-lts`, `java/spring-boot`, `java/flyway-migrations`, `java/testcontainers`, `java/gradle-multi-project`, `java/spring-modulith`, `java/jmh`, `tooling/hurl`, `tooling/gatling` |
| `python-ai` | An AI agent service in Python with an HTTP API, retrieval over PostgreSQL, evals, traces, and durable workflows, for a team that builds its own agent loop. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/langgraph-agents`, `python/pydantic-validation`, `python/fastapi-api`, `python/sqlalchemy-orm`, `python/alembic-migrations`, `postgres/pgvector`, `python/deepeval-evals`, `ai/langfuse-traces`, `python/temporal-workflows` |
| `python-api` | An HTTP API in Python with a SQL database. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/fastapi-api`, `python/pydantic-validation`, `python/sqlalchemy-orm`, `python/alembic-migrations`, `python/uv-workspace`, `python/import-linter`, `python/pytest-benchmark`, `tooling/hurl`, `tooling/locust` |
| `python-cli` | A command-line tool or a library in Python. | — | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing` |
| `python-django` | A web service and its API in Python, on Django. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/django` |
| `python-mcp` | An MCP server in Python, which gives coding agents and other AI clients tools to call. | `python-cli` | `python/uv-tooling`, `python/ruff-lint-format`, `python/mypy-typing`, `python/pytest-tests`, `python/python-version`, `python/fastmcp-server`, `python/pydantic-validation` |
| `rust-cli` | A command-line tool in Rust. | — | `rust/msrv`, `rust/cargo-lockfile`, `rust/rustfmt`, `rust/clippy`, `rust/cargo-nextest`, `rust/cargo-deny`, `rust/clap`, `tooling/hyperfine` |
| `rust-library` | A Rust library crate published on crates.io. | — | `rust/msrv`, `rust/cargo-lockfile`, `rust/rustfmt`, `rust/clippy`, `rust/cargo-nextest`, `rust/cargo-deny`, `rust/cargo-semver-checks`, `rust/criterion` |
| `rust-service` | An HTTP service in Rust. | — | `rust/msrv`, `rust/cargo-lockfile`, `rust/rustfmt`, `rust/clippy`, `rust/cargo-nextest`, `rust/cargo-deny`, `rust/axum`, `rust/sqlx`, `rust/cargo-workspace`, `rust/cargo-workspace-boundaries`, `rust/criterion`, `tooling/hurl`, `tooling/k6` |
| `ts-ai` | An AI agent service in TypeScript on Node.js with an HTTP API, retrieval over PostgreSQL, evals, traces, and durable workflows. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/fastify-api`, `typescript/zod-validation`, `typescript/prisma-orm`, `typescript/atlas-migrations`, `typescript/pnpm-turborepo-workspace`, `typescript/dependency-cruiser`, `typescript/ai-sdk`, `postgres/pgvector`, `typescript/promptfoo-evals`, `ai/langfuse-traces`, `typescript/temporal-workflows` |
| `ts-api` | A TypeScript HTTP server on Node.js, with a managed PostgreSQL database. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/fastify-api`, `typescript/zod-validation`, `typescript/prisma-orm`, `typescript/atlas-migrations`, `typescript/pnpm-turborepo-workspace`, `typescript/dependency-cruiser`, `tooling/hurl`, `tooling/k6` |
| `ts-api-edge` | A TypeScript API that runs at the edge, on Cloudflare Workers. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/hono-api`, `typescript/zod-validation`, `typescript/drizzle-orm`, `cloudflare/workers-compute`, `cloudflare/d1-or-hyperdrive`, `cloudflare/d1-migrations`, `cloudflare/wrangler`, `typescript/pnpm-turborepo-workspace`, `typescript/dependency-cruiser`, `tooling/hurl`, `tooling/k6` |
| `ts-library` | A TypeScript library or tool on Node.js. | — | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts` |
| `ts-mobile` | A mobile app for iOS and Android in TypeScript, on Expo and React Native. | — | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/node-lts`, `typescript/jest-expo`, `typescript/expo`, `typescript/maestro` |
| `ts-web` | A TypeScript web app, its pages and its server, for the browser. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/nextjs-app-router`, `typescript/tailwind-css`, `typescript/shadcn-ui`, `typescript/zod-validation`, `typescript/testing-library`, `typescript/playwright-e2e` |
| `ts-web-spa` | A TypeScript single-page app for the browser, built by Vite, such as a dashboard behind sign-in. | `ts-library` | `typescript/pnpm-tooling`, `typescript/biome-lint-format`, `typescript/tsc-strict`, `typescript/vitest-tests`, `typescript/node-lts`, `typescript/tanstack-router`, `typescript/tanstack-query`, `typescript/tailwind-css`, `typescript/shadcn-ui`, `typescript/zod-validation`, `typescript/testing-library`, `typescript/playwright-e2e` |
| `zephyr-firmware` | Microcontroller firmware on Zephyr, tested on the host and in Renode, with MISRA checks and signed MCUboot updates. | — | `embedded/zephyr`, `cpp/clang-format`, `cpp/unity-ceedling`, `embedded/misra-cppcheck`, `embedded/renode-emulation`, `embedded/mcuboot-signed-updates` |
<!-- aidd:end -->

## Keep it current

- Each version is a field, never prose. It is read at the tool's release feed on the `checked` day, never typed from memory.
- Each week, the standards workflow runs `aidd eval standards --online`. That run reads the release feed of each tool: PyPI, npm, crates.io, Maven Central, NuGet, the Go module proxy, or GitHub releases. A language version uses its official toolchain feed: go.dev, nodejs.org, the .NET release index, Adoptium, or python.org. It flags a newer major release than `checked_version`. Before 1.0, a newer minor release counts as a major one. For Go and Python, a new minor release is a major one. A pre-release never counts. A standard with `version_policy: latest_lts` is compared with the newest LTS release, so a newer release that is not LTS does not flag it.
- Each standard names who read its source in `checked_by`: `agent:<harness>/<model>` for an agent's check, or a person's identity (`@login` or `email:<address>`, as an Approver is named) for a person's review. The catalog's entries are checked by an agent until a person reviews them, and an entry without `checked_by` counts as an agent's check. `aidd standard list` shows each standard's tier, and `aidd eval standards` counts both tiers.
- On a flag, a person reads the release notes. Then the person updates `checked_version`, `pin`, and `checked` in the library file.
- A new release waits out aidd's release cooldown before a pin moves to it, and a security release skips the wait. While it waits, `cooldown_until` names the day the pin may move, as the format below says. Once that day passes, `aidd list --upkeep` lists the move, and `aidd eval standards` warns with the standard and the version it holds. A week later it fails, on the scheduled run and never on a pull request, so an unrelated change never waits on the calendar. Read the feed again, move the pin, re-read the evidence, set `checked`, and remove `cooldown_until`. `version_policy: pinned` stays for a pin kept for good, with its reason in the body.
- A person reviews each standard again after a year when it is established, and after 90 days when it is emerging.
- A new id never replaces an old one silently. `standards/renames.yaml` keeps the old id, and a deprecated standard names its `replaced_by`.
- A new standard joins the library once two projects use it. Each change is a Spec ([CONTRIBUTING.md](../CONTRIBUTING.md#add-a-standard-or-a-stack)), and [plugins/README.md](../plugins/README.md#add-a-library-standard-or-a-stack) has the template.

## The format

A library standard is `standards/<group>/<topic>.md`, with YAML front matter between `---` lines. Its body has 300 words at most.

<!-- aidd:gen fields:standard -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable id, `<group>/<topic>`, such as `python/ruff-lint-format`. It matches the file's path under `standards/`. A renamed id stays in `standards/renames.yaml`. |
| `type` | `"opinionated"` | yes | Always `opinionated`: a choice a team commits to. An industry standard lives in the registry and is only waived per project. |
| `fills` | list of string | yes | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter`. Required for a library standard, so it cannot overlap a pack. |
| `default` | boolean | no | Whether it is aidd's default for each choice it fills, in its ecosystem. The library may hold several options for one choice; exactly one active option per choice and ecosystem is the default. A project adopts one of them. |
| `implements` | string | no | The pack or skill rule it puts to work, `<pack or skill>:<rule>`, such as `product-defaults:dev_basics`. It links the rule and never restates it. |
| `roles` | list of string | yes | aidd-team roles that read it before their step, or `*` for every role. |
| `when_changed` | list of string | no | Load it, and run its tests, only for a change that touches one of these paths. |
| `why` | string | yes | Why this option, in one or two sentences. |
| `reviewed` | string | yes | The day the choice was last judged still the right one for its slot: a judgment, which no source can carry. `checked` is the other kind of date, a fact re-read at its source. Due again after a year when established, after 90 days when emerging. |
| `maturity` | `established` \| `emerging` | yes | Established tools are reviewed yearly; emerging ones every 90 days. |
| `tool` | any | no | The tool it chooses, and where its releases are published. The weekly standards check reads that feed and flags a newer major than `checked_version`. It reads stable releases only and, for `version_policy: latest_lts`, the newest LTS release where the feed marks one. |
| `version_policy` | `latest_lts` \| `current_stable` \| `current_major` \| `pinned` | no | Which version a project uses. The version itself is a field, never prose. `pinned` keeps a version for good, for a reason the body gives; a pin that only waits out a cooldown uses `cooldown_until` instead. |
| `checked_version` | string | no | The newest release read at the source on the `checked` day, or, while `cooldown_until` holds the standard back, the release it keeps. Never typed from memory. |
| `checked` | string | no | The day `checked_version` was read at the tool's release feed, or the standard's claim at its source. It needs `source` and `evidence`. |
| `checked_by` | string | no | Who read `source` on the `checked` day: `agent:<harness>/<model>` for an agent's check, or a person's identity (`@login` or `email:<address>`, as an Approver is named) for a person's review. It sets the trust tier that `aidd standard list` and `aidd eval standards` show: an entry is checked by an agent until a person reviews it, and an entry without `checked_by` counts as an agent's check. |
| `source` | string | no | The official page where `checked_version` or the standard's claim was read on the `checked` day. Required with `checked`. |
| `evidence` | string | no | The sentence read at `source` on the `checked` day, quoted exactly, so the date is never a bare assertion. Required with `checked`. |
| `pin` | string | no | The version the `enforced_by` commands run, such as `0.16.10`. |
| `cooldown_until` | string | no | The day a newer release leaves aidd's release cooldown: 3 days after a patch, 7 after a minor or a major. Until then `pin`, or `checked_version` where there is no pin, keeps the release before it on purpose. A security release skips the wait, and a cooldown ends at most 7 days ahead. Once the day passes, `aidd eval standards` warns for 7 days, then fails. |
| `alternatives` | list of string | no | Other valid options for the same choice, by name. A company picks one through `standards_policy.replace`. |
| `status` | `active` \| `deprecated` | yes | `deprecated`: kept so projects that copied it hear about it; `replaced_by` names the successor. |
| `replaced_by` | string | when status is `deprecated` | The library standard that replaces a deprecated one. |
| `enforced_by` | list of mapping | no | `tests` templates. `aidd standard add` writes each one, so the gate runs it on every change its `when_changed` matches. |
<!-- aidd:end -->

A stack is `stacks/<name>.yaml`:

<!-- aidd:gen fields:stack -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | The stack's name, the file's stem, such as `python-cli`. |
| `description` | string | yes | What the stack is for, in one sentence. |
| `extends` | string | no | One other stack this one builds on, one level deep: a stack that extends a stack that extends another is refused, and so is a cycle. |
| `standards` | list of string | yes | Ids of active opinionated standards in the library, at most one per open choice and ecosystem. |
| `project` | mapping | no | Entries `aidd stack add` merges into the project's config. |
| `reviewed` | string | yes | The day the stack was last judged still a set of standards that go together. |
<!-- aidd:end -->
