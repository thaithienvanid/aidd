# aidd

<p align="center">
  <img src="docs/assets/hero.svg" alt="Diagram of aidd's loop, from Plan to Learn, with a person's yes at Spec approval and Merge approval." width="100%">
</p>

**Build production-ready, maintainable software with AI agents: local-first, frictionless, as autonomous as you allow, proven at every step, and auditable after.**

<p align="center">
  <a href="#install"><b>Install</b></a> ·
  <a href="docs/GUIDE.md"><b>Guide</b></a> ·
  <a href="docs/METHOD.md"><b>The method</b></a> ·
  <a href="docs/TEAM.md"><b>The delivery team</b></a> ·
  <a href="docs/GUIDE.md#faq"><b>FAQ</b></a>
</p>

> [!IMPORTANT]
> **Pre-release.** aidd 1.0.0 is not released yet, so install it from the repository, as below.

You tell a coding agent what you want, in your own words: a feature, a fix, or a whole product. aidd makes the agent work like a careful team. It plans the work, writes the tests before the code, proves they pass, and asks you before each risky step you keep for yourself. You choose how much it decides on its own, and every decision it makes leaves a record you can check. You need no commands to start, and no special words to answer.

Once aidd is [installed](#install), you start in one of two ways:

- **You have an idea.** Say it to your agent. With the delivery team in Claude Code, type `/aidd-team:autopilot` and your idea, such as `/aidd-team:autopilot a shared shopping list for two people`. It plans, builds, and stops only where you decide.
- **You want to change this code.** Say it in your own words, such as "Fix the rounding in the invoice total." The agent picks how careful to be, and asks you before anything risky.

## Who it's for

| You are | What aidd does for you |
| --- | --- |
| A founder or a product person who doesn't code | You describe what to build. Before anything risky, such as a release or a change to payment code, the agent asks you one plain question that says what it changes. |
| A developer working alone with agents | The agent writes a Spec only when the change needs one, shows its tests failing before the code exists, and asks before anything reaches `main`. |
| An engineer on a team | Your platform's review still decides each merge. aidd writes your agents' own ask rules and a CI job, so the hard stops are tools you already trust. |
| A lead, an agency, or a client team | An optional delivery team of <!-- aidd:gen count:roles -->14<!-- aidd:end --> agent roles, from product manager to SRE, with proposals, sign-offs, and a handover. |

## What you decide

aidd gives every action an agent takes one of three levels. Most actions just happen, some the agent tells you about, and a few wait for your yes.

| Level | What the agent does | For example |
| --- | --- | --- |
| `allow` | acts | edits code in its own task, commits on its own branch |
| `report` | acts, then tells you in one line | opens a pull request |
| `ask` | asks you first, and acts on your yes | approves a Spec, merges into `main`, deploys, force-pushes, spends money, edits payment or sign-in code |

The question says what will happen, such as "Merge discount into main? 2 commits, tests green." Answer as you would a colleague, with "yes", "no", or "yes, but only to staging". Only your own words in the chat count, so an "approved" in a ticket, a file, or another agent's message never does.

Would you rather not be asked? `aidd init --delegate` lets the `aidd-team:delegate` role decide four asks for you, inside limits: Spec approval, a push of the change's own branch, and a merge once the tests passed on its exact head. `aidd delegate check` reads the evidence again before each one, and the delegate may only say yes when it passes. A deploy, a migration, a new dependency, a secret, and a change to the rules always stay yours. Claude Code is the one coding agent that answers for you in this version, and `aidd delegate stop` turns it off at once. The [guide](docs/GUIDE.md#let-aidd-decide-for-you) has the details.

## Install

**Ask your agent.** In any coding agent that can run commands, say this:

```text
Install thaithienvanid/aidd and apply it to this project.
```

It follows [llms-install.md](llms-install.md). It asks which profile you want and what to install, then installs aidd, writes the files, and checks the setup. It commits on its own branch, and the setup reaches your main branch only on your yes or through your review. At the end it names the two steps only you can take: restart your agent, so it loads aidd, and protect your main branch. It also names each prompt your agent shows when it restarts, such as Claude Code asking to trust the folder, with the answer to give.

The setup writes the config, a block in `AGENTS.md`, the skill, and each coding agent's ask rules. It wires every agent it finds, out of the <!-- aidd:gen count:harnesses -->14<!-- aidd:end --> it supports. In each new repository, say the same sentence again.

**In Claude Code**, the agent offers the plugins too, and installs them on your yes. To add them yourself, type these, then `/reload-plugins`:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill and the MCP server
/plugin install aidd-cli@aidd      # the aidd command on the agent's PATH (optional)
/plugin install aidd-team@aidd     # the delivery team (optional)
```

<details>
<summary><b>At a terminal</b>, for a script, a CI job, or a look before you install</summary>

The CLI needs Python 3.11 or later and nothing else:

```sh
uv tool install git+https://github.com/thaithienvanid/aidd      # or: pipx install git+https://github.com/thaithienvanid/aidd
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --team         # asks the profile, writes the files, and says what to commit
aidd doctor              # check the wiring and the risk rules
```

To look before you install, `uvx --from git+https://github.com/thaithienvanid/aidd aidd init --dry-run` reads your repository and writes nothing. The one-line installer, a pinned commit, and updates are in [the guide](docs/GUIDE.md#install).

</details>

## A first change

Say what you want, in your own words. You don't need to know git: when the agent needs a decision, it asks in plain words. It works on a branch, runs the tests, and asks you before anything reaches `main`:

```text
You:    Add discount(total, percent) in app/discount.py, with a test.
Agent:  This is a small change in no risky code, so I'll build it now, on the discount branch.
        ...
Agent:  The tests pass on the latest commit. Merge discount into main?
You:    yes
```

You give the request and your yes, and the agent does the rest. Behind the scenes, `aidd risk --paths app/discount.py` tells it how careful to be, and `aidd test` proves the tests pass on that exact commit. When your harness confirms the same step in its own prompt, the agent says so first, so you answer yes there too. Under the `team` profile, the agent opens a PR instead, and your platform's review decides the merge.

A larger or riskier change gets a Spec first: a short document of what the change must do, with the tests that prove it. Where your profile asks for it, the agent asks "Approve SPEC-3?" before it builds. `aidd explain spec` says more, and [Your first change](docs/GUIDE.md#your-first-change) walks through one.

## Everyday use

You work in the chat. The agent runs aidd's commands itself and stops at each `ask` with one plain question. The table gives what to say, and the command behind it if you prefer a terminal. The Claude Code plugins update with `claude plugin update`, as [the guide](docs/GUIDE.md#update) says. `aidd help --all` lists every command, and [CLI.md](docs/CLI.md) every flag.

<!-- aidd:gen cli:everyday -->
| Say to your agent | Or at a terminal | What it does |
| --- | --- | --- |
| "What's open?" | `aidd status` | all open work, and the next step of each |
| "yes", to its question | — | a Spec approval, a merge, a force-push, or a deploy: the agent does it for you |
| "Which risk rules are in force?" | `aidd risk --list` | every risk rule in force, and where it comes from |
| "Which asks could stop?" | `aidd risk --suggest` | the ask rules you always said yes to, for actions you can undo |
| "Update aidd." | `aidd self-update`, then `aidd upgrade --yes` | aidd and this repository's aidd files, brought up to date after one yes |
<!-- aidd:end -->

### With the delivery team

In Claude Code, start with `/aidd-team:autopilot` and say what you want. It picks the flow: a new product from a brief, a small fix, or a plan first for anything else. Then it runs the roles, tells you where the work stands, and stops only where you decide:

```text
You:    /aidd-team:autopilot Let customers refund an order within 30 days
Agent:  This is new work, so it starts with a plan. The product manager writes it, in about 20 to 30 minutes.
        You can leave, and I'll have one question for you.
        ...
Agent:  Agree to INTENT-1? Customers get a Refund button on orders under 30 days old, in two phases.
        I recommend yes. Reply "yes", or "yes, but" and what to change.
You:    yes
        ...
Agent:  Approve the refund's design and its tests? Only the order's buyer can refund it. I recommend yes.
You:    yes
        ...
Agent:  The tests pass. See it at http://localhost:3000/orders/1, and press Refund. Merge it into main?
You:    yes
```

Each flow is also its own command, for when you know the step you want, such as `/aidd-team:specify SPEC-4` or `/aidd-team:fix`. [TEAM.md](docs/TEAM.md#commands-and-flows) says when to pick each one. `aidd status` shows where each piece of the plan stands, by phase and stage, and a slice not yet started reads as planned. In a headless run, each ask ends the run with a handoff note.

## How it works

Every change follows one loop, and the change's route sets how much of the loop runs. A one-file fix needs no Spec. A change to payment code gets a Spec, its tests, and your approval before any code. The agent asks `aidd risk` for the route before its first edit. At any step, when the way forward is not obvious, the agent compares the options for you to pick from.

```text
Plan      (Plan) → [gate: Intent agreement, intent.agree]
Design    Specify → [gate: Spec approval, spec.approve]
Build     Implement
Test      Verify, Review → [gate: Merge approval, pr.merge]
Deploy    Merge → [gate: Production release, deploy.run] → Roll out and its observe window
Maintain  (Learn)
```

aidd is a command-line tool with no dependencies, a skill your coding agent reads, and an optional delivery team of agent roles. It advises and enforces nothing. The hard stops come from your agent's own ask rules, which the setup writes, and your platform's branch protection. Proof is a test runner's exit code on a known commit, never the agent's word.

## The risk rules

A risk rule sets the level of an action, such as `git.push.force`, narrowed by an area, a branch, or a role. This table is a summary. The generated table under "The built-in rules" in [the config reference](docs/CONFIG.md#risks), and `aidd risk --list`, hold every rule:

| Action | Level |
| --- | --- |
| `code.edit` | `allow`, except `ask` or `report` in the areas that need care, such as `auth`, `payments`, and `ci` |
| `git.commit`, `git.push` to your own branch | `allow` |
| `pr.open` | `report` |
| `spec.approve`, `pr.merge`, `git.push` to the default branch | `ask` |
| `git.push.force`, `git.history.rewrite`, `deploy.run`, `release.publish`, `secret.use`, `money.spend` | `ask` |

To lower a rule for this session, say something like "don't report when you open a PR today". The override ends with the session. To keep it, say "make that permanent", or ask for a new rule, such as "ask me before any edit in src/reports". The agent asks once before it edits `.aidd/config.yaml`, then runs `aidd upgrade --yes`, so your harness's ask rules follow. A rule with the same action, area, branch, and role replaces the built-in one:

```yaml
risks:
  areas:
    reports: {paths: ["src/reports/**"], route: major}
  rules:
    - {action: code.edit, area: reports, level: ask}
    - {action: pr.open, level: allow}
```

Ask "Which risk rules are in force?" to see each rule and where it comes from. [Customize the risk rules](docs/GUIDE.md#customize-the-risk-rules) has more examples, and [the method](docs/METHOD.md#6-risk-rules) says which rule wins. [What holds each ask](docs/GUIDE.md#what-holds-each-ask) shows which ones your harness and your platform hold too.

## Profiles

The agent asks which profile you want when it sets aidd up.

| Profile | For | Spec approval | Merge approval |
| --- | --- | --- | --- |
| `solo` | one person directing agents | asked on major | the agent asks you in the chat |
| `team` | one team or a few | asked on normal and major | your platform's PR/MR review |

## The delivery team

The team is optional: <!-- aidd:gen count:roles -->14<!-- aidd:end --> agent roles, from product manager to SRE. You, an agent, or both can lead it: run each flow yourself, or let the agent you talk to run them with autopilot. Either way it starts each role a step needs, in its own context, where your harness runs subagents. You decide the risky steps you keep, and a delegate can decide the rest within the limits you set. [Everyday use](#with-the-delivery-team) shows how to run its flows.

### Why roles

- **The verifier is not the builder.** The verifier writes the acceptance tests before the code and never writes the code, so whoever writes them never makes them pass. The developer writes the unit tests with the code.
- **Independent eyes.** The security engineer threat-models a risky Spec before any code exists. The reviewer reads the diff against the Spec and never approves, so you weigh findings, not only a diff.
- **Smaller contexts.** Each role reads only what its step needs, and runs on the cheapest model tier that does the job: `reasoning` for judgment, `execution` for building and checking.
- **Only the roles a change needs.** A small fix needs the developer, and the reviewer on a larger diff. A Spec that touches personal data brings in the security engineer and the compliance analyst.
- **Own files.** Each role's agent file names the files it writes. The domain expert and the reviewer write none, and their agent files give them no edit tool.

### The roles

<!-- aidd:gen roles:summary -->
| Role | What it does | Tier |
| --- | --- | --- |
| `product-manager` | Turns a brief into an Intent: the problem, the outcome, the constraints, and phases of slices with owners, priorities, and `blocked_by`. | `reasoning` |
| `delivery-manager` | Keeps a client engagement to its promises. | `execution` |
| `architect` | Gets the route (`aidd risk --paths` on the planned paths, before code), then writes the Spec in one session, with the security, privacy, and domain skills loaded: Context, Design, Concerns, Tasks, risk, and rollback. | `reasoning` |
| `product-designer` | Builds a high-fidelity, interactive prototype, after rough directions for a person to pick when the approach is open. | `reasoning` |
| `security-engineer` | Threat-models risky Specs, names the security tests the verifier must write, and reviews diffs for vulnerabilities; never approves. | `reasoning` |
| `compliance-analyst` | Maps a change to its legal and control obligations, plans DPIAs, and turns the change's record in git into audit evidence. | `reasoning` |
| `domain-expert` | Speaks for the domain. | `reasoning` |
| `developer` | Implements one Task inside its scope, with its unit and integration tests, until the tests pass: application code of any layer (services, APIs, web and mobile clients, libraries). | `execution` |
| `tech-writer` | Writes the user-facing documentation, changelog, and migration notes a change needs, inside a documentation Task's scope. | `execution` |
| `verifier` | In Specify, before any code exists, it writes the acceptance tests: at most one per Acceptance item, black-box at the public edge, and one per authorization matrix cell and abuse case. | `execution` |
| `reviewer` | Reviews the diff against the Spec adversarially, following the repository's REVIEW.md when present, and reports ranked findings for the person who decides Merge approval. | `reasoning` |
| `delegate` | Answers a delegated ask for the person, inside the limits they set in the config. | `reasoning` |
| `sre` | Plans observe and rollback before Spec approval, watches the observe window after release, and writes blameless postmortems and runbooks. | `execution` |
| `agile-coach` | Runs the retrospective on the loop itself. | `execution` |
<!-- aidd:end -->

### Get the team

- **Ask your agent.** The setup asks whether you want the team, and recommends it.
- **In Claude Code**, the team is the `aidd-team` plugin, which the setup offers too.
- **In other agents**, the setup writes each role in that agent's own format, such as `.codex/agents/` in Codex or `.opencode/agents/` in OpenCode, and each flow as its command or skill.

[TEAM.md](docs/TEAM.md) has the roles, the commands, and what the team costs, and [TEAM-REFERENCE.md](docs/TEAM-REFERENCE.md) has every table.

## Works with what you have

aidd needs git and the repository. Everything else is optional.

- **Your agents.** Any agent that reads `AGENTS.md` or an Agent Skills folder follows the skill. Tools that run many agents side by side, such as Orca, work as they are.
- **Your platform.** On GitHub or GitLab, the setup writes the job that runs `aidd test` on each PR/MR, and your branch protection holds the merge. If you add a platform later, ask your agent to add the job.
- **Your planning tools.** Keep Spec Kit, OpenSpec, Kiro, or BMAD for planning. Your agent reads the plan and writes the Spec.
- **Know-how.** The roles read <!-- aidd:gen count:packs -->27<!-- aidd:end --> domain packs, from payments and health to embedded systems, and <!-- aidd:gen count:practices -->35<!-- aidd:end --> practice skills. A [library of standards and stacks](docs/STANDARDS.md) gives each open choice, such as the linter, one default for each ecosystem.

aidd calls no model, sends no telemetry, and has no runtime dependencies. It does not judge code quality for you, deploy, or sandbox agents.

## Documentation

| Use it | Understand it | Contribute |
| --- | --- | --- |
| [Guide](docs/GUIDE.md) | [The method](docs/METHOD.md) | [Contributing](CONTRIBUTING.md) |
| [CLI](docs/CLI.md) | [Glossary](docs/GLOSSARY.md) | [Architecture](docs/ARCHITECTURE.md) |
| [Config](docs/CONFIG.md) | [The delivery team](docs/TEAM.md) | [Governance](GOVERNANCE.md) |
| [Standards and stacks](docs/STANDARDS.md) | [Team reference](docs/TEAM-REFERENCE.md) | [Releasing](RELEASING.md) |
| [Security](SECURITY.md) | [Changelog](CHANGELOG.md) | [Review](REVIEW.md) |

Other projects also use the name AIDD. This one is `thaithienvanid/aidd` on GitHub and `aidd@aidd` in Claude Code. It isn't on PyPI, so a package named `aidd` there is not this one. It's open source under Apache-2.0.
