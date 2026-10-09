+++
id = "java/spring-modulith"
type = "opinionated"
fills = ["modular-monolith:module-boundaries"]
default = true
implements = "modular-monolith:Boundary check"
roles = ["architect", "developer", "reviewer"]
when_changed = ["src/main/**", "src/test/**", "**/*.gradle.kts", "gradle/libs.versions.toml"]
why = "Spring Modulith is Spring's own tool for a modular monolith: one test call verifies that application modules form no cycle and that each one reaches another only through its API packages."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "spring-modulith", registry = "maven", package = "org.springframework.modulith:spring-modulith-core" }
version_policy = "current_stable"
checked_version = "2.1.1"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://docs.spring.io/spring-modulith/reference/verification.html"
evidence = "No cycles on the application module level — the dependencies between modules have to form a directed acyclic graph."
pin = "2.1.1"
alternatives = ["ArchUnit", "jMolecules with ArchUnit"]
status = "active"
enforced_by = [
  { name = "boundaries", command = ["./gradlew", "--no-daemon", "architectureTest"] },
]
+++

# Spring Modulith checks the Java module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for a Java service on Spring Boot (`java/spring-boot`). Spring Modulith is under the Apache License 2.0. Its 2.1.1 release builds on Spring Boot 4.1.1.

Use the 2.1.x line in `pin`. The 2.2 releases on Maven Central are milestones, such as 2.2.0-M2, so do not use them in production.

## What the team does

- Import `spring-modulith-bom` at `pin`, and add `spring-modulith-starter-test` to the test dependencies.
- Make each module a direct sub-package of the application's main package. Its top-level package is its API. Its sub-packages are internal.
- Write one test class, `ModularityTests`, in the application's subproject. It calls `ApplicationModules.of(Application.class).verify()`.
- In that subproject only, register a `Test` task named `architectureTest`. Give it the `test` source set's classes and runtime classpath, `useJUnitPlatform()`, and `filter { includeTestsMatching("*ModularityTests") }`.
- To limit what a module may use, set `@ApplicationModule(allowedDependencies = …)` in its `package-info.java`.
- An open application module lets others reach its internals. Never mark a module open to hide a violation. An open module needs an ADR.

## What the gate runs

One `[[tests]]` entry runs `architectureTest`. Only the application's subproject has the task, so a library subproject with no such test never fails it. The task fails when no test matches its filter. A cycle between modules, or a reference to another module's internal type, fails `verify()` and the change.

A Maven project adds a Surefire execution with the id `architecture` to the application's module only, with `<test>*ModularityTests</test>`. Then `./mvnw verify` runs it there, and it fails when no test matches.
