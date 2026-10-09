+++
id = "java/gradle-multi-project"
type = "opinionated"
fills = ["ci-pipeline:workspace"]
default = true
implements = "ci-pipeline:Dependencies declared and locked"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["settings.gradle.kts", "**/*.gradle.kts", "gradle/libs.versions.toml", "buildSrc/**", "build-logic/**"]
why = "A Gradle multi-project build holds every app, module, and package in one build with one settings file and one version catalog, and builds the subprojects in dependency order."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://docs.gradle.org/current/userguide/multi_project_builds.html"
evidence = "A multi-project build consists of a root project and one or more subprojects, all defined in a single settings.gradle(.kts) file."
alternatives = ["a Maven multi-module build", "a Gradle composite build"]
status = "active"
enforced_by = [
  { name = "build", command = ["./gradlew", "--no-daemon", "build"] },
]
+++

# A Gradle multi-project build holds the Java apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for Java. Its tool is Gradle, which `java/gradle-kotlin-dsl` pins through the wrapper. Gradle is under the Apache License 2.0.

## What the team does

- List each subproject once in `settings.gradle.kts` with `include()`: the apps, one subproject for each module, and the shared packages.
- Refer to a sibling with `implementation(project(":modules:orders"))`. Use `api` only for a type that the module's own API exposes.
- Share the build logic through convention plugins in `build-logic/`, never through `allprojects` or `subprojects` blocks.
- Declare every version once, in `gradle/libs.versions.toml`.
- With Spring Modulith, a module can also stay a package in one subproject. Split it into a subproject when its build or its owners differ.

## What the gate runs

One `[[tests]]` entry runs `build` on every subproject: it compiles, tests, and runs each `check` task. A failure in any subproject fails the change.
