---
id: python/diff-cover
type: opinionated
fills: [test-design:coverage-tool]
default: true
implements: test-design:Review
roles: [developer, verifier, reviewer]
when_changed: ["**/*.py", pyproject.toml, ".coveragerc", "setup.cfg"]
why: "coverage.py measures which lines the tests ran, and diff-cover holds the lines a change adds or touches to a floor of their own, so new code is covered without first raising the whole project's number."
reviewed: "2026-10-28"
maturity: established
tool:
  name: diff-cover
  registry: pypi
  package: diff-cover
version_policy: current_stable
checked_version: "11.0.0"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "10.6.0"
cooldown_until: "2026-11-03"
source: https://raw.githubusercontent.com/Bachmann1234/diff_cover/main/README.rst
evidence: Automatically find diff lines that need test coverage.
alternatives: [the coverage tool's floor alone, no coverage floor]
status: active
enforced_by:
  - name: coverage
    command: [sh, -c, "coverage run -m pytest && coverage report && coverage xml && diff-cover coverage.xml --compare-branch=\"${COVERAGE_BASE:-origin/main}\" --fail-under=80"]
---

# coverage.py and diff-cover hold coverage where the code changes

It answers the coverage-tool choice of `aidd-team:test-design` for Python. coverage.py is under the Apache License 2.0, and diff-cover is under the Apache License 2.0 too. diff-cover 11.0.0 came out on 2026-10-27, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 10.6.0 until `cooldown_until`.

## What the team does

- Set `fail_under` under `[tool.coverage.report]` in `pyproject.toml` to today's line coverage when the check is added, and raise it as coverage rises. A Spec freezes it as `pyproject.toml#tool.coverage`, so the floor is a ratchet nobody lowers unseen.
- Run `diff-cover` against the base branch with `--fail-under=80`, so the lines a change adds or touches are covered, whatever the whole project's number is.
- Measure branch coverage too (`branch = true` under `[tool.coverage.run]`), and leave out only generated code, with the reason beside the pattern.
- Read a coverage drop as a question for the review, not as proof: the Mutation run says how strong the tests are.
