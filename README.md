<p align="center">
  <img src="docs/assets/hero.svg" alt="AIDD, AI-Driven Development: you decide what to build, what lands, and what leaves your machine, and AI agents do everything in between and prove it on the exact commit. Four decisions are yours: the plan, Spec approval, Merge approval (land it, on your local trunk), and the launch of a feature built behind a flag. On your machine the AI team specifies and implements until the tests pass, then verifies and reviews side by side on that exact commit, on its own branches. Nothing leaves your machine until you publish; then the work rolls out, and Learn feeds every lesson back into the plan." width="100%">
</p>

<p align="center">
  <a href="#get-started"><b>Get started</b></a> ·
  <a href="docs/QUICKSTART.md"><b>Quickstart</b></a> ·
  <a href="docs/HOW-TO.md"><b>How do I…</b></a> ·
  <a href="docs/METHOD.md"><b>The method</b></a> ·
  <a href="docs/TEAM.md"><b>The delivery team</b></a> ·
  <a href="docs/FAQ.md"><b>FAQ</b></a>
</p>

**You decide what to build, what lands, and what leaves your machine. AI agents do everything in between, and prove it on the exact commit.**

AIDD, short for AI-Driven Development, is a way to deliver software with AI agents as your team. The agents plan, specify, build, test, and review, each change on its own branch. You make four decisions, and no agent can make them for you.

**aidd** is the open-source toolkit that runs it. Your coding agent follows aidd's skill, and an optional delivery team of agent roles shares the work. In <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->, a guard checks each step the agent takes. A check named `aidd/gate` decides whether each change may merge, on proof, on GitHub, on GitLab, or on your own machine with nothing but git.

