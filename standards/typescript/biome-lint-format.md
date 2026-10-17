---
id: typescript/biome-lint-format
type: opinionated
fills: [ci-pipeline:linter, ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.json", "**/*.css", biome.json, biome.jsonc]
why: "One fast tool lints and formats TypeScript, JavaScript, JSON, and CSS from one biome.json, so CI, the pre-commit hook, and every editor give the same answer."
reviewed: "2026-10-16"
maturity: established
tool:
  name: biome
  registry: npm
  package: "@biomejs/biome"
version_policy: current_stable
checked_version: "2.5.15"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@biomejs/biome/dist-tags
evidence: "\"latest\":\"2.5.15\""
pin: "2.5.15"
alternatives: [ESLint with Prettier, oxlint with Prettier]
status: active
enforced_by:
  - name: ci
    command: [pnpm, exec, biome, ci, "."]
---

# Biome lints and formats the TypeScript code

It answers the linter and formatter choices of `aidd-team:ci-pipeline`.

## What the team does

- Add `@biomejs/biome` as an exact dev dependency, and configure it once in `biome.json` at the root.
- Start from the recommended rules. Write the reason beside each rule you turn off.
- Run the pinned Biome in the pre-commit hook as well, with `biome check --write` on the staged files.
- Format before each commit, so nobody asks for a layout change by hand.
- Keep the ESLint plugins a pack names for its own check, such as accessibility rules; Biome stays the main linter and the only formatter.

## What the gate runs

One `tests` entry runs `biome ci`, which checks the format and the lint rules without writing a file. A finding fails the change.
