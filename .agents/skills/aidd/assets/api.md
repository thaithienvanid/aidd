# API: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec.

<!-- The architect's API doc. The machine-readable description is the frozen contract. It is an OpenAPI file for HTTP
     (at the edition the `aidd-team:apis-and-services` pack names), or an AsyncAPI 3 file for events and messages.
     Put it in the Spec's `tests.files` (or `design.files`), so Spec approval pins it. This page adds what the
     description cannot say: who depends on it, how it changes, and how a change is caught. Link the Spec's
     Acceptance ids (A1, A2, ...) where a section answers one.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Contract

- Description: TODO: the path of the OpenAPI or AsyncAPI file.
- Operations or channels this change adds or changes: TODO.

## Consumers

<!-- Every known caller, and how you would learn about an unknown one (access logs, API keys, a registry). -->

| Consumer | Owner | Operations used | Contact |
| --- | --- | --- | --- |
| TODO | TODO | TODO | TODO |

## Versioning and deprecation

<!-- The versioning scheme (a path, a header, a media type, or none), and what counts as a new version. Then how an
     old version retires: the Deprecation and Sunset headers, the notice period, and who tells the consumers. -->

TODO: the scheme and the deprecation policy.

## Error model

<!-- Write errors as RFC 9457 problem details (`application/problem+json`: type, title, status, detail, instance).
     Give one `type` URI to each error that a consumer can act on. -->

| Type | Status | When | What the consumer does |
| --- | --- | --- | --- |
| TODO | 4xx | TODO | TODO |

## Auth and scopes

<!-- How callers authenticate, and which scope or role each operation needs; the least privilege that works. -->

| Operation | Scope or role |
| --- | --- |
| TODO | TODO |

## Idempotency, pagination, and rate limits

- Idempotency: TODO: which operations are safe to retry, and the key (such as an `Idempotency-Key` header) and its lifetime.
- Pagination: TODO: cursor or offset, the page size limit, and the order it guarantees.
- Rate limits: TODO: the limit per caller, the response when it is hit (429 with `Retry-After`), and the headers that show it.

## Breaking-change assessment

<!-- For each change to an existing operation, say if it is breaking. A breaking change includes, for example, a
     removed field, a new required field, a narrowed type, or a changed status code or meaning. A breaking change
     needs a new version or a migration window. -->

| Change | Breaking | Why | Plan |
| --- | --- | --- | --- |
| TODO | no | TODO | TODO |

## Tests

<!-- Put two checks in the Spec's `tests.commands`:
     - contract tests that run the implementation against the description
     - a breaking-change diff check that compares the description on base with head (for example oasdiff for
       OpenAPI). It fails on a breaking change that nobody declared above. -->

- Contract test: TODO: the command.
- Breaking-change diff: TODO: the command.

[spec]: {{spec_link}}
