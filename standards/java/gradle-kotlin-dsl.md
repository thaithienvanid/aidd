---
id: java/gradle-kotlin-dsl
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed:
  - "**/*.gradle.kts"
  - gradle/libs.versions.toml
  - "**/gradle.lockfile"
  - gradle/wrapper/gradle-wrapper.properties
why: "Gradle with the Kotlin DSL gives typed, IDE-checked build scripts, a version catalog, and dependency lock files, and the wrapper pins Gradle itself for every machine."
reviewed: "2026-10-16"
maturity: established
tool:
  name: gradle
  registry: github
  package: gradle/gradle
version_policy: current_stable
checked_version: "9.8.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "9.8.0"
source: https://gradle.org/releases/
evidence: "9.8.0 Sep 24, 2026"
alternatives: [Maven, Gradle with the Groovy DSL]
status: active
enforced_by:
  - name: locks
    command: ["./gradlew", --no-daemon, resolveAll]
---

# Gradle with the Kotlin DSL builds and locks the Java project

It answers the package-manager choice of `aidd-team:ci-pipeline`.

## What the team does

- Write every build script as `*.gradle.kts`. Declare versions once, in `gradle/libs.versions.toml`.
- Commit the Gradle wrapper, and set its `distributionUrl` to the version in `pin`. Run `./gradlew`, never a Gradle from the runner.
- Turn on dependency locking for all configurations with `LockMode.STRICT`, and commit each `gradle.lockfile`.
- Register two tasks in every project, from a convention plugin: `resolveAndLockAll`, as Gradle's dependency-locking guide writes it, and `resolveAll`, the same task without its `--write-locks` requirement.
- Change a dependency with `./gradlew resolveAndLockAll --write-locks`, in the same change as the version.
- Verify the wrapper's checksum in CI.

## What the gate runs

One `tests` entry runs `resolveAll`, which resolves every configuration of every project against its lock state. A version that no longer matches its lock fails the change.
