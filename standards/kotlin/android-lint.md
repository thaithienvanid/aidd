---
id: kotlin/android-lint
type: opinionated
fills: [ci-pipeline:linter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.kt", "**/res/**", "**/AndroidManifest.xml", "**/*.gradle.kts", "**/lint.xml", "**/lint-baseline.xml"]
why: "Android Lint comes with the Android Gradle plugin and checks the Kotlin code, the resources, and the manifest for correctness, security, performance, usability, accessibility, and internationalization problems."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://developer.android.com/studio/write/lint
evidence: "The lint tool checks your Android project source files for potential bugs"
alternatives: [detekt]
status: active
enforced_by:
  - name: lint
    command: ["./gradlew", --no-daemon, lint]
---

# Android Lint checks the Android app's code and resources

It answers the linter choice of `aidd-team:ci-pipeline` for a native Android app.

## What the team does

- Run lint in CI on every change. The Android Gradle plugin does not run it as part of a build.
- Keep `abortOnError` at its default, true, so an error stops the run.
- Turn on `checkDependencies` in the app module, so lint also reads the library modules the app uses.
- `./gradlew lint` checks only the default build variant. Add `lintRelease` to the run when the release variant has code of its own.
- In an existing app, record today's issues in `lint-baseline.xml` and commit it, so only new issues fail. Fix its entries as you touch their code, and never add one by hand.
- Raise each issue the team treats as blocking to `error` in `lint.xml`.
- Write the reason beside each `@SuppressLint` and each `tools:ignore`. A bare suppression is a review finding.
- Add detekt through its own standard where the team wants Kotlin code-smell rules beyond lint.

## What the tests run

One `tests` entry runs `./gradlew lint`. An issue at `error` or `fatal` severity fails the change.
