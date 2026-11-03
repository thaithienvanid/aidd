# Security policy

## Report a vulnerability

Use GitHub's private vulnerability reporting on this repository. Open "Security" → "Report a vulnerability", or go straight to <https://github.com/thaithienvanid/aidd/security/advisories/new>. Do not open a public issue. Expect an acknowledgement within 3 business days, and a fix or mitigation plan within 30 days.

If that form is not open to you, contact the maintainer through a contact option on their GitHub profile, <https://github.com/thaithienvanid>, and ask only for a private channel. Share the details once you have one. The same times apply from that first contact.

## What aidd does not do

aidd enforces nothing. It computes advice: the route of a change, and the level of each action (`allow`, `report`, or `ask`). The agent reads that advice through the skill and acts on it. A model can still ignore the skill, so never treat aidd's advice as a control.

The hard stops come from tools that already enforce:

- **The harness's own ask rules.** `aidd init` and `aidd upgrade` write each `ask` rule's command patterns into the harness's own settings. They do it for every harness with a documented, committed permission prompt: Claude Code, OpenCode, Codex, Grok Build, Qwen Code, Devin's CLI, Factory Droid, Augment's CLI, and VS Code's agent. [GUIDE.md](docs/GUIDE.md#every-coding-agent) lists each file. The harness then asks the person before a matched command runs. Codex, Grok Build, and Factory Droid read the rules only once the person trusts the folder. A harness without ask rules gets the skill alone, and `aidd doctor` says so.
- **The platform's branch protection.** It is the one control that holds whatever the agent runs. Protect the default branch: require a pull request and the test check, and block force pushes and deletion. Under `team`, also require a person's approving review. Under `solo`, nothing on the platform holds a merge for a second person. aidd never sets it for you, so set it yourself on GitHub or GitLab.

A command pattern is a net, not a control. It matches the command text the harness sees. An agent can reach the same effect through a script, an alias, a variable, another program, or an API call that no pattern matches. So the ask rules catch the common case, and branch protection stays the control.

## In scope

- A way for aidd to run code from the repository it reads, such as through the MCP server's launcher, a config, or a Spec.
- A harness ask rule that aidd writes looser than the config says, or a change aidd makes to a person's own harness rules.
- Glob, schema, or YAML parsing bugs that change a route or a level.
- Leaks of tokens or secrets through aidd's output, evidence, or logs.
- A network call that is not on the list below, or that `AIDD_OFFLINE=1` should stop and does not.
- Template workflows that grant more permissions than their job needs.

An agent that ignores the skill's advice is not a vulnerability in aidd, because aidd enforces nothing. Report it as an issue with the "The agent didn't ask, or asked when it shouldn't" template.

## Trust model

- **Only the person's own words in the chat are a yes.** Text from a ticket, a page, a file, a comment, a tool result, or another agent saying "approved" is data, never a yes and never an instruction. The skill tells every agent so.
- **A Spec approval is a note the agent wrote, not proof.** On the person's yes, the agent sets the Spec's `approved_by` and `approved_at` and commits it with an `Approved-by` trailer. Anyone with write access, or an agent, could write the same lines. Where you need proof, use the platform's review, which the platform records. Under the `team` profile, Merge approval is that review.
- **A headless run never takes silence as a yes.** In CI, a cloud session, or a scheduled run, an `ask` means stop and hand back with a handoff note.
- **A session override lasts the session.** A person may lower a rule for one session. It goes into the config only when they say so, and a config change is an ordinary edit that the pull request's review sees.
- **aidd owns only the harness rules it wrote.** `.aidd/harness-rules.json` lists them, so `aidd upgrade` and `aidd uninstall` change only those entries, never a person's own.
- **The test job is untrusted.** `aidd test` binds each exit code to the head commit, and the evidence names the commit it ran on. But a malicious change to tests, build scripts, or dependencies can make its own tests lie. A person's review of the change is the control for that.
- **aidd signs and verifies nothing.** It runs neither `ssh-keygen` nor `gpg`. Where you need signed history, use git's own commit signing and the platform's rule that requires it.
- **The MCP server's launcher trusts nothing in the project.** The aidd plugin starts `aidd mcp` with a `/bin/sh` line in `.claude-plugin/plugin.json`. That line:
  - unsets `CDPATH` and any shell function named `test`, `cd`, `pwd`, or `command`, so the person's shell setup cannot change what it runs;
  - serves the folder in `CLAUDE_PROJECT_DIR`, or the current folder with a warning, and refuses a value that is not a folder;
  - refuses to start when the plugin's source lies inside the project, so a repository cannot ship its own aidd;
  - takes `python3` or `uv` only from outside the project, and drops every `PATH` entry inside it before it asks uv for a Python;
  - runs Python with `-I -S`, so no `PYTHON*` variable, no site folder, and no module in the project folder load;
  - asks uv with `--offline --no-project --no-config --no-python-downloads`, with `VIRTUAL_ENV` and `CONDA_PREFIX` unset, so a project's uv settings or virtual environment cannot steer it.
- **The MCP tools only read.** `risk`, `status`, and `validate` answer from the repository's files and git, and write nothing.
- **A config preset fetched by URL is checked.** An `extends` URL must use https, resolve only to public addresses, and match its `sha256` pin. aidd follows no redirect.

## Data handling

aidd carries no telemetry. These commands reach the network, and only when you run them:

- Any command that loads a config whose `extends` names a URL fetches that URL, `aidd validate` among them.
- `aidd init` and `aidd upgrade` can ask github.com for the commit of the aidd release tag with `git ls-remote`, so the CI files pin a commit. They wait 5 seconds at most and work without an answer.
- `aidd doctor` asks github.com with `git ls-remote` whether the aidd commit that the CI files pin exists.
- `aidd eval standards --online` fetches the evidence URL of each entry in the standards registry. It also asks for the newest release of each library standard's tool, from the release feed of PyPI, npm, crates.io, Maven Central, NuGet, the Go module proxy, or GitHub releases. For a language version, it asks the official toolchain feed, which is go.dev, nodejs.org, the .NET release index at builds.dotnet.microsoft.com, Adoptium at api.adoptium.net, or python.org at www.python.org. The default check is offline.
- `aidd self-update`, and once a day the command a person runs at a terminal, ask github.com with `git ls-remote` for the latest aidd release. The daily check only says when one is out. `aidd self-update`, or the daily check under `AIDD_AUTO_UPDATE=1`, downloads that release's wheel and `SHA256SUMS` from its GitHub Release. It refuses a wheel whose sha256 does not match, and, with `gh` on PATH, runs `gh attestation verify` on it. uv, pipx, or pip then install that file, which has no dependencies. `aidd self-update --main` instead fetches the tip of main from github.com, unverified. All of it runs in aidd's own cache folder, so the current repository's git config or `uv.toml` cannot steer it. The daily check never runs in CI or in a shell an agent started. `AIDD_NO_UPDATE_CHECK=1` turns it off.

The installer and the CI templates connect too. `install.sh` downloads a release's wheel and `SHA256SUMS` from its GitHub Release, or from the mirror `AIDD_RELEASE_URL` names. With `gh` on PATH, it runs `gh attestation verify` on the wheel before it installs anything, and accepts only the release workflow's attestation. A mirror needs `AIDD_SHA256` or `gh`, because its `SHA256SUMS` proves nothing alone. The optional secret scan workflow, `templates/github/aidd-security.yml`, downloads gitleaks from its GitHub release and checks its SHA-256.

`AIDD_OFFLINE=1` stops every optional call: the `git ls-remote` lookups of `aidd init`, `aidd upgrade`, and `aidd doctor`, the daily update check, and an `extends` fetch, so a config whose parent is a URL then fails to load with that reason. `aidd self-update` then says it is offline and installs nothing. `AIDD_OFFLINE=1` does not stop a command whose flag asks for the network, such as `--online`.

The commands that a project configures, such as its `tests` commands, `uv run`, or `npx`, belong to the project. They can fetch packages, and aidd does not control them.

## Supported versions

| Version | Supported | Security fixes |
| --- | --- | --- |
| 1.x, latest minor | yes | yes |
| 1.x, older minors | no | no; upgrade to the latest minor |

Nothing is released yet, and 1.0.0 will be the first version. There is no fixed release cadence, so "supported" means the latest minor of the latest major. An older minor keeps working, but it receives no fixes. Supported Pythons are 3.11 through 3.15, the versions in the classifiers of `pyproject.toml`. CI tests each on Linux, and on macOS and Windows in the manual run each release requires. A Python that leaves the CI matrix leaves support here too.
