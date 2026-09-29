# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The method, the schemas, the verifier, the CI templates, the skill, and the team plugin share one version, and every record carries `aidd_version`. What counts as a patch, minor, or major change: [CONTRIBUTING.md](CONTRIBUTING.md#versioning).

## [Unreleased]

1.0.0 is the first release of AIDD, the method, and aidd, the toolkit that runs it. Nothing was released before it, so everything below is new, and the Changed, Deprecated, Removed, and Fixed sections start with the next release.

### Added

#### The method and the loop

- **One loop** ([docs/METHOD.md](docs/METHOD.md)): Plan → Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Ship → Learn. The loop contract carries its own semantic version, which every gate event records.
- **One entry rule:** every change starts with `aidd next`, which computes the route from the paths and picks the lane: fast by default, spec when the change needs a Spec, and emergency for a production repair that a person declares.
- **Two human decisions:** Spec approval of what will be built and how it is proven, bound to a hash of the Spec, its tests, and its design; and Merge approval of exactly what was built, bound to the head commit. A person who asks for changes sends the work back to Specify or to Implement.
- **Learn closes the loop:** every incident, rollback, missed hypothesis, and retrospective becomes a new change.
- **Routes** named after ITIL change types (`standard`, `minor`, `normal`, `major`, `emergency`), <!-- aidd:gen count:types -->14<!-- aidd:end --> change types in Conventional Commits vocabulary, and <!-- aidd:gen count:dimensions -->8<!-- aidd:end --> risk dimensions in plain words. The gate recomputes the route from the real diff and can only raise it.
- **Four profiles**, each stricter than the last: `solo` (one person approves their own work, with Spec approval on major changes only and a cool-off before approving them), `team`, `org`, and `regulated`.
- **Objects:** the Spec (Intent, Acceptance, Tasks, tests, risk, rollback, observe window, hypothesis, and outcome), the `toml aidd` block, the optional Initiative and Epic, and the Proposal for work someone outside the team must agree to first.
- **Agile, rewritten for agents:** no sprints, estimates, or status meetings; every change is its own increment; work-in-progress limits apply to people's decisions, never to agents.
- **Normative text** with BCP 14 requirements and one conformance checklist. JSON Schemas are the source of truth for every object, and every table in the docs is generated from them.

#### The engine and the CLI

