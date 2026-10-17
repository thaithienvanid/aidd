---
name: decision-record
description: "Practice skill: record an architecture decision (MADR). Use in an aidd repository when a choice is hard to reverse, or someone asks X or Y, why we picked this, or for an ADR."
metadata:
  checked: "2026-09-30"
---

# Decision record

**Use it when** a choice is hard to reverse or affects other teams: a framework, a data model, a protocol, a boundary, a vendor.

**Do not use when** the choice is reversible, local, and obvious to the next reader. An ADR per decision buries the few that matter. Record one when undoing it costs more than re-deciding it.

## Standards

<!-- aidd:gen practice:decision-record -->
| Standard | Edition |
| --- | --- |
| MADR architecture decision records | 4.0.0 |
| ISO/IEC/IEEE 42010 (stakeholders, concerns, views) | 2022 |
| arc42 structure | 9.0, 2025 |
| Evolutionary architecture: fitness functions as executable architectural tests, run by the gate | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:decision-record`.
<!-- aidd:end -->

## Specify

- Record in the Spec's Design: the context and problem, the decision drivers, the options with their trade-offs, the decision, and its consequences, good and bad.
- When the decision deserves its own file, add a documentation Task scoped to `docs/adr/NNNN-title.md`, written after Spec approval and linked from the Spec's `decisions`.
- MADR format: a short noun-phrase title; status (proposed, accepted, deprecated, superseded by NNNN); date; deciders; the sections above; a "Confirmation" line on how the team will know the decision is followed.

## Implement

- A test, not a promise, confirms a decision a machine can check. When the architecture overview (`docs/architecture/README.md`, `aidd new architecture`) declares layers, write one layering rule per boundary as a fitness function. Run it as an ordinary test command: the repository's `tests`, or the introducing change's `tests.commands`. The gate then turns red when a change breaks the rule.
- Name the rule in the ADR's Confirmation line. List it under the overview's Fitness functions.

## Review

- The options were real alternatives, not straw men. The consequences name what gets harder. There is an owner and a revisit condition. A superseded record points forward.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Layering rule | no change crosses a boundary the architecture declares | the checker for the stack: import-linter 2.15 for Python (a `layers` contract, `lint-imports`), dependency-cruiser 18.4.0 for JavaScript and TypeScript (a `forbidden` rule, `depcruise`), ArchUnit for the JVM (`layeredArchitecture()` in a unit test), NetArchTest for .NET (`HaveDependencyOn` in a unit test) |

## Stop if

- The options are straw men, or the consequences name nothing that gets harder.
- A decision belongs to another team's owners.
- A checkable decision has no test, only a promise.

## Hand off

- Done: the decision in the Spec, and the ADR file once written. Next: the reviewer checks the code against the decision. Needs: a decision that belongs to another team's owners. Stopped at: none, or the stop rule that fired.
