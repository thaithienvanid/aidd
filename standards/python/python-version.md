---
id: python/python-version
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [".python-version", pyproject.toml, ".github/workflows/**", Dockerfile]
why: "The current stable CPython gets bug fixes for two years and security fixes for five, and pinning it in one file that uv reads gives development, CI, and production the same interpreter."
reviewed: "2026-10-16"
maturity: established
tool:
  name: python
  registry: python.org
  package: cpython
version_policy: current_stable
checked_version: "3.14.8"
checked: "2026-10-07"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.python.org/downloads/source/
evidence: Latest Python 3 Release - Python 3.14.8
alternatives: [the oldest Python release still in bugfix support, PyPy]
status: active
enforced_by:
  - name: runtime
    command:
      - uv
      - run
      - python
      - -c
      - "import pathlib, sys; want = pathlib.Path('.python-version').read_text().split()[0]; sys.exit(not sys.version.startswith(want))"
---

# The project runs on the current stable Python

It answers the language-version choice of `aidd-team:ci-pipeline`.

## What the team does

- Write the minor release in `.python-version` with `uv python pin`, the one file uv, CI, and each developer read.
- Set `requires-python` in `pyproject.toml` to admit that release, and match Ruff's `target-version` and mypy's `python_version` to it.
- Build the container image from the same minor release.
- Move to a new minor release once its first bugfix release is out and the dependencies support it, in a change of its own.
- A library keeps a wider `requires-python` floor and tests each supported release in CI.

## What the gate runs

One `tests` entry compares the interpreter `uv run` starts with `.python-version`. Another release fails the change.
