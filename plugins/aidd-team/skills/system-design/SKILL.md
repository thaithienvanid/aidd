---
name: system-design
description: "Practice skill: design from measured goals and compared options. Use in an aidd repository when a Spec's Design adds a component, a data store, a queue, or a service, or meets a new scale goal."
metadata:
  checked: "2026-10-27"
---

# System design

**Use it when** a Spec's Design adds a component, a data store, a queue, or a service. Use it too when the Design moves data, changes how parts call each other, or must meet a new goal for scale, latency, or availability.

**Do not use when** the change stays inside one module's existing design, because `aidd-team:maintainable-code` covers its shape. A single choice with nothing to design around it needs only `aidd-team:adr`.

A good design meets the measured goals with the least that is new, and plans for each failure.

## Standards

<!-- aidd:gen practice:system-design -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Quality attribute scenarios: each quality goal as a source, a stimulus, an environment, an artifact, a response, and a response measure | — | 2026-10-27 (reviewed) | <https://www.pearson.com/en-us/subject-catalog/p/software-architecture-in-practice/P200000000111/9780136886099> |
| ATAM: architectural approaches analysed against ranked quality scenarios, naming the risks, the sensitivity points, and the trade-off points | — | 2026-10-27 (reviewed) | <https://www.sei.cmu.edu/library/atam-method-for-architecture-evaluation/> |
| ISO/IEC 25010 product quality model | ISO/IEC 25010:2023 | 2026-10-16 | <https://webstore.iec.ch/en/publication/90024> |
| Pre-mortems on major changes: assume the change failed in production, and turn each cause into a test, a rollback step, or an observe signal | — | 2026-10-16 (reviewed) | <https://hbr.org/2007/09/performing-a-project-premortem> |
| MADR architecture decision records | 4.0.0 | 2026-10-16 | <https://adr.github.io/madr/> |
| Evolutionary architecture: fitness functions as executable architectural tests, run by the gate | — | 2026-10-16 (reviewed) | <https://evolutionaryarchitecture.com/> |
<!-- aidd:end -->

## Specify

1. **Goals as scenarios.** Write each quality goal that matters as a scenario someone can test. Name its source, stimulus, environment, artifact, and response, with a measure, such as "at 10x today's peak, 99% of checkouts finish within 300 ms". Name the ISO/IEC 25010 characteristic it serves. Mark each must-have or nice-to-have, with the person who owns it. A goal with no measure is a wish, so ask for one and never invent it.
2. **Size it.** Estimate today's load and 10x: peak requests per second, data added per year, the largest payload, and the monthly cost. Keep the arithmetic in the Spec, because it decides whether scale is a design problem. When it is, start from `aidd-team:performance` (`references/scalability.md`).
3. **Options.** Write two or three options, and always one that adds less that is new, such as the current design, a library, or a service the project already runs. For each, write what it changes, the scenarios it meets, its cost to build and run, and how hard it is to reverse.
4. **Trade-offs.** Put the options against the scenarios in one table. Name each risk, a decision that may miss a scenario's measure. Name each sensitivity point, a decision a goal depends on, and each trade-off point, one that two goals depend on. Pick the option that adds the least that is new and meets every must-have scenario. When two meet them but differ in cost or lock-in, list both and put the choice on Needs.
5. **Data first.** For each piece of data, name its one owner, its source of truth, and how fresh each reader needs it. A write across two owners needs a designed path. Move the boundary so one owner holds it, or use an outbox to idempotent consumers (`aidd-team:modular-monolith`) when the others may follow late. Use a saga, with a compensating step for each owner, when all must happen or none.
6. **Call or message.** Call synchronously only when the caller needs the answer to go on, and the callee's availability and latency fit inside the caller's goal. When the caller needs the answer and they don't fit, keep a local copy that events update, or move the boundary. Otherwise send an event or a job. Each remote call gets a timeout and a recovery decision (`aidd-team:resilience`).
7. **Failure.** For each new dependency, write what a user sees when it is slow, down, or wrong, its fallback, and the signal that shows it (`aidd-team:observability`). A new data store names its recovery point, its recovery time, and a restore test. On the major route, run a pre-mortem.
8. **Decide and get there.** Record each lasting choice in an ADR, with the rejected options and what the choice gives up (`aidd-team:adr`). Draw only what changes, in C4 (`aidd-team:diagrams`). Plan the move from today's design in steps that each reverse: expand and contract for data (`aidd-team:schema-migration`), and a flag for behavior (`aidd-team:release-rollout`). Give each boundary the design declares a fitness function.

## Review

- Each step above holds, and each must-have scenario has a test or an `observe` signal.
- Smells: a design with no goal behind it, a new service no scale or owner needs, and a cache or a queue "for scale" with no number behind it. Each is a finding (Medium).

## Test commands

- From `aidd-team:performance`: Regression guard.
- From `aidd-team:modular-monolith`: Boundary check.

A scenario no test on the head can reach goes in the `observe` block as a signal (`aidd-team:observability`).

## Stop if

- A must-have scenario has no measure, and nobody can give one.
- A person has fixed the option, and it misses a must-have scenario.
- The design needs a service, a store, or a vendor the project doesn't run, so a person decides.
- The team can't reverse the design, and no person has accepted that.

## Hand off

- Done: the Spec's Design, with its ranked scenarios, its sizing, the options and their trade-off table, and an ADR for each lasting choice. Next: the specialists the route calls, such as the security engineer, the SRE, or the product designer, then the verifier. Needs: a person's choice when two options meet the must-have scenarios but differ in cost or lock-in. Stopped at: none, or the stop rule that fired.
