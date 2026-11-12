---
id: kotlin/android-local-tests
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: ["**/src/main/**", "**/src/test/**", "**/*.gradle.kts", gradle/libs.versions.toml]
why: "Local tests run the app's logic on the developer's own JVM, with no device, in seconds, and one Gradle task runs them for every module and build variant."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://developer.android.com/training/testing/local-tests
  quote: "You write your local unit test class as a JUnit 4 test class."
alternatives: [Robolectric, Kotest]
status: active
enforced_by:
  - name: unit
    command: ["./gradlew", --no-daemon, test]
---

# Local tests run the Android app's logic on the JVM

It answers the test-runner choice of `aidd-team:ci-pipeline` for a native Android app. The tests are JUnit 4 classes, as Android's testing guide writes them.

## What the team does

- Put the local tests of each module in its `src/test/`. Tests that need a device go in `src/androidTest/`, under `kotlin/compose-ui-test`.
- Keep view models and other logic free of `Context` where you can, so they run without the Android framework.
- Replace a framework class with a fake, or with a Robolectric shadow where a fake is too much. Avoid complex mocks, as Android's guide advises.
- Leave `unitTests.returnDefaultValues` off. Android's guide calls it a last resort, because a null or a zero can let a failing test pass.
- Use one test method for each behavior, and a table of inputs for a family of cases.

## What the tests run

One `tests` entry runs `./gradlew test`, the local tests of every module and build variant. A failed test fails the change.
