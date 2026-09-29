# Install

In a hurry? Ask your coding agent: "Install thaithienvanid/aidd and apply it to this project." It follows [llms-install.md](../llms-install.md), a runbook of the CLI, agent, and gate sections below.

This page owns the install commands and version pinning; other pages link here.

<a id="before-the-first-release"></a>
## Before the first release

aidd is pre-release: no `v1.0.0` tag exists and nothing is on PyPI yet, so every command below that names `@v1.0.0` fails until the release. Until then, pick one commit SHA of this repository and pin it everywhere:

1. **The CLI.** Install from the commit:

   ```sh
   uv tool install "git+https://github.com/thaithienvanid/aidd@<sha>"      # or: pipx install "git+...@<sha>"
   curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh | AIDD_REF=<sha> sh
   ```

2. **The CI files.** Run `aidd init --ref <sha>`, or `aidd upgrade --ref <sha> --yes` in a repository that is already set up. Either one pins the GitHub workflows and the `aidd_pin` line of the GitLab include to that commit.
   - Without `--ref`, `aidd init` pins what it can. Run from a git checkout, it pins the commit it runs from. Installed from a wheel, it resolves the release tag to its commit when it can reach GitHub; otherwise it keeps the tag and prints how to pin it.
   - A commit pin carries a comment saying what it is: `# v1.0.0` only when the commit is that release's, otherwise `# aidd <short sha>`.

3. **Check.** `aidd --version` prints `aidd 1.0.0`, `aidd doctor` reports that the vendored skill matches it and, online with a GitHub remote, that the pinned commit exists at thaithienvanid/aidd (it warns when no branch or tag there points at it; `AIDD_OFFLINE=1` skips the check), and `grep -r '@v1.0.0' .github/workflows` finds nothing. On GitLab, `grep aidd_pin .gitlab/aidd.gitlab-ci.yml` shows the commit.

## The CLI