> [!IMPORTANT]
> **Pre-release.** aidd 1.0.0 is not released yet, so [install it from a commit](docs/INSTALL.md#before-the-first-release). [Release status](docs/ENTERPRISE.md#1-release-status-and-maturity) says what the release waits on.

## How it works

Agents can write much of the code now. The hard part is knowing what came back, whether it works, and who decided what. AIDD splits the work: four decisions are yours, and the team does everything else.

| | Your decision | When | What you look at |
| --- | --- | --- | --- |
| **D1** | **The plan** | before any code | what gets built, in which small goals, and in what order |
| **D2** | **Spec approval** | before each change is built | the contract: its intent, its scope, and the tests that define done |
| **D3** | **The release** | when a change is ready | what was built, with its proof: you land it on your machine, then publish it |
| **D4** | **The launch** | for a feature built behind a flag | when users see it |

You decide in your own words, at your agent's prompt: `approve SPEC-3`, `land it`, `publish`. aidd records each decision before the agent reads it, and `/aidd` lists every word you can type. [Your words decide](docs/ADOPTION.md#your-words-decide) has them all, including `approve all`, which lets the agents record approvals for you until you stop it.

Every change runs one loop. You decide at the steps in brackets:

```text
(Plan) → Specify → [Spec approval] → Implement ⟲ Verify → Review → [Merge approval] → [Publish] → Roll out → (Learn)
```

The agents build inside the Spec's scope until every test passes on one commit. Then Verify and Review run side by side on that commit, and a failure in either sends the change back. Not every change needs every step: before the first edit, aidd sizes the change by the files it touches. That size is its **route**, from `standard` and `minor` up to `normal` and `major`, and the route picks a lane.

| Lane | For | You decide |
| --- | --- | --- |
| **Fast** | small fixes, and pre-approved routine changes such as a bot's dependency update | the result (nothing, for a pre-approved change) |
| **Spec** | anything worth planning | the Spec and the result, plus a specialist on a `major` change |
| **Emergency** | production is down, and you declare it | that it is an emergency, and the result; the full review comes after |

The author may ask for more control, never less, and the gate computes the route again from the real diff. [The method, §4](docs/METHOD.md#4-objects) shows how the work items connect, from a big goal down to each change, and [the loop diagram](docs/TEAM.md) shows which role works at each step.

**What makes it different:**

- **Humans decide.** An approval names the exact commit you read, so a later change to the Spec or its tests voids it. An agent can never approve its own work.
- **Evidence, not prose.** A change lands on its tests' results for the exact commit that lands. A summary, or "tests pass" in a chat message, never counts.
- **Two checks that don't trust the agent.** [The guard and the gate](#how-it-stays-honest) check each step and each change.
- **State lives in git**, in files you can read, with no server and no database.
- **Quiet and small.** aidd calls no model, sends no telemetry, and has no runtime dependencies.

## Get started

**Ask your agent.** In any coding agent that can run commands, say this:

```text
Install thaithienvanid/aidd and apply it to this project.
```

It follows [llms-install.md](llms-install.md): it asks which profile you want, then installs aidd, checks the setup, and commits it.

**In Claude Code**, install the plugins, then type `/aidd init` in each repository:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill, the guard, and the commands
/plugin install aidd-team@aidd     # the delivery team (optional)
/plugin install aidd-mods@aidd     # the status pane and the /aidd verbs (optional)
```

Only `/plugin install aidd@aidd` is needed; `/plugin install aidd-team@aidd` and the pane are optional.

**With the CLI**, which needs Python 3.11 or later and nothing else, in any agent:

```sh
uv tool install git+https://github.com/thaithienvanid/aidd      # or: pipx install git+https://github.com/thaithienvanid/aidd
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --team         # asks the profile and the approver, wires the agents it finds, and offers the commit
aidd doctor              # check the wiring
```

To look before you install anything, `uvx --from git+https://github.com/thaithienvanid/aidd aidd init --dry-run` reads your repository and writes nothing.

`aidd init` writes the config, the skill, `AGENTS.md`, and the CI workflows, and wires each coding agent it finds, out of the <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> it supports. For a script, pass the answers: `aidd init --profile solo --approvers email:you@example.com --team`.

Nothing blocks you at first. The solo and team profiles start in advisory mode, so the guard and the gate report and stop nothing until you set `mode: enforce`, though no agent can ever approve, land, merge, or publish for you. With no GitHub or GitLab yet, the [local-first path](docs/ADOPTION.md#local-first-no-github-or-gitlab) runs the whole loop on your machine.

Next, take one change through the loop in the [Quickstart](docs/QUICKSTART.md), or read [a solo day](docs/ADOPTION.md#a-solo-day). To turn on every part at once, follow [Use all of aidd](docs/INSTALL.md#use-all-of-aidd), and [Install](docs/INSTALL.md) has every path and what each coding agent needs.

## Everyday commands

You work in your agent's session, so the `/aidd` verbs cover the everyday steps, and your terminal does the same:

<!-- aidd:gen cli:everyday -->
| In the session | At your terminal | What it does |
| --- | --- | --- |
| `/aidd` | — | every decision that is yours, and the words that make it |
| `/aidd status` | `aidd list --waiting-on-me` | what waits on you now, and what to type |
| your agent runs it | `aidd list` | all open work, and who holds each step |
| `/aidd approve SPEC-3` | `aidd approve spec SPEC-3` | Spec approval |
| your agent runs it | `aidd gate` | every gate rule on this branch, before Merge approval |
| `/aidd land` | `aidd land` | Merge approval, then it lands on your local trunk |
| `/aidd publish` | `aidd publish` | the verb shows what would leave your machine; typing `publish`, or `aidd publish`, pushes it and opens its PR/MR |
| `/aidd update` | `aidd self-update`, then `aidd upgrade --yes` | aidd and this repository's aidd files, brought up to date |
<!-- aidd:end -->

In place of a verb you can type the words: `approve SPEC-3`, `land it`, `publish`. The `/aidd` verbs come with the `aidd-mods` plugin in Claude Code and the terminal plugin `aidd init` writes for OpenCode, and in every other agent the guard runs in, the words work the same. [Install](docs/INSTALL.md#claude-code-plugins) lists every verb, and [CLI](docs/CLI.md#which-command-when) every command.

## The delivery team

The team is optional. It's <!-- aidd:gen count:roles -->13<!-- aidd:end --> agent roles, from product manager to SRE, led by humans. Each role writes only its own files. The verifier writes the tests and runs the built change, but never writes the code. The reviewer stays the separate check. In Claude Code each command runs as `/aidd-team:<name>`, and in OpenCode, Grok Build, and Google Antigravity as `/aidd-<name>`.

In the order work meets them:

| Stage | For | Run |
| --- | --- | --- |
| Start | an existing repository | `onboard` |
| | a client proposal | `propose` |
| | a brief to a launched MVP | `mvp` |
| Plan | trim the backlog | `refine` |
| | a goal into Epics and Specs | `plan` |
| | compare designs | `explore` |
| Build | write the Spec | `specify` |
| | a threat model or security review | `secure` |
| | build the Spec | `implement` |
| | verify and review | `review` |
| | answer findings and red checks | `rework` |
| | verify a new head | `verify` |
| Fix | a small bug, on the fast lane | `fix` |
| Ship | watch the rollout | `rollout` |
| | hand client work over | `handover` |
| Learn | after an incident | `postmortem` |
| | improve the loop | `retro` |
| Any time | due upkeep | `maintain` |
| | run between your decisions | `autopilot` |

Every command stops where you decide. [Commands and flows](docs/TEAM.md#commands-and-flows) says when to pick each one, and [Autopilot](docs/AUTOPILOT.md) how a run stops at each decision, its time box, and its cost cap.

## How it stays honest

Two checks hold the agents to the loop, and neither trusts what an agent says about itself.

**The guard** runs inside your agent, on every edit and every command. It denies an agent's attempt to approve, land, merge, or publish for you, to change your decision records, or to loosen the config. In enforce mode it also keeps each role to its own files, and holds implementation until Spec approval. It reads what a shell command really runs, through pipes, substitutions, and loops, and fails closed on what it can't read. [SECURITY.md](SECURITY.md#trust-model) lists what it denies.

**The gate**, `aidd/gate`, runs in your CI, or as `aidd gate` on your machine. It reads the change as git objects, takes its config from the base branch, and never runs the change's code. A change merges only when every rule holds for the exact commit:

<!-- aidd:gen rules:questions -->
| The gate asks | Its rules |
| --- | --- |
| Can the gate trust what it reads? | `context`, `internal`, `config`, `edited_comments` |
| Is the change what it says it is? | `change_request`, `spec`, `confidence`, `route`, `scope`, `changed_lines`, `standard_change`, `explore`, `draft` |
| Is it proven on this commit? | `tests`, `red_green`, `merge_queue` |
| Did the right humans approve it? | `spec_approval`, `merge_approval`, `specialist_approval`, `authors` |
| Is it safe to release? | `secrets`, `policy`, `policy:<rule>`, `emergency`, `observe`, `provenance` |
<!-- aidd:end -->

Every denial, finding, and error names the next step that works where you are, and [Error codes](docs/ERRORS.md) explains each one.

## From one person to many teams

Pick a profile, and tighten it later. A repository can never loosen what its organization set.

| Profile | For | What it adds |
| --- | --- | --- |
| `solo` | one person directing agents | you approve your own work, on record; Spec approval only on major changes |
| `team` | one team or a few | Spec approval before building, an Approver who is not the author, a specialist on high-risk changes |
| `org` | many teams and repositories | organization rules on high-risk and emergency changes, enforced from the start |
| `audited` | a SOC 2 or ISO 27001 audit, finance, health, public sector | two Approvers on high-risk changes, rules on every change, provenance on every commit |

Growth adds Approvers, owners, and presets, never a second loop. [Adoption](docs/ADOPTION.md) has a rollout plan for each size.

## Works with what you have

aidd needs git and the repository. Everything else is optional, and aidd uses it only if you already have it.

- **Your agents.** An agent without the guard, such as Cursor or Copilot, reads `AGENTS.md` and the skill, and the gate still decides what merges. Tools that run many agents side by side, such as [Orca](docs/ORCA.md), work as they are.
- **Your platform.** GitHub or GitLab adds approvals the platform enforces, and aidd reuses CODEOWNERS, your CI checks, rulesets, and merge queues. GitLab support is experimental.
- **Your planning tools.** Keep GitHub Spec Kit, OpenSpec, Kiro, or BMAD for planning, and `aidd import` turns their plan into a Spec.
- **Know-how.** The roles read <!-- aidd:gen count:packs -->25<!-- aidd:end --> domain packs, from payments and health to embedded systems, and <!-- aidd:gen count:practices -->34<!-- aidd:end --> practice skills. A [library of standards and stacks](docs/STANDARDS.md) gives each open choice, such as the linter, one default for each ecosystem.

## What it does not do

aidd proves who decided what, on which evidence. It doesn't judge code quality for you, so you still read what you release. It doesn't deploy, and it doesn't sandbox agents. The gate hasn't yet judged a live pull request, and autopilot's real runs were all in Claude Code. [Rationale](docs/RATIONALE.md#known-limits-in-100) lists every known limit.

## Documentation

| Start | Understand | Operate |
| --- | --- | --- |
| [Quickstart](docs/QUICKSTART.md) | [The method](docs/METHOD.md) | [CLI](docs/CLI.md) |
| [How do I…](docs/HOW-TO.md) | [The loop, step by step](docs/METHOD.md#5-the-loop) | [Config](docs/CONFIG.md) |
| [Install](docs/INSTALL.md) | [The delivery team](docs/TEAM.md) | [Platforms](docs/PLATFORMS.md) |
| [Adoption](docs/ADOPTION.md) | [What the team covers](docs/TEAM-REFERENCE.md#what-the-team-covers) | [Autopilot](docs/AUTOPILOT.md) |
| [FAQ](docs/FAQ.md) | [Glossary](docs/GLOSSARY.md) | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| [Changelog](CHANGELOG.md) | [Standards and stacks](docs/STANDARDS.md) | [Error codes](docs/ERRORS.md) |
| [Contributing](CONTRIBUTING.md) | [Rationale](docs/RATIONALE.md) | [Security](SECURITY.md) |
| [Extending: plugins, skills, packs](plugins/README.md) | [Controls](docs/CONTROLS.md) | [Enterprise readiness](docs/ENTERPRISE.md) |
| | [Architecture](docs/ARCHITECTURE.md) | [Governance](GOVERNANCE.md) |
| | | [Running inside Orca](docs/ORCA.md) |

Other projects also use the name AIDD. This one is `thaithienvanid/aidd` on GitHub and `aidd@aidd` in Claude Code. It isn't on PyPI, so a package named `aidd` there is not this one. It's open source under Apache-2.0. The schemas and the conformance suite are the contract, so anyone can reimplement the gate anywhere.
