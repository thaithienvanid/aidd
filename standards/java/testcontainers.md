---
id: java/testcontainers
type: opinionated
fills: [test-design:integration-test-services]
default: true
implements: test-design:Real throwaway dependencies
roles: [developer, verifier, reviewer]
when_changed: ["src/integrationTest/**", "**/*.gradle.kts"]
why: "Testcontainers starts the real database and services from JUnit, one throwaway container each, and Spring Boot reads their addresses through @ServiceConnection."
reviewed: "2026-10-16"
maturity: established
tool:
  name: testcontainers
  registry: maven
  package: org.testcontainers:testcontainers
version_policy: current_stable
checked_version: "2.0.5"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "2.0.5"
source: https://java.testcontainers.org/
evidence: "Testcontainers for Java is a Java library that supports JUnit tests, providing lightweight, throwaway instances of common databases, Selenium web browsers, or anything else that can run in a Docker container."
alternatives: [Docker Compose started by the test run, the provider's local emulator]
status: active
enforced_by:
  - name: integration
    command: ["./gradlew", --no-daemon, integrationTest]
---

# Testcontainers starts the Java integration-test services

It answers the integration-test-services choice of `aidd-team:test-design`.

## What the team does

- Let Spring Boot's dependency management set the version; Spring Boot 4.1.1 manages the one in `pin`. Without Spring Boot, import the Testcontainers BOM at `pin`. Add the module for each service, such as `testcontainers-postgresql`, and `spring-boot-testcontainers`.
- Put the tests in a Gradle `integrationTest` suite, so `test` stays fast and runs without Docker.
- Give each container an image with its tag and digest, the same major as production.
- Wire the container to Spring with `@ServiceConnection`, never with a fixed host or port.

## What the gate runs

One `tests` entry runs the `integrationTest` suite. A failing test, or a container that does not start, fails the change.
