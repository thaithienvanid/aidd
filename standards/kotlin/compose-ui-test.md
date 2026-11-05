---
id: kotlin/compose-ui-test
type: opinionated
fills: [mobile-apps:mobile-ui-test]
default: true
implements: mobile-apps:UI tests on the OS matrix
roles: [verifier, developer, reviewer]
when_changed: ["**/src/main/**", "**/src/androidTest/**", "**/*.gradle.kts", gradle/libs.versions.toml]
why: "The Compose testing APIs find nodes, check them, and act on them as a person would, and they wait for the UI to be idle, so a device test of a Compose screen needs no sleeps."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://developer.android.com/develop/ui/compose/testing
  quote: "Testing APIs let you find elements, verify their attributes, and perform user actions."
alternatives: [Espresso, Maestro]
status: active
enforced_by:
  - name: device
    command: ["./gradlew", --no-daemon, connectedAndroidTest]
---

# The Compose testing APIs drive the Android app on a device

It answers the mobile-ui-test choice of `aidd-packs:mobile-apps` for a native Android app on Compose. Espresso, which Android's docs describe for View-based screens, works beside it in the same test.

## What the team does

- Add `androidx.compose.ui:ui-test-junit4` to `androidTestImplementation`. Add `ui-test-manifest` to `debugImplementation` when a test calls `createComposeRule()`.
- Use `createComposeRule()` to render one screen with fake state, and `createAndroidComposeRule()` when the test needs the activity.
- Write a device test for each critical journey, from sign-up to account deletion, and for the main purchase or action.
- Find nodes through semantics the screen sets for tests, never through visible text that a translation changes.
- Let the test rule wait for the UI to go idle. A sleep in a test is a review finding.
- Run the suite on emulators in CI, across the OS matrix that the pack's UI tests row sets. Gradle Managed Devices can start those emulators for the run.
- Give each test its own account or a reset step, so the order of the tests never matters.

## What the tests run

One `tests` entry runs `./gradlew connectedAndroidTest` against a running emulator or device. It runs the instrumented tests of every module, and a failed test fails the change.
