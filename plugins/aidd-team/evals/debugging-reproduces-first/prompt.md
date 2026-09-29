---
description: A reported bug is reproduced as a failing test on the exact symptom before the code is changed, and the regression test exercises the real function rather than a stub.
plugins:
  - "../.."
  - "../../../.."
max_turns: 30
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Write
  - Edit
tags:
  - practice
---

A customer says their invoice was wrong: an order of 10 items at 3.00 each with the 10% bulk discount came to 30.00 instead of 27.00. It broke after last week's change. Here is the code, in `pricing.py`:

```python
BULK_THRESHOLD = 10
BULK_RATE = 0.10


def order_total(quantity: int, unit_price: float) -> float:
    subtotal = quantity * unit_price
    if quantity > BULK_THRESHOLD:
        subtotal -= subtotal * BULK_RATE
    return round(subtotal, 2)
```

Please fix it.
