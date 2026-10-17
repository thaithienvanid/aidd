# Install

In a hurry? Ask your coding agent: "Install thaithienvanid/aidd and apply it to this project." It follows [llms-install.md](../llms-install.md), a runbook of the CLI, agent, and gate sections below.

This page owns the install commands and version pinning; other pages link here.

<a id="before-the-first-release"></a>
## Before the first release

aidd is pre-release: no `v1.0.0` tag exists, and nothing is on PyPI yet. So every command below that names `@v1.0.0` fails until the release. Until then, pick one commit SHA of this repository. Pin it everywhere:

1. **The CLI.** Install from the commit:

   ```sh
   uv tool install "git+https://github.com/thaithienvanid/aidd@<sha>"      # or: pipx install "git+...@<sha>"
   curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh | AIDD_REF=<sha> sh
   ```

2. **The CI files.** Run `aidd init --ref <sha>`, or `aidd upgrade --ref <sha> --yes` in a repository that is already set up. Either one pins the GitHub workflows and the `aidd_pin` line of the GitLab include to that commit.
   - Without `--ref`, `aidd init` pins what it can. Run from a git checkout, it pins the commit it runs from. Installed from a wheel, it resolves the release tag to its commit when it can reach GitHub. Otherwise it keeps the tag and prints how to pin it.
   - A commit pin carries a comment saying what it is: `# v1.0.0` only when the commit is that release's, otherwise `# aidd <short sha>`.

3. **Check.** `aidd --version` prints `aidd 1.0.0`. `aidd doctor` reports that the vendored skill matches it. Online with a GitHub remote, it also reports that the pinned commit exists at thaithienvanid/aidd. It warns when no branch or tag there points at that commit. When a pin still names the `v1.0.0` tag, it says to run `aidd upgrade --ref <sha> --yes`. `AIDD_OFFLINE=1` skips this online check. `grep -r '@v1.0.0' .github/workflows` finds nothing. On GitLab, `grep aidd_pin .gitlab/aidd.gitlab-ci.yml` shows the commit.

## The CLI

