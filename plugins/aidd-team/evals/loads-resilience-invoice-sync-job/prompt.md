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

This repository uses aidd. Our nightly sync pushes lab results to the hospital records API one by one. Some pushes come back with a 503 and that result is lost. I want it to keep trying sensibly. Here is the sync:

```python
def push_all(results):
    for result in results:
        records.post("/results", json=result.to_dict())
```
