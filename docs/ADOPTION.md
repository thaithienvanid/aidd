# Adoption playbook

Start with one repository, the smallest unit that has a merge gate. Grow by choosing a stricter profile and by sharing one org preset, not by forking the method.

| You are | Start with | First week |
| --- | --- | --- |
| [one developer](#individual-solo) | `aidd init --profile solo --approvers email:you@example.com @you --enforce` | enforce from day one |
| [one developer with no platform yet](#local-first-no-github-or-gitlab) | `aidd init --profile solo --approvers email:you@example.com --ci none` | type `approve <ID>` at the prompt |
| [one person running a team of agents](#hands-off-approve-all) | `aidd init --profile solo --ci none`, then type `approve all` | agents take each change to `main` |
| [a team](#team) | `aidd init --profile team --approvers @org/leads` | advisory, then enforce |
| [an organization](#organization) | a shared organization config (preset) and the shared gate workflow | 3 pilot repositories |
| [an audited or regulated organization](#audited) | `profile: audited` in the preset | pilot with your auditors |
| [many companies](#many-companies) | one preset per company, the method shared | each company adopts on its own |

## Contents

- [Adoption levels](#adoption-levels), from the method alone to an enforced gate
- [New or existing repository](#new-or-existing-repository)
- [Bring the delivery team to a project](#bring-the-delivery-team-to-a-project)
- [Coming from Spec Kit, OpenSpec, Kiro, or BMAD](#coming-from-spec-kit-openspec-kiro-or-bmad)
- [Local-first, with no GitHub or GitLab](#local-first-no-github-or-gitlab)
- [Individual, on the solo profile](#individual-solo), and [a solo day](#a-solo-day)
- [Your words decide](#your-words-decide), and [hands-off with approve all](#hands-off-approve-all)
- [The team as your software company](#the-team-as-your-software-company), which you work with as a client works with an agency, and how to [fully delegate](#fully-delegate-you-set-the-goal-the-team-decides-the-rest) when you want the result, not the technical choices
- [Team](#team), with the three-week rollout, [two or three people](#a-small-team-two-or-three-people), and [five to nine people](#a-medium-team-five-to-nine-people)
- [New teammate](#new-teammate), your first week on a team that uses aidd
- [Multiplayer, one team of humans and agents](#multiplayer-one-team-humans-and-agents)
- [Domain experts as specialist Approvers](#domain-experts-as-specialist-approvers)
- [Project constraints and rules](#project-constraints-and-rules)
- [Proposals, for bids and internal cases](#proposals-bids-and-internal-cases)
- [Several teams](#several-teams), with Team Topologies mapped onto the config
- [Organization](#organization), for many teams and repositories
- [Compliance-ready by default](#compliance-ready-by-default)
- [Audited](#audited)
- [Many companies](#many-companies)
- [Reading the metrics](#reading-the-metrics)

## Adoption levels

Each level adds to the one before it.

| Level | You add | You get | Not guaranteed |
| --- | --- | --- | --- |
| **1. Method** | the `aidd` skill and `AGENTS.md` | instructions that tell agents to follow the loop | anything: nothing is checked |
| **2. Team** | the `aidd-team` roles | roles, handoffs, and standards | anything: nothing is checked |
| **3. Local checks** | the CLI and the agent hook | the route, the guard on scope, red-then-green tests with `aidd test`, and local approvals (`aidd approve`, `aidd land`) | a merge outside `aidd land`: a person's own git commands, or an agent with no hook |
| **4. Advisory gate** | the CI check in advisory mode, the default after `aidd init` under the solo and team profiles | a report on every PR/MR, and `aidd metrics` | any block: the gate blocks nothing |
| **5. Enforced gate** | `mode: enforce`, and a required `aidd/gate` check pinned to the gate's App ([Platforms](PLATFORMS.md#setup)) | a change merges only with proof and approval | control over an actor on the ruleset's bypass list ([rulesets](PLATFORMS.md#github-rulesets-and-aidd)) |

A team may stay at any level. Levels 1 to 3 are guidance, not control. The gate turns that guidance into proof. `aidd init --ci none` writes no CI files, so it stops at level 3. The [three-week rollout](#roll-it-out-in-three-weeks) moves a team from level 4 to level 5.

## New or existing repository

Both work; only the first days differ.

| Topic | Greenfield (new repository) | Brownfield (existing codebase) |
| --- | --- | --- |
| Setup | `aidd init` in the empty repository; commit the setup and the project scaffold straight to the default branch (Day 0), then require `aidd/gate` | `aidd init` in a setup PR/MR that an administrator merges, then advisory mode, then enforce |
| Tests | the first Spec brings the test runner and the first test; add the suite to `tests` once it exists | put the existing suite in `tests`; a characterization test (one that pins today's behavior) where code is untested |
| Risk map | the baseline rules fit most stacks; add rules as sensitive areas appear | add `risk_rules`, `owners.paths`, and `changed_lines_exclude_paths` for the real layout |
| Planning | an Initiative and Epics hold the product intent; each Spec is a slice small enough for one review | Specs per change; Epics only for multi-Spec work |
| Watch for | early churn in dependencies and CI routes normal or major: batch toolchain setup into Day 0 | legacy code outside `scope`: leave it, and give cleanups their own Spec |

The skill's [`references/scale.md`](../.agents/skills/aidd/references/scale.md) has the Greenfield and Brownfield modules agents follow.

## Bring the delivery team to a project

The same four steps work for any repository; the table after them covers the situations that change a step.

1. **Look first.** `aidd init --dry-run` reads the repository and writes nothing. It finds:

   - the stacks and their test commands, one per package in a monorepo
   - sensitive areas the baseline rules miss
   - generated and vendored code, CODEOWNERS, and existing CI
   - code with no tests beside it
   - the agent instructions and planning tools already there
   - deploy and infrastructure commands, which `aidd init` holds for a person

   It prints the config it proposes. It also reads the dependencies your manifests declare, which name the domain packs. It reports a declared auth, payment, or migration library with the baseline rule that watches it, because that rule also fires when a change adds such a library, wherever its code sits.
2. **Set up in one change.** Run `aidd init --team`. Add `--claude-plugins` to install the Claude Code plugins for your user instead of repository files. It uses the detected test command unless you pass `--test`; merge the rest of the proposal after review. The change touches `.aidd/`, so the gate treats it as major. The gate starts advisory under the solo and team profiles.
3. **Onboard the team.** Run `/aidd-team:onboard`, which also runs before `aidd init` when the plugin is installed. The architect, the security engineer, the SRE, and the product designer if there is a UI map the codebase read-only and return one brief. The brief gives the config corrections, the draft architecture overview, glossary, and design system to add first, the areas that need a characterization test, and three small first changes.
4. **Work, and ask what is next.** Small first changes prove the loop here; `aidd list` tells anyone the next step and who holds it. Enforce once the gate's findings match the team's judgment.

| Situation | What changes |
| --- | --- |
| New, empty repository | Commit the setup and the scaffold straight to the default branch as Day 0; the first Spec brings the test runner ([New or existing repository](#new-or-existing-repository)). |
| Existing repository with tests | The detected suite goes into `tests`; the gate stays advisory until its findings match yours. |
| Existing repository with thin or no tests | Each change to untested code brings a characterization test first; the dry run lists where. Legacy code outside a Task's scope stays as it is. |
| Monorepo | One `tests` entry per package with `when_changed`, `owners.paths` or CODEOWNERS for each area's approvers, and the team works per package ([FAQ](FAQ.md#does-it-work-in-a-monorepo)). |
| One project in several repositories | Run `aidd init` in each. Keep Proposals, Initiatives, and Epics in one planning repository, and each Spec in the repository it changes. Each Spec names its Epic in `parent` and shares a `trace_id` with its siblings. Each repository gates its own change. `aidd list api web infra` shows the next step in all of them. |
| Many repositories in one organization | An org preset every repository inherits and cannot loosen, the aidd plugins required by managed settings, and rollout in waves, advisory first ([Organization](#organization)). |
| A client's repository (an agency, a contractor) | The client's people are the Approvers, and your agents are bots in `identities.bots`. The client's org preset applies, with the client's `tenant`. Your own people approve there only if the client's pools name them, and an identity you qualify with your own tenant never counts. Use repository files rather than your own plugins if the client restricts them, and keep your proposals for that client in your own private repository. |
| Open source with outside contributors | Pull requests from forks get no secrets: the gate App still judges them, and a maintainer re-runs agent evals. Bots' dependency updates can be standard changes. |
| Another platform (Bitbucket, Azure DevOps, Gerrit) or no CI yet | Run `aidd gate` against a `context.json` your CI builds ([Any other CI](PLATFORMS.md#any-other-ci)); with no CI at all, the gate runs locally as a preflight until one exists. |
| A mix of coding agents on the team | Every agent reads `AGENTS.md` and the skill; the roles are native agents in Claude Code, Codex, Copilot, OpenCode, Kiro, Grok Build, and Google Antigravity, and advisory elsewhere. Each role can run on a different model ([TEAM.md](TEAM.md#mixing-harnesses-and-models)). |
| Its own agent instructions or planning tool already | `aidd init` keeps them and adds a pointer; Spec Kit, OpenSpec, Kiro, or BMAD keep planning, and aidd gates ([Coming from Spec Kit, OpenSpec, Kiro, or BMAD](#coming-from-spec-kit-openspec-kiro-or-bmad)). |
| Only one team in a shared repository adopts | The gate is per repository, so stay advisory until every owner agrees, and meanwhile use `owners.paths` and risk rules for the adopting area. Opting in per directory is not supported. |
| A maintenance-only or legacy service | aidd without the team is often enough: dependency updates as standard changes, fixes on the fast lane, and the emergency lane for incidents. |
| Audited or regulated work | The `audited` profile, the managed-settings template, and the controls in [Enterprise readiness](ENTERPRISE.md). |
| A very large repository | The dry run stops after twenty thousand files and says so; the gate's speed on very large monorepos is not benchmarked ([Enterprise readiness](ENTERPRISE.md)). |
| The team leaves the project | `aidd uninstall` lists what it would remove and keeps what you changed; the Specs, records, and history stay. |

## Coming from Spec Kit, OpenSpec, Kiro, or BMAD

Keep the planning tool you like. These tools help an agent **plan** a change; aidd **controls** it. aidd checks the plan's risk against the real diff, freezes the tests at Spec approval, and proves them red then green on the exact commit. It also records two human approvals that the agent cannot give itself. The two jobs fit together:

1. Plan in your tool as today.
2. Draft the aidd Spec from the plan with `aidd import <tool> <path>`, as the table below shows. The Spec stays short, because it quotes the plan's problem in Intent and links every file it read instead of copying them.
3. Name the tests and write them, fill the rollback, get Spec approval, and build. From here aidd's loop runs as usual.

What `aidd import` writes in `specs/SPEC-<n>.md`, which `--id` and `--out` change:

- **Acceptance.** Each acceptance scenario, EARS requirement, or acceptance criterion gets an id, such as `A1` and `A2`.
- **Tasks.** You get one per task group in the plan that names file paths, with those paths as its `scope`. When the plan names no path, the Task keeps the template's TODO scope.
- **Route.** It's computed from those paths the way `aidd new spec --paths` does, and never below normal.
- **Tests.** They're left as TODO, with a comment naming any test file the plan mentions. A plan's tests are not assumed to exist or to prove the Acceptance.

`aidd validate` flags every TODO until a person fills it.

| Your tool writes | Run | It becomes, in the aidd Spec |
| --- | --- | --- |
| **GitHub Spec Kit**: `specs/<NNN-feature>/spec.md`, `plan.md`, `tasks.md` | `aidd import speckit specs/001-photo-albums` | The `**Input**` user description becomes Intent; each **Given/When/Then** acceptance scenario an Acceptance item (the `FR-###` requirements when there are none). `plan.md`'s Summary becomes the Design pointer, and each `## Phase` of `tasks.md` a Task. Both live under `specs/`; only files whose `---` front matter names a `kind` are aidd objects. |
| **OpenSpec**: `openspec/changes/<change>/proposal.md`, `design.md`, `tasks.md`, spec deltas | `aidd import openspec openspec/changes/add-dark-mode` | `proposal.md`'s Why becomes Intent; each `#### Scenario` of an ADDED or MODIFIED requirement in the deltas an Acceptance item; `design.md` the Design pointer; each `## N.` group of `tasks.md` a Task. |
| **Kiro**: `.kiro/specs/<feature>/requirements.md` (or `bugfix.md`), `design.md`, `tasks.md` | `aidd import kiro .kiro/specs/user-auth` | The introduction becomes Intent; each EARS requirement ("WHEN … THE SYSTEM SHALL …") an Acceptance item, one for one; `design.md` the Design pointer; each top-level task a Task. A bugfix spec is type `fix`, with the expected and unchanged behavior as its Acceptance. |
| **BMAD**: a PRD, an architecture document, and story files | `aidd import bmad _bmad-output/implementation-artifacts/1-2-password-reset.md` | One story becomes one Spec: its Story becomes Intent, its Acceptance Criteria the Acceptance, each top-level task a Task. The PRD belongs in an Initiative or Epic, the architecture in a decision record. |

The formats were checked on 2026-09-28 against Spec Kit 1.0, OpenSpec 1.13, the Kiro documentation, and BMAD 6.12. On 2026-10-22, the headings the importer reads were the same in Spec Kit 1.2.2 and OpenSpec 1.14.3. The standards registry keeps each tool's edition as `github-spec-kit`, `openspec`, and `kiro-specs`, with its release feed or its documentation as the source, so `aidd eval standards` names each one when it's due for a re-check. A newer layout the importer cannot read gives a Spec with more TODOs, never a wrong one, because it only copies what it finds.

**Which to pick if you have none.** Start with aidd alone, since its Spec already holds intent, design, Tasks, and tests. Add **Spec Kit** if you want a separate, richer planning step. It is the best-known option and sits beside aidd without overlap. **OpenSpec** suits long-lived systems where you track how each capability's spec changes over time. **Kiro** is a good fit if your team already works in its editor.

**BMAD, one team of roles at a time.** BMAD brings its own agent roles, such as an analyst, a product manager, an architect, a developer, and QA. So does the aidd delivery team. Running both gives agents two sets of instructions for the same job. Use BMAD's planning documents if you have them, as above, and let one set of roles do the work. aidd's gate works either way, since it checks the diff and the evidence, not which roles produced them.

## Local-first: no GitHub or GitLab

The loop runs locally, with the same two decisions, for:

- a solo founder who does not code
- a team that keeps work on one machine and pushes later
- a prototype that is not on a platform yet

This section is the one place the setup is spelled out; other pages link here.

1. Set up with the email that your git commits use. Commit the setup on `main` yourself. This is Day 0, the one change that lands without `aidd land`:

   ```sh
   aidd init --profile solo --approvers email:you@example.com --ci none
   git add -A && git commit -m "chore: adopt aidd"
   ```

   A local approval is recorded as `email:<git user.email>`, so list that as the Approver. When it isn't listed, `aidd approve` refuses and `aidd doctor` warns. With no test command found, `aidd init` binds a smoke test in this commit, so the first change has a suite to pass. The detected sensitive areas become `risk_rules`, and `.env*` goes into `.gitignore`. What your stack's tests and builds leave goes there too, such as `__pycache__/` and `.pytest_cache/` for Python or `coverage/` for Node. That's because `aidd test` counts an untracked file as a dirty tree. Init adds only the lines git doesn't already ignore, and `aidd init --dry-run` lists them.

2. Your agent works on a branch as usual. It asks the gate for the route with `aidd gate --paths`, writes the Spec and its tests, and stops. You read the Spec and type `approve <ID>` at the prompt. aidd records your approval of the Spec as it reads at that commit. Under solo, the gate requires Spec approval only on a major change. But approving a Spec before any code is still the cheapest place to catch a wrong plan. Once it's recorded, the approval binds, so a changed Spec or test fails the gate, and red-then-green is required for that Spec. `aidd list` then shows the Spec as ready.
3. The agent implements and runs `aidd test`. Then `aidd gate` tells you when the change waits only on Merge approval. In the Spec phase, while the branch holds only the Spec and its tests, `aidd test` exits 0 with the failing tests marked as expected. In that phase, the gate leads with Spec approval.
4. You read the agent's report and run `aidd land`. It shows the gate's report and the diffstat before asking you to confirm. It checks the change's declaration first, meaning the config, the block, the route, the scope, and the changed lines, and stops before any test if that fails. Then it runs the tests on exactly what will land. When only your Merge approval is missing, your yes records it and the change lands. `aidd approve merge` stays for approving without merging. It shows the digest, the diffstat, and the gate's state first, and refuses while another rule fails. `--squash` makes one commit that keeps every agent's `Assisted-by` trailer, so you can keep the work local and tidy and push it later.

**The fast lane locally.** A fast-lane change needs no Change Request block. The gate takes the route from the diff, the type from the commit subjects, such as `fix(cart): ...`, and the agents from the `Assisted-by:` trailers. So run `aidd test`, then `aidd land`, on the same head. When a change wants a block, such as to raise its route, `aidd describe --commit` records it in an empty commit on the branch. That moves the head, so run it before `aidd test`. `aidd test`, `aidd gate`, and `aidd land` read the newest such commit; `--body-file` on `aidd gate` and `aidd land` overrides it. A Spec branch needs none, because its Spec is found in the diff.

**When `main` moved.** If `main` moved since the branch left it, `aidd land` uses `git merge-tree` to merge the head into the new tip in a temporary worktree. It runs the tests there and lands exactly the merge commit it tested, or with `--squash`, one commit with that tree. A conflict lands nothing. Merge or rebase `main` into the branch yourself, then approve the new head. A Merge approval you gave before a rebase still counts when the rebase was trivial, as [PLATFORMS.md](PLATFORMS.md#approvals-across-rebases) explains.

`aidd approve spec`, `aidd approve merge`, and `aidd land` each show what you decide on, then ask one question, such as `Approve SPEC-1? [y/N]`. Only `y` or `yes` goes on. They refuse to run without an interactive terminal, or in a shell that an agent started, where `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT` is set. So run them in a terminal that you opened yourself. `aidd approve spec SPEC-1 --ref spec/SPEC-1` approves a Spec as a branch holds it, from any worktree.

**Publish when you choose.** Landed work stays on your machine until you type `publish` or run `aidd publish`. It pushes the local trunk, or a branch, with your decision records. `aidd list` says how far your local trunk is ahead of the remote, and warns when it waits too long. No agent pushes or opens a pull request until you publish, unless the config says `publish: agents`.

**With a platform.** Once the repository has a remote and a CI gate, a branch you published is decided by the platform's `aidd/gate`, which never reads this machine's approvals. On GitHub, `aidd publish` carries your recorded Spec approvals onto the pull request. After that, `aidd approve spec` posts the approval line on the branch's pull request as you, and `aidd approve merge` posts an approving review of the head. Both use your own GitHub token from `gh auth login`. They check first that GitHub knows you as an Approver in `owners.approvers`, and post only after your yes. With several accounts signed in to `gh`, aidd uses the one that is an Approver, whichever is active. `aidd land` refuses there, because the pull request merges on the platform. The prompt, MCP, and terminal routes below all work the same way.

<a id="approve-in-claude-code"></a>
**Approve at the prompt.** In any primary agent, type `approve SPEC-1` at the prompt, or `approve SPEC-1 and SPEC-4`, or just `approve` for every Spec that waits on you. aidd's prompt hook, not the model, catches the prompt, so your own words are the approval. It records each Spec at its current commit before the model reads the prompt, and tells you which commit. The agent then tells you what it does now, where it stops next for you, and how to stop it, and starts. The record says `Aidd-Decided-Via: prompt`. The guard keeps an agent from typing these words into another session. In Claude Code, the optional aidd-mods plugin counts only what you type at your keyboard, shows anything else in Claude Code's own dialog first, and records `Aidd-Decided-Via: claude-code`.

Merge approval works the same way. Type `approve merge`, and aidd records your Merge approval of this branch's head when the gate fails on nothing but that approval. On a local trunk, `land it` does what `aidd land` does. It runs the tests again on what lands, merges only if they pass, and records your Merge approval when that's all the gate waits for. `publish` then takes the work off your machine, when you choose.

When a Spec or its tests change after you approved it, the old approval no longer counts, and the Spec waits on you again. When you approve it again, at the prompt, in an MCP dialog, or at the terminal, aidd first shows each file and line that changed since your last approval.

**In any agent that speaks MCP.** Say "I approve SPEC-1" to the agent, and it calls the `approve_spec` tool of `aidd mcp`. "I approve the merge" calls `approve_merge`, and "land it" calls `land` on a local trunk. Your client then shows the Spec in its own dialog, through MCP elicitation, in Claude Code, VS Code, Cursor, and other clients that support it. Choose `Approve` and the approval is recorded, with `Aidd-Decided-Via: mcp:<client>`. The model's call alone records nothing, and `Not now` is the default. A client without elicitation gets the steps for you to run instead. Keep auto-answering hooks for elicitation, such as Claude Code's `Elicitation` hook, out of your settings, because such a hook answers in your place.

Here's what this proves, said plainly. On one machine an agent runs as you. The guard denies an agent's own `aidd approve`, but an agent that gets past the guard could record an approval itself, at a terminal or in Claude Code. A signing key that asks for your presence makes an approval yours alone, and it asks for your touch in Claude Code too. The setting is `gates.local_approvals: signed`, below.

What else to know:

- **The base branch is the gate's.** With no platform, the agent hook denies an agent any git command that lands work on `main`. `aidd init --harness claude-code` wires the hook for Claude Code; an agent with no hook is not stopped. The hook denies a merge, commit, cherry-pick, revert, rebase, or reset there, a push to it, `git branch -f main`, and `git update-ref refs/heads/main`, even after `git checkout main &&` in the same command. Only `aidd land`, which you run, moves it. Your own git commands are yours.
- **Parallel work** fits in git worktrees, one per Task or per agent. Each keeps its own files and evidence, and the approvals, kept on a ref, are shared by all of them.
- **Signing.** Set up git commit signing with an SSH key that asks for your presence. List each Approver's public key in `.aidd/allowed_signers` on the base branch, and set `gates.local_approvals: signed`. Then only approvals signed by a listed key count, whatever this machine's git config says. The limits of a local approval are in [METHOD.md §8](METHOD.md#local-approvals).
- **Going online.** When the work starts to matter to other people, push it to a platform and let its reviews take over. Once the repository has a remote and a CI gate from `aidd init --ci github` or `gitlab`, the local `aidd gate` is a preflight. Its hints name the platform's steps, such as posting the approval line on the PR/MR, because the platform's `aidd/gate` decides.

## Individual (solo)

**Goal.** Agents move fast without landing unproven or out-of-scope changes.

1. Run `aidd init --profile solo --approvers email:you@example.com @you --enforce --test "<your test command>"`, merge it, and require `aidd/gate` as [Platforms](PLATFORMS.md#setup) shows. Try the loop locally first with the [Quickstart](QUICKSTART.md).
2. If you have no tests, write one characterization test first. [METHOD.md §10](METHOD.md#10-scale-modules) says how.
3. Write a Spec for anything above minor, so the tests exist before the code. The gate asks for Spec approval on major changes only.
4. You are the only Approver, so the gate asks for an explicit second look instead of a second person. Type `approve <ID>` for a major Spec and `merge it` for a merge, and aidd posts `/aidd approve-spec <ID> <commit>` and `/aidd approve-merge <full head SHA>` on the pull request as you. [METHOD.md §8](METHOD.md#solo) has the solo rules.

**Done when** every merge in the last two weeks passed the gate, and none needed a revert.

### A solo day

One founder, one agent, no platform. The commands you type are yours; the agent runs the rest.

**Morning, pick the work.** `aidd list` shows every open piece of work and who holds it. Describe the next change to the agent, and it asks the gate for the route with `aidd gate --paths` before the first edit.

**A small fix, on the fast lane.** The agent works on a branch, commits, runs `aidd test`, and stops. You read its report and run `aidd land`. It runs the tests again on what will land and shows the report and the diffstat. Then your yes records your Merge approval and merges into `main`.

**A feature, on the spec lane.** The agent writes the Spec and its failing test and stops. You read them and run `aidd approve spec specs/<ID>.md`. From then on the Spec and its test are frozen, and the test must fail before the code and pass after it. The agent implements, runs `aidd test` and `aidd gate`, and stops again; you run `aidd land`.

**A risky, major change.** Authentication, migrations, secrets, and your aidd config are major, and so may be what your risk rules name. The Spec needs your approval before the work starts.

**What the agent cannot do.** It cannot approve, land work on `main`, or publish by any git command. The hook denies it. In Claude Code, `aidd init --harness claude-code` wires that hook. `aidd land` and `aidd approve` want you at a terminal that the agent did not start, answering yes at the prompt.

**When something is off.** `aidd gate` says what it waits for and how to fix it; `aidd gate --explain <rule>` says why. A secret-shaped line in the diff is a warning, so rotate the key if it's real. `aidd doctor` checks the setup.

**Evening.** Run `aidd list` again, and what waits on you is at the top. When the work starts to matter to other people, push to a platform and let its reviews take over, as [going online](#local-first-no-github-or-gitlab) describes.

## Your words decide

What you type at the prompt is the decision, so you never open a terminal for it. aidd's prompt hook reads your prompt before the agent does, with no plugin to install. It works in every agent aidd wires, which are Claude Code, Codex, Grok Build, Antigravity, and OpenCode. It records exactly what you named:

| You type | What aidd records |
| --- | --- |
| `approve SPEC-1` (or `/aidd approve SPEC-1`) | the Spec approval of SPEC-1 at its current commit |
| `approve` | every Spec approval that waits on you |
| `approve merge` | the Merge approval of this branch's head, even while the gate still fails on something else: aidd says what, and the gate holds the merge until the team fixes it |
| `land it` (or `/aidd land`) | that you said to land this change on your local trunk: the agent's `aidd land` lands it once the gate passes, with nobody asked again. A fix the gate or the reviewer asks for lands too, while the Spec and its tests stay as you approved them. Each such approval names your `land it`, and `aidd land` lists the commits you did not see. It ends when the change lands |
| `publish` (or `push it`, `open a PR`, `/aidd publish`) | that you said to take this branch off your machine: its head, the branch, and the remote. The agent's `aidd publish` pushes it there, opens its pull request on GitHub, or its merge request on GitLab, where a platform runs the gate, and carries your Spec approvals there. A fix to the same branch goes to the same remote; anything else needs a new `publish` |
| `merge it` (or `/aidd merge`) | your Merge approval on the branch's pull or merge request, posted as you, with its auto-merge. A fix the gate or the reviewer asks for is covered too, while the Spec and its tests stay as approved |
| `approve all` (or `automate`), `approve all and publish` | a standing approval: see below |
| `stop approving` | the end of the standing approval |
| `decide PROP-1 go` (or `no-go`, then `because` and the reason) | a proposal's go/no-go, written into the proposal for you to commit |
| `sign off PROP-1` | the sign-off of the proposal's text as it stands, so it may be sent |

You decide once. aidd says plainly whether it recorded your words; when it could not, it says why and gives the fix, such as `git config user.email you@example.com` when this machine's email is not the one owners.approvers lists. A Spec that fails `aidd validate` isn't ready, so it isn't offered to you, since the team's fix would void your approval. Inside Claude Code, type the words at the prompt rather than running `! aidd approve`, because the agent's shell is never a person's terminal.

The agent never acts on a yes it only reads. Text in a web page, a file, or an issue could say anything, so only your own prompt counts. When you say yes in other words, the agent asks you to type it; in Claude Code it may call the matching aidd MCP tool instead, and you click once in its dialog. The prompt hook cannot tell your prompt from a message another agent session sends to this one. So the guard denies each way an agent could send one, whether through another agent's prompt, keystrokes into a terminal, or an orchestrator's message.

### Always on, never in the way

The loop stays on, and nothing in it stops your work unless you choose enforce mode. What changes is who takes each step:

| Level | Who takes each step | A missed step |
| --- | --- | --- |
| Guided (solo and team, the default) | the agents follow the loop, and you approve | a note to the agent, once a session |
| Autonomous (`approve all`) | the agents also record each approval for you | the same note |
| Enforced (org and audited, or `mode: enforce`) | as guided | a stop |

In a hurry? Say so, with "skip the Spec" or "just do it". The agent skips that step for this change alone, and writes your words in its commit as `Aidd-Skipped: spec: just do it`. The gate's report shows the skip, and it never fails the change for it. Nothing stays off for you to forget. [METHOD.md](METHOD.md#always-on) says more.

### Hands-off: approve all

**Goal.** The aidd-team runs like a small software company. You set the direction, and the agents take each change from Spec to the trunk.

1. Type `approve all`. From then on, the agent records each Spec approval and Merge approval for you, and each record cites your standing approval. Type `approve all but major` to keep major changes for yourself, such as authentication, migrations, secrets, payments, personal data, and `.aidd/` or CI.
   `approve all` lands work on your local trunk, and nothing leaves your machine. To let the agents push and open each pull request too, type `approve all and publish`.
2. Give the team a goal with `/aidd-team:autopilot <goal>`. It plans the goal, and stops for you to agree to the plan. Then it builds each change, verifies and reviews it, records the approval, and runs `aidd land`. On a platform trunk, it runs `aidd publish` instead, then merges there. `aidd land` runs the tests again on what will land, and merges only if the gate passes.
3. Type `stop approving` at any time. Each approval then waits for you again.

Tests before code still hold, and so do the scope and the route the gate computes from the diff. The status pane and `aidd list` show that a standing approval is on, and since when. Only you start one, because the guard denies an agent's `aidd approve all`, and the command refuses in a shell an agent started. With a platform, the agent posts each approval on the pull request as you, and the pull request merges once `aidd/gate` passes, when you turn on its auto-merge.

**Before you start, put the rails up.** The agents take each change the standing approval covers to the base branch, so make sure the rest still catches what matters:

1. Name the paths that matter here, such as billing, auth, and customer data, in `risk_rules`, so a change to them is major. Start with `approve all but major`, which keeps major changes for you.
2. On GitHub, set `mode: enforce`, require the `aidd/gate` check on the base branch, and allow auto-merge in the repository's settings. aidd then turns on each pull request's auto-merge when it approves it for you, so it merges once the gate passes, with no merge of yours. On GitLab, aidd doesn't approve or merge for you yet, so you merge each merge request.
3. Where the Approvers are platform logins such as `@you`, aidd records your login with the standing approval, read from your own `gh` sign-in. If neither your login nor your email is an Approver, `approve all` says so and records nothing.
4. `aidd doctor` names a rail that is missing while a standing approval is on.

On GitHub, `stop approving` turns off the auto-merge your standing approval turned on, on every open pull request. One you approved yourself with `merge it` keeps its auto-merge.

**Done when** a change goes from goal to the trunk with no step of yours, and `stop approving` hands every approval back.

### A new GitHub repository, run by the team

**Goal.** The team works in the open on GitHub, from Spec to merged pull request, while you keep the plan and the launches.

1. `aidd init --ci github`, then import the ruleset and create the gate App, as init prints. The ruleset requires `aidd/gate` on the base branch.
2. Set `publish: agents` in `.aidd/config.yaml` and land that change. Agents then push their branches and open their pull requests.
3. Type `approve all and publish`, or `approve all and publish, but major`.

Each change then runs on its own. It's specified, approved for you, built, verified, reviewed, published as a pull request, gated by CI, and auto-merged. Without `publish: agents`, the same words publish for you, one reviewed change at a time. The digest shows each decision made for you, and `stop approving` ends it.

## The team as your software company

**Goal.** You work with the aidd-team as a client works with a software company. You decide what is built, whether it lands, and when it leaves your machine, and the team decides how.

| A client and an agency | You and the aidd-team |
| --- | --- |
| The scope or roadmap sign-off | D1, the plan |
| Requirements and acceptance criteria, signed off | D2, Spec approval: it names the commit, which freezes them |
| Acceptance testing of the delivered work | D3, the release: the Merge approval page leads with Acceptance against the verifier's run |
| Go-live | D4, the launch of a flagged feature |
| A change request, priced and approved | a change order: `aidd revise`, then Spec approval again |
| The delivery manager, the one point of contact | the lead: the session that runs the team, with the `delivery-manager` role for status and risks |
| The vendor's code review and QA | the verifier, the reviewer, and the gate: evidence, never an approval |
| The weekly status report | `aidd digest` (`--client` for the plain-words view), and the pane |

How you work with it:

- **Talk to the lead.** Give it intent and limits, such as the plan, the Spec, the route, and `approve all but major`. The lead brings back one decision card, with its recommendation, for each thing [only you decide](METHOD.md#decision-rights).
- **Or talk to any role directly.** It answers questions from the files. A change to what you approved becomes a change order, never a quiet addition, and the role records your ask in its handoff note, so the lead sees it.
- **Pick how close you stay.** Approve each Spec and each release, as on a formal fixed-price project. Or type `approve all but major` and keep major changes, the plan, and launches, as with a trusted team. Or keep only the plan and launches under `approve all`, as on a retainer.
- **A person who leads the team is an Approver for their area** in `owners.paths`, as a vendor's human tech lead would be. An agent never approves, at any level, and the lead takes only the team's own decisions, each on its evidence.

**Done when** you decide only the four decisions and the change orders, and the team handles everything between them.

### Fully delegate: you set the goal, the team decides the rest

**Goal.** You say what you want built, in your own words, and the team makes every technical choice. This suits a founder, a product lead, or anyone who wants the result rather than the details. You decide only what no standard can settle for you.

1. Adopt aidd with the team by running `aidd init --profile solo --team`. Then type `approve all`.
2. Say what you want, such as `/aidd-team:autopilot "Let customers book a table online"`. The team plans it in plain words, and stops once for you to agree to the plan.
3. The team builds it. It settles on its own every choice a standard, the project's rules, or aidd's defaults answer, such as the database, the libraries, the names, and the limits. It lists each one, with what settled it, under **What we decided for you** in `aidd digest --client`.
4. You decide only what's yours. That's the plan, the launch of anything users see, a change to what you agreed, and anything outside the code, such as an account or a payment. Each comes as one question in plain words, with the team's recommendation.

| When | What you do |
| --- | --- |
| You disagree with a decision the team made | Say so in your own words: it becomes a change order, and the team redoes that part |
| You want something more or different | Say it: a change to an agreed plan or Spec comes back once, as a change order for you to agree to |
| Something breaks for users | Say so: the team repairs it on the emergency route first, and writes the follow-up after |
| You are away | Nothing you must decide happens without you: the work waits at that step, and `aidd list --waiting-on-me` lists it |
| You want a spending limit | Set `autopilot.max_cost` and `autopilot.timebox` in `.aidd/config.yaml` ([Autopilot](AUTOPILOT.md#limits-and-settings)) |

**Done when** you made only the decisions in the table, and you can read what the team decided for you in plain words.

## Team

**Goal.** A human decides *what* gets built before agents build it, and someone other than the author decides *what* merges.

Agents do the building, so a small team is enough to deliver a real product. The team profile needs somebody other than the author to approve each change, which is the four-eyes principle. It also needs a `security` specialist Approver pool before a major change can land. Nobody approves their own change, so a pool of one can never approve a major change that its only member wrote. Every config or CI change is major, too. So name at least two people in every specialist pool, and `aidd doctor` warns about a pool of one. That sets the minimum at two people, both in the `security` pool; one person uses [solo](#individual-solo), with or without a [platform](#local-first-no-github-or-gitlab).

### Roll it out in three weeks

**Week 1: advisory.**

1. `aidd init --profile team --approvers @org/leads --specialist security=@org/security --test "<tests>"`.
2. The team profile starts in advisory mode. The gate reports on `aidd/gate (advisory)`, the guard notes what is outside the rules, and neither blocks. No agent approves, lands, merges, or publishes for a person in any mode.
3. Read `aidd metrics` from the gate events, as [Reading the metrics](#reading-the-metrics) explains. Move on when the would-block share in `aidd metrics` is low, and you agree with the blocks it reports.

**Week 2: enforce.**

1. Set `mode: enforce` in `.aidd/config.yaml`, and require `aidd/gate`. The workflow's `mode` input applies only when the config sets no mode. A private repository on GitHub Free can't require the check, so there the gate stays advisory. See [what holds without it](PLATFORMS.md#what-holds-without-the-full-setup).
2. Adopt the Spec-first draft PR/MR habit for normal changes.
3. Add `identities.bots` for agent bot accounts.

**Week 3: tune.**

1. Add `risk_rules` for your sensitive paths, such as payments or PII.
2. Add `standard_changes` for bot dependency patches, as the [FAQ](FAQ.md#bots) shows.
3. Add `changed_lines_exclude_paths` for generated code and `owners.paths` for per-directory Approvers.

**Done when:**

- the first-pass test rate is stable
- the gate rarely has to raise a route the agent set too low
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
| Engineer | authors most changes; Merge approval of the tech lead's changes | `/aidd-team:specify`, `implement`, `verify`, `review`, `sweep` | the CLI and the plugins |

```yaml
profile: team
goal: checkout succeeds on the first try

owners:
  approvers: ["@product-lead", "@tech-lead", "@engineer"]
  specialists: {security: ["@tech-lead", "@engineer"]}  # two humans, so either one's major change can land

  paths:
    - paths: ["docs/architecture/**", "docs/adr/**", "schemas/**"]
      approvers: ["@tech-lead"]

agents:
  proactive_roles: []  # several people's agents: only humans start work; the product lead plans on purpose
```

**How they work together.**

- **One change, one branch, one author.** The person who asked their agents for a change is its author. Everything their agents do is that person's change, marked by `Assisted-by:`. Nobody's agents push to someone else's branch.
- **Nobody approves their own work.** A change gets its Merge approval from someone who did not write it. A Spec can narrow who approves it with its own `approvers`, such as `["@product-lead"]` for a product change and `["@tech-lead"]` for a design change.
- **One queue, where everyone already looks.** Pull requests that wait for a review are the queue. `aidd list --branch` shows each person the next step on their branch. It warns when another branch's Spec changes the same code, with a line like "SPEC-2 overlaps SPEC-1 on alice/cart". So the two people agree who goes first, before their agents collide. The later change waits, `blocked` on the first.
- **Everyone's agents, one team definition.** Each person runs their own agent sessions. But the roles, the config, the skill, and the standards are shared, and change only through the gate. Each change gets its own branch or worktree, so parallel agents never share files.
- **Spend in proportion.** A minor fix is one agent, not the team. The specialists run only when their start condition holds, whoever's session it is.

**When only some of them use agents.**

- The gate judges every pull request, including the ones a person writes by hand. Those declare `assisted_by: []` or carry `Assisted-by: none`, and a small change needs only the short Change Request block that `aidd describe` prints.
- The product lead never needs the CLI to take part. They approve on the pull request, and a Spec is a Markdown file they can read and comment on.
- Start in advisory mode, so whoever does not use agents yet sees what the gate would say before it blocks anything.

**Growing.** Add humans to `owners.approvers`. Give an area its own owners in `owners.paths` once someone owns it. Bind specialist pools such as `security`, `privacy`, and `data` once two humans can hold each.

### A medium team: five to nine people

This is the "two-pizza team", small enough that everyone knows everyone's work, and big enough that one person can't review it all. Here's a worked example of eight people building a checkout product, in one repository with a web app and an API:

| People | Decide | Own |
| --- | --- | --- |
| Product lead | proposals, the plan, Spec approval of product changes | the goal, `proposals/`, the Initiatives |
| Designer | Spec approval of changes to what users see | the design files and prototypes |
| Tech lead | Spec approval of design changes; the security pool, with the platform engineer | `docs/architecture/`, `schemas/` |
| Four engineers, two on `web/` and two on `api/` | Merge approval of each other's changes, within their area | `web/` or `api/` |
| Platform engineer | Merge approval of infrastructure changes; the incident commander on call | `infra/`, and the deploy commands held for a person |

```yaml
profile: team
goal: checkout succeeds on the first try

owners:
  approvers: ["@org/checkout"]  # the whole team; nobody approves their own change
  codeowners: true  # per-area approvers from CODEOWNERS
  specialists: {security: ["@tech-lead", "@platform-engineer"], privacy: ["@product-lead", "@designer"]}

  paths:
    - paths: ["infra/**"]
      approvers: ["@platform-engineer"]

gates:
  approvals: {major: 2}  # two human approvals on anything the gate calls major

tests:
  - name: web
    command: [pnpm, --dir, web, test]
    when_changed: ["web/**"]

  - name: api
    command: [uv, run, --directory, api, pytest]
    when_changed: ["api/**"]

standard_changes:
  - name: dependency updates
    paths: [web/package.json, web/pnpm-lock.yaml, api/pyproject.toml, api/uv.lock]
    authors: ["dependabot[bot]"]

guard:
  held_commands:
    - name: production deploy
      match: [deploy, production]
      environment: production
      requires: RELEASE_APPROVAL
```

**What changes from three people.**

- **Ownership by area.** CODEOWNERS routes each change to the people who own the code it touches, and the gate requires one of them to approve. An engineer's agents on `web/` never need an approval from `api/`.
- **Each area runs only its own tests.** `when_changed` keeps an `api/` change from waiting on the web suite.
- **The routine is automatic.** Dependency updates from a bot merge on green tests as standard changes; nobody approves them by hand. A production deploy waits for a person, whoever's agent asks.
- **More parallel work, more overlap.** Eight people's agents on one repository collide more often. `aidd list --branch` and `aidd gate` warn when two branches change the same code, and the later change waits.
- **Look at the flow every week.** `aidd metrics` shows where changes wait and for whom, `aidd metrics --dora --specs specs` how delivery is doing against your `targets`, and `aidd metrics --autonomy` which agents have earned lighter review. The agile coach's retrospective turns the answers into changes. A [scheduled job](HOW-TO.md#run-the-routine-checks-on-a-schedule) can run these for you.

For more than one team, read [Organization](#organization).

## New teammate

This is for you if you're joining a team that already uses aidd. The team lead pairs you with one person for the week.

- [ ] Read [TEAM.md](TEAM.md) for the roles and the loop. Read [GLOSSARY.md](GLOSSARY.md) for the words the team uses, such as Spec, Acceptance id, route, and the two approvals.
- [ ] Run the [Quickstart](QUICKSTART.md) once in a scratch repository, from `aidd init` to `aidd land`, so the commands are familiar before they matter.
- [ ] With your pair, shadow one Spec from Specify to Roll out. Read the Spec and its tests before Spec approval, and watch the agent implement and verify. Read the gate's report at Merge approval, and watch the observe window.
- [ ] Learn the two approvals, Spec approval and Merge approval, and who holds which pool. See `owners.approvers` and `owners.specialists` in `.aidd/config.yaml`, and `aidd owners` for the owners by path.
- [ ] Find the runbooks in `docs/runbooks/` for the services you'll be on call for, and the postmortems of their last incidents in `docs/postmortems/`.
- [ ] Before you approve anything, get the team lead to add you to the Approver list. An agent never does that.

This week is also the team's AI-literacy measure under Article 4 of the EU AI Act, as amended by Regulation (EU) 2026/1744. The article still asks each provider and deployer of AI systems to take measures for its staff's AI literacy. So the team lead keeps a dated note of who finished the checklist and when, such as a line in the team's onboarding log.

## Multiplayer: one team, humans and agents

A team that shares its agents gets more from them than the same people each running their own. Everyone reads the same context, so nobody has to rediscover it. The work shows up where everyone can review it, and trust can be earned and recorded. Four habits make that work, and each one maps onto something aidd already has:

| Habit | What it means | In aidd |
| --- | --- | --- |
| Work in public, with broad context | Agents and humans read the same instructions and write to the same place | One committed `.aidd/config.yaml`, AGENTS.md, skill, and hooks for everyone. Specs and decisions live in the repository. Every role ends with a handoff note where the team works (on the PR/MR when there is a platform) |
| Clear roles, with the tools for each | Everyone knows who owns what, and each agent can do its job and nothing more | `owners` for the humans; the delivery team's roles, each with its write area enforced by the guard; `aidd owners` shows both |
| A written goal | One goal everyone steers by | `goal` in the config; agents weigh open choices against it, and `aidd observe --band` writes it into the draft Specs it opens |
| Release gradually | An agent gets more autonomy as it proves reliable, and one agent checks another's work | The spec lane first, then the fast lane, then standard changes earned from `aidd metrics --autonomy`. The Verifier and the reviewer check the implementer's work, and the gate checks everyone's |

**Check readiness.** Five questions tell whether a team is ready to work with agents, and aidd answers each from the repository. `aidd doctor` checks the first four, and `aidd owners` shows the fifth next to who decides and who works. Run both when the team forms and whenever someone joins.

1. Is the work written down where everyone can read it? The config and the Specs.
2. Does every decision have a named owner? `owners.approvers`.
3. Does everyone have the same tools? `AGENTS.md` and the skill.
4. Do tests and a rubric check the key work? `tests` and `REVIEW.md`.
5. Is there a goal? Set it with `aidd init --goal` or `goal` in the config.

**Avoid a fleet of personal agents.** When each person runs a private agent with private instructions, the context splits apart. Then the same work gets done twice, and nobody can see what an agent did. Keep one shared config, skill, and set of roles, and change them through the gate like any other change. Give each agent its own bot account in `identities.bots`, so its commits are attributed to it and it can never approve.

**Earn autonomy with evidence.** `aidd metrics --autonomy` groups the gate events by agent, read from `Assisted-by:`, and by kind of change. It puts each group on one of three stages:

1. *Review every change.* Every agent and every new kind of work starts here.
2. *Review the trade-offs.* The group has enough changes, enough of them passing on the first try, with no failures and no Spec rework. Reviewers focus on the decisions rather than every line.
3. *Candidate standard change.* The group has more changes and a higher first-try share, still with no failures or rework. A human may add the class to `standard_changes`, through the gate, so it merges on green tests.

How many changes and what share each stage needs are set in `agents.autonomy`; the defaults are in [CONFIG.md](CONFIG.md#mission-goal-and-agents). A single failure or reworked Spec sends the group back to stage 1. The report only suggests a stage. A person decides, and the change to `standard_changes` goes through the gate like any other, as [Proposing a standard change](#proposing-a-standard-change) shows.

**Let the right agents suggest work.** `agents.proactive_roles` names the roles that may suggest work nobody asked for. By default they're product-manager, agile-coach, and sre. They suggest it only as a draft Spec that a human triages. The other roles work only when asked. Set `proactive_roles: []` to have no agent propose anything.

**Ask humans in batches, and in the open.** Each role gathers what only a human can answer into the `Needs` line of its handoff note. It does not interrupt with one question at a time. The note and the gate's decision appear on the PR/MR, and with no platform `aidd list` shows what waits for whom. To reach people where they already talk, the [notifier template](PLATFORMS.md#notifications) posts to Slack or Teams. Or subscribe a channel to the PR/MR through the platform's own integration.

## Domain experts as specialist Approvers

Some changes need a person who knows the business, not only the code:

- a payments specialist for how money moves
- a clinician for a dosage calculation
- a tax adviser for invoicing rules
- a lawyer for consent text

In aidd a domain expert is a person in a named specialist Approver pool. No agent role stands in for one. The delivery team's compliance analyst or security engineer drafts and flags, and the expert decides.

1. **Name the pool** in `owners.specialists`, beside `security`. Any name works.
2. **Point a risk rule at it.** A rule names, in `specialists`, the pools that must approve what it matches. A rule that makes a change major asks them through the major route; a rule below major asks them on any route, so a small change is reviewed by the expert too.
3. **The expert approves on the PR/MR**, like any Approver, on the head commit. They need no CLI, and they can block a change by requesting changes.

```yaml
owners:
  approvers: ["@org/engineering"]
  specialists:
    security: ["@org/security"]
    clinical: ["@org/clinical-safety"]
risk_rules:
  - name: dosage
    paths: ["src/dosing/**"]
    route: major
    specialists: [clinical]
```

With this, every change to `src/dosing/` is major and waits for an approval from the `clinical` pool, on top of the usual Merge approval.

- **From the team profile up**, each named pool must give one approval, through `specialist_approvals`. Under `audited`, the pool also approves the Spec before any code. Under `solo`, no pool is required.
- **The built-in dimensions** already name their pools. `financial` changes go to `finance`, and `data`, `privacy`, `security`, and `compliance` go to pools of the same name, as [METHOD.md §6](METHOD.md#6-routes) lists. Bind a person to each pool your work touches.
- **An unbound pool** falls back to `security`. So bind the expert's pool before the rule goes live, or the security pool gets their reviews.
- **Asked by what the change does.** A rule's `content` holds regular expressions that the gate searches in the lines a diff adds, in the files its `paths` match. A team that asks its DBA about raw SQL writes:

  ```yaml
  risk_rules:
    - name: raw-sql
      paths: ["src/**/*.py"]
      content: ['\.execute\(\s*f["'']']
      specialists: [data]
  ```

  A change of any size that adds such a line waits for the `data` pool; one that only touches the file does not. The CI adapter and the local gate read the added lines with git. `aidd gate --paths` cannot see code that does not exist yet, so a plan's forecast never shows a content rule.
- **Few experts, many changes.** Keep the rule's `paths` narrow, so the expert sees only the changes that need them. Ask for their review on the PR/MR, so the platform tells them. The gate's report names the pool a change waits for.

## Project constraints and rules

Agents follow the rules they can read. Write the project's constraints once, in `project` of `.aidd/config.yaml`, and every role sees them. The architect designs within them, the reviewer flags what breaks them, and the SRE spends within the budget. They change through a change like the rest of the config.

```yaml
project:
  hosting: one VPS in the EU

  stack:  # a technology radar
    adopt: [Python, PostgreSQL, pytest]
    trial: [htmx]
    hold: [MongoDB]  # not for new work without an ADR and a person's decision

  budget:
    max_infra_per_month: 50
    currency: EUR
    new_paid_service: ask  # or "allowed", "forbidden"

  rules:
    - id: money-in-minor-units  # stable: a waiver names it
      level: must  # must, should, may (BCP 14)
      statement: Store money as an integer count of the currency's minor unit.
      why: Floats lose minor units on rounding.
      applies: ["src/billing/**"]  # omit for the whole repository
      check: unit  # the command or `tests` name that enforces it
      source: docs/adr/0002-money.md
      owner: "@alice"
      review_due: "2027-03-01"

  waivers:
    - rule: money-in-minor-units
      reason: The legacy export still reads floats until its rewrite.
      approved_by: "@alice"  # a person, never an agent or a bot
      until: "2026-12-31"
```

- **Read.** `aidd gate --paths src/billing/refund.py` and `aidd owners --changed <path>` print the stack in one line and the rules whose `applies` match, must first, each with its why and any waiver in force.
- **Checked.** `aidd validate` fails on a repeated rule id, a waiver of an unknown rule, a waiver an agent or bot approved, and a waiver past its `until`. It warns 14 days before a waiver expires, and once a rule's `review_due` has passed. When a Spec's Context or Design names a `hold` technology and links no ADR, it warns, though that's a text match and only a hint. It also warns when a Spec gives no `cost_estimate`, such as `{monthly: "40 EUR", at_10x: "300 EUR"}`, if its Task scopes hit the `baseline:iac` paths or its risk names `cost`. It reads the estimate from the Spec's `cost_estimate`. It also warns when the monthly estimate, in the budget's currency, is above `max_infra_per_month`. The gate never reads `project`; a rule is enforced by its `check`, or by a reviewer.
- **Layered.** An org preset that lists `project` in `locks` binds its rules. A repository adds its own, and may raise a rule from should to must, but never lower one. Nor may it waive a locked rule, adopt what the preset holds, or raise the budget.
- **Started.** `aidd init` writes the stacks and test runners it detected as a commented `project.stack`, for you to uncomment and edit. It never guesses the hosting, the budget, or the rules.

[CONFIG.md](CONFIG.md#project) covers it field by field.

## Proposals: bids and internal cases

A software agency writes proposals to win work, and any company writes them to get a change approved. Both are the same [object in aidd](METHOD.md#47-proposal), with `audience: client` or `"internal"`.

1. **Qualify.** Run `aidd new proposal PROP-12 --title "Checkout rebuild for Acme" --addressee "Acme Corp"`. For an internal case, use `--audience internal --addressee "the executive committee"`. The product manager writes the goal, the needs with their sources, and the questions, and a person records go or no-go with `aidd proposal decide PROP-12 go` or `no-go`. Most of the saving is here, because a quick no-go costs an hour and a lost bid costs weeks.
2. **Draft in parallel.** `/aidd-team:propose` runs the specialists at once, each writing its own file in the proposal's folder. The files cover architecture and the estimate, experience, security, compliance, and operations. The tech writer makes it one document, and `aidd proposal matrix` renders the needs, options, estimate, assumptions, exclusions, risks, and open questions as tables.
3. **Sign off and send.** A person reviews the needs that are not fully met, the range, the assumptions, and the exclusions, and sets the price. That person types `/aidd sign-off PROP-12`, or says so to the agent and confirms in its dialog, or runs `aidd proposal sign-off PROP-12`. Each records `sign_off` with the proposal's hash. No agent sets a price or commits the company. After sign-off, a change needs a change order the client approves, then a new sign-off.
4. **Deliver what you promised.** Accepted, `aidd proposal convert` makes an Initiative and one Epic per group of needs; every Spec under them traces back to the proposal.

Keep each client's proposals where only the people cleared for that client can read them. For example, use one private repository per client or per bid. Never let an agent copy one client's material into another's proposal. Record each outcome as `accepted`, `rejected`, or `withdrawn`. Then compare past estimates with what delivery took, because that's the reference class the next estimate starts from.

## Several teams

**Goal.** Each team owns its own area of the code, and the teams that support them are named in the config, not in a chart nobody reads.

Team Topologies (Skelton and Pais, 2019, with a second edition in 2025) names four kinds of team. Each one maps onto config aidd already reads, so you add no new object:

| Team Topologies | In aidd | What you set |
| --- | --- | --- |
| Stream-aligned team, which delivers one flow of work end to end | one area of the code, its approvers, its tests, and its own work | an `owners.paths` entry for its area, with its approvers; the same `owner_team` on its Initiatives, Epics, and Specs, which `owners.default_owner_team` writes; and `tests` entries with `when_changed` for its paths |
| Platform team, which offers a service the other teams use | the humans who own the org preset | the preset, the CI templates, and the managed settings, as [Organization](#organization) shows |
| Enabling team, which helps the other teams learn a practice | the agile coach, the practice skills, and the shared standards | the `agile-coach` role's retrospectives, the `aidd-team` practice skills, and `standards` entries, with `when_changed` where one applies to a single area |
| Complicated-subsystem team, which owns a part only specialists can change safely | a specialist Approver pool | a pool in `owners.specialists`, named in the `specialists` of the `risk_rules` entry that matches its part, as [Domain experts as specialist Approvers](#domain-experts-as-specialist-approvers) shows |

Work that crosses two stream-aligned teams follows the [Multi-team module](METHOD.md#102-modules). Its Epic holds the shared glossary, and a Spec that waits for the other team names it in `depends_on` as `team:ID`. Each area's approvers approve what touches it, because `owners.paths` asks for them. On the agent side, each area gets one delivery team, as [TEAM.md](TEAM.md#at-scale) says.

Growth adds Approvers, owners, and presets, never a second loop. So a new team is a new `owners.paths` entry and a new `owner_team`, and every team keeps the same Spec, gate, and decisions ([METHOD §10.1](METHOD.md#101-one-loop-at-every-scale)).

## Organization

**Goal.** Many repositories and teams share one policy baseline, and the security and platform teams review every major change.

When several teams share code, services, and rules, the team setup stays the same inside each team, and a few things are added above it. Take a worked example of forty repositories, six product teams like the [medium team](#a-medium-team-five-to-nine-people), a platform team, a security team, and a compliance function.

| Who | Owns | How aidd holds it |
| --- | --- | --- |
| Platform team | the org preset, the CI templates, the plugin marketplace, the managed settings | a baseline every repository inherits and cannot loosen (the steps below); managed settings require the plugins on every machine |
| Security team | the `security` pool, protected paths, the Policy (freezes and deny lists) | major changes in any repository need one of them; the preset binds the pool and the Policy |
| Compliance | the `audited` profile where the law requires it, the audit evidence | the gate record per change, mapped in [Controls](CONTROLS.md) |
| Domain experts | the pools for their areas (payments, clinical safety, tax) | risk rules in the preset send each area's major changes to its pool ([Domain experts as specialist Approvers](#domain-experts-as-specialist-approvers)) |
| Each product team | its repositories, its approvers, its goal | its own config, which may only tighten the preset |
| Leadership | proposals that ask for money or cross team lines | Proposals with `audience: internal`, decided go/no-go and signed off by a person |

**What changes from one team.**

- **One baseline, many teams.** The org preset sets the profile, the protected paths, the risk rules, the specialist pools, and the Policy once. A team can tighten it, never loosen it, and the platform team changes it through the gate like any change.
- **Work across teams.** An Epic whose Specs name two or more `owner_team`s holds the shared glossary in its `context`. A Spec that waits for another team's work names it in `depends_on` as `team:ID`. The changes of one piece of work across repositories share a `trace_id`, so their records can be joined. `aidd list api web infra` shows every repository's next step.
- **Evidence nobody can touch.** Tests run in a central required workflow, and the gate accepts only its attested evidence, as step 4 sets up.
- **Measure per team, compare per service.** `aidd metrics --by team` shows where each team's changes wait; `aidd metrics --dora` compares each service with its own targets, not teams with each other.

**1. Write the org preset** in `aidd-org-preset.yaml`, in a repository only the platform team can change. It holds:

- `profile: org`, the profile every repository inherits
- org-wide `risk_rules` and `protected_paths`, the sensitive and protected areas every repository shares
- `owners.specialists`, the specialist Approver pools that approve high-risk changes, such as security, data, privacy, finance, compliance, and any domain experts' pools
- a Policy command, a script of yours the gate runs to enforce freeze calendars and deny lists
- `standards_policy`, which says which library standards every repository carries with `require`, may not add with `exclude`, or replaces with the company's own with `replace`, and which stacks it allows with `allow_stacks`. `aidd doctor` fails on a breach, as [Standards](STANDARDS.md#a-companys-policy) explains.

A repository can only tighten the preset. It cannot replace its specialist Approvers, Policy, evidence source, or identity exemptions.

**2. Apply it in one of two ways:**

| Topic | `extends` in each repo config | `org-preset-url` on the reusable workflow |
| --- | --- | --- |
| How | `extends: [{url: "https://<host>/aidd-org-preset.yaml", sha256: "<digest>"}]` | in each `aidd-gate.yml`: `org-preset-url: https://<host>/aidd-org-preset.yaml` and `org-preset-sha256: <digest>` |
| Opt-out | a repo edits its config (protected, major) | a repo edits its gate workflow (protected, major) |
| Change | bump the pin in each repo | bump the pin in each caller, or roll the caller out centrally |

Write the pin literally in the file, never through a repository variable. A repository admin can override variables without a pull request. For a guarantee that no repository can edit, put the caller in a platform repository. Make it an organization **required workflow** there, through a ruleset rule.

**3. Roll out in waves.** The org profile starts in enforce mode, so set `mode: advisory` in each repository's config for the pilot.

1. Install the gate's GitHub App on the organization, and store `AIDD_APP_ID` as an organization variable. Keep `AIDD_APP_PRIVATE_KEY` only in each repository's `aidd-gate` environment. [PLATFORMS.md](PLATFORMS.md#setup) has every step, and [METHOD.md §14](METHOD.md#14-platform-bindings-and-trust) says why it is never an organization secret.
2. Use `aidd init --profile org --approvers <handles> --specialist security=<handles> --test "<command>" --policy "<command>"` to open the setup PR in each repository; the flags make it scriptable. When the preset binds the Policy instead, check with `AIDD_ORG_PRESET=aidd-org-preset.yaml aidd doctor`.
3. Pilot 3 repositories with `mode: advisory` for 2 weeks, then 20% of repositories, then all.
4. Enforce with an **organization ruleset** that requires `aidd/gate` from the App. Target repositories with a custom property such as `aidd = enforced`, so a wave is a property change and exemptions are explicit and auditable.

**4. Make evidence tamper-resistant, if you want to.** Run the tests from a central required workflow and require [its attestation](PLATFORMS.md#evidence-the-pull-request-cannot-touch).

**5. Operate.**

- Collect gate events centrally, from the workflow artifacts or by sending `--events` output to your log pipeline.
- Rotate the App private key on your normal secret schedule, with a script over the environments API. The gate reads it per run.
- Gate runs cost roughly 15 to 30 API calls each, under the App's installation rate limit. One installation per organization is shared by every repository. [ENTERPRISE.md](ENTERPRISE.md#10-cost) covers CI minutes, storage, and tokens.
- Upgrade by changing one pin, and the reusable workflow and the test action refs, the CLI, and the vendored skill move together.

**Done when:**

- 100% of protected branches require `aidd/gate`
- `aidd metrics --by team` shows the AI-assisted metrics per team, and `aidd metrics --dora --specs specs` the DORA proxies against your `targets`
- the Policy freeze is exercised once, including an emergency break-glass drill

## Compliance-ready by default

**Goal.** The product carries the controls that an enterprise buyer or an auditor asks about, from its first Spec. The evidence for each control is an export, not a project.

Say what the product must be ready for in `project.compliance`. `aidd init` writes the table commented out and asks nothing. `aidd init --compliance-target soc2 --compliance-target gdpr` writes it filled in, and the proposal's first questions ask the client for it. Compliance is on when `targets` names a framework or law, or when the profile is `audited`; there is no level to pick.

```yaml
project:
  compliance:
    targets: [soc2, gdpr]  # soc2, iso27001, gdpr, hipaa, pci-dss, fedramp, cra, other
```

The `cra` target is the EU Cyber Resilience Act. It needs `support_period: {ends: "YYYY-MM"}`, the last month of security updates, and `aidd validate` fails without it. It leans on two controls most. EC-08 is scanning and an SBOM per release, and EC-18 is vulnerability handling. `aidd new vulnerability-policy` writes the policy, and `aidd doctor` warns when the repository's `security.txt` is missing or its `Expires` is near.

| Compliance | What it turns on |
| --- | --- |
| off (no target, and a profile other than audited) | Nothing beyond the defaults every project gets. |
| on (any target, or the audited profile) | The `aidd-team:enterprise-controls` pack, named in `aidd gate --paths` and `aidd owners`, with its 19 controls as the default for every Spec. `aidd validate` warns when a change on a security or auth path links no threat model or authorization matrix, whatever its risk says. `aidd init` on GitHub writes `.github/workflows/aidd-security.yml` (dependency scan, static analysis, and an SBOM, each with a read-only token). ASVS Level 2 on authentication, session, and admin surfaces. |

A target that expects separation of duties, such as soc2, iso27001, pci-dss, fedramp, or hipaa, gets a warning from `aidd validate` under the `solo` profile. Solo waives it, so move to the team profile with a second approver before the audit.

Every project also gets `.github/dependabot.yml` for the ecosystems `aidd init` finds, and OWASP ASVS Level 1 as the default level of every Spec. It also gets a warning from `aidd validate` on a postmortem action item past its due date. Evidence by control is `aidd record export records <record dirs> --by-control`. Each Spec's compliance doc names its control ids, `EC-01` to `EC-19` or your own, in its Obligations table. The export [groups the gate records and the linked docs](CONTROLS.md#what-aidd-builds-into-the-product-when-compliance-is-on) under them.

**The readiness ladder.** Climb it one stage at a time; the pack's `references/readiness.md` lists what each stage needs.

| Stage | Compliance | The team builds | People outside the team |
| --- | --- | --- | --- |
| MVP | off | change management, secure coding, deny-by-default authorization, secrets in a manager, scanning, CI least privilege, TLS | name an owner for security questions |
| First paying customer | off, or on with the customer's targets | backups with a drilled restore, logging and security events, MFA and sessions, rate limits, incident response, vulnerability disclosure | a data processing agreement, the subprocessor list |
| First enterprise deal | on | all 19 controls and the enterprise-deal checklist: SSO, SCIM, audit log, admin console, IP allowlisting, residency, SLA and status page, trust center, VPAT | the security questionnaire, often a third-party penetration test |
| Certification | on, with the audit's targets | the same, with the evidence exported for the audit period | policies, the ISMS, vendor reviews, training, the penetration test, and the auditor |

aidd never certifies anything. An independent auditor issues a SOC 2 report or an ISO/IEC 27001 certificate. Most of what they examine beyond the product is organizational work outside the team.

## Audited

**Goal.** The audit trail proves who approved what, on which evidence, under which policy, for every AI-assisted change.

1. `profile: audited`. This means:
   - two Approvers and a specialist Approver approve every major change
   - a bound Policy is required on every route
   - every commit carries an `Assisted-by` trailer
   - an observe window after release is required on normal changes, not only major
   - no pre-approved standard change classes, so every change gets a human
2. Retain the gate records in `aidd-record.json`, the events, the evidence, and the logs for as long as your regime requires. The workflows keep them as artifacts [for a limited time](ENTERPRISE.md#6-audit-evidence). Send the records and the `--events` output to durable storage for anything longer.
3. Map controls with [CONTROLS.md](CONTROLS.md), and add your organization's control IDs to `risk_rules` names.
4. Add license and secret scanners to `tests`, so the gate enforces them.

## Many companies

**Goal.** Agencies, vendors, open-source maintainers, and groups of companies use one loop without any company deciding for another.

- **Each company owns its gate.** Its preset, approvers, specialist Approvers, Policy, and App or token stay inside it. Nothing is shared except the method's version and, when chosen, a public preset pinned by sha256.
- **Each company is a tenant.** Its org preset sets `tenant: "<company>"` and locks it with `locks: ["tenant"]`, so no repository moves itself to another company. Every gate record, event, and change record carries the tenant. `aidd metrics --tenant`, `aidd record export --tenant`, and `aidd record verify --tenant` read [one company's alone](ENTERPRISE.md#13-multi-tenancy).
- **An agency runs one tenant per client.** Each client's repositories name that client's tenant, and its preset names that client's Approvers. Write a pool entry or an identity as `<tenant>:<login>` when the same login works for two clients. An approval by an identity of another tenant never counts, and the gate says `merge_approval.other_tenant`, so one client's lead can't approve another client's change by accident.
- **Contributors from outside are authors.** A vendor's or agency's agents and humans open changes in the client's repository. The client's Approvers decide Spec approval and Merge approval. A person who works for several companies approves only where they sit in a pool.
- **Cross-company work shares a `trace_id`.** Each company gates its own child change; neither gate can pass the other's.
- **Compare without pooling.** Each company runs `aidd metrics --by repo --tenant <company>` on its own events. A group of companies that agrees to pool events uses `--by org`.

## Reading the metrics

On one machine, `aidd metrics` needs no file. Every local `aidd gate` run on a branch, and each `aidd land`, keeps its decision in `.git/aidd/events.jsonl`, which every worktree shares and git never commits. Each `aidd test` run keeps a test line there too, so the report shows the full suite runs per head, and the aim is one per independent reader. With `--specs`, it also counts the handoff notes a reader cannot use. The line is a record for a retrospective, never evidence. The gate, `aidd land`, and the guard never read it, and the client's digest from `aidd digest --client` leaves it out. A file over 8 MiB, a link in its place, or a held lock costs one warning, never the gate's answer. To start the history again, delete the file.

Every CI gate run uploads an artifact `aidd-gate-<run>-<pr>` holding `aidd-events.jsonl`. To summarize a repository:

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
| Median changed lines | `aidd metrics` | down, or stable under the changed-line limit |
| Median wait per approval, waits above `--target-wait` | `aidd metrics` | down; nothing above a day |
| Open changes waiting, per approval | `aidd metrics` | at or below the WIP limit per Approver |
| Time to first feedback (p50, p90), paired with the first-pass test rate | `aidd metrics` | down, while the first-pass test rate holds; within `max_first_feedback_minutes` |
| Approval wait p50 and p90 per approval, paired with Spec rework after Spec approval | `aidd metrics` | down, while rework stays flat; within `max_approval_wait_p90_minutes` |
| Flow efficiency (lead time not spent waiting on an approval), paired with the first-pass share | `aidd metrics` | up, while the first-pass share holds; at or above `min_flow_efficiency` |
| Cost per change, paired with the first-pass share | `aidd metrics --cost cost.jsonl` | stable or down; display only, never enforced |
| Major changes merge-approved within 10 minutes of the gate asking (`fast_major_merge_approvals`, a rubber-stamp signal) | `aidd metrics` | zero, or each one explained at the retrospective; it measures the gate's view of the wait, not reading time, and is never enforced |
| Throughput (passing changes per week) | `aidd metrics` | up, or stable while the size stays small |
| Change fail rate, recovery time (DORA proxies) | `aidd metrics --dora --specs specs` | down, and within `targets` |
| Lead time, deployment frequency, rework rate (DORA proxies) | `aidd metrics --dora` | stable or better after week 3, and within `targets` |
| Overdue incident reviews | `aidd validate` | zero |
| AI-assisted share of changes | `aidd metrics` | whatever the team chooses; read beside the first-pass test rate |

The DORA proxies come from gate events; pair them with your deployment data where it measures more directly. `aidd metrics --by author` serves agent autonomy and a person's self-review, never ranking or appraising people.

### Loop speed, and what each is paired with

`aidd metrics` computes only what the gate events support. It shows every speed metric beside the quality metric that it must not degrade, as METHOD §12.1 asks:

- **Time to first feedback** runs per head, from its push to the first gate decision on that head that holds its test results. The push time is `head_pushed_at`, or `opened_at` for a change's first head without one. A head the events cannot date gives no sample. Paired with the first-pass test rate.
- **Approval wait** is how many minutes each Spec approval, Merge approval, or specialist approval stayed pending. It runs from the first event that reported it pending to the first later event that did not. It is reported as p50 and nearest-rank p90. A wait still open at the last event is not counted. Paired with the share of approved Specs reworked after Spec approval, which rises when approvals are rushed.
- **Flow efficiency** is active time divided by lead time, over the changes that passed. Lead time runs from `opened_at`, or the first gate run, to the first pass. Waiting is the time between an event reporting an approval pending and the next event. Active is lead time minus waiting. It counts agent work, CI, and fix-ups as active, so it is an upper bound on touch time. Paired with the first-pass share.

Events written before these fields existed give no sample for them and never an error. `max_first_feedback_minutes`, `max_approval_wait_p90_minutes`, and `min_flow_efficiency` in `targets` make `aidd metrics` exit 1 when missed, as [Config](CONFIG.md#targets) explains.

### Cost per change

aidd calls no model and sees no bill, so the cost comes from the host. `aidd metrics events.jsonl --cost cost.jsonl` joins a cost log you export to the changes. One JSON object per line:

```json
{"ts": "2026-09-28T10:00:00Z", "amount": 0.42, "currency": "USD", "agent": "claude-code/claude-opus-5-5", "spec": "SPEC-42", "branch": "feat/login", "sha": "3f2a9c1"}
```

- **Fields.** `ts`, `amount`, and `currency` are required; `agent`, `spec`, `branch`, and `sha` are optional.
- **Joining.** An entry joins a change by its Spec id first. Then it joins by a commit, meaning seven or more hex digits that match a head the gate judged. Last, it joins by its branch, which is the change id for local and `--context` runs. An entry matching several changes is split evenly, and one matching none is shown as not joined.
- **Currencies.** Totals stay per currency, because aidd converts nothing.
- **A cap per change.** `targets.max_cost_per_change: {amount: 20, currency: "USD"}` makes `aidd metrics --cost` print a warning for each change whose cost in that currency is over it. `aidd metrics --cost` also lists them under `over_cap`, and the target is met when none is over.
- **Display only.** Cost is never a gate rule and never pauses an agent. A missed target or a change over the cap never changes the exit code.

To produce the cost log:

- **From a harness's usage export.** Most coding agents can export usage per session with its cost, time, and working directory or branch. Map each session to one line, with `branch` from the session's branch and `spec` from the Spec it worked on. Take the Spec from the `Spec:` line of its handoff note, or from the branch name when it carries the id. A `jq` filter over the export's JSON is usually enough.
- **From an orchestrator's cost API.** An orchestrator that runs agents per Task knows the Spec and the commit that each run produced. Write one line per run with `spec` and `sha`, from the API or a webhook. Put the lines in a file that the scheduled metrics job reads.

### Proposing a standard change

`aidd metrics events.jsonl --autonomy --suggest-standard-changes` prints a `standard_changes` entry for each agent and change type that meets the candidate-standard-change thresholds in `agents.autonomy`. A comment holds the evidence, which is the changes, how many passed, the first-pass share, and that none failed or had its Spec reworked.

It is a proposal. `.aidd/**` is protected, so a person merges it as a major change with its approvals. `paths` is left empty because gate events don't record paths, so the entry fails `aidd validate` until a person fills it.
