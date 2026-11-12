---
id: php/php-version
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [composer.json, composer.lock]
why: "Each PHP branch gets two years of full support, then two of security fixes only, so the project names its PHP floor in composer.json and checks the locked packages against it."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://www.php.net/supported-versions.php
  quote: "Each release branch of PHP is fully supported for two years"
alternatives: ["a toolchain file, such as mise.toml, beside the constraint"]
status: active
enforced_by:
  - name: platform
    command: [composer, check-platform-reqs, --lock]
---

# composer.json names the PHP version

It answers the language-version choice of `aidd-team:ci-pipeline` for PHP.

## What the team does

- Pick a PHP branch in active support that the framework in use also supports. Laravel's release notes list the PHP versions of each major.
- Name that branch as the floor in `require.php` of `composer.json`.
- Install the same PHP release in CI and on every machine, from one file they all read, as `ci-pipeline:toolchain-manager` sets.
- Move to a newer PHP branch in its own change, before the one in use leaves active support. Run the whole suite on it first.

## What the tests run

One `tests` entry runs `composer check-platform-reqs --lock`. It checks the PHP and its extensions against the requirements of the locked packages, and a mismatch fails the change.
