# Routes

Every change starts with `aidd next`, the loop's entry rule, and the fast lane is the default. The route is one choice: **no Spec (`minor`), a Spec (`normal`), or a production repair (`emergency`)**. You do not need to guess `major`: when a Spec-backed `normal` change's diff requires it, the gate raises it and applies the major gates (a specialist reviewer and an `observe` block), so add those as soon as the computed route (`aidd next`, or `aidd new spec --paths`) says major. A `minor` block whose diff needs a Spec still fails. `standard` is for configured bot changes.

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

- `confidence = "low"`: a missing fact could change the route. Ask for it.
- Freeze: Policy answers `freeze`. Only a production repair (route emergency) continues.
- No owner: nobody can be named as `owner_team` (a judgment stop; the gate only checks that the field is set).

## Risk dimensions

Pick every dimension the change can harm; the gate computes the ones the paths imply, and an inline block must declare them (a missing one fails), while a Spec gets a warning. `data`, `security`, `privacy`, `financial`, and `compliance` make it major and name the specialist pool that reviews it (`data`, `security`, `privacy`, `finance`, `compliance`); the others only rule out minor. Irreversibility is not a dimension: set `risk.reversible = false`, which also makes it major. `confidence = "medium"` changes nothing in the gate; it tells the Approver which facts you could not check (list them in `open_questions`).

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

Declare every dimension the diff implies. A path rule that adds a dimension you did not declare fails an inline block and warns on a Spec.

## Route meanings

<!-- aidd:gen vocab:route -->
| Token | Meaning |
| --- | --- |
| `standard` | A pre-approved change class from config standard_changes, such as a bot's dependency patch. Merges on green tests with no human approval. Never touches protected paths. |
| `minor` | Small, reversible, one Task, no risk dimension, within the minor budget. No Spec file needed; one Merge approval. |
| `normal` | Everything that is not minor, standard, major, or emergency. Spec, Spec approval, SHA-bound tests with red-then-green, one Merge approval. |
| `major` | Touches a protected path, data, security, privacy, money, or compliance, or cannot be reverted. Normal plus a specialist review, an observe block, and stricter profile gates. Computed by the gate, never guessed. |
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

Protected paths gate the gate itself: the aidd config (`.aidd/`), CI, CODEOWNERS, and agent instructions and skills. They are always major and cannot be disabled. A repo may add rules and paths, and may disable a `baseline:` rule by name in the config, which is itself a protected change.

