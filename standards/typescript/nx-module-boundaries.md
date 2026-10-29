---
id: typescript/nx-module-boundaries
type: opinionated
fills: [modular-monolith:module-boundaries]
default: false
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed:
  - "apps/**"
  - "modules/**"
  - "packages/**"
  - "**/project.json"
  - nx.json
  - "eslint.config.*"
  - boundaries-baseline.json
  - package.json
why: "Nx's enforce-module-boundaries rule checks the tags of each project and the cycles between projects, so a team that already runs Nx and ESLint gets the boundary check from the same tool."
reviewed: "2026-10-16"
maturity: established
tool:
  name: nx-eslint-plugin
  registry: npm
  package: "@nx/eslint-plugin"
version_policy: current_stable
checked_version: "23.3.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://nx.dev/docs/technologies/eslint/eslint-plugin/guides/enforce-module-boundaries
evidence: "This rule only works for JavaScript/TypeScript projects. It runs on ESLint, and experimentally on Oxlint."
pin: "23.3.0"
alternatives: [dependency-cruiser, eslint-plugin-boundaries]
status: active
enforced_by:
  - name: boundaries
    command: [pnpm, exec, nx, run-many, -t, lint]
---

# Nx enforce-module-boundaries checks the TypeScript module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for a TypeScript team on Nx (`typescript/nx-workspace`). `@nx/eslint-plugin` is MIT. `typescript/dependency-cruiser` stays the default.

The rule needs ESLint. With `typescript/biome-lint-format`, the team runs ESLint for this rule only, or adopts `typescript/eslint-prettier`. Nx's Conformance plugin also checks project boundaries, but it needs a commercial license. This standard does not use it.

## What the team does

- Add `@nx/eslint-plugin` at `pin` as an exact dev dependency, at the same version as `nx`.
- Make each module an Nx project. Give it tags in its `project.json`, such as `scope:orders` and `type:api`.
- Turn on `@nx/enforce-module-boundaries` as an error in `eslint.config.mjs`. Write one `depConstraints` entry for each dependency rule of the skill, with `onlyDependOnLibsWithTags`.
- Keep the check for cycles between projects on. Keep the known cycles in `boundaries-baseline.json`, and load it in `eslint.config.mjs` as `ignoredCircularDependencies`.
- That list holds cycles only. A `depConstraints` violation has no baseline: fix it before the merge, or widen the constraint in an ADR.
- Give each project a `lint` target.

## What the gate runs

One `tests` entry runs the `lint` target of every project. A dependency that breaks a constraint, or a cycle between projects, is an ESLint error and fails the change.
