# The contract's lifecycle: GraphQL, gRPC, webhooks, and generated code

Load this when the contract is a GraphQL schema, a Protobuf service, or a webhook. Also load it when an operation takes an idempotency key, or is generated, deprecated, retired, or updated concurrently. The pack's Test commands and the two tests at the end of this page prove each rule.

## GraphQL

- The schema (SDL) is the contract, in `design.files`. `graphql-inspector diff` against the base commit is the breaking-change check. Name a dangerous change (a new enum value, a changed default) in the Spec.
- Every server limits what one request may cost before it runs:
  - a maximum depth;
  - a maximum cost or complexity per operation, with lists weighted by their page size;
  - a cap on aliases and batched operations;
  - a timeout.
- Paginate by connection, with a required `first` or `last` and a stated maximum.
- A first-party client sends persisted operations (trusted documents). The build registers each operation's hash, and production accepts only registered hashes. Introspection is off in production for a private API.
- Authorization runs in the resolver or the data layer for every object and field, never only at the gateway. An error returns no stack trace or internal names.
- Deprecate a field with `@deprecated(reason: "...")`, and watch its usage per client. Remove it only when usage is zero or the window has passed.

## gRPC and Protobuf

- In CI, run `buf lint` with the default rules and `buf breaking --against` the base branch. Use `WIRE_JSON` compatibility where clients use JSON transcoding.
- Never reuse or renumber a field: mark a removed field `reserved` (its number and its name). Add fields; never change a type. A new required meaning is a new message or a new major package (`acme.orders.v2`).
- Every call carries a deadline. Status codes follow the gRPC set, with details in `google.rpc.Status` where clients need them.

## Webhooks (Standard Webhooks)

- Send `webhook-id`, `webhook-timestamp`, and `webhook-signature`. The signature is an HMAC-SHA256 over `id.timestamp.body` with a per-endpoint secret, `v1,<base64>`. Support two secrets at once for rotation.
- The receiver verifies the signature over the raw body with a constant-time comparison. It rejects a timestamp outside a stated tolerance (five minutes is common). It drops a `webhook-id` it has already processed, so a replay moves nothing. It answers 2xx fast and processes asynchronously.
- The sender retries with exponential backoff and jitter for a stated period, then disables the endpoint and tells its owner. Where the data is sensitive, payloads are thin (an id and a type), and the receiver fetches the rest.
- A provider that signs its webhooks its own way, with its own header, is verified with the provider's library. Keep the same timestamp tolerance and id deduplication.

## Idempotency keys, lists, clients, and events

The server stores each key with a hash of its request. A repeat gets the first response, and the same key with another body gets 422. A repeat that arrives while the first still runs gets 409. PUT and DELETE are idempotent by their HTTP meaning. The `Idempotency-Key` draft expired with no RFC, so the header is a convention.

- Resources are plural nouns in kebab-case paths. A large or changing list paginates by cursor, and filters and sorts through documented parameters.
- Clients state their timeouts, retries, and backoff. An event names its delivery semantics, at least once with idempotent consumers, and each boundary names its integration pattern.
- Keep an inventory of every API version and host, and retire the old ones (OWASP API9).

## Generated code and filtered fields

Consumers generate types and clients from the contract with one pinned generator. A schema another team or vendor owns is vendored at a pinned version, with its source URL. A scheduled job re-fetches it and opens a change when it differs. Two tests hold it:

| Test | Proves | How |
| --- | --- | --- |
| Generated-code drift check | no contract edit without regenerated code, and no hand edit to generated code | run the pinned generator, then `git diff --exit-code` on the generated paths, in CI |
| Field survival test | every field the schema declares survives each filtering layer | one round-trip test per serializer, DTO, allow-list, or resolver that sends every declared field |

Carry a correlation id on every request and event. Log structured, never secrets or personal data.

## Deprecation, sunset, and concurrent updates

- A deprecated HTTP operation answers with `Deprecation: @<unix-time>` (RFC 9745) and a `Link` with `rel="deprecation"` to the migration guide. Once a removal date is set, it also answers with `Sunset: <HTTP-date>` (RFC 8594). The contract marks it `deprecated: true` with the same dates. The window is announced to every known consumer.
- The Spec that deprecates it adds a `deprecations` entry: `what`, `announced_on` (the `Deprecation` date), `sunset`, the `replacement`, and the `consumers`. The Spec that removes it lists the `what` in `removes_deprecations`. Until then, a passed sunset is overdue work in `aidd status`, and the client status shows consumers the calendar.
- A resource that two clients may update carries an `ETag`. An update sends `If-Match`, and gets `412 Precondition Failed` when the resource changed since it was read (RFC 9110, section 13). So no update is lost. A create that must not overwrite sends `If-None-Match: *`.

## Two more tests

| Test | Proves | How |
| --- | --- | --- |
| GraphQL depth and cost limits | an over-limit or unpersisted operation is refused before it runs | one query per cap |
| Lost-update test | a stale `If-Match` gets 412 and changes nothing | two clients read, both write |
