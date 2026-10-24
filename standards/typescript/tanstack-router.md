---
id: typescript/tanstack-router
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, reviewer]
when_changed: ["src/**", vite.config.ts, tsconfig.json, package.json]
why: "TanStack Router gives a single-page React app fully typed routes, search params, and loaders, built by Vite and split per route, for an app-like screen that the server need not render."
reviewed: "2026-10-22"
maturity: established
tool:
  name: tanstack-router
  registry: npm
  package: "@tanstack/react-router"
version_policy: current_major
checked_version: "1.170.46"
cooldown_until: "2026-10-29"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
source: https://tanstack.com/router/latest/docs/framework/react/installation/with-vite
evidence: "This file is managed by TanStack Router and therefore shouldn't be changed by your linter or formatter."
alternatives: [Next.js, React Router, TanStack Start]
status: active
enforced_by:
  - name: build
    command:
      - sh
      - -c
      - "pnpm exec vite build && git diff --exit-code -- src/routeTree.gen.ts && pnpm exec tsc --noEmit"
---

# TanStack Router routes the single-page React app

It answers the web-framework choice of `aidd-team:web-front-end` for a client-rendered app, such as a dashboard behind sign-in. License: MIT. `typescript/nextjs-app-router` stays the default, because a public page renders on the server.

## What the team does

- Add `@tanstack/react-router` and `@tanstack/router-plugin` as exact dependencies. In `vite.config.ts`, pass `tanstackRouter({ target: 'react', autoCodeSplitting: true })` before `@vitejs/plugin-react`.
- Build with Vite 8, which bundles with Rolldown. Add `vite` as an exact dev dependency at 8.3.4 until 2026-10-28, because 8.3.5 came out on 2026-10-21, inside the cooldown of `aidd-team:dependency-upgrade`.
- Turn on the React Compiler with `@vitejs/plugin-react` 6. Pass `babel({ presets: [reactCompilerPreset()] })`, from `@rolldown/plugin-babel`, after `react()`. Add `babel-plugin-react-compiler` 1.0.0 and `@babel/core` as exact dev dependencies.
- Lint with the `recommended-latest` preset of `eslint-plugin-react-hooks` too. Each component or hook it reports is one the compiler leaves as written.
- Write one file per route under `src/routes/`. The plugin writes `src/routeTree.gen.ts`: commit it, and exclude it from Biome.
- Declare each route's search params with a Zod schema in `validateSearch`, so a link with a wrong param fails the type check.
- Load a route's data in its `loader` through the query cache of `typescript/tanstack-query`, never in an effect.
- Give each route an `errorComponent` and a `pendingComponent`, so every state has a screen.
- Serve the build as static files with a fallback to `index.html`, under the same security headers as any page.
- When a screen needs server rendering or server functions, move to TanStack Start, which is built on this router. `typescript/tanstack-start` holds it as an emerging choice, with the patched release its gate checks.

## What the gate runs

One `tests` entry builds with Vite, fails when the committed route tree differs from the one the build wrote, and then runs `tsc --noEmit` over every typed link.
