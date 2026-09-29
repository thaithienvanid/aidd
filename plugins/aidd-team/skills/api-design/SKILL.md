---
name: api-design
description: "Practice skill: design or change an HTTP, gRPC, or event API. Use when a Task adds or changes an endpoint, a route, a request or response field, a message or event, an OpenAPI or AsyncAPI file, a GraphQL or gRPC schema, a webhook, or an SDK, or when someone mentions a breaking change, versioning, pagination, the error format, idempotency keys, rate limits, generated clients, or types drifting from the API: contract first, RFC 9457 errors, idempotency, pagination, versioning, generated consumer types with a drift check, and the test commands that prove them."
metadata:
  checked: "2026-09-28"
---

# API design

**Use it when** a Task adds or changes an endpoint, a message, a contract, a webhook, or an SDK. The `aidd-team:apis-and-services` pack says what applies; this skill is how to do the work.

**Do not use when** the change exposes or consumes no interface across a process boundary; an internal function signature is a code review matter, not a contract.

## Standards

- OpenAPI 3.1.0 for HTTP (3.2.1 where your linter supports it), AsyncAPI 3.1.0 for events.
- RFC 9110 HTTP semantics.
- RFC 9457 problem details.
- OWASP API Security Top 10 (2023).
- Semantic Versioning 2.0.0 for public contracts.
- The IETF `Idempotency-Key` and `RateLimit` header drafts.

## Specify, before Spec approval

- Contract first: write the OpenAPI or AsyncAPI change, list it in `design.files` so Spec approval freezes it, and reference its operations in the Acceptance.
- Resources are plural nouns in kebab-case paths; methods and status codes follow RFC 9110; every error is a problem-details document with a stable `type` URI.
- Every list paginates (cursor pagination for large or changing sets), filters and sorts through documented parameters, and states its maximum page size.
- Every unsafe request that a client may retry takes an idempotency key; rate limits are documented in the contract.
- Versioning: additive changes need no bump; a removal or a changed meaning goes through expand and contract with a deprecation window and headers; a breaking change is a new major version.
- Authorization is per object and per field (OWASP API1, API3); timeouts, retries, and backoff are stated for clients; events name delivery semantics (at least once with idempotent consumers).

## Implement

- Validate input against the contract at the boundary and generate stubs or clients from it; map every internal error to a problem-details response that leaks nothing.
- Consumers generate their types and clients from the contract, never a hand-written copy of it; the generated files are committed (or built in CI) from one pinned generator version.
- A schema that another team or vendor owns is vendored at a pinned version, with its source URL beside it; a scheduled CI job re-fetches it and opens a change when it differs.
- Where a layer filters or whitelists fields (a serializer, a DTO, a response allow-list, a GraphQL resolver), a test builds a value with every field the schema declares and asserts each one survives the round trip, so a new field is never dropped silently.
- Carry a correlation id on every request and event; log structured, never a secret or personal data.

## Test commands

- `spectral lint` on the contract; `schemathesis run` against the running service; Pact provider verification, then `can-i-deploy`.
- `oasdiff breaking` between the base and head contracts; authorization tests per object (an IDOR attempt per resource); a rate-limit test.
- A drift check in CI: run the generator, then `git diff --exit-code` on the generated paths, so a contract edit without regenerated code, or a hand edit to generated code, fails the build.
- The field-survival test above, one per filtering layer; the scheduled re-fetch of vendored schemas.

## Review

- The breaking-change diff is empty or a major version; every new operation has authorization, pagination, error mapping, and documentation; names match the existing style; no consumer hand-writes a type the contract defines.

## Hand off

- Done: the contract and the operations it names. Next: the tester for contract and abuse tests. Needs: any consumer that cannot be verified. Stopped at: none, or the stop rule that fired.
