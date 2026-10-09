+++
id = "typescript/dependency-cruiser"
type = "opinionated"
fills = ["modular-monolith:module-boundaries"]
default = true
implements = "modular-monolith:Boundary check"
roles = ["architect", "developer", "reviewer"]
when_changed = ["apps/**", "modules/**", "packages/**", ".dependency-cruiser.cjs", "boundaries-baseline.json", "package.json"]
why = "dependency-cruiser checks the import rules and cycles without a linter, so it runs beside Biome, and it keeps a baseline of known violations so only a new one fails."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "dependency-cruiser", registry = "npm", package = "dependency-cruiser" }
version_policy = "current_stable"
checked_version = "18.5.0"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/dependency-cruiser/dist-tags"
evidence = '"latest":"18.5.0"'
pin = "18.5.0"
alternatives = ["Nx enforce-module-boundaries (runs on ESLint)", "eslint-plugin-boundaries (runs on ESLint)"]
status = "active"
enforced_by = [
  { name = "boundaries", command = ["pnpm", "exec", "depcruise", "apps", "modules", "packages", "--config", ".dependency-cruiser.cjs", "--ignore-known", "boundaries-baseline.json"] },
]
+++

# dependency-cruiser checks the TypeScript module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for TypeScript, on Node.js and on Cloudflare Workers. dependency-cruiser is MIT. It needs no linter, so it works beside `typescript/biome-lint-format`.

## What the team does

- Add `dependency-cruiser` at `pin` as an exact dev dependency. Run `pnpm exec depcruise --init` once, and save the result as `.dependency-cruiser.cjs`.
- Write one `forbidden` rule for each dependency rule of the skill. Use group matching on `^modules/([^/]+)/`, so one rule covers every module.
- Keep the `no-circular` rule that `--init` writes. Add a `circular` rule with `scope: "folder"` for the folders under `modules/`.
- The folder rule compares the deepest folders only. A cycle such as `orders/internal` to `billing/api` and `billing/internal` to `orders/api` passes. So a reviewer keeps the module graph acyclic: draw it from the imports between modules, and refuse an import that closes a loop.
- Write the violations baseline with `--baseline boundaries-baseline.json`, also when it is empty. After that, update it only with `--baseline-mode shrink-only`.
- `--ignore-known` hides the known violations of rules on files, such as an import of another module's `internal/`. It never hides a folder cycle, even one that `--baseline` wrote. Fix a folder cycle before the merge. To keep one, name its folders in the folder rule's `from.pathNot`, with the reason and its ADR in a comment.
- On Workers, the check runs in CI on Node.js. The Worker never loads it.

## What the gate runs

One `[[tests]]` entry cruises `apps/`, `modules/`, and `packages/` with the default `err` reporter. Its exit code is the number of violations with severity `error`, so one new violation fails the change. The violations in `boundaries-baseline.json` are ignored. Its config and its baseline are both the violations baseline for the gate (`baseline:module-boundaries`).
