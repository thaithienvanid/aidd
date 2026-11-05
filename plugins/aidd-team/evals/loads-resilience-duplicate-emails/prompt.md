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

This repository uses aidd. Our worker sends the "order shipped" email through an outside mailer. When the mailer is slow, the call gives up, the task runs again, and customers get the same email twice. Stop that. Here is the code:

```python
def send_shipped_email(order):
    mailer.send(to=order.email, subject="Your order shipped", body=render(order))
```
