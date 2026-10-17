---
id: python/fastapi-api
type: opinionated
fills: [apis-and-services:api-framework]
default: true
implements: apis-and-services:Breaking-change diff
roles: [developer, architect, reviewer]
when_changed: ["**/*.py", pyproject.toml, openapi.yaml, openapi.json]
why: "FastAPI builds the OpenAPI document from the typed route signatures and their Pydantic models, so the contract, the validation, and the code come from one definition."
reviewed: "2026-10-16"
maturity: established
tool:
  name: fastapi
  registry: pypi
  package: fastapi
version_policy: current_stable
checked_version: "0.142.2"
checked: "2026-10-07"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/fastapi/json
evidence: "\"version\":\"0.142.2\""
alternatives: [Litestar, Django REST framework, Flask]
status: active
enforced_by:
  - name: openapi
    command: [uv, run, python, scripts/check_openapi.py]
---

# FastAPI serves the Python API

It answers the api-framework choice of `aidd-team:apis-and-services`.

## What the team does

- Type each route's parameters, body, and `response_model`, so FastAPI validates both ways and documents each one.
- Keep the committed contract (`openapi.yaml` or `openapi.json`) as the source a consumer reads; a person reviews each diff to it.
- Keep `scripts/check_openapi.py`: it writes `app.openapi()` and exits non-zero when that differs from the committed contract.
- Share database sessions, settings, and the caller's identity through `Depends`, never through module globals.
- Write `async def` routes only over async clients; a blocking call goes in a plain `def` route, which runs in a thread pool.
- Answer every error through one exception handler in the service's error format, with no stack trace.

## What the gate runs

One `tests` entry runs the contract check. A route that changed without its contract fails the change.
