# Rights and records: the privacy-by-default detail

Articles are the GDPR's. The data map (`aidd new data-map`) is the one place the facts live. Every
table below reads from it, and no Spec copies it.

## Classification

| Class | Examples | Default handling |
| --- | --- | --- |
| Public | a display name the person published | no restriction beyond integrity |
| Internal | an account id, a flag state | not in public responses |
| Personal | email, phone, address, IP address, device id, order history | minimised, access-controlled, out of logs, retention set |
| Special category (Art. 9) or criminal (Art. 10) | health, biometric, genetic, ethnic origin, beliefs, union membership, sex life, offences | an Art. 9(2) condition beside the lawful basis, encrypted at rest with a separate key, a DPIA considered every time |

A field no one can classify is personal until someone decides otherwise.

## Lawful basis per purpose (Art. 6)

One purpose, one basis: an email for sign-in (contract) and for a newsletter (consent) is two rows. Consent is never the
basis for what the service cannot run without. Legitimate interests needs its balancing test written down.

| Basis | Art. 6(1) | Typical purpose | What changes when the person objects or withdraws |
| --- | --- | --- | --- |
| Consent | (a) | marketing email, optional analytics, non-essential cookies | processing stops; the data is deleted unless another row's basis covers it |
| Contract | (b) | the account, the order, delivery | nothing until the contract ends; then the retention clock starts |
| Legal obligation | (c) | invoices kept for tax law | nothing: the law sets the retention |
| Vital interests | (d) | an emergency contact, in an emergency | rare; name the case |
| Public task | (e) | a public body's statutory function | the objection right applies (Art. 21) |
| Legitimate interests | (f) | fraud prevention, service security | processing stops unless compelling grounds override (Art. 21) |

## Data-subject rights endpoints

Each right the change touches is an endpoint (or an audited admin action), an Acceptance item, and a test. The answer is
due within one month, extendable by two for complex requests (Art. 12(3)). The identity check collects no more than the
account holds.

| Right | Article | Endpoint shape | What it must touch | Test |
| --- | --- | --- | --- | --- |
| Access | Art. 15 | `GET /me/data` or an admin export | every mapped store, plus the purposes, recipients, retention, and source | Export completeness test |
| Rectification | Art. 16 | `PATCH /me/profile` | every copy: stores, caches, search indexes, processors | Rectify and restrict test |
| Erasure | Art. 17 | `DELETE /me` or an erase queue | every mapped store; processors told (Art. 19); backups expire or are crypto-shredded | Erase request test |
| Restriction | Art. 18 | `POST /me/restrict` | a flag every downstream job reads: the data is kept, not processed | Rectify and restrict test |
| Portability | Art. 20 | `GET /me/export` in JSON or CSV | what the person provided, under consent or contract, machine-readable | Export completeness test |
| Objection | Art. 21 | `POST /me/object` with the purpose | the purposes on legitimate interests or public task; direct marketing stops at once | Rectify and restrict test |
| Automated decisions | Art. 22 | a human-review route | a decision with legal or similar effect made without a person | the review route reaches a person |

An erasure keeps what a legal obligation requires (an invoice) and says so; everything else goes.

## Consent record (Art. 7)

Per person and purpose: the notice version shown, the time, how it was given, and the time of withdrawal,
one action from the same place. Consent is never bundled with the terms, never pre-ticked. Children add verifiable parental consent (`aidd-team:products-for-children`).

## Privacy notice hooks (Art. 13 and 14)

A new purpose, processor, transfer, or retention in the data map changes the notice in the same change. The Spec names the
hook: the notice file or CMS entry, and the version it bumps. Data collected from someone else (Art. 14) is noticed
within one month.

## Retention schedule and deletion jobs

Every data-map row has a period and a trigger ("24 months after the last order"). Each becomes a scheduled job. It
deletes, anonymises (irreversibly, not a hash of the email), or crypto-shreds (destroys the per-subject key), logs a
count, and alerts on failure.

## Processors and subprocessors (Art. 28)

The data map's register lists each processor: the service, the data items, the location, the Art. 28 contract and its
date, and how customers hear of a new subprocessor. A new processor in a diff (an SDK, an API client, a webhook) without
a row is a Review finding.

## International transfers (Art. 44-49)

Any access from outside the EEA is a transfer, a processor's support staff included. The data map's Transfers column
names its mechanism: adequacy (Art. 45), SCCs with a transfer impact assessment (Art. 46), BCRs (Art. 47), or a
narrow derogation (Art. 49).

## Owned elsewhere

The DPIA (Art. 35) lives in the compliance doc (`aidd new compliance`), and the records of processing are the data map's
columns (`aidd new data-map`). The breach clocks (Art. 33 and 34, and the other regimes) are `aidd-team:incident-response`'s.

## Test-data masking

Fixtures, seeds, snapshots, and staging data are synthetic, or masked one way with the format kept (an email on
`example.com`). A copy of production into a lower environment has its own data-map row, or it does not happen.

## CCPA/CPRA, the comparable US regime

- Notice at collection is the notice hook.
- Know, delete, and correct map to access, erasure, and rectification.
- The opt-out of sale or sharing is a consent-like switch that honours the Global Privacy Control signal.
- Sensitive personal information has a use limit.
- A service provider contract plays Art. 28's role.

Build the endpoints once, map both laws.
