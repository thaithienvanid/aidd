+++
id = "typescript/eslint-prettier"
type = "opinionated"
fills = ["ci-pipeline:linter", "ci-pipeline:formatter"]
default = false
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.json", "**/*.css", "eslint.config.*", ".prettierrc*", "prettier.config.*"]
why = "ESLint has the largest plugin ecosystem and, with typescript-eslint, rules that read the type checker; Prettier formats the code, so a team that needs those plugins or type-aware rules gets them."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "eslint", registry = "npm", package = "eslint" }
version_policy = "current_stable"
checked_version = "10.12.0"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/eslint/dist-tags"
evidence = '"latest":"10.12.0"'
pin = "10.12.0"
alternatives = ["Biome", "oxlint with Prettier"]
status = "active"
enforced_by = [
  { name = "lint", command = ["pnpm", "exec", "eslint", ".", "--max-warnings", "0"] },
  { name = "format", command = ["pnpm", "exec", "prettier", ".", "--check"] },
]
+++

# ESLint and Prettier lint and format the TypeScript code

It answers the linter and formatter choices of `aidd-team:ci-pipeline`, for a team that needs ESLint's plugins or type-aware rules. Licence: MIT for ESLint, typescript-eslint, and Prettier. `typescript/biome-lint-format` stays the default.

## What the team does

- Add `eslint` at `pin`, `prettier` (3.9.9 when this file was checked), `typescript-eslint`, and `eslint-config-prettier` as exact dev dependencies.
- typescript-eslint reads the TypeScript 6 API: its 8.71.1 release accepts TypeScript `>=4.8.4 <6.1.0`, and `typescript/tsc-strict` pins TypeScript 7. Install both side by side, as the TypeScript 7.0 announcement shows: `"typescript": "npm:@typescript/typescript6@6.0.2"` for the tooling, and `"@typescript/native": "npm:typescript@7.0.2"` for `tsc`. The first gives only a `tsc6` executable, so `tsc` stays TypeScript 7.
- Configure ESLint once in `eslint.config.js` (flat config). Extend `tseslint.configs.recommendedTypeChecked` with `parserOptions.projectService` on, and put `eslint-config-prettier` last, so no ESLint rule fights the formatter.
- Leave layout to Prettier and code quality to ESLint. Do not run Prettier as an ESLint rule.
- Write the reason beside each rule you turn off.
- Run both on the staged files in the pre-commit hook, with `--fix` and `--write`.

## What the gate runs

Two `[[tests]]` entries: `eslint . --max-warnings 0`, then `prettier . --check`, which lists each file it would change and writes none. A finding of either fails the change.
