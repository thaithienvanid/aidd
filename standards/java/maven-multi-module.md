+++
id = "java/maven-multi-module"
type = "opinionated"
fills = ["ci-pipeline:workspace"]
default = false
implements = "ci-pipeline:Dependencies declared and locked"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["**/pom.xml", ".mvn/**", "mvnw", "mvnw.cmd"]
why = "A Maven multi-module build aggregates every app, module, and package under one parent POM, and the reactor builds them in dependency order."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://maven.apache.org/guides/mini/guide-multiple-modules.html"
evidence = "Because modules within a multi-module build can depend on each other, it is important that the reactor sorts all the projects in a way that guarantees any project is built before it is required."
alternatives = ["a Gradle multi-project build"]
status = "active"
enforced_by = [
  { name = "verify", command = ["./mvnw", "--batch-mode", "--no-transfer-progress", "verify"] },
]
+++

# A Maven multi-module build holds the Java apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for a Java team on Maven (`java/maven`). Maven is under the Apache License 2.0. `java/gradle-multi-project` stays the default.

## What the team does

- Keep one parent `pom.xml` at the root, with `<packaging>pom</packaging>`. List the apps, one module for each business module, and the shared packages in `<modules>`.
- Set every version in the parent's `<dependencyManagement>`. A child POM names a dependency with no version.
- Refer to a sibling by its coordinates, at the version of the reactor.
- Run builds from the root through `./mvnw`, so the reactor builds every module in order.

## What the gate runs

One `[[tests]]` entry runs the `verify` phase on the whole reactor in batch mode, which asks no question. A failure in any module fails the change.
