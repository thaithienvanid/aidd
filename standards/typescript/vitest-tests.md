---
id: typescript/vitest-tests
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: test-design:Flake check
roles: [developer, tester, reviewer]
when_changed: ["**/*.ts", "**/*.tsx", package.json, vitest.config.ts, vite.config.ts]
why: "Vitest runs TypeScript tests natively, with the same transform as the Vite build and a Jest-compatible API, and isolates each test file by default."
reviewed: "2026-10-16"
maturity: established
tool:
  name: vitest
  registry: npm
  package: vitest
version_policy: current_stable
checked_version: "5.0.5"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/vitest/dist-tags
evidence: "\"latest\":\"5.0.5\""
pin: "5.0.3"
alternatives: [Jest, node:test]
status: active
enforced_by:
  - name: unit
    command: [pnpm, exec, vitest, run]
---

# Vitest runs the TypeScript tests

It answers the test-runner choice of `aidd-team:ci-pipeline`.

## What the team does

- Add `vitest` as an exact dev dependency, and keep its settings in `vitest.config.ts`.
- Put a unit test beside its module as `*.test.ts`. Keep slower integration suites in a separate Vitest project.
- Shuffle the test order in CI (`sequence.shuffle`), so a test that leans on another one fails early.
- Keep `retry` at 0 in CI. For the Flake check of `aidd-team:test-design`, rerun a new test with the `repeats` option.
- Never commit `.only` or `.skip` without an issue link beside it.
- Set a coverage floor with `@vitest/coverage-v8` and raise it as the code grows; never lower it to pass.

## What the gate runs

One `tests` entry runs `vitest run` once, with no watch mode. A failing test fails the change.
