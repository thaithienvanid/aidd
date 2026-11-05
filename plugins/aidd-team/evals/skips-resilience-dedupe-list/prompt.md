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

This repository uses aidd. Remove the duplicates from this list in plain Python, keeping the first occurrence of each item.

```python
items = ["b", "a", "b", "c", "a"]
```
