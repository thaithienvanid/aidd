---
id: typescript/nx-workspace
type: opinionated
fills: [ci-pipeline:workspace]
default: false
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [nx.json, "**/project.json", pnpm-workspace.yaml, pnpm-lock.yaml, package.json, "**/package.json"]
why: "Nx builds a project graph of the whole repository, runs each task in dependency order with a cache, and runs only the projects a change affects, which helps a large repository most."
reviewed: "2026-10-16"
maturity: established
tool:
  name: nx
  registry: npm
  package: nx
version_policy: current_stable
checked_version: "23.3.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/nx/dist-tags
evidence: "\"latest\":\"23.3.0\""
pin: "23.3.0"
alternatives: [pnpm workspaces with Turborepo]
status: active
enforced_by:
  - name: build
    command: [pnpm, exec, nx, run-many, -t, build]
---

# Nx holds the TypeScript apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for a large TypeScript repository. `nx` is MIT. Its Conformance plugin needs a commercial license, and this standard does not use it. `typescript/pnpm-turborepo-workspace` stays the default.

## What the team does

- Keep pnpm workspaces from `typescript/pnpm-tooling` for the packages. Nx reads them as projects.
- Add `nx` at `pin` as an exact dev dependency of the root. pnpm runs its install script only after a ruling in `allowBuilds`.
- Give each module a `project.json` with its targets. Set `dependsOn: ["^build"]` for `build` in `targetDefaults` of `nx.json`.
- Name each target's `outputs`, so the cache restores them.
- For the boundary check on Nx, adopt `typescript/nx-module-boundaries`.

## What the gate runs

One `tests` entry runs the `build` target of every project in dependency order. A failed build fails the change. A long pipeline can run `nx affected -t build` with the base commit instead.
