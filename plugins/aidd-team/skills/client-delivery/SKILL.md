---
name: client-delivery
description: "Practice skill: run a client engagement from qualification to handover. Use in an aidd repository for a kickoff, RAID log, milestone, change order, or handover."
metadata:
  checked: "2026-09-30"
---

# Client delivery

**Use it when** a client pays for the work: qualifying the request, kickoff, keeping them informed, scope changes, their acceptance, and handing the product over.

**Do not use when** the team builds for itself: an internal change needs no contract, milestones, or handover.

## Standards

<!-- aidd:gen practice:client-delivery -->
| Standard | Edition |
| --- | --- |
| The APMP Body of Knowledge: qualification and the bid/no-bid decision, a compliance matrix, win themes, and color-team reviews | — |
| A RAID log (risks, assumptions, issues, dependencies) with an owner and a status per line, reviewed at every status report | — |
| Written change control: no scope, date, or price change without a change order the client decides | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:client-delivery`.
<!-- aidd:end -->

## Plan

### Qualify and propose

1. Record `qualification` in the proposal before anyone drafts: fit, budget, authority, decision process. Write `unknown` rather than guess. Keep each gap in `questions`. Recommend `go`, `no_go`, or `ask`. A person records `go_no_go`.
2. An existing system: list what it does now, with `file:line`, before the scope ([references/verify-what-exists.md](references/verify-what-exists.md)).
3. After go, write the proposal's `## Delivery`: the kickoff agenda, access provisioning, tenant and environment setup, and the communication cadence. Add `milestones`: each triggers on acceptance of listed ids, the listed Specs shipped, or an event. A person sets each `due` date. Add the RAID entries, each with an owner and a status. A person sets every amount. Sign-off freezes the proposal.

### Deliver

- Kickoff: run the Delivery kickoff agenda. Turn each access or environment item into a `dependencies` entry with an owner and a date.
- Status: after `aidd proposal convert`, the Initiative holds the RAID log and the milestones. Update the statuses. A person records each milestone's `reached_on`. Review the RAID log. Send `aidd digest --client` on the cadence, with support against the contract's levels. Never soften a red item.
- Contract: `aidd new contract <proposal id>` writes the SOW base, with its support levels, in the proposal's folder. Leave every "for a person or a lawyer" line to them. The contract is never legal advice.
- Change: a false assumption or a new request becomes the next change order, `aidd new contract <proposal id>` again. No scope, date, or price changes without one. The price and client decision are a person's.
- Documents: write at the `plain` level (`aidd-team:plain-language`). Run [references/client-documents.md](references/client-documents.md) before sign-off.
- Vendors: `aidd new vendors` writes the repository's register. `aidd validate` warns 30 days before a renewal.

## Ship

- Acceptance: run `aidd new acceptance`. List the ids to accept (the Spec's Acceptance ids) and the gate's evidence. A person records each decision.
- Handover (`/aidd-team:handover`) opens the Handover lists in the acceptance record and the runbook. Name each credential with where it now lives, never the secret. The warranty start is a date.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Engagement records check | the proposal, contract, vendor register, and acceptance record are valid; no renewal is due unnoticed | `aidd validate` over the repository |

## Stop if

- You are about to guess a qualification field instead of writing `unknown` and asking.
- Scope, a date, or a price would change without a change order a person decides.
- A secret would be written into the Handover lists.
- You are about to soften a red status item.

## Hand off

- Done: the qualification, questions, RAID log, milestones, and Delivery section current, or the Handover lists ready. Next: a person decides (go/no-go, sign-off, a change order, acceptance). Needs: every price, legal term, and client decision. Stopped at: none, or the stop rule that fired.
