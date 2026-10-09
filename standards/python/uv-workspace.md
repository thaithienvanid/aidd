+++
id = "python/uv-workspace"
type = "opinionated"
fills = ["ci-pipeline:workspace"]
default = true
implements = "ci-pipeline:Dependencies declared and locked"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["pyproject.toml", "**/pyproject.toml", "uv.lock"]
why = "A uv workspace gives each module its own pyproject.toml and resolves them all into one lockfile, so every module runs on one consistent set of dependencies."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://docs.astral.sh/uv/concepts/projects/workspaces/"
evidence = "In a workspace, each package defines its own pyproject.toml, but the workspace shares a single lockfile, ensuring that the workspace operates with a consistent set of dependencies."
alternatives = ["Pants", "one package with a folder per module"]
status = "active"
enforced_by = [
  { name = "sync", command = ["uv", "sync", "--locked", "--all-packages"] },
]
+++

# A uv workspace holds the Python apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for Python. Its tool is uv, which `python/uv-tooling` pins. uv is MIT or Apache-2.0, at the user's choice.

## What the team does

- Declare the members in the root `pyproject.toml`: `[tool.uv.workspace] members = ["apps/*", "modules/*", "packages/*"]`.
- Give each module its own `pyproject.toml`. Declare a sibling it imports in `dependencies`, with `{ workspace = true }` under `[tool.uv.sources]`.
- Keep one `requires-python` range for all members. uv takes the intersection of the ranges.
- Run a command in one member with `uv run --package <name>`.

## What the gate runs

One `[[tests]]` entry installs every member from the lockfile with `--locked`. A lockfile that is missing or out of date fails the change, and so does a member that does not install.
