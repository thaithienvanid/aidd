---
id: python/pants
type: opinionated
fills: [ci-pipeline:workspace]
default: false
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed:
  - pants.toml
  - "**/BUILD"
  - "**/BUILD.pants"
  - "**/*.py"
  - "**/*.lock"
  - pyproject.toml
  - "**/pyproject.toml"
why: "Pants infers the dependencies of each file, runs only the work a change needs with a cache, and covers Python, Go, Java, and Shell in one build, which helps a large polyglot repository."
reviewed: "2026-10-16"
maturity: established
tool:
  name: pants
  registry: github
  package: pantsbuild/pants
version_policy: current_stable
checked_version: "2.33.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.pantsbuild.org/stable/docs/introduction/welcome-to-pants
evidence: "Pants is useful for repos of all sizes, but is particularly valuable for those containing multiple distinct but interdependent pieces."
pin: "2.33.1"
alternatives: [a uv workspace]
status: active
enforced_by:
  - name: ci
    command: [pants, lint, check, test, "::"]
---

# Pants holds a large polyglot repository

It answers the workspace choice of `aidd-team:ci-pipeline` for a large repository in Python and other languages. Pants is under the Apache License 2.0. `python/uv-workspace` stays the default.

## What the team does

- Install the `pants` launcher, and set `pants_version` in `pants.toml` to `pin`. Read the version from GitHub releases: PyPI does not list the current ones.
- Turn on the backends the repository needs, such as `pants.backend.python`.
- Let `pants tailor` write the `BUILD` files. Review each one as code.
- Generate the lockfiles with `pants generate-lockfiles`, and commit them.
- Keep the linters and the test runner of the other standards. Pants runs them as its own goals.

## What the gate runs

One `tests` entry runs the `lint`, `check`, and `test` goals over every target (`::`). A finding, a type error, or a failing test fails the change. A long pipeline can add `--changed-since` with the base commit.
