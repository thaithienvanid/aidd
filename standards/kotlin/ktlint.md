---
id: kotlin/ktlint
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.kt", "**/*.kts", ".editorconfig"]
why: "ktlint is an anti-bikeshedding Kotlin linter with a built-in formatter, and Spotless runs it from the Gradle build, so CI, the pre-commit hook, and every machine lay out the Kotlin code the same way."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://ktlint.github.io/ktlint/latest/install/integrations/
  quote: "a general-purpose formatting plugin which amongst many others also supports ktlint"
alternatives: [ktfmt, ktlint-gradle, kotlinter]
status: active
enforced_by:
  - name: format
    command: ["./gradlew", --no-daemon, spotlessCheck]
---

# ktlint, run by Spotless, sets the layout of the Kotlin code

It answers the formatter choice of `aidd-team:ci-pipeline` for Kotlin. ktlint is under the MIT License.

## What the team does

- Apply the Spotless plugin from the version catalog, and turn on its ktlint step for the Kotlin sources and the `*.gradle.kts` scripts.
- Name the ktlint version in the version catalog too. A new ktlint can change the layout, so its upgrade is a change of its own.
- Keep ktlint's settings in the `.editorconfig` at the repository root, which ktlint reads.
- Run `./gradlew spotlessApply` from the pre-commit hook, so a commit is already formatted.
- Leave layout out of reviews. The formatter settles it.

## What the tests run

One `tests` entry runs `./gradlew spotlessCheck`. A Kotlin file whose layout differs fails the change.
