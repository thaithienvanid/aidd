# The service and repository product defaults: what each builds, and its test

Each is on unless `project.defaults.disabled` names it with its reason. Build only what is on, and name each one you built on the handoff note.

- `api_conventions`:
  - a version in the path (`/v1/`) or a header;
  - lists paginate by an opaque cursor (`?cursor=`, a `next` link), never an offset;
  - every non-idempotent write accepts an `Idempotency-Key` header and replays the stored response on a repeat;
  - that header is a convention, not a standard: its IETF draft expired on 2026-04-18;
  - errors are RFC 9457 problem details (`application/problem+json`), and the body carries the trace ID as an extension member (`trace_id`), so support can find the log line;
  - responses send the `RateLimit` and `RateLimit-Policy` fields, and a 429 sends `Retry-After`.
- `data_conventions`:
  - times stored in UTC and exchanged in ISO 8601 with the offset (`2026-09-30T08:00:00Z`);
  - money as integer minor units with its ISO 4217 currency (`amount_minor: 1999`, `currency: EUR`), never a float;
  - sortable IDs, UUIDv7 (RFC 9562) or ULID, never a sequential id in a URL;
  - `created_at`, `updated_at`, and `created_by` on every record;
  - a soft delete (`deleted_at`) where a person can undo, with a purge job for what the retention policy ends.
- `operability`:
  - `/healthz` checks the process only, never a dependency, so an outage of a shared database never restarts every instance;
  - `/readyz` checks that its dependencies answer, and fails while one is down;
  - structured JSON logs with a request ID and the W3C trace context trace ID on every line, and no secret or personal data in them; an error's line also carries its `code`;
  - graceful shutdown on SIGTERM and configuration validated at start, as the Twelve-Factor rules of `aidd-team:observability` say, with a `.env.example` and no secret committed.
- `security_headers`:
  - on every response, `Content-Security-Policy` (nonces or hashes, no `unsafe-inline`), `Strict-Transport-Security: max-age=63072000; includeSubDomains`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin`;
  - `frame-ancestors` in the policy, against clickjacking;
  - every cookie `Secure`, `HttpOnly` (unless script must read it), and `SameSite=Lax` or `Strict`;
  - CSRF protection on every state-changing request: a synchronizer token, or a double-submit cookie with an Origin check.
- `dev_basics`:
  - a formatter, a linter, and a type check, each run in CI and in a pre-commit hook (the `pre-commit` framework, or husky with lint-staged);
  - an `.editorconfig`;
  - one command to set up and one to run the project (`make setup`, `make dev`, or the package scripts);
  - a dependency update bot (Dependabot or Renovate), grouped by ecosystem;
  - commit messages in Conventional Commits.

## How each test runs

The test names are the SKILL.md table's.

- API conventions: contract tests (Schemathesis custom checks, or the framework's test client) assert four things. Every error is `application/problem+json`, a repeated `Idempotency-Key` has one effect, a list returns a next cursor, and a 429 carries `Retry-After`. A migration lint checks that every table has `created_at` and `updated_at`, and no float money column.
- Operability smoke, in this order:
  1. Start the service.
  2. Call `/healthz` and `/readyz`.
  3. Send SIGTERM mid-request, and assert the request completes and the process exits 0.

  A log line parses as JSON and carries the trace ID. An error's line carries its `code`, and its problem body the same `trace_id`.
- Security headers: request each route (Playwright's `request` or the framework's test client). Assert the four headers and the `Set-Cookie` attributes. A request without the CSRF token is refused.
- Dev basics: CI runs the formatter in check mode, the linter, and the type check. `pre-commit run --all-files` passes on a clean checkout.
