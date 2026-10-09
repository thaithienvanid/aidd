# Security policy

## Report a vulnerability

Use GitHub's private vulnerability reporting on this repository ("Security" → "Report a vulnerability", or <https://github.com/thaithienvanid/aidd/security/advisories/new>). Do not open a public issue. Expect an acknowledgement within 3 business days, and a fix or mitigation plan within 30 days.

While this repository is private, GitHub offers no private vulnerability reporting on it. Contact the maintainer through a contact option on their GitHub profile, <https://github.com/thaithienvanid>, and ask only for a private channel. Share the details once you have one. The same times apply from that first contact.

## In scope

- Any way for a change to reach a protected branch while `aidd/gate` should have failed or stayed pending. That includes forged evidence, approval replay, separation-of-duties bypass, protected-path evasion, config tampering, and trusting PR-controlled code in the gate job.
- Glob, schema, or TOML parsing bugs that change a decision.
- Leaks of tokens or secrets through gate output, events, or artifacts.
- Template workflows that grant more permissions than their job needs.

## Trust model

[METHOD.md §14](docs/METHOD.md#14-platform-bindings-and-trust) owns the full model; this is a summary. Known limits are in [RATIONALE.md](docs/RATIONALE.md#known-limits-in-100).

- **The gate job is trusted.** It runs from the default branch and reads the PR/MR head as git objects only. It runs Policy from the base branch without tokens, and never executes the change's code.
- **The status source must be pinned** to a dedicated GitHub App. Without it, anyone with write access can post `aidd/gate`, and the gate is advisory. It is also advisory without `mode = "enforce"` or a rule that requires the check, which a private repository on GitHub Free cannot have ([what holds without them](docs/PLATFORMS.md#what-holds-without-the-full-setup)).
- **The gate runs aidd from the reusable workflow's own commit**, with no package build, and keeps the App key only in the `aidd-gate` environment.
- **The test job is untrusted.** The platform token is present in the job and stripped from every test command. aidd rejects stale, missing, substituted, self-reported, and cross-PR evidence. But it cannot make hostile test code honest: a malicious change to tests, build scripts, or dependencies can make its own tests lie. The Spec approval and Merge approval human reviews are the control for that.
- **The config is read from the base branch**, and changing it is a protected, major change.
- **The guard trusts the repository's Claude Code settings.** A repository's committed Claude Code settings can set environment variables and add their own hooks. So they can weaken the guard. The guard runs git from a fixed system path and passes it only a short list of variables, such as `HOME` and `LANG`. So a `PATH`, `GIT_*`, or `LD_PRELOAD` setting does not reach that git. It also turns off `core.fsmonitor`, git hooks, and the filter, diff, and merge driver programs in the repository's own git config. Your global and system git config still apply. The plugin's launchers do not use `[`, which an exported function can replace. These defend against what reaches the session through the repository's committed content and the ordinary commands an agent runs. They do not defend against a local writer that changes `.git/config`, `HOME`, or the git programs. They also do not defend against code that an agent runs through the shell, which it can already do. For both, `aidd/gate` in CI, on a clean checkout, is the control. Trust those settings as you trust the repository's code: `aidd/gate` still decides on the diff.
- **The guard reads only the writes it knows.** It judges each write in the repository that holds the target, whatever the session's folder. It reads a path as the kernel does, following each symbolic link before the `..` after it. It puts a path into its case on disk, and treats a hard link's source as written. It denies a write to a file with more than one hard link wherever it holds the writer. A test runs each case under real bash and checks that the guard denies exactly the writes bash makes. For a writer it holds (a role, a helper, or the lead under `delegate`), it denies a command that runs code it cannot read:
  - a command substitution or backticks where a command starts;
  - a shell fed by stdin: a here-string, a here-document, an input file, or a pipe (`... | bash`);
  - code bash runs later or from elsewhere: `trap` with a command, and `source` or `.` of a file;
  - a program that runs commands: `xargs`, `parallel`, and `find -exec`, `-execdir`, `-ok`, or `-okdir`.

  It also denies a write target with a brace expansion, such as `src/{a,b}.py`. These are its known limits, and `aidd/gate` in CI decides on the diff:
  - a program that writes by itself, such as an interpreter (`python -c`), a build tool, or a package manager;
  - a writer outside the documented list, such as `rsync`, `curl -o`, or `git checkout -- path`;
  - a command that the guard's parser reads differently from bash;
  - an MCP server whose tools the hook matcher never sends, or whose tools name a path under a key the guard does not read;
  - a hard link to a repository file, written from a session whose folder is outside every repository;
  - a local writer of `.git/`, such as one that moves the autopilot lease away or edits the files next to it.
- **GitLab** is only as trustworthy as the pipeline execution policy that injects the gate. Fork MR pipelines and merge train pipelines fail closed.
- **An approval line an App posts for a person never counts**, since whoever holds the App's user token, an agent included, could have posted it.

## Data handling

The gate reads the change through the platform's API and writes a status, a record, and an event, and it carries no telemetry. At run time the gate reaches the platform's API and the artifact storage that API redirects evidence downloads to. It fetches the change's commits from the platform's git server. Beyond those, it reaches only what you configure: an `extends` parent or org preset fetched by URL, and the attestation endpoints when `evidence.signer_workflow` is set ([the full egress list](docs/PLATFORMS.md#github-enterprise-server-and-restricted-actions)). What it reads, writes, and keeps, and for how long, is listed in [docs/ENTERPRISE.md](docs/ENTERPRISE.md#7-data-handling-and-privacy).

Outside the gate, these commands reach the network, and only when you run them:

- Any command that loads a config whose `extends` names a URL fetches that URL, `aidd validate` among them. The guard hook and the session hooks never do.
- `aidd init` and `aidd upgrade` can ask github.com for the commit of the aidd release tag with `git ls-remote`. They wait 5 seconds at most and work without an answer.
- `aidd doctor` asks github.com with `git ls-remote` whether the aidd commit that the CI files pin exists. With a GitHub token (`GH_TOKEN`, `GITHUB_TOKEN`, or `gh auth token`), it also reads the repository and its branch rules from the GitHub API. `aidd assess`, `aidd list`, `aidd autopilot next`, `aidd digest`, and the MCP `assess` tool run the same checks.
- `aidd autopilot next` may read the approval lines and reviews of the branch's open pull request from the platform's API, as the gate does. It needs a GitHub token for that. It also fetches the pull request's head and base from the platform's git server into `refs/aidd/*` in your local repository. It trusts only the repository that `[project] repo` pins on the base branch, because `origin` is local git config that an agent can change. It counts an approval only for the local head and the local Spec hash. Offline (`AIDD_OFFLINE=1`), without a token, or without a pinned repository, it asks a person instead.
- `aidd import issues --github` reads the open issues of the repository you name from the GitHub API.
- `aidd eval standards --online` fetches the evidence URL of each entry in the standards registry. It also asks the release feed of each library standard's tool for its newest release: PyPI, npm, crates.io, Maven Central, NuGet, the Go module proxy, or GitHub releases. For a language version, it asks the official toolchain feed: go.dev, nodejs.org, the .NET release index at builds.dotnet.microsoft.com, Adoptium at api.adoptium.net, or python.org at www.python.org. The default check is offline.
- `aidd record verify --online` and `aidd record verify --bundle` run `gh attestation verify`, which reaches the attestation endpoints.

`AIDD_OFFLINE=1` turns off the `git ls-remote` lookup of `aidd init` and `aidd upgrade`, and the network checks of `aidd doctor` and of the commands that run them. The session hooks turn off the same checks for themselves. `AIDD_OFFLINE=1` does not stop an `extends` fetch, or a command whose flag asks for the network, such as `--online` or `--github`.

Autopilot (experimental) writes outside the working tree, in the git directory (`$(git rev-parse --git-common-dir)/aidd/`). `aidd autopilot` writes `lease.json`, `journal.jsonl`, and the run events in `events.jsonl`. These files hold session ids, scopes, your git email, times, step codes and results, the heads they ran on, and the token counts, costs, and words a note records. Nothing sends them anywhere, and git never commits them. aidd commands write them, refuse a symbolic link in their place, and keep only the last lines of each journal file. But an agent with a shell can edit them. So the autopilot limits (the timebox, and the token and cost caps) guide a cooperating autopilot, and its spend is self-reported. The person and the gate stay the controls: a journal line never counts as an approval, and a person's outcome never comes from it. A person can remove the folder at any time; the next run starts without a lease or a journal. Autopilot's checks resist edits to the working tree and to the branch's content. They do not resist a local writer that rewrites git refs or `.git/config`, such as one that moves the local base branch; the gate in CI, on a clean checkout, stays the control for merges.

The commands that a project configures, such as its `[[tests]]` commands, `uv run`, or `npx`, belong to the project. They can fetch packages, and aidd does not control them.

## Supported versions

| Version | Supported | Security fixes |
| --- | --- | --- |
| 1.x, latest minor | yes | yes |
| 1.x, older minors | no | no; upgrade to the latest minor |

Nothing is released yet: 1.0.0 will be the first version. There is no fixed release cadence, so "supported" means the latest minor of the latest major. An older minor keeps working — the gate is versioned through `aidd_version` — but it receives no fixes. Supported Pythons are 3.11 through 3.14, the versions in the classifiers of `pyproject.toml`, each tested on Linux, macOS, and Windows. CI also tests 3.15 as a prerelease; it is not supported until it is released and listed. A Python that leaves the CI matrix leaves support here too.
