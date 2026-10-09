+++
id = "python/pydantic-validation"
type = "opinionated"
fills = ["apis-and-services:validation-library"]
default = true
implements = "apis-and-services:Schema conformance"
roles = ["developer", "architect", "reviewer"]
when_changed = ["**/*.py", "pyproject.toml"]
why = "Pydantic validates data against type-annotated models and writes their JSON Schema, so one model is the run-time check, the static type, and the contract's schema."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "pydantic", registry = "pypi", package = "pydantic" }
version_policy = "current_major"
checked_version = "2.13.5"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pypi.org/pypi/pydantic/json"
evidence = '"version":"2.13.5"'
alternatives = ["msgspec", "attrs with cattrs", "marshmallow"]
status = "active"
enforced_by = [
  { name = "major", command = ["uv", "run", "python", "-c", "import importlib.metadata as m, sys; sys.exit(not m.version('pydantic').startswith('2.'))"] },
]
+++

# Pydantic validates input at the boundary

It answers the validation-library choice of `aidd-team:apis-and-services`.

## What the team does

- Model every request, message, and file the service reads as a `BaseModel`, and validate it where it enters; pass on the model, not the raw dict.
- Forbid unknown fields at the boundary (`model_config = ConfigDict(extra="forbid")`).
- Use constrained types and `Field` limits for lengths, ranges, and formats, so the schema states them.
- Read settings with `pydantic-settings`, so a missing or malformed setting stops the process at startup.
- Turn on the `pydantic.mypy` plugin, so the type checker reads the models as Pydantic builds them.

## What the gate runs

One `[[tests]]` entry checks that the environment resolves the major release this standard was checked at, so an upgrade is a reviewed change.
