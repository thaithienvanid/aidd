---
id: python/tach
type: opinionated
fills: [modular-monolith:module-boundaries]
default: false
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: ["**/*.py", pyproject.toml, tach.toml]
why: "Tach is built for a modular Python code base: each module declares the modules it depends on and its public interface, and a check fails on any import or cycle that the declarations do not allow."
reviewed: "2026-10-16"
maturity: emerging
tool:
  name: tach
  registry: pypi
  package: tach
version_policy: current_stable
checked_version: "0.35.3"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/tach/json
evidence: "\"Development Status :: 4 - Beta\""
pin: "0.35.3"
alternatives: [Import Linter]
status: active
enforced_by:
  - name: boundaries
    command: [uv, run, --with, tach==0.35.3, tach, check]
---

# Tach checks the Python module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Python. Tach is MIT. `python/import-linter` stays the default.

Tach is in Beta: PyPI marks it "4 - Beta", and it is still before 1.0. Its repository moved to the `tach-org` organization on GitHub. Review this choice every 90 days.

## What the team does

- Write `tach.toml` at the root. Declare each module once, with `depends_on` that lists the modules it may import. Never omit `depends_on`: without it, a module may import any other.
- Give each module a public interface: `expose` names its `api` package. An import from another module that goes around it fails.
- Set `forbid_circular_dependencies: true`, so a cycle between modules fails. Its default is `false`.
- Mark a known violation only with a `tach-ignore(<reason>)` comment. Count the comments each week: the count only goes down.

## What the gate runs

One `tests` entry runs `tach check` at `pin`. An undeclared import, an import that skips a public interface, or a cycle fails the change.
