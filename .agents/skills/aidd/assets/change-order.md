# Change order CO-{{number}}: {{proposal}}

Contract: `../contract.md` of {{proposal}} (`../proposal.md`). Written {{today}}. A person fills in the client's
decision after this change order is sent.

<!-- `aidd new contract <proposal id>` writes the next change order once the contract exists. A change order changes
     what the client agreed to buy. It is not aidd's Change Request (the block in a PR/MR that points at the Spec).
     Once a person records the client's decision, the Spec changes to match and goes back through Spec approval. An
     agent may draft the delta. The price, the time, and the client decision fields are for humans only.
     Write for the client at the `plain` level (the `aidd-team:plain-language` skill). -->

## Scope delta

<!-- What is added, removed, or changed, in the client's words, and what stays out. -->

| Change | Added, removed, or changed | Reason |
| --- | --- | --- |
| TODO | added | TODO: a new request, or an assumption that proved false (its RAID id) |

## Affected work

| Spec | Acceptance ids | Effect |
| --- | --- | --- |
| TODO: SPEC-1 | TODO: A? | TODO: new, changed, or dropped |

## Price and time delta

<!-- A person fills this in: an agent never sets the commercial terms. -->

| Price delta | Time delta | New due date of the affected milestones | Basis |
| --- | --- | --- | --- |
| | | | |

## Client decision

<!-- Only humans fill this in, from the client's own record (a signed document, an email), never an agent. -->

| Decision (approved, rejected, deferred) | By | Date | Record |
| --- | --- | --- | --- |
| | | | |

Once the client approves, a person changes the proposal to match and signs it off again: they type `sign off <proposal id>`.
