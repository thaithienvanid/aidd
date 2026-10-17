# Changelog

This file lists every notable change to aidd.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The method, the schemas, the gate, the CI templates, the skill, and the team plugin share one version. Every record carries `aidd_version`. [CONTRIBUTING.md](CONTRIBUTING.md#versioning) says what counts as a patch, a minor, or a major change.

## [1.0.0] - Unreleased

AIDD (AI-Driven Development) is a method for delivering software with AI agents: agents do the work, and humans decide what to build and what ships. aidd is the open-source toolkit that runs it. It is a command-line tool with no runtime dependencies, a CI check named `aidd/gate`, a skill that coding agents read, and an optional delivery team of agent roles. This is the first release, so everything below is new.

### Added

#### The method

- **One loop for every change**: Plan, Specify, Spec approval, Implement and Verify until green, Review, Merge approval, Ship, and Learn ([METHOD.md](docs/METHOD.md)). The person runs the outer loop, and the team runs the inner one. The loop is always on.
- **Four decisions stay a person's**: D1 the plan, D2 Spec approval, D3 the release, and D4 the launch. Spec approval binds a hash of the Spec, its tests, and its design. Merge approval binds the head commit.
- **Who decides what**: the person decides what is built and whether it ships, and the team decides how, on evidence. A table in METHOD §5.2 names each decision, who takes it, on what, and when it goes to a person. The session that runs the team, the lead, is never a second stakeholder.
- **Routes**: aidd sizes each change by what it touches, as `standard`, `minor`, `normal`, `major`, or `emergency`. The author may ask for more control, never less, and the gate computes the route again from the real diff. Four profiles, `solo`, `team`, `org`, and `audited`, set how strict the gate is.
- **The Spec** is the work item and the contract: the intent, the Acceptance, the scope, the tests, the risk, the rollback, and an observe window. `aidd revise <ID> "<why>"` reopens an approved Spec as a change order, and its next approval says why.
- **Maintain** is the same loop on a rhythm: `aidd list --upkeep` lists the upkeep that is due, and each item a person picks becomes its own change.

#### Decide once, in your own words

- **Typed words are the decision.** `approve SPEC-1`, `approve merge`, and `ship it` at the prompt record exactly what you named, before the model reads the prompt: in aidd-mods, or through aidd's own prompt hook. A yes in other words opens a dialog (MCP tools `approve_spec`, `approve_merge`, `ship`), and you click once.
- **No question twice.** A note says whether aidd recorded your words, and why not, with the fix. A Spec that is not ready is not offered to you. A typed `ship it` holds for the fix the gate or the reviewer asks for, while the Spec stays as approved, on a platform too. Each approval it covers names it, and `aidd ship` lists the commits you did not see.
- **Never blocked by a failing gate.** Your Merge approval is recorded whatever else fails, and the gate holds the merge until the team fixes it. On GitHub, `ship it` posts your approving review and turns on the pull request's auto-merge where the base branch requires `aidd/gate` (`aidd approve merge --auto-merge`).
- **Your account, found for you.** Where the Approvers are GitHub logins, aidd uses the signed-in `gh` account that is an Approver, whichever is active, and names it. With a wrong git email, the refusal gives the one-line fix.
- **Hands-off when you want it.** `approve all` is a standing approval: the agent records each Spec approval and release for you, and ships, until you type `stop approving`. `approve all but major` keeps major changes for you. The plan and every launch stay yours.
- **Local-first.** aidd needs only git. `aidd approve spec`, `aidd approve merge`, and `aidd ship` work at your own terminal, and `aidd ship` lands exactly the tree it tested. Where a platform's gate decides, aidd posts your approval on the pull request instead.

#### The gate and the guard

- **The gate** checks each change before it merges. `aidd gate` decides pass, pending, or fail from facts: new behavior fails on the base commit and passes on the head, the change stays in its approved scope, and the right humans approved it. Its rules answer five questions, generated from the rulebook.
- **The guard** checks each step an agent takes. It denies an edit outside the active Spec's scope, an edit of a frozen test, and an agent's command that approves, merges, or ships. It holds deploy commands until a person allows them.
- **Checks follow the branch.** The default branch gets the full gate, a goal branch moves only through `aidd integrate` and `aidd sync`, and a Spec or Task branch keeps each edit in scope ([METHOD §10.4](docs/METHOD.md#checks-by-branch)).
- **Explore branches** are free work: on `explore/<topic>` the guard allows every edit, and the gate fails any change from it (`explore.branch`) until it is renamed. Only a person starts one.
- **Specialists by content**: a risk rule's `content` patterns match the lines a diff adds, such as raw SQL or a model API call, and ask that specialist pool on any route.
- **Every stop says what to do next.** Each denial, gate finding, and `aidd validate` error says why and gives the next step, as a way that works where the person is. A test fails on a message with no step, or one that names a command or flag that does not exist.
- **Use only the parts you want.** `components` turns off the session hooks, the loop, or autopilot, one at a time, and `mode: advisory` stops the gate from blocking ([How-to](docs/HOW-TO.md#use-only-the-parts-you-want)).

#### Coding agents and platforms

- **Any coding agent.** The `aidd` skill is a self-contained Agent Skills folder. aidd supports <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> coding agents, such as Claude Code, Codex, Cursor, and Copilot, and `aidd init` wires the ones it finds. The guard runs in <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->: Codex, Antigravity, and Grok Build through their own hook files, with the session hooks, and OpenCode through a plugin. Each was checked against a live run of that harness.
- **MCP.** `aidd mcp` serves the checks and the decision dialogs as MCP tools. It speaks MCP 2026-07-28, and still answers a client that opens with `initialize` at 2025-11-25 or 2025-06-18.
- **Platforms.** On GitHub: a reusable gate workflow, a composite test action, a GitHub App as the status source, and merge-queue support. GitLab support is experimental. Any other CI builds a context file and runs `aidd gate --context`.
- **Setup.** `aidd init --dry-run` reads the repository first, `aidd init` writes the config, the skill, and the CI files with the gate in advisory mode, and `aidd doctor` checks the wiring. `aidd upgrade` keeps the files current, `aidd uninstall` reverses them, and the CLI keeps itself current ([Install](docs/INSTALL.md#updates)).

#### Plans, goals, and the flow

- **Big goals and small goals.** A big goal is an Initiative of small goals, Epics of two weeks or less. Each Epic says how it ships: `incremental` (each Spec merges by itself, the default), `flagged` (behind a flag until its `launch` Spec), or `batched` (a goal branch).
- **Goal branches.** `aidd goal open` cuts `goal/<EPIC>`, `aidd integrate` lands each verified Spec in it with no person asked, and `aidd sync` merges newer work in, never rebasing. `--undo` takes a Spec out, and the release to `main` is one decision ([METHOD §10.3](docs/METHOD.md#103-goals-big-small-and-how-each-ships)).
- **Trunk-based flow.** `aidd list`, `aidd goal list`, and `aidd doctor` show each open branch with its age, and warn past `gates.max_open_branches`, `gates.max_branch_days`, and `gates.max_goal_days` ([METHOD §10.4](docs/METHOD.md#104-trunk-based-flow)). A branch another open branch holds counts once, and a finished one costs no git call, so `aidd list` stays under a second with a hundred branches.
- **Worktrees.** `aidd worktrees` shows what each worktree holds and whether it merged, and `aidd worktrees clean` removes the merged ones after a person's yes. One dev stack serves them all (`project.dev_services`, `AIDD_WORKTREE`).

#### The delivery team

- **Agent roles led by humans.** The optional `aidd-team` plugin adds <!-- aidd:gen count:roles -->17<!-- aidd:end --> roles, from product manager to SRE, and <!-- aidd:gen count:commands -->19<!-- aidd:end --> commands, from `/aidd-team:plan` to `/aidd-team:maintain`. Each role writes only its own files and hands off through a file and a short note. The tester never builds the code, and the verifier wrote neither.
- **The team as your software company.** The team decides what a standard, the project's rules, or aidd's default settles, and lists each such decision with what settled it. You read them under "Decisions the team made" in `aidd digest` (`--client`: "What we decided for you") and on the Merge approval page. A request to any role that changes what you agreed becomes a change order ([ADOPTION.md](docs/ADOPTION.md#the-team-as-your-software-company)).
- **Client work.** The `delivery-manager` role qualifies client work, keeps the RAID log, and writes the contract with `aidd new contract`; where it is not installed, the product manager does its work (`fallback`). `/aidd-team:handover` hands a delivered system over for sign-off.
- **Perspectives before a plan.** A consult round asks the architect, the designer, the security engineer, and the `domain-expert` for a card each. The domain expert speaks for its domain pack and edits no file.
- **The ecosystem on demand.** `aidd extensions suggest` names the plugins that fit each role in this repository, each pinned with evidence, and the line a person runs to install it. aidd installs none.

#### Autopilot

- **The engine decides.** `aidd autopilot next` computes the one next action from git: run a team command, ask a person, or stop. `/aidd-team:autopilot` runs those actions between your decisions, and its stop message names each decision that waits and the command that goes on.
- **Bounded.** A run holds a lease on its work, with a timebox, token and cost caps, a circuit breaker per step, and a stall breaker across the run. In Claude Code, the token cap counts what the session's transcripts show, not what a step reports.
- **For runs nobody watches.** `autopilot.notify` runs a command once each time a run stops for you, read only from the base branch's config. A crashed session's lease is taken over after 20 quiet minutes, and `claude -p` runs it headless ([Autopilot](docs/AUTOPILOT.md#runs-nobody-watches)).
- **Side by side.** Independent Specs run in parallel worktrees (`autopilot.parallel`), and you approve the ready ones together.
- **A harness you can check.** `aidd doctor --autopilot` checks that the sandbox is on and prints every `permissions.allow` rule a run needs: the project's files, aidd, its read-only tools, and the team's flow files. A fix runs as one step of the run, under its lease.
- **Tried for real.** Six runs with real models, from a one-line fix to a new goal, each stopped at a person's decision or at a problem it reported. The four problems they found are fixed, each with a test ([Real runs](docs/AUTOPILOT.md#real-runs)).

#### Knowledge and documents

- **Domain packs and practice skills.** The roles read <!-- aidd:gen count:packs -->22<!-- aidd:end --> domain packs and <!-- aidd:gen count:practices -->32<!-- aidd:end --> practice skills. Each standard records its edition, its source, a quoted sentence, and a `checked` date, and `aidd eval standards` fails on one past its review.
- **Business domains.** Each business pack (payments, commerce, health, devices, the public sector, children, education, HR) names its terms and its invariants, which the domain expert checks a plan against.
- **The standards library and stacks.** A library standard fills one open choice, such as the linter, with exactly one default per ecosystem. `aidd standard add` and `aidd stack add` copy them into a project, with their tests.
- **Compliance and defaults.** The `enterprise-controls` pack maps each control to SOC 2, ISO/IEC 27001:2022, and GDPR, with the test or record that proves it. **Product defaults** (`project.defaults`) give every product light and dark themes, responsive layouts, security headers, and more; a person turns one off only with a reason.
- **Plain language.** The plain-language skill sets the writing level by reader: ste-80 inside the team, plain language (ISO 24495-1) for clients and users. aidd writes its own pages and messages at ste-80.
- **Design and proposals.** `aidd new design-spec --prototype` writes a design spec and an HTML prototype of a flow. `/aidd-team:explore` drafts two or three directions, and `aidd explore` renders one page that compares them. A proposal records its go or no-go and its sign-off by hash, and `aidd proposal convert` turns it into a plan.
- **A person's review of the registry.** `aidd eval standards` says how much of the library a person has reviewed, and `--unreviewed` lists what waits, the laws first. `aidd eval standards --due DAYS` lists the reviews coming due, spread over the cadence so they never fall due on one day.
- **Templates held to their standards**: the ADR (MADR 4.0.0), the SLO (the SRE Workbook), the threat table (the ICO's scale), the architecture overview (arc42), the runbook, and the contract.

#### Views, files, and proof

- **The status pane.** The optional `aidd-mods` plugin (Claude Code 2.1.295 or later) opens a side pane with no model turn. It leads with your next decision and the words to type, then the shape of the work, this branch, the flow, and the autopilot run.
- **Pages for decisions.** `aidd hash --html` writes the Spec approval page, and `aidd gate --html` the Merge approval page, behavior first. `aidd digest` is the weekly status, and `aidd list --waiting-on-me --html` lists what waits on you.
- **Files you can read.** Every file aidd reads or writes is YAML, read by its own strict parser so a value means the same everywhere. Everything about a work item sits in its folder (`specs/SPEC-12/`), and aidd's output for a worktree sits in `.aidd/<folder>/`, which git ignores.
- **Proof.** The conformance suite holds <!-- aidd:gen count:examples -->25<!-- aidd:end --> gate examples and <!-- aidd:gen count:mutations -->215<!-- aidd:end --> mutations, each pinned by a finding code; `aidd eval examples` replays them. `aidd eval routing` and `aidd eval roles` score an agent on <!-- aidd:gen count:routing-scenarios -->59<!-- aidd:end --> routing scenarios and <!-- aidd:gen count:role-scenarios -->21<!-- aidd:end --> role scenarios.
- **Output for tools.** `aidd validate --json` and `aidd doctor --json` print one JSON object each, to a schema in `schemas/`, like `aidd list` and `aidd gate`.
- **Why it is built this way.** `docs/adr/` records the design decisions behind 1.0.0 as short MADR records: the gate's evidence, the local decision records, standing approval and `ship it`, explore branches, autopilot, and who decides what.
- **Docs that stay current.** The JSON Schemas are the source, and `aidd gen-docs --check` fails on a stale table or count. A test fails on wording a change retired, and on a concept with no glossary row (CONTRIBUTING.md, "Keeping the docs current").

### Security

- **Updates you can trust.** `aidd self-update` installs only a release, never the tip of main unless you pass `--main`. It installs the release's wheel only once it matches the release's SHA256SUMS, and its build provenance with `gh`. The daily check says a release is out; it installs by itself only with `AIDD_AUTO_UPDATE=1`.

- **The trust model.** The gate job runs from the default branch, reads the change as git objects only, and never runs its code. The test job is untrusted: the platform token is stripped from its commands, and the evidence binds to the commit ([SECURITY.md](SECURITY.md)).
- **Pinned CI.** Every workflow pins each third-party action by commit SHA, and CodeQL, zizmor, actionlint, and OpenSSF Scorecard check the repository.
- **Provenance.** The release workflow verifies the tag signature, CI, and `aidd/gate` before it builds, attests build provenance and a CycloneDX SBOM, and publishes through PyPI trusted publishing.
- **Scanning for adopters.** `aidd init --security-ci` adds OSV-Scanner, Semgrep Community Edition, gitleaks, and an SBOM, each on a read-only token.
- **No telemetry.** SECURITY.md lists every place aidd connects, and a test fails on a network module missing from that list. `AIDD_OFFLINE=1` stops the network checks.
- **The guard fails closed where it must.** It denies a command it cannot read for a writer it holds. It blocks when it cannot run only where the project asks: the `audited` profile, or an organization's `AIDD_HOOK_FAIL_CLOSED=1`. It never writes to the user's settings.
- **The approvals ref stays a person's.** The guard denies every way it knows that an agent's command could write `refs/aidd/approvals` or move the base branch under a name it cannot read. Among them: a name the shell builds, a wildcard or brace refspec, and refs fed on stdin. Also a refspec set with `-c`, `--config-env`, `GIT_CONFIG_*`, an include, or a remote's stored config, a mirror remote, and a shell write into the git directory. A test runs each form in a real shell against a real repository, and fails when one writes and the guard allowed it.
- **Agents never pass for humans.** One rule decides whether an identity is an agent, and a lookalike name counts as one. Only a person starts an explore branch, and the guard denies an agent's attempt to type a decision into another terminal.

### Known limits

[RATIONALE.md](docs/RATIONALE.md#known-limits-in-100) lists every limit. These matter most in 1.0.0:

- Autopilot runs in Claude Code. It ran six times with real models before 1.0.0, on a small repository. Another agent runs its steps by hand with `aidd autopilot next`.
- Autopilot trusts the local machine: a local writer of git refs or `.git/config` is out of its scope, and the gate in CI is the control.
- The guard reaches only the writes it can read. A program that writes by itself, such as an interpreter or a build tool, is out of its reach, and the gate on the real diff is the control.
- The role evals were not run again with real models after the agent files changed, and aidd publishes no eval baselines.
- The gate has not yet judged a live pull request on GitHub or GitLab.
- Signing and publishing wait for a public repository.

[1.0.0]: https://github.com/thaithienvanid/aidd/releases/tag/v1.0.0
