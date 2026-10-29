---
id: tooling/mise
type: opinionated
fills: [ci-pipeline:toolchain-manager]
default: true
implements: ci-pipeline:Dev/prod parity
roles: [developer, sre, reviewer]
when_changed: [mise.toml, mise.lock, "mise.*.toml", "mise.*.lock", ".github/workflows/**"]
why: "One file pins every runtime and command-line tool a repository needs, and a lockfile with checksums makes each machine and each CI job install the same binaries."
reviewed: "2026-10-22"
maturity: established
tool:
  name: mise
  registry: github
  package: jdx/mise
version_policy: current_stable
checked_version: "2026.10.17"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.thoughtworks.com/radar/tools/mise
evidence: "For teams looking to standardize their developer environment setup, mise has become our recommended default."
pin: "2026.10.14"
cooldown_until: "2026-10-28"
alternatives: [the language's own version file, asdf, a dev container image]
status: active
enforced_by:
  - name: locked
    command: [mise, install, --locked]
---

# mise installs the pinned toolchain

It answers the toolchain-manager choice of `aidd-team:ci-pipeline`. License: MIT for mise and for `jdx/mise-action`. Thoughtworks moved mise to Adopt in Technology Radar volume 34 (April 2026).

mise 2026.10.17 came out on 2026-10-21, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 2026.10.14 until `cooldown_until`.

## What the team does

- List each runtime and tool in `mise.toml` under `[tools]` at an exact version, such as `node = "24.11.0"`, never `latest` or a prefix. That file is also where the language-version choice is pinned.
- Run `mise lock` and keep `mise.lock` in the repository next to `mise.toml`. It records each version with its download URL and checksum.
- Set `lockfile = true` under `[settings]`, so `mise use` and `mise upgrade` keep the lockfile current.
- Keep the package manager's lockfile too: `mise.lock` covers tools, not the application's dependencies.
- In CI, use `jdx/mise-action` pinned by commit, `08ae2a091c038e1e05ec6f5115dc5c69d5a2a6b8` for v5.1.2, with `version` set to `pin` and `install_args: --locked`. Its v5.2 releases were inside the cooldown when this file was checked.
- Ignore `mise.local.toml` and `mise.local.lock`, which hold one person's own tools.

## What the gate runs

One `tests` entry runs `mise install --locked`. Locked mode installs only what `mise.lock` records, so it fails when a tool in `mise.toml` has no entry there for the runner's platform.
