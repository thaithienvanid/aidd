---
id: swift/swiftlint
type: opinionated
fills: [ci-pipeline:linter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.swift", ".swiftlint.yml"]
why: "SwiftLint enforces Swift style and conventions, under the MIT License, and runs as a Swift Package Manager build tool plugin, so the Xcode build and CI report the same findings."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://github.com/realm/SwiftLint
  quote: "A tool to enforce Swift style and conventions."
alternatives: ["swift-format's lint rules alone"]
status: active
enforced_by:
  - name: lint
    command: [swiftlint, --strict]
---

# SwiftLint checks the Swift code

It answers the linter choice of `aidd-team:ci-pipeline` for Swift.

## What the team does

- Add the plugin from the SwiftLintPlugins repository, as SwiftLint's README recommends, and pin it to one version, so `Package.resolved` records it.
- Install the same release of the `swiftlint` command in CI for the `tests` entry.
- Keep one `.swiftlint.yml` at the repository root.
- Turn off each rule that swift-format already decides, so the formatter and the linter never disagree.
- In an existing app, start from a baseline file of today's violations, so only new ones fail. Let the baseline only shrink.
- Write the reason beside each rule turned off in code. A bare one is a review finding.

## What the tests run

One `tests` entry runs `swiftlint --strict`, so a warning fails the change as an error does.
