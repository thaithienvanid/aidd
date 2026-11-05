---
id: php/larastan
type: opinionated
fills: [ci-pipeline:linter, ci-pipeline:type-checker]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.php", phpstan.neon, phpstan.neon.dist, composer.lock]
why: "Larastan adds code analysis for Laravel to PHPStan, under the MIT License, so type errors and wrong calls that PHP finds only at run time fail in CI first."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://github.com/larastan/larastan
  quote: "Adds code analysis to Laravel improving developer productivity and code quality."
alternatives: [PHPStan alone, Psalm]
status: active
enforced_by:
  - name: analyse
    command: ["./vendor/bin/phpstan", analyse]
---

# Larastan, on PHPStan, checks the types of the Laravel code

It answers the linter and type-checker choices of `aidd-team:ci-pipeline` for PHP. PHP checks its types only when the code runs, so static analysis does both jobs before it does.

## What the team does

- Add it with `composer require --dev larastan/larastan`, and include `vendor/larastan/larastan/extension.neon` in `phpstan.neon`.
- Set a `level` in `phpstan.neon`, and raise it as the code allows. Level 10 is the highest.
- In an older code base, start from a PHPStan baseline of today's errors and commit it. Let the baseline only shrink.
- Write the reason beside each ignored error. A bare ignore is a review finding.

## What the tests run

One `tests` entry runs `./vendor/bin/phpstan analyse` with the project's `phpstan.neon`. An error at the set level fails the change.
