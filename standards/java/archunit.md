---
id: java/archunit
type: opinionated
fills: [modular-monolith:module-boundaries]
default: false
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: ["src/main/**", "src/test/**", "**/*.gradle.kts", gradle/libs.versions.toml, "archunit_store/**"]
why: "ArchUnit writes architecture rules as plain JUnit tests over the compiled classes, so it checks module rules in any Java code, with or without Spring, and freezes known violations in a store."
reviewed: "2026-10-16"
maturity: established
tool:
  name: archunit
  registry: maven
  package: com.tngtech.archunit:archunit
version_policy: current_stable
checked_version: "1.5.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://repo1.maven.org/maven2/com/tngtech/archunit/archunit/maven-metadata.xml
evidence: "<release>1.5.1</release>"
pin: "1.5.1"
alternatives: [Spring Modulith]
status: active
enforced_by:
  - name: boundaries
    command: ["./gradlew", --no-daemon, architectureTest]
---

# ArchUnit checks the Java module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Java code outside Spring, or for rules that Spring Modulith does not express. ArchUnit is under the Apache License 2.0. `java/spring-modulith` stays the default.

## What the team does

- Add `com.tngtech.archunit:archunit-junit5` at `pin` to the test dependencies.
- Write one test class, `ArchitectureTest`, in the application's subproject, with `@AnalyzeClasses` over the application's packages.
- In that subproject only, register a `Test` task named `architectureTest`, filtered to `*ArchitectureTest`, as `java/spring-modulith` shows.
- Use `slices().matching("..modules.(*)..").should().beFreeOfCycles()`, so no cycle between modules passes.
- Write one rule for each dependency rule of the skill. For example, no class outside a module may depend on its `..internal..` packages.
- Wrap each rule in `FreezingArchRule.freeze()` when a code base starts with violations. Set `freeze.store.default.path=archunit_store` in `archunit.properties`, and commit that folder: it is the violations baseline. `freeze.store.default.allowStoreCreation` is `false` by default, so the first frozen run fails. Set it to `true` for that one local run.
- Also set `freeze.store.default.allowStoreUpdate=false` there, so a test run never changes the store. To shrink it, a person sets the property to `true` for one local run.

## What the gate runs

One `tests` entry runs `architectureTest`, which fails when no test matches its filter. A broken rule, or a violation that the frozen store does not hold, fails the change. A Maven project adds a Surefire execution for `*ArchitectureTest` to the application's module only.
