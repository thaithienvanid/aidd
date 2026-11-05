# Metrics dictionary: {{title}}

Written {{today}}. The repository's one metrics dictionary, at a fixed path (`aidd new metrics-dictionary`). The
product manager keeps it current. Each Spec's tracking plan (`aidd new analytics`) folds its new metrics and events into
it in the same change, so a metric or an event is named once. `aidd validate` warns about a tracking-plan event that is
not in it.

<!-- A metric is a number a person reads. An event is one thing the product records. A Spec's tracking plan holds its
     questions and its events before the code ships. This file holds what stays true after: one row per metric and
     one row per event, each with an owner. Reuse a row before you add one. Write the prose at the `ste-80` level (the
     `aidd-team:plain-language` skill). -->

## Naming convention

Events are named Object Action in Title Case, past tense (`Cart Viewed`, `Order Completed`). Properties are snake_case. TODO: or the project's own convention, by link.

## Metrics

| Metric | Definition | Events it counts | Baseline | Target | Owner | Introduced by |
| --- | --- | --- | --- | --- | --- | --- |
| TODO: checkout conversion | TODO: orders completed divided by carts viewed, per day | TODO Viewed | TODO | TODO | TODO | SPEC-? |

## Events

| Event (Object Action) | Trigger | Properties (name: type) | PII | Owner | Introduced by |
| --- | --- | --- | --- | --- | --- |
| TODO Viewed | TODO: the moment it fires, in the user's terms | TODO: cart_id: string | none | TODO | SPEC-? |
