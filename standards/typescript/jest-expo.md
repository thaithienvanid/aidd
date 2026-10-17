---
id: typescript/jest-expo
type: opinionated
fills: [ci-pipeline:test-runner]
default: false
implements: test-design:Flake check
roles: [developer, tester, reviewer]
when_changed: ["**/*.ts", "**/*.tsx", package.json, jest.config.js, jest.config.ts, app.json, app.config.ts]
why: "Expo's unit-testing guide sets up Jest with the jest-expo preset, which mocks the native part of the Expo SDK, and it documents no other runner, so an Expo app follows the path its SDK supports."
reviewed: "2026-10-16"
maturity: established
tool:
  name: jest-expo
  registry: npm
  package: jest-expo
version_policy: current_stable
checked_version: "57.0.5"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://docs.expo.dev/develop/unit-testing/
evidence: "You will also use the jest-expo library, which is a Jest preset that mocks the native part of the Expo SDK and handles most of the configuration required for your Expo project."
alternatives: [Vitest (not covered by Expo's guide)]
status: active
enforced_by:
  - name: unit
    command: [pnpm, exec, jest, --ci]
---

# Jest with jest-expo runs the Expo app's unit tests

It answers the test-runner choice of `aidd-team:ci-pipeline` for an Expo app. License: MIT for Jest and jest-expo. `typescript/vitest-tests` stays the default for TypeScript outside Expo.

## What the team does

- Install with `npx expo install jest-expo jest @types/jest -- --dev`, so the preset's major matches the Expo SDK (57 when this file was checked). Move it with the SDK, never on its own.
- Set `"preset": "jest-expo"` in the Jest config, and widen `transformIgnorePatterns` only for a package that ships untranspiled code.
- Put a unit test beside its component as `*.test.tsx`, and test what a person sees with `@testing-library/react-native`.
- Keep `--watchAll` for local work only; CI runs once with `--ci`, which fails on a missing snapshot instead of writing it.
- Never commit `.only` or `.skip` without an issue link beside it. Rerun a new test several times before merging, for the Flake check of `aidd-team:test-design`.

## What the gate runs

One `tests` entry runs `jest --ci` once. A failing test, or a snapshot that is missing, fails the change.
