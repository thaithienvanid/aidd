---
description: 'A bug report, a failing or flaky test, or a wrong result makes the agent load the debugging practice skill.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
  - debugging
  - claim:trigger:debugging
  - tier:description-change
---

This repository uses aidd. A customer paid 9.00 for a 2.5 kg parcel and should have paid 7.50. It was right last week. Here is the code. Please fix it.

```rust
const RATE_PER_KG: f64 = 3.0;

fn shipping_fee(weight_kg: f64) -> f64 {
    weight_kg.ceil() * RATE_PER_KG
}
```
