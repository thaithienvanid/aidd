---
id: typescript/sveltekit
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, reviewer]
when_changed: ["src/**", vite.config.ts, "tsconfig*.json", package.json]
why: "SvelteKit renders Svelte on the server, loads each page's data in server code, and posts forms that work before JavaScript loads, with a small client bundle, for a team that writes Svelte."
reviewed: "2026-10-22"
maturity: established
tool:
  name: sveltekit
  registry: npm
  package: "@sveltejs/kit"
version_policy: current_major
checked_version: "3.1.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://svelte.dev/docs/kit/configuration
evidence: "An array of origins that are allowed to make cross-origin form submissions to your app."
pin: "3.1.0"
alternatives: [Next.js, Nuxt, Astro]
status: active
enforced_by:
  - name: check
    command: [sh, -c, "pnpm exec svelte-kit sync && pnpm exec svelte-check --fail-on-warnings"]
  - name: build
    command: [pnpm, exec, vite, build]
---

# SvelteKit renders the Svelte web front end

It answers the web-framework choice of `aidd-team:web-front-end` for a team that writes Svelte. License: MIT for SvelteKit and Svelte. SvelteKit 3.0.0 came out on 2026-10-01, and Svelte was at 5.57.2 when this file was checked. `typescript/nextjs-app-router` stays the default.

## What the team does

- Add `@sveltejs/kit` at `pin`, `svelte`, `svelte-check` (4.7.7 here), and one adapter, such as `@sveltejs/adapter-node` 6.0.0, as exact dev dependencies. SvelteKit 3 reads its options from the `sveltekit()` plugin in `vite.config.ts`, not from `svelte.config.js`.
- SvelteKit 3.1.0 and `svelte-check` accept TypeScript 6 only, so install TypeScript 6 beside 7, as `typescript/eslint-prettier` shows.
- Load a page's data in `+page.server.ts` and change it through form actions, so a form works before the page's JavaScript runs. Validate each action's form data with a Zod schema.
- Keep the CSRF check on. Leave `csrf.trustedOrigins` empty, and add only the full origin of a service that posts a form back, such as a payment provider, never `'*'`.
- Run unit tests with `typescript/vitest-tests` and journeys with `typescript/playwright-e2e`.

## What the gate runs

Two `tests` entries. `svelte-check --fail-on-warnings` fails on a type error or a warning in any component, after `svelte-kit sync` writes the route types. `vite build` fails when a page or a server route does not build.
