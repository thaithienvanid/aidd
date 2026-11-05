---
description: 'A nearby request that adds no call across a process boundary leaves the resilience practice skill alone.'
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

This repository uses aidd. Add a short README section on timeouts. List the three settings below with one sentence each, and change no code or value.

```yaml
connect_s: 2
read_s: 10
total_s: 30
```
