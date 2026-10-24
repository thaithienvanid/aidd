---
name: caching
description: "Practice skill: cache a result without serving a wrong one. Use in an aidd repository when a Task adds or changes a cache, HTTP cache headers, a CDN rule, or memoization, or users see stale data."
metadata:
  checked: "2026-10-22"
---

# Caching

**Use it when** a Task adds or changes a cache of any kind. That is HTTP cache headers, a CDN or edge rule, a shared in-memory cache, an in-process memo, or a client-side data cache. Use it too when users see stale data, or another user's data.

**Do not use when** nothing is measured as slow or costly. Remove the work first, with `aidd-team:performance`: a cache in front of an N+1 query only hides it.

## Standards

<!-- aidd:gen practice:caching -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| RFC 9111 HTTP caching: Cache-Control, freshness, and validation | RFC 9111 (STD 98) | 2026-10-17 | <https://www.rfc-editor.org/rfc/rfc9111.html> |
| RFC 5861 stale-while-revalidate and stale-if-error | RFC 5861 | 2026-10-17 | <https://www.rfc-editor.org/rfc/rfc5861.html> |
| RFC 9213 targeted HTTP cache control (CDN-Cache-Control) | RFC 9213 | 2026-10-17 | <https://www.rfc-editor.org/rfc/rfc9213.html> |
| RFC 9110 HTTP semantics: methods, status codes, and conditional requests | RFC 9110 (STD 97) | 2026-10-16 | <https://www.rfc-editor.org/rfc/rfc9110.html> |
<!-- aidd:end -->

## Specify

- Name each cache in the Design. Write what it stores and its key: every input that changes the answer, such as the tenant, the user, the locale, the permissions, and a version. Write its lifetime, who may read it (`private` or shared), and how a write reaches it (expiry, invalidation, or a new version in the key).
- State the staleness the product accepts as an Acceptance line, such as "a price change shows on the product page within 60 s". Zero staleness means no cache, or an invalidation that the tests prove.
- State the saving the cache must buy, against the baseline `aidd-team:performance` measured. A cache that does not move the number comes out.

## Implement

- HTTP (RFC 9111): every response sends `Cache-Control`. Anything personal or authenticated is `private` or `no-store`. Shared content is `public` with a `max-age` and a validator (`ETag` or `Last-Modified`). A fingerprinted static asset is `max-age=31536000, immutable`. `Vary` lists every request header that changes the response.
- Never mark `public` a response to a request with `Authorization`, because that lets a shared cache store it. `no-cache` still stores, and revalidates on each use. Use `no-store` when a response must never be stored.
- Cache by the response's `Cache-Control`, never by the path's file extension. A rule by extension lets a CDN store a personal page whose URL ends in `.css`.
- Serve stale on purpose: `stale-while-revalidate` hides a refresh, and `stale-if-error` keeps a page up when the origin fails (RFC 5861). Give a CDN its own lifetime with `CDN-Cache-Control` (RFC 9213), not a longer `max-age` for every browser.
- Application cache: cache-aside by default. On a miss, read the source, then store it with a TTL. On a write, delete the key after the transaction commits, or bump the version in the key. A reader that missed before the commit can store the old value after the delete. So every key keeps a TTL, which bounds how long that stale value lives. Add jitter to TTLs, so keys do not all expire at once.
- Put the cached value's format version in the key, so a deploy never reads a value in the old shape. A client-side cache clears on sign-out, so the next person on the device sees none of it.
- Stampede: when a hot key expires, one caller recomputes it (a lock or request coalescing), and the others wait or get the stale value. Cap the cache's memory and name its eviction policy.
- The cache is never the only copy. A flushed or failed cache makes the system slower, never wrong. Time out cache calls short, and fall back to the source.
- Never cache an error, a partial result, or one tenant's data under a key another tenant can produce. Cache a not-found answer only with a short TTL, so a new record shows soon.
- A validator lets a client revalidate cheaply, because `If-None-Match` gets `304 Not Modified` with no body (RFC 9110).

## Review

- Each cache has its key, lifetime, audience, and invalidation written down, and the key holds every input that changes the answer. Personal data never reaches a shared cache. The hit ratio, the latency, and the source's load are measured before and after.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Key isolation test | a user or tenant never gets another's cached answer | two users request the same resource in turn; assert each sees their own |
| Invalidation test | a write shows within the staleness the Spec accepts | write, then read through the cache with the clock at the limit |
| Header check | each route sends the `Cache-Control` and `Vary` the Spec names, and no response that sets a cookie is shared-cacheable | an integration test that asserts the headers per route |
| Cache-down test | the system still answers correctly with no cache | fail the cache in the test; assert correct, slower answers |
| Stampede test | one recompute when many callers miss one key at once | N parallel reads of an expired key; assert one call to the source |

## Stop if

- A cache comes before a baseline that shows the cost it removes.
- The key leaves out an input that changes the answer, such as the tenant or the permissions.
- A shared cache or a CDN would store an authenticated or personal response.
- Losing the cache would lose data.
- A response varies on an input the key leaves out, such as an unkeyed header. One request can then poison the cache for every user.

## Hand off

- Done: each cache with its key, lifetime, audience, invalidation, and measured effect, and the tests above. Next: the reviewer, and the SRE to watch the hit ratio and the source's load in the observe window. Needs: none. Stopped at: none, or the stop rule that fired.
