---
description: A charge wrapped in a broad retry at two layers is recognized as a double-charge risk; the answer uses an idempotency key or a durable record with a dedupe key, a timeout, one retry layer, and a lost-acknowledgement test.
plugins:
  - "../.."
  - "../../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - practice
---

Our payment call sometimes times out and customers end up not charged, so I added retries. The queue worker that calls this also retries a failed job three times. Can you make it more reliable before I ship it?

```python
import time

import requests


def charge(order_id: str, amount_cents: int) -> dict:
    for attempt in range(5):
        try:
            response = requests.post(
                "https://payments.example.test/v1/charges",
                json={"order": order_id, "amount": amount_cents},
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            time.sleep(1)
    return {"status": "unknown"}
```
