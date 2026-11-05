---
id: swift/swift-testing
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: ["**/*.swift", "**/*.xctestplan", Package.swift]
why: "Swift Testing comes with the Swift toolchain and Xcode, writes each check as a plain Swift expression, and runs beside XCTest, so a team moves its tests over one file at a time."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://github.com/swiftlang/swift-testing
evidence: "Swift Testing is included with the Swift 6 toolchain and Xcode 16."
alternatives: [XCTest]
status: active
---

# Swift Testing runs the Swift unit tests

It answers the test-runner choice of `aidd-team:ci-pipeline` for Swift. It is under the Apache License 2.0.

## What the team does

- Write each new test as a `@Test` function, with `#expect` for each check. Use `#require` for a value the rest of the test needs.
- Leave working XCTest tests where they are, and move each one when you next change it. The two run side by side.
- Keep the UI tests in XCUITest, as the pack's UI tests row expects for a native app.
- Replace the network and the clock with fakes in unit tests. A test that reaches a real service runs in its own suite.
- Run the tests in CI on one stated simulator and OS version, and keep the test report as an artifact.

## What the tests run

No entry of its own. The run names the project's scheme and a simulator, which only the project knows. So the project adds its `tests` entry when it adopts this standard. A failed test fails the change.
