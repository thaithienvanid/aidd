# Errors and public names, by default

A public name is permanent once a client depends on it. Decide it in Specify, with the `aidd-team:naming` skill, and freeze it with the contract. Name each thing as the standard the Spec cites names it, in the language's own convention. These are the defaults; a project's own convention, written in its standards, wins.

## The error body (RFC 9457)

| What | Default | Not |
| --- | --- | --- |
| The body's schema | `ProblemDetails` (the RFC's own name; .NET names it so, Spring `ProblemDetail`) | `Problem`, `Error`, `ErrorResponse` |
| Its media type | `application/problem+json` | `application/json` |
| `type` | an https URL the team controls, which documents the error (`https://errors.example.com/payment-declined`), or `about:blank` | a `tag:` URI, a relative path |
| A stable code | `code`, snake_case, one per error (`payment_declined`), never reused | a number, a message text |
| Validation issues | `errors: [{pointer, detail}]`, `pointer` a JSON Pointer into the request | free text |
| `status`, `title` | the status code and its RFC 9110 reason phrase | a custom phrase |

On a stream that has already started (SSE, a WebSocket, a chunked response), an error is an event, `event: error`, whose data is the same `ProblemDetails` with the same `code`. The status line has already gone.

## Responses in the contract

Name a reusable response by its meaning, as RFC 9110 names the status: `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `PayloadTooLarge`, `UnsupportedMediaType`, `TooManyRequests`. Never by its number (`Problem404`), and never by the tenant or caller (`TenantProblem`).

## The exception that renders it

Name the exception for what it is, in the language's convention, never for the body it renders to:

| Language | Default |
| --- | --- |
| Python | `ApiError` (PEP 8: an `Error` suffix), subclasses by meaning: `NotFoundError` |
| TypeScript | `class ApiError extends Error` |
| Go | `ErrNotFound` values, an `APIError` type |
| Java, Kotlin | `ApiException` |

One mapping turns each exception into its `ProblemDetails`, and nothing else builds one.

## Other public names

Events are past-tense facts (`order.placed`), and fields are camelCase in JSON or as the API already spells them. Environment variables are UPPER_SNAKE with the product's prefix, and database roles say what they may do (`app_readonly`). Give each public term one glossary entry (`docs/GLOSSARY.md`, or the domain pack's `## Terms`), decided once and used everywhere.

## When a frozen name is wrong

Rename it while nothing outside depends on it. Change the contract, its tests, and the Spec in one revision that says it is a rename only. The next Spec approval is one typed `approve <ID>`, or the person's standing approval covers it. Once a client depends on the name, it goes through expand and contract instead.
