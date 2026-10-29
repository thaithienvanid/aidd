# Compliance: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec.

<!-- The compliance analyst's record of what binds this change, and how the change meets it (`aidd new compliance
     <topic> --spec <ID> --no-link`). The architect links it. An agent drafts it, and a person with the authority
     decides every open row before Spec approval. A sign-off given later goes in the living acceptance record.
     Link the Spec's Acceptance ids (A1, A2, ...) where a test proves a control. The Control id is the
     enterprise-controls pack's (EC-01 to EC-19) or the team's own. Separate several ids with commas.
     `aidd record export records --by-control` groups the gate records and this Spec's linked docs by Control id.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Obligations

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or gate record) | Owner |
| --- | --- | --- | --- | --- |
| TODO: EC-?? | TODO: the law, standard, or contract clause, by name and article | TODO: what the change does to meet it | TODO: the test (A?), the log, or the record that proves it | TODO |

## Accessibility statement

<!-- The information a service provider publishes under the European Accessibility Act, Directive (EU) 2019/882,
     Annex V, in its general terms and conditions or an equivalent document. Fill it from the accessibility test
     results: the last run on the base branch, and the Acceptance ids that prove this change on its head. When the
     results change after Spec approval, the published statement changes with the release, never this frozen
     document. Delete this section, with the reason, when the change ships no product or service the EAA covers. -->

- Service: TODO: a general description of the service, and how a person operates it (Annex V, points 1(a) and 1(b)).
- Conformance: TODO: how the service meets the requirements of Annex I (point 1(c)). Name the level the results show,
  such as EN 301 549 V3.2.1 or WCAG 2.1 AA, and the test run and its commit.
- Known exceptions: TODO: each failing criterion, why it fails, its workaround, and its fix date, or the
  disproportionate-burden assessment (Art. 14) that covers it.
- Contact: TODO: where a person reports a barrier or asks for the content in another format.
- Date: TODO: the date of the results the statement rests on, and its next review.

## DPIA

<!-- A data protection impact assessment, under GDPR Art. 35. Write it when the processing is likely to result in a
     high risk to people's rights and freedoms. The triggers are:
     - special categories or criminal data at scale
     - systematic monitoring of a public area
     - profiling or automated decisions with legal or similar effects
     - a new technology
     - large-scale tracking of location or behavior
     - matching or combining datasets
     - data about vulnerable people (children, patients, employees)
     - processing that stops people using a service.
     Two or more triggers make a DPIA the default. With none, write a one-line reason here. High residual risk means
     prior consultation with the authority (Art. 36). Delete this section, with the reason, when none applies. The
     records of processing are the data map's, never restated here. -->

### Processing

TODO: what personal data, whose, for what purpose, on what legal basis, kept how long, shared with whom.

### Consultation

<!-- Whose views were sought, and what changed because of them: the data subjects or their representatives where
     appropriate (Art. 35(9)), the processors, and the DPO, whose advice the controller must seek (Art. 35(2)). -->

TODO: who was consulted, and what they said.

### Necessity and proportionality

TODO: why this data is needed for the purpose, and why less would not do.

### Risks and mitigations

<!-- The same threat table as the threat model, with LINDDUN rows for the risks to people. Risk is the harm to
     people: its likelihood (remote, possible, probable) times its severity (minimal, significant, severe), as low,
     medium, or high, on the ICO's DPIA scale. A high risk left after the mitigations means prior consultation. -->

| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Risk | Mitigation | Acceptance id | Owner |
| --- | --- | --- | --- | --- | --- |
| Linking: TODO | | TODO | | | |
| Identifying: TODO | | TODO | | | |
| Data disclosure: TODO | | TODO | | | |
| Unawareness: TODO | | TODO | | | |
| Non-compliance: TODO | | TODO | | | |

### Residual risk

TODO: the likelihood and severity to people after the mitigations, and whether prior consultation (Art. 36) applies.
The DPO's advice and decision come after Spec approval. They go in the living acceptance record (`aidd new
acceptance`), never in this frozen document.

[spec]: {{spec_link}}
