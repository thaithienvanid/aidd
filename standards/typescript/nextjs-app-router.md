---
id: typescript/nextjs-app-router
type: opinionated
fills: [web-front-end:web-framework]
default: true
implements: product-defaults:perf_budget
roles: [developer, product-designer, reviewer]
when_changed: ["app/**", "src/app/**", "components/**", next.config.ts, next.config.mjs, package.json]
why: "Next.js renders React on the server with the App Router, streams each page, and ships only the client components a page needs, which fits the server-rendered default and the performance budget."
reviewed: "2026-10-22"
maturity: established
tool:
  name: next
  registry: npm
  package: next
version_policy: current_major
checked_version: "16.4.2"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/next/dist-tags
evidence: "\"latest\":\"16.4.2\""
alternatives: [React Router, Astro, SvelteKit]
status: active
enforced_by:
  - name: build
    command: [pnpm, exec, next, build]
---

# Next.js with the App Router renders the web front end

It answers the web-framework choice of `aidd-team:web-front-end`.

## What the team does

- Build pages under `app/` with the App Router. Leave a component on the server unless it needs state, effects, or a browser API.
- Mark the smallest client boundary with `'use client'`, and pass it plain props only.
- Read data in server components or route handlers. Validate each server action's input as untrusted, with the project's validation library.
- Set the Content Security Policy with a nonce in `proxy.ts`, and the other security headers in `next.config.ts`.
- Use `next/image` and `next/font`, so images and fonts stay within the performance budget.
- Turn on the React Compiler with `reactCompiler: true` in `next.config.ts`, a top-level option since Next.js 16. Add `babel-plugin-react-compiler` (1.0.0 here) as an exact dev dependency.
- Run `eslint-plugin-react-hooks` with its `recommended-latest` preset beside the main linter. The compiler skips each component or hook that those rules report, so the findings list what it left unoptimized.

## What the gate runs

One `tests` entry runs `next build`. A type error, a broken server and client boundary, or a failed page fails the change.
