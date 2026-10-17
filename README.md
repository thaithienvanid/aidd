<p align="center">
  <img src="docs/assets/hero.svg" alt="AIDD, AI-Driven Development: you decide what to build and what ships, and AI agents do everything in between and prove it. Four decisions are yours: the plan, Spec approval, Merge approval, and the launch of a feature built behind a flag. Between them the AI team specifies, implements, verifies, and reviews on its own branches. A green aidd/gate, then Ship; Learn feeds every lesson back into the loop." width="100%">
</p>

<p align="center">
  <a href="#get-started"><b>Get started</b></a> ·
  <a href="docs/QUICKSTART.md"><b>Quickstart</b></a> ·
  <a href="docs/HOW-TO.md"><b>How do I…</b></a> ·
  <a href="docs/METHOD.md"><b>The method</b></a> ·
  <a href="docs/TEAM.md"><b>The delivery team</b></a> ·
  <a href="docs/FAQ.md"><b>FAQ</b></a>
</p>

**You decide what to build and what ships. An AI team does everything in between, and proves it.**

AIDD (AI-Driven Development) is a way of working with AI agents as a delivery team. You stay the stakeholder: you agree to the plan, approve each contract, and release the result. The agents plan, specify, build, test, and review their own work, on their own branches, inside rules they cannot bend.

**aidd** is the open-source toolkit that runs it. It gives your coding agent a skill, an optional team of agent roles, and a command-line tool. In <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->, a guard also checks each step the agent takes. A CI check, `aidd/gate`, lets work reach your main branch only on proof. It runs on GitHub, on GitLab, or on your own machine with nothing but git.

> [!IMPORTANT]
> **Pre-release.** aidd 1.0.0 is unreleased and Beta until it is tagged, published, and one pull request has passed this repository's own live gate. Until then, install it from a commit: [before the first release](docs/INSTALL.md#before-the-first-release). GitLab support is experimental. What is done, partial, and missing: [Enterprise readiness](docs/ENTERPRISE.md).

## Why AIDD

Agents can now write much of the code. The hard part is the rest: knowing what came back, whether it works, and who decided what. Left alone, the work drifts, "done" is claimed rather than shown, and nobody can later say which decisions a person made.

AIDD answers with a split. Four decisions are yours, and only these:

| | Your decision | When | What you look at |
| --- | --- | --- | --- |
| **D1** | **The plan** | before any code | what will be built, in which small goals, and in what order |
| **D2** | **Spec approval** | before each change is built | the contract: its intent, its scope, and the tests that define done |
| **D3** | **The release** | when work is ready for main | exactly what was built, with the proof that it works |
| **D4** | **The launch** | for a feature built behind a flag | when users see it |

Everything between them is the team's. A hash freezes each approved contract, and a guard keeps each agent to its own files. A change reaches main only when the tests prove it on the exact commit. An agent can never approve its own work.

## Get started

**Ask your agent.** In any agent that can run commands:

```text
Install thaithienvanid/aidd and apply it to this project.
```

It follows [llms-install.md](llms-install.md): it installs the CLI, sets up the repository for the agents it finds, checks the result, and commits. It asks which profile you want, and shows you what `aidd init --dry-run` proposes first. It stops at branch protection, which is yours to switch on.

