# Adoption playbook

Start with one repository, the smallest unit that has a merge gate. Grow by choosing a stricter profile and by sharing one org preset, not by forking the method.

| You are | Start with | First week |
| --- | --- | --- |
| [one developer](#individual-solo) | `aidd init --profile solo --approvers email:you@example.com @you --enforce` | enforce from day one |
| [one developer with no platform yet](#local-first-no-github-or-gitlab) | `aidd init --profile solo --approvers email:you@example.com --ci none` | approve at your own terminal |
| [a team](#team) | `aidd init --profile team --approvers @org/leads` | advisory, then enforce |
| [an organization](#organization) | a shared organization config (preset) and the shared gate workflow | 3 pilot repositories |
| [a regulated organization](#regulated) | `profile = "regulated"` in the preset | pilot with your auditors |
| [many companies](#many-companies) | one preset per company, the method shared | each company adopts on its own |

## Contents

- [Adoption levels](#adoption-levels): from the method alone to an enforced gate
- [New or existing repository](#new-or-existing-repository)
- [Bring the delivery team to a project](#bring-the-delivery-team-to-a-project)
- [Coming from Spec Kit, OpenSpec, Kiro, or BMAD](#coming-from-spec-kit-openspec-kiro-or-bmad)
- [Local-first: no GitHub or GitLab](#local-first-no-github-or-gitlab)
- [Individual (solo)](#individual-solo), and [a solo day](#a-solo-day)
- [Team](#team): the three-week rollout, [two or three people](#a-small-team-two-or-three-people), and [five to nine people](#a-medium-team-five-to-nine-people)
- [New teammate](#new-teammate): the first week on a team that uses aidd
- [Multiplayer: one team, humans and agents](#multiplayer-one-team-humans-and-agents)
- [Domain experts as specialist Approvers](#domain-experts-as-specialist-approvers)
- [Project constraints and rules](#project-constraints-and-rules)
- [Proposals: bids and internal cases](#proposals-bids-and-internal-cases)
- [Organization](#organization): many teams and repositories
- [Compliance-ready by default](#compliance-ready-by-default)
- [Regulated](#regulated)
- [Many companies](#many-companies)
- [Reading the metrics](#reading-the-metrics)

## Adoption levels

Each level adds to the one before it.

| Level | You add | You get | Not guaranteed |
| --- | --- | --- | --- |
| **1. Method** | the `aidd` skill and `AGENTS.md` | instructions that tell agents to follow the loop | anything: nothing is checked |
| **2. Team** | the `aidd-team` roles | roles, handoffs, and standards | anything: nothing is checked |
| **3. Local checks** | the CLI and the agent hook | the route, the guard on scope, red-then-green tests with `aidd test`, and local approvals (`aidd approve`, `aidd ship`) | a merge outside `aidd ship`: a person's own git commands, or an agent with no hook |
| **4. Advisory gate** | the CI check in advisory mode, the default after `aidd init` | a report on every PR/MR, and `aidd metrics` | any block: the gate blocks nothing |
| **5. Enforced gate** | `mode = "enforce"`, and a required `aidd/gate` check pinned to the gate's App ([Platforms](PLATFORMS.md#setup)) | a change merges only with proof and approval | control over an actor on the ruleset's bypass list ([rulesets](PLATFORMS.md#github-rulesets-and-aidd)) |

A team may stay at any level. Levels 1 to 3 are guidance, not control. The gate turns that guidance into proof. `aidd init --ci none` writes no CI files, so it stops at level 3. The [three-week rollout](#roll-it-out-in-three-weeks) moves a team from level 4 to level 5.

## New or existing repository

Both work; only the first days differ.

| Topic | Greenfield (new repository) | Brownfield (existing codebase) |
| --- | --- | --- |
| Setup | `aidd init` in the empty repository; commit the setup and the project scaffold straight to the default branch (Day 0), then require `aidd/gate` | `aidd init` in a setup PR/MR that an administrator merges, then advisory mode, then enforce |
| Tests | the first Spec brings the test runner and the first test; add the suite to `[[tests]]` once it exists | put the existing suite in `[[tests]]`; a characterization test (one that pins today's behavior) where code is untested |
| Risk map | the baseline rules fit most stacks; add rules as sensitive areas appear | add `risk_rules`, `owners.paths`, and `budget_exclude_paths` for the real layout |
| Planning | an Initiative and Epics hold the product intent; each Spec is a slice small enough for one review | Specs per change; Epics only for multi-Spec work |
| Watch for | early churn in dependencies and CI routes normal or major: batch toolchain setup into Day 0 | legacy code outside `scope`: leave it, and give cleanups their own Spec |

The skill's [`references/scale.md`](../.agents/skills/aidd/references/scale.md) has the Greenfield and Brownfield modules agents follow.

## Bring the delivery team to a project

The same four steps work for any repository; the table after them covers the situations that change a step.

1. **Look first.** `aidd init --dry-run` reads the repository and writes nothing. It finds:

   - the stacks and their test commands (one per package in a monorepo)
   - sensitive areas the baseline rules miss
   - generated and vendored code, CODEOWNERS, and existing CI
   - code with no tests beside it
   - the agent instructions and planning tools already there
   - deploy and infrastructure commands, which `aidd init` holds for a person

   It prints the config it proposes. It also reads the dependencies your manifests declare, which name the domain packs. It reports a declared auth, payment, or migration library with the baseline rule that watches it. The reason: that rule also fires when a change adds such a library, wherever its code sits.
2. **Set up in one change.** `aidd init --team` (or `--claude-plugins` to install the Claude Code plugins for your user instead of repository files). It uses the detected test command unless you pass `--test`; merge the rest of the proposal after review. The change touches `.aidd/`, so the gate treats it as major, and the gate starts advisory.
3. **Onboard the team.** `/aidd-team:onboard`: the architect, the security engineer, and the SRE map the codebase read-only and return one brief. The brief gives the config corrections, the architecture overview to add first, the areas that need a characterization test, and three small first changes.
4. **Work, and ask what is next.** Small first changes prove the loop here; `aidd list` tells anyone the next step and who holds it. Enforce once the gate's findings match the team's judgment.

| Situation | What changes |
| --- | --- |
| New, empty repository | Commit the setup and the scaffold straight to the default branch as Day 0; the first Spec brings the test runner ([New or existing repository](#new-or-existing-repository)). |
| Existing repository with tests | The detected suite goes into `[[tests]]`; the gate stays advisory until its findings match yours. |
| Existing repository with thin or no tests | Each change to untested code brings a characterization test first; the dry run lists where. Legacy code outside a Task's scope stays as it is. |
| Monorepo | One `[[tests]]` entry per package with `when_changed`, `[[owners.paths]]` or CODEOWNERS for each area's approvers, and the team works per package ([FAQ](FAQ.md#does-it-work-in-a-monorepo)). |
| One project in several repositories | Run `aidd init` in each. Keep Proposals, Initiatives, and Epics in one planning repository, and each Spec in the repository it changes. Each Spec names its Epic in `parent` and shares a `trace_id` with its siblings. Each repository gates its own change. `aidd list api web infra` shows the next step in all of them. |
| Many repositories in one organization | An org preset every repository inherits and cannot loosen, the aidd plugins required by managed settings, and rollout in waves, advisory first ([Organization](#organization)). |
| A client's repository (an agency, a contractor) | The client's people are the Approvers, and your agents are bots in `identities.bots`. The client's org preset applies, with the client's `tenant`. Your own people approve there only if the client's pools name them, and an identity you qualify with your own tenant never counts. Use repository files rather than your own plugins if the client restricts them, and keep your proposals for that client in your own private repository. |
| Open source with outside contributors | Pull requests from forks get no secrets: the gate App still judges them, and a maintainer re-runs agent evals. Bots' dependency updates can be standard changes. |
| Another platform (Bitbucket, Azure DevOps, Gerrit) or no CI yet | Run `aidd gate` against a `context.json` your CI builds ([Any other CI](PLATFORMS.md#any-other-ci)); with no CI at all, the gate runs locally as a preflight until one exists. |
| A mix of coding agents on the team | Every agent reads `AGENTS.md` and the skill; the roles are native agents in Claude Code, Codex, Copilot, OpenCode, and Kiro, and advisory elsewhere. Each role can run on a different model ([TEAM.md](TEAM.md#mixing-harnesses-and-models)). |
| Its own agent instructions or planning tool already | `aidd init` keeps them and adds a pointer; Spec Kit, OpenSpec, Kiro, or BMAD keep planning, and aidd gates ([Coming from Spec Kit, OpenSpec, Kiro, or BMAD](#coming-from-spec-kit-openspec-kiro-or-bmad)). |
| Only one team in a shared repository adopts | The gate is per repository, so stay advisory until every owner agrees, and meanwhile use `[[owners.paths]]` and risk rules for the adopting area. Opting in per directory is not supported. |
| A maintenance-only or legacy service | aidd without the team is often enough: dependency updates as standard changes, fixes on the fast lane, and the emergency lane for incidents. |
| Regulated work | The `regulated` profile, the managed-settings template, and the controls in [Enterprise readiness](ENTERPRISE.md). |
| A very large repository | The dry run stops after twenty thousand files and says so; the gate's speed on very large monorepos is not benchmarked ([Enterprise readiness](ENTERPRISE.md)). |
| The team leaves the project | `aidd uninstall` lists what it would remove and keeps what you changed; the Specs, records, and history stay. |

## Coming from Spec Kit, OpenSpec, Kiro, or BMAD

Keep the planning tool you like. These tools help an agent **plan** a change; aidd **controls** it. aidd checks the plan's risk against the real diff, freezes the tests at Spec approval, and proves them red then green on the exact commit. It also records two human approvals that the agent cannot give itself. The two jobs fit together:

1. Plan in your tool as today.
2. Draft the aidd Spec from the plan with `aidd import <tool> <path>` (below). The Spec is short: it quotes the plan's problem in Intent and links every file it read instead of copying them.
3. Name the tests and write them, fill the rollback, get Spec approval, and build. From here aidd's loop runs as usual.

What `aidd import` writes, in `specs/SPEC-<n>.md` (or `--id`, `--out`):

- **Acceptance:** each acceptance scenario, EARS requirement, or acceptance criterion gets an id (`A1`, `A2`, ...).
- **Tasks:** one per task group in the plan that names file paths, with those paths as its `scope`. When the plan names no path, the Task keeps the template's TODO scope.
- **Route:** computed from those paths the way `aidd new spec --paths` does, never below normal.
- **Tests:** left as TODO, with a comment naming any test file the plan mentions. A plan's tests are not assumed to exist or to prove the Acceptance.

`aidd validate` flags every TODO until a person fills it.

| Your tool writes | Run | It becomes, in the aidd Spec |
| --- | --- | --- |
| **GitHub Spec Kit**: `specs/<NNN-feature>/spec.md`, `plan.md`, `tasks.md` | `aidd import speckit specs/001-photo-albums` | The `**Input**` user description becomes Intent; each **Given/When/Then** acceptance scenario an Acceptance item (the `FR-###` requirements when there are none). `plan.md`'s Summary becomes the Design pointer, and each `## Phase` of `tasks.md` a Task. Both live under `specs/`; only files with `+++` front matter are aidd objects. |
| **OpenSpec**: `openspec/changes/<change>/proposal.md`, `design.md`, `tasks.md`, spec deltas | `aidd import openspec openspec/changes/add-dark-mode` | `proposal.md`'s Why becomes Intent; each `#### Scenario` of an ADDED or MODIFIED requirement in the deltas an Acceptance item; `design.md` the Design pointer; each `## N.` group of `tasks.md` a Task. |
| **Kiro**: `.kiro/specs/<feature>/requirements.md` (or `bugfix.md`), `design.md`, `tasks.md` | `aidd import kiro .kiro/specs/user-auth` | The introduction becomes Intent; each EARS requirement ("WHEN … THE SYSTEM SHALL …") an Acceptance item, one for one; `design.md` the Design pointer; each top-level task a Task. A bugfix spec is type `fix`, with the expected and unchanged behavior as its Acceptance. |
| **BMAD**: a PRD, an architecture document, and story files | `aidd import bmad _bmad-output/implementation-artifacts/1-2-password-reset.md` | One story becomes one Spec: its Story becomes Intent, its Acceptance Criteria the Acceptance, each top-level task a Task. The PRD belongs in an Initiative or Epic, the architecture in a decision record. |

The formats were checked on 2026-09-28 against Spec Kit 1.0, OpenSpec 1.13, the Kiro documentation, and BMAD 6.12. A newer layout the importer cannot read gives a Spec with more TODOs, never a wrong one: it only copies what it finds.

**Which to pick if you have none.** Start with aidd alone: its Spec already holds intent, design, Tasks, and tests. Add **Spec Kit** if you want a separate, richer planning step. It is the best-known option and sits beside aidd without overlap. **OpenSpec** suits long-lived systems where you track how each capability's spec changes over time. **Kiro** is a good fit if your team already works in its editor.

**BMAD: one team of roles at a time.** BMAD brings its own agent roles (analyst, product manager, architect, developer, QA, and others), and so does the aidd delivery team. Running both gives agents two sets of instructions for the same job. Use BMAD's planning documents if you have them, as above, and let one set of roles do the work. aidd's gate works either way, since it checks the diff and the evidence, not which roles produced them.

## Local-first: no GitHub or GitLab

The loop runs locally, with the same two decisions, for:

- a solo founder who does not code
- a team that keeps work on one machine and pushes later
- a prototype that is not on a platform yet

This section is the one place the setup is spelled out; other pages link here.

1. Set up with the email that your git commits use. Commit the setup on `main` yourself (Day 0, the one change that lands without `aidd ship`):

   ```sh
   aidd init --profile solo --approvers email:you@example.com --ci none
   git add -A && git commit -m "chore: adopt aidd"
   ```

   A local approval is recorded as `email:<git user.email>`, so that is the approver to list: `aidd approve` refuses, and `aidd doctor` warns, when it is not. With no test command found, `aidd init` binds a smoke test in this commit, so the first change has a suite to pass. The detected sensitive areas become `[[risk_rules]]`, and `.env*` goes into `.gitignore`.

2. Your agent works on a branch as usual: it checks the route with `aidd assess`, writes the Spec and its tests, and stops. You read the Spec and run `aidd approve spec specs/<ID>.md` at your own terminal. It shows the Spec's title, its Acceptance, and its hash before the code. Under solo, the gate requires Spec approval only on a major change. But approving a Spec before any code is still the cheapest place to catch a wrong plan. Once recorded, the approval binds: a changed Spec or test fails the gate, and red-then-green is required for that Spec. `aidd assess` and `aidd list` then show the Spec as ready.
3. The agent implements and runs `aidd test`; `aidd gate` tells you when it is ready: it then waits only on Merge approval. In the Spec phase, while the branch holds only the Spec and its tests, `aidd test` exits 0 with the failing tests marked as expected. In that phase, the gate leads with Spec approval.
4. You read the agent's report and run `aidd ship`. It shows the gate's report and the diffstat before the code. It checks the change's declaration first: the config, the block, the route, the scope, and the budget. When that fails, it stops before any test. Then it runs the tests on exactly what will land. When only your Merge approval is missing, the one code you type records it and ships. `aidd approve merge` stays for approving without merging. It shows the digest, the diffstat, and the gate's state first, and refuses while another rule fails. `--squash` makes one commit that keeps every agent's `Assisted-by` trailer, so you can keep the work local and tidy and push it later.

**The fast lane locally.** With no PR/MR, there is no description to hold the Change Request block. `aidd describe --commit` records it in an empty commit on the branch, which moves the head. So the order is describe, test, ship: `aidd describe --commit`, then `aidd test`, then `aidd ship`. `aidd describe --commit` takes the type from the newest Conventional Commit subject, such as `fix(cart): ...`. `aidd test`, `aidd gate`, and `aidd ship` read the newest such commit; `--body-file` on `aidd gate` and `aidd ship` overrides it. A Spec branch needs none: its Spec is found in the diff.

**When `main` moved.** If `main` moved since the branch left it, `aidd ship` merges the head into the new tip in a temporary worktree (`git merge-tree`). It runs the tests there and lands exactly that tree: the merge commit it tested, or, with `--squash`, one commit with that tree. A conflict ships nothing: merge or rebase `main` into the branch yourself, and approve the new head. A Merge approval you gave before a rebase still counts when the rebase was trivial ([PLATFORMS.md](PLATFORMS.md#approvals-across-rebases)).

`aidd approve spec`, `aidd approve merge`, and `aidd ship` each show a six-character one-time code and continue only when you type it back. They refuse to run without an interactive terminal, or in a shell that an agent started (one where `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT` is set). So run them in a terminal that you opened yourself.

What else to know:

- **The base branch is the gate's.** With no platform, the agent hook denies an agent any git command that lands work on `main`. `aidd init --harness claude-code` wires the hook for Claude Code; an agent with no hook is not stopped. The hook denies a merge, commit, cherry-pick, revert, rebase, or reset there, a push to it, `git branch -f main`, or `git update-ref refs/heads/main` (following `git checkout main &&` in the same command). Only `aidd ship`, which a person runs, moves it. A person's own git commands are theirs.
- **The cool-off.** A major change waits 30 minutes after its head commit before your approval counts; locally it is a reminder, not a control ([METHOD.md §8](METHOD.md#local-approvals)). `aidd ship --skip-cooloff` skips it, and the gate record names you.
- **Parallel work** fits in git worktrees, one per Task or per agent. Each keeps its own files and evidence, and the approvals, kept on a ref, are shared by all of them.
- **Signing.** Set up git commit signing with an SSH key that asks for your presence. List each Approver's public key in `.aidd/allowed_signers` on the base branch, and set `gates.local_approvals = "signed"`. Then only approvals signed by a listed key count, whatever this machine's git config says. The limits of a local approval are in [METHOD.md §8](METHOD.md#local-approvals).
- **Going online.** When the work starts to matter to other people, push it to a platform and let its reviews take over. Once the repository has a remote and a CI gate (`aidd init --ci github` or `gitlab`), the local `aidd gate` is a preflight. Its hints name the platform's steps (post the approval line on the PR/MR), because the platform's `aidd/gate` decides.

## Individual (solo)

**Goal:** agents move fast without shipping unproven or out-of-scope changes.

1. `aidd init --profile solo --approvers email:you@example.com @you --enforce --test "<your test command>"`, merge it, and require `aidd/gate` ([Platforms](PLATFORMS.md#setup)); try the loop locally first with the [Quickstart](QUICKSTART.md).
2. If you have no tests, write one characterization test first ([METHOD.md §10](METHOD.md#10-scale-modules)).
3. Write a Spec for anything above minor, so the tests exist before the code. The gate asks for Spec approval on major changes only.
4. You are the only Approver, so the gate asks for an explicit second look instead of a second person. Approve a major Spec yourself with `/aidd approve-spec ID HASH COMMIT`, and approve every merge with `/aidd approve-merge <full head SHA>`. A major change waits 30 minutes after the platform first sees its head commit before your approval counts. The solo rules: [METHOD.md §8](METHOD.md#solo).

**Done when:** every merge in the last two weeks passed the gate, and none needed a revert.

### A solo day

One founder, one agent, no platform. The commands you type are yours; the agent runs the rest.

**Morning: pick the work.** `aidd list` shows every open piece of work and who holds it. Describe the next change to the agent; it checks the route (`aidd assess --paths`) before the first edit.

**A small fix (fast lane).** The agent works on a branch, commits, runs `aidd describe --commit`, then `aidd test`, and stops. You read its report and run `aidd ship`. It runs the tests again on what will land and shows the report and the diffstat. Then one code records your Merge approval and merges into `main`.

**A feature (spec lane).** The agent writes the Spec and its failing test and stops. You read them and run `aidd approve spec specs/<ID>.md`. From then on the Spec and its test are frozen, and the test must fail before the code and pass after it. The agent implements, runs `aidd test` and `aidd gate`, and stops again; you run `aidd ship`.

**A risky change (major).** Authentication, migrations, secrets, and your aidd config are major, and so may be what your risk rules name. The Spec needs your approval, and your Merge approval counts 30 minutes after the head commit. Take the break, or `aidd ship --skip-cooloff` on record.

**What the agent cannot do.** It cannot approve, ship, or land work on `main` by any git command. The hook denies it (in Claude Code, once `aidd init --harness claude-code` wired it). `aidd ship` and `aidd approve` want a person at a terminal that the agent did not start, typing a code that the prompt shows.

**When something is off.** `aidd gate` says what it waits for and how to fix it; `aidd gate --explain <rule>` says why. A secret-shaped line in the diff is a warning: rotate the key if it is real. `aidd doctor` checks the setup.

**Evening.** `aidd list` again: what waits on you is at the top. When the work starts to matter to other people, push to a platform and let its reviews take over ([Local-first](#local-first-no-github-or-gitlab), going online).

## Team

**Goal:** a human decides *what* gets built before agents build it, and someone other than the author decides *what* ships.

Agents do the building, so a small team is enough to deliver a real product. The team profile needs somebody other than the author to approve each change (the four-eyes principle). It also needs a `security` specialist Approver pool before a major change can ship. Nobody approves their own change, so a pool of one can never approve a major change that its only member wrote. Every config or CI change is major, too. So name at least two people in every specialist pool (`aidd doctor` warns about a pool of one). That sets the minimum at two people, both in the `security` pool; one person uses [solo](#individual-solo), with or without a [platform](#local-first-no-github-or-gitlab).

### Roll it out in three weeks

**Week 1: advisory.**

1. `aidd init --profile team --approvers @org/leads --specialist security=@org/security --test "<tests>"`.
2. The gate starts in advisory mode: it reports on `aidd/gate (advisory)` and blocks nothing.
3. Read `aidd metrics` from the gate events ([below](#reading-the-metrics)). Move on when the gate would rarely have blocked (a low would-block share in `aidd metrics`), and you agree with the blocks it reports.

**Week 2: enforce.**

1. Set `mode = "enforce"` in `.aidd/config.toml` (the workflow's `mode` input applies only when the config sets no mode), and require `aidd/gate`. A private repository on GitHub Free cannot require it, so there the gate stays advisory ([what holds without it](PLATFORMS.md#what-holds-without-the-full-setup)).
2. Adopt the Spec-first draft PR/MR habit for normal changes.
3. Add `identities.bots` for agent bot accounts.

**Week 3: tune.**

1. Add `risk_rules` for your sensitive paths, such as payments or PII.
2. Add `standard_changes` for bot dependency patches ([FAQ](FAQ.md#bots)).
3. Add `budget_exclude_paths` for generated code and `owners.paths` for per-directory Approvers.

**Done when:**

- the first-pass test rate is stable
- the gate rarely has to raise a route the agent under-assessed
- reviewers report smaller PRs/MRs

### A small team: two or three people

| Team | Who | Who approves whom |
| --- | --- | --- |
| **Two** | two people who both build, or one who decides the product and one who builds | each approves the other's Specs and merges; both sit in the `security` pool |
| **Three** (recommended) | a product lead, a tech lead, and an engineer: the product, design, and engineering trio of product discovery | below |

**The trio, worked out.** Design sits with whichever of the product lead or the tech lead is closer to the users. The agents' product designer does the drafting.

| Person | Decides | Directs these agents | Installs |
| --- | --- | --- | --- |
| Product lead | go/no-go and sign-off on proposals; the plan; Spec approval of product changes | `/aidd-team:propose`, `/aidd-team:plan` | nothing, to approve (they review on the pull request); the plugins, to direct agents |
| Tech lead | Spec approval of design changes; the architecture and security areas; Merge approval of the engineer's changes | `/aidd-team:onboard`, `/aidd-team:specify`, `/aidd-team:secure` | the CLI and the plugins |
| Engineer | authors most changes; Merge approval of the tech lead's changes | `/aidd-team:specify`, `implement`, `review`, `sweep` | the CLI and the plugins |

```toml
profile = "team"
goal = "checkout succeeds on the first try"

[owners]
approvers = ["@product-lead", "@tech-lead", "@engineer"]
specialists = { security = ["@tech-lead", "@engineer"] }   # two people, so either one's major change can ship

[[owners.paths]]
paths = ["docs/architecture/**", "docs/adr/**", "schemas/**"]
approvers = ["@tech-lead"]

[agents]
proactive_roles = []   # several people's agents: only people start work; the product lead plans on purpose
```

**How they work together.**

- **One change, one branch, one author.** The person who asked their agents for a change is its author. Everything their agents do is that person's change, marked by `Assisted-by:`. Nobody's agents push to someone else's branch.
- **Nobody approves their own work.** A change gets its Merge approval from someone who did not write it. A Spec can narrow who approves it with its own `approvers`: `["@product-lead"]` for a product change, `["@tech-lead"]` for a design change.
- **One queue, where everyone already looks.** Pull requests that wait for a review are the queue. `aidd assess` shows each person the next step on their branch. It warns when another branch's Spec changes the same code ("SPEC-2 overlaps SPEC-1 on alice/cart"). So the two people agree who goes first, before their agents collide. The later change waits, `blocked` on the first.
- **Everyone's agents, one team definition.** Each person runs their own agent sessions. But the roles, the config, the skill, and the standards are shared, and change only through the gate. Each change gets its own branch or worktree, so parallel agents never share files.
- **Spend in proportion.** A minor fix is one agent, not the team. The specialists run only when their start condition holds, whoever's session it is.

**When only some of them use agents.**

- The gate judges every pull request, including the ones a person writes by hand. Those declare `assisted_by = []` (or carry `Assisted-by: none`), and a small change needs only a short Change Request block (`aidd describe` prints it).
- The product lead never needs the CLI to take part. They approve on the pull request, and a Spec is a Markdown file they can read and comment on.
- Start in advisory mode, so whoever does not use agents yet sees what the gate would say before it blocks anything.

**Growing.** Add people to `owners.approvers`. Give an area its own owners in `[[owners.paths]]` once someone owns it. Bind specialist pools (`security`, `privacy`, `data`) once two people can hold each.

### A medium team: five to nine people

A team small enough that everyone knows everyone's work, big enough that one person cannot review it all: the "two-pizza team". A worked example of eight people shipping a checkout product, one repository with a web app and an API:

| People | Decide | Own |
| --- | --- | --- |
| Product lead | proposals, the plan, Spec approval of product changes | the goal, `proposals/`, the Initiatives |
| Designer | Spec approval of changes to what users see | the design files and prototypes |
| Tech lead | Spec approval of design changes; the security pool, with the platform engineer | `docs/architecture/`, `schemas/` |
| Four engineers, two on `web/` and two on `api/` | Merge approval of each other's changes, within their area | `web/` or `api/` |
| Platform engineer | Merge approval of infrastructure changes; the incident commander on call | `infra/`, and the deploy commands held for a person |

```toml
profile = "team"
goal = "checkout succeeds on the first try"

[owners]
approvers = ["@org/checkout"]                  # the whole team; nobody approves their own change
codeowners = true                              # per-area approvers from CODEOWNERS
specialists = { security = ["@tech-lead", "@platform-engineer"], privacy = ["@product-lead", "@designer"] }

[[owners.paths]]
paths = ["infra/**"]
approvers = ["@platform-engineer"]

[gates]
approvals = { major = 2 }                      # two people on anything the gate calls major

[[tests]]
name = "web"
command = ["pnpm", "--dir", "web", "test"]
when_changed = ["web/**"]

[[tests]]
name = "api"
command = ["uv", "run", "--directory", "api", "pytest"]
when_changed = ["api/**"]

[[standard_changes]]
name = "dependency updates"
paths = ["web/package.json", "web/pnpm-lock.yaml", "api/pyproject.toml", "api/uv.lock"]
authors = ["dependabot[bot]"]

[[guard.held_commands]]
name = "production deploy"
match = ["deploy", "production"]
environment = "production"
requires = "RELEASE_APPROVAL"
```

**What changes from three people.**

- **Ownership by area.** CODEOWNERS routes each change to the people who own the code it touches, and the gate requires one of them to approve. An engineer's agents on `web/` never need an approval from `api/`.
- **Each area runs only its own tests.** `when_changed` keeps an `api/` change from waiting on the web suite.
- **The routine is automatic.** Dependency updates from a bot merge on green tests as standard changes; nobody approves them by hand. A production deploy waits for a person, whoever's agent asks.
- **More parallel work, more overlap.** Eight people's agents on one repository collide more often. `aidd assess` warns when two branches change the same code, and the later change waits.
- **Look at the flow every week.** `aidd metrics` shows where changes wait and for whom, `aidd metrics --dora --specs specs` how delivery is doing against your `[targets]`, and `aidd metrics --autonomy` which agents have earned lighter review. The agile coach's retrospective turns the answers into changes. A scheduled job can run these for you ([How do I…](HOW-TO.md#run-the-routine-checks-on-a-schedule)).

Beyond one team: [Organization](#organization).

## New teammate

A person joining a team that already uses aidd. The team lead pairs them with one person for the week.

- [ ] Read [TEAM.md](TEAM.md) for the roles and the loop. Read [GLOSSARY.md](GLOSSARY.md) for the words the team uses (Spec, Acceptance id, route, the two approvals).
- [ ] Run the [Quickstart](QUICKSTART.md) once in a scratch repository, from `aidd init` to `aidd ship`, so the commands are familiar before they matter.
- [ ] With your pair, shadow one Spec from Specify to Ship. Read the Spec and its tests before Spec approval, and watch the agent implement and verify. Read the gate's report at Merge approval, and watch the observe window.
- [ ] Learn the two approvals, Spec approval and Merge approval, and who holds which pool. See `owners.approvers` and `owners.specialists` in `.aidd/config.toml`, and `aidd owners` for the owners by path.
- [ ] Find the runbooks (`docs/runbooks/`) for the services you will be on call for, and the postmortems (`docs/postmortems/`) of their last incidents.
- [ ] Before you approve anything: get added to the approver list by the team lead, never by an agent.

## Multiplayer: one team, humans and agents

A team that shares its agents gets more from them than the same people each running their own. Everyone reads the same context, so nobody has to rediscover it. The work shows up where everyone can review it, and trust can be earned and recorded. Four habits make that work, and each one maps onto something aidd already has:

| Habit | What it means | In aidd |
| --- | --- | --- |
| Work in public, with broad context | Agents and people read the same instructions and write to the same place | One committed `.aidd/config.toml`, AGENTS.md, skill, and hooks for everyone. Specs and decisions live in the repository. Every role ends with a handoff note where the team works (on the PR/MR when there is a platform) |
| Clear roles, with the tools for each | Everyone knows who owns what, and each agent can do its job and nothing more | `[owners]` for the humans; the delivery team's roles, each with its write area enforced by the guard; `aidd owners` shows both |
| A written goal | One goal everyone steers by | `goal` in the config; agents weigh open choices against it, and `aidd observe --band` writes it into the draft Specs it opens |
| Release gradually | An agent gets more autonomy as it proves reliable, and one agent checks another's work | The spec lane first, then the fast lane, then standard changes earned from `aidd metrics --autonomy`. The Verifier and the reviewer check the implementer's work, and the gate checks everyone's |

**Check readiness.** Five questions tell whether a team is ready to work with agents, and aidd answers each from the repository. `aidd doctor` checks the first four, and `aidd owners` shows the fifth next to who decides and who works. Run both when the team forms and whenever someone joins.

1. Is the work written down where everyone can read it? The config and the Specs.
2. Does every decision have a named owner? `owners.approvers`.
3. Does everyone have the same tools? `AGENTS.md` and the skill.
4. Do tests and a rubric check the key work? `[[tests]]` and `REVIEW.md`.
5. Is there a goal? Set it with `aidd init --goal` or `goal` in the config.

**Avoid a fleet of personal agents.** When each person runs a private agent with private instructions, the context splits apart. Then the same work gets done twice, and nobody can see what an agent did. Keep one shared config, skill, and set of roles, and change them through the gate like any other change. Give each agent its own bot account (`identities.bots`), so its commits are attributed to it and it can never approve.

**Earn autonomy with evidence.** `aidd metrics --autonomy` groups the gate events by agent (from `Assisted-by:`) and by kind of change, and puts each group on one of three stages:

1. *review every change*: every agent and every new kind of work starts here
2. *review the trade-offs*: enough changes, enough of them passing on the first try, with no failures and no Spec rework. Reviewers focus on the decisions rather than every line
3. *candidate standard change*: more changes and a higher first-try share, still with no failures or rework. A human may add the class to `[[standard_changes]]`, through the gate, so it merges on green tests

How many changes and what share each stage needs are set in `[agents.autonomy]`; the defaults are in [CONFIG.md](CONFIG.md#mission-goal-and-agents). A single failure or reworked Spec sends the group back to stage 1. The report only suggests a stage. A person decides, and the change to `[[standard_changes]]` goes through the gate like any other ([Proposing a standard change](#proposing-a-standard-change)).

**Let the right agents suggest work.** `[agents] proactive_roles` names the roles that may suggest work nobody asked for (by default product-manager, agile-coach, and sre). They suggest it only as a draft Spec that a human triages. The other roles work only when asked. Set `proactive_roles = []` to have no agent propose anything.

**Ask people in batches, and in the open.** Each role gathers what only a human can answer into the `Needs` line of its handoff note. It does not interrupt with one question at a time. The note and the gate's decision appear on the PR/MR, and with no platform `aidd list` shows what waits for whom. To reach people where they already talk, the notifier template posts to Slack or Teams ([Platforms](PLATFORMS.md#notifications)). Or subscribe a channel to the PR/MR through the platform's own integration.

## Domain experts as specialist Approvers

Some changes need a person who knows the business, not only the code:

- a payments specialist for how money moves
- a clinician for a dosage calculation
- a tax adviser for invoicing rules
- a lawyer for consent text

In aidd a domain expert is a person in a named specialist Approver pool. No agent role stands in for one: the delivery team's compliance analyst or security engineer drafts and flags, and the expert decides.

1. **Name the pool** in `owners.specialists`, beside `security`. Any name works.
2. **Point a risk rule at it.** A rule that makes a change major names, in `specialists`, the pools that must approve it.
3. **The expert approves on the PR/MR**, like any Approver, on the head commit. They need no CLI, and they can block a change by requesting changes.

```toml
[owners]
approvers = ["@org/engineering"]
specialists = { security = ["@org/security"], clinical = ["@org/clinical-safety"] }

[[risk_rules]]
name = "dosage"
paths = ["src/dosing/**"]
route = "major"
specialists = ["clinical"]
```

With this, every change to `src/dosing/` is major and waits for an approval from the `clinical` pool, on top of the usual Merge approval.

- **From the team profile up**, each named pool must give one approval (`specialist_approvals`). Under `regulated`, the pool also approves the Spec before any code. Under `solo`, no pool is required.
- **The built-in dimensions** already name their pools: `financial` changes go to `finance`, and `data`, `privacy`, `security`, and `compliance` to pools of the same name ([METHOD.md §6](METHOD.md#6-routes)). Bind a person to each pool your work touches.
- **An unbound pool** falls back to `security`. So bind the expert's pool before the rule goes live, or the security pool gets their reviews.
- **Few experts, many changes:** keep the rule's `paths` narrow, so the expert sees only the changes that need them. Ask for their review on the PR/MR, so the platform tells them. The gate's report names the pool a change waits for.

## Project constraints and rules

Agents follow the rules they can read. Write the project's constraints once, in `[project]` of `.aidd/config.toml`, and every role sees them. The architect designs within them, the reviewer flags what breaks them, and the platform engineer spends within the budget. They change through a change like the rest of the config.

```toml
[project]
hosting = "one VPS in the EU"

[project.stack]                 # a technology radar
adopt = ["Python", "PostgreSQL", "pytest"]
trial = ["htmx"]
hold = ["MongoDB"]              # not for new work without an ADR and a person's decision

[project.budget]
max_infra_per_month = 50
currency = "EUR"
new_paid_service = "ask"        # or "allowed", "forbidden"

[[project.rules]]
id = "money-in-minor-units"           # stable: a waiver names it
level = "must"                  # must, should, may (BCP 14)
statement = "Store money as an integer count of the currency's minor unit."
why = "Floats lose minor units on rounding."
applies = ["src/billing/**"]    # omit for the whole repository
check = "unit"                  # the command or [[tests]] name that enforces it
source = "docs/adr/0002-money.md"
owner = "@alice"
review_due = 2027-03-01

[[project.waivers]]
rule = "money-in-minor-units"
reason = "The legacy export still reads floats until its rewrite."
approved_by = "@alice"          # a person, never an agent or a bot
until = 2026-12-31
```

- **Read.** `aidd assess --paths src/billing/refund.py` and `aidd owners --changed <path>` print the stack in one line and the rules whose `applies` match, must first, each with its why and any waiver in force.
- **Checked.** `aidd validate` fails on a repeated rule id, a waiver of an unknown rule, a waiver an agent or bot approved, and a waiver past its `until`. It warns 14 days before a waiver expires, and once a rule's `review_due` has passed. When a Spec's Context or Design names a `hold` technology and links no ADR, it warns: a text match, so a hint only. For a Spec whose Task scopes hit the infrastructure paths (`baseline:iac`), it warns when no monthly estimate is stated (`about 40 EUR a month`). It looks for the estimate in the Spec's Context and in a linked tech spec's "Scale and cost" row. It also warns when the first estimate in the budget's currency is above `max_infra_per_month`. The gate never reads `[project]`; a rule is enforced by its `check`, or by a reviewer.
- **Layered.** An org preset that lists `project` in `locks` binds its rules. A repository adds its own, and may raise a rule from should to must, but never lower one. Nor may it waive a locked rule, adopt what the preset holds, or raise the budget.
- **Started.** `aidd init` writes what it detected (the stacks and test runners) as a commented `[project.stack]`; uncomment and edit it. It never guesses the hosting, the budget, or the rules.

Field by field: [CONFIG.md](CONFIG.md#project).

## Proposals: bids and internal cases

A software agency writes proposals to win work, and any company writes them to get a change approved. Both are the same object in aidd ([METHOD.md §4.7](METHOD.md#47-proposal)), with `audience = "client"` or `"internal"`.

1. **Qualify.** `aidd new proposal PROP-12 --title "Checkout rebuild for Acme" --addressee "Acme Corp"` (or `--audience internal --addressee "the executive committee"`). The product manager writes the goal, the needs with their sources, and the questions, and a person records go or no-go. Most of the saving is here: a quick no-go costs an hour, a lost bid costs weeks.
2. **Draft in parallel.** `/aidd-team:propose` runs the specialists at once, each writing its own file in the proposal's folder. The files cover architecture and the estimate, experience, security, compliance, and operations. The tech writer makes it one document, and `aidd proposal matrix` renders the needs, options, estimate, assumptions, exclusions, risks, and open questions as tables.
3. **Sign off and send.** A person reviews the needs that are not fully met, the range, the assumptions, and the exclusions, and sets the price. That person records `sign_off` with the hash that `aidd hash` prints for the proposal. No agent sets a price or commits the company. After sign-off, a change needs a new sign-off or a change order that names the new hash.
4. **Deliver what you promised.** Accepted, `aidd proposal convert` makes an Initiative and one Epic per group of needs; every Spec under them traces back to the proposal.

Keep each client's proposals where only the people cleared for that client can read them. For example, use one private repository per client or per bid. Never let an agent copy one client's material into another's proposal. Record each outcome (`accepted`, `rejected`, `withdrawn`). Compare past estimates with what delivery took: that is the reference class the next estimate starts from.

## Organization

**Goal:** many repositories and teams share one policy baseline, and the security and platform teams review every major change.

When several teams share code, services, and rules, the team setup stays the same inside each team, and a few things are added above it. A worked example: six product teams like the [medium team](#a-medium-team-five-to-nine-people), a platform team, a security team, and a compliance function, forty repositories.

| Who | Owns | How aidd holds it |
| --- | --- | --- |
| Platform team | the org preset, the CI templates, the plugin marketplace, the managed settings | a baseline every repository inherits and cannot loosen (the steps below); managed settings require the plugins on every machine |
| Security team | the `security` pool, protected paths, the Policy (freezes and deny lists) | major changes in any repository need one of them; the preset binds the pool and the Policy |
| Compliance | the `regulated` profile where the law requires it, the audit evidence | the gate record per change, mapped in [Controls](CONTROLS.md) |
| Domain experts | the pools for their areas (payments, clinical safety, tax) | risk rules in the preset send each area's major changes to its pool ([Domain experts as specialist Approvers](#domain-experts-as-specialist-approvers)) |
| Each product team | its repositories, its approvers, its goal | its own config, which may only tighten the preset |
| Leadership | proposals that ask for money or cross team lines | Proposals with `audience = "internal"`, decided go/no-go and signed off by a person |

**What changes from one team.**

- **One baseline, many teams.** The org preset sets the profile, the protected paths, the risk rules, the specialist pools, and the Policy once. A team can tighten it, never loosen it, and the platform team changes it through the gate like any change.
- **Work across teams.** An Epic whose Specs name two or more `owner_team`s holds the shared glossary in its `context`. A Spec that waits for another team's work names it in `depends_on` as `team:ID`. The changes of one piece of work across repositories share a `trace_id`, so their records can be joined. `aidd list api web infra` shows every repository's next step.
- **Evidence nobody can touch.** Tests run in a central required workflow, and the gate accepts only its attested evidence (step 4).
- **Measure per team, compare per service.** `aidd metrics --by team` shows where each team's changes wait; `aidd metrics --dora` compares each service with its own targets, not teams with each other.

**1. Write the org preset** (`aidd-org-preset.toml`, in a repository only the platform team can change):

- `profile = "org"`: the profile every repository inherits
- org-wide `risk_rules` and `protected_paths`: the sensitive and protected areas every repository shares
- `owners.specialists`: the specialist Approver pools (security, data, privacy, finance, compliance, and any domain experts' pools) that approve high-risk changes
- a Policy command: a script of yours the gate runs to enforce freeze calendars and deny lists
- `[standards_policy]`: the opinionated library standards every repository carries (`require`), may not add (`exclude`), or replaces with the company's own (`replace`), and the stacks it allows (`allow_stacks`). `aidd doctor` fails on a breach ([Standards](STANDARDS.md#a-companys-policy)).

A repository can only tighten the preset. It cannot replace its specialist Approvers, Policy, evidence source, or identity exemptions.

**2. Apply it in one of two ways:**

| Topic | `extends` in each repo config | `org-preset-url` on the reusable workflow |
| --- | --- | --- |
| How | `extends = [{ url = "https://<host>/aidd-org-preset.toml", sha256 = "<digest>" }]` | in each `aidd-gate.yml`: `org-preset-url: https://<host>/aidd-org-preset.toml` and `org-preset-sha256: <digest>` |
| Opt-out | a repo edits its config (protected, major) | a repo edits its gate workflow (protected, major) |
| Change | bump the pin in each repo | bump the pin in each caller, or roll the caller out centrally |

Write the pin literally in the file, never through a repository variable. A repository admin can override variables without a pull request. For a guarantee that no repository can edit, put the caller in a platform repository. Make it an organization **required workflow** (a ruleset rule) there.

**3. Roll out in waves.** Repositories start in advisory mode.

1. Install the gate's GitHub App on the organization, and store `AIDD_APP_ID` as an organization variable. Keep `AIDD_APP_PRIVATE_KEY` only in each repository's `aidd-gate` environment. [PLATFORMS.md](PLATFORMS.md#setup) has every step, and [METHOD.md §14](METHOD.md#14-platform-bindings-and-trust) says why it is never an organization secret.
2. Use `aidd init --profile org --approvers <handles> --specialist security=<handles> --test "<command>" --policy "<command>"` to open the setup PR in each repository; the flags make it scriptable. When the preset binds the Policy instead, check with `AIDD_ORG_PRESET=aidd-org-preset.toml aidd doctor`.
3. Pilot 3 repositories in advisory mode (2 weeks), then 20% of repositories, then all.
4. Enforce with an **organization ruleset** that requires `aidd/gate` from the App. Target repositories with a custom property (for example `aidd = enforced`), so a wave is a property change and exemptions are explicit and auditable.

**4. Make evidence tamper-resistant (optional).** Run the tests from a central required workflow and require its attestation: [PLATFORMS.md](PLATFORMS.md#evidence-the-pull-request-cannot-touch).

**5. Operate.**

- Collect gate events centrally, from the workflow artifacts or by shipping `--events` output to your log pipeline.
- Rotate the App private key on your normal secret schedule (a script over the environments API). The gate reads it per run.
- Gate runs cost roughly 15 to 30 API calls each, under the App's installation rate limit. One installation per organization is shared by every repository. CI minutes, storage, and tokens: [ENTERPRISE.md](ENTERPRISE.md#10-cost).
- Upgrade by changing one pin: the reusable workflow and the test action refs, the CLI, and the vendored skill move together.

**Done when:**

- 100% of protected branches require `aidd/gate`
- `aidd metrics --by team` shows the AI-assisted metrics per team, and `aidd metrics --dora --specs specs` the DORA proxies against your `[targets]`
- the Policy freeze is exercised once, including an emergency break-glass drill

## Compliance-ready by default

**Goal:** the product carries the controls that an enterprise buyer or an auditor asks about, from its first Spec. The evidence for each control is an export, not a project.

Say what the product must be ready for in `[project.compliance]`. `aidd init` writes the table commented out and asks nothing. `aidd init --compliance-target soc2 --compliance-target gdpr` writes it filled in, and the proposal's first questions ask the client for it. Compliance is on when `targets` names a framework or law, or when the profile is `regulated`; there is no level to pick.

```toml
[project.compliance]
targets = ["soc2", "gdpr"]   # soc2, iso27001, gdpr, hipaa, pci-dss, fedramp, other
```

| Compliance | What it turns on |
| --- | --- |
| off (no target, and a profile other than regulated) | Nothing beyond the defaults every project gets. |
| on (any target, or the regulated profile) | The `aidd-team:enterprise-controls` pack, named in `aidd assess` and `aidd owners`, with its 19 controls as the default for every Spec. `aidd validate` warns when a change on a security or auth path links no threat model or authorization matrix, whatever its risk says. `aidd init` on GitHub writes `.github/workflows/aidd-security.yml` (dependency scan, static analysis, and an SBOM, each with a read-only token). ASVS Level 2 on authentication, session, and admin surfaces. |

A target that expects separation of duties (soc2, iso27001, pci-dss, fedramp, hipaa) under the `solo` profile gets a warning from `aidd validate`. Solo waives it, so move to the team profile with a second approver before the audit.

Every project also gets `.github/dependabot.yml` for the ecosystems `aidd init` finds, and OWASP ASVS Level 1 as the default level of every Spec. It also gets a warning from `aidd validate` on a postmortem action item past its due date. Evidence by control is `aidd record export records <record dirs> --by-control`. Each Spec's compliance doc names its control ids (`EC-01` to `EC-19`, or your own) in its Obligations table. The export groups the gate records and the linked docs under them ([CONTROLS.md](CONTROLS.md#what-aidd-builds-into-the-product-when-compliance-is-on)).

**The readiness ladder.** Climb it one stage at a time; the pack's `references/readiness.md` lists what each stage needs.

| Stage | Compliance | The team builds | People outside the team |
| --- | --- | --- | --- |
| MVP | off | change management, secure coding, deny-by-default authorization, secrets in a manager, scanning, CI least privilege, TLS | name an owner for security questions |
| First paying customer | off, or on with the customer's targets | backups with a drilled restore, logging and security events, MFA and sessions, rate limits, incident response, vulnerability disclosure | a data processing agreement, the subprocessor list |
| First enterprise deal | on | all 19 controls and the enterprise-deal checklist: SSO, SCIM, audit log, admin console, IP allowlisting, residency, SLA and status page, trust center, VPAT | the security questionnaire, often a third-party penetration test |
| Certification | on, with the audit's targets | the same, with the evidence exported for the audit period | policies, the ISMS, vendor reviews, training, the penetration test, and the auditor |

aidd never certifies anything. An independent auditor issues a SOC 2 report or an ISO/IEC 27001 certificate. Most of what they examine beyond the product is organizational work outside the team.

## Regulated

**Goal:** the audit trail proves who approved what, on which evidence, under which policy, for every AI-assisted change.

1. `profile = "regulated"`. This means:
   - two Approvers and a specialist Approver approve every major change
   - a bound Policy is required on every route
   - every commit carries an `Assisted-by` trailer
   - an observe window after release is required on normal changes, not only major
   - no pre-approved (standard) change classes: every change gets a human
2. Retain the gate records (`aidd-record.json`), events, evidence, and logs for as long as your regime requires. The workflows keep them as artifacts for a limited time ([ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)). Ship the records and the `--events` output to durable storage for anything longer.
3. Map controls with [CONTROLS.md](CONTROLS.md), and add your organization's control IDs to `risk_rules` names.
4. Add license and secret scanners to `[[tests]]`, so the gate enforces them.

## Many companies

**Goal:** agencies, vendors, open-source maintainers, and groups of companies use one loop without any company deciding for another.

- **Each company owns its gate.** Its preset, approvers, specialist Approvers, Policy, and App or token stay inside it. Nothing is shared except the method's version and, when chosen, a public preset pinned by sha256.
- **Each company is a tenant.** Its org preset sets `tenant = "<company>"` and locks it (`locks = ["tenant"]`), so no repository moves itself to another company. Every gate record, event, and change record carries the tenant; `aidd metrics --tenant`, `aidd record export --tenant`, and `aidd record verify --tenant` read one company's alone ([ENTERPRISE.md §13](ENTERPRISE.md#13-multi-tenancy)).
- **An agency runs one tenant per client.** Each client's repositories name that client's tenant, and its preset names that client's Approvers. Write a pool entry or an identity as `<tenant>:<login>` when the same login works for two clients. An approval by an identity of another tenant never counts (`merge_approval.other_tenant`), so one client's lead cannot approve another client's change by accident.
- **Contributors from outside are authors.** A vendor's or agency's agents and people open changes in the client's repository. The client's Approvers decide Spec approval and Merge approval. A person who works for several companies approves only where they sit in a pool.
- **Cross-company work shares a `trace_id`.** Each company gates its own child change; neither gate can pass the other's.
- **Compare without pooling.** Each company runs `aidd metrics --by repo --tenant <company>` on its own events. A group of companies that agrees to pool events uses `--by org`.

## Reading the metrics

Every gate run uploads an artifact `aidd-gate-<run>-<pr>` holding `aidd-events.jsonl`. To summarize a repository:

```sh
gh run list --workflow aidd-gate --limit 200 --json databaseId -q '.[].databaseId' \
  | xargs -I{} gh run download {} --dir gate-events
aidd metrics gate-events/*/aidd-events.jsonl
aidd record export events gate-events --format csv --out warehouse     # one table for a spreadsheet or a warehouse
aidd record export records gate-events --out warehouse                 # every audit record, as one JSON array
```

| Metric | Source | Healthy direction |
| --- | --- | --- |
| First-pass test rate | `aidd metrics` | up |
| Route corrections (declared below required) | `aidd metrics` | down |
| Top failed rules | `aidd metrics` | moves away from `scope` and `red_green` failures toward none |
| Median changed lines | `aidd metrics` | down, or stable under the budget |
| Median wait per approval, waits above `--target-wait` | `aidd metrics` | down; nothing above a day |
| Open changes waiting, per approval | `aidd metrics` | at or below the WIP limit per Approver |
| Time to first feedback (p50, p90), paired with the first-pass test rate | `aidd metrics` | down, while the first-pass test rate holds; within `max_first_feedback_minutes` |
| Approval wait p50 and p90 per approval, paired with Spec rework after Spec approval | `aidd metrics` | down, while rework stays flat; within `max_approval_wait_p90_minutes` |
| Flow efficiency (lead time not spent waiting on an approval), paired with the first-pass share | `aidd metrics` | up, while the first-pass share holds; at or above `min_flow_efficiency` |
| Cost per change, paired with the first-pass share | `aidd metrics --cost ledger.jsonl` | stable or down; display only, never enforced |
| Major changes merge-approved within 10 minutes of the gate asking (`fast_major_merge_approvals`, a rubber-stamp signal) | `aidd metrics` | zero, or each one explained at the retrospective; it measures the gate's view of the wait, not reading time, and is never enforced |
| Throughput (passing changes per week) | `aidd metrics` | up, or stable while the size stays small |
| Change fail rate, recovery time (DORA proxies) | `aidd metrics --dora --specs specs` | down, and within `[targets]` |
| Lead time, deployment frequency, rework rate (DORA proxies) | `aidd metrics --dora` | stable or better after week 3, and within `[targets]` |
| Overdue incident reviews | `aidd validate` | zero |

`aidd metrics --by author` serves agent autonomy and a person's self-review, never ranking or appraising people.

### Loop speed, and what each is paired with

`aidd metrics` computes only what the gate events support. It shows every speed metric beside the quality metric that it must not degrade (METHOD §12.1):

- **Time to first feedback**: per head, from its push to the first gate decision on that head that holds its test results. The push time is `head_pushed_at`, or `opened_at` for a change's first head without one. A head the events cannot date gives no sample. Paired with the first-pass test rate.
- **Approval wait**: per approval (Spec approval, Merge approval, specialist approval), the minutes it stayed pending. It runs from the first event that reported it pending to the first later event that did not. It is reported as p50 and nearest-rank p90. A wait still open at the last event is not counted. Paired with the share of approved Specs reworked after Spec approval, which rises when approvals are rushed.
- **Flow efficiency**: over the changes that passed, active time divided by lead time. Lead time runs from `opened_at` (or the first gate run) to the first pass. Waiting is the time between an event reporting an approval pending and the next event. Active is lead time minus waiting. It counts agent work, CI, and fix-ups as active, so it is an upper bound on touch time. Paired with the first-pass share.

Events written before these fields existed give no sample for them and never an error. `max_first_feedback_minutes`, `max_approval_wait_p90_minutes`, and `min_flow_efficiency` in `[targets]` make `aidd metrics` exit 1 when missed ([Config](CONFIG.md#targets)).

### Cost per change

aidd calls no model and sees no bill, so the cost comes from the host. `aidd metrics events.jsonl --cost ledger.jsonl` joins a ledger you export to the changes. One JSON object per line:

```json
{"ts": "2026-09-28T10:00:00Z", "amount": 0.42, "currency": "USD", "agent": "claude-code/claude-opus-5-5", "spec": "SPEC-42", "branch": "feat/login", "sha": "3f2a9c1"}
```

- **Fields.** `ts`, `amount`, and `currency` are required; `agent`, `spec`, `branch`, and `sha` are optional.
- **Joining.** An entry joins a change by its Spec id first. Then it joins by a commit: seven or more hex digits matching a head that the gate judged. Last, it joins by its branch (the change id, which is the branch for local and `--context` runs). An entry matching several changes is split evenly, and one matching none is shown as not joined.
- **Currencies.** Totals stay per currency: aidd converts nothing, and judges `max_mean_cost_per_change` only when the ledger has one currency.
- **A cap per change.** `[agents] max_cost_per_change = { amount = 20, currency = "USD" }` makes `aidd metrics --cost` print a warning for each change whose cost in that currency is over it. `aidd metrics --cost` also lists them under `over_cap`. `max_mean_cost_per_change` in `[targets]` is the mean; this cap is each change's ceiling.
- **Display only.** Cost is never a gate rule and never pauses an agent. A missed target or a change over the cap never changes the exit code.

To produce the ledger:

- **From a harness's usage export.** Most coding agents can export usage per session with its cost, time, and working directory or branch. Map each session to one line, with `branch` from the session's branch and `spec` from the Spec it worked on. Take the Spec from the `Spec:` line of its handoff note, or from the branch name when it carries the id. A `jq` filter over the export's JSON is usually enough.
- **From an orchestrator's cost API.** An orchestrator that runs agents per Task knows the Spec and the commit that each run produced. Write one line per run with `spec` and `sha`, from the API or a webhook. Put the lines in a file that the scheduled metrics job reads.

### Proposing a standard change

`aidd metrics events.jsonl --autonomy --suggest-standard-changes` prints a `[[standard_changes]]` entry for each agent and change type that meets the candidate-standard-change thresholds in `[agents.autonomy]`. A comment holds the evidence: the changes, how many passed, the first-pass share, and that none failed or had its Spec reworked.

It is a proposal. `.aidd/**` is protected, so a person merges it as a major change with its approvals. `paths` is left empty (gate events do not record paths), so the entry fails `aidd validate` until a person fills it.
