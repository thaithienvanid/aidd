+++
id = "java/java-lts"
type = "opinionated"
fills = ["ci-pipeline:language-version"]
default = true
implements = "ci-pipeline:Dev/prod parity"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["**/*.gradle.kts", "Dockerfile", "**/Dockerfile"]
why = "The newest Java LTS release gets years of updates from every vendor, and a Gradle toolchain pins it in the build, so CI, each machine, and the image compile and run the same version."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "java", registry = "adoptium", package = "temurin" }
version_policy = "latest_lts"
checked_version = "25"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "25"
source = "https://www.oracle.com/java/technologies/java-se-support-roadmap.html"
evidence = "Java SE 8, 11, 17, 21, and 25 are LTS releases."
alternatives = ["the current non-LTS feature release", "a declared minimum release"]
status = "active"
enforced_by = [
  { name = "toolchain", command = ["./gradlew", "--no-daemon", "compileJava"] },
]
+++

# The project targets the newest Java LTS release

It answers the language-version choice of `aidd-team:ci-pipeline`.

## What the team does

- Set `java { toolchain { languageVersion = JavaLanguageVersion.of(<pin>) } }` in the build, with the release in `pin`. Gradle then compiles and tests with that JDK, whatever runs Gradle.
- Build the runtime image from a JRE of the same release, such as Eclipse Temurin.
- Take each quarterly update of that release; move to the next LTS release in a change of its own.
- Use no preview features in production code.

## What the gate runs

One `[[tests]]` entry compiles the main sources with the declared toolchain. A toolchain Gradle cannot provide fails the change.
