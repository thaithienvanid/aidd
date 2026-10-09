+++
id = "typescript/tsc-strict"
type = "opinionated"
fills = ["ci-pipeline:type-checker"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts", "tsconfig.json", "**/tsconfig*.json"]
why = "The TypeScript compiler is the reference checker for the language, and its strict mode catches null, any, and unchecked-call mistakes before a test runs."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "typescript", registry = "npm", package = "typescript" }
version_policy = "current_stable"
checked_version = "7.0.2"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/typescript/dist-tags"
evidence = '"latest":"7.0.2"'
pin = "7.0.2"
alternatives = ["tsc without strict, tightened file by file"]
status = "active"
enforced_by = [
  { name = "types", command = ["pnpm", "exec", "tsc", "--noEmit"] },
]
+++

# tsc in strict mode checks the TypeScript types

It answers the type-checker choice of `aidd-team:ci-pipeline`.

## What the team does

- Add `typescript` as an exact dev dependency, so the editor and CI run one compiler. With `typescript/eslint-prettier`, install it under the `@typescript/native` alias that standard names.
- Write `"strict": true` in the root `tsconfig.json` even where it is the default, and add `noUncheckedIndexedAccess` and `noImplicitOverride`.
- In a monorepo, give each package its own `tsconfig.json` that extends the root one, and check them all.
- Give every exported function its parameter and return types.
- Prefer `unknown` to `any`. Write the reason on each `@ts-expect-error`; a bare `@ts-ignore` is a review finding.

## What the gate runs

One `[[tests]]` entry runs `tsc --noEmit` with the project's compiler. A type error fails the change.
