---
id: swift/swift-format
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.swift", ".swift-format"]
why: "swift-format is part of the Swift toolchain that comes with Xcode, so CI and every Mac format the code with one tool and nothing more to install."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://github.com/swiftlang/swift-format
  quote: "Swift 6 (included with Xcode 16) and above include swift-format in the toolchain."
alternatives: [SwiftFormat]
status: active
enforced_by:
  - name: format
    command: [swift, format, lint, --strict, --recursive, "."]
---

# swift-format sets the layout of the Swift code

It answers the formatter choice of `aidd-team:ci-pipeline` for Swift.

## What the team does

- Run it as `swift format`, the toolchain's own copy, so its version moves with the Xcode release the project states.
- Keep its settings in one `.swift-format` file at the repository root. Start from the output of `swift format dump-configuration`, and change only what the team agrees on, once.
- Format on save in each editor and in the pre-commit hook.
- A review never asks for a layout change, because swift-format decides it.

## What the tests run

One `tests` entry runs `swift format lint --strict --recursive .`. A file the formatter would change fails the change.
