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

This repository uses aidd. The trip page asks the weather system for a forecast. When that system is down, the page hangs and then fails for every visitor. What should the call do? Here it is:

```python
def forecast(city):
    return requests.get(f"http://weather/forecast/{city}").json()["summary"]
```
