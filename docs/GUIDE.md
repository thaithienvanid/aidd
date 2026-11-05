# The aidd guide

This guide takes you from install to a team running many agents. [METHOD.md](METHOD.md) is the method itself, and [GLOSSARY.md](GLOSSARY.md) defines each term. [CLI.md](CLI.md) has every command and flag, and [CONFIG.md](CONFIG.md) every config key.

- [Install](#install)
- [Your first change](#your-first-change)
- [Decide the risky steps](#decide-the-risky-steps)
- [Customize the risk rules](#customize-the-risk-rules)
- [Every coding agent](#every-coding-agent)
- [Teams and CI](#teams-and-ci)
- [Orca and parallel agents](#orca-and-parallel-agents)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

## Install

**The quickest way** is to ask your coding agent, in any agent that can run commands:

```text
Install thaithienvanid/aidd and apply it to this project.
```

It follows [llms-install.md](../llms-install.md). It asks which profile you want and what to install, then installs aidd and checks the setup. It commits on its own branch, and the setup reaches your main branch only on your yes or through your review.

> [!IMPORTANT]
> **Pre-release.** No `v1.0.0` tag exists yet, so every command that names `@v1.0.0` fails until the release. Install from the repository, as below. aidd isn't on PyPI, so a package named `aidd` there is not this one.

### The CLI

The CLI needs Python 3.11 or later and nothing else. It bundles the schemas, the skill, the CI templates, and the team plugin, so `aidd init` works offline.

| Method | Command |
| --- | --- |
| uv | `uv tool install git+https://github.com/thaithienvanid/aidd` |
| pipx | `pipx install git+https://github.com/thaithienvanid/aidd` |
| uv, no install | `uvx --from git+https://github.com/thaithienvanid/aidd aidd --help` |
| From a checkout | `python3 -m venv .venv && .venv/bin/pip install .` |
| One line | `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh \| AIDD_REF=<sha> sh` |

Add `@<sha>` to a URL to pin one commit. After the release, add `@v1.0.0` instead. The one-line installer uses uv, pipx, or a private venv, whichever you have. With `AIDD_REF=<release tag>`, it installs nothing until the wheel matches the release's `SHA256SUMS`. With `gh` on your PATH, it also waits until `gh attestation verify` accepts the wheel's build provenance.

Each GitHub Release will also carry `aidd.pyz`, the whole CLI as one file, for a machine where you can't install packages. Run it as `python3 aidd.pyz --version`.

### Claude Code plugins

In Claude Code, add the marketplace and install the plugins:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill and the MCP server
/plugin install aidd-cli@aidd      # the aidd command on the agent's PATH (optional)
/plugin install aidd-team@aidd     # the delivery team (optional)
/reload-plugins
```

Only `aidd@aidd` is needed. `aidd-cli` puts `aidd` on the PATH of Claude Code's Bash tool, so you need no other install. `aidd-team` brings the <!-- aidd:gen count:roles -->13<!-- aidd:end --> roles, the flow commands, the domain packs, and the practice skills. From a local folder, `/plugin marketplace add /path/to/aidd` reads the plugins in place.

### Set up a repository

```sh
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --team         # asks the profile, writes the files, and says what to commit
aidd doctor              # check the wiring, the config, and the risk rules
```

`aidd init` writes these:

- `.aidd/config.yaml`, which names the profile, the tests, and your own risk rules. [CONFIG.md](CONFIG.md) has every key.
- A block in `AGENTS.md` that points every coding agent at the skill, and the skill itself in `.agents/skills/aidd/`.
- The harness ask rules for each coding agent it finds, so the harness itself asks you before a risky command ([Every coding agent](#every-coding-agent)).
- With `--team`, the delivery team's roles and commands. With `--ci github` or `--ci gitlab`, the CI job that runs the tests.

For a script, pass the answers: `aidd init --profile solo --ci none`. Run `aidd init --harness <key>` later to add a coding agent. It keeps every file that exists and writes only what is new.

### Update

1. Run `aidd self-update`. It installs the latest release the way you installed aidd, and only after it checks the wheel. `--check` only says what it would install, and `--main` takes the tip of `main`, the only source until the first release.
2. In each repository, run `aidd upgrade`. It is a dry run that lists what it would change: the skill, the team files, the harness ask rules, the CI pins, and `aidd_version`. `aidd upgrade --yes` makes the changes.
3. For the Claude Code plugins, run `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, and the same for `aidd-cli@aidd` and `aidd-team@aidd`.

Merge the upgrade as one change. To roll it back, revert that change.

### Remove

1. Run `aidd uninstall` to list everything `aidd init` wrote, then `aidd uninstall --yes` to remove it. It keeps your Specs and every file you changed since, and says so.
2. Run `claude plugin uninstall aidd@aidd`, and the same for each other plugin you installed.
3. Remove the CLI with `uv tool uninstall aidd` or `pipx uninstall aidd`.

## Your first change

In about ten minutes, you take one change through the loop on your own machine, with no platform and no CI. You need Python 3.11+, git, the `aidd` CLI, and a coding agent. The commands use the `sh` syntax of macOS and Linux.

**1. Make a practice repository**, with a tiny Python app and one test:

```sh
mkdir aidd-practice && cd aidd-practice
git init -b main
mkdir app tests && touch app/__init__.py tests/__init__.py
printf '__pycache__/\n' > .gitignore
printf 'def total(items):\n    return sum(items)\n' > app/cart.py
printf 'import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n' > tests/test_cart.py
git add -A && git commit -m "scaffold"
```

**2. Set up aidd** with the `solo` profile, for one person directing agents:

```sh
aidd init --profile solo --ci none
aidd doctor
```

Then name the test suite in `.aidd/config.yaml`, so `aidd test` runs it on every change:

```yaml
tests:
  - name: unit
    command: [python3, -m, unittest]
```

Commit the setup straight to `main`, as Day 0: `git add -A && git commit -m "chore: adopt aidd"`.

**3. Ask for the change.** Start your coding agent in the folder and say: "Add `discount(total, percent)` in `app/discount.py`, with a test." The agent works on a branch and checks the route before its first edit:

```sh
aidd risk --paths app/discount.py
```

It prints `minor`, the fast lane, because one new file in no area needs no Spec. Ask for a Spec anyway ("write a Spec first"), because you want to see the test fail before the code exists. The agent runs `aidd new spec SPEC-1 --title "Apply a percentage discount" --paths app/discount.py` and fills it in.

**4. Spec approval.** Under `solo`, only a major Spec needs approval, so on this one the agent would say it goes on. Say "ask me before you build", and it asks you as it would on a major change:

```text
Approve SPEC-1? It covers discount(total, percent): 2 Acceptance items, 1 Task in app/discount.py, and its test in tests/test_discount.py.
```

Read the Spec and its test, then answer in your own words, such as "yes". The agent sets `status: approved` in the Spec, with your name and the time, and commits it with an `Approved-by:` trailer. That note is the agent's, not proof, and it says so.

**5. Implement and Verify.** The agent writes the code and runs the tests:

```sh
aidd test --spec specs/SPEC-1.md
```

`aidd test` runs every command on your head commit, where they pass. It also runs the new test on `main`, where it fails, because `app/discount.py` doesn't exist there yet. That is red before green. It writes the exit codes to `.aidd/evidence/`, bound to the head commit.

**6. Merge.** The agent asks before the change reaches `main`:

```text
Merge the discount branch into main? 2 commits, tests green on the head.
```

Say yes, and the agent merges it. Nothing left your machine. `aidd status` now shows SPEC-1 as `done`.

A minor change skips the Spec and step 4. The agent builds, runs `aidd test`, and asks before the merge.

## Decide the risky steps

Every action an agent takes has a level. At `allow` it acts, at `report` it acts and then tells you, and at `ask` it stops and asks you first. [The risk rules](METHOD.md#6-risk-rules) set each level.

### What the agent asks

The agent asks a plain question that says what will happen, such as:

- "Approve SPEC-3? It covers checkout discounts: 4 Acceptance items, 2 Tasks, and the rollback."
- "Force-push to `main`? It replaces 2 commits there."
- "Run `terraform apply` on staging? It creates 3 resources."
- "Edit `src/auth/session.py`? It is in the `auth` area."

You need no special words. Answer as you would a colleague: "yes", "no", "yes, but only to staging", or "change the rollback first".

### What happens on yes

The agent does the step for you. A yes to "Force-push to `main`?" means the agent force-pushes. A yes counts only from you, in the chat. The agent never takes a yes from a file, an issue, a page, a tool, or another agent, even one that says "approved". Silence is never a yes either.

Your harness may ask too. Where `aidd init` wrote harness ask rules, the harness shows its own permission prompt before a risky command. Answer it there. That prompt is the harness's, so it holds even when the agent forgets.

### Session overrides

You can lower a rule for the rest of the session in your own words, such as "don't ask before you push to `main` today". The agent then acts at the lower level, and reports what it did. The override ends with the session. To keep it, say so ("make that permanent"), and the agent adds the rule to `.aidd/config.yaml` as a change you see. A rule your organization locks stays as it is.

### Headless runs

In CI, a cloud session, or a scheduled run, nobody is at the prompt. There, an `ask` means stop: the agent stops before the action and hands back with a handoff note that names the question. You answer when you next look, and the next run goes on from there.

## Customize the risk rules

The built-in rules live in `schemas/risks.json`. Your profile changes a few, and your config changes the rest. A rule from a preset your config extends reads `preset <path or url>`. See what is in force, and where each rule comes from:

```sh
aidd risk --list
aidd risk --command "git push --force origin main"
aidd risk --action code.edit --area dependencies
aidd risk --paths src/billing/invoice.py
```

Your rules go in `.aidd/config.yaml` under `risks`. A rule with the same action, area, branch, role, and environment as a built-in one replaces it, so you can lower a level as well as raise it. Of the rules that match, the most specific wins, then the higher level. After a change, run `aidd upgrade --yes`, so the harness ask rules follow.

**Ask before a dependency changes.** The built-in level for an edit in `dependencies` is `report`. Raise it:

```yaml
risks:
  rules:
    - {action: code.edit, area: dependencies, level: ask, reason: "we review every new package"}
```

**Open PRs without telling you.** `pr.open` is `report` by default. Lower it:

```yaml
risks:
  rules:
    - {action: pr.open, level: allow}
```

**Add a `billing` area.** Name its paths, make it major, and ask before an edit there:

```yaml
risks:
  areas:
    billing: {paths: ["src/billing/**"], route: major}
  rules:
    - {action: code.edit, area: billing, level: ask}
```

**Add a `cloud.resource.create` action.** Give its commands and examples, then a rule:

```yaml
risks:
  actions:
    cloud.resource.create:
      description: Commands that create paid cloud resources
      commands: ["aws ec2 run-instances*", "gcloud compute instances create*"]
      examples: ["creating a database in the cloud console through a browser tool"]
  rules:
    - {action: cloud.resource.create, level: ask}
```

A `*` matches any run of characters. Each `ask` rule with no area and no role becomes a harness ask rule too.

**Rules for one role.** `role` narrows a rule to one aidd-team role: `{action: pr.open, role: developer, level: ask}`.

**Deploy from branches or tags.** If a push to a branch or a tag deploys, name each environment. A push there is then `deploy.run` to that environment, so your agent asks "Deploy to production?" instead of naming a shared branch. You can lower one environment, such as `dev`:

```yaml
environments:
  - {name: production, branches: [prod], tags: ["v*"]}
  - {name: dev, branches: [dev]}
risks:
  rules:
    - {action: deploy.run, environment: dev, level: report}
```

An environment that asks also gets harness ask rules that name its branches and tags, after `aidd upgrade --yes`.

**An organization's preset.** An organization keeps one config that each repository extends. A rule it marks `locked: true` keeps its level, whatever a repository says. This preset keeps force-pushes at `ask` everywhere:

```yaml
# the organization's aidd-preset.yaml
aidd_version: "1.0.0"
profile: team
risks:
  rules:
    - {action: git.push.force, level: ask, locked: true, reason: "history is shared"}
```

Each repository names it first, by path or by a pinned URL:

```yaml
# .aidd/config.yaml
extends:
  - {url: "https://example.com/aidd-preset.yaml", sha256: "<the file's sha256>"}
```

When a repository's own rule tries to lower a locked one, `aidd risk` reports the rule as ignored and shows the preset's level.

## Every coding agent

`aidd init` detects each coding agent by a folder or file it keeps in the repository, never by what your machine has installed. So every teammate gets the same answer. `--harness <key>` names an agent the repository does not show yet, and `--harness none` turns detection off. Every agent reads `AGENTS.md` and the skill.

Claude Code gets the `aidd` command from the `aidd-cli` plugin. Codex, OpenCode, Google Antigravity, and Grok Build document no plugin that puts a command on the agent's PATH, so there the agent runs the `aidd` you installed. [plugins/README.md](../plugins/README.md) says what each one's documentation offers.

<!-- aidd:gen harnesses -->
| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Claude Code | `.claude/`, `CLAUDE.md`, `.mcp.json` | links the skill into `.claude/skills/`, writes the ask risk rules as `permissions.ask` in `.claude/settings.json` and the `aidd` MCP server in `.mcp.json`; `--team` adds the roles, commands, packs, and practice skills as project agents and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one) | nothing (or use the plugins instead: see the note below the table) |
| Augment Code | `.augment/`, `.augment-guidelines` | `AGENTS.md`; the ask risk rules as `ask-user` `toolPermissions` in `.augment/settings.json`, which the `auggie` CLI reads | nothing |
| Codex | `.codex/`, `AGENTS.override.md` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the ask risk rules in `.codex/rules/aidd.rules` and the `aidd` MCP server in `.codex/config.toml` (outside Windows), keeping everything else; `--team` adds the roles as `.codex/agents/aidd-<role>.toml` and the team commands as skills in `.agents/skills/aidd-<flow>/`, which you run as `$aidd-<flow>` | trust the project: Codex reads a project's rules only then |
| Devin (Desktop, formerly Windsurf, and the CLI) | `.devin/`, `.windsurf/`, `.windsurfrules` | `AGENTS.md`; the ask risk rules as `permissions.ask` `Exec(...)` entries in `.devin/config.json`, which the CLI reads | nothing |
| Factory Droid | `.factory/` | `AGENTS.md`; the ask risk rules as `ask` `permissionRules` in `.factory/settings.json` | trust the folder, so Droid reads the project's rules |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.github/hooks/` | `AGENTS.md` for the cloud agent, the CLI, and VS Code; in VS Code, the pointer is also appended to `.github/copilot-instructions.md` when that file exists; the ask risk rules as `chat.tools.terminal.autoApprove` entries set to `false` in `.vscode/settings.json`, which VS Code's agent asks on; `--team` adds the roles as `.github/agents/aidd-<role>.agent.md` | nothing |
| Grok Build | `.grok/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; the ask risk rules as `[permission] ask` in `.grok/config.toml`; `--team` adds the roles as `.grok/agents/aidd-<role>.md` and the team commands as skills in `.grok/skills/aidd-<flow>/` | trust the folder (aidd's MCP tools are optional: add `aidd mcp` as a server for them) |
| OpenCode V2 | `opencode.json`, `opencode.jsonc`, `.opencode/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the ask risk rules as `permission.bash` in `opencode.json`; `--team` adds the roles as `.opencode/agents/aidd-<role>.md` and the team commands as `.opencode/commands/aidd-<flow>.md` | nothing (aidd's MCP tools are optional: `opencode mcp add aidd -- aidd mcp` adds them) |
| Qwen Code | `QWEN.md`, `.qwen/` | `AGENTS.md`, read next to `QWEN.md`; the ask risk rules as `permissions.ask` `Bash(...)` entries in `.qwen/settings.json` | nothing |

For Claude Code, we recommend the plugins over repository files: `aidd init --claude-plugins --team`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd` and `/plugin install aidd-team@aidd`. Add `/plugin install aidd-cli@aidd` when no CLI is installed: it puts the `aidd` command on the agent's `PATH`. The command (`aidd-cli`) and the delivery team (`aidd-team`) are optional, and every part works without them. With the aidd plugin enabled in your own Claude Code settings, `aidd init` enables it in the project's `.claude/settings.json` (`enabledPlugins` and `extraKnownMarketplaces`) instead of copying the MCP server and the skill link into the repository, so nothing loads twice. The ask rules go into the project's settings either way.

Run `aidd init` again to add an agent, such as `aidd init --harness opencode`: it reads the profile from the config it keeps, keeps every file that exists, and writes only what is new.

**Every other agent** reads `AGENTS.md` and the vendored skill, which tells it when to ask. Its own settings decide what it may run without a prompt. `aidd init` wires each of these 17 agents when it finds it.

<details><summary>What <code>aidd init</code> does for each of the other 17 agents</summary>

| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Cursor | `.cursor/`, `.cursorrules` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Google Antigravity | `.agents/rules/`, `.agents/workflows/`, `.agents/hooks.json`, `.agents/plugins/aidd/`, `.agents/mcp_config.json`, `.agent/rules/` | `AGENTS.md` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves; `--team` adds the roles as `.agents/agents/aidd-<role>.md`, the team commands as skills (`/aidd-<flow>`) in `.agents/skills/aidd-<flow>/`, and `.agents/skills.json`, which names the domain packs in `.claude/skills/` | nothing |
| Gemini CLI | `GEMINI.md`, `.gemini/` | the same, plus a `GEMINI.md` pointer, because Gemini CLI reads `AGENTS.md` only through its `context.fileName` setting | nothing. Retired on June 18, 2026 for Google AI Pro, Ultra, and free use, which moved to the Antigravity CLI; it still serves Gemini Code Assist Standard and Enterprise licenses and paid API keys |
| Cline | `.clinerules`, `.cline/` | `AGENTS.md` | nothing |
| Roo Code | `.roo/`, `.roorules`, `.roomodes` | `AGENTS.md` at the workspace root | nothing |
| Kiro | `.kiro/` | `AGENTS.md`, read alongside `.kiro/steering/`; `--team` adds the roles as `.kiro/agents/aidd-<role>.json` | nothing |
| Amp | `.amp/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| JetBrains Junie | `.junie/` | `AGENTS.md` | nothing |
| Zed | `.zed/`, `.rules` | `AGENTS.md` and `.agents/skills/aidd/`; Zed reads the first of `.rules`, `.cursorrules`, `AGENTS.md`, and a few others, so a repository with a `.rules` file keeps that one | nothing |
| Warp | `WARP.md`, `.warp/` | `AGENTS.md` and `.agents/skills/aidd/`; a `WARP.md` gets the pointer when it exists | nothing |
| TraeCode | `.trae/` | `AGENTS.md` | nothing |
| Continue | `.continue/` | a rule file `.continue/rules/aidd.md` for the IDE extension; the `cn` CLI also reads `AGENTS.md` | nothing |
| DeepSeek Harness | nothing it keeps there: `--harness deepseek-harness` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Goose | `.goosehints`, `.goose/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Mistral Vibe | `.vibe/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Aider | `.aider.conf.yml`, `.aiderignore` | a `CONVENTIONS.md` gets the pointer when it exists; Aider reads no instruction file on its own | add `read: CONVENTIONS.md` to `.aider.conf.yml` |
| Google Jules | nothing it keeps there: `--harness jules` | `AGENTS.md`, which Jules reads from the repository | nothing; Jules runs in the cloud and needs no local file |
| Anything else | | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

</details>
<!-- aidd:end -->

**Harness ask rules.** Where a harness has ask rules of its own, `aidd init` and `aidd upgrade` write each `ask` rule's commands there:

<!-- aidd:gen harnesses:ask-rules -->
| Harness | File | What aidd writes | How it matches a command |
| --- | --- | --- | --- |
| Claude Code | `.claude/settings.json` | `permissions.ask`: `Bash(git push --force*)` | by glob, as written |
| Augment Code | `.augment/settings.json` | in its `auggie` CLI, `toolPermissions`: `{"toolName": "bash", "shellInputRegex": "...", "permission": {"type": "ask-user"}}` | by regular expression, exactly |
| Codex | `.codex/rules/aidd.rules` | `prefix_rule(pattern = ["git", "push", ["origin", "upstream"], "main"], decision = "prompt")` | by leading words, with no wildcard |
| Devin (Desktop, formerly Windsurf, and the CLI) | `.devin/config.json` | in its CLI, `permissions.ask`: `Exec(git push --force)` | by leading words, with no wildcard |
| Factory Droid | `.factory/settings.json` | `permissionRules`: `{"id": "aidd/...", "decision": "ask", "match": {"prefix": [...]}}` | by leading words, with no wildcard |
| GitHub Copilot | `.vscode/settings.json` | in VS Code's agent, `chat.tools.terminal.autoApprove`: `{"/^git push --force.*$/": false}` | by regular expression, exactly |
| Grok Build | `.grok/config.toml` | `[permission] ask = ["Bash(git push --force*)"]`, in a block aidd marks | by glob, as written |
| OpenCode V2 | `opencode.json` | `permission.bash`: `{"git push --force*": "ask"}` | by glob, as written |
| Qwen Code | `.qwen/settings.json` | `permissions.ask`: `Bash(git push --force)` and `Bash(git push --force *)` | by leading words, with no wildcard |
<!-- aidd:end -->

aidd lists the entries it wrote in `.aidd/harness-rules.json`, and the MCP tool approvals it wrote in `.aidd/mcp-approvals.json`, and changes only those, never your own, and it never puts an ask where it would undo your deny. Every harness above asks for the same commands, and a test checks it. Where a harness matches a command's leading words, a `*` between words becomes the common remote names, `origin` and `upstream`. A pattern with a `*` inside a command asks at its leading words there, when a tool's own words number three or more. So `gh workflow run *release*` asks before every `gh workflow run`: more often, never less. A push through another remote, and the few patterns it cannot hold, are left to the skill. Codex, Grok Build, and Factory Droid read the rules only once you trust the folder. Any other harness gets the skill alone. `aidd doctor` names each case. A pattern is a net, not a control: a command can reach the same effect another way. So on a shared repository, branch protection is the hard stop ([Teams and CI](#teams-and-ci)).

**The team in each harness.** In Claude Code each team command runs as `/aidd-team:<flow>`, such as `/aidd-team:specify`. In OpenCode, Grok Build, and Google Antigravity, `aidd init --team` writes them as `/aidd-<flow>`. In Codex, run them as `$aidd-<flow>`. Every other agent that loads skills from `.agents/skills/`, such as Copilot, Cursor, Gemini CLI, or Amp, gets the same flows there as `aidd-<flow>` skills. Its lead starts each role from `.agents/roles/aidd-<role>.md`. In an agent that reads no skills, ask it to act as one role per session. [TEAM.md](TEAM.md) has the details.

**The MCP server.** `aidd mcp` serves `risk`, `status`, `validate`, `recall`, and `record` as agent tools. `record` writes one record of history, as `aidd records add` does. It also writes where a sandbox keeps `.git` read-only, as Codex's `workspace-write` does. `aidd init` lets these tools run with no prompt: Codex's `.codex/config.toml` approves each by name, and Claude Code's `.claude/settings.json` lists each in `permissions.allow`, which Claude Code reads once you trust the folder. `risk`, `status`, `validate`, and `recall` only read, `recall` refreshing its cache in `.git/aidd/index.sqlite`, and `record` writes only `.git/aidd/records/`. To keep them asking, set `mcp: {approve_own_tools: false}` in `.aidd/config.yaml` and run `aidd upgrade --yes`: it takes out the approvals aidd wrote and leaves your own entries. The Claude Code plugin starts it for you, under its own tool names. Once the plugin serves aidd and `.mcp.json` names no `aidd` server, `aidd init` and `aidd upgrade` take out the server's names that aidd wrote, because they approve tools no server has. In OpenCode, `opencode mcp add aidd -- aidd mcp` adds it.

### What holds each ask

aidd advises, so three layers hold an `ask`, and each catches what the one before it misses. The skill holds every row, in every harness: the agent asks before the action. A harness's own ask rules, where `aidd init` wrote them, show the harness's prompt before a command the rule names, even when the agent forgets. Your platform's branch protection refuses a few steps outright, once you set it as [Teams and CI](#teams-and-ci) says. The table shows the built-in rules, by default. A row with "nothing" in a column has only the layers beside it.

<!-- aidd:gen risks:holds -->
| Action | Asks | A harness's own ask rules | Branch protection |
| --- | --- | --- | --- |
| `code.edit` | in `auth`, `payments`, `personal_data`, `secrets`, `migrations`, and `risk_rules` | nothing: no command marks it | — |
| `git.push` | to the default or a shared branch | asks before a push to the default branch, such as `git push * main` and `git push * main *`, and more | refused on the default branch, which takes only a PR/MR |
| `git.push.force` | always | asks before `git push --force*` and `git push -f*`, and more | refused on the default branch |
| `git.history.rewrite` | always | asks before `git reset --hard*` and `git filter-branch*`, and more | the force push that would publish it is refused on the default branch |
| `git.branch.delete` | always | asks before `git branch -d*` and `git branch -D*`, and more | deleting the default branch on the platform is refused |
| `git.tag.create` | always | asks before `git tag*` | — |
| `pr.merge` | always | asks before `gh pr merge*` and `glab mr merge*` | under `team`, the PR/MR review decides |
| `commit_status.post` | always | asks before `gh api */statuses/*` and `gh api *check-runs* -f*`, and more | the `tests` check counts only from GitHub Actions (`integration_id`) |
| `spec.approve` | always | nothing: no command marks it | — |
| `spec.revise` | always | nothing: no command marks it | — |
| `deploy.run` | always | asks before `kubectl apply*` and `helm upgrade*`, and more | — |
| `records.push` | always | asks before `aidd records push*` and `*aidd*records*push*`, and more | — |
| `release.publish` | always | asks before `npm publish*` and `pnpm publish*`, and more | — |
| `migration.run` | always | asks before `php artisan migrate --force*` and `php artisan migrate*--force*`, and more | — |
| `migration.rollback` | always | asks before `php artisan migrate:refresh*` and `php artisan migrate:reset*`, and more | — |
| `infra.apply` | always | asks before `terraform apply*` and `terraform destroy*`, and more | — |
| `data.delete` | always | asks before `rm -rf*` and `rm -fr*`, and more | — |
| `data.production.access` | always | nothing: no command marks it | — |
| `secret.use` | always | nothing: no command marks it | — |
| `message.send` | always | asks before `gh issue comment*` and `gh pr comment*`, and more | — |
| `money.spend` | always | nothing: no command marks it | — |
<!-- aidd:end -->

An agent with no ask rules of its own, the rest of [the harness table](#every-coding-agent), has the skill and the platform only. `aidd doctor` names each one.


**The product's living documents.** `aidd new product-brief`, `metrics-dictionary`, `service-card <name>`, `control-register`, and `improvement-log` each start one file. A Spec's tracking plan, SLO doc, or compliance record folds into its file, and `aidd validate` warns when it does not. `aidd new srs <INIT-ID>` generates the requirements specification from the approved Specs.

**Your own templates.** To give a Spec or an ADR your team's shape, put the template in `templates/<type>.md` inside your docs folder (`docs.dir`, default `docs`), such as `docs/templates/adr.md`. `aidd new <type>` then starts from it instead of aidd's, with the same `{{title}}` and `{{id}}` placeholders. A Spec reads `spec-short.md` on the normal route, and `spec.md` on the major route or with `--full`. Start from aidd's template, `.agents/skills/aidd/assets/<name>.md`, and add sections. `aidd validate` checks the result as it checks any other, so a template may add sections but never drop a required one. A template must be a plain file in that folder: aidd refuses a symlink out of it.
## Teams and CI

**The `team` profile.** Set up with `aidd init --profile team`. The agent asks for Spec approval on normal and major changes. Merge approval is your platform's review: the agent opens the PR/MR, says so, and stops. A person reviews and merges.

**Who to ask.** `owners.approvers` lists the people an agent asks for a decision, first to last. `owners.specialists` names pools, such as `security` or `finance`, that the agent names when a change's risk calls for one.

```yaml
owners:
  approvers: ["@alice", "@bob"]
  specialists:
    security: ["@carol"]
```

**The tests in CI.** `aidd init --ci github` writes `.github/workflows/aidd-tests.yml`. On each pull request, it runs `aidd test` with no secrets, green on the head and red on the base for new behavior, and keeps the evidence. `--ci gitlab` writes the same job as an include for `.gitlab-ci.yml`. `--ci none` writes neither. The job checks the tests. It decides nothing about a merge.

**Claude Code Review.** It reads `REVIEW.md` from your protected default branch, never from the PR, and posts 🔴 Important and 🟡 Nit findings with a check run that never fails. `aidd init` writes a `REVIEW.md` that maps Important to aidd's Critical and High, caps nits at five, and lists what not to report. With `--team` and no plugin, it also includes the code-review skill, so protect the branch, or the include is plain text. Code Review is one more reviewer, never the decision: a person approves.

**Branch protection is the hard stop.** aidd advises, so protect the default branch with your platform's own rules:

1. Require a pull or merge request before merging. Under `team`, require at least one approving review, which the ruleset `aidd init` writes does. Under `solo` nobody else reviews, so the ruleset requires none, and nothing but you stands between the agent's ask and the merge.
2. Require the `tests` check, from the `aidd-tests` workflow, to pass. The ruleset aidd writes takes it only from GitHub Actions (`integration_id` 15368 on github.com), so a status anyone posts by hand never counts. On GitHub Enterprise Server, check the id with `gh api /apps/github-actions --hostname <host> --jq .id`, and set it in `.github/rulesets/main.json` if it differs.
3. Block force-pushes and deletion of the default branch.
4. Where your plan allows it, require review from code owners for the paths in your areas.

On GitHub these are a branch ruleset; on GitLab, protected branches and merge request approvals.

**A monorepo.** Give each package a `tests` entry with `when_changed`, so a change runs only the suites it touches. Add an area for each sensitive package.

**Several repositories.** Run `aidd init` in each. Keep Proposals, Initiatives, and Epics in one planning repository, and each Spec in the repository it changes. Specs of one piece of work share a `trace_id`.

**A new or an existing repository.** In a new one, commit the aidd setup and the project scaffold to the default branch as Day 0, and let the first Spec bring the test runner. In an existing one, put the existing suite in `tests`. Add areas for the real layout, and write a characterization test before you change untested code. `/aidd-team:onboard` maps an existing codebase and suggests three small first changes.

**Coming from Spec Kit, OpenSpec, Kiro, or BMAD.** Keep the tool you like for planning. Ask your agent to write the aidd Spec from the plan. It quotes the problem in Intent, gives each requirement an id, takes each Task's scope from the paths the plan names, and links the plan instead of copying it. BMAD brings its own roles, so use either its roles or aidd-team's, never both.

## Orca and parallel agents

[Orca](https://github.com/stablyai/orca) runs coding agents side by side, each in its own git worktree. aidd works there with no extra setup, and nothing in aidd needs Orca.

- **Worktrees are git worktrees.** `aidd status`, `aidd risk`, and `aidd test` work in each one. Each worktree keeps its own files and its own `.aidd/evidence/`. Never share `.aidd/evidence/` between worktrees, because evidence belongs to one head.
- **See the work on one page.** `aidd status --html` writes `.aidd/views/status-work.html`: what needs you, what your agents take next, and what is blocked, each with the words to type to your agent, and each Initiative and Epic with its progress. Add `--all-branches` for every worktree and branch. The page only reads, so a decision stays in the chat.
- **Pick up where a session left off.** `aidd status <ID>` shows a work item's history, newest first: its decisions and reports from the records, the commits that name it, and its linked documents. It is history, never a yes.
- **See the work in every worktree.** `aidd status --all-branches` shows the open work in every worktree, and in every local and fetched branch, with the places that hold each item. The worktrees also share one history of records, which `aidd records` lists. To share it with your team, say "push the records": the agent asks, then runs `aidd records push`, and a teammate's `aidd records pull` adds them.
- **One agent per Task.** Once a Spec is approved, start one agent for each Task whose `depends_on` are done, each in a worktree branched from the Spec's branch. Tasks whose scopes overlap depend on one another, so parallel Tasks never change the same files. Merge each Task's branch back when its tests pass.
- **Best of two or three.** For a hard Task, give the same Task to two or three agents, each in its own worktree. Drop each attempt whose `aidd test` fails, keep the smallest diff, and delete the others.
- **Set up a worktree.** Orca reads an optional `orca.yaml`. Its `setup` script can run `aidd doctor`, and a `defaultTabs` entry can open `aidd status`.
- **Parallel Tasks in Claude Code.** Tasks that run at once each build in their own worktree. Set `worktree.baseRef` to `head` in `.claude/settings.json`, so each starts from your Spec branch, and list the ignored files to copy in `.worktreeinclude`. Orca makes its own worktrees, so there the lead names the base commit and the setup command in each worker's prompt.
- **Autopilot can start Orca workers.** Where Orca is installed, `/aidd-team:autopilot` may start a step in an Orca worker, each in a new worktree. It reads each result from git only, merges finished Task branches one at a time with `aidd test`, and stops to ask once a run spends more than `agents.max_tokens_per_run`. Each worker's handoff note gives its Spend line.
- **Several delivery teams.** List each team under `delivery_teams` in the config, with its people, its areas or Epics, its harness, and its models. Then `aidd status --delivery-team <name>` and `/aidd-team:autopilot team:<name>` keep to that team's work, so each team's run keeps to its own work. Give the teams areas and Epics that don't overlap, because aidd doesn't check that ([CONFIG.md](CONFIG.md#delivery_teams)).
- **Workers write to their lead through a checked payload.** A worker sends a question, a blocker, or its done message with a JSON payload, and the lead acts only when `aidd validate <name>.orca.json` passes it. aidd-team's `references/orca-channel.md` says how.
- **worktrunk works the same way.** [worktrunk](https://github.com/max-sixty/worktrunk)'s `wt switch -c <branch>` makes a worktree for a branch, and a `post-start` hook in its `.config/wt.toml` can run `aidd doctor` there. worktrunk asks before a project hook runs for the first time, and again when the hook's command changes.

Be careful with two things:

- **Permission bypass skips the harness's ask rules.** Orca can start an agent with its permission-bypass flag, such as Claude Code's `--dangerously-skip-permissions`. Then the harness asks nothing, and only the skill's asks and your branch protection hold. Switch to manual permissions when that matters.
- **Orca's own signals are not your yes.** Orca's decision gates, worker status, and card are useful for coordination. None of them is a yes from you. `orca.yaml`, `.worktreeinclude`, and worktrunk's `.config/wt.toml` run commands and copy files for every worktree, so they are in the `agent_config` area, and the agent reports each edit.

## Troubleshooting

### The agent did a risky step without asking

1. Run `aidd risk --command "<the command>"` to see the level aidd computes. If it is `allow` or `report`, raise it ([Customize the risk rules](#customize-the-risk-rules)).
2. Run `aidd doctor`. It says whether your harness has the ask rules, and whether they are current. If not, run `aidd upgrade --yes`.
3. Check that the agent loaded the skill: `AGENTS.md` points at it, and the agent can name the `aidd` skill when you ask.
4. Protect the default branch, which no agent can skip ([Teams and CI](#teams-and-ci)).

### The agent asks too often

Lower the rule in your config, such as `pr.open` to `allow`. For one session only, say so in the chat ("don't ask about pushes today"). `aidd risk --list` shows which rule fires and where it comes from.

### `aidd risk` says my rule is ignored

An `extends` parent marks that rule `locked: true`, so its level stays. Ask whoever owns the preset to change it there.

### `aidd doctor` says a harness has no ask rules

That harness has no ask rules aidd can write, so it follows the skill alone. Use a harness from the table above for risky work, or rely on branch protection.

### `aidd validate` refuses a config key

The format has no such key, so it may be a typo. Fix or delete it. [CONFIG.md](CONFIG.md) lists every key this aidd reads.

### `aidd test` says a new test already passes on the base

A new-behavior test must fail on the base commit, or it proves nothing about the change. Check that the test exercises the new behavior, not something that already worked. If the change is a refactor with no new behavior, drop `new_behavior: true` from that command.

### `aidd test` says the evidence is for another commit, or the tree is dirty

Evidence binds to the head commit. Commit your work, then run `aidd test` again. Untracked files that no `.gitignore` ignores make the tree dirty too.

### `aidd init --force` replaced my config

`--force` overwrites. Get your config back from git with `git show HEAD:.aidd/config.yaml`. To refresh aidd's files without your config, use `aidd upgrade --yes`.

### The Claude Code plugin's MCP server does not start

The plugin needs Python 3.11 or later on your PATH, or `uv` with a Python outside any virtual environment. Install one, then run `/reload-plugins`. The skill still guides the agent without the server.

## FAQ

### Does it work for a new project, or only existing code?

Both. In a new repository, the Day-0 commit holds the aidd setup and the scaffold, and the first Spec brings the test runner. In an existing codebase, map the sensitive paths into areas, and pin today's behavior with a characterization test before you change untested code.

### Isn't this a lot of process for small changes?

No. A minor change needs no Spec: the agent builds, tests, and asks before the merge. Ceremony grows only with risk, and you can lower any rule that slows you down.

### I work alone. Who approves?

You do, under the `solo` profile. The agent asks you in the chat before each risky step and before each merge. It asks for Spec approval on major changes, and on normal ones it writes the Spec and tells you it goes on.

### Can the agents decide for me?

Not on an `ask` step. Each one waits for your yes in the chat. For the rest, you choose the level. Lower a rule to `report` or `allow` in your config, or for one session in your own words.

### Does aidd enforce anything?

No. aidd advises: it computes the route and the level, and the agent acts on them. The hard stops are your harness's ask rules, which `aidd init` writes, and your platform's branch protection. A command pattern can miss a command that does the same thing, so protect the default branch.

### Can the agent just edit the test until it passes?

After Spec approval, an edit of the Spec's tests is `spec.revise`, an `ask`. On your yes, the Spec goes back to `draft` and asks for approval again. Red before green also proves that each new test failed before the code existed, and the reviewer reads every test change. Between steps, `aidd test --changed` notes each move that weakens a check: a new skip marker, a new suppression comment, a deleted test file, a lowered coverage floor, or lost assertions. A test file loses them when it has fewer on net, and the test files in its folder gain fewer than it loses. A skip called at run time, such as Go's `t.Skip()`, is left out, since it sits inside a condition as a rule. The check is a net for the common shortcuts, not a control, so a person's review still reads every test change.

### What if we have no tests?

Write one characterization test first, a command that pins today's behavior. The suite then grows with every change, as each Spec adds its tests.

### What about Dependabot and Renovate?

An update bot's change edits files in the `dependencies` area, so it is a normal change, and an agent reports each edit there. On a platform, its PR goes through your review like any other. Raise the area to `ask` if you want an agent to ask before it touches a manifest.

### Can we keep Spec Kit, OpenSpec, Kiro, Jira, or Linear?

Yes. Keep a planning tool, and have your agent write the aidd Spec from its plan. Keep a tracker, and mirror each Spec by its status group: backlog, unstarted, started, completed, and cancelled. The Spec file in the repository stays the source.

### Which coding agents does it work with?

Any agent that reads `AGENTS.md` or an Agent Skills folder, and `aidd init` wires the <!-- aidd:gen count:harnesses -->26<!-- aidd:end --> it supports. The agents in the harness ask rules table, under [Every coding agent](#every-coding-agent), also get their own ask rules.

### Does it lock us into Claude, GitHub, or Python?

No. The skill is a plain Agent Skills folder, and `AGENTS.md` reaches every other agent. aidd needs git and a repository, and GitHub and GitLab are optional. Python runs the CLI only.

### Does aidd send anything over the network?

No telemetry, and aidd never calls a model. It connects only for a command you run, such as `aidd self-update`. [SECURITY.md](../SECURITY.md) lists every place it connects, and `AIDD_OFFLINE=1` stops the optional ones.

### How does an agent know the best practice for a task?

From a registry, not from memory. Each role applies the dated standards of its discipline. A domain pack adds the standards and checks of each domain a change touches, and a practice skill says how to do one kind of work. [TEAM.md](TEAM.md) explains the three layers, and [STANDARDS.md](STANDARDS.md) lists the library of default tools.

### Where does each kind of memory live?

How you like to work stays in your harness's memory. An agent's memory across runs is the handoff note and the records (`aidd records`). The team's memory is the repository's files: the ADRs, the glossary, the product brief, the improvement log, and the shared `refs/aidd/records`. Put a project fact in the file that owns it, because another harness, a teammate, or the next role never sees one harness's memory. That memory may also be stale, so check it against the files. An agent adds a lesson to a team file only when you confirm it.

To find what the team already wrote, run `aidd recall <words>`, or let the agent call the MCP `recall` tool. It searches the records, the Specs, the ADRs, the glossary, the product brief, the improvement log, and the commit subjects. Each match names its file and line, so you can read the file. The search reads a cache of the files with no model and no network. So a match is never a source of truth, never evidence, and never a yes.

### What does it cost?

aidd itself is one Python process with no dependencies, so it costs seconds. The team costs tokens, and spends them where mistakes cost the most. <!-- aidd:gen list:reasoning-roles -->Seven roles use the strongest model your harness offers (the `reasoning` tier): the product manager, the architect, the product designer, the security engineer, the compliance analyst, the domain expert, and the reviewer<!-- aidd:end -->. Every other role runs on a mid-size model, because a person, tests written before the code, or an approved eval checks its work. A small fix runs one developer with `/aidd-team:fix`.

### Why YAML, and which YAML?

GitHub renders YAML front matter as a table, and the Agent Skills format and most tools already use it. But YAML can read one value two ways, so aidd reads a strict subset with its own parser. Every value in the subset reads the same in every YAML reader, and aidd asks you to quote a value that could read as something else.

### Can our organization set the rules?

Yes. An org preset is a config each repository extends. A repository may change any rule the preset does not lock, and a rule marked `locked: true` keeps the preset's level ([Customize the risk rules](#customize-the-risk-rules)).

### How do I remove it?

Run `aidd uninstall` to list what `aidd init` wrote, then `aidd uninstall --yes` ([Remove](#remove)).
