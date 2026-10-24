---
id: tooling/bruno
type: opinionated
fills: [apis-and-services:api-test]
default: false
implements: product-defaults:api_conventions
roles: [verifier, developer, reviewer]
when_changed: ["api-tests/**", openapi.yaml, openapi.json, "**/openapi.yaml"]
why: "Bruno gives a desktop app for API requests and keeps each collection as plain files in the repository, so a person explores in the app while `bru run` checks the same files in CI. It is under MIT."
reviewed: "2026-10-22"
maturity: established
tool:
  name: bruno-cli
  registry: npm
  package: "@usebruno/cli"
version_policy: current_stable
checked_version: "4.3.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.2.1"
cooldown_until: "2026-10-29"
source: https://registry.npmjs.org/@usebruno%2fcli/4.3.0
evidence: "\"version\":\"4.3.0\""
alternatives: [Hurl, Postman]
status: active
enforced_by:
  - name: api
    command: [sh, -c, "cd api-tests && npx --yes @usebruno/cli@4.2.1 run -r --env ci"]
---

# Bruno runs the API tests from a desktop app's collection

It answers the api-test choice of `aidd-team:apis-and-services` for a team that wants a desktop app. `tooling/hurl` stays the default, with no app to install. The app and `@usebruno/cli` are open source under MIT, and paid editions add features on top.

`@usebruno/cli` 4.3.0 came out on 2026-10-22, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 4.2.1 until `cooldown_until`.

## What the team does

- Keep the collection in `api-tests/`, in the OpenCollection YAML format that Bruno uses by default for a new collection since 3.1. An older collection keeps its `.bru` files until the app migrates it.
- Import a Postman collection, exported as Collection v2 or v2.1, into Bruno once. Then review and commit the files it writes.
- Write each check as an assertion or a test on the request, so a failed one fails `bru run`.
- Keep a `ci` environment whose address and secrets come from CI variables, never a value in the repository.
- Keep the CLI's default Safe Mode. A script that needs Developer Mode states why.

## What the gate runs

One `api` test runs `bru run` over the collection, from its folder, against the service CI started first. It exits with 1 when a request, a test, or an assertion fails, so the change fails.
