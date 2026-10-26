---
id: typescript/tanstack-query
type: opinionated
fills: [web-front-end:data-fetching]
default: true
implements: caching:Invalidation test
roles: [developer, architect, reviewer]
when_changed: ["src/**", "app/**", package.json]
why: "TanStack Query keeps server data in one cache with a staleness per query, deduplicates requests, and refetches after a mutation, so a screen never holds a second copy of server data in its own state."
reviewed: "2026-10-22"
maturity: established
tool:
  name: tanstack-query
  registry: npm
  package: "@tanstack/react-query"
version_policy: current_major
checked_version: "5.104.5"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults
evidence: "Query instances via `useQuery` or `useInfiniteQuery` by default consider cached data as stale."
alternatives: [SWR, RTK Query, Apollo Client, The framework's own data loaders]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/@tanstack/react-query/package.json').version.startsWith('5.') ? 0 : 1)"
---

# TanStack Query holds the server data a client screen reads

It answers the data-fetching choice of `aidd-team:web-front-end`. License: MIT. In a Next.js app it serves only the client components that read data after the page loads; a server component reads its own.

## What the team does

- Create one `QueryClient` per app, and one per request on the server.
- Give each module a query-key factory, such as `orders.keys.detail(id)`, next to its `queryOptions`. A key holds every variable its query reads, and no screen writes a key by hand.
- Set `staleTime` on purpose, for each query or once for the client, with the reason beside it. The default treats every cached answer as stale at once.
- After each mutation, invalidate the keys it changed in `onSuccess`, or write the answer into the cache with `setQueryData`.
- Parse each response with its Zod schema inside the query function, so the cache holds only parsed data.
- Keep UI state in the component or the URL, never in the query cache.

## What the gate runs

One `tests` entry checks that the project resolves the major release this file was checked at, so an upgrade is a change a person reads.
