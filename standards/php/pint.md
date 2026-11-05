---
id: php/pint
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.php", pint.json]
why: "Pint comes with every new Laravel app and fixes the PHP code style with Laravel's preset and no configuration, on top of PHP CS Fixer, so CI and every machine lay out the code the same way."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://laravel.com/docs/pint
evidence: "Pint is automatically installed with all new Laravel applications"
alternatives: [PHP CS Fixer, PHP_CodeSniffer]
status: active
enforced_by:
  - name: format
    command: ["./vendor/bin/pint", --test]
---

# Pint sets the layout of the PHP code

It answers the formatter choice of `aidd-team:ci-pipeline` for PHP.

## What the team does

- Keep `laravel/pint` in `require-dev`, where a new app has it. An older app adds it with `composer require laravel/pint --dev`.
- Keep the `laravel` preset, unless the whole repository moves to `per` or `psr12`, once, in `pint.json`.
- Run `./vendor/bin/pint --dirty` in the pre-commit hook. It fixes only the files with uncommitted changes.
- Format Blade templates only through the `Pint/laravel_blade` rule, which needs Node.js and Prettier on every machine and in CI.
- Run `--test` in CI, never a job that commits Pint's fixes back to the branch, so every change to the code passes through its author.

## What the tests run

One `tests` entry runs `./vendor/bin/pint --test`, which changes no file and exits non-zero on a style error. That fails the change.
