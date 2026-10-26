---
id: python/mypy-typing
type: opinionated
fills: [ci-pipeline:type-checker]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.py", "**/*.pyi", pyproject.toml]
why: "mypy is the reference type checker for Python's typing rules, and it runs in the project's own environment, so it sees the real dependencies."
reviewed: "2026-10-22"
maturity: established
tool:
  name: mypy
  registry: pypi
  package: mypy
version_policy: current_stable
checked_version: "2.4.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/mypy/json
evidence: "\"version\":\"2.4.0\""
pin: "2.4.0"
alternatives: [pyright, pyrefly, "ty (beta, emerging)"]
status: active
enforced_by:
  - name: types
    command: [uv, run, --with, mypy==2.4.0, mypy]
---

# mypy checks the Python types

It answers the type-checker choice of `aidd-team:ci-pipeline`.

## What the team does

- Configure mypy under `[tool.mypy]` in `pyproject.toml`. Name the packages to check in `files`.
- Set `check_untyped_defs = true` and `warn_unused_ignores = true` at the least. Turn on `strict` for new packages.
- Give every public function its parameter and return types.
- Write the error code and the reason on each `# type: ignore[code]`. A bare `# type: ignore` is a review finding.

## What the gate runs

One `tests` entry runs mypy inside the project's environment, so it sees the real dependencies. An error fails the change.
