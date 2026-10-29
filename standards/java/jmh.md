---
id: java/jmh
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["src/jmh/**", "**/src/jmh/**"]
why: "JMH, from the OpenJDK project, handles the JVM's warmup, forks, and dead-code removal that make a hand-written Java timing loop wrong, and reports each score with its error."
reviewed: "2026-10-22"
maturity: established
tool:
  name: jmh
  registry: maven
  package: org.openjdk.jmh:jmh-core
version_policy: current_stable
checked_version: "1.37"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.37"
source: https://repo1.maven.org/maven2/org/openjdk/jmh/jmh-core/maven-metadata.xml
evidence: "<release>1.37</release>"
alternatives: [hyperfine for a whole program]
status: active
---

# JMH benchmarks the Java code

It answers the benchmark-tool choice of `aidd-team:performance` for the JVM. JMH is under GPL-2.0 with the Classpath Exception. It runs only in the benchmark build and never ships in the service.

## What the team does

- Keep the benchmarks in their own source set or module, such as `src/jmh/java`, with `jmh-core` and `jmh-generator-annprocess` at `pin`.
- On Gradle, use the community `me.champeau.jmh` plugin. Its compatibility table names Gradle 8 as the newest line, so check it on the project's Gradle first. On Maven, start from JMH's archetype.
- Return each result, or pass it to a `Blackhole`, so the JIT cannot remove the work. Keep `@Fork` at 1 or more.
- In the Regression guard, run the base's and the head's benchmark jars one after the other on the same runner, each with `-rf json`.
- Fail the guard when the head's score is worse by more than the Spec's bound, and the two error intervals do not overlap.

## What the gate runs

No `tests` entry of its own. The Regression guard of `aidd-team:performance` runs the benchmarks when a Spec sets a budget.
