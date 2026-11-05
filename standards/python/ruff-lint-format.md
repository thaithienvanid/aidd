---
id: python/ruff-lint-format
type: opinionated
fills: [ci-pipeline:linter, ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.py", pyproject.toml, ruff.toml]
why: "One fast tool lints and formats Python, with one configuration in pyproject.toml, so CI, the pre-commit hook, and every editor agree."
maturity: established
tool:
  name: ruff
  registry: pypi
  package: ruff
version_policy: current_stable
checked_version: "0.17.1"
checked: "2026-10-20"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/ruff/json
evidence: "\"version\":\"0.17.1\""
alternatives: [flake8 with Black, pylint]
status: active
lock_command: [uv, add, --dev, ruff]
enforced_by:
  - name: lint
    command: [uv, run, ruff, check, "."]
  - name: format
    command: [uv, run, ruff, format, --check, "."]
---

# Ruff lints and formats the Python code

It answers the linter and formatter choices of `aidd-team:ci-pipeline`.

## What the team does

- Configure Ruff under `[tool.ruff]` in `pyproject.toml`, once for the whole repository.
- Select rule sets on purpose, such as `E`, `F`, `W`, `I`, `B`, and `UP`. Write the reason beside each ignored rule.
- Run the project's locked Ruff in the pre-commit hook too.
- Format before you commit. A reviewer never asks for a layout change by hand.

## What the tests run

Two `tests` entries run `ruff check` and `ruff format --check` through `uv run`, at the version the project's lock holds. Add it once with `uv add --dev ruff`. A finding fails the change.