**Or by hand.** The CLI needs Python 3.11+ and nothing else ([Install](docs/INSTALL.md#the-cli)):

```sh
aidd init --dry-run                                     # see what it proposes; writes nothing
aidd init --profile solo --approvers email:you@example.com --team
aidd doctor                                             # check the wiring
```

`aidd init` writes the config, the skill, and the CI workflows, and wires every coding agent it finds (<!-- aidd:gen count:harnesses -->26<!-- aidd:end --> are supported). `--team` adds the delivery team. For a team, use `--profile team --approvers @your-org/leads`. The gate starts in advisory mode, so it blocks nothing until you enforce it.

**In Claude Code**, we recommend the plugins:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill, the guard, and the commands
/plugin install aidd-team@aidd     # the delivery team (optional)
/plugin install aidd-mods@aidd     # the status pane (optional)
```

Only `/plugin install aidd@aidd` is needed; `/plugin install aidd-team@aidd` and the status pane are optional ([Claude Code plugins](docs/INSTALL.md#claude-code-plugins)). Every agent and what it needs: [Your coding agent](docs/INSTALL.md#your-coding-agent). No GitHub or GitLab yet? Run the whole loop on your machine: [Local-first](docs/ADOPTION.md#local-first-no-github-or-gitlab). Every part at once: [Use all of aidd](docs/INSTALL.md#use-all-of-aidd).

## How work flows

You say what you want, in your own words. The rest happens around your four decisions.

1. **Ask.** Tell your agent, or start the team: `/aidd-team:autopilot "let patients book a visit online"`.
2. **Agree to the plan (D1).** The product manager drafts a big goal and its small goals, each with its Specs. You read it and say go.
3. **Approve the contracts (D2).** Each Spec arrives with its tests, which fail because nothing is built yet. Type `approve SPEC-3`, or `approve` for every Spec that waits on you.
4. **The team builds.** Each Spec gets its own branch. Agents build, verify, and review, several Specs at once, until the tests pass on the exact commit.
5. **Release (D3).** When a small goal is ready, type `ship it`. The tests run once more on exactly what lands.
6. **Launch (D4).** For a feature built behind a flag, you decide when users see it.

Your typed words are the decision. aidd records `approve SPEC-3` or `ship it` the moment you type them, before the model reads the prompt, so no agent can say it for you. Type `approve all`, and the agents record D2 and D3 for you until you type `stop approving`. The plan and every launch stay yours.

In Claude Code, `/aidd status` opens a pane beside the conversation. It leads with the one decision that waits on you, and what to type:

```text
spec/SPEC-3  clinic · updated 10:42                         Refresh  Close
◆ D2 Spec approval  SPEC-3  Hold a slot while the patient pays
  type  approve SPEC-3   · 1 more waits on you

Shape of work                            D1 plan  D2 specs  D3 release  D4 launch
  INIT-1  Online booking  0/2 small goals done
    EPIC-1  Find a slot   incremental    ✓        ✓         1/2         —
    EPIC-2  Book and pay  flagged        ✓        ◆ 1/2     ·           ·

Flow  2 branches with unmerged work · oldest spec/SPEC-2, 1d
Autopilot  live · all · 3h left · last step spec.verify ok
```

The example is illustrative. One change with every command: [Quickstart](docs/QUICKSTART.md). A founder's whole day: [A solo day](docs/ADOPTION.md#a-solo-day).

### The loop

Every change runs one loop. You decide at the steps in bold.

| Step | Who | What happens |
| --- | --- | --- |
| Plan | agents draft, **you agree** | Only for work bigger than one change: a big goal, its small goals, and a Spec stub for each change. |
| Specify | agents | The Spec: the intent, the scope, the tests that define done, the risk, and the rollback. |
| **Spec approval** | **you** | You approve the Spec and its tests. A hash freezes them. |
| Implement ⟲ Verify | agents | They build inside the scope until the tests pass on the exact commit. |
| Review | agents | The change is read against the Spec before you see it. |
| **Merge approval** | **you** | You approve exactly what was built, once `aidd/gate` has checked the proof. |
| **Ship** | **you** | You decide that it ships and how it rolls out. |
| Learn | agents propose, **you** adopt | An incident, a rollback, or a missed goal becomes a new change at Plan. |

Not every change needs every step. Before the first edit, aidd sizes the change by the files it will touch. That size is its **route**, from `minor` to `major`, and the route picks a lane:

| Lane | For | You decide |
| --- | --- | --- |
| **Fast** | small fixes, and pre-approved routine changes such as a bot's dependency update | the result (nothing, for a pre-approved change) |
| **Spec** | anything worth planning | the Spec and the result, plus a specialist on a `major` change |
| **Emergency** | production is down, and a person declares it | that it is an emergency, and the result; the full review comes after |

The author can ask for more control, never less. Which role works at each step: [the loop diagram](docs/TEAM.md). The method in full: [docs/METHOD.md](docs/METHOD.md).

### Shapes of work

An ask becomes work of three sizes. A big goal (an Initiative) runs over weeks or months, and a small goal (an Epic) takes two weeks or less. A change (a Spec) is one reviewable change with its tests; a small fix needs no Spec. Each small goal says how it reaches users:

| It ships | When | How |
| --- | --- | --- |
| `incremental` (the default) | each piece is useful by itself | each Spec merges to main as soon as it is done |
| `flagged` | useful only when complete, and it can be hidden | each Spec merges behind a feature flag that stays off; a last launch Spec turns it on |
| `batched` | it must land at once and cannot be hidden | a goal branch: the team integrates each Spec into it, and you release it once |

Main stays the one trunk, as DORA's research recommends: few branches, each living hours or days. `aidd list` and the pane warn when a branch grows old. How the work items connect: [the method, §4](docs/METHOD.md#4-objects).

## Everyday commands

Everything aidd knows comes from git and the files in your repository: no server and no database. The commands a person types:

<!-- aidd:gen cli:everyday -->
| Command | When |
| --- | --- |
| `aidd hash --line`, or `aidd approve spec` | to get Spec approval: an Approver posts the line; with no platform, a person approves at the terminal |
| `aidd gate` | before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request |
| `aidd ship` | with no platform: merge a passing branch and record the Merge approval |
| `aidd list` | to see all open work and who holds each step; `--branch` for the change in hand |
<!-- aidd:end -->

`aidd list --waiting-on-me` is your inbox: only your decisions. `aidd goal list` shows each goal on the ladder of your four decisions. `aidd digest --since <tag>` writes a status report, or a client's view with `--client`, and `aidd metrics` shows where changes wait. Your agent runs the rest: the route before the first edit (`aidd gate --paths`), the Spec (`aidd new spec`), and the tests (`aidd test`). Every command: [CLI](docs/CLI.md#which-command-when).

## The delivery team

The team is optional: <!-- aidd:gen count:roles -->17<!-- aidd:end --> agent roles, from product manager to SRE, led by humans. Each role writes only its own files, and the tester never builds the code. Add it with `aidd init --team`, or with the `aidd-team` plugin in Claude Code. Run one command for each job; in Claude Code, each one is `/aidd-team:<name>`, for example `/aidd-team:specify`.

| When you want to… | Run |
| --- | --- |
| build one change | `specify`, `implement`, `verify`, then `review`; you approve the merge |
| fix a small bug | `fix` |
| clear review comments or red checks on a PR/MR | `sweep` |
| get a threat model or a security review | `secure` |
| turn a goal into Epics and Specs | `plan`, after `refine` trims a long backlog |
| pick between two or three designs | `explore` |
| go from a brief to a launched MVP | `mvp` |
| start in an existing repository | `onboard` |
| win and close client work | `propose` before it, `handover` at the end |
| watch a merged change roll out | `ship` |
| learn from an incident, or improve the loop | `postmortem`, `retro` |
| do the upkeep that is due | `maintain` |
| let the loop run between your decisions | `autopilot` |

Every command stops where a person decides. When to pick each one, and which roles it runs: [Commands and flows](docs/TEAM.md#commands-and-flows).

## How it stays honest

Two checks hold the agents to the loop, and neither trusts what an agent says about itself.

- **The guard** runs inside your agent, on every edit and command. It keeps each role to its own files, stops implementation before Spec approval, and denies an agent's attempt to approve, merge, or move a protected branch. To try an idea with free edits, a person starts an explore branch (`git switch -c explore/<topic>`); nothing merges from it until they rename it.
- **The gate**, `aidd/gate`, runs in your CI, or as `aidd gate` on your machine. It lets a change merge only when every rule holds for the exact commit. Its rules answer five questions:

<!-- aidd:gen rules:questions -->
| The gate asks | Its rules |
| --- | --- |
| Can the gate trust what it reads? | `context`, `internal`, `config`, `edited_comments` |
| Is the change what it says it is? | `change_request`, `spec`, `confidence`, `route`, `scope`, `budget`, `standard_change`, `explore`, `draft` |
| Is it proven on this commit? | `tests`, `red_green`, `merge_queue` |
| Did the right humans approve it? | `spec_approval`, `merge_approval`, `specialist_approval`, `authors` |
| Is it safe to ship? | `secrets`, `policy`, `policy:<rule>`, `emergency`, `observe`, `provenance` |
<!-- aidd:end -->

The gate reads only facts: the diff, your CI's results, and the approvals. Each run writes a record you can verify later. What holds before you enforce it: [Platforms](docs/PLATFORMS.md#what-holds-without-the-full-setup).

## From one person to a whole company

Pick a profile, and tighten it later. A repository can never loosen what its organization set.

| Profile | For | What it adds |
| --- | --- | --- |
| `solo` | one person directing agents | you approve your own work, on record; Spec approval only on major changes, after a 30-minute cool-off |
| `team` | one team or a few | Spec approval before building, an Approver who is not the author, a specialist on high-risk changes |
| `org` | many teams and repositories | organization rules on high-risk and emergency changes |
| `audited` | a SOC 2 or ISO 27001 audit, finance, health, public sector | two Approvers on high-risk changes, rules on every change, provenance on every commit |

Humans and agents share one config, one skill, and one set of roles. Rollout plans for each size: [Adoption](docs/ADOPTION.md).

## Works with what you have

aidd needs git and the repository. Everything else is optional, and aidd uses it only if you already have it.

- **Your agents.** The guard runs in <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->. Cursor, Copilot, and every other agent read `AGENTS.md` and the skill, and the gate still decides what merges ([the install table](docs/INSTALL.md#your-coding-agent)). Tools that run many agents side by side, such as [Orca](docs/ORCA.md), work as they are.
- **Your platform, if you have one.** GitHub or GitLab adds approvals the platform enforces, and aidd reuses CODEOWNERS, your CI checks, rulesets, and merge queues. With no platform, the [local-first path](docs/ADOPTION.md#local-first-no-github-or-gitlab) holds every decision on your machine.
- **Your planning tools.** Keep GitHub Spec Kit, OpenSpec, Kiro, or BMAD for planning. `aidd import` turns their plan into a Spec.
- **Knowledge.** <!-- aidd:gen count:packs -->22<!-- aidd:end --> domain packs, <!-- aidd:gen count:practices -->32<!-- aidd:end --> practice skills, and a library of standards and stacks: [Standards](docs/STANDARDS.md).

## What it does not do

aidd proves who decided what, on which evidence. It does not judge code quality for you: you still read what you release. It does not deploy, and it does not sandbox agents. The gate has not yet judged a live pull request. Every known limit: [Rationale](docs/RATIONALE.md#known-limits-in-100).

## Documentation

| Start | Understand | Operate |
| --- | --- | --- |
| [Quickstart](docs/QUICKSTART.md) | [The method](docs/METHOD.md) | [CLI](docs/CLI.md) |
| [How do I…](docs/HOW-TO.md) | [The loop, step by step](docs/METHOD.md#5-the-loop) | [Config](docs/CONFIG.md) |
| [Install](docs/INSTALL.md) | [The delivery team](docs/TEAM.md) | [Platforms](docs/PLATFORMS.md) |
| [Adoption](docs/ADOPTION.md) | [What the team covers](docs/TEAM-REFERENCE.md#what-the-team-covers) | [Autopilot](docs/AUTOPILOT.md) |
| [FAQ](docs/FAQ.md) | [Glossary](docs/GLOSSARY.md) | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| [Changelog](CHANGELOG.md) | [Rationale](docs/RATIONALE.md) | [Enterprise readiness](docs/ENTERPRISE.md) |
| [Contributing](CONTRIBUTING.md) | [Controls](docs/CONTROLS.md) | [Security](SECURITY.md) |
| [Extending: plugins, skills, packs](plugins/README.md) | [Architecture](docs/ARCHITECTURE.md) | [Governance](GOVERNANCE.md) |
| | | [Running inside Orca](docs/ORCA.md) |

Other projects also use the name AIDD. This one is `thaithienvanid/aidd` on GitHub, `aidd` on PyPI, and `aidd@aidd` in Claude Code. Apache-2.0. Open source, no runtime dependencies, no telemetry. The schemas and the conformance suite are the contract, so anyone can reimplement the gate anywhere.
