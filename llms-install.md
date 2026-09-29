# Install aidd in a project: a runbook for coding agents

You are a coding agent, and a person asked you to install aidd (the toolkit for AI-Driven Development, AIDD: one loop from intent to production with change control at its core, <https://github.com/thaithienvanid/aidd>) in the repository you are working in. Follow these steps in order, run the commands as written, and stop where a step says the decision is the person's. Report each step's outcome. Do not improvise around a failure: report it.

## 0. Before you start

- Work at the repository root, on a branch you may commit to (create `chore/adopt-aidd` if the default branch is protected).
- The person decides two things; ask both in one message unless they already said:
  - the setup, one of these three (a profile, and whether there is a platform):
    - `solo` on GitHub or GitLab: one person and their agents; needs their own handle, such as `@login`
    - `team` on GitHub or GitLab: several people; needs Approver handles such as `@org/leads`
    - `solo`, local-first: one person with no platform yet; needs the email their git commits use, such as `email:you@example.com`

    The other two profiles, `org` and `regulated`, are set up by hand from [docs/ADOPTION.md](https://github.com/thaithienvanid/aidd/blob/main/docs/ADOPTION.md).
  - Claude Code users only: repository files (default) or plugins (`--claude-plugins`, which installs the `aidd` and `aidd-team` plugins for their user through the `claude` CLI)
- Default when they do not answer: `solo` on the platform the repository's remote points to, with their own handle (`gh api user -q .login` when `gh` is signed in; otherwise ask), repository files, no team. With no remote, use local-first with the email from `git config user.email`.

## 1. Install the CLI (Python 3.11+, no dependencies)

Check `python3 --version` first; 3.11 or later is required.

aidd is pre-release: no `v1.0.0` tag exists yet ([README](https://github.com/thaithienvanid/aidd#readme)). Take the latest commit SHA of `main` (`git ls-remote https://github.com/thaithienvanid/aidd main`), tell the person which SHA you pinned, and use it as `<sha>` below. Then the first of these that applies:

```sh
uv tool install "git+https://github.com/thaithienvanid/aidd@<sha>"      # uv is on PATH
pipx install "git+https://github.com/thaithienvanid/aidd@<sha>"         # pipx is on PATH
curl -fsSL https://raw.githubusercontent.com/thaithienvanid/aidd/<sha>/install.sh | AIDD_REF=<sha> sh   # neither: the installer uses uv, pipx, or a private venv; until aidd is on PyPI it refuses a release tag without AIDD_SHA256
```

Fetch `install.sh` from the commit you pinned, as above, not from `https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh`: `main` can move between the fetch and the install. Verify: `aidd --version` prints the version. If `aidd` is not on `PATH` after the installer's venv fallback, add `~/.local/bin` to `PATH` and say so. Every install path, and pinning after the release: [docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md).

## 2. Adopt it in the repository

First look, and show the person what aidd proposes:

```sh
aidd init --dry-run
```

It writes nothing. It prints the stacks and test commands it found, the sensitive areas, the owners, the CI, and the config it proposes. Show that to the person, and use what they confirm (the test command, the Approvers) in the next command. Then run the one that matches their profile:

```sh
aidd init --profile solo --approvers @login --ref <sha>                                              # solo: the person's own handle
aidd init --profile team --approvers @org/leads --reviewer security=@org/security --test "npm test" --ref <sha>   # team: real handles and the real test command
aidd init --profile solo --approvers email:you@example.com --ci none                                  # local-first: the email their commits use
```

- `--ref <sha>` pins the generated CI files to the same commit as the CLI (local-first writes no CI files, so it needs none). Without it, an installed CLI can only pin `@v1.0.0`, a release tag that does not exist yet ([docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#before-the-first-release)).
- Add `--test "<command>"` with the project's real test command when you know it (`npm test`, `pytest`, `go test ./...`); otherwise leave it out and say that every Spec must bring its own test commands.
- Add `--team` when the person wants the delivery team of agent roles.
- Add `--claude-plugins` only when they chose plugins; it needs the `claude` CLI on `PATH`.
- Add `--ci gitlab` on GitLab, `--ci none` on any other CI (the person will run `aidd gate --context` from their pipeline, see [docs/PLATFORMS.md](https://github.com/thaithienvanid/aidd/blob/main/docs/PLATFORMS.md)) or with no platform at all.
- `aidd init` detects the coding agents the repository uses (their own folders and files in it) and wires each one; add `--harness <agent>` for one the repository does not show yet, such as Claude Code in a fresh repository (init prints the ones installed on this machine that need wiring). It writes `.aidd/config.toml`, `specs/`, `AGENTS.md`, `REVIEW.md`, the vendored skill `.agents/skills/aidd/`, the CI workflows (advisory mode), and the agent-specific files. It never overwrites an existing file; `--force` does, config included, so do not use it on a repository that already has aidd.
- The agents it recognizes, and what it writes for each, are in [the install table](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#your-coding-agent). In short:

<!-- aidd:gen harnesses:summary -->
| Your agent | What `aidd init` does | What you do |
| --- | --- | --- |
| Claude Code | links the skill into `.claude/skills/`, wires the edit-time hook and the `aidd` MCP server; `--team` adds the roles, commands, packs, and practice skills as project agents and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one) | nothing (or use the plugins instead: see the note below the table) |
| Codex, Cursor, Google Antigravity, Devin (Desktop, formerly Windsurf, and the CLI), Cline, Roo Code, Kiro, Amp, OpenCode, JetBrains Junie, Zed, Qwen Code, TraeCode, Augment Code, Factory Droid, DeepSeek Harness, Goose, Grok Build, Mistral Vibe, Google Jules | vendors the skill in `.agents/skills/aidd/` and points `AGENTS.md` at it; `--team` adds a short roles section to `AGENTS.md`, plus native agent files for Codex, Copilot, OpenCode, and Kiro; outside Claude Code the team is advisory | nothing |
| Gemini CLI (`GEMINI.md`), Continue (`.continue/rules/aidd.md`) | the same, plus a pointer in the agent's own instruction file, which init creates | nothing |
| GitHub Copilot (`.github/copilot-instructions.md`), Warp (`WARP.md`), Aider (`CONVENTIONS.md`) | the same, and appends the pointer to the agent's own instruction file only when that file already exists | nothing, except Aider: `read: CONVENTIONS.md` in `.aider.conf.yml` |
| Anything else | `AGENTS.md` and `.agents/skills/aidd/` | tell the agent to read `AGENTS.md` |

Gemini CLI was retired on June 18, 2026 for most users, who moved to the Antigravity CLI; it still serves some paid licenses ([details](docs/INSTALL.md#your-coding-agent)).

Claude Code users who prefer plugins over repository files run `aidd init --claude-plugins`, or in Claude Code `/plugin marketplace add thaithienvanid/aidd` and then `/plugin install aidd@aidd`.
<!-- aidd:end -->

## 3. Verify

```sh
aidd doctor
aidd validate
```

Both must exit 0. Fix only what they name (for example, a missing Approver under `team`), and rerun. If `aidd doctor` warns that no test command is configured, report it; do not invent one.

## 4. Commit

Commit everything `aidd init` wrote, with the trailer aidd expects on agent commits:

```text
chore: adopt aidd

Assisted-by: <your harness>/<your model>
```

Do not push to a protected branch; open a pull request if the branch is protected.

## 5. Hand back to the person

Tell them, in this order:

1. What was installed and detected (the `aidd init` output), and the commit SHA you pinned.
2. On GitHub or GitLab: the gate runs in advisory mode. It reports on `aidd/gate (advisory)` and blocks nothing until they set `mode = "enforce"` in `.aidd/config.toml` (or `mode: enforce` in `.github/workflows/aidd-gate.yml`). The one step only they can do: on GitHub, create the gate App and require the `aidd/gate` status on the protected branch ([docs/PLATFORMS.md](https://github.com/thaithienvanid/aidd/blob/main/docs/PLATFORMS.md#setup)); on GitLab, the pipeline execution policy. To see the loop work first, the local tutorial needs neither ([docs/QUICKSTART.md](https://github.com/thaithienvanid/aidd/blob/main/docs/QUICKSTART.md)).
3. Local-first: there is no platform to set up. They approve at their own terminal with `aidd approve spec specs/<ID>.md` and `aidd approve merge`, and merge a passing branch with `aidd ship` ([docs/ADOPTION.md](https://github.com/thaithienvanid/aidd/blob/main/docs/ADOPTION.md#local-first-no-github-or-gitlab)). Each of those commands shows a six-character one-time code and continues only when the person types it back; they refuse to run without an interactive terminal or in a shell an agent started (`CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT` set), so the person runs them in a terminal they opened themselves.
4. How work flows from now on: before any change, an agent reads `AGENTS.md`, loads the skill, runs `aidd next`, and follows the loop. `aidd change` prints the block a pull request needs; people give the two approvals, Spec approval and Merge approval.

## Never

- Never set the gate's mode to enforce, create the GitHub App, or change branch protection yourself.
- Never edit `.agents/skills/aidd/` (it is vendored; `aidd upgrade --yes` refreshes it) or anything between the `aidd:gen` and `aidd:end` comment markers of a generated block.
- Never approve, merge, or weaken the gate, and never run `aidd approve` or `aidd ship`; the person decides those.
- Never install from any source but `github.com/thaithienvanid/aidd` or, once it is published there, the `aidd` package on PyPI, and never run a script you did not fetch from there.

## Remove it

`aidd uninstall` lists everything init wrote; `aidd uninstall --yes` removes it and keeps Specs and any file the person changed since ([docs/INSTALL.md](https://github.com/thaithienvanid/aidd/blob/main/docs/INSTALL.md#remove-it)).
