# Acceptance record: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. A living doc (`frozen: false`). Humans fill it in after Spec approval: when
the client accepts, and when a person gives a sign-off.

<!-- This record is for a client who accepts the work by hand (the Spec's `uat: true`), such as an agency's client.
     It records which of the Spec's Acceptance ids the client accepted, when, by whom, and on what evidence. The ids
     are the Spec's own (A1, A2, ...), never new ones. A person fills the rows from the client's own record, never an
     agent. A rejected id is a defect or a change order (`aidd new contract <proposal id>` once the contract exists),
     never an edit to this record.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

| Acceptance id | Accepted | By | Date | Evidence |
| --- | --- | --- | --- | --- |
| A1 | | | | |

## Notes

TODO: the environment and build the client accepted on, and anything they accepted with a condition.

## Sign-offs

<!-- The decisions humans give after Spec approval go here. A frozen doc cannot hold them without voiding it. They are:
     - the user acceptance that the test plan names
     - the DPO's decision on the compliance record's DPIA
     - any other sign-off that the Spec's docs ask for.
     A person fills each row, never an agent. -->

| Sign-off | By | Decision | Date | Evidence |
| --- | --- | --- | --- | --- |
| User acceptance (test plan) | | | | |
| DPO advice and decision (DPIA) | | | | |

## Handover

<!-- For a client engagement: what passes to the client's team when the client accepts the work
     (`/aidd-team:handover`). The delivery manager lists the items. The runbook's Handover section holds the
     operational side. A person marks each item done from the client's own record. Name each credential with where it
     now lives, never a secret itself. -->

| Item | Where | Done by | Date |
| --- | --- | --- | --- |
| Docs index: the user, admin, and API docs, the runbook, and the architecture overview | TODO | | |
| Credentials transfer log: each account or key, who held it, who holds it now, rotated on | TODO: the vault entry | | |
| Training sessions log: who was trained on what, and the recording | TODO | | |
| Open issues: each known defect or gap, with its Spec or issue | TODO | | |
| Warranty start: the date the warranty in the contract begins, and its end | TODO | | |

[spec]: {{spec_link}}
