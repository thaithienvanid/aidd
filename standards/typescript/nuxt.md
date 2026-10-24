---
id: typescript/nuxt
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, reviewer]
when_changed: ["app/**", "server/**", "shared/**", nuxt.config.ts, package.json]
why: "Nuxt renders Vue on the server by default, with file-based pages, server routes, and data fetching that hands the server's answer to the client, for a team that writes Vue."
reviewed: "2026-10-22"
maturity: established
tool:
  name: nuxt
  registry: npm
  package: nuxt
version_policy: current_major
checked_version: "4.6.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://nuxt.com/docs/4.x/api/commands/typecheck
evidence: "The typecheck command runs vue-tsc or Golar to check types throughout your app."
alternatives: [Next.js, SvelteKit, Angular]
status: active
enforced_by:
  - name: types
    command: [pnpm, exec, nuxt, typecheck]
  - name: build
    command: [pnpm, exec, nuxt, build]
---

# Nuxt renders the Vue web front end

It answers the web-framework choice of `aidd-team:web-front-end` for a team that writes Vue. License: MIT for Nuxt and Vue. Nuxt was at 4.6.2 and Vue at 3.5.44 when this file was checked. `typescript/nextjs-app-router` stays the default.

## What the team does

- Keep Nuxt 4's layout: the app under `app/`, with `server/`, `shared/`, and `public/` at the root.
- Write each component as `<script setup lang="ts">`, with typed `defineProps` and `defineEmits`.
- Read a page's data with `useFetch` or `useAsyncData`, so the server's answer reaches the client in the payload and the browser never asks twice. Use `$fetch` only for a request the browser alone makes.
- Validate each server route's body and query with a Zod schema (`readValidatedBody`, `getValidatedQuery`).
- Add `vue-tsc` as an exact dev dependency. `tsc` does not read `.vue` files, so `nuxt typecheck` is the type check.
- Lint with `@nuxt/eslint` under `typescript/eslint-prettier`, because Biome's support for Vue files is still experimental.
- Run unit tests with `typescript/vitest-tests` and `@nuxt/test-utils` in its `nuxt` environment, and journeys with `typescript/playwright-e2e`.

## What the gate runs

Two `tests` entries. `nuxt typecheck` fails on a type error in any component or server route. `nuxt build` fails when a page or a server route does not build.
