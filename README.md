# aidd

<p align="center">
  <img src="docs/assets/hero.svg" alt="aidd, the AI-Driven Development toolkit: agents do the work, and you decide the risky steps. Every change runs one loop: Plan, Specify, Spec approval, Implement, Verify and Review side by side, Merge approval, Merge, Roll out, and Learn, which feeds each lesson back into Plan. At each approval the agent asks a plain question, such as 'Approve SPEC-3?' or 'Merge into main?', and acts on your yes. Every action has a level: allow, the agent acts; report, it acts, then tells you; ask, it waits for your yes, as before a force-push or a deploy. aidd advises: the hard stops are your harness's own ask rules and your platform's branch protection." width="100%">
</p>

**The AI-Driven Development toolkit. Agents do the work, and you decide the risky steps.**

<p align="center">
  <a href="#install"><b>Install</b></a> ·
  <a href="docs/GUIDE.md"><b>Guide</b></a> ·
  <a href="docs/METHOD.md"><b>The method</b></a> ·
  <a href="docs/TEAM.md"><b>The delivery team</b></a> ·
  <a href="docs/GUIDE.md#faq"><b>FAQ</b></a>
</p>

> [!IMPORTANT]
> **Pre-release.** aidd 1.0.0 is not released yet, so install it from the repository, as below.

AIDD, AI-Driven Development, is a way to deliver software with AI agents as your team. Agents plan, specify, build, test, and review, and every change follows one loop. Each action an agent takes has a level: `allow` (it acts), `report` (it acts, then tells you), or `ask` (it waits for your yes, then acts). aidd is the open-source toolkit that runs it: a command-line tool with no dependencies, a skill for your coding agent, and an optional delivery team of agent roles. aidd advises and records nothing, so the hard stops come from your harness's own ask rules, which `aidd init` writes, and your platform's branch protection.

```text
(Plan) → Specify → [ask: spec.approve] → Implement ⟲ Verify → Review → [ask: pr.merge] → Merge → Roll out → (Learn)
```

## Install

**Ask your agent.** In any coding agent that can run commands, say this:

```text
Install thaithienvanid/aidd and apply it to this project.
```

It follows [llms-install.md](llms-install.md): it asks which profile you want, installs aidd, checks the setup, and offers to commit it.

**With the CLI**, which needs Python 3.11 or later and nothing else:

```sh
uv tool install git+https://github.com/thaithienvanid/aidd      # or: pipx install git+https://github.com/thaithienvanid/aidd
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --team         # asks the profile, writes the files, and offers the commit
aidd doctor              # check the wiring and the risk rules
```

To look before you install, `uvx --from git+https://github.com/thaithienvanid/aidd aidd init --dry-run` reads your repository and writes nothing. The one-line installer, a pinned commit, and updates are in [the guide](docs/GUIDE.md#install).

**In Claude Code**, install the plugins, then run `aidd init` in each repository:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill and the MCP server
/plugin install aidd-cli@aidd      # the aidd command on the agent's PATH (optional)
/plugin install aidd-team@aidd     # the delivery team (optional)
```

`aidd init` writes the config, a block in `AGENTS.md`, the skill, and the harness ask rules for each coding agent it finds, out of the <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> it supports.

## A first change

```sh
git switch -c discount
aidd risk --paths app/discount.py      # minor: the fast lane, no Spec
# tell your agent: "Add discount(total, percent) in app/discount.py, with a test."
aidd test                              # the agent runs the suite: green on the head, with evidence
# the agent asks "Merge discount into main?", and you say yes
```

[Your first change](docs/GUIDE.md#your-first-change) walks through a Spec and its approval too.

## Everyday commands

Four commands cover most days. `aidd status` shows the open work and each next step, and `aidd risk` the route or the level of a command. `aidd new` writes a Spec or another work item, and `aidd test` runs the tests and writes the evidence. `aidd help --all` lists every command, and [CLI.md](docs/CLI.md) every flag.

<!-- aidd:gen cli:everyday -->
| In the session | At your terminal | What it does |
| --- | --- | --- |
| ask your agent | `aidd status` | all open work, and the next step of each |
| ask your agent | `aidd risk --paths <paths>` | the route a change needs, and whether the agent asks before it edits |
| answer its question | — | a yes to a Spec approval, a merge, a force-push, a deploy: the agent does it for you |
| — | `aidd risk --list` | every risk rule in force, and where it comes from |
| — | `aidd self-update`, then `aidd upgrade --yes` | aidd and this repository's aidd files, brought up to date |
<!-- aidd:end -->

## The risk rules

A risk rule sets the level of an action, such as `git.push.force`, narrowed by an area, a branch, or a role. The built-in rules include these:

| Action | Level |
| --- | --- |
| `code.edit` | `allow`; `ask` in `auth`, `payments`, `personal_data`, `secrets`, and `migrations`; `report` in `ci`, `infra`, and `dependencies` |
| `git.commit`, `git.push` to your own branch | `allow` |
| `pr.open` | `report` |
| `spec.approve`, `pr.merge`, `git.push` to the default branch | `ask` |
| `git.push.force`, `git.history.rewrite`, `deploy.run`, `release.publish`, `secret.use`, `money.spend` | `ask` |

Change any of them in `.aidd/config.yaml`. A rule with the same action, area, branch, and role replaces the built-in one:

```yaml
risks:
  areas:
    billing: {paths: ["src/billing/**"], route: major}
  rules:
    - {action: code.edit, area: billing, level: ask}
    - {action: pr.open, level: allow}
```

`aidd risk --list` shows every rule in force and where it comes from. [Customize the risk rules](docs/GUIDE.md#customize-the-risk-rules) has more examples, and [the method](docs/METHOD.md#6-risk-rules) says which rule wins.

## Profiles

| Profile | For | Spec approval | Merge approval |
| --- | --- | --- | --- |
| `solo` | one person directing agents | asked on major | the agent asks you in the chat |
| `team` | one team or a few | asked on normal and major | your platform's PR/MR review |

## The delivery team

The team is optional: <!-- aidd:gen count:roles -->13<!-- aidd:end --> agent roles, from product manager to SRE, led by humans. Each role writes only its own files. The verifier writes the tests and never the code, and the reviewer reads the diff and never approves. In Claude Code each flow runs as `/aidd-team:<name>`, such as `/aidd-team:specify`, `/aidd-team:implement`, or `/aidd-team:fix`. Every flow stops at each ask. [TEAM.md](docs/TEAM.md) has the roles and the flows.

## Works with what you have

aidd needs git and the repository. Everything else is optional.

- **Your agents.** Any agent that reads `AGENTS.md` or an Agent Skills folder follows the skill. Tools that run many agents side by side, such as Orca, work as they are.
- **Your platform.** On GitHub or GitLab, `aidd init --ci` writes the job that runs `aidd test` on each PR/MR, and your branch protection holds the merge.
- **Your planning tools.** Keep Spec Kit, OpenSpec, Kiro, or BMAD for planning: your agent reads the plan and writes the Spec.
- **Know-how.** The roles read <!-- aidd:gen count:packs -->25<!-- aidd:end --> domain packs, from payments and health to embedded systems, and <!-- aidd:gen count:practices -->36<!-- aidd:end --> practice skills. A [library of standards and stacks](docs/STANDARDS.md) gives each open choice, such as the linter, one default for each ecosystem.

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
