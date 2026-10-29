---
id: typescript/tanstack-start
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, security-engineer, reviewer]
when_changed: ["src/**", vite.config.ts, tsconfig.json, package.json, pnpm-lock.yaml]
why: "TanStack Start adds server rendering, streaming, and typed server functions to the routes of TanStack Router, built by Vite, so a React app can move work to the server without changing how it is written."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: tanstack-start
  registry: npm
  package: "@tanstack/react-start"
version_policy: current_major
checked_version: "1.169.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.169.3"
source: https://tanstack.com/blog/tanstack-start-security-update-cve-2026-102989
evidence: "Update your Start dependencies and lockfile, confirm that the resolved @tanstack/start-server-core version is 1.169.39 or later, then rebuild and redeploy."
alternatives: [Next.js, React Router, TanStack Router]
status: active
enforced_by:
  - name: build
    command:
      - sh
      - -c
      - "pnpm exec vite build && git diff --exit-code -- src/routeTree.gen.ts && pnpm exec tsc --noEmit"
  - name: floor
    command:
      - node
      - -e
      - "const r=require.resolve('@tanstack/react-start/package.json'), s=require.resolve('@tanstack/start-server-core/package.json', {paths: [r]}), atLeast=(f, m)=>{const v=require(f).version.split('.').map(Number); return (v[0]-m[0] || v[1]-m[1] || v[2]-m[2]) >= 0}; process.exit(atLeast(r, [1, 168, 60]) && atLeast(s, [1, 169, 39]) ? 0 : 1)"
---

# TanStack Start renders the React app on the server, on TanStack Router

It answers the web-framework choice of `aidd-team:web-front-end` for a React app on typed routes that needs server rendering or server functions. License: MIT. It's emerging, because 1.0 shipped on 2026-10-13 and a critical XSS fix came two weeks before. Review it every month. `typescript/nextjs-app-router` stays the default of the `ts-web` stack. In the `ts-web-spa` stack, Start is the later swap for `typescript/tanstack-router`, because Start is built on that router.

## What the team does

- Add `@tanstack/react-start` as an exact dependency, at 1.168.60 or later, so the lockfile resolves `@tanstack/start-server-core` 1.169.39 or later. After an upgrade, rebuild and redeploy.
- Write routes as `typescript/tanstack-router` says. Start writes the same `src/routeTree.gen.ts`.
- Give every server function a Zod schema in `.validator()`, as `typescript/zod-validation` says. Treat its input as untrusted, and check the user's access inside the handler.
- Keep Start's CSRF middleware on server functions. When you write `src/start.ts`, add `createCsrfMiddleware()` there yourself.
- Load data in route loaders, through the query cache of `typescript/tanstack-query`.
- Cover the server render and the hydration of each journey with a `typescript/playwright-e2e` test against the production build.
- Build with `vite build`, with `tanstackStart()` before `@vitejs/plugin-react`. Deploy through the `nitro()` Vite plugin, or the host's own plugin that Start's hosting guide names.
- Keep secrets out of `VITE_` variables, because Vite puts them in the browser code.
- Leave Server Components off. They're an experimental add-on in Start, so turn them on only in a change of their own.

## What the gate runs

One `tests` entry builds with Vite, fails when the committed route tree differs, and runs `tsc --noEmit`. A second fails when the installed `@tanstack/react-start`, or the `@tanstack/start-server-core` it resolves, is older than the CVE-2026-102989 fix.
