---
name: decision-record
description: "Practice skill: record an architecture decision. Use when a choice is hard to reverse or affects other teams, such as a framework, a database, a data model, a protocol, a vendor, or a security boundary, or when someone asks should we use X or Y, why did we pick this, write an ADR, or record this decision: MADR format, options considered, consequences, and where it lives in the Spec and in docs/adr."
metadata:
  checked: "2026-09-25"
---

# Decision record

**Use it when** a choice is hard to reverse or affects other teams: a framework, a data model, a protocol, a boundary, a vendor.

**Do not use when** the choice is reversible, local, and obvious to the next reader; an ADR per decision buries the few that matter. Record one when undoing it would cost more than re-deciding it.

## Standards

- MADR 4.0.0 (Markdown Any Decision Records).
- ISO/IEC/IEEE 42010 concerns and viewpoints.
- The arc42 decisions section.

## Specify, before Spec approval

- Record in the Spec's Design: the context and problem, the decision drivers, the options considered with their trade-offs, the decision, and its consequences, good and bad.
- When the decision deserves its own file, add a documentation Task whose scope covers `docs/adr/NNNN-title.md`; write it after Spec approval, and link it from the Spec's `decisions`.

## Format, MADR

- Title as a short noun phrase; status (proposed, accepted, deprecated, superseded by NNNN); date; deciders; the sections above; a "Confirmation" line saying how the team will know the decision is followed.

## Review

- The options were real alternatives, not straw men; the consequences name what gets harder; an owner and a revisit condition exist; a superseded record points forward.

## Hand off

- Done: the decision in the Spec, and the ADR file once written. Next: the reviewer checks the code matches the decision. Needs: a decision that belongs to another team's owners. Stopped at: none, or the stop rule that fired.
