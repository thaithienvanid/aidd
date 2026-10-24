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

**aidd** is the open-source toolkit that runs it. It gives your coding agent a skill to follow, and an optional delivery team of agent roles. In <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->, a guard also checks each step the agent takes. A check named `aidd/gate` decides whether each change may merge, on proof. It runs on GitHub, on GitLab, or on your own machine with nothing but git.

> [!IMPORTANT]
> **Pre-release.** aidd 1.0.0 is not released yet, so [install it from a commit](docs/INSTALL.md#before-the-first-release). [Release status](docs/ENTERPRISE.md#1-release-status-and-maturity) says what the release waits on.

## Why AIDD

Agents can write much of the code now. The hard part is knowing what came back, whether it works, and who decided what. Left alone, the work drifts, and "done" gets claimed rather than shown.

AIDD splits the work. Four decisions are yours, and the team does everything else:

| | Your decision | When | What you look at |
| --- | --- | --- | --- |
| **D1** | **The plan** | before any code | what gets built, in which small goals, and in what order |
| **D2** | **Spec approval** | before each change is built | the contract: its intent, its scope, and the tests that define done |
| **D3** | **The release** | when a change is ready | what was built, with its proof: you land it on your machine, then publish it |
| **D4** | **The launch** | for a feature built behind a flag | when users see it |

What makes it different:

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

It follows [llms-install.md](llms-install.md). It asks which profile you want, then installs aidd, checks the setup, and commits it.

**In Claude Code**, install the plugins:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill, the guard, and the commands
/plugin install aidd-team@aidd     # the delivery team (optional)
/plugin install aidd-mods@aidd     # the status pane and the /aidd verbs (optional)
```

Then type `/aidd init` in each repository. The agent shows what `aidd init` proposes, asks you once, and sets it up with the plugin's own `aidd`, so you install nothing else. Only `/plugin install aidd@aidd` is needed, because `/plugin install aidd-team@aidd` and the pane are optional. [Claude Code plugins](docs/INSTALL.md#claude-code-plugins) has the details.

**Try it first, with nothing installed.** With [uv](https://docs.astral.sh/uv/), this reads your repository and writes nothing:

```sh
uvx --from git+https://github.com/thaithienvanid/aidd aidd init --dry-run
```

**In any other agent**, install [the CLI](docs/INSTALL.md#the-cli), which needs Python 3.11+ and nothing else. Use an install, not `uvx`, for everyday work, because the hooks start the aidd that ran `aidd init`:

```sh
uv tool install git+https://github.com/thaithienvanid/aidd      # or: pipx install git+https://github.com/thaithienvanid/aidd
```

That takes the latest commit, and `aidd init` pins your CI files to that exact commit. Then run this in your repository:

```sh
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --team         # asks the profile and the approver, wires the agents it finds, and offers the commit
aidd doctor              # check the wiring
```

`aidd init` writes the config, the skill, `AGENTS.md`, and the CI workflows. It wires each coding agent it finds, out of the <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> it supports, and `--harness codex` adds one it can't see. It also adds what your tests, builds, and operating system leave behind to `.gitignore`, in marked blocks. Then restart each agent it names. Codex runs aidd's hooks once you trust the project and review them in `/hooks`, and Grok Build once you trust the folder. [Your coding agent](docs/INSTALL.md#your-coding-agent) lists what each agent needs.

- **No one to answer**, as in a script? Pass the answers, with `aidd init --profile solo --approvers email:you@example.com --team`, or for a team, `--profile team --approvers @your-org/leads`.
- **Each teammate** installs the CLI and runs `aidd init` once, to set up their own machine. Under the org or audited profile, or `mode: enforce`, their agent takes no step until they do, and its message says so.
- **Nothing blocks you at first.** The solo and team profiles start in advisory mode, so the guard and the gate report and stop nothing until you set `mode: enforce`. Even so, no agent can approve, land, merge, or publish for you.
- **No GitHub or GitLab yet?** The [local-first path](docs/ADOPTION.md#local-first-no-github-or-gitlab) runs the whole loop on your machine.

To turn on every part at once, follow [Use all of aidd](docs/INSTALL.md#use-all-of-aidd). Then take one change through the loop in the [Quickstart](docs/QUICKSTART.md), or read [a solo day](docs/ADOPTION.md#a-solo-day).

## What you type

You decide in your own words, at your agent's prompt. aidd records each decision the moment you type it, before the agent reads it. That works in every agent the guard runs in, with no plugin needed. The agent then says what it does now, and where it stops for you next. You never need to know the words in advance, because `/aidd` alone lists them, one line each.

| You type | Or run | What happens |
| --- | --- | --- |
| `approve SPEC-3` | `/aidd approve SPEC-3` | Spec approval, for the Spec and its tests as you read them. `approve` alone approves every Spec that waits on you. |
| `approve merge` | `/aidd approve merge` | Your Merge approval of this branch's head. |
| `land it` | `/aidd land` | Your Merge approval. The tests run once more on exactly what lands, then it lands on your local trunk. |
| `publish` | `/aidd publish` | The work leaves your machine. It's pushed, and on GitHub its pull request opens. |
| `merge it` | `/aidd merge` | Your Merge approval on a pull request. It merges once `aidd/gate` passes. |
| `approve all` | `/aidd approve all` | The agents record Spec and Merge approvals for you, until you stop it. Add `and publish` to let them publish too, or `but major` to keep major changes for yourself. |
| `stop approving` | `/aidd stop` | The end of `approve all`, so each decision waits on you again. |
| `explore branch <topic>` | `/aidd explore <topic>` | A throwaway branch where every edit is free. Nothing merges from it until you rename it. |
| `decide PROP-1 go`, `sign off PROP-1` | `/aidd decide PROP-1 go`, `/aidd sign-off PROP-1` | A client proposal's go or no-go, and its sign-off. |

The plan and every launch stay yours, even under `approve all`. Something may change outside the agent's session, such as a file a script wrote. Your next decision takes it in, and aidd shows you each change with how to put it back. A change that weakens the guard waits for a dialog that shows it.

The `/aidd` verbs ask the same in a dialog, with no model turn. Claude Code gets them from the `aidd-mods` plugin, and OpenCode from the terminal plugin `aidd init` writes. `/aidd status` opens a pane that leads with the one decision that waits on you, and what to type.

**At your own terminal**, the same decisions and the state of the work come from git and your repository's files:

<!-- aidd:gen cli:everyday -->
| Command | When |
| --- | --- |
| `aidd gate` | before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request |
| `aidd land` | land a passing branch on the local trunk and record the Merge approval; at the prompt, `land it` |
| `aidd publish` | take the branch off this machine: push it, open its pull request on GitHub, and carry your approvals there; at the prompt, `publish` |
| `aidd list` | to see all open work and who holds each step; `--branch` for the change in hand |
<!-- aidd:end -->

`aidd list --waiting-on-me` is your inbox, and `aidd gate --explain <code>` explains a finding. `aidd doctor` checks the setup, and `aidd upgrade --yes` brings aidd's files up to a new aidd. `aidd uninstall --yes` takes them out, and keeps your Specs and every file you changed. Your agent runs the rest, and [CLI](docs/CLI.md#which-command-when) has every command.

## The loop

Every change runs one loop. You decide at the steps in brackets.

```text
(Plan) → Specify → [Spec approval] → Implement ⟲ Verify → Review → [Merge approval] → [Publish] → Roll out → (Learn)
```

Plan runs only for work bigger than one change. A change worth planning gets a Spec with its intent, its scope, the tests that define done, the risk, and the rollback. The agents build inside that scope until every test passes on one commit. Then **Verify and Review run side by side on that commit**. The verifier runs the tests and checks each Acceptance line, while the reviewer reads the diff against the Spec. A failure in either goes back to Implement, and a new commit needs both again. Roll out deploys and watches the change, and Learn turns an incident or a missed goal into new work at Plan.

Not every change needs every step. Before the first edit, aidd sizes the change by the files it will touch. That size is its **route**, from `standard` and `minor` up to `normal` and `major`, with `emergency` for production repairs. The author may ask for more control, never less, and the gate computes the route again from the real diff. The route picks a lane:

| Lane | For | You decide |
| --- | --- | --- |
| **Fast** | small fixes, and pre-approved routine changes such as a bot's dependency update | the result (nothing, for a pre-approved change) |
| **Spec** | anything worth planning | the Spec and the result, plus a specialist on a `major` change |
| **Emergency** | production is down, and you declare it | that it is an emergency, and the result; the full review comes after |

A big goal, an Initiative, holds small goals, Epics of two weeks or less, and each says how it reaches users. [The method, §4](docs/METHOD.md#4-objects) shows how the work items connect, and [the loop diagram](docs/TEAM.md) shows which role works at each step.

## The delivery team

The team is optional. It's <!-- aidd:gen count:roles -->13<!-- aidd:end --> agent roles, from product manager to SRE, led by humans. Each role writes only its own files. The verifier writes the tests and runs the built change, and never writes the code. The reviewer stays the separate check of the code. Add it with `aidd init --team`, or with the `aidd-team` plugin in Claude Code. There, each command runs as `/aidd-team:<name>`, and in OpenCode, Grok Build, and Google Antigravity as `/aidd-<name>`.

| When you want to… | Run |
| --- | --- |
| build one change | `specify`, `implement`, then `review`, which runs Verify beside it, and you land it |
| fix a small bug | `fix` |
| clear review comments or red checks on a PR/MR | `sweep`, then `verify` to check the new head |
| get a threat model or a security review | `secure` |
| turn a goal into Epics and Specs | `plan`, after `refine` trims a long backlog |
| pick between two or three designs | `explore` |
| go from a brief to a launched MVP | `mvp` |
| start in an existing repository | `onboard` |
| win and close client work | `propose` before it, `handover` at the end |
| watch a published change roll out | `rollout` |
| learn from an incident, or improve the loop | `postmortem`, `retro` |
| do the upkeep that is due | `maintain` |
| let the loop run between your decisions | `autopilot` |

Every command stops where you decide. [Commands and flows](docs/TEAM.md#commands-and-flows) says when to pick each one, and which roles it runs.

**Autopilot** runs the loop between your decisions. `aidd autopilot next` works out the one next step from git. A run stops at each decision that waits on you, and at its time box or cost cap. [Autopilot](docs/AUTOPILOT.md) has the details.

## How it stays honest

Two checks hold the agents to the loop, and neither trusts what an agent says about itself.

**The guard** runs inside your agent, on every edit and every command. In enforce mode it keeps each role to its own files, and holds implementation until Spec approval. In every mode, it denies an agent's attempt to approve, land, merge, or publish for you, to change your decision records, or to loosen the config. Unless your config lets agents publish, it holds every push until you type `publish`.

The guard reads what a shell command really runs, through pipes, `xargs`, `find`, substitutions, and loops. Where it can't read a command exactly, it fails closed and names a plain form that works. It's one code path with a dialect for each harness, so what it denies in one harness, it denies in all of them. [SECURITY.md](SECURITY.md#trust-model) lists what it denies.

**The gate**, `aidd/gate`, runs in your CI, or as `aidd gate` on your machine. It reads the change as git objects, takes its config from the base branch, and never runs the change's code. A change merges only when every rule holds for the exact commit. Its rules answer five questions:

<!-- aidd:gen rules:questions -->
| The gate asks | Its rules |
| --- | --- |
| Can the gate trust what it reads? | `context`, `internal`, `config`, `edited_comments` |
| Is the change what it says it is? | `change_request`, `spec`, `confidence`, `route`, `scope`, `changed_lines`, `standard_change`, `explore`, `draft` |
| Is it proven on this commit? | `tests`, `red_green`, `merge_queue` |
| Did the right humans approve it? | `spec_approval`, `merge_approval`, `specialist_approval`, `authors` |
| Is it safe to release? | `secrets`, `policy`, `policy:<rule>`, `emergency`, `observe`, `provenance` |
<!-- aidd:end -->

Each finding has a stable code, such as `scope.outside`, and [Error codes](docs/ERRORS.md) gives each one its meaning and its fix. Every denial, finding, and error names the next step that works where you are. [Platforms](docs/PLATFORMS.md#what-holds-without-the-full-setup) says what holds before you enforce the gate.

## From one person to many teams

Pick a profile, and tighten it later. A repository can never loosen what its organization set.

| Profile | For | What it adds |
| --- | --- | --- |
| `solo` | one person directing agents | you approve your own work, on record; Spec approval only on major changes |
| `team` | one team or a few | Spec approval before building, an Approver who is not the author, a specialist on high-risk changes |
| `org` | many teams and repositories | organization rules on high-risk and emergency changes, enforced from the start |
| `audited` | a SOC 2 or ISO 27001 audit, finance, health, public sector | two Approvers on high-risk changes, rules on every change, provenance on every commit |

Humans and agents share one config, one skill, and one set of roles. Growth adds Approvers, owners, and presets, never a second loop. [Adoption](docs/ADOPTION.md) has a rollout plan for each size, and [Several teams](docs/ADOPTION.md#several-teams) maps Team Topologies onto the config.

## Works with what you have

aidd needs git and the repository. Everything else is optional, and aidd uses it only if you already have it.

- **Your agents.** An agent without the guard, such as Cursor or Copilot, reads `AGENTS.md` and the skill, and the gate still decides what merges. Tools that run many agents side by side, such as [Orca](docs/ORCA.md), work as they are.
- **Your platform, if you have one.** GitHub or GitLab adds approvals the platform enforces, and aidd reuses CODEOWNERS, your CI checks, rulesets, and merge queues. GitLab support is experimental.
- **Your planning tools.** Keep GitHub Spec Kit, OpenSpec, Kiro, or BMAD for planning. `aidd import` turns their plan into a Spec.
- **Know-how.** The roles read <!-- aidd:gen count:packs -->25<!-- aidd:end --> domain packs, from payments and health to embedded systems, and <!-- aidd:gen count:practices -->34<!-- aidd:end --> practice skills. A [library of standards and stacks](docs/STANDARDS.md) gives each open choice, such as the linter, one default for each ecosystem. It covers the web, data, the cloud, AI work, C and C++, firmware, and Rust. A pin that waits out a new release's cooldown names the day it may move, in `cooldown_until`.

## What it does not do

aidd proves who decided what, on which evidence. It doesn't judge code quality for you, so you still read what you release. It doesn't deploy, and it doesn't sandbox agents. The guard reaches only the writes it can read, so a program that writes by itself is left to the gate. The gate hasn't yet judged a live pull request, and autopilot's real runs were all in Claude Code. [Rationale](docs/RATIONALE.md#known-limits-in-100) lists every known limit.

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
