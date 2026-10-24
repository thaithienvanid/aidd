---
id: typescript/hono-api
type: opinionated
fills: [apis-and-services:api-framework]
default: true
implements: apis-and-services:Breaking-change diff
roles: [developer, architect, reviewer]
when_changed: ["**/*.ts", package.json, openapi.yaml, openapi.json]
why: "Hono is a small framework on the Web Standards Request and Response, so one service runs on Node.js, Cloudflare Workers, Deno, and Bun, and its OpenAPI routes take Zod schemas."
reviewed: "2026-10-16"
maturity: established
tool:
  name: hono
  registry: npm
  package: hono
version_policy: current_major
checked_version: "4.13.13"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/hono/dist-tags
evidence: "\"latest\":\"4.13.13\""
alternatives: [NestJS, Fastify, Express]
status: active
enforced_by:
  - name: openapi
    command: [pnpm, run, openapi:check]
---

# Hono serves the TypeScript API

It answers the api-framework choice of `aidd-team:apis-and-services`.

## What the team does

- Declare each route with `@hono/zod-openapi`, so its input schema, its responses, and the OpenAPI document come from one definition.
- Keep the committed contract (`openapi.yaml` or `openapi.json`) as the source a consumer reads; the app writes it, and a person reviews each diff.
- Add an `openapi:check` script to `package.json` that writes the document from the app and exits non-zero when it differs from the committed one.
- Answer every error through one `app.onError` handler in the service's error format, with no stack trace.
- Set timeouts, body limits, and CORS with Hono's middleware, once, at the app.

## What the gate runs

One `tests` entry runs `pnpm run openapi:check`. A route that changed without its contract fails the change.
