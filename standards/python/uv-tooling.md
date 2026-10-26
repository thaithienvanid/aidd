---
id: python/uv-tooling
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [pyproject.toml, uv.lock]
why: "uv resolves, locks, and installs Python dependencies and runs the tools, with one lockfile for every platform, so CI and each machine build the same environment."
reviewed: "2026-10-16"
maturity: established
tool:
  name: uv
  registry: pypi
  package: uv
version_policy: current_stable
checked_version: "0.13.5"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/uv/json
evidence: "\"version\":\"0.13.5\""
pin: "0.13.5"
alternatives: [pip with pip-tools, Poetry]
status: active
enforced_by:
  - name: lock
    command: [uv, lock, --check]
---

# uv installs, locks, and runs the Python tooling

It answers the package-manager choice of `aidd-team:ci-pipeline`.

## What the team does

- Declare every dependency in `pyproject.toml`. Commit `uv.lock`.
- Install with `uv sync --locked` in CI, so a stale lockfile fails the job.
- Run tools through `uv run` or `uvx` with a pinned version, never from whatever is on the runner.
- Set `required-version` under `[tool.uv]`, so every machine runs a compatible uv.

## What the gate runs

One `tests` entry runs `uv lock --check`. A lockfile that no longer matches `pyproject.toml` fails the change.
