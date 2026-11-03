# Changelog

This file lists every notable change to aidd.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The method, the schemas, the risk rules, the CI templates, the skill, and the team plugin share one version. Every config carries `aidd_version`. [CONTRIBUTING.md](CONTRIBUTING.md#versioning) says what counts as a patch, a minor, or a major change. An upgrade within a major version never turns an approved Spec's frozen test red ([the promise](CONTRIBUTING.md#frozen-tests)).

## [1.0.0] - Unreleased

AIDD, short for AI-Driven Development, is a method for delivering software with AI agents. Agents do the work and follow one loop, and you decide the risky steps. aidd is the open-source toolkit that runs it. It's a command-line tool with no runtime dependencies, a skill that coding agents read, an optional delivery team of agent roles, and a standards library. aidd advises and enforces nothing. This is the first release, so everything below is new.

### Added

#### The method and the loop

- **[One loop](docs/METHOD.md) for every change.** It runs Plan, Specify, Spec approval, Implement and Verify until green, Review, Merge approval, Merge, Roll out, and Learn. The team runs the work, and you decide at each ask. Retries are capped at 3 a Task, a flaky test is a finding, and red before green is the practice for new behavior.
- **Routes as advice.** `aidd risk --paths` sizes a change by what it touches, as `minor`, `normal`, `major`, or `emergency`. The route sets the lane: the fast lane with no Spec, the spec lane, or the emergency lane, which repairs production first and writes the Spec after. An area can raise the route, so an edit in `payments` makes the change major. The author may declare higher.
- **Profiles.** `solo` asks for Spec approval on major changes, and asks before anything reaches the default branch. `team` asks for Spec approval on normal and major changes, and leaves Merge approval to the platform's review: the agent opens the PR and stops there.
- **Spec approval, asked plainly.** The agent asks "Approve SPEC-3?" with what the Spec covers. On your yes, it sets the Spec's `status: approved`, `approved_by`, and `approved_at`, and commits it with an `Approved-by` trailer. After that, editing the Spec's tests or Acceptance is `spec.revise`, which asks you again and puts the Spec back to `draft`, with a `revisions` entry.
- **The Spec** is the work item and the contract, `type: spec` in its front matter, as each work item names its `type`. It holds the intent, its `change_type` (a Conventional Commits type), the Acceptance, the scope, the tests, the risk, the rollback, an observe window, and a cost estimate that `aidd validate` checks against the project's budget. Its status runs from `draft` to `ready`, `approved`, `in_progress`, `in_review`, and `done`, or `rolled_back` and `cancelled`.
- **Requirements a machine can check.** A business rule with three or more conditions becomes a decision table, with one Acceptance id per row. `aidd validate` warns about a word the glossary says to avoid.
- **Runbook readiness.** `aidd validate` warns about a linked runbook's unchecked launch-readiness boxes while its Spec is in review.
- **Deprecations.** A Spec's `deprecations` names what it deprecates and its sunset, and a passed sunset warns until a Spec that removes it lands.
- **Big goals and small goals.** A big goal is an Initiative of small goals, Epics of two weeks or less, each with its Specs.
- **Headless runs stop at an ask.** In CI, a cloud session, or a scheduled run, an `ask` means stop and hand back with a handoff note, because silence is never a yes.
- **The loop fits the work to its reason.** A major change gets a tech spec, a threat model when it touches security, privacy, or data, and a rollout plan. A minor change gets none of them.

#### Risk rules

- **Actions, areas, and levels.** An agent acts by a risk rule's level: `allow` acts, `report` acts and then says what it did, and `ask` waits for your yes. Each action is `resource.verb`, such as `pr.open`, `git.push.force`, or `deploy.run`, with its command patterns and examples that no pattern catches. An area is a named set of path globs, such as `auth`, `payments`, or `personal_data`.
- **Modelled on authorization.** The rules borrow the shape and names of Cedar, Google Cloud IAM, and Kubernetes RBAC, with no engine of their own. A rule names an action, and optionally an area, a branch (`own`, `default`, or `shared`), and a role. The most specific rule that matches wins, then the higher level.
- **Built-in rules you can read.** `schemas/risks.json` holds the built-in actions, the areas, and the rules between them. Editing code is `allow`, and `ask` in `auth`, `payments`, `personal_data`, `secrets`, and `migrations`. Pushing your own branch is `allow`, and pushing to the default or a shared branch is `ask`. Force pushes, history rewrites, tags, merges, deploys, releases, migrations, production data, secrets, messages, and spending money all ask.
- **Your own rules.** The config's `risks` adds areas, actions, and rules, and a rule with a built-in's selector replaces it, so a project can lower a level as well as raise it. An `extends` preset can lock a rule, and `aidd risk` then reports a project's change to it as ignored.
- **One answer for every question.** `aidd risk --paths` gives the route, the lane, the areas hit, and the first step. `aidd risk --command "<cmd>"` gives the actions a command matches and the winning level, `aidd risk --action` gives one action's level, and `aidd risk --list` shows every effective rule and where it came from.
- **Session overrides.** You may lower a rule for one session, such as "don't ask about pushes today". It lasts the session, and goes into the config only when you say so.

#### Every coding agent

- **Any coding agent.** The `aidd` skill is a self-contained Agent Skills folder. aidd supports <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> coding agents, such as Claude Code, Codex, Cursor, and Copilot, and `aidd init` wires the ones it finds.
- **The harness's own ask rules.** `aidd init` and `aidd upgrade` write each `ask` rule's commands as the harness's own ask rules, in the format its documentation gives. Nine harnesses get them: Claude Code, OpenCode, Codex, Grok Build, Qwen Code, Devin's CLI, Factory Droid, Augment's CLI, and VS Code's agent. A test checks that all nine ask for the same commands. aidd changes only the entries it listed in `.aidd/harness-rules.json`, never yours, and never puts an ask where it would undo your deny. A harness without ask rules gets the skill alone, and `aidd doctor` says so.
- **The team's flows in every harness that reads skills.** With `--team`, every agent that loads skills from `.agents/skills/` gets the flows there, and each role's file in `.aidd/team/roles/` for its lead to hand a subagent.
- **The `aidd-cli` plugin.** It puts the `aidd` command on the PATH of Claude Code's Bash tool, so nothing else needs installing.
- **MCP.** `aidd mcp` serves three tools that only read: `risk`, `status`, and `validate`.
- **Setup.** `aidd init --dry-run` reads the repository first. `aidd init` writes the config, the block in `AGENTS.md`, the skill, the harness ask rules, and, with `--team` and `--ci`, the team and the CI test workflow. Run again, it adds only what's new, such as another agent with `--harness`. `aidd doctor` checks the wiring, `aidd upgrade` keeps the files current, and `aidd uninstall` reverses them.
- **From GitHub only.** aidd is not on PyPI, so a package named `aidd` there is not this one. `install.sh` installs a release's wheel from its GitHub Release. It installs once the wheel matches the release's `SHA256SUMS` and, with `gh` on PATH, once its build provenance verifies. `AIDD_RELEASE_URL` points it at a mirror of the releases, which also needs `AIDD_SHA256` or `gh`, because a mirror's `SHA256SUMS` proves nothing alone.

#### Commands

- **17 commands, in three groups.** Setup is `init`, `upgrade`, `self-update`, `uninstall`, `doctor`, and `standard`. Work is `status`, `risk`, `new`, `test`, `validate`, `explore`, and `prototype`. Maintainers have `eval`, `gen-docs`, `mcp`, and `help`.
- **Short help first.** `aidd --help` lists only the everyday commands: `status`, `risk`, `new`, and `test`. `aidd help --all` lists every command by group, and `aidd help <command>` shows one in full.
- **`aidd status`** lists the open work: each Spec and work item, its status, and its next step, with `--mine` and `--json`.
- **`aidd test`** runs the project's tests, green on the head and red on the base for new behavior, and writes the evidence: each exit code bound to the head commit. It records when it ran in a tree with changes the repository's `.gitignore` files don't ignore. `--changed` runs only what changed, and `--watch` runs again on each save.
- **`aidd new`** writes a Spec, an Epic, an Initiative, a Proposal, an exploration, or a linked doc, from an ADR to a runbook.
- **Exit codes you can script.** 0 is ok, 1 is a check that failed (`test`, `validate`, `doctor`), and 2 is an error. Every stop names its next step, and a crash says it's a bug in aidd, with `AIDD_DEBUG=1` to print the traceback.

#### The delivery team

- **Agent roles led by humans.** The optional `aidd-team` plugin adds <!-- aidd:gen count:roles -->13<!-- aidd:end --> roles, from product manager to SRE, and <!-- aidd:gen count:commands -->19<!-- aidd:end --> commands, from `/aidd-team:plan` to `/aidd-team:maintain`. `/aidd-team:autopilot` runs the loop and stops at each ask.
- **One developer for every code Task.** The developer builds AI features and data work too, and the Task's `skills` load the specialty: `ai-evals`, `ai-features`, `schema-migration`, or a data pack.
- **Client work.** The `delivery-manager` role qualifies client work, keeps the RAID log, and writes the contract. Where it isn't installed, the product manager does its work as the `fallback`. `/aidd-team:handover` hands a delivered system over for sign-off.
- **Perspectives before a plan.** A consult round asks the architect, the designer, the security engineer, and the `domain-expert` for a card each. The domain expert speaks for its domain pack and edits no file.
- **Role placement.** The lead of each team command places each role: it plays the role for a small step of its own work, or starts it when it checks the work, runs cheaper, or works in parallel.
- **Each role keeps its product-level work.** The team registry says which of a change's documents feeds which product-level work, such as the architecture overview or the product prototype. When a change feeds one and leaves it as it was, `aidd validate` warns, so the same change brings it in line.
- **Verify and Review side by side.** Once a head is green, the verifier and the reviewer check that head. A failure in either returns to Implement, and a new head needs both again.
- **Security findings with a shape.** A security finding names who attacks, the input they control, the control it gets past, the boundary, the impact, and the proof, or it's a hardening note with no severity. Severity follows the impact shown.
- **Worked examples for judgment.** The reviewer's code-review skill and the security engineer's threat-model skill each carry contrast pairs: a weak finding or threat entry, a strong one, and the line between them.
- **A `context` practice skill.** Every role reads by path, never re-reads what it has, and ends with the handoff note.
- **Each role thinks as hard as its tier asks.** In Claude Code, a reasoning role runs at `xhigh` effort and an execution role at `high`. `agents.effort` sets any level per tier or role.

#### Design and prototypes

- **The whole product, clickable.** `aidd new product-prototype` starts the designer's living prototype in `docs/design/app/`. `sitemap.json` defines the navigation once, so every screen shows the same items in the same order. `aidd prototype` assembles it into one page and checks it.
- **One prototype viewer, like a design tool.** A Spec's prototype and the whole product open in the same workspace. It has device frames for the web, iOS, and Android, a review column that opens the next unseen state, and a Board that shows every screen in every state.
- **The prototype tool, aidd-team's own.** The viewer, the checks, and the component contract live in `plugins/aidd-team/tools/prototype/`, one standard-library file that runs without aidd. `aidd prototype --check <file>` names each problem with its line, and holds a design to the rules of the format it names.
- **The product designer checks the finish.** Its fidelity pass reads a screenshot of every state at three widths, in both themes, at 200% text and right to left. The pass is sized to the change.
- **Components named once, built once.** The designer names each reusable part with `data-component` and `data-variant`. `aidd prototype --components` prints the component contract, and `aidd prototype --stories storybook-static/index.json` fails when a variant has no story under its name.
- **Explorations.** `/aidd-team:explore` drafts two or three directions, and `aidd explore` renders one page that compares them.

#### Knowledge and standards

- **Domain packs and practice skills.** The roles read <!-- aidd:gen count:packs -->25<!-- aidd:end --> domain packs and <!-- aidd:gen count:practices -->36<!-- aidd:end --> practice skills. Each standard records its source, its edition where it has one, and a `checked` or `reviewed` date. `aidd eval standards` fails on an entry past its review.
- **Business domains.** Each business pack names its terms and its invariants, which the domain expert checks a plan against.
- **The standards library and stacks.** A library standard fills one open choice, such as the linter, with exactly one default per ecosystem. `aidd standard add`, for one standard or a `--stack`, copies them into a project, with their tests. Each standard runs its tool from the project's own lockfile.
- **Compliance and defaults.** The `enterprise-controls` pack maps each control to SOC 2, ISO/IEC 27001:2022, and GDPR, with the test or record that proves it. Product defaults, set in `project.defaults`, give every product light and dark themes, responsive layouts, security headers, and more.
- **Laws by their dates.** The packs carry the EU Cyber Resilience Act's reporting duty, which has applied since 2026-09-11, the EU Data Act, and the US rules on automated decisions.
- **The `cra` target.** It needs a declared support period, and `aidd validate` fails without one. `aidd new vulnerability-policy` writes the policy on ISO/IEC 29147 and 30111, and `aidd doctor` checks `security.txt` and its `Expires`.
- **Plain language.** The plain-language skill sets the writing level by what the text does, with ste-80 for steps and rules and ISO 24495-1 for text clients and users read. A test holds every page of aidd's own docs to it.
- **Templates held to their standards.** The ADR follows MADR 4.0.0, the SLO the SRE Workbook, the threat table the ICO's scale, and the architecture overview arc42.

#### Files and proof

- **Files you can read.** Every file aidd reads is Markdown with YAML front matter, or YAML, read by its own strict parser. aidd's output for a worktree sits in `.aidd/evidence/` and `.aidd/views/`, which git ignores. `aidd validate --json` and `aidd doctor --json` give the same answers to a program.
- **Agent evals.** `aidd eval routing` and `aidd eval roles` score an agent on routing scenarios and role scenarios, run by hand with the agent you name.
- **Docs that stay current.** The JSON Schemas and `schemas/risks.json` are the source, and `aidd gen-docs --check` fails on a stale table or count. A test fails on a concept with no glossary row.

### Security

- **aidd enforces nothing, and says so.** The hard stops are the harness's own ask rules and the platform's branch protection. A command pattern is a net, not a control, as [SECURITY.md](SECURITY.md) explains.
- **Text is data.** The skill tells every agent that a ticket, a page, a file, a comment, or another agent saying "approved" is never a yes. Only your own words in the chat are.
- **A launcher that trusts nothing in the project.** The aidd plugin starts its MCP server with Python in isolated mode, from outside the project, and refuses to start when the plugin's source lies inside the project.
- **Updates you can trust.** `aidd self-update` installs only a release, never the tip of main unless you pass `--main`, and only once the wheel matches the release's `SHA256SUMS` and, with `gh` on PATH, its build provenance. The daily check only says a release is out.
- **Pinned CI and provenance.** Every workflow pins each third-party action by commit SHA, and CodeQL, zizmor, actionlint, and OpenSSF Scorecard check the repository. The release workflow verifies the tag signature and CI before it builds, and attests build provenance and a CycloneDX SBOM.
- **Releases you can rebuild.** The release builds every artifact again on a fresh runner, and stops unless each matches `SHA256SUMS`.
- **Scanning for adopters.** The CI templates add OSV-Scanner, Semgrep Community Edition, gitleaks, and an SBOM, each on a read-only token.
- **No telemetry.** SECURITY.md lists every place aidd connects, and a test fails on a network module missing from that list. `AIDD_OFFLINE=1` stops the optional network calls.

### Known limits

- aidd advises. An agent that ignores the skill acts on its own, and only the harness's ask rules and the platform's branch protection stop it.
- A command pattern matches the command text. A script, an alias, or an API call can reach the same effect without a match.
- A Spec approval is a note the agent wrote, not proof. Under `team`, the platform's review is the Merge approval.
- A harness without ask rules gets the skill alone.
- The role evals weren't run again with real models after the agent files changed, and aidd publishes no eval baselines.
- Signing and publishing a release wait for a public repository.

[1.0.0]: https://github.com/thaithienvanid/aidd/releases/tag/v1.0.0
