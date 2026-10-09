# Contract (statement of work): {{proposal}}

Proposal: {{proposal}} (`proposal.md` beside this file). Written {{today}}. This file sits in the proposal's folder,
beside its change orders (`change-orders/CO-<n>.md`). People revise it only through change orders. The signed copy is
the client's record, not this file.

<!-- A base for a statement of work (SOW). `aidd new contract <proposal id>` writes it once the proposal is accepted.
     It states what the engagement delivers in the terms the team already keeps: Acceptance ids, and the proposal's
     milestones and RAID log. It points at them instead of copying them, so the contract and the delivery say one
     thing. It is not legal advice.
     The delivery manager drafts the scope, deliverables, and acceptance. A person writes every price, legal term, and
     clause marked "for a person or a lawyer". A lawyer reviews the contract where the law or the amount calls for one.
     Never copy another client's contract in here.
     Write for the client at the `plain` level (the `aidd-team:plain-language` skill). -->

Parties: TODO: for a person or a lawyer: the legal names, addresses, and signatories.

## Scope

<!-- One row per deliverable piece of work, by the Spec's Acceptance ids, so "done" means the tests the client can see.
     A need the proposal answered `not_met` is never in scope. -->

| Spec | Acceptance id | What the client gets |
| --- | --- | --- |
| TODO: SPEC-1 | A1 | TODO |

## Deliverables

- TODO: the software, its source and where it is delivered, the documentation, and the training.

## Milestones

The milestones are the proposal's `milestones`, as signed off. From acceptance, they are the Initiative's (`aidd
proposal convert` copies them). Each milestone has a due date, a trigger, and an amount. The trigger is the acceptance
of listed ids, the listed Specs shipped, or an event. `aidd proposal matrix` on the proposal renders the table to
attach. This contract names the milestones by id and never copies a date or an amount.

## Assumptions and exclusions

- Assumptions: the proposal's `assumptions` (its RAID log), by id; an assumption that proves false is a change order.
- Exclusions: the proposal's `exclusions`, as signed off.
- Client responsibilities: TODO: the access, data, decisions, and people the client provides, and by when (the
  proposal's `dependencies`, by id).

## Change control

Any change to scope, dates, or price is a change order. `aidd new contract {{proposal}}` writes the next one,
`change-orders/CO-<n>.md`. It holds the delta, the affected Acceptance ids, and the price and time that a person sets.
A change order binds once the client's decision is recorded. Then the Spec changes to match and goes back through Spec
approval.

## Acceptance

- Acceptance criteria: the Acceptance ids in Scope, shown on the acceptance environment with the evidence the gate
  recorded.
- Acceptance period: TODO: for a person: the business days the client has to accept or reject, and what happens when
  they do neither.
- The client's decision on each id goes in the acceptance record (`aidd new acceptance`). A rejected id is a defect
  or a change order.

## Support and service levels

<!-- The support the client gets after go-live or after the warranty: who answers, how fast, and how it is measured.
     The targets are commitments that a person agrees with the client. An agent never changes one. A service level
     objective (`aidd new slo`) is the system's reliability target. This schedule is the people's support target. -->

- Tiers: TODO:
  - tier 1: intake, triage, and known answers from the knowledge base (the support desk or the client's service desk)
  - tier 2: defects and configuration, through the loop (the delivery team)
  - tier 3: platform and third-party faults (the vendor or the original author).
- Channels and hours: TODO: where issues are filed, the phone line for S1 only, the support hours and time zone, and
  the public holidays excluded.

Response means a person acknowledges and triages. Resolution means fixed, or worked around with the fix scheduled.
Both are measured inside the support hours, unless a row says 24x7:

| Severity | Meaning | Response | Resolution |
| --- | --- | --- | --- |
| S1 | Production down or data at risk, no workaround | TODO: 1 hour, 24x7 | TODO: 8 hours |
| S2 | A main function degraded, a workaround exists | TODO: 4 hours | TODO: 3 business days |
| S3 | A minor function affected | TODO: 1 business day | TODO: the next release |
| S4 | A question or a request for change | TODO: 2 business days | TODO: planned as a change order |

- Escalation: TODO: the support desk, then the delivery manager, then the named client and supplier owners. Give each
  one the time after which you call the next one.
- Maintenance windows: TODO: the planned window, the notice given before it, and how an emergency change is announced.
- Exclusions: TODO: changes to scope (a change order), faults in systems the client runs, misuse, and third-party
  outages beyond their own SLA.
- Reporting: the delivery manager reports every TODO: month. The report holds the issues by severity, attainment
  against this table, each breach with its cause, and the knowledge-base articles added.

## Warranty

TODO: for a person or a lawyer:

- the warranty period, from the warranty start in the acceptance record's Handover
- what it covers (defects against the accepted Acceptance ids), and what it does not
- the support levels above that apply after it.

## Intellectual property and licensing

TODO: for a person or a lawyer:

- who owns the delivered code and documents
- the licence to pre-existing and open-source components (the repository lists their licences)
- what the team may reuse.

## Confidentiality

TODO: for a person or a lawyer: what is confidential, for how long, and who may see it. The client's material stays in
its proposal's folder and this engagement's documents, never reused for another client without permission.

## Signatures

<!-- Only people fill this in, from the signed copy, never an agent. -->

| Party | Name | Role | Date |
| --- | --- | --- | --- |
| | | | |
