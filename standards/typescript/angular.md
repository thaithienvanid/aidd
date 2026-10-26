---
id: typescript/angular
type: opinionated
fills: [web-front-end:web-framework]
default: false
implements: product-defaults:perf_budget
roles: [developer, architect, reviewer]
when_changed: ["src/**", angular.json, "tsconfig*.json", package.json]
why: "Angular is one framework with routing, forms, an HTTP client, and server rendering from one team, on a fixed release schedule with long-term support, for a team that wants those decisions made once."
reviewed: "2026-10-22"
maturity: established
tool:
  name: angular
  registry: npm
  package: "@angular/core"
version_policy: current_major
checked_version: "22.2.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://angular.dev/guide/zoneless
evidence: "Zoneless is the default in Angular v21+ so you do not need to do anything to enable it."
alternatives: [Next.js, Nuxt, SvelteKit]
status: active
enforced_by:
  - name: build
    command: [pnpm, exec, ng, build]
  - name: unit
    command: [pnpm, exec, ng, test, --watch=false]
---

# Angular renders the web front end

It answers the web-framework choice of `aidd-team:web-front-end` for a team that writes Angular. License: MIT. `typescript/nextjs-app-router` stays the default.

## What the team does

- Create the app with `ng new` at the checked major. Add `--ssr` for any public page, so the server renders it.
- Write standalone components only, with no `NgModule`. Hold component state in signals (`signal`, `computed`, `input`), and use `OnPush` change detection.
- Stay zoneless, the default: never add `zone.js` or `provideZoneChangeDetection`.
- Keep the CLI's strict template checks on.
- Unit tests run on Vitest, the CLI's default runner, through `ng test`; skip `typescript/vitest-tests`, whose bare `vitest run` misses the CLI's build. Keep `typescript/playwright-e2e` for the journeys.
- Lint with angular-eslint (`ng add angular-eslint`) under `typescript/eslint-prettier`. Biome's language support lists HTML, Vue, Svelte, and Astro but not Angular templates, so it would skip every binding and `@if` block.
- `@angular/compiler-cli` 22.2.3 accepts TypeScript `>=6.0 <6.1`. Install TypeScript 6 and 7 side by side, as `typescript/eslint-prettier` says. The root `tsconfig.json` lists no files, so `ng build` is the type check that reads the components and their templates.

## What the gate runs

Two `tests` entries. `ng build` compiles every template ahead of time and fails on a type or template error. `ng test --watch=false` runs the unit tests once.
