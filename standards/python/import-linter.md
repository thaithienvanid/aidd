---
id: python/import-linter
type: opinionated
fills: [modular-monolith:module-boundaries]
default: true
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: ["**/*.py", pyproject.toml, ".importlinter", setup.cfg]
why: "Import Linter checks import contracts over the whole code base, including indirect imports, and its protected and layers contracts hold the module rules and forbid cycles between modules."
maturity: established
tool:
  name: import-linter
  registry: pypi
  package: import-linter
version_policy: current_stable
checked_version: "2.15"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://pypi.org/pypi/import-linter/json
  quote: "\"version\":\"2.15\""
alternatives: [Tach (Beta), an architecture test in pytest]
status: active
lock_command: [uv, add, --dev, import-linter]
enforced_by:
  - name: boundaries
    command: [uv, run, lint-imports]
---

# Import Linter checks the Python module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Python. Import Linter is under the BSD 2-Clause license, and PyPI marks it "Production/Stable".

## What the team does

- Write the contracts in `.importlinter` at the root, in its INI format, not in `pyproject.toml`. The `module_boundaries` area then treats the file as the violations baseline. List each module's package in `root_packages`; each one must be importable.
- For each module, write a `protected` contract: `protected_modules` is its `internal` package, and `allowed_importers` is the module itself.
- Write one `layers` contract that lists the modules in their dependency order. A lower module that imports a higher one fails, so no cycle between modules can pass. Separate modules on one layer with `|`, so they stay independent.
- Write a `forbidden` contract: no package under `packages/` imports a module or an app.
- Record each known violation in `ignore_imports`, with the reason in a comment. That list only gets shorter.

## What the tests run

One `tests` entry runs `lint-imports` through `uv run`, at the version the project's lock holds. Add it once with `uv add --dev import-linter`. A broken contract fails the change.
