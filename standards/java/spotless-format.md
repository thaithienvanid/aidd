---
id: java/spotless-format
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.java", "**/*.gradle.kts"]
why: "Spotless runs one pinned Java formatter from the build, so CI, the pre-commit hook, and every editor produce the same layout without a separate install."
reviewed: "2026-10-16"
maturity: established
tool:
  name: spotless
  registry: maven
  package: com.diffplug.spotless:spotless-plugin-gradle
version_policy: current_stable
checked_version: "8.10.4"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "8.10.3"
source: https://plugins.gradle.org/plugin/com.diffplug.spotless
evidence: "id(\"com.diffplug.spotless\") version \"8.10.4\""
alternatives: [google-java-format CLI, palantir-java-format]
status: active
enforced_by:
  - name: format
    command: ["./gradlew", --no-daemon, spotlessCheck]
---

# Spotless formats the Java code

It answers the formatter choice of `aidd-team:ci-pipeline`.

## What the team does

- Apply the `com.diffplug.spotless` plugin at the version in `pin`, from the version catalog.
- In the `spotless {java { }}` block, pick google-java-format and give its version, so an upgrade is a reviewed change.
- Add `removeUnusedImports()` and format the Kotlin build scripts too.
- Run `./gradlew spotlessApply` before you commit, or from the pre-commit hook.

## What the gate runs

One `tests` entry runs `spotlessCheck`. A file whose layout differs fails the change.
