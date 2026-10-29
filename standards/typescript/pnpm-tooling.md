---
id: typescript/pnpm-tooling
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [package.json, pnpm-lock.yaml, pnpm-workspace.yaml, "**/package.json"]
why: "pnpm installs from one content-addressed store with a strict node_modules, so a package can import only what it declares, and its lockfile makes every machine and CI install the same tree."
reviewed: "2026-10-16"
maturity: established
tool:
  name: pnpm
  registry: npm
  package: pnpm
version_policy: current_stable
checked_version: "12.14.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/pnpm/dist-tags
evidence: "\"latest\":\"12.14.0\""
pin: "12.14.0"
alternatives: [npm, Yarn, Bun]
status: active
enforced_by:
  - name: lock
    command: [pnpm, install, --frozen-lockfile]
---

# pnpm installs and locks the TypeScript dependencies

It answers the package-manager choice of `aidd-team:ci-pipeline`.

## What the team does

- Declare every dependency in `package.json`, and commit `pnpm-lock.yaml`.
- Pin pnpm itself in the `packageManager` field of the root `package.json`, so each machine runs the same release.
- Keep a monorepo's packages in `pnpm-workspace.yaml`, and refer to a sibling with `workspace:*`.
- Add a dependency with `pnpm add --save-exact` for a tool, so its version changes only in a reviewed change.
- Never import a package the manifest does not name; pnpm's strict layout turns that into an error.
- pnpm 12 runs no dependency's install script until the project rules on it, and `pnpm install` fails with `ERR_PNPM_IGNORED_BUILDS` on one nobody has ruled on. Record each ruling in the `allowBuilds` map of `pnpm-workspace.yaml`: `true` runs the script, `false` skips it. `pnpm approve-builds <name>` writes the entry. In aidd's TypeScript standards, these packages have one: `@ariga/atlas`, which downloads its binary; `esbuild`, through drizzle-kit and wrangler; `workerd`, through wrangler; `prisma` and `@prisma/engines`; `nx`, through the Nx standards; and `ssh2` and `cpu-features`, through testcontainers.

## What the gate runs

One `tests` entry installs with `--frozen-lockfile`. A lockfile that no longer matches the manifests fails the change.
