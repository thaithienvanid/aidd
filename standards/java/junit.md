---
id: java/junit
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, verifier, reviewer]
when_changed: ["**/*.java", "**/*.gradle.kts", gradle/libs.versions.toml]
why: "JUnit is the JVM's common test framework, and Gradle, every IDE, Spring Boot, and Testcontainers run it natively; JUnit 6 is its current generation."
maturity: established
tool:
  name: junit
  registry: maven
  package: org.junit:junit-bom
version_policy: pinned
checked_version: "6.1.3"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/4.1.1/spring-boot-dependencies-4.1.1.pom
evidence: "<junit-jupiter.version>6.0.3</junit-jupiter.version>"
alternatives: [TestNG, Spock]
status: active
enforced_by:
  - name: test
    command: ["./gradlew", --no-daemon, test]
---

# JUnit runs the Java unit tests

It answers the test-runner choice of `aidd-team:ci-pipeline`.

## Which version

Spring Boot's dependency management sets the JUnit version, through `spring-boot-starter-test`, so never import a JUnit BOM over it. A project without Spring Boot imports the newest `org.junit:junit-bom` from its version catalog.

## What the team does

- Declare the JUnit artifacts without versions.
- Set `useJUnitPlatform()` on each test task. Keep unit tests in the `test` suite, and tests with real services in `integrationTest`.
- Use `@ParameterizedTest` for a table of cases, and `@Nested` to group them by behavior.
- Never mark a test `@Disabled` without an issue link in its reason.

## What the tests run

One `tests` entry runs `./gradlew test`. A failing or erroring test fails the change.
