# The aidd guide

This guide takes you from install to a team running many agents. [METHOD.md](METHOD.md) is the method itself, and [GLOSSARY.md](GLOSSARY.md) defines each term. [CLI.md](CLI.md) has every command and flag, and [CONFIG.md](CONFIG.md) every config key. [decisions/README.md](decisions/README.md) says why aidd is as it is.

Once aidd is installed, say your idea or the change you want to your agent, or with the development team in Claude Code, type `/aidd-team:autopilot` and the idea. [Your first change](#your-first-change) walks through one.

- [Install](#install)
- [Your first change](#your-first-change)
- [Decide the risky steps](#decide-the-risky-steps)
- [Change your mind](#change-your-mind)
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

It follows [llms-install.md](../llms-install.md). It installs the aidd CLI, shows you what aidd found, and asks a few plain choices, such as which profile you want. Then it writes the files and checks the setup. It commits on its own branch, and the setup reaches your main branch only on your yes or through your review. In each new repository, say the same sentence again.

> [!IMPORTANT]
> **Pre-release.** No `v1.0.0` tag exists yet, so every command that names `@v1.0.0` fails until the release. Install from the repository, as below. aidd isn't on PyPI, so a package named `aidd` there is not this one.

### The CLI

The CLI needs Python 3.11 or later and git. It bundles the schemas, the skill, the CI templates, and the team plugin, so `aidd init` works offline.

| Method | Command |
| --- | --- |
| uv | `uv tool install git+https://github.com/thaithienvanid/aidd` |
| pipx | `pipx install git+https://github.com/thaithienvanid/aidd` |
| uv, no install | `uvx --from git+https://github.com/thaithienvanid/aidd aidd --help` |
| uv, look first | `uvx --from git+https://github.com/thaithienvanid/aidd aidd init --dry-run`, which reads your repository and writes nothing |
| From a checkout | `python3 -m venv .venv && .venv/bin/pip install .` |
| One line | `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh \| AIDD_REF=<sha> sh` |

Add `@<sha>` to a URL to pin one commit. After the release, add `@v1.0.0` instead. With no `AIDD_REF`, the one-line installer installs the release when one is out. When none is, it resolves `main` to one commit, says that this is unreleased code with no `SHA256SUMS` or provenance to check, and builds from source at that commit. The one-line installer uses uv, pipx, or a private venv, whichever you have. With `AIDD_REF=<release tag>`, it installs nothing until the wheel matches the release's `SHA256SUMS`. With `gh` on your PATH, it also waits until `gh attestation verify` accepts the wheel's build provenance.

Each GitHub Release will also carry `aidd.pyz`, the whole CLI as one file, for a machine where you can't install packages. Run it as `python3 aidd.pyz --version`.

### Claude Code plugins

In Claude Code, add the marketplace and install the plugins:

```text
/plugin marketplace add thaithienvanid/aidd
/plugin install aidd@aidd          # the skill and the MCP server
/plugin install aidd-cli@aidd      # the aidd command on the agent's PATH (optional)
/plugin install aidd-team@aidd     # the development team (optional)
/plugin install aidd-packs@aidd    # the domain packs, for a project that calls for one (optional)
/reload-plugins
```

Until aidd's first release, that marketplace follows `main`, so the plugins carry each commit there, released or not. Each release moves the `stable` branch to its commit, so after the first release, add `thaithienvanid/aidd#stable` instead and get plugin updates only with a release. `aidd init --claude-plugins` picks `stable` once it exists, `aidd upgrade --yes` moves the project's marketplace there, and `aidd doctor` says which branch each settings file follows.

Only `aidd@aidd` is needed. `aidd-cli` puts `aidd` on the PATH of Claude Code's Bash tool, so you need no other install. `aidd-team` brings the <!-- aidd:gen count:roles -->12<!-- aidd:end --> roles, the flow commands, and the practice skills. `aidd-packs` brings the domain packs, and its descriptions share Claude Code's skill listing budget, so enable it in a project that calls for a pack: `aidd doctor` names the packs a repository calls for. From a local folder, `/plugin marketplace add /path/to/aidd` reads the plugins in place.

### Set up a repository

```sh
aidd init --dry-run      # see what it proposes; writes nothing
aidd init --aidd-team    # asks the profile, writes the files, and says what to commit
aidd doctor              # check the wiring, the config, and the risk rules
```

`aidd init` writes these:

- `.aidd/config.yaml`, which names the profile, the tests, and your own risk rules. [CONFIG.md](CONFIG.md) has every key.
- A block in `AGENTS.md` that points every coding agent at the skill, and the skill itself in `.agents/skills/aidd/`.
- The harness ask rules for each coding agent it finds, so the harness itself asks you before a risky command ([Every coding agent](#every-coding-agent)).
- With `--aidd-team`, the development team's roles and commands. With `--ci github` or `--ci gitlab`, the CI job that runs the tests. With no `--ci`, it writes GitHub's files only when the repository has a remote, and with none, it says how to add CI later.

After `aidd init`, restart your coding agent in the folder, because it loads aidd only when a session starts. Claude Code then asks you to trust the folder, and to install the plugins the project enables or approve the `aidd` MCP server. Say yes to each.

For a script, pass the answers: `aidd init --profile solo --ci none`. Run `aidd init --harness <key>` later to add a coding agent. It keeps every file that exists and writes only what is new.

### Update

1. Run `aidd self-update`. It installs the latest release the way you installed aidd, and only after it checks the wheel. `--dry-run` only says what it would install. Until the first release, it takes the unverified tip of `main` and says so. `--main` takes that tip even after a release, and releases win again with no flag.
2. In each repository, run `aidd upgrade`. It is a dry run that lists what it would change. First come the retired names in your config and work items (below). Then come the skill, the team files, the text between aidd's marks in `AGENTS.md`, the harness ask rules, the CI pins, and `aidd_version`. `aidd upgrade --yes` makes the changes, keeping your own text in `AGENTS.md` and any team file you edited. To replace a kept team file with the latest, remove it and run `aidd upgrade --yes`. It then runs the checks of `aidd validate`, lists each problem that remains, and exits 1 while one remains.
3. For the Claude Code plugins, run `claude plugin marketplace update aidd`, then `claude plugin update aidd@aidd`, and the same for `aidd-cli@aidd` and `aidd-team@aidd`.

Merge the upgrade as one change. To roll it back, revert that change.

One `claude plugin update` moves every project on your machine at once, while the `aidd` command and each repository's files stay as they were. `aidd doctor` says so. It warns when the plugin or the skill in the repository is newer than the `aidd` command (run `aidd self-update`), when the plugin is older (step 3), and when a file still holds a retired name (run `aidd upgrade --yes`). It reads each version from a file, and says nothing for a version it cannot read.

`aidd upgrade` also moves each file that still holds a retired name, and prints a line for each change, such as `would migrate specs/SPEC-1.md: old_key -> new_key (retired in 1.1.0)`. Those files are the config, the Specs, Intents, proposals, runbooks, postmortems, releases, explorations, and handoff notes, and the edited copies of library standards. It reads the shape from the keys in the file, so it needs no version and keeps no record of what ran. It edits the text of one key at a time, so your comments, key order, quoting, and line endings stay. A cut prints the value it removes. A name it cannot place on a line of its own stays as it is, such as one inside `{...}` or one beside its replacement. A `manual` line names the file and says what to change, and `aidd validate` names it too. A second run changes nothing. `aidd upgrade --only ask-rules` moves no file. A `cli_value` row is a value you type after a flag, which no file holds, so the CLI refuses it and says what to type now. These are the names aidd retired:

<!-- aidd:gen retired:names -->
No name is retired yet.
<!-- aidd:end -->

### Remove

1. Run `aidd uninstall` to list everything `aidd init` wrote, then `aidd uninstall --yes` to remove it. It keeps your Specs and every file you changed since, and says so.
2. Run `claude plugin uninstall aidd@aidd`, and the same for each other plugin you installed.
3. Remove the CLI with `uv tool uninstall aidd` or `pipx uninstall aidd`.

## Your first change

In about ten minutes, you take one change through the loop on your own machine, with no platform and no CI, because a repository with no remote gets no CI files. You need Python 3.11+, git, the `aidd` CLI, and a coding agent. The commands use the `sh` syntax of macOS and Linux.

**1. Make a practice repository**, with a tiny Python app and one test. You can ask your coding agent in these words: "Make a git repository `aidd-practice` on `main`, with `app/cart.py`, where `total(items)` returns their sum, and one unittest for it. Commit it." Or make it yourself:

```sh
mkdir aidd-practice && cd aidd-practice
git init -b main
mkdir app tests && touch app/__init__.py tests/__init__.py
echo '__pycache__/' > .gitignore
cat > app/cart.py <<'EOF'
def total(items):
    return sum(items)
EOF
cat > tests/test_cart.py <<'EOF'
import unittest
from app.cart import total


class Cart(unittest.TestCase):
    def test_total(self):
        self.assertEqual(total([1, 2]), 3)
EOF
git add -A && git commit -m "scaffold"
```

**2. Set up aidd** with the `solo` profile, for one person directing agents. `--test` names the command that runs your tests, so `aidd test` runs it on every change:

```sh
aidd init --profile solo --test "python3 -m unittest"
aidd doctor
```

Commit the setup straight to `main`, as your starting point: `git add -A && git commit -m "chore: adopt aidd"`.

**3. Ask for the change.** Start your coding agent in the folder and say: "Add `discount(total, percent)` in `app/discount.py`, with a test." The agent works on a branch, and before its first edit it asks aidd how careful to be:

```sh
aidd risk --paths app/discount.py
```

It prints `minor`: a small change in no risky folder, so it needs no Spec. A Spec is a short document of what the change must do, with the tests that prove it, and `aidd explain spec` says more. Ask for one anyway ("write a Spec first"), so you see the test fail before the code exists. The agent writes it in `specs/SPEC-1.md`.

**4. Approve the Spec.** Under `solo`, the agent asks you to approve a Spec only for a risky change, so here it would go on. Say "ask me before you build", and it asks:

```text
Approve SPEC-1? It adds discount(total, percent) in app/discount.py, and its test fails until the code exists. I recommend yes. Reply "yes", or "no" and what to change.
```

Read the Spec and its test, then answer in your own words, such as "yes". The agent records your yes in the Spec and commits it. That record is the agent's note, not proof, and it says so.

**5. Build it and prove it.** The agent writes the code, with any unit tests it needs, and runs the tests:

```sh
aidd test --spec specs/SPEC-1.md
```

`aidd test` runs every test on your latest commit, where they pass. It also runs the new test on `main`, where it fails, because `app/discount.py` doesn't exist there yet. So the test proves the new code, and it doesn't pass by accident. The results go in `.aidd/evidence/`, tied to that commit.

**6. Merge.** The agent asks before the change reaches `main`:

```text
Merge the discount branch into main? 2 commits, and the tests pass on the latest one.
```

Say yes, and the agent merges it. Nothing left your machine. `aidd status` now shows SPEC-1 as `done`.

A small change skips the Spec and step 4. The agent builds, runs `aidd test`, and asks before the merge.

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

### Let the delegate decide for you

If you would rather not be asked each time, set a standing delegation: `aidd init --delegate`. `aidd init` reads your deploy workflows. When one names the default branch, it writes the environments they name, with a comment on the file and line beside each. It cannot see a host's Git integration, such as Vercel or Netlify, so tell it where a push deploys with `--environment production=main` (or `refs/tags/v*` for a tag), `--own-environment dev=dev` for one only you use, or `--environment none` when nothing does. Until you do, a delegated merge stays yours, and `aidd delegate check` says so. `aidd doctor` warns when `environments: []` sits beside a workflow that deploys on the default branch, or when an environment's branches are gone. A workflow, or a file a host deploys from such as `vercel.json`, that deploys on the default branch keeps the merge yours too. Commit the config to the default branch, since only its tip counts. Then the `aidd-team:delegate` role answers four asks for you, inside limits. They are Spec approval, a push of the change's own branch, and a merge on GitHub once the `tests` check passed on its head. With no remote, the fourth is a local merge once the check ran your suite itself. Before each one, `aidd delegate check` reads the evidence again, and the delegate may say yes only when it passes. The delegate reads your Spec whole, and a Spec or a commit message too long to fit, or one with a hidden character, comes back to you with the part named. If you keep `spec.approve` for yourself, you merge a Spec-first change yourself too, because only the delegate's own approval of a Spec counts for a delegated merge. A deploy, a migration, a new dependency, a secret, and a change to what decides always stay yours, and so does anything the check defers.

`aidd status` shows what was decided for you. `aidd delegate stop` turns it off in this clone at once, and after `review_due` every ask comes back to you. Claude Code is the one coding agent that answers a delegated ask in this version; every other agent keeps asking you. When the hook fails or never loads (`claude --bare`, `disableAllHooks`), you get the prompt. A Claude Code mod that approves the call, a merge through another MCP server's tool, or an action no ask rule names passes the hook with no prompt. Before you delegate a merge, protect the default branch: require the `tests` check, and block force pushes and deletion.

### Headless runs

In CI, a cloud session, or a scheduled run, nobody is at the prompt. There, an `ask` means stop: the agent stops before the action and hands back with a handoff note that names the question. You answer when you next look, and the next run goes on from there.

The agent cannot record your approval of an Intent there, because the commit that records it asks and nobody answers. So it stops. `aidd status` then gives you one command to run in your own terminal, such as `aidd approve INTENT-1 INTENT-2`, which names every Intent of one request. Read each Intent first. The command sets `approval` to your git identity and now on those Intents alone, and commits them as you, with your `Approved-by:` line and an `Approves:` line that names each Intent. That commit is what makes the approval hold: an `approval` that no such commit brought reads as a draft.

## Change your mind

Say any of these in your own words, at any point. The rows run in the order a change meets them:

| You want to | Say | What the agent does |
| --- | --- | --- |
| Change an answer or a pick | "Change my pick to B" | Before Spec approval, it updates the plan or the Spec. After, it asks first, because the Spec and its tests need your approval again. |
| Skip a step | "Skip the design review for this change" | It skips it for this change only, and the commit says so. It never skips a question that waits for your yes. |
| Go faster | "Don't ask before you push today" | It lowers that rule for this session ([Session overrides](#session-overrides)). |
| Pause one change | "Pause SPEC-3 until the API is ready" | It marks the Spec blocked, and goes on with the rest. |
| Stop the run | "Stop", or Esc in Claude Code | It stops and says what is saved, and the words to go on. |
| Go on after a stop | "Go on" | It starts again where it stopped. |
| Undo a merge | "Undo the discount merge" | It reverts it on a branch, runs the tests, and asks before the revert reaches `main`. |

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

**Deploy from branches or tags.** If a push to a branch or a tag deploys, name each environment. A push there is then `deploy.run` to that environment, so your agent asks "Deploy to production?" instead of naming a shared branch. Mark an environment that only you use with `shared: false`, so your agent deploys there and then tells you:

```yaml
environments:
  - {name: production, branches: [prod], tags: ["v*"]}
  - {name: staging, branches: ["release/*"]}
  - {name: dev, branches: [dev], shared: false}
```

Every environment is shared unless you mark it, so a deploy to `staging` or `production` still asks. A deploy command that names no environment, such as `kubectl apply` or `vercel deploy --prod`, asks too, because aidd cannot tell where it goes. To change one environment's level, add a rule that names it. So `{action: deploy.run, environment: dev, level: ask}` makes your own environment ask again.

Name your own environment's branches and tags without a wildcard. A glob such as `dev/*` can match a teammate's branch, so a push it matches still asks, unless it pushes the branch you have checked out. A wildcard tag glob, such as `dev-*`, never gives way. `aidd validate` and `aidd doctor` warn about such a glob. Under a standing delegation, a deploy to your own environment still reports when it names its branches and tags exactly, and asks when it has a wildcard or a parent locked a rule for deploys.

An environment that asks also gets harness ask rules that name its branches and tags, after `aidd upgrade --yes`.

**An organization's preset.** An organization keeps one config that each repository extends. A rule it marks `locked: true` is a floor: a repository's rules never lower the level below it. This preset keeps force-pushes at `ask` everywhere:

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

When a repository's own rule tries to lower a locked one, `aidd risk` reports the rule as ignored and shows the preset's level. A lock never lowers anything either: one set below aidd's built-in level changes nothing there, so a preset that locks `code.edit: report` still asks about edits in `auth` and `payments`. To ask more than a lock, name a narrower selector. `aidd risk --list` ends with a `lock:` line for each lock: the rules it raises to its level, and that it lowers none.

## Every coding agent

`aidd init` detects each coding agent by a folder or file it keeps in the repository. It also wires the agent that runs `aidd init`, from the variable its vendor documents that agent sets in its own shell, such as Claude Code's `CLAUDECODE`, so that agent gets its ask rules. Because that writes the agent's files for every teammate, init says so in one `note` line, in the dry run too: the agent, the variable, the file, and how to leave it out. Name the agents you want with `--harness`, or give `--harness none`, and init wires no other. A variable no vendor page documents marks a shell an agent started and names no agent. A `hint` line names other agents it finds on your machine and wires none of them, and once init has written an agent's files, every teammate's run finds the same agents. `--harness <key>` names an agent the repository does not show yet, and `--harness none` turns detection off. Every agent reads `AGENTS.md` and the skill.

When no agent init wires takes ask rules, nothing stops an agent at an ask by itself. So init prints the exact `aidd init --harness <key>` line that writes them, and `aidd doctor` warns until one agent has them.

Claude Code gets the `aidd` command from the `aidd-cli` plugin. Codex, OpenCode, Google Antigravity, and Grok Build document no plugin that puts a command on the agent's PATH, so there the agent runs the `aidd` you installed. [plugins/README.md](../plugins/README.md) says what each one's documentation offers.

<!-- aidd:gen harnesses -->
| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Claude Code | `.claude/`, `CLAUDE.md`, `.mcp.json` | links the skill into `.claude/skills/`, writes the ask risk rules as `permissions.ask` in `.claude/settings.json` and the `aidd` MCP server in `.mcp.json`; `--aidd-team` adds the roles, commands, packs, and practice skills as project agents and skills, and sets `worktree.baseRef` to `head` in `.claude/settings.json` unless the file sets it, so each role's worktree starts from your current commit; a `CLAUDE.md` or `.claude/CLAUDE.md` gets one line that imports `AGENTS.md`, and a lone `CLAUDE.local.md` gets a `CLAUDE.md` with it (Claude Code reads `AGENTS.md` only when none of the three exists) | trust the folder, because until then it holds back the plugin marketplace, `permissions.allow`, and the `aidd` MCP server in `.mcp.json`, which it asks about before it connects (a `claude -p` run connects it without asking). To trust it, start `claude` in the repository and accept its trust dialog (or use the plugins instead: see the note below the table) |
| Codex | `.codex/`, `AGENTS.override.md` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the ask risk rules in `.codex/rules/aidd.rules` and the `aidd` MCP server in `.codex/config.toml` (outside Windows), keeping everything else; `--aidd-team` adds the roles as `.codex/agents/aidd-<role>.toml` and the team commands as skills in `.agents/skills/aidd-<flow>/`, which you run as `$aidd-<flow>` | trust the folder, because until then it holds back everything in `.codex/`, its ask rules in `.codex/rules/` and the `aidd` MCP server in `.codex/config.toml` too. To trust it, start `codex` in the repository and choose "Trust and continue" |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.github/hooks/` | `AGENTS.md` for the cloud agent, the CLI, and VS Code; in VS Code, the pointer is also appended to `.github/copilot-instructions.md` when that file exists; the ask risk rules as `chat.tools.terminal.autoApprove` entries set to `false` in `.vscode/settings.json`, which VS Code's agent asks on; `--aidd-team` adds the roles as `.github/agents/aidd-<role>.agent.md` | trust the folder, because until then it holds back its agent, which does not run in Restricted Mode. To trust it, trust the authors when VS Code asks, or run `Workspaces: Manage Workspace Trust` from the Command Palette |
| Grok Build | `.grok/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; the ask risk rules as `[permission] ask` in `.grok/config.toml`; `--aidd-team` adds the roles as `.grok/agents/aidd-<role>.md` and the team commands as skills in `.grok/skills/aidd-<flow>/` | trust the folder, because until then it holds back its ask rules in `.grok/config.toml`, the project's instructions and skills, its MCP servers, and its hooks. To trust it, start `grok` in the repository and type `/hooks-trust` (aidd's MCP tools are optional: add `aidd mcp` as a server for them) |
| OpenCode v2 | `opencode.json`, `opencode.jsonc`, `.opencode/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the ask risk rules in the `permissions` list of `opencode.json`, which needs OpenCode v2 or later; `--aidd-team` adds the roles as `.opencode/agents/aidd-<role>.md` and the team commands as `.opencode/commands/aidd-<flow>.md` | nothing (aidd's MCP tools are optional: add an `aidd` server that runs `aidd mcp` in `opencode.json`'s `mcp` section, as OpenCode's MCP servers docs show) |
| Qwen Code | `QWEN.md`, `.qwen/` | `AGENTS.md`, read next to `QWEN.md`; the ask risk rules as `permissions.ask` `Bash(...)` entries in `.qwen/settings.json` | trust the folder (only when folder trust is on, which is off by default), because until then it holds back all of `.qwen/settings.json`, its ask rules too, and asks before every tool instead. To trust it, choose "Trust folder" when Qwen Code asks |

For Claude Code, we recommend the plugins over repository files: `aidd init --claude-plugins --aidd-team`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd` and `/plugin install aidd-team@aidd`. Add `/plugin install aidd-cli@aidd` when no CLI is installed: it puts the `aidd` command on the agent's `PATH`. Add `/plugin install aidd-packs@aidd` in a project that calls for a domain pack, such as health or payments, because a role loads each pack by name. The plugin's descriptions share Claude Code's skill listing budget, so it is not on by default. The command (`aidd-cli`), the development team (`aidd-team`), and the packs (`aidd-packs`) are optional, and every part works without them. With the aidd plugin enabled in your own Claude Code settings, `aidd init` enables it in the project's `.claude/settings.json` (`enabledPlugins` and `extraKnownMarketplaces`) instead of copying the MCP server and the skill link into the repository, so nothing loads twice. The ask rules go into the project's settings either way.

Run `aidd init` again to add an agent, such as `aidd init --harness opencode`: it reads the profile from the config it keeps, keeps every file that exists, and writes only what is new.

**Every other agent** reads `AGENTS.md` and the vendored skill, which tells it when to ask. Its own settings decide what it may run without a prompt. `aidd init` wires each of these 8 agents when it finds it.

<details><summary>What <code>aidd init</code> does for each of the other 8 agents</summary>

| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Cursor | `.cursor/`, `.cursorrules` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Google Antigravity | `.agents/rules/`, `.agents/workflows/`, `.agents/hooks.json`, `.agents/plugins/aidd/`, `.agents/mcp_config.json`, `.agent/rules/` | `AGENTS.md` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves; `--aidd-team` adds the roles as `.agents/agents/aidd-<role>.md`, the team commands as skills (`/aidd-<flow>`) in `.agents/skills/aidd-<flow>/`, and `.agents/skills.json`, which names the domain packs in `.claude/skills/` | nothing |
| Kiro | `.kiro/` | `AGENTS.md`, read alongside `.kiro/steering/`; `--aidd-team` adds the roles as `.kiro/agents/aidd-<role>.json` | nothing |
| JetBrains Junie | `.junie/` | `AGENTS.md` | nothing |
| TraeCode | `.trae/` | `AGENTS.md` | nothing |
| DeepSeek Harness | `.dsh/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Muse Code | `.muse/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Mistral Vibe | `.vibe/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Anything else | | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

</details>
<!-- aidd:end -->

**OpenCode v2.** aidd writes OpenCode's ask rules in the `permissions` list of OpenCode v2, which OpenCode v1 refuses, so aidd supports OpenCode v2 and later. `aidd doctor` names an installed v1. Its `opencode upgrade` can stay on v1, so install v2 in one of the ways OpenCode's README gives: `npm rm -g opencode-ai && npm i -g @opencode/cli@latest` with npm, `brew install opencode` with Homebrew, or `curl -fsSL https://opencode.ai/v2/install | bash`. In every project, `.agents/skills/` flow skills carry `metadata.opencode/autoinvoke: "false"` so OpenCode's model cannot start one by itself, and adding OpenCode later rewrites nothing.

**Harness ask rules.** Where a harness has ask rules of its own, `aidd init` and `aidd upgrade` write each `ask` rule's commands there:

<!-- aidd:gen harnesses:ask-rules -->
| Harness | File | What aidd writes | How it matches a command | Asks in | Does not hold under |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `.claude/settings.json` | `permissions.ask`: `Bash(git push --force*)`, `Read(**/.env)`, and `Edit(/tests/test_a.py)` | by glob, as written | every permission mode, `bypassPermissions` included | a settings file it cannot parse, which it skips with its ask rules (silently under `claude -p`) ([page](https://code.claude.com/docs/en/settings), read 2026-11-11) |
| Codex | `.codex/rules/aidd.rules` | `prefix_rule(pattern = ["git", "push", ["origin", "upstream"], "main"], decision = "prompt")` | by leading words, with no wildcard | the default approval policy | Unconfirmed: `--dangerously-bypass-approvals-and-sandbox` (`--yolo`), which its page describes as no sandbox and no approvals; whether a `prompt` rule still asks there is not documented ([page](https://learn.chatgpt.com/docs/agent-approvals-security), read 2026-11-11); `codex exec --ignore-rules`, which skips user and project rules ([page](https://learn.chatgpt.com/docs/non-interactive-mode), read 2026-11-11); Unconfirmed: a command that runs inside the sandbox: its rules page governs commands outside the sandbox, and does not say whether a `prompt` rule asks for the others ([page](https://learn.chatgpt.com/docs/agent-configuration/rules), read 2026-11-11) |
| VS Code's Copilot agent | `.vscode/settings.json` | in VS Code's agent, `chat.tools.terminal.autoApprove`: `{"/^git push --force.*$/": false}` | by regular expression, exactly | Manual permissions, the default level | the Allow all permission level, Autopilot, and the `chat.tools.global.autoApprove` setting ([page](https://code.visualstudio.com/docs/agents/run/security), read 2026-11-11); read-only or sandboxed commands in Copilot sessions, which the runtime approves before the rules run, and worktree sessions, which always use Allow all ([page](https://code.visualstudio.com/docs/agents/run/approvals), read 2026-11-11); the Copilot CLI and the cloud agent, which read no ask rules from the repository: the CLI's permissions file has no ask rules or repository-local policy ([page](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference), read 2026-11-11) |
| Grok Build | `.grok/config.toml` | `[permission] ask = ["Bash(git push --force*)", "Read(**/.env)", "Edit(**/tests/test_a.py)"]`, in a block aidd marks | by glob, as written | ask mode, the default | always-approve (`grok --always-approve`), where only `deny` rules and PreToolUse hooks still apply ([page](https://docs.x.ai/build/features/permissions), read 2026-11-11) |
| OpenCode v2 | `opencode.json` or `opencode.jsonc` | `permissions`: `{"action": "shell", "resource": "git push --force*", "effect": "ask"}` and `{"action": "edit", "resource": "*tests/test_a.py", "effect": "ask"}` | by glob, as written | an agent that sets no permissions of its own | an agent whose own `permissions` allow the command, because agent rules come last and the last match wins ([page](https://opencode.ai/docs/permissions/), read 2026-11-11); a config in `.opencode/`, which outranks the root `opencode.json` aidd writes ([page](https://opencode.ai/docs/config/), read 2026-11-11); Unconfirmed: `opencode.json` and `opencode.jsonc` in one folder: its docs do not say which wins ([page](https://opencode.ai/docs/config/), read 2026-11-11) |
| Qwen Code | `.qwen/settings.json` | `permissions.ask`: `Bash(git push --force)`, `Bash(git push --force *)`, and `Read(**/.env)` | by leading words, with no wildcard | the Ask Permissions mode, the default | Unconfirmed: YOLO mode, which approves all tool calls; its page does not say whether an ask rule still prompts there ([page](https://qwenlm.github.io/qwen-code-docs/en/users/features/approval-mode/), read 2026-11-11) |
<!-- aidd:end -->

aidd lists the entries it wrote, and the MCP tools it allowed, in `.aidd/harness-rules.json`, and changes only those, never your own, and it never puts an ask where it would undo your deny. The harnesses do not ask for the same commands. A harness shows its prompt only in the mode the table names. The last column lists each mode, setting, or surface where it shows none, with the page that says so and the date aidd read it. An entry marked unconfirmed is one the vendor's page leaves open. VS Code's agent reads `.vscode/settings.json`, and the Copilot CLI and the cloud agent read no ask rules from the repository. An agent that matches leading words asks more often for a few commands, and it holds none of the patterns that need a `*` inside a command. Where a harness matches a command's leading words, a `*` between words becomes the common remote names, `origin` and `upstream`. A pattern with a `*` inside a command asks at its leading words there, when a tool's own words number three or more. So `gh workflow run *release*` asks before every `gh workflow run`: more often, never less. A push through another remote, and the forms it cannot hold, are left to the skill, and the holds table below counts them. Codex and Grok Build read the rules only once you trust the folder. Any other harness gets the skill alone. `aidd doctor` names each case: the actions no rule of the agent holds, the actions it holds in part, and every mode where its rules do not hold. VS Code's settings file, Qwen Code's, and OpenCode's `opencode.jsonc` take comments, so aidd edits the file you keep in place, and your comments, key order, line endings, and other settings stay. It writes only a result that reads back as the same settings. Otherwise it leaves the file as it is and says what to add by hand. A file with a comment in a harness that reads strict JSON, such as Claude Code's, is left as it is. OpenCode's ask rules cover shell commands and the file edits of frozen tests, because aidd writes them for its `shell` and `edit` actions. Codex approves each aidd MCP tool by name, so those tools run with no prompt there. Set `mcp: {allow_own_tools: false}` to keep them asking. A pattern is a net, not a control: a command can reach the same effect another way. So on a shared repository, branch protection is the hard stop ([Teams and CI](#teams-and-ci)).

**Listings and previews in the harness rules.** A harness's ask rule matches a command's leading words, so your harness asks before `git tag -l` as it does before `git tag v1`. `aidd risk --command` reads a few forms that provably write nothing as `allow` and says so in a note: a tag listing, `kubectl apply --dry-run=client`, `kubectl delete --dry-run=client`, `aws s3 rm ... --dryrun`, and `-h` or `--help` where the tool documents it. Your harness still asks for them, because aidd does not change its rules here. A preview that runs the project's code, such as `git push --dry-run` or `npm publish --dry-run`, is not one of them, so it asks.

**Frozen tests in the harness rules.** After Spec approval, a Spec's tests change only by `spec.revise`. `aidd upgrade --yes` also writes an `Edit` ask rule for each test file of every Spec that is approved, in progress, or in review. After a Spec approval, `aidd upgrade --only ask-rules --yes` writes only the ask rules and changes no other file. Claude Code, Grok Build, and OpenCode have a file-edit rule, so each asks before its own edit tool changes one. OpenCode gets them only when `opencode.json` holds no edit rule of yours, because it applies the last rule that matches; `aidd doctor` says when it writes none. The rules come from the Spec files. They leave at the next upgrade once the Spec is done, rolled back, cancelled, or back to a draft, and `aidd doctor` says when they lag. Codex, Qwen Code, and VS Code's agent have no such rule. A shell write such as `sed -i` is no edit tool, so the rule may miss it, and `aidd validate` and `aidd test` do not compare a test with its approved form. Your review of the pull request catches it, and so does `aidd delegate check` for a delegated merge. [SECURITY.md](../SECURITY.md) lists the limits.

**`gh api` in the harness rules.** Claude Code, OpenCode, Grok Build, and VS Code ask before any `gh api` call that may write: an explicit method (`-X`, `--method`), a field or an input, or GraphQL. They cannot tell a read from a write, so they also ask for an explicit `-X GET`, a GET with a field, and a GraphQL query, which `aidd risk --command` allows and says so in a note. A call such as `PATCH releases/assets/3 --input` asks the same way. Codex and Qwen Code match leading words, so they ask only when the method, the field, the input, or `graphql` comes first, as in `gh api -X DELETE repos/o/r/git/refs/heads/old`, and the skill asks for the rest. The harnesses match the text of a command typed by its plain name, while `aidd risk --command` reads it exactly, a path such as `./bin/gh` and a wrapper such as `sudo` included. So a harness misses a path-qualified `gh`, a run of short flags that hides `-f` in its middle, and anything the shell builds, such as an alias, and the skill and branch protection hold the rest.

**The team in each harness.** In Claude Code each team command runs as `/aidd-team:<flow>`, such as `/aidd-team:specify`. In OpenCode, Grok Build, and Google Antigravity, `aidd init --aidd-team` writes them as `/aidd-<flow>`. In Codex, run them as `$aidd-<flow>`. Every other agent that loads skills from `.agents/skills/`, such as GitHub Copilot, Cursor, or JetBrains Junie, gets the same flows there as `aidd-<flow>` skills. Its lead starts each role from `.agents/roles/aidd-<role>.md`. In an agent that reads no skills, ask it to act as one role per session. [TEAM.md](TEAM.md) has the details.

**The MCP server.** `aidd mcp` serves eight tools: `risk`, `status`, `validate`, `recall`, and `record` for everyday use, and `delegate_check`, `delegate_packet`, and `delegate_answer` for a delegation. `record` writes one record of history, as `aidd records add` does. It also writes where a sandbox keeps `.git` read-only, as Codex's `workspace-write` does. `aidd init` lets the five everyday tools run with no prompt: Codex's `.codex/config.toml` approves each by name, and Claude Code's `.claude/settings.json` lists each in `permissions.allow`, which Claude Code reads once you trust the folder. `risk`, `status`, `validate`, and `recall` only read, `recall` refreshing its cache in `.git/aidd/index.sqlite`, and `record` writes only `.git/aidd/records/`. To keep them asking, set `mcp: {allow_own_tools: false}` in `.aidd/config.yaml` and run `aidd upgrade --yes`: it takes out the approvals aidd wrote and leaves your own entries. The Claude Code plugin starts it for you, under its own tool names. Otherwise `.mcp.json` starts it through the launcher `~/.aidd/bin/aidd`. Only an installed aidd writes it. `aidd init` from a source checkout keeps it as it is and says so. `aidd doctor` warns when it starts a source checkout or a path that is gone. Once the plugin serves aidd and `.mcp.json` names no `aidd` server, `aidd init` and `aidd upgrade` take out the server's names that aidd wrote, because they approve tools no server has. In OpenCode, add an `aidd` server that runs `aidd mcp` in `opencode.json`'s `mcp` section, as OpenCode's MCP servers docs show.

### What holds each ask

aidd advises, so three layers hold an `ask`, and each catches what the one before it misses. The skill holds every row, in every harness: the agent asks before the action. A harness's own ask rules, where `aidd init` wrote them, show the harness's prompt before a command the rule names, even when the agent forgets. They hold in the harness's default permission mode, and several skip them in an allow-all mode, as the table above says. Your platform's branch protection refuses a few steps outright, once you set it as [Teams and CI](#teams-and-ci) says. The table shows the built-in rules, by default. A row with "nothing" in a column has only the layers beside it.

<!-- aidd:gen risks:holds -->
| Action | Asks | A harness's own ask rules | Branch protection |
| --- | --- | --- | --- |
| `code.edit` | in `auth`, `payments`, `personal_data`, `secrets`, `migrations`, and `risk_rules` | nothing: no command marks it | — |
| `git.push` | to the default or a shared branch | asks before a push to the default branch, such as `git push * main` and `git push * main *`, and more; Codex and Qwen Code hold 1 of its 26 forms in full and 25 more by a narrower rule; no harness rule holds a push that names no branch, such as `git push` or `git push origin HEAD`, while the default branch is checked out, so the skill asks first | refused on the default branch, which takes only a PR/MR |
| `git.push.force` | always | asks before `git push --force*` and `git push -f*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 2 of its 19 forms in full and 16 more by a narrower rule | refused on the default branch |
| `git.history.rewrite` | always | asks before `git reset --hard*` and `git filter-branch*`, and more | the force push that would publish it is refused on the default branch |
| `git.branch.delete` | always | asks before `git branch -d*` and `git branch -D*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Claude Code and Grok Build hold 19 of its 20 forms in full; Codex and Qwen Code hold 2 of its 20 forms in full and 17 more by a narrower rule | deleting the default branch on the platform is refused |
| `git.tag.create` | always | asks before `git tag*` | — |
| `git.merge` | on any branch but your own | nothing: a harness rule cannot see the branch checked out | the push that would publish it is refused on the default branch, which takes only a PR/MR |
| `pr.merge` | always | asks before `gh pr merge*` and `glab mr merge*`; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 2 of its 14 forms in full and 12 more by a narrower rule | under `team`, the PR/MR review decides |
| `commit_status.post` | always | Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 0 of its 12 forms in full and 12 more by a narrower rule | the `tests` check counts only from GitHub Actions (`integration_id`) |
| `branch_protection.change` | always | Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 0 of its 12 forms in full and 12 more by a narrower rule | — |
| `repo.settings.change` | always | asks before `gh repo edit*` and `gh repo archive*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 4 of its 16 forms in full and 12 more by a narrower rule | — |
| `product_scope.approve` | always | asks before `git commit *Approves*` and `git * commit *Approves*`, and more; Codex and Qwen Code hold 8 of its 12 forms in full | — |
| `intent.approve` | always | asks before `git commit *Approves*` and `git * commit *Approves*`, and more; Codex and Qwen Code match leading words only, and Claude Code's pattern misses a message written as a heredoc, so the skill asks, and `aidd status` counts an approval only with its `Approved-by` and `Approves` lines | — |
| `result.approve` | always | asks before `git commit *Approves*` and `git * commit *Approves*`, and more; Codex and Qwen Code hold 8 of its 12 forms in full | — |
| `intent.cancel` | always | asks before `git commit *Cancels*` and `git * commit *Cancels*`, and more; Codex and Qwen Code hold 8 of its 12 forms in full | — |
| `spec.approve` | always | asks before `git commit *Approves*` and `git * commit *Approves*`, and more; Codex and Qwen Code hold 8 of its 12 forms in full | — |
| `spec.revise` | always | nothing: no command marks it | — |
| `spec.cancel` | always | asks before `git commit *Cancels*` and `git * commit *Cancels*`, and more; Codex and Qwen Code hold 8 of its 12 forms in full | — |
| `postmortem.publish` | always | nothing: no command marks it | — |
| `deploy.run` | to any environment but your own | asks before `kubectl apply*` and `helm upgrade*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 17 of its 29 forms in full and 12 more by a narrower rule | — |
| `records.push` | always | asks before `aidd records push*` and `*aidd* records push*`, and more; Codex and Qwen Code hold 8 of its 11 forms in full | — |
| `release.publish` | always | asks before `npm publish*` and `pnpm publish*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 19 of its 39 forms in full and 18 more by a narrower rule | — |
| `migration.run` | always | asks before `php artisan migrate --force*` and `php artisan migrate*--force*`, and more; Codex and Qwen Code hold 18 of its 53 forms in full | — |
| `migration.rollback` | always | asks before `php artisan migrate:refresh*` and `php artisan migrate:reset*`, and more; Codex and Qwen Code hold 10 of its 60 forms in full and 30 more by a narrower rule | — |
| `infra.apply` | always | asks before `terraform apply*` and `terraform destroy*`, and more | — |
| `data.delete` | always | asks before `rm -rf*` and `rm -fr*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 39 of its 131 forms in full and 69 more by a narrower rule | — |
| `data.production.access` | always | nothing: no command marks it | — |
| `secret.use` | always | Claude Code, Grok Build, and Qwen Code ask before their own file-read tool reads a file that holds secrets, such as `Read(**/.env)` | — |
| `message.send` | always | asks before `gh issue comment*` and `gh pr comment*`, and more; Claude Code, VS Code's Copilot agent, OpenCode v2, and Grok Build ask before any `gh api` write, such as `gh api* -X*` and `gh api* -f*`; Codex and Qwen Code hold 3 of its 15 forms in full and 12 more by a narrower rule | — |
| `money.spend` | always | nothing: no command marks it | — |
<!-- aidd:end -->

An agent with no ask rules of its own, the rest of [the harness table](#every-coding-agent), has the skill and the platform only. `aidd doctor` names each one.


**The product's living documents.** `aidd new product-brief`, `metrics-dictionary`, `service-card <name>`, `control-register`, and `improvement-log` each start one file. A Spec's tracking plan, SLO doc, or compliance record folds into its file. `aidd validate` warns when a tracking plan's events are not in the metrics dictionary, or an SLO doc's targets are not on a service card. It does not check the compliance record's fold. `aidd new srs <INTENT-ID>` generates the requirements specification from the approved Specs.

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

**The tests in CI.** `aidd init --ci github` writes `.github/workflows/aidd-tests.yml`. On each pull request, it runs `aidd test` with no secrets, green on the head and red on the base for new behavior, and keeps the evidence. `--ci gitlab` writes the same job as an include for `.gitlab-ci.yml`. `--ci none` writes neither. The job fails when no test command ran, because a green check must mean the tests passed. It then runs `aidd validate`, prints each warning as an annotation, and fails on an error in a Spec or the config, so a Spec error shows on the pull request. It decides nothing about a merge.

**Claude Code Review.** It reads `REVIEW.md` from your protected default branch, never from the PR, and posts 🔴 Important and 🟡 Nit findings with a check run that never fails. `aidd init` writes a `REVIEW.md` that maps Important to aidd's Critical and High, caps nits at five, and lists what not to report. With `--aidd-team` and no plugin, it also includes the code-review skill, so protect the branch, or the include is plain text. Code Review is one more reviewer, never the decision: a person approves.

**Branch protection is the hard stop.** aidd advises, so protect the default branch with your platform's own rules:

1. Require a pull or merge request before merging. Under `team`, require at least one approving review, which the ruleset `aidd init` writes does. Under `solo` nobody else reviews, so the ruleset requires none, and nothing but you stands between the agent's ask and the merge.
2. Require the `tests` check, from the `aidd-tests` workflow, to pass. The ruleset aidd writes takes it only from GitHub Actions (`integration_id` 15368 on github.com), so a status anyone posts by hand never counts. On GitHub Enterprise Server, check the id with `gh api /apps/github-actions --hostname <host> --jq .id`, and set it in `.github/rulesets/main.json` if it differs. The check holds a change to the tests of the commit its branch forked from, and the author chooses that commit. So the ruleset aidd writes also turns on "Require branches to be up to date before merging", which holds a change to the tests the default branch added since. A branch that fell behind is updated from the default branch before it merges. Where many changes merge at once, use a merge queue instead ([GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), read 2026-11-11). On GitLab, use the fast-forward merge method, which needs a rebased branch ([GitLab](https://docs.gitlab.com/ee/user/project/merge_requests/methods/), read 2026-11-11). Without it, `aidd test` tells you when the default branch changed what decides a run since your branch forked. A delegated merge defers on a head that does not hold the default branch's tip.
3. Block force-pushes and deletion of the default branch.
4. Where your plan allows it, require review from code owners for the paths in your areas.

On GitHub these are a branch ruleset; on GitLab, protected branches and merge request approvals.

**A monorepo.** Give each package a `tests` entry with `when_changed`, so a change runs only the suites it touches, and `runs_in`, so the command runs in the package's folder. `when_changed` globs and a `report` path stay relative to the repository's top, whatever the folder. A folder outside the repository, or one reached through a link, is refused. Add an area for each sensitive package.

```yaml
tests:
  - name: api
    command: [pytest, -q]
    runs_in: packages/api
    when_changed: ["packages/api/**"]
  - name: web
    command: [npm, test]
    runs_in: packages/web
    when_changed: ["packages/web/**"]
```

**A quick check that runs only the related tests.** In a project with one test command, `aidd test --changed` runs that whole command between steps. Many runners can run only the tests that cover the files you changed, such as Jest's `--findRelatedTests` and `vitest related`. Give the command a `related_tests` form, and `--changed` runs it instead:

```yaml
tests:
  - name: unit
    command: [npx, vitest, run]
    related_tests:
      command: [npx, vitest, related, --run, --passWithNoTests, "{changed_paths}"]
      sees: ["src/**/*.ts", "src/**/*.tsx"]
```

`{changed_paths}` becomes each changed path, from the folder the command runs in, and `{base_commit}` becomes the commit your branch left the base at. `sees` lists the files the runner traces to their tests. A change to anything else, such as a lock file, the config, a fixture, or a deleted file, runs the full command, and a note says why. The result reads "only its related tests", and the evidence stays `partial`. A full `aidd test`, `--require-green`, CI, the verifier's run, and the delegate's check always run the full command, so the one full run on the final head stays the proof. When a command's runner has a related-tests mode, `aidd test --changed` and `aidd doctor` suggest the form; [`schemas/test-runners.json`](../schemas/test-runners.json) records each runner's mode with its source.

**Several repositories.** Run `aidd init` in each. Keep Proposals and Intents in one home repository, and each Spec in the repository it changes. A slice names its `repo`, and the Specs of one piece of work share a `trace_id`. A client engagement uses two by default, the firm's home repository and the client's, and may use one. The `aidd-team:client-delivery` skill says what each holds, and the handover checks what the client receives.

**A new or an existing repository.** In a new one, commit the aidd setup and the project scaffold to the default branch as Day 0, and let the first Spec bring the test runner. In an existing one, put the existing suite in `tests`. Add areas for the real layout, and write a characterization test before you change untested code. `/aidd-team:onboard` maps an existing codebase and suggests three small first changes.

**Coming from Spec Kit, OpenSpec, Kiro, or BMAD.** Keep the tool you like for planning. Ask your agent to write the aidd Spec from the plan. It quotes the problem in `## Request`, gives each requirement an id, takes each Task's scope from the paths the plan names, and links the plan instead of copying it. BMAD brings its own roles, so use either its roles or aidd-team's, never both. An AI-native playbook's `intent.md` maps to two things in aidd: the request, the person's own words, and the Intent the team writes from it.

## Orca and parallel agents

[Orca](https://github.com/stablyai/orca) runs coding agents side by side, each in its own git worktree. aidd works there with no extra setup, and nothing in aidd needs Orca.

- **Worktrees are git worktrees.** `aidd status`, `aidd risk`, and `aidd test` work in each one. Each worktree keeps its own files and its own `.aidd/evidence/`. Never share `.aidd/evidence/` between worktrees, because evidence belongs to one head.
- **See the work on one page.** `aidd status --html` writes `.aidd/views/status-work.html`. Needs you lists what waits for a person, each with the words to copy and paste to your agent. The Board shows the open Specs by stage, and a row per team if the config names teams. A merged Spec moves to Done. A card that waits for your decision names its gate, such as Spec approval. The Tree shows each Intent and its phases with what is finished. Press `/` to search, J and K to move, Enter to open an item, and `?` for every key. The address keeps the view and filters, so you can share what you see. Add `--development-team <name>` for one team's file, or `--all-branches` for every worktree and branch. The page only reads, so a decision stays in the chat.
- **Pick up where a session left off.** `aidd status <ID>` shows a work item's history, newest first: its decisions and reports from the records, the commits that name it, and its linked documents. It is history, never a yes.
- **See the work in every worktree.** `aidd status --all-branches` shows the open work in every worktree, and in every local and fetched branch, with the places that hold each item. The worktrees also share one history of records, which `aidd records` lists. To share it with your team, say "push the records": the agent asks, then runs `aidd records push`, and a teammate's `aidd records pull` adds them.
- **One agent per Task.** Once a Spec is approved, start one agent for each Task whose `blocked_by` Tasks are done, each in a worktree branched from the Spec's branch. Tasks whose scopes overlap depend on one another, so parallel Tasks never change the same files. Merge each Task's branch back when its tests pass.
- **One branch for an Intent's Specs.** `incremental` stays the default: small batches reach `main` by themselves, so review keeps up (the DORA trunk-based practice). Under `reaches: batched`, your agent cuts `intent/<ID>` from the default branch, and each Spec's `spec/<ID>` from it. It runs two or three Specs with disjoint scopes at a time, each in its own worktree. Each merges into `intent/<ID>` once its tests, verifier, and review pass, with no Merge approval, and `aidd status` says which Specs are done there and which wait, and that the Intent's one Merge approval is pending. A Spec merged there is `done`, yet nothing is shipped until the branch lands on `main`. The trade-off: it saves merges to `main`, but its one Merge approval is one large review, so keep a batch to what you can review in one sitting. To see the batch run before then, set `aidd init --own-environment dev=intent/<ID>`. It marks the environment `shared: false`, so a deploy from the Intent branch is yours, and your agent reports it, even under a delegation.
- **Best of two or three.** For a hard Task, give the same Task to two or three agents, each in its own worktree. Drop each attempt whose `aidd test` fails, keep the smallest diff, and delete the others.
- **Set up a worktree.** Orca reads an optional `orca.yaml`. Its `setup` script can run `aidd doctor`, and a `defaultTabs` entry can open `aidd status`.
- **Parallel Tasks in Claude Code.** Tasks that run at once each build in their own worktree. `aidd init --aidd-team` and `aidd upgrade` set `worktree.baseRef` to `head` in `.claude/settings.json`, so each starts from your Spec branch. A value you set there stays, and `aidd doctor` notes when no settings file sets it. List the ignored files to copy in `.worktreeinclude`. Orca makes its own worktrees, so there the lead names the base commit and the setup command in each worker's prompt.
- **Autopilot can start Orca workers.** Where Orca is installed, `/aidd-team:autopilot` may start a step in an Orca worker, each in a new worktree. It reads each result from git only, merges finished Task branches one at a time with `aidd test`, and stops to ask once a run spends more than `agents.max_tokens_per_run`. Each worker's handoff note gives its Spend line.
- **Several development teams.** List each team under `development_teams` in the config, name it in the `development_team` of its Intents, slices, and Specs, with its approvers, its areas, its harness, its models, and its effort. Then `aidd status --development-team <name>` and `/aidd-team:autopilot team:<name>` keep to that team's work, so each team's run keeps to its own work. Give the teams areas and work that don't overlap, because aidd doesn't check that ([CONFIG.md](CONFIG.md#development_teams)).
- **Workers write to their lead through a checked payload.** A worker sends a question, a blocker, or its done message with a JSON payload, and the lead acts only when `aidd validate <name>.orca.json` passes it. aidd-team's `references/orca-channel.md` says how.
- **worktrunk works the same way.** [worktrunk](https://github.com/max-sixty/worktrunk)'s `wt switch -c <branch>` makes a worktree for a branch, and a `post-start` hook in its `.config/wt.toml` can run `aidd doctor` there. worktrunk asks before a project hook runs for the first time, and again when the hook's command changes.

Be careful with two things:

- **Permission bypass skips the harness's ask rules.** Orca can start an agent with its permission-bypass flag, such as Claude Code's `--dangerously-skip-permissions`. Then the harness asks nothing, and only the skill's asks and your branch protection hold. Switch to manual permissions when that matters.
- **Orca's own signals are not your yes.** Orca's decision gates, worker status, and card are useful for coordination. None of them is a yes from you. `orca.yaml`, `.worktreeinclude`, and worktrunk's `.config/wt.toml` run commands and copy files for every worktree, so they are in the `agent_config` area, and the agent reports each edit.

## Troubleshooting

### The agent did a risky step without asking

1. Run `aidd risk --command "<the command>"` to see the level aidd computes. If it is `allow` or `report`, raise it ([Customize the risk rules](#customize-the-risk-rules)).
2. Run `aidd doctor`. It says whether your harness has the ask rules, and whether they are current. If not, run `aidd upgrade --yes`. It also says whether your harness holds them back until you trust the folder.
3. Check that the agent loaded the skill: `AGENTS.md` points at it, and the agent can name the `aidd` skill when you ask.
4. Protect the default branch, which no agent can skip ([Teams and CI](#teams-and-ci)).

### The agent asks too often

Lower the rule in your config, such as `pr.open` to `allow`. For one session only, say so in the chat ("don't ask about pushes today"). `aidd risk --list` shows which rule fires and where it comes from.

### `aidd risk` says my rule is ignored

An `extends` parent marks that rule `locked: true`, a floor, so its level stays. Ask whoever owns the preset to change it there.

### `aidd doctor` says a harness has no ask rules

That harness has no ask rules aidd can write, so it follows the skill alone. Use a harness from the table above for risky work, or rely on branch protection.

### `aidd doctor` says a harness waits for folder trust

Some harnesses read a project's own rules only once you trust its folder, so until then their ask rules do not hold. Codex, Grok Build, and Qwen Code with folder trust on are such harnesses. The trust lives in your own files outside the repository, which aidd never reads, so `aidd doctor` cannot see it. Its line says how to check and gives the words to type to trust the folder. Claude Code's ask rules hold either way, and only its `.mcp.json` server, its plugin marketplace, and its `allow` rules wait.

### `aidd validate` refuses a config key

The format has no such key, so it may be a typo. Fix or delete it. [CONFIG.md](CONFIG.md) lists every key this aidd reads.

### `aidd test` says a new test already passes on the base

A new-behavior test must fail on the base commit, or it proves nothing about the change. Check that the test exercises the new behavior, not something that already worked. If the change is a refactor with no new behavior, drop `new_behavior: true` from that command.

### `aidd test` says nothing ran

A full run that ran no command exits 1 where one is needed. Either the config has no `tests` and no Spec for the change declares any, or a Spec that applies has every command limited by `when_changed` to other paths. Ask the person who owns the config to add a command under `tests:`, such as the project's suite. A Spec's `tests.commands` count too. A `--changed` run that selects nothing is a quick check, so it exits 0 and reads `partial`.

### `aidd test` says no test applied

The config has test commands, and every one is limited by `when_changed` to paths your change does not touch, such as a docs-only change. The project's own config says no test covers those paths, so the run exits 0, says it proved nothing, and `aidd status` reads it as no test applied, never passed. A delegated merge of such a change carries the same note, and it defers to a person only when the change's paths are above `minor`. To have a check on every change, add one command with no `when_changed`, such as a lint.

### The check is red on a pull request that holds only a Spec

The check is red because the Spec's new tests fail until Implement builds the code, and the CI run (`aidd test --require-green`) excuses nothing, so a green check means every test that applies passed. Your local `aidd test` marks those tests `..` and exits 0 to tell you they fail as expected. Nothing is wrong. Ask for Spec approval on the pull request as usual, then build: the check turns green when Implement makes the tests pass. To merge the Spec on its own first, a person decides on the red check.

### `aidd test` says a Spec's tests did not run

Your change touches the Task scope of an approved or in-progress Spec but does not hold it, so aidd did not run that Spec's tests, and the verdict is the suite's. If the change is that Spec's work, work on a branch named `spec/<ID>` or pass `--spec <ID>`, so its tests run and count. If it is not, there is nothing to do. A delegated merge of such a change defers to a person.

### `aidd test` ran a command named `base.<name>`

The change removed or changed a command under `tests:` in `.aidd/config.yaml`. A change cannot pass by weakening the tests that check it, so aidd also ran the base commit's version, and it must still pass on your head. If it fails, split the change: keep the old command and its test file working in this one, and remove them in a later change. The next entry gives the steps.

### `aidd test` is red after you revised an approved Spec's tests

An approved Spec's test commands are frozen, so changing one is `spec.revise`: the person who agreed to it approves the Spec again. The note says the head changed an approved Spec and ran the base's commands as `base.<name>`. Each must still pass on your head, because otherwise a change could pass by rewriting the tests that check it. aidd cannot see a person's yes, so the head has no switch to turn a base command off.

Whether the check is green depends on the shape of the revision, and no shape needs a bypass of a required check:

1. **A new expectation in the test file, the command unchanged, the code changed to pass it.** One change, green.
2. **A command added, nothing else changed.** One change, green.
3. **A command renamed, or its file renamed.** The old file is gone on your head, so the base's copy fails. Do it in three changes. Add the new command and its file beside the old ones. Drop the old command and leave its file. Then delete the old file. Each is green.
4. **A command removed because the behavior is retired.** The old test would fail once the code goes. Do it in two changes. Drop the command and leave the code and the test file, so the base's copy still passes. Then delete the code and the file, which no command runs.
5. **The Spec and a failing test, with no code, as a change of its own.** It stays red, because the new test fails until the code exists. Put the Spec, its tests, and the code in one change instead.

If a Spec is still `draft` in the head, re-approval is pending: the check can be green, and a delegated merge defers until a person approves it.

### `aidd test` says the default branch moved since your branch forked

The note names what the default branch changed in `tests`, `specs_dir`, `docs_dir`, or a Spec this run answers to. The run used the fork point's values, so it did not hold your branch to them, and it does not fail your branch for a test your branch cannot pass yet. Update your branch from the default branch, then run `aidd test` again. A delegated merge defers on a head that does not hold the default branch's tip. To make the platform hold every branch to the newest tests, turn on "Require branches to be up to date before merging", or use a merge queue.

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

On four `ask` steps, yes, if you set a standing delegation: [Let the delegate decide for you](#let-the-delegate-decide-for-you). Every other `ask` waits for your yes in the chat. For the rest, you choose the level. Lower a rule to `report` or `allow` in your config, or for one session in your own words.

### Does aidd enforce anything?

No. aidd advises: it computes the route and the level, and the agent acts on them. The hard stops are your harness's ask rules, which `aidd init` writes, and your platform's branch protection. A command pattern can miss a command that does the same thing, so protect the default branch.

### Can the agent just edit the test until it passes?

After Spec approval, an edit of the Spec's acceptance tests is `spec.revise`, an `ask`. The skill tells the agent to ask, and Claude Code, Grok Build, and OpenCode also ask before their edit tool changes one. The agent writes its own unit tests with the code, and the skill tells it never to edit a frozen test. On your yes, the Spec goes back to `draft` and asks for approval again. Red before green also proves that each new test failed before the code existed, and the reviewer reads every test change. The reviewer treats a weakened check as a finding, because the fix goes in the code, never the test. A weakened check is a new skip or suppression, a deleted test or assertion, or a lowered coverage floor.

### What if we have no tests?

Write one characterization test first, a command that pins today's behavior. The suite then grows with every change, as each Spec adds its tests. Until a command runs, `aidd test` exits 1 and says nothing was proven.

### What about Dependabot and Renovate?

An update bot's change edits files in the `dependencies` area, so it is a normal change, and an agent reports each edit there. On a platform, its PR goes through your review like any other. Raise the area to `ask` if you want an agent to ask before it touches a manifest.

### Can we keep Spec Kit, OpenSpec, Kiro, Jira, or Linear?

Yes. Keep a planning tool, and have your agent write the aidd Spec from its plan. Keep a tracker, and mirror each Spec by its status group: backlog, unstarted, started, completed, and cancelled. The Spec file in the repository stays the source.

### Which coding agents does it work with?

Any agent that reads `AGENTS.md` or an Agent Skills folder, and `aidd init` wires the <!-- aidd:gen count:harnesses -->14<!-- aidd:end --> it supports. The agents in the harness ask rules table, under [Every coding agent](#every-coding-agent), also get their own ask rules.

### Does it lock us into Claude, GitHub, or Python?

No. The skill is a plain Agent Skills folder, and `AGENTS.md` reaches every other agent. aidd needs git and a repository, and GitHub and GitLab are optional. Python runs the CLI only.

### Does aidd send anything over the network?

No telemetry, and aidd's advice calls no model. It connects only for a command you run, such as `aidd self-update`. [SECURITY.md](../SECURITY.md) lists every place it connects, and `AIDD_OFFLINE=1` stops the optional ones.

### How does an agent know the best practice for a task?

From a registry, not from memory. Each role applies the dated standards of its discipline. A domain pack adds the standards and checks of each domain a change touches, and a practice skill says how to do one kind of work. [TEAM.md](TEAM.md) explains the three layers, and [STANDARDS.md](STANDARDS.md) lists the library of default tools.

### Where does each kind of memory live?

How you like to work stays in your harness's memory. An agent's memory across runs is the handoff note and the records (`aidd records`). The team's memory is the repository's files: the ADRs, the glossary, the product brief, the improvement log, and the shared `refs/aidd/records`. Put a project fact in the file that owns it, because another harness, a teammate, or the next role never sees one harness's memory. That memory may also be stale, so check it against the files. An agent adds a lesson to a team file only when you confirm it.

To find what the team already wrote, run `aidd recall <words>`, or let the agent call the MCP `recall` tool. It searches the records, the Specs, the ADRs, the glossary, the product brief, the improvement log, and the commit subjects. Each match names its file and line, so you can read the file. The search reads a cache of the files with no model and no network. So a match is never a source of truth, never evidence, and never a yes.

### What does it cost?

aidd itself is one Python process with no dependencies, so it costs seconds. The team costs tokens, and spends them where mistakes cost the most. <!-- aidd:gen list:reasoning-roles -->Seven roles use the strongest model your harness offers (the `reasoning` tier): the product manager, the architect, the product designer, the security engineer, the compliance analyst, the reviewer, and the delegate<!-- aidd:end -->. Every other role runs on a mid-size model, because a person, tests written before the code, or an approved eval checks its work. A small fix runs one developer with `/aidd-team:fix`.

### Why YAML, and which YAML?

GitHub renders YAML front matter as a table, and the Agent Skills format and most tools already use it. But YAML can read one value two ways, so aidd reads a strict subset with its own parser. Every value in the subset reads the same in every YAML reader, and aidd asks you to quote a value that could read as something else.

### Can our organization set the rules?

Yes. An org preset is a config each repository extends. A repository may change any rule the preset does not lock, and a rule marked `locked: true` is a floor your rules never lower ([Customize the risk rules](#customize-the-risk-rules)).

### How do I remove it?

Run `aidd uninstall` to list what `aidd init` wrote, then `aidd uninstall --yes` ([Remove](#remove)).
