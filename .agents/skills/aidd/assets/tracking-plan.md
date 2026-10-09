# Tracking plan: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec.

<!-- The product manager's tracking plan: the events that measure the Spec's `hypothesis`, written before the code that
     fires them. `aidd validate` asks for one when the Spec has a hypothesis. An event nobody reads is cost and risk: every
     row answers a question below.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Questions and metrics

| Question | Metric | Events |
| --- | --- | --- |
| TODO: does the change move the hypothesis metric? | TODO: the metric, its baseline, and its target | TODO |

## Naming convention

Events are named Object Action in Title Case, past tense (`Cart Viewed`, `Order Completed`); properties in snake_case. TODO: or the project's own convention, by link.

## Events

| Event (Object Action) | Trigger | Properties (name: type) | Required | PII | Owner | Platforms |
| --- | --- | --- | --- | --- | --- | --- |
| TODO Viewed | TODO: the moment it fires, in the user's terms | TODO: cart_id: string, item_count: integer | cart_id | none | TODO | web, iOS, Android |

## Experiment

<!-- Only when the Spec has an `[experiment]` table; delete it otherwise. The exposure event fires once per unit when
     the flag assigns a variant. The analysis joins the metric events to it. Without it, no result is trustworthy. -->

| Event (Object Action) | Trigger | Properties (name: type) | Answers |
| --- | --- | --- | --- |
| Experiment Viewed | the first time the unit sees a variant | experiment: string, variant: string | the sample ratio check and the join |
| TODO | the primary metric's event | TODO | `experiment.metric` |
| TODO | each guardrail's event | TODO | `experiment.guardrails` |

## Identity

<!-- How a person is identified across sessions and devices: the anonymous id, the user id once known, and when they
     are joined. Then what is never sent (an email, a name, a free-text field). -->

TODO: the identity model.

## QA

<!-- How a wrong event is caught before it pollutes the data. The events are validated against a schema (a JSON
     Schema per event, in the Spec's tests). This runs in CI and in a staging stream. A missing required property fails
     the test. -->

TODO: the schema validation and where it runs.

[spec]: {{spec_link}}
