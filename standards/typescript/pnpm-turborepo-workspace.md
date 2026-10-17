---
id: typescript/pnpm-turborepo-workspace
type: opinionated
fills: [ci-pipeline:workspace]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [pnpm-workspace.yaml, pnpm-lock.yaml, package.json, "**/package.json", turbo.json, "**/turbo.json"]
why: "pnpm workspaces hold every app, module, and package with one lockfile, and Turborepo runs their tasks in dependency order with a cache, so a change rebuilds only what it touches."
reviewed: "2026-10-16"
maturity: established
tool:
  name: turbo
  registry: npm
  package: turbo
version_policy: current_stable
checked_version: "2.11.7"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://turborepo.com/docs/crafting-your-repository/structuring-a-repository
evidence: "turbo is built on top of Workspaces, a feature of package managers in the JavaScript ecosystem that allows you to group multiple packages in one repository."
pin: "2.11.7"
alternatives: [Nx, pnpm workspaces alone]
status: active
enforced_by:
  - name: dedupe
    command: [pnpm, dedupe, --check]
  - name: build
    command: [pnpm, exec, turbo, run, build]
---

# pnpm workspaces and Turborepo hold the TypeScript apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for TypeScript, on Node.js and on Cloudflare Workers. pnpm and Turborepo are MIT. It builds on `typescript/pnpm-tooling`, which installs and locks the dependencies.

## What the team does

- List `apps/*`, `modules/*`, and `packages/*` in `pnpm-workspace.yaml`. Give each module its own `package.json`, and name it `@<project>/<module>`.
- Depend on a sibling with `workspace:*`, and declare it in the package that imports it.
- Keep one version of each dependency. Put shared versions in the `catalog` of `pnpm-workspace.yaml`, and refer to them with `catalog:`.
- Add `turbo` at `pin` as an exact dev dependency of the root. Define the `build`, `lint`, and `test` tasks in `turbo.json`, with `dependsOn: ["^build"]` for `build`.
- Give each task its `outputs`, so the cache restores them.

## What the gate runs

Two `tests` entries. `pnpm dedupe --check` exits non-zero when a dedupe would change the lockfile, so two versions of a dependency that could be one fail the change. Then `turbo run build` builds every package in dependency order, and a failed build fails the change.