| Method | Command |
| --- | --- |
| One line | `curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh \| AIDD_SHA256=<wheel sha256> sh` |
| uv | `uv tool install "git+https://github.com/thaithienvanid/aidd@v1.0.0"` |
| pipx | `pipx install "git+https://github.com/thaithienvanid/aidd@v1.0.0"` |
| uv, no install | `uvx --from "git+https://github.com/thaithienvanid/aidd@v1.0.0" aidd --help` |
| From a checkout | `python3 -m venv .venv && .venv/bin/pip install .` |
| One file, no install | `aidd.pyz` from the GitHub Release: `python3 aidd.pyz --version` ([below](#one-file-aiddpyz)) |

Until the release, use `@<sha>` for `@v1.0.0` and `AIDD_REF=<sha>` for the one-line installer ([above](#before-the-first-release)).

The one-line installer uses uv, pipx, or a private venv, whichever you have:

- `AIDD_REF=vX.Y.Z` (default: this release) installs that release's wheel from PyPI, and `AIDD_SHA256=<sha256>` (from the release's `SHA256SUMS`) checks the wheel before it is installed.
- `AIDD_REF=<commit sha>` builds from source, for testing unreleased code only.
- Until aidd is published on PyPI, the installer refuses a release tag without `AIDD_SHA256`: before aidd holds the name there, the name alone proves nothing.
- Fetch the script from a tag or commit URL instead of `main` when you want the script itself fixed.

If you use Claude Code, install the CLI rather than running it through `uvx`: the hook and the MCP server that `aidd init` writes start the aidd it resolved at init time (`aidd` on `PATH`, else that Python with `-m aidd`), and a `uvx` cache is not a stable place to start it from.

<a id="one-file-aiddpyz"></a>
**One file: `aidd.pyz`.** Each GitHub Release also carries `aidd.pyz`, the whole CLI as one [zipapp](https://docs.python.org/3/library/zipapp.html) with its bundled data, for a machine where you cannot install packages (a locked-down CI runner, a container, a shared host). Download it, check it, and run it with any Python 3.11+:

```sh
curl -fsSLO https://github.com/thaithienvanid/aidd/releases/download/v1.0.0/aidd.pyz
curl -fsSLO https://github.com/thaithienvanid/aidd/releases/download/v1.0.0/SHA256SUMS
grep ' aidd.pyz$' SHA256SUMS | sha256sum -c -              # macOS: shasum -a 256 -c
gh attestation verify aidd.pyz --repo thaithienvanid/aidd   # the release's build provenance
python3 aidd.pyz --version
```

The first run extracts the bundled data once into `~/.cache/aidd/` (or `$XDG_CACHE_HOME/aidd/`), in a folder named by the file's sha256. The one-line installer does not install it: it is a file you place yourself, for example as `~/.local/bin/aidd.pyz` with an alias `aidd='python3 ~/.local/bin/aidd.pyz'`. `aidd init` run from it wires the hooks and the MCP server as that Python with `-m aidd` and `PYTHONPATH` naming the file, so keep the file where it is. Maintainers build it with `PYTHONPATH=src python3 -m aidd.pyz <out>/aidd.pyz`.

The CLI needs Python 3.11+ and nothing else. The package bundles the schemas, the skill, the CI templates, and the team plugin with its domain packs and practice skills, so `aidd init` works offline.

## Your coding agent

Run `aidd init` in the repository. It detects the coding agents the repository uses (a folder or file each one keeps in it, never what your machine has installed, so every teammate gets the same answer) and wires each one the way it reads instructions. `--harness <agent>` names one the repository does not show yet (init points at the ones installed on your machine whose wiring matters, such as Claude Code), `--harness none` disables detection, and `aidd doctor` reports the result, with the agents that need nothing but `AGENTS.md` on one line.

<!-- aidd:gen harnesses -->
| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |
| --- | --- | --- | --- |
| Claude Code | `.claude/`, `CLAUDE.md`, `.mcp.json` | links the skill into `.claude/skills/`, wires the edit-time hook and the `aidd` MCP server; `--team` adds the roles, commands, packs, and practice skills as project agents and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one) | nothing (or use the plugins instead: see the note below the table) |
| Codex | `.codex/`, `AGENTS.override.md` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; `--team` adds the roles as `.codex/agents/aidd-<role>.toml` | nothing |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/skills/`, `.github/hooks/` | `AGENTS.md` for the cloud agent, the CLI, and VS Code; in VS Code, the pointer is also appended to `.github/copilot-instructions.md` when that file exists; `--team` adds the roles as `.github/agents/aidd-<role>.agent.md` | nothing |
| Cursor | `.cursor/`, `.cursorrules` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Google Antigravity | `.agents/rules/`, `.agents/workflows/`, `.agents/hooks.json`, `.agents/mcp_config.json`, `.agent/rules/` | `AGENTS.md` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves | nothing |
| Gemini CLI | `GEMINI.md`, `.gemini/` | the same, plus a `GEMINI.md` pointer, because Gemini CLI reads `AGENTS.md` only through its `context.fileName` setting | nothing. Retired on June 18, 2026 for Google AI Pro, Ultra, and free use, which moved to the Antigravity CLI; it still serves Gemini Code Assist Standard and Enterprise licenses and paid API keys |
| Devin (Desktop, formerly Windsurf, and the CLI) | `.devin/`, `.windsurf/`, `.windsurfrules` | `AGENTS.md` | nothing |
| Cline | `.clinerules`, `.cline/` | `AGENTS.md` | nothing |
| Roo Code | `.roo/`, `.roorules`, `.roomodes` | `AGENTS.md` at the workspace root | nothing |
| Kiro | `.kiro/` | `AGENTS.md`, read alongside `.kiro/steering/`; `--team` adds the roles as `.kiro/agents/aidd-<role>.json` | nothing |
| Amp | `.amp/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| OpenCode | `opencode.json`, `opencode.jsonc`, `.opencode/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself; `--team` adds the roles as `.opencode/agents/aidd-<role>.md` | nothing |
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
| Grok Build | `.grok/` | `AGENTS.md` | nothing |
| Mistral Vibe | `.vibe/` | `AGENTS.md`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself | nothing |
| Aider | `.aider.conf.yml`, `.aiderignore` | a `CONVENTIONS.md` gets the pointer when it exists; Aider reads no instruction file on its own | add `read: CONVENTIONS.md` to `.aider.conf.yml` |
| Google Jules | nothing it keeps there: `--harness jules` | `AGENTS.md`, which Jules reads from the repository | nothing; Jules runs in the cloud and needs no local file |
| Anything else | | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

Claude Code users who prefer plugins over repository files run `aidd init --claude-plugins`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd` and then `/plugin install aidd@aidd`.
<!-- aidd:end -->

- **Claude Code, as plugins.** `aidd init --claude-plugins` runs `claude plugin marketplace add thaithienvanid/aidd` and `claude plugin install aidd@aidd` for your user, plus `aidd-team@aidd` with `--team`. It writes no `.claude/` files; the repository keeps `.agents/skills/aidd/` and `AGENTS.md` for other agents. Inside Claude Code, the same steps are `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd`. The plugin ships the skill, the MCP server, and the hook, run from its own source (Python 3.11+ on `PATH`).
- **Claude Code, repository files.** `aidd init` links the skill at `.claude/skills/aidd`, adds the edit-time guard as a `PreToolUse` hook in `.claude/settings.json`, and registers `aidd mcp` in `.mcp.json`.
  - The hook and the server start aidd the way init resolved it when it ran: `aidd` when it is on `PATH`, otherwise the running Python with `-m aidd` (and `PYTHONPATH` naming the source, for an install from a checkout). On Windows, init writes each hook for PowerShell and names it (`"shell": "powershell"`), since Claude Code otherwise picks Git Bash or PowerShell by what is installed; the aidd plugin's own hooks need Git Bash there.
  - `aidd doctor` starts both once with a harmless input and fails when either cannot run; `aidd init --agent-hooks` repairs a launcher that does not resolve on this machine.
  - `--team` adds roles in `.claude/agents/`, commands in `.claude/commands/aidd-team/`, and packs and practice skills in `.claude/skills/`. `--no-agent-hooks` skips the hook and the server; `--agent-hooks` forces them.
- **Claude in chat, the desktop app, and Cowork.** The same plugins load there, but not all of them.
  - Chat loads the skill and runs commands as skills, and ignores agents, hooks, and the local `aidd` MCP server. So chat gets the method and none of its enforcement: use it to draft or discuss a Spec, and deliver the change from Claude Code or another agent in the repository, where the hook and the gate apply.
  - Cowork loads agents and hooks, and the MCP server only when the session runs on your computer.
  - The gate on the platform applies either way.
- **A whole team or organization.** Commit `extraKnownMarketplaces` and `enabledPlugins` to the repository's `.claude/settings.json` so every contributor who trusts the folder gets the plugins, or require them on every machine with managed settings ([ENTERPRISE.md](ENTERPRISE.md#12-agent-sessions-under-managed-settings)). The marketplace names `relevance` signals (a `.aidd/config.toml` read, an `aidd` command run), so once an administrator lists `aidd` in `pluginSuggestionMarketplaces`, Claude Code suggests the plugin to a teammate who works in an aidd repository without it. It never installs one by itself.
- **Any other coding agent.** One that reads `AGENTS.md` or `.agents/skills/` is covered by the section and the vendored folder, whether or not it is in the table. For the team, ask the agent to act as one role per session.
- **Other skill folders.** `aidd init --link <dir>` links the skill into one more folder, for example `--link .github/skills`, in addition to `.claude/skills`.

`aidd doctor` reports a vendored skill or a copied link that differs from the CLI's version. `aidd upgrade` lists what it would refresh, and `aidd upgrade --yes` refreshes it. Do not use `aidd init --force` for this: it also overwrites your config. Never edit the vendored folder; put repository-specific guidance in `AGENTS.md`.

## The gate

`aidd init --ci github` (the default) writes the workflows and the PR template; `--ci gitlab` writes the include; `--ci none` writes neither. The gate starts in advisory mode. Going live (the gate's App, its environment, and the branch ruleset), GitLab, and other CI systems are in [PLATFORMS.md](PLATFORMS.md).

## Versions

Pin one version everywhere: the CLI install, the workflow templates (the `@v1.0.0` refs of the reusable gate and the test action), and the vendored skill (`metadata.version`). A tag can be moved; a commit SHA cannot, so pin the SHA of a release for the strongest integrity. `aidd init --ref <sha>` and `aidd upgrade --ref <sha> --yes` write that pin into the CI files. Upgrade them together in one change. That change touches files the gate protects (its own workflows and config), so the gate treats it as major: the strictest review.

- **Before the first release.** Pin a commit SHA ([above](#before-the-first-release)).
- **Upgrade.**
  1. Upgrade the CLI: `uv tool upgrade aidd`, `pipx upgrade aidd`, or the one-line installer with `AIDD_REF=<release>`. For the Claude Code plugins, `claude plugin update aidd@aidd` and `aidd-team@aidd`.
  2. Run `aidd upgrade` in each repository: a dry run that lists what it would change. That is the vendored skill, the team files already installed (adding what the release added, and naming what it retired), the aidd pins in your CI files, and `aidd_version`. Your config, REVIEW.md, AGENTS.md, and your own CI steps stay as they are.
  3. `aidd upgrade --yes` makes the changes. Run `aidd doctor`, and merge them as one change through the gate. The gate reads config from the base branch, so the new version judges only later changes.
- **Roll back.** Revert that PR/MR.
- **The Claude Code plugins.** Both manifests set `version`, so Claude Code updates an installed plugin only when that number changes; a release that forgets to bump it leaves users on the old copy.

What a patch, minor, or major version may change is in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning).

## Remove it

1. Drop `aidd/gate` from the branch ruleset first. The removal touches protected paths, so it would otherwise wait on the gate it removes (an administrator can merge instead).
2. `aidd uninstall` lists everything `aidd init` and `aidd init --team` wrote; `aidd uninstall --yes` removes it, keeps any file you changed since, and says so. Specs stay. On GitLab, `.gitlab/aidd.gitlab-ci.yml` goes with it; remove the `include:` you added to `.gitlab-ci.yml` yourself.
3. Uninstall the gate App and delete the `aidd-gate` environment.
4. Claude Code plugin users: `claude plugin uninstall aidd@aidd` and `claude plugin uninstall aidd-team@aidd`.
5. Remove the CLI: `uv tool uninstall aidd` or `pipx uninstall aidd`; for the installer's venv fallback, delete `~/.local/share/aidd` and `~/.local/bin/aidd`.

Every command and flag: [CLI.md](CLI.md).