`<sha>` is one commit of this repository ([above](#before-the-first-release)). Until the release, it is the only form that works. The last column is for after the release.

| Method | Command now | After the release |
| --- | --- | --- |
| uv | `uv tool install "git+https://github.com/thaithienvanid/aidd@<sha>"` | `@v1.0.0` for `@<sha>` |
| pipx | `pipx install "git+https://github.com/thaithienvanid/aidd@<sha>"` | `@v1.0.0` for `@<sha>` |
| uv, no install | `uvx --from "git+https://github.com/thaithienvanid/aidd@<sha>" aidd --help` | `@v1.0.0` for `@<sha>` |
| From a checkout | `python3 -m venv .venv && .venv/bin/pip install .` | the same |
| One line | `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh \| AIDD_REF=<sha> sh` | `.../main/install.sh \| AIDD_SHA256=<wheel sha256> sh` |
| One file, no install | none yet | `aidd.pyz` from the GitHub Release: `python3 aidd.pyz --version` ([below](#one-file-aiddpyz)) |

The one-line installer uses uv, pipx, or a private venv, whichever you have:

- `AIDD_REF=vX.Y.Z` (default: this release) installs that release's wheel from PyPI. `AIDD_SHA256=<sha256>` (from the release's `SHA256SUMS`) checks the wheel before the installer installs it.
- `AIDD_REF=<commit sha>` builds from source, for testing unreleased code only.
- Until aidd is on PyPI, the installer refuses a release tag without `AIDD_SHA256`. Before aidd holds the name there, the name alone proves nothing.
- Fetch the script from a tag or commit URL instead of `main` when you want the script itself fixed.

<a id="updates"></a>
**Updates.** Once a day, after a command you run at a terminal, aidd asks GitHub (`git ls-remote`) for the latest release of thaithienvanid/aidd. When it is newer than the one you run, aidd says so in one line, and changes nothing. `aidd self-update` installs it the way you installed aidd (uv, pipx, or the one-line installer's venv). It installs the release's own wheel, and only after checking it: the wheel's sha256 must match the release's `SHA256SUMS`, and, with `gh` on your PATH, `gh attestation verify` must accept its build provenance. A mismatch installs nothing. `AIDD_AUTO_UPDATE=1` lets the daily check install a verified release itself. The check never runs in CI, in a shell an agent started, inside a hook, or offline (`AIDD_OFFLINE=1`), and `AIDD_NO_AUTO_UPDATE=1` turns its note off. It follows releases only, and never moves to a lower version. `aidd self-update --main` installs the tip of `main`, unreleased, with no release to check it against. `aidd self-update --check` only says what it would install. A failed update leaves the old CLI in place. A checkout (`pip install -e`, `uv tool install --editable`) follows its own checkout, and aidd does not update `aidd.pyz` or an install it did not make. The update covers the CLI only: your repositories change only when you run `aidd upgrade` ([Versions](#versions)).

If you use Claude Code, install the CLI instead of running it through `uvx`. The hook and the MCP server that `aidd init` writes start the aidd that it resolved at init time: the Python that ran `aidd init`, by its full path and isolated with `-I`. A `uvx` cache is not a stable place to start it from.

<a id="one-file-aiddpyz"></a>
**One file: `aidd.pyz`.** Each GitHub Release also carries `aidd.pyz`: the whole CLI as one [zipapp](https://docs.python.org/3/library/zipapp.html) with its bundled data. It is for a machine where you cannot install packages (a locked-down CI runner, a container, a shared host). The commands below download it, check it, and run it with any Python 3.11+:

```sh
curl -fsSLO https://github.com/thaithienvanid/aidd/releases/download/v1.0.0/aidd.pyz
curl -fsSLO https://github.com/thaithienvanid/aidd/releases/download/v1.0.0/SHA256SUMS
grep ' aidd.pyz$' SHA256SUMS | sha256sum -c -              # macOS: shasum -a 256 -c
gh attestation verify aidd.pyz --repo thaithienvanid/aidd   # the release's build provenance
python3 aidd.pyz --version
```

The first run extracts the bundled data once into `~/.cache/aidd/` (or `$XDG_CACHE_HOME/aidd/`). Inside it, a subfolder takes its name from the file's sha256. The one-line installer does not install it. It is a file you place yourself, for example as `~/.local/bin/aidd.pyz` with an alias `aidd='python3 ~/.local/bin/aidd.pyz'`. When you run `aidd init` from it, init wires the hooks and the MCP server as that Python, isolated with `-I`, with a short loader that names the file. So keep the file where it is. Maintainers build it with `PYTHONPATH=src python3 -m aidd.pyz <out>/aidd.pyz`.

The CLI needs Python 3.11+ and nothing else. The package bundles the schemas, the skill, the CI templates, and the team plugin with its domain packs and practice skills, so `aidd init` works offline.

## Your coding agent

Run `aidd init` in the repository. It detects the coding agents that the repository uses, and wires each one the way it reads instructions. It detects an agent by a folder or file that the agent keeps in the repository, never by what your machine has installed. So every teammate gets the same answer. `--harness <agent>` names an agent that the repository does not show yet. Init points at the agents installed on your machine whose wiring matters, such as Claude Code. `--harness none` disables detection. `aidd doctor` reports the result, with the agents that need nothing but `AGENTS.md` on one line. aidd stops an agent at edit time only when its hooks are wired. The other agents follow the skill, and the gate checks their work at merge.

<!-- aidd:gen harnesses -->
| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Claude Code | `.claude/`, `CLAUDE.md`, `.mcp.json` | links the skill into `.claude/skills/`, wires the guard hook and the `aidd` MCP server; `--team` adds the roles, commands, packs, and practice skills as project agents and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one) | nothing (or use the plugins instead: see the note below the table) |
| Codex | `.codex/`, `AGENTS.override.md` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; wires the guard and the session hooks in `.codex/hooks.json` (outside Windows), keeping any other hook there; `--team` adds the roles as `.codex/agents/aidd-<role>.toml` | trust the project, and review aidd's hooks once in `/hooks`: Codex runs a project's hooks only then |
| Google Antigravity | `.agents/rules/`, `.agents/workflows/`, `.agents/hooks.json`, `.agents/mcp_config.json`, `.agent/rules/` | `AGENTS.md` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves; wires the guard and the session hooks in `.agents/hooks.json` (outside Windows); `--team` adds the roles as `.agents/agents/aidd-<role>.md`, the flow commands as skills (`/aidd-<flow>`) in `.agents/skills/aidd-<flow>/`, and `.agents/skills.json`, which names the domain packs in `.claude/skills/` | nothing |
| Grok Build | `.grok/` | `AGENTS.md` and `.grok/skills/aidd/`; wires the guard and the session hooks in `.grok/hooks/aidd.json` (outside Windows, and only after the folder is trusted); `--team` adds the roles as `.grok/agents/aidd-<role>.md` and the flow commands as skills in `.grok/skills/aidd-<flow>/` | trust the folder, and add the MCP server (`aidd mcp`) |
| OpenCode V2 | `opencode.json`, `opencode.jsonc`, `.opencode/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; writes the guard plugin `.opencode/plugins/aidd.js` (outside Windows); `--team` adds the roles as `.opencode/agents/aidd-<role>.md` and the flow commands as `.opencode/commands/aidd-<flow>.md` | wire the aidd MCP server: `opencode mcp add aidd -- aidd mcp` |

For Claude Code, we recommend the three plugins over repository files: `aidd init --claude-plugins --team --mods`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd`, `/plugin install aidd-team@aidd`, and `/plugin install aidd-mods@aidd`. The delivery team (`aidd-team`) and the status pane (`aidd-mods`) are optional, and every part works without them.

**Every other agent** reads `AGENTS.md` and the vendored skill. No hook checks its steps, so its team is advisory, and the `aidd/gate` check decides what merges. `aidd init` wires each of these 21 agents when it finds it.

<details><summary>What <code>aidd init</code> does for each of the other 21 agents</summary>

| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.github/hooks/` | `AGENTS.md` for the cloud agent, the CLI, and VS Code; in VS Code, the pointer is also appended to `.github/copilot-instructions.md` when that file exists; `--team` adds the roles as `.github/agents/aidd-<role>.agent.md` | nothing |
| Cursor | `.cursor/`, `.cursorrules` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Gemini CLI | `GEMINI.md`, `.gemini/` | the same, plus a `GEMINI.md` pointer, because Gemini CLI reads `AGENTS.md` only through its `context.fileName` setting | nothing. Retired on June 18, 2026 for Google AI Pro, Ultra, and free use, which moved to the Antigravity CLI; it still serves Gemini Code Assist Standard and Enterprise licenses and paid API keys |
| Devin (Desktop, formerly Windsurf, and the CLI) | `.devin/`, `.windsurf/`, `.windsurfrules` | `AGENTS.md` | nothing |
| Cline | `.clinerules`, `.cline/` | `AGENTS.md` | nothing |
| Roo Code | `.roo/`, `.roorules`, `.roomodes` | `AGENTS.md` at the workspace root | nothing |
| Kiro | `.kiro/` | `AGENTS.md`, read alongside `.kiro/steering/`; `--team` adds the roles as `.kiro/agents/aidd-<role>.json` | nothing |
| Amp | `.amp/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| JetBrains Junie | `.junie/` | `AGENTS.md` | nothing |
| Zed | `.zed/`, `.rules` | `AGENTS.md` and `.agents/skills/aidd/`; Zed reads the first of `.rules`, `.cursorrules`, `AGENTS.md`, and a few others, so a repository with a `.rules` file keeps that one | nothing |
| Warp | `WARP.md`, `.warp/` | `AGENTS.md` and `.agents/skills/aidd/`; a `WARP.md` gets the pointer when it exists | nothing |
| Qwen Code | `QWEN.md`, `.qwen/` | `AGENTS.md`, read next to `QWEN.md` | nothing |
| TraeCode | `.trae/` | `AGENTS.md` | nothing |
| Continue | `.continue/` | a rule file `.continue/rules/aidd.md` for the IDE extension; the `cn` CLI also reads `AGENTS.md` | nothing |
| Augment Code | `.augment/`, `.augment-guidelines` | `AGENTS.md` | nothing |
| Factory Droid | `.factory/` | `AGENTS.md` | nothing |
| DeepSeek Harness | nothing it keeps there: `--harness deepseek-harness` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Goose | `.goosehints`, `.goose/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Mistral Vibe | `.vibe/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Aider | `.aider.conf.yml`, `.aiderignore` | a `CONVENTIONS.md` gets the pointer when it exists; Aider reads no instruction file on its own | add `read: CONVENTIONS.md` to `.aider.conf.yml` |
| Google Jules | nothing it keeps there: `--harness jules` | `AGENTS.md`, which Jules reads from the repository | nothing; Jules runs in the cloud and needs no local file |
| Anything else | | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

</details>
<!-- aidd:end -->

### Claude Code

- **Claude Code, as plugins.** `aidd init --claude-plugins` runs `claude plugin marketplace add thaithienvanid/aidd` and `claude plugin install aidd@aidd` for your user, plus `aidd-team@aidd` with `--team` and the optional `aidd-mods@aidd` with `--mods`. It writes no `.claude/` files. A Claude Code older than 2.1.295 skips `aidd-mods`, and a failed `aidd-mods` install leaves the other plugins in place. The repository keeps `.agents/skills/aidd/` and `AGENTS.md` for other agents. The plugin ships the skill, the MCP server, and the hook, run from its own source. To install the plugins inside Claude Code, see [Claude Code plugins](#claude-code-plugins).
- **Claude Code, repository files.** `aidd init` links the skill at `.claude/skills/aidd`, adds the guard as a `PreToolUse` hook in `.claude/settings.json`, and registers `aidd mcp` in `.mcp.json`.
  - The hook and the server start aidd through `~/.aidd/bin/aidd`, a launcher that `aidd init` writes for your user on this machine. It runs the Python that ran `aidd init`, by its full path, with `-I`. `-I` keeps the repository and `PYTHONPATH` off the module path, so a repository cannot replace aidd.
  - The files in the repository name the launcher through `$HOME`. So they hold no machine's path, and they are the same for every contributor. Each contributor runs `aidd init --agent-hooks` once, on their own machine, to write their own launcher.
  - Init never writes the bare `aidd`, because its script runs without `-I`. For an install from a checkout, a short loader names the source folder. `aidd doctor` reports a bare `aidd` or an older launcher, and `aidd init --agent-hooks` replaces it.
  - On Windows, init writes this machine's launcher into each hook, for PowerShell, and names the shell (`"shell": "powershell"`). Without that field, Claude Code on Windows picks Git Bash or PowerShell by what is installed. A team on several systems uses the plugin, whose hooks are the same everywhere. The aidd plugin's own hooks need Git Bash on Windows.
  - Where the launcher cannot run, the guard prints `aidd: the guard could not run on this machine`, with the command that fixes it, and the session-start hook tells the agent. The guard then allows the call, or blocks it where the project fails closed (the `audited` profile, or an organization's `AIDD_HOOK_FAIL_CLOSED=1`).
  - `aidd doctor` starts both once with a harmless input, and fails when either cannot run. It refuses a launcher that init did not write, one that another user can change, and one inside the repository. It also fails when a Claude Code settings file sets `HOME` in its `env`, since the hooks find the launcher through `HOME`. `aidd uninstall` keeps the launcher, because every repository on the machine uses it.
  - `--team` adds roles in `.claude/agents/`, commands as `.claude/commands/aidd-<name>.md`, and packs and practice skills in `.claude/skills/`. A command from these files runs as `/aidd-<name>`, such as `/aidd-implement`. From the plugin, it runs as `/aidd-team:<name>`. `--no-agent-hooks` skips the hook and the server. `--agent-hooks` forces them.
- **Claude in chat, the desktop app, and Cowork.** The same plugins load there, but not all of them.
  - Chat loads the skill and runs commands as skills. It ignores agents, hooks, and the local `aidd` MCP server. So chat gets the method and none of its enforcement. Use it to draft or discuss a Spec. Deliver the change from Claude Code or another agent in the repository, where the hook and the gate apply.
  - Cowork loads agents and hooks, and the MCP server only when the session runs on your computer.
  - The gate on the platform applies either way.
- **A whole team or organization.** Commit `extraKnownMarketplaces` and `enabledPlugins` to the repository's `.claude/settings.json`. Then every contributor who trusts the folder gets the plugins. Or require them on every machine with managed settings ([ENTERPRISE.md](ENTERPRISE.md#12-agent-sessions-under-managed-settings)). The marketplace names `relevance` signals (a `.aidd/config.yaml` read, an `aidd` command run). So once an administrator lists `aidd` in `pluginSuggestionMarketplaces`, Claude Code suggests the plugin to a teammate who works in an aidd repository without it. It never installs one by itself.

#### Claude Code plugins

The `aidd` marketplace holds three plugins. `aidd` carries the skill, the MCP server, and the hooks. `aidd-team` carries the roles, the commands, the domain packs, and the practice skills, and needs `aidd`. `aidd-mods` is optional and experimental, and needs `aidd`. It answers `/aidd <verb>` in Claude Code with no model turn:

| You type | What happens |
| --- | --- |
| `/aidd status` | a side pane: your next decision and what to type, the shape of the work (each small goal on the ladder of your four decisions), this branch's work, the trunk-based flow, and the autopilot run; `/aidd close` closes it |
| `approve SPEC-1`, `/aidd approve SPEC-1` | approved, for exactly the hash it names; `approve` alone approves what waits on you ([Approve in Claude Code](ADOPTION.md#approve-in-claude-code)) |
| `approve merge`, `ship it`, `/aidd ship` | the Merge approval of this branch's head, or the ship with no platform |
| `/aidd update` | one dialog, then the CLI (`aidd self-update`) and this repository's aidd files (`aidd upgrade --yes`) |
| `/aidd install [flags]` | one dialog, then `aidd init [flags]`, as solo unless you name a profile |
| `/aidd help`, `/aidd` | the verbs; a bare `/aidd` loads the skill for the agent |

Your own typed words are the decision, so they are recorded at once. The agent cannot type into your prompt. A request that did not come from your keyboard, such as the agent running `/aidd approve` through the skill, asks you in Claude Code's own dialog first. The pane only shows what the `aidd` CLI prints, and nothing it draws reaches the model. It needs Claude Code 2.1.295 or later and the CLI on the `PATH`.

- **From the public repository.** In Claude Code, run these commands:

  ```text
  /plugin marketplace add thaithienvanid/aidd
  /plugin install aidd@aidd
  /plugin install aidd-team@aidd
  /plugin install aidd-mods@aidd
  ```

  We recommend all three. `aidd-team` and `aidd-mods` are optional, and every part works without them. Then run `/reload-plugins` or restart Claude Code, so that the roles, the commands, and the hooks load.
- **From a local folder.** Use this before the repository is public, or to try local changes: `/plugin marketplace add /path/to/aidd`. Claude Code reads the plugins in place. An edit applies at the next session or after `/reload-plugins`, with no version bump. In the aidd repository itself, the plugin's MCP server does not start, because its source is inside the project. The hooks still run.
- **From a private repository.** Claude Code clones with the git credentials already on the machine, and it never prompts. Without a GitHub SSH key, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`. Then store an HTTPS credential with `gh auth login`, then `gh auth setup-git`.
- **Updates.** Run `claude plugin update aidd@aidd`, `claude plugin update aidd-team@aidd`, and `claude plugin update aidd-mods@aidd` ([Versions](#versions)).
- **Python.** The aidd plugin's hook and MCP server need Python 3.11 or later, or `uv` with a Python outside any virtual environment (`uv python install 3.12`). The hook never downloads anything. Without either, the hooks do not run. Under `AIDD_HOOK_FAIL_CLOSED=1`, the edit hook blocks every edit instead. Otherwise the skill and the team still guide the agents, and the CI gate still decides. This is skill-only mode.
- **Hooks.** The aidd plugin wires the guard (PreToolUse) and the session hooks: SessionStart, UserPromptSubmit, Stop, SubagentStop, and PreCompact. `aidd init --agent-hooks` writes the same hooks into `.claude/settings.json`. With the team installed, the guard also applies `agents.delegate`. By default (`auto`), it tells the main session which role owns a file, and it denies the edit only in an autopilot run's session. The audited profile's default, `always`, applies only when the team is installed. An explicit `delegate: always` without the team denies every main-session edit of repository content and says to install the team, and `aidd doctor` reports it as an error ([Config](CONFIG.md#mission-goal-and-agents)).

### Codex

`aidd init` wires aidd's hooks in `.codex/hooks.json`, the Claude Code shape Codex reads, and keeps every other hook in that file. Codex runs a project's hooks only once you trust the project, and each new or changed hook only once you review it: run `/hooks` in Codex after `aidd init` and after each `aidd upgrade`. The commands are sh, so init skips them on Windows.

- **The guard** sees every tool call: a shell command (`Bash`), an edit (`apply_patch`, each file the patch names), and an MCP tool. It denies what it denies in Claude Code. Codex's tool event names no subagent, so a role's write area is not enforced; its `.codex/agents/` sandbox settings and the gate still hold.
- **An allowed call** gets no answer, and your approval settings decide.
- **When aidd cannot run**, the guard gives no opinion, or denies where the project fails closed.
- **The session hooks**: `SessionStart` adds the change's summary, `UserPromptSubmit` the next step, and `Stop` continues a finished turn once when the tests have not passed on the head.

Codex gives a command no variable for its session, so under autopilot the session note names it, for `--session`. `aidd doctor` checks the hook file and runs the guard once. Add the MCP server in `.codex/config.toml` or with `codex mcp add aidd -- aidd mcp`.

### Google Antigravity

`aidd init` wires aidd's hooks in `.agents/hooks.json`, under one hook name, `aidd`. It never changes another hook in that file. The commands are sh, so init skips them on Windows, where Antigravity runs hooks with `cmd`. The hooks start aidd through `~/.aidd/bin/aidd`, like Claude Code's.

- **The guard** sees every tool call. It denies a write outside the Spec's scope, a frozen test, a protected path, an approval, and a merge, as in Claude Code. Antigravity's hook event names the conversation, never the role, so a role's write area is not enforced.
- **An allowed call** gets no opinion (`{"decision": ""}`), so your own permission settings still decide. The guard never answers `allow`, which would approve the call for you.
- **When aidd cannot run**, the guard gives no opinion, or denies where the project fails closed (the `audited` profile, or an organization's `AIDD_HOOK_FAIL_CLOSED=1`).
- **Per project.** Install the plugins for your user: aidd does nothing in a repository without `.aidd/config.yaml`, and it never writes to your user settings.
- **The session hooks**: `SessionStart` adds the change's summary. `PreInvocation` adds the next step before a turn's first model call, under the team and org profiles. `Stop` continues a finished turn once when the tests have not passed on the head.

Antigravity has no variable for a conversation's id. Under autopilot, the session note names it, and `/aidd-autopilot` passes it as `--session`. `aidd doctor` checks the hook file and runs the guard once.

`aidd init --team --harness antigravity` writes the roles as `.agents/agents/aidd-<role>.md` and the flow commands as skills, `.agents/skills/aidd-<flow>/SKILL.md`. Run a flow as `/aidd-<flow>`. Antigravity deprecates workflows (`.agents/workflows/`) for skills. `.agents/skills.json` names `.claude/skills/`, so Antigravity also finds the domain packs and practice skills.

Antigravity reads MCP servers only from your user config or a plugin, so init writes none. To add aidd's, put it in `~/.gemini/config/mcp_config.json`:

```json
{ "mcpServers": { "aidd": { "command": "aidd", "args": ["mcp"] } } }
```

### Grok Build

`aidd init` wires aidd's hooks in `.grok/hooks/aidd.json`, in the Claude Code shape Grok Build reads. Grok runs a project's hooks only after you trust the folder: run `/hooks-trust` once, or start with `grok --trust`. The commands are sh, so init skips them on Windows.

- **The guard** sees every tool call and reads the role from `subagentType`, so a role's write area holds, as in Claude Code. An allowed call gets no answer, and your permission settings decide.
- **The session hooks**: `SessionStart` adds the change's summary, and `Stop` reminds the agent once when the tests have not passed on the head. Grok drops a prompt hook's context, so no next-step line comes with a prompt.
- **The aidd plugin.** Grok also loads the Claude Code plugins installed for you. With the aidd plugin installed, its own guard runs in Grok sessions too, beside the project's hook file.

`aidd init --team --harness grok-build` writes the roles as `.grok/agents/aidd-<role>.md` and the flow commands as skills, `.grok/skills/aidd-<flow>/SKILL.md`. Run a flow as `/aidd-<flow>`. Add the MCP server yourself, with `aidd mcp` as its command.

### OpenCode

aidd requires **OpenCode V2**; **V1 is not supported**. The role agents use the native V2 format, a `permissions:` rule list (V2 still loads the V1 format). OpenCode V1 ignores these rules, so on V1 the roles run without them. Upgrade OpenCode, then run `aidd upgrade --yes`: it rewrites role files an older aidd wrote in the V1 shape.

aidd's guard hook, which checks each edit and command and enforces the autopilot lease, is wired for <!-- aidd:gen list:guard-harnesses -->Claude Code, Codex, Google Antigravity, Grok Build, and OpenCode V2<!-- aidd:end -->. On OpenCode it is a plugin, `.opencode/plugins/aidd.js`, which `aidd init` writes and OpenCode loads by itself (restart OpenCode after init):

- **The guard** sees every tool call through OpenCode's `execute.before` hook: a shell command, an edit or a write, a patch, and an MCP or plugin tool. It denies what it denies in Claude Code, and a role (`aidd-<role>`) keeps to its write area. A deny throws, so the call does not run and the agent reads why.
- **An allowed call** gets no answer, so the role's `permissions:` rules and your own settings decide.
- **When aidd cannot run**, the plugin warns and allows, or denies where the project fails closed (the `audited` profile, or an organization's `AIDD_HOOK_FAIL_CLOSED=1`).
- **No session hooks.** OpenCode's plugin API has no session start, so the change's summary and the stop reminder do not come; the skill and `aidd list` say what is next. The launcher is an sh script, so init skips the plugin on Windows.

OpenCode gives a command no variable that names its session. So `/aidd-autopilot` writes `--session ${AIDD_SESSION_ID}`, and aidd's plugin puts the session's id in its place before the command runs. Without the plugin, `aidd autopilot start` makes a new id and prints it, and the run passes that id on.

`aidd init --team --harness opencode` writes the roles as `.opencode/agents/aidd-<role>.md` and the flow commands as `.opencode/commands/aidd-<flow>.md`. Run a flow as `/aidd-<flow>`, such as `/aidd-specify`. Wire the aidd MCP server:

```sh
opencode mcp add aidd -- aidd mcp
```

`aidd mcp` speaks both the 2026-07-28 revision and the legacy `initialize` ones, so the server's `protocol` setting can stay at OpenCode's default, `legacy`, or be `auto`.

Or add it to `opencode.json` yourself:

```json
{
  "mcp": {
    "servers": {
      "aidd": { "type": "local", "command": ["aidd", "mcp"], "cwd": "." }
    }
  }
}
```

### Other agents

Every other agent reads `AGENTS.md` and the vendored skill, and `aidd init` wires it the way the folded table above says. No hook checks its steps: the team is advisory there, and the `aidd/gate` check decides what merges.

- **Any other coding agent.** The section and the vendored folder cover any agent that reads `AGENTS.md` or `.agents/skills/`, whether or not it is in the table. For the team, ask the agent to act as one role per session.
- **Other skill folders.** `aidd init --link <dir>` links the skill into one more folder, for example `--link .github/skills`, in addition to `.claude/skills`.

`aidd doctor` reports a vendored skill or a copied link that differs from the CLI's version. `aidd upgrade` lists what it would refresh, and `aidd upgrade --yes` refreshes it. Do not use `aidd init --force` for this: it also overwrites your config. Never edit the vendored folder. Put repository-specific guidance in `AGENTS.md`.

Do not link the vendored skill to an aidd checkout with a symlink. The link breaks in CI and for teammates, who do not have your checkout. Also, `.agents/**` is a protected path. Through the link, the agents' instructions would change without review. `aidd upgrade` skips a linked skill.

### Use all of aidd

This recipe turns on every part of aidd in Claude Code: the three plugins, the delivery team, and the strongest session hooks.

1. Install the CLI ([The CLI](#the-cli)).
2. In Claude Code, install the plugins, then load them:

   ```text
   /plugin marketplace add thaithienvanid/aidd
   /plugin install aidd@aidd
   /plugin install aidd-team@aidd
   /plugin install aidd-mods@aidd
   /reload-plugins
   ```

3. In the repository, set up aidd with the team profile, your email as the Approver, and the delivery team:

   ```sh
   aidd init --profile team --approvers email:you@example.com --team --claude-plugins --mods
   ```

   With `--claude-plugins`, the plugins carry the Claude Code part, so init writes no `.claude/` files and nothing loads twice. Init also runs the same installs through the `claude` CLI. A plugin that is already installed stays as it is. If init reports `failed` or `skipped` for a plugin, it wired the whole set of repository files for Claude Code instead, and its `fallback` line names them. These files replace the plugins, so uninstall the two plugins (`claude plugin uninstall aidd@aidd` and `aidd-team@aidd`, or `/plugin` in Claude Code). Otherwise the skill and the roles load twice, and `aidd doctor` warns. To use the plugins instead, first remove the cause. If the `claude` CLI is missing, install it. If an install failed, see the `failed` line above it. Then run `aidd uninstall --yes` and the same `aidd init` again.
4. For the strongest hold, set the session hooks to `strict` in `.aidd/config.yaml` ([Config](CONFIG.md#hooks)):

   ```yaml
   hooks:
     level: strict
   ```

   At `strict`, the stop hook blocks the agent's stop once while a Spec's changes have no passing tests on the head commit.
5. Run `aidd doctor`. It checks the wiring and fails on a part that cannot run.
6. Restart Claude Code, so that the session starts with the plugins and the new config.
7. For a team, commit these keys to the repository's `.claude/settings.json`. Claude Code prompts each contributor who trusts the folder to install both plugins:

   ```json
   {
     "extraKnownMarketplaces": {
       "aidd": { "source": { "source": "github", "repo": "thaithienvanid/aidd" } }
     },
     "enabledPlugins": { "aidd@aidd": true, "aidd-team@aidd": true }
   }
   ```

   `.claude/` is a protected path, so this change takes the major route.


## The gate

`aidd init --ci github` (the default) writes the workflows and the PR template. `--ci gitlab` writes the include. `--ci none` writes neither. The gate starts in advisory mode. [PLATFORMS.md](PLATFORMS.md) covers going live (the gate's App, its environment, and the branch ruleset), GitLab, and other CI systems.

The secret scan runs gitleaks over the history and the working tree. It is the `secrets` job of `aidd-security.yml` (GitHub) or the `aidd-secrets` job of `aidd-security.gitlab-ci.yml` (GitLab). `aidd init` writes either file with compliance on or with `--security-ci`. On a pull or merge request, the scan reads `.gitleaks.toml` and `.gitleaksignore` from the base branch. So a change cannot turn off its own scan. The scan also ignores inline `gitleaks:allow` comments. On GitLab, turn on "run pipelines in the parent project for merge requests from forks". A fork controls a pipeline in its own project.

- **A fake key in a test.** In `.gitleaks.toml`, keep `[extend] useDefault = true`. Add an `[[allowlists]]` entry with `condition = "AND"`, the test file's path, and a regex for the fake value only. Never allow a path alone: a real secret in that file would pass too. aidd's own `.gitleaks.toml` is an example.
- **A revoked secret still in the history.** Revoke the secret first. Then add its fingerprint to `.gitleaksignore`. The job log names the fingerprint of each finding.
- **GitHub push protection.** It complements the scan where your plan offers it. It blocks a secret before the push lands, but it never scans the history.

## Versions

Pin one version everywhere. That covers the CLI install, the workflow templates (the `@v1.0.0` refs of the reusable gate and the test action), and the vendored skill (`metadata.version`). Someone can move a tag, but nobody can move a commit SHA. So pin the SHA of a release for the strongest integrity. `aidd init --ref <sha>` and `aidd upgrade --ref <sha> --yes` write that pin into the CI files. Upgrade them together in one change. That change touches files the gate protects (its own workflows and config), so the gate treats it as major: the strictest review.

- **Before the first release.** Pin a commit SHA ([above](#before-the-first-release)).
- **Upgrade.**
  1. Update the CLI: `aidd self-update` installs the latest release, checked first ([Updates](#updates)). To pin a commit by hand, install it again at that commit: `uv tool install --force "git+https://github.com/thaithienvanid/aidd@<sha>"` or `pipx install --force "git+...@<sha>"`. `uv tool upgrade aidd` and `pipx upgrade aidd` do not work here: they reinstall the commit the install already pins. For the Claude Code plugins, run `claude plugin update aidd@aidd` and `aidd-team@aidd`.
  2. Run `aidd upgrade` in each repository. It is a dry run that lists what it would change. The list covers the vendored skill, the team files already installed, the aidd pins in your CI files, and `aidd_version`. For the team files, `aidd upgrade --yes` then adds what the release added and names what it retired. Your config, REVIEW.md, AGENTS.md, and your own CI steps stay as they are.
  3. `aidd upgrade --yes` makes the changes. Run `aidd doctor`. Then merge the changes as one change through the gate. The gate reads config from the base branch, so the new version judges only later changes.
- **Roll back.** Revert that PR/MR.
- **The Claude Code plugins.** Both manifests set `version`, so Claude Code updates an installed plugin only when that number changes. A release that forgets to bump it leaves users on the old copy.

What a patch, minor, or major version may change is in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning).

## Remove it

1. Drop `aidd/gate` from the branch ruleset first. The removal touches protected paths, so it would otherwise wait on the gate it removes (an administrator can merge instead).
2. `aidd uninstall` lists everything that `aidd init` and `aidd init --team` wrote. `aidd uninstall --yes` removes it, and aidd's output folders in `.aidd/` (the evidence, the pages, the preview captures). It leaves `.git/aidd/`, the autopilot journal and the guard's log, which init never wrote. It keeps any file you changed since, and says so. Specs stay. On GitLab, `.gitlab/aidd.gitlab-ci.yml` and `.gitlab/aidd-security.gitlab-ci.yml` go with it. Remove the `include:` lines you added to `.gitlab-ci.yml` yourself.
3. Uninstall the gate App. Delete the `aidd-gate` environment.
4. Claude Code plugin users: `claude plugin uninstall aidd@aidd` and `claude plugin uninstall aidd-team@aidd`.
5. Remove the CLI: `uv tool uninstall aidd` or `pipx uninstall aidd`. For the installer's venv fallback, delete `~/.local/share/aidd` and `~/.local/bin/aidd`. Once no repository on the machine uses aidd, delete `~/.aidd`, which holds the launcher of its hooks.

Every command and flag: [CLI.md](CLI.md).
