---
id: python/pytest-tests
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: test-design:Flake check
roles: [developer, verifier, reviewer]
when_changed: ["**/*.py", pyproject.toml, conftest.py, "**/conftest.py"]
why: "pytest is the common Python test runner: plain assert statements, fixtures for setup, and a plugin ecosystem for async code, coverage, and property tests."
reviewed: "2026-10-16"
maturity: established
tool:
  name: pytest
  registry: pypi
  package: pytest
version_policy: current_stable
checked_version: "9.1.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/pytest/json
evidence: "\"version\":\"9.1.1\""
pin: "9.1.1"
alternatives: [unittest]
status: active
enforced_by:
  - name: unit
    command: [uv, run, --with, pytest==9.1.1, pytest]
---

# pytest runs the Python tests

It answers the test-runner choice of `aidd-team:ci-pipeline`.

## What the team does

- Configure pytest under `[tool.pytest.ini_options]` in `pyproject.toml`, with `testpaths` and `--strict-markers`.
- Put shared setup in fixtures in `conftest.py`, scoped as narrowly as the test allows. A test never depends on another test's leftovers.
- Turn warnings into errors (`filterwarnings = ["error"]`) and allow each known one by name.
- Mark a slow or external test with a registered marker, so the fast suite stays fast.
- Install no rerun-on-failure plugin. For the Flake check of `aidd-team:test-design`, rerun a new test with `pytest-repeat` (`--count`).
- Never commit a skip without a reason and an issue link.

## What the gate runs

One `tests` entry runs the pinned pytest inside the project's environment. A failing test fails the change.
