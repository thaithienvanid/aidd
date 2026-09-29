# RFC NNNN: One line, in the form of a decision

<!-- Number it with the next unused NNNN and name the file NNNN-short-name.md. Open a PR with only
     this file (CONTRIBUTING.md, "Change the method"). Discussion stays open at least 7 days, or 14 for anything that
     loosens a gate. Use BCP 14 keywords (RFC 2119, RFC 8174) — MUST, MUST NOT, SHOULD, MAY — where you
     mean them, with a subject, as docs/METHOD.md does. Delete every HTML comment before merging. -->

- Status: draft | accepted | declined | withdrawn | superseded
- Author:
- Created: YYYY-MM-DD
- Discussion: <!-- the PR URL. Required: an RFC without a linked thread has no decision record. -->
- Affects: <!-- any of --> the method (routes, profiles, gate rules, the loop) | schemas | verifier | skill | team | templates | docs
- Version impact: patch | minor | major <!-- see CONTRIBUTING.md. Major is anything that can turn a
     passing change into a failing one, or the reverse, under an unchanged config. -->
- Implemented by: <!-- the Spec id, once accepted. CONTRIBUTING.md: an accepted RFC is implemented in
     its own PR, with a Spec. Leave empty while draft. -->
- Supersedes: <!-- an RFC id, or empty -->
- Superseded by: <!-- an RFC id, or empty -->

## Summary

<!-- One paragraph. What changes, for whom, and why now. A reviewer reads this to decide whether to
     read the rest, so it carries the conclusion, not the background. -->

## Problem

<!-- What fails today, for whom, with evidence: a gate event, an incident, an adopter report, a
     number. Then two or three concrete cases where the failure bites, because a problem with no
     instance is a taste. If the evidence is "this feels wrong", say so and expect the RFC to be
     declined. -->

## Proposal

<!-- The exact change, precise enough to implement from this text alone: the rule text, the schema
     diff, the profile table diff, the CLI flag. Corner cases dissected by example. If the change is
     a new field or rule, give its full definition here, not a description of it. -->

### How an adopter experiences it after

<!-- Explain the change as if it had already shipped and you were teaching it to someone who runs a
     repository under aidd: what they see in the gate status, what `aidd validate` or `aidd doctor`
     now says, what they must do to an existing config or Spec, and the exact wording of any new
     error or warning. A proposal whose message text you cannot write is not specified yet. -->

## Effect on decisions

<!-- The part of this RFC that is checkable. Which existing `examples/` cases change their decision,
     which new cases this RFC adds, and what `aidd eval examples` prints before and after. A change
     that flips any decision under an unchanged config is major and MUST list every case it flips.
     A change that flips none says so explicitly — that is a real answer, not an empty section. -->

| Case | Before | After | Why |
| --- | --- | --- | --- |
| | | | |

## Drawbacks

<!-- Why should we not do this? The cost an adopter pays, the complexity the verifier gains, the
     thing that becomes harder to explain, the migration somebody has to run. An RFC with no
     drawbacks has not been thought about; the honest answer is often "it makes minor changes to
     protected paths heavier", and that is worth stating. -->

## Alternatives

<!-- One row per option seriously weighed, including "do nothing" and "do it later", and why not.
     This is where a reviewer checks whether you searched the design space or stopped at the first
     idea that worked. -->

| Option | Why not |
| --- | --- |
| the proposal above | chosen |
| do nothing | |

### Rejected during discussion

<!-- Filled in as the thread runs, not before. Ideas a reviewer raised that you considered and turned
     down, with the reason, so the next reader does not raise them again. -->

## Prior art

<!-- How other methods and tools solve this, and what their experience was: ITIL's change models,
     ISO/IEC/IEEE 12207, ISO 42001, the EU AI Act, DevOps and DORA, Trunk-Based Development, another
     project's RFC process, a paper. Precedent is evidence, not motivation: "someone else does it"
     does not on its own justify a change here, and aidd deliberately diverges from common practice
     in places that the skill's loop reference (.agents/skills/aidd/references/loop.md) explains. No prior art is an acceptable answer. -->

## Security

<!-- How an agent or a hurried human could abuse the change, and the red-team test that proves they
     cannot. Name the test file and the case. Per AGENTS.md every new gate rule needs a passing and
     a failing case in `examples/` or `tests/test_redteam.py`, so this section says which.
     Never write "none" without saying what you checked to reach it. -->

## Privacy

<!-- What this change causes aidd to read, store, transmit, or retain about people: commit authors
     and committers, e-mail addresses, platform logins, approval timestamps, agent identities. Where
     it goes (a gate record, an event log, a commit status, a workflow artifact), how long it is
     kept, and who can see it. A change that adds a field to `record.schema.json` or `event.schema.json`
     is a privacy change even when the field looks innocuous, because records are retained artifacts. -->

## Compatibility

<!-- What breaks for an existing adopter: a config that stops loading, a Spec that stops validating,
     a record an older verifier cannot read, a workflow pin that must move. State whether the change
     is observable by a conforming repository at all — if it is not, it is a patch. Name the
     deprecation path from CONTRIBUTING.md when a key, rule name, or flag is replaced: it keeps
     working for at least one minor release, warns naming the replacement, and the changelog lists
     it under Deprecated before removal in the next major. -->

## How this is taught

<!-- Which documents change, because a rule nobody can find is a rule nobody follows: docs/METHOD.md,
     docs/GLOSSARY.md, docs/FAQ.md, references/*.md, the skill's SKILL.md, the generated tables in
     docs/CONFIG.md and docs/TEAM.md, and the aidd-team roles in schemas/roles.json. Say which are
     hand-written and which `aidd gen-docs` regenerates. -->

## Rollout

<!-- Migration steps for adopters, in order, and how `aidd doctor` or `aidd validate` guides them.
     Whether existing Specs and records are migrated or grandfathered, and what an adopter who does
     nothing experiences on the day this ships. -->

## Unresolved questions

<!-- What you expect to settle during discussion before this merges; what you expect to settle during
     implementation; and what is deliberately out of scope here but could be its own RFC later. An
     RFC with none says "none" — but check first, because an unresolved question found by a reviewer
     costs a week and one found by an adopter costs a rollback. -->

## Future possibilities

<!-- The natural extension of this proposal, and how it would interact with the rest of the method.
     Also the place to park a related idea that is out of scope here. Writing something down is not
     a reason to accept it later; it still gets its own RFC. -->

## Decision

<!-- Filled in by a maintainer, never by the author. The outcome, the date, the reason, and any
     condition attached to acceptance. This is the record CONTRIBUTING.md refers to when it says the
     maintainers accept or decline in the PR. -->

- Outcome:
- Date: YYYY-MM-DD
- Reason:
- Conditions:

## Change history

<!-- Newest first, one bullet per substantive revision, in YYYY-MM-DD format (ISO 8601), like every date in this template, so a reader who
     returns after the 7- or 14-day discussion window can see what moved without reading the thread. -->

- YYYY-MM-DD: drafted.
