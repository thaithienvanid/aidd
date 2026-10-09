---
name: api-design
description: "Practice skill: design or change an API contract first. Use in an aidd repository when a Task changes an endpoint, event, schema, webhook, or SDK, or someone says breaking change."
metadata:
  checked: "2026-09-30"
---

# API design

**Use it when** a Task adds or changes an endpoint, a message, a contract, a webhook, or an SDK. The `aidd-team:apis-and-services` pack says what applies. This skill is how to do the work.

**Do not use when** the change exposes or consumes no interface across a process boundary. An internal function signature is a code review matter, not a contract.

## Standards

<!-- aidd:gen practice:api-design -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| OpenAPI Specification | 3.2.1 | 2026-09-29 | <https://spec.openapis.org/oas/v3.2.1.html> |
| RFC 9110 HTTP semantics: methods, status codes, and conditional requests | RFC 9110 (STD 97) | 2026-09-30 | <https://www.rfc-editor.org/rfc/rfc9110.html> |
| RFC 9457 problem details | 2023 | 2026-09-30 | <https://www.rfc-editor.org/rfc/rfc9457> |
| OWASP API Security Top 10 | 2023 | 2026-10-07 | <https://api-security.owasp.org/editions/2023/en/0x11-t10/> |
| Semantic Versioning for public contracts | 2.0.0 | 2026-09-29 | <https://semver.org/> |
| Idempotency keys and rate limits (emerging) | draft-ietf-httpapi-idempotency-key-header-07; draft-ietf-httpapi-ratelimit-headers-11 | 2026-09-30 | <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/> |
| Integration patterns: channel, endpoint, and the error-handling pattern each boundary uses | — | 2026-09-29 (reviewed) | <https://www.enterpriseintegrationpatterns.com/> |
| HTTP Deprecation and Sunset header fields | RFC 9745; RFC 8594 | 2026-09-30 | <https://www.rfc-editor.org/rfc/rfc9745.html> |

Steward: @thaithienvanid.
<!-- aidd:end -->

## Specify

- Contract first: write the OpenAPI or AsyncAPI change. List it in `design.files`, so Spec approval freezes it. Reference its operations in the Acceptance.
- Resources are plural nouns in kebab-case paths. Methods and status codes follow RFC 9110. Every error is a problem-details document with a stable `type` URI.
- Every list paginates (cursor pagination for large or changing sets), filters and sorts through documented parameters, and states its maximum page size.
- Every unsafe request that a client may retry takes an idempotency key. The `Idempotency-Key` draft expired on 2026-04-18: the header is a convention, not a standard. The contract documents the rate limits.
- Versioning: additive changes need no bump. A removal or a changed meaning goes through expand and contract with a deprecation window that the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers announce. A breaking change is a new major version.
- A resource two clients may update carries an `ETag` and takes `If-Match`, answering `412` to a stale one (RFC 9110), so no update is lost.
- GraphQL, Protobuf, webhooks, and the deprecation headers: [references/graphql-grpc-webhooks.md](references/graphql-grpc-webhooks.md).
- Authorization is per object and per field (OWASP API1, API3). State timeouts, retries, and backoff for clients. Events name delivery semantics (at least once with idempotent consumers) and the integration pattern each boundary uses.
- The `api_conventions` and `data_conventions` product defaults: `aidd-team:product-defaults`.

## Implement

- Validate input against the contract at the boundary. Generate stubs or clients from it. Map every internal error to a problem-details response that leaks nothing.
- Consumers generate types and clients from the contract with one pinned generator, never a hand-written copy.
- A schema another team or vendor owns is vendored at a pinned version, with its source URL. A scheduled job re-fetches it and opens a change when it differs.
- Where a layer filters fields (a serializer, a DTO, an allow-list, a resolver), a test sends every field the schema declares. The test asserts each field survives, so a new field is never dropped silently.
- Carry a correlation id on every request and event. Log structured, never a secret or personal data.

## Review

- The breaking-change diff is empty or a major version. Every new operation has authorization, pagination, error mapping, and documentation. Names match the existing style. No consumer hand-writes a type the contract defines.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Generated-code drift check | no contract edit without regenerated code, and no hand edit to generated code | run the pinned generator, then `git diff --exit-code` on the generated paths, in CI |
| Field survival test | every field the schema declares survives each filtering layer | one round-trip test per serializer, DTO, allow-list, or resolver; plus the scheduled re-fetch of vendored schemas |
| Object-level authorization tests | no caller reaches another's object | an IDOR attempt per resource and per field |
| Webhook signature and replay tests | a bad signature, a stale timestamp, or a repeated id moves nothing | one test each, on the raw body |
| GraphQL depth and cost limits | an over-limit or unpersisted operation is refused before it runs | one query per cap |
| Lost-update test | a stale `If-Match` gets 412 and changes nothing | two clients read, both write |

- From `aidd-team:apis-and-services`: Spectral, Contract tests, Schema conformance, Breaking-change diff.

## Stop if

- The contract change is not in `design.files`, or the Acceptance does not name its operations.
- A removal or a changed meaning ships without a major version or an expand-and-contract plan.
- A consumer would hand-write a type the contract defines.

## Hand off

- Done: the contract and the operations it names. Next: the tester for contract and abuse tests. Needs: any consumer that cannot be verified. Stopped at: none, or the stop rule that fired.
