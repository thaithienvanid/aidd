---
id: tooling/hurl
type: opinionated
fills: [apis-and-services:api-test]
default: true
implements: product-defaults:api_conventions
roles: [verifier, developer, reviewer]
when_changed: ["api-tests/**", openapi.yaml, openapi.json, "**/openapi.yaml"]
why: "Hurl keeps each API test as a plain-text file of requests and asserts in the repository, and its one binary exits non-zero on a failed assert, so the run itself is the evidence. Orange maintains it under Apache-2.0."
reviewed: "2026-10-22"
maturity: established
tool:
  name: hurl
  registry: github
  package: Orange-OpenSource/hurl
version_policy: current_stable
checked_version: "8.0.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "8.0.1"
source: https://api.github.com/repos/Orange-OpenSource/hurl/releases/tags/8.0.1
evidence: "\"tag_name\": \"8.0.1\""
alternatives: [Bruno, Postman, the framework's own HTTP test client]
status: active
enforced_by:
  - name: api
    command: [hurl, --test, api-tests/]
---

# Hurl runs the API tests

It answers the api-test choice of `aidd-team:apis-and-services`. Hurl is under Apache-2.0 from Orange. `tooling/bruno` is the alternative for a team that wants a desktop app.

Postman is not the default. Its shared workspaces live in Postman Cloud and need an account, and its app and CLI are proprietary. Its CLI can run a local collection without signing in, so a team already on Postman may keep it.

## What the team does

- Install `hurl` at `pin` in CI, and keep one `.hurl` file per scenario in `api-tests/`.
- Chain the requests of a scenario in its file, capturing a token or an id from one response for the next.
- Assert the status, the headers, and the body of each response, such as `jsonpath "$.id" exists`.
- Cover the API conventions: a problem+json error, a repeated `Idempotency-Key`, a next cursor, and `Retry-After` on 429.
- Pass the address as `HURL_VARIABLE_base_url`, and each credential as `HURL_SECRET_<name>`, so Hurl redacts it from logs and reports.
- Write a JUnit report with `--report-junit` where CI shows test results.

## What the gate runs

One `api` test runs `hurl --test` over `api-tests/` against the service CI started first. Hurl exits with 3 when it cannot reach the service and with 4 on a failed assert, so either fails the change.
