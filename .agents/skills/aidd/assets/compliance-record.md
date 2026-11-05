# Compliance: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec. The control register
(`aidd new control-register`) holds each control once, so fold this record's controls into it in the same change.

<!-- The compliance analyst's record of what binds this change, and how the change meets it (`aidd new compliance-record
     <topic> --spec <ID> --no-link`). The architect links it. An agent drafts it, and a person with the authority
     decides every open row before Spec approval. A sign-off given later goes in the living acceptance record.
     Link the Spec's Acceptance ids (A1, A2, ...) where a test proves a control. The Control id is the
     enterprise-controls pack's (`references/controls.md`) or the team's own. Separate several ids with commas.
     A service sold to EU consumers also publishes an accessibility statement (Directive (EU) 2019/882, Annex V). It is a
     living, published text, never part of this frozen record. With aidd-team, `aidd-team:accessible-ui` gives its
     parts in `references/statement.md`.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Obligations

| Control id | Obligation (law or standard, article) | Control | Evidence (test, file, or `aidd test` evidence) | Owner |
| --- | --- | --- | --- | --- |
| TODO: EC-?? | TODO: the law, standard, or contract clause, by name and article | TODO: what the change does to meet it | TODO: the test (A?), the log, or the record that proves it | TODO |

## DPIA

<!-- A data protection impact assessment, under GDPR Art. 35. Write it when the processing is likely to result in a
     high risk to people's rights and freedoms. The nine criteria are the Article 29 Working Party's (WP248 rev.01):
     1. evaluation or scoring, including profiling and predicting
     2. automated decision-making with legal or similarly significant effect
     3. systematic monitoring, including through networks or of a publicly accessible area
     4. sensitive data or data of a highly personal nature (special categories, Art. 9; criminal-offence data, Art. 10)
     5. data processed on a large scale
     6. matching or combining datasets
     7. data about vulnerable people (children, patients, employees)
     8. innovative use of a technology or an organizational solution
     9. processing that itself stops people exercising a right or using a service or a contract.
     Two or more criteria make a DPIA the default. With none, write a one-line reason here. High residual risk means
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

<!-- Each risk to people is a LINDDUN row of the component's threat model, its one home, with its Risk on the ICO's
     DPIA scale, its Mitigation, and its Acceptance id. Link the model and list the ids. Never copy a row here. The
     model is living, so the DPIA cites its rows as of this doc's commit, and git history holds that version. A high
     risk left after the mitigations means prior consultation. -->

TODO: the threat model's path, and the LINDDUN threat ids this change adds or changes (Linking, Identifying, Data
disclosure, Unawareness, Non-compliance).

### Residual risk

TODO: the likelihood and severity to people after the mitigations, and whether prior consultation (Art. 36) applies.
The DPO's advice and decision come after Spec approval. They go in the living acceptance record (`aidd new
acceptance`), never in this frozen document.

[spec]: {{spec_link}}
