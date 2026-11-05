# What a change adds, removes, and moves: a worked example

Draw the after state. Give each node a class, and keep the removed ones, dashed, so the reviewer sees what goes. A moved node takes `changed`. Add a table keyed by node id, so the delta reads without color.

```mermaid
flowchart LR
  accTitle: Retry added to the payment call
  accDescr: Checkout now calls a new retry wrapper, which calls the payment client. The direct call to the legacy charge is removed.
  checkout["checkout.place_order"]
  retry["payments.with_retry"]:::added
  client["payments.client"]:::changed
  legacy["payments.legacy_charge"]:::removed
  checkout -->|charge request| retry
  retry -->|charge request| client
  checkout -.->|old call| legacy
  classDef added stroke-width:3px,stroke:#1a7f37
  classDef changed stroke-width:3px,stroke:#9a6700
  classDef removed stroke-width:2px,stroke:#cf222e,stroke-dasharray:5 3
```

| Node id | Change | What |
| --- | --- | --- |
| `retry` | added | retries a timed-out charge up to three times |
| `client` | changed | its timeout moves from 30 s to 10 s |
| `legacy` | removed | no caller is left, so it goes |
