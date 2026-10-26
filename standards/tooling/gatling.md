---
id: tooling/gatling
type: opinionated
fills: [apis-and-services:load-test]
default: false
implements: apis-and-services:Load test
roles: [sre, verifier, developer, reviewer]
when_changed: ["src/gatling/**", "**/src/gatling/**"]
why: "Gatling writes the load as code in Java or Kotlin inside the Gradle or Maven build, so a JVM team reviews it like the service, and a failed assertion fails the build. It is under Apache-2.0."
reviewed: "2026-10-22"
maturity: established
tool:
  name: gatling
  registry: maven
  package: io.gatling:gatling-core
version_policy: current_stable
checked_version: "3.16.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "3.16.0"
source: https://repo1.maven.org/maven2/io/gatling/gatling-core/maven-metadata.xml
evidence: "<release>3.16.0</release>"
alternatives: [k6, Locust]
status: active
enforced_by:
  - name: load
    command: ["./gradlew", --no-daemon, gatlingRun, --all]
---

# Gatling runs the load test for a JVM team

It answers the load-test choice of `aidd-team:apis-and-services` where the team works on the JVM. `tooling/k6` stays the default. Gatling's Community Edition is open source under Apache-2.0, and Gatling Enterprise is a paid product.

## What the team does

- Apply the `io.gatling.gradle` plugin in the subproject that holds the simulations, at a version whose first three digits are `pin`. Keep the simulations in its `src/gatling/java` folder.
- Write each SLO as an assertion in `setUp`, such as `global().responseTime().percentile(95.0).lt(200)` and `global().failedRequests().percent().lt(1.0)`.
- Inject an open workload, such as `constantUsersPerSec`, so a slow service cannot lower the arrival rate.
- Read the base URL from a system property or an environment variable, and run against a test deployment, never production.
- Maven projects run the same simulations with `mvn gatling:test`.

## What the gate runs

One `load` test runs every simulation with `gatlingRun --all`. Gatling checks the assertions after the run, and a failed assertion fails the simulation and the change.
