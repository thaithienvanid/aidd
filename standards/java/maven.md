---
id: java/maven
type: opinionated
fills: [ci-pipeline:package-manager]
default: false
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: ["**/pom.xml", ".mvn/**", mvnw, mvnw.cmd]
why: "Maven builds from declarative POMs that most Java tools and many Spring teams already know, and the Maven Wrapper pins Maven itself for every machine."
reviewed: "2026-10-16"
maturity: established
tool:
  name: maven
  registry: maven
  package: org.apache.maven:maven-core
version_policy: current_stable
checked_version: "3.10.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "3.10.0"
source: https://maven.apache.org/download.cgi
evidence: Apache Maven 3.10.0 is the latest release.
alternatives: [Gradle with the Kotlin DSL, Gradle with the Groovy DSL]
status: active
enforced_by:
  - name: enforce
    command: ["./mvnw", --batch-mode, --no-transfer-progress, validate]
---

# Maven builds the Java project and keeps its versions fixed

It answers the package-manager choice of `aidd-team:ci-pipeline`. aidd's default for Java is `java/gradle-kotlin-dsl`. This option is for a team that keeps Maven POMs. Maven is under the Apache License 2.0.

## Which version

Use the 3.x release in `pin`. Maven 4 is still a preview, and the Maven project says that it is not safe for production use.

## What the team does

- Commit the Maven Wrapper: `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/maven-wrapper.properties`. Set its `distributionUrl` to the version in `pin`, and set `distributionSha256Sum`. Run `./mvnw`, never a Maven from the runner.
- Declare each version once, in `<dependencyManagement>` or in an imported BOM such as Spring Boot's.
- Maven writes no lock file. So bind the Maven Enforcer Plugin's `enforce` goal in the parent POM, with the `banDynamicVersions` and `dependencyConvergence` rules: every version is exact, and each artifact resolves to one version.
- The other `java/` standards run their tests with `./gradlew`. A Maven project writes its own entries for them, through `standards_policy.replace`.

## What the gate runs

One `tests` entry runs `./mvnw validate`, the phase that the `enforce` goal binds to by default. A version range, a snapshot, or two versions of one artifact fails the change.
