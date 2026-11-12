# What a change adds, removes, and moves: a worked example

Draw the after state. Give each node a class, and keep the removed ones, dashed, so the reviewer sees what goes. A moved node takes `changed`. Add a table keyed by node id, so the delta reads without color. The classes here are the border-only ones from [craft.md](craft.md) (D14); a project with a palette in its DESIGN.md copies its own lines instead. The chain runs top-down, so the code's long names keep their full size (D9).

```mermaid
flowchart TD
  accTitle: Retry added to the payment call
  accDescr: Checkout now calls a new retry wrapper, which calls the payment client. The direct call to the legacy charge is removed.
  checkout["checkout.place_order"]
  retry["payments.with_retry"]:::added
  client["payments.client"]:::changed
  legacy["payments.legacy_charge"]:::removed
  checkout -->|charge request| retry
  retry -->|charge request| client
  checkout -.->|old call| legacy
  classDef default fill:#747a8333,stroke:#747a83,stroke-width:1px
  classDef added fill:#158a5726,stroke:#158a57,stroke-width:2px
  classDef changed fill:#ad6a0a26,stroke:#ad6a0a,stroke-width:3px
  classDef removed fill:#d04c4c26,stroke:#d04c4c,stroke-width:2px,stroke-dasharray:6 4
```

Legend: a thick border is a node the change adds or alters, and a dashed one a node it removes, as the table says.

| Node id | Change | What |
| --- | --- | --- |
| `retry` | added | retries a timed-out charge up to three times |
| `client` | changed | its timeout moves from 30 s to 10 s |
| `legacy` | removed | no caller is left, so it goes |
