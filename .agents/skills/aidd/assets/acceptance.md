# Acceptance record: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. A living doc (`frozen: false`). Humans fill it in after Spec approval: when
the change is accepted, and when a person gives a sign-off.

<!-- This record is for any project. It records which of the Spec's Acceptance ids a person accepted by hand (the
     Spec's `manual_acceptance: true`), when, by whom, and on what evidence. With a client, the client accepts. With
     no client, the product owner or the QA owner does, and Sign-offs holds the user acceptance and the DPO's
     decision. The ids are the Spec's own (A1, A2, ...), never new ones. A person fills the rows from the record of
     whoever accepted, never an agent. A rejected id is a defect, or a change order with a client
     (`aidd new contract <proposal id>` once the contract exists), never an edit to this record. Handover is for a
     client engagement only: delete it otherwise.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

| Acceptance id | Accepted | By | Date | Evidence |
| --- | --- | --- | --- | --- |
| A1 | | | | |

## Environment and build

- Environment: TODO: where it ran, a (simulated) operational one (staging, a client's test tenant, a device).
- Build accepted: TODO: the commit.

## Open defects

<!-- A conditional acceptance rests on these: one row per defect the accepter knew of and accepted. Write "none" if so. -->

| Defect | Severity | Agreed disposition |
| --- | --- | --- |
| TODO: the issue or Spec id | TODO | TODO: fix before release, fix in a named Spec, or accept as is |

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
     (`/aidd-team:handover`). The delivery manager lists the items, and this table is the one list of them. A person
     marks each item done from the client's own record. Name each credential with where it now lives, never a secret
     itself. The rows run in the order a handover goes. First what passes: the code, the docs, the licences, the accounts,
     and the credentials. Then the people (training), then what stays open (issues and the warranty). Last, what ends
     or stays with the firm: the client's data, the agent setup, and who decides. With one repository for the
     engagement, the history holds the firm's own records, so the first row says what the client gets and what is
     left out. -->

| Item | Where | Done by | Date |
| --- | --- | --- | --- |
| Repository: the code and its history that the client receives, and the firm's own records left out | TODO: the client's repository | | |
| Docs index: the user, admin, and API docs, the runbooks, and the architecture overview | TODO | | |
| Third-party licences: each component's licence, and where it was checked | TODO | | |
| Vendor accounts: each account (hosting, email, payments, a model provider) now in the client's name or closed, and the vendor register updated | TODO | | |
| Credentials transfer log: each account or key, who held it, who holds it now, rotated on | TODO: the vault entry | | |
| Training sessions log: who was trained on what, the recording, and the date the client's operators ran a runbook once with us | TODO | | |
| Open issues: each known defect or gap, with its Spec or issue | TODO | | |
| Warranty start: the date the warranty in the contract begins and ends, and the support levels that apply after it | TODO | | |
| Client's data: returned to the client, then deleted from the team's systems and every agent's storage, or kept for a reason the client gave in writing | TODO: the date, and who confirmed it | | |
| Agent setup: what stays of aidd and the agents (the config, the ask rules, the team's files, the records), what is removed, and every agent's access and key ended | TODO | | |
| Who decides: whether the client keeps aidd. If so, the client's approvers in `owners.approvers`, and who answers each ask. If not, the client's own rule for who decides a change, merges it, and releases it | TODO | | |

[spec]: {{spec_link}}
