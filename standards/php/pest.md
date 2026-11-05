---
id: php/pest
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: ["app/**", "routes/**", "database/**", "tests/**", phpunit.xml, composer.lock]
why: "A new Laravel app supports Pest and PHPUnit out of the box, and `php artisan test` runs either with the same arguments, so the team writes short Pest tests behind one runner command."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://laravel.com/docs/testing
evidence: "support for testing with Pest and PHPUnit is included out of the box"
alternatives: [PHPUnit]
status: active
enforced_by:
  - name: test
    command: [php, artisan, test]
---

# Pest runs the Laravel app's tests

It answers the test-runner choice of `aidd-team:ci-pipeline` for PHP.

## What the team does

- Write most tests as feature tests in `tests/Feature`, as Laravel's guide advises. Keep `tests/Unit` for code that needs no booted app.
- Set the `testing` environment in `phpunit.xml` or `.env.testing`, and point it at a throwaway database, never a shared one.
- Run `php artisan config:clear` before the suite, because a cached configuration hides the testing values.
- Replace each outside service with a fake in feature tests, so the suite never calls a real provider.
- To run in parallel, add `brianium/paratest` as a dev dependency and pass `--parallel`. Laravel then gives each process its own test database.

## What the tests run

One `tests` entry runs `php artisan test`, which runs Pest, or PHPUnit in an app that uses it. A failed test fails the change.
