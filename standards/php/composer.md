---
id: php/composer
type: opinionated
fills: [ci-pipeline:package-manager, ci-pipeline:dependency-audit]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [composer.json, composer.lock]
why: "Composer installs the exact versions that the committed composer.lock records, and its own audit checks those locked packages, so CI builds and audits what production runs."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://getcomposer.org/doc/03-cli.md
evidence: "it will use the exact versions from there instead of resolving them."
status: active
enforced_by:
  - name: lock
    command: [composer, validate, --strict]
  - name: audit
    command: [composer, audit, --locked]
---

# Composer installs, locks, and audits the PHP dependencies

It answers the package-manager and dependency-audit choices of `aidd-team:ci-pipeline` for PHP.

## What the team does

- Commit `composer.lock`. Install with `composer install` in CI and on each deploy, never with `composer update`.
- Change a dependency with `composer require` or `composer update <package>`, in the same change as the code that needs it.
- Run `composer audit --locked` beside OSV-Scanner, the Dependency scan of `aidd-team:enterprise-controls`. It reads the lock, whatever the `vendor` folder holds.

## What the tests run

Two `tests` entries. `composer validate --strict` fails when `composer.lock` is out of date with `composer.json`, and on any warning. `composer audit --locked` exits non-zero on a locked package that its policies flag. Either fails the change.