<!-- aidd:gen baseline -->
| Rule | Minimum route | Dimensions | Paths | Excluded |
| --- | --- | --- | --- | --- |
| protected (cannot be disabled) | major | none | <details><summary>110 paths</summary>`.aidd/**`, `.github/workflows/**`, `.github/actions/**`, `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`, `.gitlab-ci.yml`, `.gitlab/**`, `**/AGENTS.md`, `**/CLAUDE.md`, `**/GEMINI.md`, `.agents/**`, `.claude/**`, `.codex/**`, `.cursor/**`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md`, `.github/instructions/**`, `.github/skills/**`, `.mcp.json`, `.vscode/mcp.json`, `**/AGENTS.override.md`, `**/CLAUDE.local.md`, `.gemini/**`, `.github/prompts/**`, `.github/agents/**`, `.devcontainer/**`, `orca.yaml`, `.worktreeinclude`, `.husky/**`, `.githooks/**`, `.pre-commit-config.yaml`, `lefthook.yml`, `.lefthook.yml`, `.gitmodules`, `.github/dependabot.yml`, `.github/dependabot.yaml`, `renovate.json`, `renovate.json5`, `.renovaterc`, `.renovaterc.json`, `.github/renovate.json`, `.github/renovate.json5`, `Jenkinsfile`, `**/Jenkinsfile`, `.circleci/**`, `azure-pipelines.yml`, `.azure-pipelines/**`, `.buildkite/**`, `bitbucket-pipelines.yml`, `.drone.yml`, `.travis.yml`, `.kiro/**`, `.roo/**`, `.clinerules`, `.clinerules/**`, `.windsurf/**`, `.continue/**`, `.aider*`, `.junie/**`, `.amazonq/**`, `.trae/**`, `.augment/**`, `**/AGENT.md`, `.github/copilot/**`, `action.yml`, `action.yaml`, `**/.github/actions/**`, `cloudbuild.yaml`, `cloudbuild.yml`, `.tekton/**`, `.woodpecker.yml`, `.woodpecker.yaml`, `.woodpecker/**`, `install.sh`, `**/install.sh`, `pyproject.toml`, `**/pyproject.toml`, `SECURITY.md`, `**/SECURITY.md`, `GOVERNANCE.md`, `RELEASING.md`, `REVIEW.md`, `setup.py`, `setup.cfg`, `.github/hooks/**`, `.agent/rules/**`, `.devin/**`, `.cline/**`, `.roorules`, `.roomodes`, `.amp/**`, `opencode.json`, `opencode.jsonc`, `.opencode/**`, `.zed/**`, `.rules`, `WARP.md`, `.warp/**`, `QWEN.md`, `.qwen/**`, `.augment-guidelines`, `.factory/**`, `.goosehints`, `.goose/**`, `.grok/**`, `.vibe/**`, `.aiderignore/**`, `CONVENTIONS.md`</details> | none; also every file a bound Policy or Observe command runs |
| `baseline:dependencies` | normal | third_party | `**/package.json`, `**/package-lock.json`, `**/pnpm-lock.yaml`, `**/yarn.lock`, `**/bun.lockb`, `**/bun.lock`, `**/requirements*.txt`, `**/pyproject.toml`, `**/poetry.lock`, `**/uv.lock`, `**/Pipfile`, `**/Pipfile.lock`, `**/go.mod`, `**/go.sum`, `**/Cargo.toml`, `**/Cargo.lock`, `**/Gemfile`, `**/Gemfile.lock`, `**/pom.xml`, `**/build.gradle`, `**/build.gradle.kts`, `**/*.csproj`, `**/packages.lock.json`, `**/composer.json`, `**/composer.lock`, `**/Package.swift`, `**/Package.resolved`, `**/pubspec.yaml`, `**/pubspec.lock`, `**/.npmrc`, `**/.yarnrc`, `**/.yarnrc.yml`, `**/.pnpmfile.cjs`, `**/setup.py`, `**/setup.cfg`, `**/requirements*.in`, `**/go.work`, `**/go.work.sum`, `**/*.gradle`, `**/*.gradle.kts`, `**/gradle.properties`, `**/libs.versions.toml`, `**/.terraform.lock.hcl`, `**/Podfile`, `**/Podfile.lock`, `**/Chart.lock`, `**/nuget.config`, `**/NuGet.Config`, `**/settings.xml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:build-tooling` | normal | third_party | `**/gradle/wrapper/**`, `**/gradlew`, `**/gradlew.bat`, `**/mvnw`, `**/mvnw.cmd`, `**/.mvn/**`, `**/Makefile`, `**/justfile`, `**/Taskfile.yml`, `**/Taskfile.yaml`, `**/noxfile.py`, `.tool-versions`, `.nvmrc`, `.node-version`, `.python-version`, `mise.toml`, `.mise.toml`, `.gitattributes` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:containers` | normal | third_party | `**/Dockerfile`, `**/*.dockerfile`, `**/Containerfile`, `**/docker-compose*.yml`, `**/docker-compose*.yaml`, `**/compose.yaml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:test-config` | normal | none | `**/jest.config.*`, `**/vitest.config.*`, `**/pytest.ini`, `**/conftest.py`, `**/tox.ini`, `**/.coveragerc`, `**/phpunit.xml`, `**/karma.conf.*`, `**/playwright.config.*`, `**/cypress.config.*` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:quality-config` | normal | none | `**/.eslintrc`, `**/.eslintrc.*`, `**/eslint.config.*`, `**/tsconfig.json`, `**/tsconfig.*.json`, `**/.prettierrc`, `**/.prettierrc.*`, `**/prettier.config.*`, `**/biome.json`, `**/biome.jsonc`, `**/ruff.toml`, `**/.ruff.toml`, `**/mypy.ini`, `**/.mypy.ini`, `**/.flake8`, `**/.pylintrc`, `**/.golangci.yml`, `**/.golangci.yaml`, `**/.golangci.toml`, `**/.golangci.json`, `**/clippy.toml`, `**/.clippy.toml`, `**/rustfmt.toml`, `**/.rustfmt.toml`, `**/.rubocop.yml`, `**/phpstan.neon`, `**/phpstan.neon.dist`, `**/detekt.yml`, `**/.swiftlint.yml`, `**/analysis_options.yaml`, `**/.eslintignore`, `**/.prettierignore`, `**/.stylelintrc*`, `**/pyrightconfig.json`, `**/.clang-tidy`, `**/.swiftformat`, `**/.scalafmt.conf`, `**/.markdownlint*`, `**/deno.json`, `**/deno.jsonc` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:iac` | normal | availability | `**/*.tf`, `**/*.tfvars`, `**/terraform/**`, `**/k8s/**`, `**/kubernetes/**`, `**/helm/**`, `**/Chart.yaml`, `**/charts/*/templates/**`, `**/*.bicep`, `**/cloudformation/**`, `**/pulumi/**`, `**/kustomization.yaml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:migrations` | major | data | `**/migrations/**`, `**/migrate/**`, `**/alembic/**`, `**/db/migration/**`, `**/db/changelog/**`, `**/db/schema.rb`, `**/schema.prisma`, `**/flyway/**`, `**/liquibase/**` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:auth` | major | security | `**/auth/**`, `**/authn/**`, `**/authz/**`, `**/iam/**`, `**/rbac/**`, `**/permissions/**`, `**/*.rego` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:secrets-crypto` | major | security | `**/crypto/**`, `**/secrets/**`, `**/.env`, `**/.env.*`, `**/*.pem`, `**/*.key`, `**/*.p12` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**`, `**/.env.example`, `**/.env.sample`, `**/.env.template`, `**/.env.dist` |
<!-- aidd:end -->

## Confidence

<!-- aidd:gen vocab:confidence -->
| Token | Meaning |
| --- | --- |
| `high` | Every fact that could change the route is known. open_questions is empty. |
| `medium` | Some facts are missing, and none of them could change the route. List them; the gate does not act on medium. |
| `low` | A missing fact could change the route. Stop and ask. |
<!-- aidd:end -->
