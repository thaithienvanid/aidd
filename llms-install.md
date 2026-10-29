# Install aidd in a project: a runbook for coding agents

You are a coding agent. A person asked you to install aidd in the repository you are working in. aidd, at <https://github.com/thaithienvanid/aidd>, is the toolkit for AI-Driven Development, or AIDD, which runs one loop from intent to production with change control at its core. Follow these steps in order. Run the commands as written. Stop where a step says the decision is the person's. Report each step's outcome. Never improvise around a failure; report it instead.

## 0. Before you start

- Work at the repository root. Create the branch `chore/adopt-aidd` from the base branch, and work on it. In a new repository with no commit yet, there's no base branch, so stay where you are and see step 4.
- The person decides two things. Ask both in one message, unless they already said:
  - the setup, meaning a profile and whether there's a platform, as one of these three:
    - `solo` on GitHub or GitLab, for one person and their agents, which needs their own handle, such as `@login`
    - `team` on GitHub or GitLab, for several people, which needs Approver handles such as `@org/leads`
    - `solo`, local-first, for one person with no platform yet, which needs the email their git commits use, such as `email:you@example.com`

    The other two profiles, `org` and `audited`, are set up by hand from [docs/ADOPTION.md](https://github.com/thaithienvanid/aidd/blob/main/docs/ADOPTION.md).
  - what to install. Recommend everything, and offer it first. That's the delivery team with `--team`, and for Claude Code users the three plugins with `--claude-plugins --team --mods`, which `aidd init` installs for their user through the `claude` CLI. The team and the `aidd-mods` status pane are optional, and so are the plugins, because repository files work too.
- If they don't answer, default to `solo` on the platform the repository's remote points to, with their own handle and everything recommended. That's the team and, for Claude Code, the three plugins. Get the handle with `gh api user -q .login` when `gh` is signed in; otherwise ask. With no remote, use local-first with the email from `git config user.email`.

## 1. Install the CLI (Python 3.11+, no dependencies)

Check `python3 --version` first. Version 3.11 or later is required.

aidd is pre-release, so no `v1.0.0` tag exists yet, as [release status](https://github.com/thaithienvanid/aidd/blob/main/docs/ENTERPRISE.md#1-release-status-and-maturity) says. Run the first of these that applies. Each installs the latest commit, and `aidd init` later pins the CI files to that exact commit:

```sh
uv tool install git+https://github.com/thaithienvanid/aidd      # uv is on PATH
pipx install git+https://github.com/thaithienvanid/aidd         # pipx is on PATH
```

With neither, use the installer, which needs one commit SHA: take it with `git ls-remote https://github.com/thaithienvanid/aidd main`, tell the person which commit you pinned, and run `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh | AIDD_REF=<sha> sh`. Fetch `install.sh` from that commit, never from `https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh`, because `main` can move between the fetch and the install. Verify that `aidd --version` prints the version. If `aidd` is not on `PATH` after the installer's venv fallback, add `~/.local/bin` to `PATH`. Then say so. [docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md) covers every install path, and pinning after the release.

## 2. Adopt it in the repository

First look, and show the person what aidd proposes:

```sh
aidd init --dry-run
```

It writes nothing. It prints the stacks and test commands it found, the sensitive areas, the owners, the CI, and the config it proposes. Show that to the person. Use what they confirm, such as the test command and the Approvers, in the next command. Then run the one that matches their profile:

```sh
aidd init --profile solo --approvers @login --ref <sha>                                              # solo: the person's own handle
aidd init --profile team --approvers @org/leads --specialist security=@org/security --test "npm test" --ref <sha>   # team: real handles and the real test command
aidd init --profile solo --approvers email:you@example.com --ci none                                  # local-first: the email their commits use
```

- `--ref <sha>` pins the generated CI files to the same commit as the CLI. Local-first writes no CI files, so it needs none. Without it, an installed CLI can only pin `@v1.0.0`, a release tag that doesn't exist yet, as [docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#before-the-first-release) explains.
- Add `--test "<command>"` with the project's real test command when you know it, such as `npm test`, `pytest`, or `go test ./...`. Otherwise, leave it out and say that every Spec must bring its own test commands.
- Add `--team` unless the person declined the delivery team of agent roles.
- For Claude Code, add `--claude-plugins --mods` unless the person chose repository files. It needs the `claude` CLI on `PATH`. A Claude Code older than 2.1.295 skips `aidd-mods`, and the rest still installs.
- Add `--ci gitlab` on GitLab. Add `--ci none` on any other CI, or with no platform at all. On another CI, the person will run `aidd gate --context` from their pipeline, as [docs/PLATFORMS.md](https://github.com/thaithienvanid/aidd/blob/main/docs/PLATFORMS.md) shows.
- `aidd init` detects the coding agents the repository uses from their own folders and files in it, and wires each one. Add `--harness <agent>` for an agent the repository does not show yet, such as Claude Code in a fresh repository. `aidd init` prints the agents installed on this machine that need wiring. It writes `.aidd/config.yaml`, `specs/`, `AGENTS.md`, `REVIEW.md`, the vendored skill `.agents/skills/aidd/`, the CI workflows (in advisory mode under the solo and team profiles), and the agent-specific files. It also adds what the stack's tests and builds leave, and the files macOS and Windows leave, to `.gitignore` in marked blocks. It never overwrites an existing file. `--force` does, config included, so do not use `--force` on a repository that already has aidd.
- The agents it recognizes, and what it writes for each, are in [the install table](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#your-coding-agent). In short:

<!-- aidd:gen harnesses:summary -->
| Your agent | What `aidd init` does | What you do |
| --- | --- | --- |
| **Claude Code** | links the skill into `.claude/skills/`, wires the guard hook and the `aidd` MCP server; `--team` adds the roles, commands, packs, and practice skills as project agents and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one) | nothing (or use the plugins instead: see the note below the table) |
| **Codex** | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; wires the guard and the session hooks in `.codex/hooks.json` and the `aidd` MCP server in `.codex/config.toml` (outside Windows), keeping everything else in both; `--team` adds the roles as `.codex/agents/aidd-<role>.toml` and the team commands as skills in `.agents/skills/aidd-<flow>/`, which you run as `$aidd-<flow>` | trust the project, and review aidd's hooks once in `/hooks`: Codex runs a project's hooks only then |
| **Google Antigravity** | `AGENTS.md` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves; wires the guard and the session hooks in `.agents/hooks.json` and the `aidd` MCP server in `.agents/plugins/aidd/` (outside Windows); `--team` adds the roles as `.agents/agents/aidd-<role>.md`, the team commands as skills (`/aidd-<flow>`) in `.agents/skills/aidd-<flow>/`, and `.agents/skills.json`, which names the domain packs in `.claude/skills/` | nothing |
| **Grok Build** | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; wires the guard and the session hooks in `.grok/hooks/aidd.json` (outside Windows, and only after the folder is trusted); `--team` adds the roles as `.grok/agents/aidd-<role>.md` and the team commands as skills in `.grok/skills/aidd-<flow>/` | trust the folder (aidd's MCP tools are optional: add `aidd mcp` as a server for them) |
| **OpenCode V2** | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the guard plugin `.opencode/plugins/aidd.js`, which carries the guard and the loop hooks, and the terminal surface beside it in `.opencode/plugins/aidd-tui/` (`/aidd status`, `/aidd approve`, `/aidd land`, `/aidd merge`, `/aidd publish`, `/aidd decide`, `/aidd sign-off`, `/aidd update`, `/aidd init`); `--team` adds the roles as `.opencode/agents/aidd-<role>.md` and the team commands as `.opencode/commands/aidd-<flow>.md` | nothing (aidd's MCP tools are optional: `opencode mcp add aidd -- aidd mcp` adds them) |
| Cursor, Devin (Desktop, formerly Windsurf, and the CLI), Cline, Roo Code, Kiro, Amp, JetBrains Junie, Zed, Qwen Code, TraeCode, Augment Code, Factory Droid, DeepSeek Harness, Goose, Mistral Vibe, Google Jules | vendors the skill in `.agents/skills/aidd/` and points `AGENTS.md` at it; `--team` adds a short roles section to `AGENTS.md`, plus native agent files for GitHub Copilot, Kiro; no hook checks the agent, so the team is advisory | nothing |
| Gemini CLI (`GEMINI.md`), Continue (`.continue/rules/aidd.md`) | the same, plus a pointer in the agent's own instruction file, which init creates | nothing |
| GitHub Copilot (`.github/copilot-instructions.md`), Warp (`WARP.md`), Aider (`CONVENTIONS.md`) | the same, and appends the pointer to the agent's own instruction file only when that file already exists | nothing, except Aider: `read: CONVENTIONS.md` in `.aider.conf.yml` |
| Anything else | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

Gemini CLI was retired on June 18, 2026 for most users, who moved to the Antigravity CLI; it still serves some paid licenses ([details](docs/INSTALL.md#your-coding-agent)).

For Claude Code, we recommend the plugins over repository files: `aidd init --claude-plugins --team --mods`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd`, `/plugin install aidd-team@aidd`, and `/plugin install aidd-mods@aidd`. Init installs no `aidd-cli`, which puts the `aidd` command on the agent's `PATH`, so add it with `/plugin install aidd-cli@aidd` when no CLI is installed. The command (`aidd-cli`), the delivery team (`aidd-team`), and the status pane (`aidd-mods`) are optional, and every part works without them. With the aidd plugin enabled in your own Claude Code settings, `aidd init` enables it in the project's `.claude/settings.json` (`enabledPlugins` and `extraKnownMarketplaces`) instead of copying the hook, the MCP server, and the skill link into the repository. So Claude Code offers the plugin to everyone who trusts the folder, and nothing loads twice. A repository's own settings never count for this, and an `aidd` marketplace there that names another source gets the hooks instead. `--claude-hooks` copies them anyway.

Run `aidd init` again to add an agent, such as `aidd init --harness grok-build`: it reads the profile and approvers from the config it keeps, keeps every file that exists, and writes only what is new. It ends with the agents to restart: each loads aidd's hooks and instructions only when a session starts.
<!-- aidd:end -->

## 3. Verify

```sh
aidd doctor
aidd validate
```

Both must exit 0. Fix only what they name, such as a missing Approver under `team`. Then rerun them. If `aidd doctor` warns that no test command is configured, report it. Do not invent one.

## 4. Commit

Commit this setup on the branch `chore/adopt-aidd`, with everything `aidd init` wrote. Add the `Assisted-by:` trailer aidd expects on agent commits:

```text
chore: adopt aidd

Assisted-by: <your harness>/<your model>
```

Never commit, merge, or push onto the base branch yourself. A person lands the setup:

- **Local-first, or set up with `--ci none`.** A person then lands that Day-0 commit on the base branch, with a fast-forward merge. It is the one change that lands without `aidd land`.
- **On GitHub or GitLab with the gate workflow.** Push the branch and open the setup PR/MR. A person merges the setup PR/MR.
- **A new repository with no commit yet.** Do not commit. New repository: a person makes the Day-0 commit, this setup and the project scaffold, on the default branch. Stop here and hand back.

## 5. Hand back to the person

Tell them, in this order:

1. What `aidd init` installed and detected, and the commit SHA you pinned.
   When `aidd init` printed a `Restart ...` line, pass it on, because each agent it names loads aidd's hooks only when a session starts. This session doesn't have them yet.
2. On GitHub or GitLab, under the solo and team profiles, the gate runs in advisory mode. It reports on `aidd/gate (advisory)` and blocks nothing until they set `mode: enforce` in `.aidd/config.yaml` on the base branch. The org and audited profiles, and `aidd init --enforce`, start it in enforce mode. On GitHub, the workflow's `mode` input applies only when the config sets no mode, and `aidd init` writes one only with `--enforce`. On a private repository on GitHub Free, the status cannot be required, so the gate stays advisory whatever the config says. Tell them. The one step only they can do:
   - on GitHub, create the gate App and require the `aidd/gate` status on the protected branch, as [docs/PLATFORMS.md](https://github.com/thaithienvanid/aidd/blob/main/docs/PLATFORMS.md#setup) describes
   - on GitLab, the pipeline execution policy

   To see the loop work first, try the [local tutorial](https://github.com/thaithienvanid/aidd/blob/main/docs/QUICKSTART.md), which needs neither.
3. How they decide. In every agent the guard runs in, they type the decision at the agent's prompt, such as `approve SPEC-1`, `land it`, or `publish`. aidd records it before the agent reads the prompt. With local-first, there's no platform to set up. They can also approve at their own terminal with `aidd approve spec specs/<ID>.md` and `aidd approve merge`. They land a passing branch on the local trunk with `aidd land`, and publish it with `aidd publish`, as [docs/ADOPTION.md](https://github.com/thaithienvanid/aidd/blob/main/docs/ADOPTION.md#local-first-no-github-or-gitlab) describes. Each of those commands shows what the person decides on, and continues only when they answer yes. The commands refuse to run without an interactive terminal. They also refuse to run in a shell an agent started, where `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT` is set. So the person runs them in a terminal they opened themselves.
4. How work flows from now on. Every change runs one loop. It goes through Plan, for work bigger than one change, then Specify and Spec approval. Implement runs until the tests pass on a head, and Verify and Review then check that head side by side. Merge approval, Publish, Roll out, and Learn follow. Before the first edit, an agent reads `AGENTS.md`, loads the skill, and asks the gate for the change's route with `aidd gate --paths`. Then it follows the loop. With the team that `--team` adds, work starts from `/aidd-team:plan` or `/aidd-team:specify`. `aidd describe` prints the block a pull request needs. `aidd list` shows the open work and who holds each step. The person makes four decisions, and no agent makes them. They're the plan, Spec approval, the release as Merge approval, and the launch of a flagged feature. For free work that never merges as it is, the person types `explore branch <topic>` to start an explore branch.

## Never

- Never set the gate's mode to enforce, create the GitHub App, or change branch protection yourself.
- Never edit `.agents/skills/aidd/`, because it's vendored and `aidd upgrade --yes` refreshes it.
- Never edit anything between the `aidd:gen` and `aidd:end` comment markers of a generated block.
- Never approve, merge, or weaken the gate. Never run `aidd approve` or `aidd land`. The person decides those.
- Never edit the config so that a change needs no approval. Never start a standing approval with `aidd approve all`, because the person types `approve all` when they want the agents to approve for them. A yes you only read is not an approval.
- Never install from any source but `github.com/thaithienvanid/aidd` and its GitHub Releases. aidd is not on PyPI, so never install a package named `aidd` from there. Never run a script you did not fetch from there.

## Remove it

`aidd uninstall` lists everything init wrote. `aidd uninstall --yes` removes it, with its `.gitignore` blocks, and keeps Specs and any file the person changed since, as [docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#remove-it) describes.
