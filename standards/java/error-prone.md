+++
id = "java/error-prone"
type = "opinionated"
fills = ["ci-pipeline:linter"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.java", "**/*.gradle.kts"]
why = "Error Prone runs inside javac, so every compile checks Google's bug patterns with full type information, and no separate lint step can be skipped."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "error-prone", registry = "maven", package = "com.google.errorprone:error_prone_core" }
version_policy = "current_stable"
checked_version = "2.50.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "2.50.0"
source = "https://github.com/google/error-prone/releases/tag/v2.50.0"
evidence = "Error Prone 2.50.0"
alternatives = ["SpotBugs", "PMD", "Checkstyle"]
status = "active"
enforced_by = [
  { name = "lint", command = ["./gradlew", "--no-daemon", "compileJava", "compileTestJava"] },
]
+++

# Error Prone checks the Java code at compile time

It answers the linter choice of `aidd-team:ci-pipeline`.

## What the team does

- Apply the `net.ltgt.errorprone` Gradle plugin at a fixed version from the version catalog (5.1.1 on the `checked` day), and add `error_prone_core` at the version in `pin` to the `errorprone` configuration.
- Keep Error Prone's ERROR checks as errors. Raise the WARNING checks you rely on to errors, by name.
- Add NullAway with JSpecify annotations. Set `check("NullAway", CheckSeverity.ERROR)` (`-Xep:NullAway:ERROR`) and exactly one of `NullAway:AnnotatedPackages` or `NullAway:OnlyNullMarked`; without one, NullAway does not run. Then a possible null dereference fails the compile.
- Suppress one finding with `@SuppressWarnings("CheckName")` and a comment that gives the reason.
- Error Prone needs a recent JDK to run; `java/java-lts` sets the toolchain.

## What the gate runs

One `[[tests]]` entry compiles the main and the test sources. An Error Prone error fails the change.
