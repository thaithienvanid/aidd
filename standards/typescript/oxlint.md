---
id: typescript/oxlint
type: opinionated
fills: [ci-pipeline:linter]
default: false
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", ".oxlintrc.json", oxlint.config.ts, "tsconfig*.json"]
why: "Oxlint runs typescript-eslint's type-aware rules on TypeScript 7 itself, through tsgolint, so a large code base gets rules that read the types without a TypeScript 6 copy. Its maintainers measured it at 12 to 18 times faster than ESLint."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: oxlint
  registry: npm
  package: oxlint
version_policy: current_stable
checked_version: "1.89.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://oxc.rs/blog/2026-07-22-type-aware-linting-stable
evidence: "This release tracks TypeScript v7.0.2 and brings tsgolint to 59 of typescript-eslint's 61 type-aware rules."
pin: "1.88.0"
cooldown_until: "2026-10-26"
alternatives: [Biome, ESLint with Prettier]
status: active
enforced_by:
  - name: lint
    command: [pnpm, exec, oxlint, --type-aware, --deny-warnings]
---

# Oxlint checks the TypeScript code, with type-aware rules

It answers the linter choice of `aidd-team:ci-pipeline`, for a team that wants rules that read the types on TypeScript 7. License: MIT for Oxlint and tsgolint. `typescript/biome-lint-format` stays the default. Type-aware linting went stable on 2026-07-22, so this choice is emerging.

Oxlint 1.89.0 came out on 2026-10-19, a minor inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 1.88.0 until `cooldown_until`.

## What the team does

- Add `oxlint` at `pin` and `oxlint-tsgolint` as exact dev dependencies. A tsgolint version names the TypeScript release it is built on: 7.0.2004 is built on TypeScript 7.0.2, the `typescript/tsc-strict` pin. Move the two together.
- Configure Oxlint once in `.oxlintrc.json` or `oxlint.config.ts`, and write the reason beside each rule you turn off.
- Run the same command in the pre-commit hook, on the staged files.
- Oxlint does not format. Biome and ESLint with Prettier each fill the linter choice too, so a project cannot add either beside this one. Write the project's own formatter standard instead: Prettier (3.9.10 here) with `prettier . --check`, or `biome format` with Biome's linter off.

## What the gate runs

One `tests` entry runs `oxlint --type-aware --deny-warnings`, which turns each warning into a failure. A finding fails the change.
