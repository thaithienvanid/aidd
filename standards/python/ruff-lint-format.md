+++
id = "python/ruff-lint-format"
type = "opinionated"
fills = ["ci-pipeline:linter", "ci-pipeline:formatter"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.py", "pyproject.toml", "ruff.toml"]
why = "One fast tool lints and formats Python, with one configuration in pyproject.toml, so CI, the pre-commit hook, and every editor agree."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "ruff", registry = "pypi", package = "ruff" }
version_policy = "current_stable"
checked_version = "0.16.10"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pypi.org/pypi/ruff/json"
evidence = '"version":"0.16.10"'
pin = "0.16.10"
alternatives = ["flake8 with Black", "pylint"]
status = "active"
enforced_by = [
  { name = "lint", command = ["uvx", "ruff@0.16.10", "check", "."] },
  { name = "format", command = ["uvx", "ruff@0.16.10", "format", "--check", "."] },
]
+++

# Ruff lints and formats the Python code

It answers the linter and formatter choices of `aidd-team:ci-pipeline`.

## What the team does

- Configure Ruff under `[tool.ruff]` in `pyproject.toml`, once for the whole repository.
- Select rule sets on purpose, such as `E`, `F`, `W`, `I`, `B`, and `UP`. Write the reason beside each ignored rule.
- Run the pinned Ruff in the pre-commit hook too.
- Format before you commit. A reviewer never asks for a layout change by hand.

## What the gate runs

Two `[[tests]]` entries: `ruff check` and `ruff format --check`. A finding fails the change.
