# Enterprise readiness

What a platform, security, or compliance team checks before adopting aidd, with the honest status of each item in this release. **yes** means it exists and the file that satisfies it is named. **partial** means it exists with a stated limit. **no** means it is not built or not written yet. Built is not proven. The platform table says separately whether each platform has been **exercised live**, on a real instance rather than against a faked API. The open items at the end say which are documentation and which are product, so this page cannot drift into overclaiming.

## Contents

1. [Release status and maturity](#1-release-status-and-maturity)
2. [Installation in restricted environments](#2-installation-in-restricted-environments)
3. [Supply chain and release integrity](#3-supply-chain-and-release-integrity)
4. [Secrets and permissions](#4-secrets-and-permissions)
5. [Identity and access](#5-identity-and-access)
6. [Audit evidence](#6-audit-evidence)
7. [Data handling and privacy](#7-data-handling-and-privacy)
8. [Operations](#8-operations)
9. [Governance](#9-governance)
10. [Cost](#10-cost)
11. [Platform coverage](#11-platform-coverage)
12. [Agent sessions under managed settings](#12-agent-sessions-under-managed-settings)
13. [Multi-tenancy](#13-multi-tenancy)

The [open items](#open-items) close the page: the known gaps in this release.

## 1. Release status and maturity

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| A released, tagged version | no | 1.0.0 is unreleased ([CHANGELOG.md](../CHANGELOG.md)); until the `v1.0.0` tag exists, pin a commit SHA ([INSTALL.md](INSTALL.md#versions)) |
| Published on PyPI | no | the release workflow publishes with trusted publishing once a maintainer tags ([RELEASING.md](../RELEASING.md)); install from the git URL until then |
| Exercised on a live GitHub repository | no | the first real pull request through this repository's own gate is the release criterion ([RATIONALE.md](RATIONALE.md#known-limits-in-100)) |
| GitLab | partial | end-to-end tests against a real git repository and a faked API; not yet run against a production instance ([PLATFORMS.md](PLATFORMS.md#gitlab)) |
| Published agent eval scores | no | the scenarios and scorers ship; no baseline per model is recorded yet ([evals/roles/README.md](../evals/roles/README.md)) |
| Conformance suite | yes | <!-- aidd:gen count:examples -->22<!-- aidd:end --> example cases plus <!-- aidd:gen count:mutations -->198<!-- aidd:end --> mutations, replayable by any implementation: `aidd eval examples` ([examples/README.md](../examples/README.md)) |

## 2. Installation in restricted environments

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| No runtime dependencies | yes | `dependencies = []` in [pyproject.toml](../pyproject.toml); TOML and JSON Schema come from the standard library and `src/aidd/schema.py` |
| Works offline after install | yes | the wheel bundles the schemas, the skill, the templates, and the team plugin; `aidd validate` (unless the config `extends` a URL), `aidd gate --explain`, and `aidd --help` need no network; `aidd init` needs none either, but unless `AIDD_OFFLINE=1` it may try `git ls-remote` with a 5-second timeout |
| Install from a private mirror | partial | any index or mirror that serves the wheel or the git URL works (`uv tool install`, `pipx`, `pip`); a PyPI release is the missing piece for mirrors that proxy PyPI |
| Pinned install | yes | tag or commit SHA in every path: `AIDD_REF` (and `AIDD_SHA256` for the wheel) for the installer, `@<sha>` in the git URL, the workflow refs ([INSTALL.md](INSTALL.md#versions)); fetch the installer itself from a tag URL rather than `main` for a fixed script |
| Proxy and custom CA | partial | the gate uses `urllib`, which honors `HTTPS_PROXY`, `NO_PROXY`, and the system certificate store; not tested against a corporate proxy yet |
| Runtime network egress, complete list | yes | the gate reaches the platform's API, its git server, and its artifact storage, the URL of an `extends` parent or org preset when set, and the attestation endpoints when `evidence.signer_workflow` is set; nothing else, ever ([egress list](PLATFORMS.md#github-enterprise-server-and-restricted-actions)). The CLI commands that reach the network outside the gate are in [SECURITY.md](../SECURITY.md#data-handling) |
| GitHub Enterprise Server and air-gapped Actions | partial | GHES lacks `job.workflow_sha`: copy `gate.yml` into a repository of your own and mirror or allowlist the actions it uses ([PLATFORMS.md](PLATFORMS.md#github-enterprise-server-and-restricted-actions)) |
| Offline documentation | partial | `docs/` ships in the sdist and every rule has `aidd gate --explain`; the wheel carries no docs |

## 3. Supply chain and release integrity

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| Every GitHub Action pinned by commit SHA | partial | every third-party action in the workflows, templates, and `action.yml` is pinned by SHA, and Dependabot bumps them monthly, in one grouped pull request ([.github/dependabot.yml](../.github/dependabot.yml)). The CI files `aidd init` writes pin aidd itself to a commit when init can find one: the commit it runs from in a git checkout, or the release tag's commit when an installed CLI can reach GitHub. Otherwise they keep the tag, and `aidd init --ref <sha>` or `aidd upgrade --ref <sha> --yes` pins the SHA ([INSTALL.md](INSTALL.md#before-the-first-release)) |
| The gate runs code nobody can swap at run time | yes | the reusable workflow checks out `job.workflow_repository@job.workflow_sha` and runs the gate from that commit; no package index, no PR code ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)) |
| Build provenance | yes, in the release workflow; not yet exercised by a release | the `attest` job runs `actions/attest-build-provenance` on every dist, and nothing is published without it ([release.yml](../.github/workflows/release.yml), [RELEASING.md](../RELEASING.md)) |
| Signed tags | yes, in the release workflow; not yet exercised by a release | the `verify` job refuses a lightweight tag and a tag whose signature GitHub does not verify; the tag ruleset and the signing keys are set up as [RELEASING.md](../RELEASING.md) says |
| SBOM attached to releases | yes, in the release workflow; not yet exercised by a release | a CycloneDX SBOM of exactly what installing the wheel yields, attested with `actions/attest-sbom` for the dists and `aidd.pyz` and attached to the GitHub Release with the checksums ([RELEASING.md](../RELEASING.md)) |
| Build backend pinned | yes, in the release workflow; not yet exercised by a release | `uv build --require-hashes` against the hash-locked `.github/requirements/build.txt`, with a pinned uv and `SOURCE_DATE_EPOCH` from the tag commit ([RELEASING.md](../RELEASING.md)); a local build still takes the range `hatchling>=1.27,<2` in [pyproject.toml](../pyproject.toml) |
| Dependency policy | yes | none at runtime, by design ([CONTRIBUTING.md](../CONTRIBUTING.md)); development tools run through `uvx` in CI |
| Third-party extensions | yes, with a trust boundary | installed packages may add commands, exporters, renderers, and packs through entry points ([CONTRIBUTING.md](../CONTRIBUTING.md#extending-the-cli)). The commands that decide or change what the gate trusts (`gate`, `test`, `validate`, `hash`, `approve`, `ship`, `hook`, `mcp`, `describe`, `assess`, `list`, `record verify`, and `init`, `upgrade`, `uninstall`, which write the wiring) never discover them: discovery is sealed before their parser is built, so no extension code is imported in their process, and a test proves the gate's output and record are byte-identical with a hostile plugin installed. The boundary is aidd's own imports: Python still runs any `.pth` file an installed package ships, so the gate job installs aidd alone, from the pinned commit ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)), and extensions belong in the environment where people read reports |

## 4. Secrets and permissions

| Secret or variable | Where it lives | Who reads it |
| --- | --- | --- |
| `AIDD_APP_PRIVATE_KEY` | the `aidd-gate` environment only, with deployment branches limited to the protected bases; the caller passes no secrets | the gate job mints a short-lived installation token with `actions/create-github-app-token` right before it posts the status |
| `AIDD_APP_ID` | a repository or organization variable; keep it where only organization admins edit ([PLATFORMS.md](PLATFORMS.md#github)) | the same step |
| `GITHUB_TOKEN` | Actions default, `statuses: write` on the gate job only, `contents: read` on the test job | the gate when no App is configured (advisory quality, since anyone with write access could post the status) |
| `AIDD_GITLAB_TOKEN` | injected into the gate job by a pipeline execution policy, `read_api` scope, Reporter role | the GitLab adapter |
| `ANTHROPIC_API_KEY` | this repository's own secret, on its `evals` environment where the plan offers one, for the agent evals: weekly, and by hand. No pull request run reads it, since a pull request's code could: a maintainer runs the evals by hand on a branch that changes agent configuration, after reading it. Never needed by an adopter | [.github/workflows/evals.yml](../.github/workflows/evals.yml) |

- The Policy command runs in a clean worktree of the base branch with the secret environment stripped. The test job runs pull request code with a read-only token and no secrets ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)).
- The GitHub App's permissions, including organization `Members: read` when approvers are teams, are listed once, in [PLATFORMS.md](PLATFORMS.md#setup).
- Rotate the key on your schedule; the gate reads it per run.

## 5. Identity and access

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| Approvals attributed from platform facts only | yes | reviews and unedited comments on the head commit; authors are the PR/MR author plus every commit author and committer; bots never approve, system accounts are bot-like only ([METHOD.md §8](METHOD.md#8-approvals-and-separation-of-duties)) |
| Separation of duties | yes | enforced from the team profile up; recorded as `waived_solo` under solo; two Approvers and a specialist on major under regulated ([schemas/profiles.json](../schemas/profiles.json)) |
| SSO, SAML, SCIM, enterprise managed users | partial | the gate trusts the platform's logins and team membership, so it inherits your SSO; not yet exercised with enterprise managed users or SAML-enforced team resolution |
| Service accounts | yes, by design | a human-looking service account cannot be exempted as a system account; list agent accounts in `identities.bots`, which can never approve |
| Path owners | yes | `[[owners.paths]]` and CODEOWNERS, with separation of duties and team resolution applied at Spec approval and Merge approval ([PLATFORMS.md](PLATFORMS.md#reuse-what-you-already-have)) |
| Org presets and locked keys | yes | `extends` by path or pinned URL, `AIDD_ORG_PRESET`, and keys a parent locks; a child can only tighten ([ADOPTION.md](ADOPTION.md#organization), [FAQ](FAQ.md#can-our-org-change-the-rules)) |
| Many repositories, monorepos, many companies | yes | `trace_id` across repositories, `owners.paths` and `when_changed` inside one, and a `tenant` per company, set by its org preset and stamped on every record and event ([§13](#13-multi-tenancy), [METHOD.md §10](METHOD.md#10-scale-modules)) |
| Administrator bypass | partial | the first config and the removal PR/MR merge outside the gate; the platform's audit log is the evidence of a bypass, and a ruleset bypass list makes it explicit; no aidd record is written for a bypass |

## 6. Audit evidence

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| A record per decision, with a schema | yes | `aidd-record.json` per run, validated against [schemas/record.schema.json](../schemas/record.schema.json); its fields and what each evidences are in [CONTROLS.md](CONTROLS.md#what-the-record-evidences) |
| An event per run, including crashes | yes | one JSON line per decision, and an `error` line when a run crashed and posted an error status ([schemas/event.schema.json](../schemas/event.schema.json)); `aidd metrics` reads them |
| Traceability | yes | `trace_id` from the Spec through the Change Request block to the record and the event; the gate checks they agree |
| Retention | partial | records, events, test evidence, and logs are workflow artifacts that aidd's workflows upload with `retention-days: 90`. GitHub keeps an artifact for the shorter of that and the repository's artifact retention setting, which may be 1 to 90 days on a public repository and 1 to 400 days on a private or internal one (90 by default). For longer retention, ship the records and the `--events` output to your own log store; this row is the one statement of retention, and other pages link here |
| Integrity of the record | partial | the gate record is a plain artifact; beside it, `aidd gate --record` writes the agent change record, an in-toto statement of the decision whose subject is the head commit ([schemas/change-record.schema.json](../schemas/change-record.schema.json), a draft). The gate workflow template signs a passing one with a GitHub artifact attestation when the repository variable `AIDD_ATTEST_CHANGE_RECORD` is `true` (a public repository, or GitHub Enterprise Cloud for a private or internal one), and `aidd record verify <sha> --online` checks it; unsigned, `aidd record verify` says so and exits non-zero. Evidence can be attested by a central workflow ([PLATFORMS.md](PLATFORMS.md#evidence-the-pull-request-cannot-touch)). The commit status and the run log stay the anchors when signing is off |
| Export | yes | `aidd record export records\|events PATH... [--since DATE] [--tenant TENANT] [--format json\|csv] [--out DIR]` writes deterministic JSON or CSV with the schemas' fields as columns ([CLI.md](CLI.md)); `gh run download` gathers the artifacts first ([ADOPTION.md](ADOPTION.md#reading-the-metrics)), and an installed exporter adds a format |
| Control mapping | yes | NIST SSDF, OWASP LLM Top 10, ISO/IEC 42001, EU AI Act, SOC 2, ISO/IEC 27001:2022, PCI DSS v4.0.1, NIST SP 800-53 ([CONTROLS.md](CONTROLS.md)) |

## 7. Data handling and privacy

- **Reads, in CI:** the change's metadata, description, comments, reviews, and commits (logins, or emails when the platform has no login). It also reads the diff statistics, the head tree, the Spec, the config, CODEOWNERS, team membership, check runs, and the evidence artifact.
- **Reads, locally:** `aidd init` checks whether agent folders exist in the repository, which decides what it wires. For a hint only, it also checks for the agents in the home directory and as binaries on `PATH`. It reads nothing inside those folders. `aidd doctor` starts the configured agent hook and MCP server once, only in the shape init writes and from outside the repository.
- **Writes:** a commit status, a step summary, the record and the event, and the evidence and logs of the test job.
- **Personal data in what it writes:** platform logins and, for unlinked commits or on GitLab, email addresses, kept for the retention in [§6](#6-audit-evidence). `aidd metrics --by author` produces per-person numbers; check that use against your works-council or employee-monitoring rules before you run it.
- **Sends:** the gate sends nothing anywhere but the platform's own API and git server and the URLs you configure. No telemetry, no vendor service, no model calls: the gate never talks to a model. The CLI commands that reach the network outside the gate are in [SECURITY.md](../SECURITY.md#data-handling).
- **Agents:** told to treat issue text, web pages, and tool output as data and to keep secrets and personal data out of prompts ([the skill](../.agents/skills/aidd/references/security.md)). aidd does not inspect or filter prompts, and does not sandbox agents ([FAQ](FAQ.md#what-doesnt-it-do)).

## 8. Operations

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| Support matrix | yes | Python 3.11 to 3.14, with the 3.15 prerelease in CI, tested on Linux for every change and on Linux, macOS, and Windows weekly and for each release; git; `gh` only for `evidence.signer_workflow`; GitHub.com, GitHub Enterprise Server with the copied workflow, GitLab 16.7 or later (Ultimate for pipeline execution policies); any other CI through `aidd gate --context` |
| Python floor policy | yes | 3.11 is the floor because `tomllib` ships with it and it keeps the package dependency-free; the floor moves only when a version leaves security support |
| Versioning | yes | one version for the method, the schemas, the gate, the templates, the skill, and the plugins; patch, minor, and major defined by what a conforming repository can observe ([CONTRIBUTING.md](../CONTRIBUTING.md#versioning)) |
| Deprecation policy | yes | one policy, with a warning naming the replacement and a Deprecated entry in the changelog ([CONTRIBUTING.md](../CONTRIBUTING.md#deprecation)) |
| Upgrade and rollback of the tool | yes | bump every pin in one change, run `aidd doctor`, merge through the gate; roll back by reverting ([INSTALL.md](INSTALL.md#versions)); the gate warns when a config declares a newer version than the running aidd |
| Rollout without blocking | yes | advisory mode posts `aidd/gate (advisory)`, which never satisfies a required status; `aidd init` starts there ([ADOPTION.md](ADOPTION.md)) |
| Failure modes | yes | a crash posts `error` and exits 2, so a required status stays red (fail closed); a malformed context fails; an unreachable Policy denies; API errors retry three times; a moved head is not posted; a head shared by several pull requests gets the worst decision ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)) |
| Runbook for a red gate | partial | re-run the workflow for a platform error; `aidd gate --explain <rule>` for a rule; an administrator merge for a wrong-config emergency, evidenced by the platform audit log; not yet a page of its own |
| Scale limits | yes | 250 commits per change, 3,000 comments or reviews, 1,000 check runs; 15 to 30 API calls per run under the App installation's rate limit; one gate run per pull request at a time ([ADOPTION.md](ADOPTION.md#organization)) |
| Performance on large monorepos | no | not benchmarked; the gate lists the head tree once per run |

## 9. Governance

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| License | yes | Apache-2.0 ([LICENSE](../LICENSE)); the vendored JSON Schema test suite keeps its own license |
| Code of conduct, security disclosure, contribution process | yes | [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [SECURITY.md](../SECURITY.md) (acknowledgement in 3 business days, a fix or mitigation plan in 30), [CONTRIBUTING.md](../CONTRIBUTING.md) with an RFC process for changes to the method |
| Maintainers and succession | partial | one maintainer today, stated in [GOVERNANCE.md](../GOVERNANCE.md) with the succession plan; no organization backs the project |
| Roadmap | no | none is published; the open items below are the known gaps in this release, not commitments |
| Contributor agreement | none required | Apache-2.0 inbound equals outbound; no CLA or DCO |
| Support model | community | issues and pull requests, no SLA ([GOVERNANCE.md](../GOVERNANCE.md)) |

## 10. Cost

| Item | What it costs |
| --- | --- |
| The gate job | one Python process with no dependencies, seconds per run; it runs on every pull request event, `/aidd` comment, and test completion |
| The test job | your own suite once (green), and the Spec's new-behavior tests once more on the base commit (red): up to twice the test time on spec-lane changes; `evidence.status_checks` reuses a suite your CI already ran |
| Storage | one record, one event file, and the evidence per run, kept as [§6](#6-audit-evidence) says, against the Actions storage quota |
| API calls | 15 to 30 per run under the App installation's rate limit, shared by every repository in the organization |
| Tokens | the team spends them where mistakes are expensive: the strongest model only for the six deciders (the `reasoning` tier), such as the architect and the reviewer, whose mistakes no later check catches; every other role, the verifier included, is in the `execution` tier on a mid-size model (`[agents.models]` runs a tier or a role on any named model, or on the session's with `inherit`); a specialist runs only when its start condition holds, and a small minor fix runs one developer ([TEAM.md](TEAM.md#what-it-costs-and-when-it-is-worth-it)); the gate itself calls no model |
| Seeing what agents cost | `aidd metrics --cost ledger.jsonl` joins a ledger you export from your harness or orchestrator to changes by Spec id, commit, or branch, and shows cost per change beside the first-pass share, against `max_mean_cost_per_change` in `[targets]`; display only, never a gate rule and never a reason to pause work ([ADOPTION.md](ADOPTION.md#cost-per-change)) |

## 11. Platform coverage

**Implemented** says what is built; **exercised live** says whether it has run on a real instance. No platform has yet: the first live pull request through this repository's own gate is the release criterion (§1). On any platform, the gate blocks only in enforce mode, as a required check, from a pinned source. Without them it is advisory ([what holds without them](PLATFORMS.md#what-holds-without-the-full-setup)).

| Platform | Implemented | Exercised live |
| --- | --- | --- |
| GitHub.com | yes: reusable gate workflow, composite test action, App status source, rulesets, CODEOWNERS, central attested evidence ([PLATFORMS.md](PLATFORMS.md#github)) | no: tested end to end against a faked API |
| GitHub Enterprise Server | partial: copy `gate.yml`; artifact attestations and `create-github-app-token` need a GHES version that ships them | no |
| GitLab | partial: experimental adapter, execution-policy enforcement, self-managed API hosts ([PLATFORMS.md](PLATFORMS.md#gitlab)) | no: experimental; tested against a real git repository and a faked API |
| Any other CI | yes: build a context and run `aidd gate --context` ([PLATFORMS.md](PLATFORMS.md#any-other-ci)) | no |
| Merge queues | GitHub: yes, each entry is judged on its merge-group commit ([PLATFORMS.md](PLATFORMS.md#merge-queues)). GitLab merge trains: no; turn them off on gated branches | no |

## 12. Agent sessions under managed settings

The gate decides at merge whatever the developer's machine allowed. A regulated organization also bounds the agent session itself. In a bounded session, the inner loop runs without prompts and cannot reach secrets, arbitrary hosts, or a bypass mode. For Claude Code, deploy [templates/claude/managed-settings.json](../templates/claude/managed-settings.json) as managed settings, which no user, project, or `--settings` value overrides.

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| A managed policy for Claude Code | yes | the template: `permissions.deny` for credential files (`~/.ssh`, `~/.aws/credentials`, `.env`) and arbitrary egress (`curl`, `wget`, `WebFetch`), `permissions.allow` for the inner loop (`aidd test`, `aidd gate`, `aidd validate`, `aidd assess`, `aidd list`, `aidd hash`, read-only git, the `aidd` MCP tools), `disableBypassPermissionsMode`, and `allowManagedPermissionRulesOnly` |
| Sandboxed shell with fixed egress | yes | `sandbox.enabled` with `failIfUnavailable` and `allowUnsandboxedCommands: false`; `network.allowedDomains` with `allowManagedDomainsOnly`, where you replace the placeholder with your package mirror; `sandbox.credentials` removes `GITHUB_TOKEN` and `GH_TOKEN` and hides `~/.aws/credentials` from sandboxed commands, and `filesystem.denyRead` hides `~/.ssh` |
| Only the organization's hooks and MCP servers | yes | `allowManagedHooksOnly`, with the aidd guard hook coming from the force-enabled plugin (a force-enabled plugin's hooks are exempt) and `env` setting `AIDD_HOOK_FAIL_CLOSED=1`, so the hook blocks every checked tool call when it cannot run (no Python 3.11, a crash of its launcher) instead of allowing it; and `allowManagedMcpServersOnly` with `allowedMcpServers` naming the `aidd mcp` server by its command, both the project server `aidd init` writes and the plugin's |
| Only the approved plugin marketplace | yes | `strictKnownMarketplaces` names the aidd marketplace (`thaithienvanid/aidd`); add your own marketplace beside it. `disableSideloadFlags` rejects `--plugin-dir`, `--plugin-url`, and `--agents`, which the allowlist does not cover |
| The same plugins on every machine | yes | `extraKnownMarketplaces` registers the aidd marketplace with `autoUpdate: false`, so the organization decides when a new version reaches machines, and `enabledPlugins` requires `aidd@aidd`; add `"aidd-team@aidd": true` for the delivery team. `pluginSuggestionMarketplaces` lets Claude Code suggest the plugins where the marketplace's `relevance` signals match. A force-enabled plugin's hooks are exempt from `allowManagedHooksOnly`, so the guard runs once, from the plugin, with no managed duplicate. A machine where the plugin failed to install has no guard; the gate still decides every merge |
| A floor on the Claude Code version | yes | `requiredMinimumVersion`, set to 2.1.259, a release whose settings reference documents every key the template uses; raise it on your schedule |
| `aidd doctor` checks the machine | partial | under profile regulated, it warns when it finds no managed settings file, drop-in, macOS MDM profile, Windows HKLM value, or server-managed cache; a claude.ai console policy that has never reached this machine is invisible to it, so confirm with `/status` in Claude Code |
| Other coding agents | no | the template is Claude Code's; other agents' managed policies are theirs to configure |
| A container with default-deny egress | partial | aidd does not sandbox. [templates/devcontainer/](../templates/devcontainer/devcontainer.json) (`aidd init --devcontainer`) is a starting point: a dev container whose firewall allows HTTPS and SSH only to the code platform, the model API host, and the package registries, baked into the image as build arguments; the agent runs as a non-root user that may run only the firewall script as root. DNS and the allowed hosts remain channels out, the list resolves once at start, and it is not tested against your network ([HOW-TO](HOW-TO.md#many-agents-at-once)) |

**Deploy it.** Remove the keys you do not want, replace the network placeholder, and deliver the same JSON by one of Claude Code's managed sources:

- **A file.** Save it as `managed-settings.json` in the system directory: `/Library/Application Support/ClaudeCode/` on macOS, `/etc/claude-code/` on Linux and WSL, `C:\Program Files\ClaudeCode\` on Windows. A team that owns part of the policy can add its own file in `managed-settings.d/` next to it. Use the tooling that already places files on the fleet.
- **MDM.** On macOS, a configuration profile for the `com.anthropic.claudecode` managed preferences domain (Jamf, Iru, Intune), with the same top-level keys. On Windows, the JSON as a `REG_SZ` value named `Settings` under `HKLM\SOFTWARE\Policies\ClaudeCode` (Intune, Group Policy). Anthropic keeps starter templates in the `examples/mdm` folder of the `anthropics/claude-code` repository.
- **The admin console.** Paste the JSON into server-managed settings in the claude.ai admin console; this is the only source that also reaches cloud sessions.

Then, on one machine, run `/status` in Claude Code: the `Setting sources` line names the managed source in force. Run `aidd doctor` in a regulated repository to check the machine too. Pair the template with deploy commands held for a person in the repository's config ([`[[guard.held_commands]]`](CONFIG.md#guard)). With that pairing, a production deploy waits for a person even inside an allowed session.

## 13. Multi-tenancy

One aidd engine serves many companies, or an agency's many clients, when each repository names its `tenant` ([CONFIG.md](CONFIG.md#top-level-keys)). What the engine does, and where it stops:

| Requirement | Status | Satisfied by, or what is missing |
| --- | --- | --- |
| A tenant per repository | yes | the top-level `tenant` key (lowercase letters, digits, and hyphens); an org preset sets it and may lock it (`locks = ["tenant"]`), and a child config cannot change a parent's tenant: a `config.warning`, and the parent's stands |
| Tenant on every artifact | yes | the gate record, every gate event (an `error` event carries the org preset's tenant), and the agent change record carry `tenant` ([schemas/record.schema.json](../schemas/record.schema.json), [schemas/event.schema.json](../schemas/event.schema.json)) |
| Tenant-scoped identities and approver pools | yes | an identity may be written `<tenant>:<login>` or `<tenant>:email:<address>`; an unqualified one belongs to the config's tenant. A pool entry of another tenant names nobody, and an approval by an identity of another tenant never counts (`spec_approval.other_tenant`, `merge_approval.other_tenant`, both warnings; the approval then stays missing) |
| Reports per tenant | yes | `aidd metrics --tenant T` and `aidd record export records\|events --tenant T` keep only that tenant's items; an item without a tenant belongs to none |
| Verification per tenant | yes | `aidd record verify <sha> --tenant T` refuses a change record of another tenant |
| One preset per tenant | yes | each company's org preset (`org-preset-url` with its sha256) carries its `tenant`, its approvers, and its locks; a repository cannot move itself to another tenant |
| Isolation of stored records | partial | the tenant is a label on files the platform stores (workflow artifacts, your log store). aidd keeps no store of its own, so separating one tenant's records from another's is the storage's access control, and `--tenant` only filters |
| Platform logins across tenants | partial | the GitHub and GitLab adapters report bare logins, which count as the config's own tenant: the scope holds only as far as an identity names its tenant. Keep each tenant's approvers in its own organization's teams |
| One repository, several tenants | no | a repository belongs to one tenant; split the work into one repository per tenant |

## Open items

| Item | Kind | Status |
| --- | --- | --- |
| Tag and publish 1.0.0; run the first live pull request through the gate | operational | the release criterion |
| A SLSA Source VSA per protected branch, derived from the change records | product | not built: the change record is aidd's own predicate, and no verification summary attestation is issued yet |
| Runbook page for a red gate and administrator bypass | documentation | partly in this page and [PLATFORMS.md](PLATFORMS.md) |
| Benchmark on a large monorepo | product | not started |
| GitHub merge queues exercised live; GitLab merge trains | validation, product | queues shipped, untested live; trains not started |
| Support newer MCP revisions in `aidd mcp`, which speaks <!-- aidd:gen mcp:revisions -->2025-06-18, 2025-03-26, and 2024-11-05<!-- aidd:end --> and answers a newer request with <!-- aidd:gen mcp:latest -->2025-06-18<!-- aidd:end --> | product | not built |
| Enterprise managed users and SAML team resolution, exercised | validation | not started |

Every path named on this page is checked by a test, so a renamed file cannot leave a stale claim.
