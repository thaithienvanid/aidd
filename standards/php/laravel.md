---
id: php/laravel
type: opinionated
fills: [apis-and-services:api-framework, schema-migration:orm, schema-migration:migration-tool]
default: true
implements: schema-migration:Migration up and down
roles: [architect, developer, reviewer]
when_changed: ["app/**", "routes/**", "config/**", "database/migrations/**", composer.json, composer.lock]
why: "Laravel holds routing, validation, the Eloquent ORM, migrations, queues, and testing in one framework, with a new major each year and security fixes for two years, so one option covers the app, its API, and its data."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://laravel.com/docs/releases
  quote: "For all Laravel releases, bug fixes are provided for 18 months"
alternatives: [Symfony, Slim]
status: active
enforced_by:
  - name: migrations
    command: [php, artisan, test, --group=migrations]
---

# Laravel serves the PHP web app and its API, and owns its data

It fills three choices at once: the api-framework choice of `aidd-packs:apis-and-services`, and the orm and migration-tool choices of `aidd-team:schema-migration`. Eloquent maps the models and Laravel's migrations change the schema, so a project that adopts it adds no other standard for these choices.

## What the team does

- Require `laravel/framework` with a caret constraint on the current major, as Laravel's release notes advise. A minor or a patch then arrives through `composer.lock`, and a major is a change of its own.
- Move to each new major while the one in use still gets bug fixes. A major arrives once a year, around the first quarter.
- Never call a Laravel method with named arguments, because Laravel's compatibility promise does not cover parameter names.
- Validate each request with Laravel's validation before its data reaches a model. Shape API responses with resources.
- Write each schema change as a migration with both an `up` and a `down` method. Read a risky one's SQL with `migrate --pretend` first.
- Keep one feature test in the `migrations` group that runs `migrate:refresh`.
- Deploy from several servers with `migrate --isolated`, so only one of them migrates.
- Run `migrate:fresh` only on a database that nothing else shares, because it drops every table, whatever its prefix.
- Squash old migrations with `schema:dump` once the folder grows long.

## What the tests run

One `tests` entry runs `php artisan test --group=migrations`. That group holds a feature test that calls `$this->artisan('migrate:refresh')` on the throwaway database `phpunit.xml` sets for the `testing` environment. It rolls every migration back and applies it again, so a missing or broken `down` fails the change. No command touches the database `.env` names.
