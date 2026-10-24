---
id: typescript/fastify-api
type: opinionated
fills: [apis-and-services:api-framework]
default: false
implements: apis-and-services:Breaking-change diff
roles: [developer, architect, reviewer]
when_changed: ["**/*.ts", package.json, openapi.yaml, openapi.json]
why: "Fastify is a long-running Node.js server with a large plugin ecosystem; each route declares a schema that validates the request and serializes the reply, and the same schemas write the OpenAPI document."
reviewed: "2026-10-16"
maturity: established
tool:
  name: fastify
  registry: npm
  package: fastify
version_policy: current_major
checked_version: "5.12.7"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/fastify/dist-tags
evidence: "\"latest\":\"5.12.7\""
alternatives: [Hono, NestJS, Express]
status: active
enforced_by:
  - name: openapi
    command: [pnpm, run, openapi:check]
---

# Fastify serves the TypeScript API on a Node.js server

It answers the api-framework choice of `aidd-team:apis-and-services` for a service that runs as a Node.js process, not on an edge runtime. License: MIT. `typescript/hono-api` stays the default.

## What the team does

- Stay on Fastify 5. Version 6 is an alpha on the `next` tag; move to it only after its final release and its migration guide.
- Declare each route's body, query, params, and replies with Zod through `@fastify/type-provider-zod`, so the handler's types come from the same schema.
- Register `@fastify/swagger` with the provider's `jsonSchemaTransform`, and commit the OpenAPI document it writes as the contract a consumer reads.
- Add an `openapi:check` script that writes the document from the app without listening and exits non-zero when it differs from the committed copy.
- Set `bodyLimit`, timeouts, and one `setErrorHandler` that answers in the service's error format with no stack trace.
- Log through `request.log`, Fastify's built-in Pino logger, so each line belongs to its request.

## What the gate runs

One `tests` entry runs `pnpm run openapi:check`. A route whose contract changed without the committed document fails the change.
