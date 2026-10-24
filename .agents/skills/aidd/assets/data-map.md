# Data map: {{title}}

Written {{today}}. The repository's one data map, at a fixed path. The compliance analyst keeps it
current. Each Spec that adds, moves, shares, or deletes personal data revises it in its own diff. That Spec links it as
a living doc (`docs` kind `data-map`, `frozen: false`).

<!-- One file that is both the personal-data inventory and the records of processing activities (GDPR Art. 30). Write
     it once for the product (`aidd new data-map`), never one per Spec. One row per data item and purpose: the same
     email used for sign-in and for marketing is two rows, with two lawful bases. Describe the data, never copy it: no
     real value goes in here. The erasure and export tests read this table. A row that a store does not honor is then
     a failing test, not a note.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

Controller: TODO: the legal entity, its contact, and its representative in the EU if it has one (Art. 27).
Data protection officer: TODO: name and contact, or "none designated" with the reason (Art. 37).
Last reviewed: {{today}} by TODO.

## Records of processing

<!-- What goes in each column:
     - Category: identity, contact, account, financial, location, device and online identifiers, usage, content, a
       special category (Art. 9), or criminal data (Art. 10). The special categories are health, biometric, genetic,
       racial or ethnic origin, political opinions, religious or philosophical beliefs, trade-union membership, and sex
       life or orientation. Mark a special category or criminal data "special", and name the Art. 9(2) condition beside
       the lawful basis.
     - Lawful basis (Art. 6(1)): consent, contract, legal obligation, vital interests, public task, or legitimate
       interests (with the balancing test's location).
     - Retention: a period and its trigger ("24 months after the last order"), never "as long as needed".
     - Deletion method: hard delete, anonymisation, or crypto-shredding, and the job that runs it, including backups.
     - Transfers: each country outside the EEA and its mechanism (adequacy, SCCs, BCRs), or "none". -->

| Data item | Category | Purpose | Lawful basis | Source | Systems and stores | Processors | Retention | Deletion method | Transfers | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TODO: such as `customer.email` | TODO: contact | TODO: send the order confirmation | TODO: contract, Art. 6(1)(b) | TODO: the data subject, at checkout | TODO: `customers` table, search index, backups | TODO: the email service | TODO: 24 months after the last order | TODO: the nightly erasure job; backups expire in 35 days | TODO: US, EU-US DPF | TODO |

## Data subjects and recipients

| Data subjects | Recipients (internal teams, processors, third parties, authorities) |
| --- | --- |
| TODO: customers, prospects, employees, children (then the products-for-children pack applies) | TODO |

## Processors and subprocessors

<!-- Every processor named in the table above, with its Art. 28 contract. Then the public subprocessor list, and the
     notice given to customers before a new one is added. -->

| Processor | Service | Data items | Location | Contract (Art. 28) and date | Subprocessor notice |
| --- | --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | TODO | TODO: where customers are told, and how far ahead |

## Security measures

TODO: a general description of the technical and organisational measures (Art. 32): encryption at rest and in transit,
access control, pseudonymisation, and logging. Also state where the threat model that details these measures lives.

## Changes

| Date | Spec | What changed |
| --- | --- | --- |
| {{today}} | | First version. |
