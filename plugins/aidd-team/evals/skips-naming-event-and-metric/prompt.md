---
description: 'A nearby request that is not about choosing or improving a name leaves the naming practice skill alone.'
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
  - naming
  - claim:trigger:naming
  - tier:description-change
---

This repository uses aidd. Which event does this handler consume, and which metric does it count? Answer from the code only.

```python
@on("order_shipped")
def shipped(event):
    metrics.inc("orders_shipped_total")
```
