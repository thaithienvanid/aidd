---
id: kotlin/jetpack-compose
type: opinionated
fills: [mobile-apps:mobile-framework]
default: true
implements: mobile-apps:Store minimum SDK and target levels
roles: [architect, developer, reviewer]
when_changed: ["**/*.kt", "**/*.gradle.kts", gradle/libs.versions.toml, "**/AndroidManifest.xml"]
why: "Jetpack Compose is the toolkit Android recommends for native UI, written in the same Kotlin as the rest of the app, so a team that ships a native Android app writes its screens and its logic in one language."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://developer.android.com/compose
evidence: "Jetpack Compose is Android’s recommended modern toolkit for building native UI."
alternatives: [Android Views with XML layouts, Flutter, Expo (React Native)]
status: active
---

# Jetpack Compose builds the native Android app's screens

It answers the mobile-framework choice of `aidd-team:mobile-apps` for a native Android app in Kotlin. An iOS app beside it is a separate Swift app, on `swift/swiftui`.

## What the team does

- Write every new screen in Compose. Keep a View-based screen only until its rewrite is planned; `kotlin/compose-ui-test` tests both kinds.
- Declare the Compose libraries once, in `gradle/libs.versions.toml`, and lock them with `java/gradle-kotlin-dsl`, so a Compose upgrade is one reviewed change.
- Pass each screen its state and take its events out, so a preview or a test can show any state without the app running.
- Give each screen a preview or a test for its loading, empty, error, and filled states.
- Set the minimum and target SDK levels in the app module's build script. The pack's store check reads them from the built bundle.
- Build the store bundle in CI from a clean checkout, never on a developer's machine.
- Format, lint, and test with the `kotlin/` standards of the `kotlin-android` stack.

## What the tests run

Nothing of its own. `kotlin/ktlint`, `kotlin/android-lint`, `kotlin/android-local-tests`, `kotlin/compose-ui-test`, and `java/gradle-kotlin-dsl` each add their `tests` entry.
