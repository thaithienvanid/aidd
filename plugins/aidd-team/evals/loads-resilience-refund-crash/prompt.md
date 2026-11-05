---
description: 'Code that calls a service, queue, or provider, with a timeout, a retry, or a duplicate, makes the agent load the resilience practice skill.'
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
  - resilience
  - claim:trigger:resilience
  - tier:description-change
---

This repository uses aidd. A refund calls the card processor, then marks the order refunded in our database. If the process dies between the two steps, the customer is refunded but the order still shows paid. Make it safe to run again. Here is the code:

```python
def refund(order):
    processor.refund(order.charge_id, order.total)
    order.status = "refunded"
    order.save()
```