- **`aidd`**, a Python 3.11+ command line with no dependencies, and **the verifier** behind `aidd/gate`: a pure function from the facts of a change to pass, pending, or fail, with a stable code on every finding.
- **Evidence** bound to the head and base commits: new behavior must fail before the change and pass after it (red-then-green), from your tests, your existing CI checks, or an attested central workflow.
- **Controls:** separation of duties against every author, co-author, and committer; provenance from `Assisted-by:` trailers; scope that can never be a catch-all; protected paths that are always major; per-path owners and CODEOWNERS; specialist reviewer pools; a Policy command in any language; standard changes for trusted bots; and an emergency route with a named human commander and a review deadline.
- **Fail closed:** the config is read from the base branch, the platform adapters post `error` on any failure, and every run writes a gate record with a schema.
- **Commands:** `init`, `doctor`, `next`, `owners`, `new`, `import`, `validate`, `change`, `hash`, `test`, `gate`, `approve`, `ship`, `observe`, `watch`, `metrics`, `export`, `log`, `proposal`, `verify`, `eval`, `mcp`, `hook`, `upgrade`, `uninstall`, and `gen-docs` ([docs/CLI.md](docs/CLI.md)).
- **`aidd init`** reads the repository first with `--dry-run` (stacks, test commands, lint and type checks, sensitive areas, owners, CI), then writes the config, the skill, and the CI workflows, starts the gate in advisory mode, and wires <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> coding agents. Every profile except `solo` requires `--approvers`.
- **A fast local loop:** `aidd test --changed` runs only what your changes select, and `--watch` runs it again on every save; both write partial evidence, which the gate never accepts.
- **Keep current:** `aidd upgrade` refreshes the skill, the team files, and the CI pins without touching your own edits, and `aidd uninstall` reverses `init`; both are dry runs unless `--yes`.
- **Extensions** add commands, exporters, renderers, and domain packs through Python entry points, and never load in the commands that decide or change what the gate trusts ([CONTRIBUTING.md](CONTRIBUTING.md#extending-the-cli)).

#### Local-first and platforms

- **Local-first,** with no GitHub or GitLab: `aidd approve spec` and `aidd approve merge` record a person's decision on their own machine, and `aidd ship` merges a passing branch. Git worktrees share the approvals, so several agents can work in parallel.
- **GitHub:** a reusable gate workflow run from its own commit, a composite test action, and a GitHub App as the status source, with every action pinned by commit SHA. `aidd doctor` checks the branch rules when it can reach GitHub.
- **Merge queues on GitHub:** the gate judges each queue entry on its merge-group commit. Approvals stay on the pull request head, the tests run again on the merge-group commit, and its tree must be exactly the approved head merged into the commit the entry was built on.
- **GitLab**, experimental: merged-results pipelines and approval settings read from the API.
- **Any other CI** builds a context file and runs `aidd gate --context`.

#### Agents, hooks, and MCP

- **The `aidd` skill** (`.agents/skills/aidd/`), a self-contained Agent Skills folder any coding agent can read, and `AGENTS.md` wiring with a "Verifying your work" block.
- **The edit-time guard** allows or denies, never prompts: it denies edits outside the active Spec's scope, frozen tests and design files, commands that approve, merge, or ship, approval text typed into another terminal, and deploy commands held in `[[guard.gated_commands]]` until a person allows them.
- **Session hooks** at three levels (`[hooks] level`): an `aidd next` briefing at session start, a reminder or a hold when code changed without passing evidence, and a handoff reminder after a compaction. `aidd metrics --guard` counts every denial.
- **`aidd mcp`** serves the checks as MCP tools (`next`, `check_edit`, `validate`, `hash`, `change`, `gate`) over the <!-- aidd:gen mcp:revisions -->2025-06-18, 2025-03-26, and 2024-11-05<!-- aidd:end --> protocol revisions (a newer request is answered with <!-- aidd:gen mcp:latest -->2025-06-18<!-- aidd:end -->).
- **Claude Code plugins** (`aidd` and `aidd-team`) in their own marketplace, with evals against a no-plugin baseline and a managed-settings template.
- **Orca**, optional: aidd works inside it as it is, and the session hooks show aidd's next step and the work's state on each worktree's card, for display only ([docs/ORCA.md](docs/ORCA.md)).

#### The delivery team

- **`aidd-team`**, an optional plugin: <!-- aidd:gen count:roles -->15<!-- aidd:end --> agent roles led by people, from product manager to SRE. Each writes only its own files, hands off through a file and a four-line note, and never approves or merges. The tester who writes the tests never builds the code, and the verifier who runs the result wrote neither.
- **Commands** `/aidd-team:propose`, `onboard`, `plan`, `specify`, `implement`, `verify`, `review`, `secure`, `sweep`, `ship`, `postmortem`, and `retro`, each tested against its flow in `schemas/roles.json`.
- **Current, dated standards:** every standard carries its edition, source, and checked date; <!-- aidd:gen count:packs -->14<!-- aidd:end --> domain packs and <!-- aidd:gen count:practices -->23<!-- aidd:end --> practice skills; `aidd eval standards` fails on an entry older than a year.
- **Extensions per role** (skills, plugins, MCP servers, and tools), each with a tier, a license, a pin, and what it can touch.
- **Design before code:** two or three rough directions a person picks from, one named design system frozen at Spec approval, and a prototype lint the tester freezes.
- **Model tiers per role** priced to the cost of its mistakes, `[agents.models]` to choose a model per tier or role on each harness, and `[agents] independent_review` to ask for review on another model family.
- **Coverage:** every ISO/IEC/IEEE 12207 life cycle process mapped to the roles, commands, and people that cover it.

#### Work items

- **A backlog without a tracker:** `aidd next --all`, filtered by `--mine`, `--agent`, `--blocked`, `--label`, and `--waiting-on-me` (the Approver inbox, with a warning past `gates.max_open_per_approver` and escalation to `owners.backup_approvers`).
- **Why and where:** each step names its mission, goal, Initiative, Epic, and hypothesis, and a status group (backlog, unstarted, started, completed, cancelled) a tracker can mirror.
- **Triage, relations, and labels:** work an agent proposed waits for a person's `triage`; typed `relations` and `labels` sit on Specs, Epics, and Initiatives; an `aidd-handoff` block records who has the work and what a person must decide.
- **Parallel Tasks:** `aidd next --json` lists each Spec's Tasks as ready, blocked, or done, so a script can start one agent per ready Task.
- **History:** `aidd log <spec>` shows status transitions with time in state, approvals, and `Assisted-by:` trailers.
- **Proposals:** `aidd new proposal` and `aidd proposal matrix|convert`, with go/no-go and sign-off by a person, and an accepted proposal turned into an Initiative and Epics.

#### Teams, tenants, and organizations

- **One team of people and agents:** one shared config, skill, and set of roles; a `goal` every agent steers by; `aidd owners` for who decides and who works; `aidd next` warns when two branches' Specs change the same code.
- **House standards** under `[[standards]]`, with the roles that read them and the tests that enforce them.
- **Autonomy earned from evidence:** `aidd metrics --autonomy` suggests, per agent and kind of change, how much review it needs, and `--propose` drafts the `[[standard_changes]]` entry a person may merge.
- **Organizations:** org presets that repositories inherit and cannot loosen, locked keys, and an [Enterprise readiness](docs/ENTERPRISE.md) checklist with the status of every item.
- **Tenants:** a top-level `tenant` an org preset sets and may lock, stamped on every record and event. Identities written `<tenant>:<login>` scope approver pools, so another tenant's approval never counts, and `aidd metrics`, `aidd export`, and `aidd verify` take `--tenant`.

#### Metrics, records, the change record, and verify

- **`aidd metrics`:** lead time, where changes wait, first-pass share, loop speed paired with quality, cost per change from a ledger you export (`--cost`), and the five DORA metrics against your `[targets]` (`--dora`).
- **`aidd observe --window`** polls a Spec's observe command through its window and says when the rollback trigger fires; it never rolls back.
- **`aidd watch`** judges a metric against its control band, with no model, and writes a draft Spec on a serious breach.
- **Runbooks and postmortems** as validated repository objects; `aidd doctor` warns about a runbook not tested recently.
- **The gate record** (`aidd-record.json`) for every run, and `aidd export records|events` as JSON or CSV.
- **The agent change record:** `aidd gate --record` also writes `change-record.intoto.json`, an in-toto statement whose subject is the head commit ([`schemas/change-record.schema.json`](schemas/change-record.schema.json), a draft). The gate workflow template can sign a passing one with a GitHub artifact attestation.
- **`aidd verify <sha|path>`** checks a change record's shape, subject, tenant, decision, and human approvals, and its signature with `--online` or `--bundle`; an unsigned record fails unless `--allow-unsigned`.
- **Approve from a phone:** `aidd hash --comment --digest` prints the Spec in at most 25 lines above the approval line, and the gate summary carries a Merge approval digest.

#### Adoption helpers

- **`aidd import speckit|openspec|kiro|bmad`** writes a short Spec from another tool's plan: its words in Intent, an Acceptance item per scenario or requirement, a Task per task group, and the computed route. It never invents tests.
- **A notifier with no server:** `templates/github/aidd-notify.yml` posts status lines, a weekday digest, and a weekly metrics summary to Slack or Teams webhooks. Text only, never an approval.
- **One file, no install:** each GitHub Release carries `aidd.pyz`, the CLI as one zipapp for any Python 3.11+.
- **A dev container starting point:** `aidd init --devcontainer` writes a container whose firewall denies outbound traffic except to an allow-list, with the agent as a non-root user. aidd itself sandboxes nothing.
- **Your own hooks beside the guard:** [examples/hooks](examples/hooks/README.md).

#### Conformance and documentation

- **Conformance:** <!-- aidd:gen count:examples -->15<!-- aidd:end --> verifier examples and <!-- aidd:gen count:mutations -->115<!-- aidd:end --> data mutations pinned by finding code ([`schemas/conformance.schema.json`](schemas/conformance.schema.json)), so another verifier can prove it behaves the same; <!-- aidd:gen count:routing-scenarios -->45<!-- aidd:end --> routing scenarios and <!-- aidd:gen count:role-scenarios -->15<!-- aidd:end --> role scenarios; the official JSON Schema Test Suite.
- **Documentation:** a quickstart, a [how-to guide](docs/HOW-TO.md), the method, the delivery team and its reference tables, adoption from one person to many companies, platforms, config, CLI, a glossary, FAQ, and rationale.
- **License:** Apache-2.0.

### Security

- **Separation of duties** is computed from platform facts. Every profile requires `owners.approvers`; `solo` waives only the rule that the Approver differs from the author, and records the waiver.
- **The Spec approval hash** is a SHA-256 over one canonical JSON document of the Spec's stable fields, its body, and its frozen files, so no part can absorb another.
- **The base branch decides:** the config, its mode, the Policy, and CODEOWNERS come from the base. A CI variable never relaxes an enforcing config, and an org preset locks what repositories cannot loosen.
- **Approvals:** an approval of an older head, or given before the change was retargeted, does not count; a local approval counts only with a good signature once signing is set up; an agent account never approves, and the gate warns when one approves on the platform.
- **Agents never approve or merge:** the hook denies approve, merge, ship, and force-push commands to agents, including approval text typed into another terminal.
- **Protected paths** include workspace scripts (`orca.yaml`, `.worktreeinclude`) and the dev container; a change to a lint, type-check, or formatter config is at least normal.
- **Evidence and adapters:** required checks are judged per check suite, downloads are capped, `extends` fetches refuse redirects, and `aidd observe` drops credential-like variables.
- **Supply chain:** a minimal App token, comment triggers limited to members, releases verified by tag signature, ancestry, CI, and gate, with build provenance and a CycloneDX SBOM; CodeQL, zizmor, actionlint, and OpenSSF Scorecard in CI.
- **The trust model** and how to report a vulnerability: [SECURITY.md](SECURITY.md).

Every known limit of this release: [docs/RATIONALE.md](docs/RATIONALE.md#known-limits-in-100).

[Unreleased]: https://github.com/thaithienvanid/aidd/commits/main
