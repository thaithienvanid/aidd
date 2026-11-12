---
id: swift/swiftui
type: opinionated
fills: [mobile-apps:mobile-framework]
default: true
implements: mobile-apps:Store minimum SDK and target levels
roles: [architect, developer, reviewer]
when_changed: ["**/*.swift", "**/*.xcodeproj/**", "**/*.xcconfig", "**/Info.plist", Package.swift]
why: "SwiftUI is Apple's own framework for app screens on every Apple platform, declared in Swift, so a native iOS app needs one language and Xcode alone."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://developer.apple.com/swiftui/
  quote: "SwiftUI helps you build great-looking apps across all Apple platforms"
alternatives: [UIKit, Flutter, Expo (React Native)]
status: active
---

# SwiftUI builds the native iOS app's screens

It answers the mobile-framework choice of `aidd-packs:mobile-apps` for a native iOS app in Swift. An Android app beside it is a separate Kotlin app, on `kotlin/jetpack-compose`.

## What the team does

- Write every new screen in SwiftUI. Keep a UIKit screen only until its rewrite is planned.
- Build with one stated Xcode release, the same in CI and on every Mac. Move to a newer one in its own change, after you read its release notes.
- Commit the Xcode project and its `Package.resolved`, and review a change to either as code.
- Hand each view its state from a model, so a preview or a test can show any state.
- Give each screen a preview for its loading, empty, error, and filled states.
- Set the iOS deployment target once, in the project. The pack's store check reads the minimum OS from the built archive.
- Format, lint, and test with the `swift/` standards of the `swift-ios` stack. The UI tests run in XCUITest, the runner the pack names for a native app.

## What the tests run

Nothing of its own. `swift/swift-format` and `swift/swiftlint` each add a `tests` entry. `swift/swift-testing` leaves its entry to the project, and says why.
