---
name: adr
description: "Practice skill: record an architecture decision (MADR). Use in an aidd repository when a choice is hard to reverse, or someone asks X or Y, why we picked this, or for an ADR."
metadata:
  checked: "2026-10-22"
---

# Decision record

**Use it when** a choice is hard to reverse or affects other teams: a framework, a data model, a protocol, a boundary, a vendor.

**Do not use when** the choice is reversible, local, and obvious to the next reader. An ADR per decision buries the few that matter. Record one when undoing it costs more than re-deciding it.

## Standards

<!-- aidd:gen practice:adr -->
| Standard | Edition |
| --- | --- |
| MADR architecture decision records | 4.0.0 |
| ISO/IEC/IEEE 42010 (stakeholders, concerns, views) | 2022 |
| arc42 structure | 9.0, 2025 |
| Evolutionary architecture: fitness functions as executable architectural tests, run by the gate | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:adr`.
<!-- aidd:end -->

## Specify

- Record in the Spec's Design the context and problem, the stakeholders and their concerns, the drivers, the options with doing nothing among them, the decision, and its consequences, good and bad. Adopting a maintained project or service is one of the options.
- A decision that deserves its own file gets `aidd new adr <topic> --spec <ID>`. It writes `docs/adr/NNNN-<topic>.md` from the MADR 4.0.0 template and links it in the Spec's `docs`, so Spec approval freezes it.
- Follow the template's comments. Name the decision-makers, the people consulted, and the people informed. aidd derives the status, so never write it. The Confirmation says how the team will know the decision holds.
- A Spec that only relies on an earlier ADR lists it in `adrs`.

## Implement

- A test, not a promise, confirms a decision a machine can check. When the architecture overview (`aidd new architecture`) declares layers, write one layering rule per boundary as a fitness function. Run it as a `tests` entry, or in the introducing change's `tests.commands`. The gate then turns red when a change breaks the rule.
- Name the rule in the ADR's Confirmation. List it under the overview's Fitness functions.

## Review

- The options were real alternatives, not straw men. Building what a maintained project already does has its reason: its licence, its fit, its exit cost, or a gap it leaves. The consequences name what gets harder. There is an owner and a revisit condition. An accepted record is never edited, because a new one supersedes it and says so.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Layering rule | no change crosses a boundary the architecture declares | the checker the `modular-monolith:module-boundaries` choice names, as a `tests` entry, such as import-linter, dependency-cruiser, ArchUnit, or ArchUnitNET for .NET |

## Stop if

- The options are straw men, or the consequences name nothing that gets harder.
- A decision belongs to another team's owners.
- A checkable decision has no test, only a promise.

## Hand off

- Done: the decision in the Spec, and the ADR file once written. Next: the reviewer checks the code against the decision. Needs: a decision that belongs to another team's owners. Stopped at: none, or the stop rule that fired.
