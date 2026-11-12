---
name: client-delivery
description: "Practice skill: run a client engagement from qualification to handover. Use in an aidd repository for a kickoff, RAID log, phase, change order, or handover."
metadata:
  checked: "2026-10-22"
---

# Client delivery

**Use it when** a client pays for the work: qualifying the request, kickoff, keeping them informed, scope changes, their acceptance, and handing the product over.

**Do not use when** the team builds for itself: an internal change needs no contract, invoiced phases, or handover.

**The client reads and decides, and never runs aidd.** Every client document is a file the client can read, and the client's decision is a person's record from the client's own words. aidd writes those documents as Markdown, and as the HTML pages it already makes: the work-item page (`aidd status --html`) and, on request, an explainer deck. A PDF, a Word file, or a portal is the firm's own step.

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

1. Record `qualification` in the proposal before anyone drafts: fit, budget, authority, decision process. Write `unknown`, never a guess. Keep each gap in `questions`. Recommend `go`, `no_go`, or `questions_first`. A person records `go_no_go`.
2. An existing system: list what it does now, with `file:line`, before the scope ([references/verify-what-exists.md](references/verify-what-exists.md)).
3. In the first question round, ask the AI-use questions of the contract's `## AI use` section: may the client's code and data reach a model provider, where, and who owns what the agents write. aidd names the questions and writes no answer and no term. A person or a lawyer settles each with the client, and the model provider is a row of the vendor register.
4. After go, write the proposal's `## Delivery`: what the addressee provides, and tenant and environment setup. The contract holds the cadence. Add `phases`: each triggers on acceptance of listed ids, the listed Specs landed, or an event. A person sets each `due` date. Add the RAID entries, each with an owner and a status. A person sets every amount. Sign-off freezes the proposal.

### Where the records live

An engagement uses two repositories by default. The firm's home repository holds what is the firm's own: the proposal with its qualification, budget, and amounts, the contract, the change orders, the status reports, and the Intent. The client's repository holds the product: the code, the Specs, the tests, the docs, and the acceptance record with its Handover list. Run `aidd init` in each. A slice names its `repo`, and its Spec's `trace_id` points home (the aidd skill's `references/scale.md`, "Multi-repo").

One repository is allowed for a small engagement. Keep the firm's records in folders of their own, because the history carries them. The Handover list's Repository row says what the client receives and what is left out.

### Deliver

- Kickoff: run the contract's agenda. Turn each access or environment item into a `dependencies` entry with an owner and a date.
- Status: once accepted, the Intent holds the RAID log and the phases. Update the statuses and review the RAID log. A person records each phase's `finished_on`. Write the client status from `aidd status` on the cadence, with support against the contract. Never soften a red item.
- Contract: `aidd new contract <proposal id>` writes the statement of work, with its support levels, in the proposal's folder. Leave every "for a person or a lawyer" line to them. The contract is never legal advice.
- Change: a false assumption, a new request, or a slipped client task becomes the next change order, `aidd new contract <proposal id>` again. No scope, date, or price changes without one ([references/change-and-handover.md](references/change-and-handover.md)).
- Documents: write at the `plain` level (`aidd-team:plain-language`). Run [references/client-documents.md](references/client-documents.md) before sign-off.
- Vendors: `aidd new vendors` writes the vendor register. `aidd validate` warns 30 days before a renewal.

## Roll out

- Acceptance: run `aidd new acceptance`. List the Spec's Acceptance ids to accept, with their `aidd test` evidence. A person records each decision.
- Handover (`/aidd-team:handover`) opens the Handover list in the acceptance record. The accounts move to the client, and the team's access ends. The list asks whether the client keeps aidd, and it hands over who decides ([references/change-and-handover.md](references/change-and-handover.md)).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Engagement records check | the proposal, contract, vendor register, and acceptance record are valid; no renewal is due unnoticed | `aidd validate` over the repository |

## Stop if

- You are about to guess a qualification field instead of writing `unknown` and asking.
- Scope, a date, or a price would change without a change order a person decides.
- A secret would be written into the Handover list.
- You are about to soften a red status item.

## Hand off

- Done: the qualification, questions, RAID log, phases, and Delivery section current, or the Handover list ready. Next role: a person decides (go/no-go, sign-off, a change order, acceptance). Needs: every price, legal term, and client decision. Stopped at: none, or the stop rule's code.
