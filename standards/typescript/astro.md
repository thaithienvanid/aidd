---
id: typescript/astro
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, reviewer]
when_changed: ["src/**", astro.config.mjs, astro.config.ts, "tsconfig*.json", package.json]
why: "Astro builds a content-first site to static HTML and sends JavaScript only for the components that ask for it, so docs, a blog, or marketing pages stay inside the performance budget."
reviewed: "2026-10-22"
maturity: established
tool:
  name: astro
  registry: npm
  package: astro
version_policy: current_stable
checked_version: "7.4.2"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
source: https://docs.astro.build/en/concepts/islands/
evidence: "They render to static HTML with no client-side runtime."
pin: "7.4.1"
cooldown_until: "2026-10-28"
alternatives: [Next.js, SvelteKit, Nuxt]
status: active
enforced_by:
  - name: check
    command: [pnpm, exec, astro, check, --minimumFailingSeverity, warning]
  - name: build
    command: [pnpm, exec, astro, build]
---

# Astro renders the content-first web front end

It answers the web-framework choice of `aidd-team:web-front-end` for a site that is mostly content, such as docs, a blog, or marketing pages. License: MIT. `typescript/nextjs-app-router` stays the default, for an app whose screens hold much state.

Astro 7.4.2 came out on 2026-10-21, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 7.4.1 until `cooldown_until`.

## What the team does

- Add `astro` at `pin` and `@astrojs/check` (0.9.11 here) as exact dev dependencies. `@astrojs/check` accepts TypeScript 5 or 6 only, so install TypeScript 6 beside 7, as `typescript/eslint-prettier` shows.
- Keep the static output, the default. Render a page on demand only when it needs the request, with `export const prerender = false` and an adapter pinned exactly.
- Send no JavaScript by default. Give each interactive component a `client:` directive, and prefer `client:visible` or `client:idle`. Write the reason beside each `client:load`.
- Define each content collection in `src/content.config.ts`, with a loader and a schema built from `z` in `astro/zod`. An entry that breaks its schema then fails the build.
- Run unit tests with `typescript/vitest-tests` and journeys with `typescript/playwright-e2e`.

## What the gate runs

Two `tests` entries. `astro check` fails on an error or a warning in any `.astro` file. `astro build` fails when a page or a content entry does not build.
